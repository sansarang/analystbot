"""SEC-1 — API 키가 저장·로그·알림에 **평문으로 남지 않는다.**

🔴 실사고 2026-09-07: 오염된 `GROQ_API_KEY` 값 안에 NVIDIA·OPENROUTER 키가
   함께 들어 있었고, 그 문자열이 **운영 로그에 평문으로** 찍혔다. 그리고
   `ledger.record_outage` 가 `detail[:200]` 을 원문 그대로 Redis 에 넣어
   `llm_outage:*` 211행이 **TTL 14일** 동안 조회 가능한 상태로 남았다.

⚠️ 반대 위험을 함께 잰다 — 마스킹이 넓으면 "무엇이 실패했는지"가 사라진다.
   진단에 필요한 문구(상태 코드·오류 종류·모델명)는 **그대로 남아야** 한다.
"""
import logging

import pytest

from app.secrets_mask import install_log_filter, mask_secrets

# 형태만 진짜와 같게 만든 가짜 키 (실제 키가 아니다)
FAKE = {
    "groq":       "gsk_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4",
    "nvidia":     "nvapi-" + "zY9xW8vU7tS6rQ5pO4nM3lK2jI1hG0fE9dC8bA7z6y5x4w3v2u1t0s",
    "openrouter": "sk-or-v1-" + "0123456789abcdef0123456789abcdef0123456789abcdef01234567",
    "anthropic":  "sk-ant-api03-" + "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH",
    "gemini":     "AIza" + "SyD-1234567890abcdefghijklmnopqrstuvw",
    "xai":        "xai-" + "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKL",
    "perplexity": "pplx-" + "abcdefghijklmnopqrstuvwxyz0123456789abcdefghijkl",
}


@pytest.mark.parametrize("name,key", sorted(FAKE.items()))
def test_알려진_키는_가려진다(name, key):
    out = mask_secrets(f"Error code: 401 — invalid api key {key} for {name}")
    assert key not in out, f"{name} 키가 그대로 남았다"
    assert "…" in out or "*" in out


def test_한_문자열에_키가_여럿이면_전부_가린다():
    # 실사고의 형태 — 한 값 안에 키 셋이 섞여 있었다
    raw = f"GROQ_API_KEY={FAKE['groq']} NVIDIA_API_KEY={FAKE['nvidia']} OR={FAKE['openrouter']}"
    out = mask_secrets(raw)
    for k in (FAKE["groq"], FAKE["nvidia"], FAKE["openrouter"]):
        assert k not in out


def test_헤더와_쿼리스트링도_가린다():
    tok = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
    assert tok not in mask_secrets(f"Authorization: Bearer {tok}")
    assert tok not in mask_secrets(f"https://x.example/v1?key={tok}&model=m")
    assert tok not in mask_secrets(f"https://x.example/v1?api_key={tok}")


def test_진단_문구는_살아남는다():
    """반대 위험 — 마스킹이 진단을 삼키면 안 된다."""
    raw = ("anthropic(matchup): Error code: 400 - {'type':'invalid_request_error',"
           "'message':'Your credit balance is too low'}")
    out = mask_secrets(raw)
    assert out == raw, "키가 없는 문자열은 한 글자도 바뀌면 안 된다"
    keep = mask_secrets(f"groq 429 rate_limit model=gpt-oss-120b key={FAKE['groq']}")
    for word in ("groq", "429", "rate_limit", "gpt-oss-120b"):
        assert word in keep


def test_가린_뒤에도_어느_provider_인지는_남는다():
    out = mask_secrets(FAKE["groq"])
    assert out.startswith("gsk_"), "접두사는 남겨 어느 키인지 알 수 있어야 한다"


def test_None_과_빈문자열은_그대로():
    assert mask_secrets("") == ""
    assert mask_secrets(None) is None


@pytest.mark.asyncio
async def test_record_outage_는_저장_전에_가린다():
    """🔴 이것이 SEC-1 의 본체 — Redis 에 평문이 들어가면 TTL 14일간 남는다."""
    from app.llm import ledger

    captured = []

    class _FakeRedis:
        async def lpush(self, key, value):
            captured.append((key, value))
        async def ltrim(self, *a, **kw):
            pass
        async def expire(self, *a, **kw):
            pass

    await ledger.record_outage(_FakeRedis(), "groq", "matchup", "auth",
                               detail=f"401 invalid key {FAKE['groq']}")
    assert captured, "기록이 남지 않았다"
    _key, payload = captured[0]
    assert FAKE["groq"] not in payload
    assert "401" in payload and "groq" in payload   # 진단은 남는다


def test_로그_필터가_설치되면_평문이_안_찍힌다(caplog):
    logger = logging.getLogger("test.sec1")
    install_log_filter(logger)
    with caplog.at_level(logging.WARNING, logger="test.sec1"):
        logger.warning("[llm] 실패 %s", f"key={FAKE['nvidia']}")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE["nvidia"] not in text
    assert "[llm] 실패" in text


def test_서비스_진입점_셋에_필터가_걸려_있다():
    """등록은 배선이 아니다 — 세 진입점이 실제로 이 함수를 부르는지 본문에서 본다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for rel in ("app/scheduler.py", "app/pipeline.py", "app/bot/main.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "install_log_filter" in src, f"{rel} 에 로그 필터 설치가 없다"
