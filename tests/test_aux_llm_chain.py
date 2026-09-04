"""[2026-09-04] 보조 LLM 사슬이 한쪽으로 몰려 통째로 멈췄다.

🔴 운영 경보: `W-LLM-FAIL judge — 연속 24회 실패 — 판정이 멈춰 있다`
   (narrator: 크레딧 소진 gemini: 429 quota…)

원인 사슬 (전부 재현 완료):
  ① Groq `openai/gpt-oss-120b` 가 강제 함수호출에서 **자기 내부 `json` 툴**을
     부른다 → 400 "attempted to call tool 'json' which was not in request.tools".
     입력에 따라 나기도 안 나기도 하는 간헐 결함이다.
  ② 그래서 narrator·interpreter·intent 가 **전부 gemini 로 몰렸다.**
  ③ 몰린 부하로 gemini 가 429. 그 429 본문이 "quota"·"billing"을 말해
     `ApiQuotaError`(크레딧 소진)로 오분류됐고, 크레딧 소진은 **폴백 없이
     즉시 중단**이라 체인이 통째로 멈췄다.
  ④ 경보 문구는 "판정이 멈춰 있다"였지만 **매치업 판정은 무료 사슬이라
     무관**했다 — 같은 시각 KBO·NPB 카드는 정상 발송됐다.

실측 (같은 계정·같은 narrator 스키마 2636자):
  tools+tool_choice         200 (되기도 하고) / 400 tool_use_failed (안 되기도)
  response_format json_schema  200 · 200   ← 두 번 다 성공
  gemini 키 자체는 몇 분 뒤 정상 응답 — **소진이 아니라 시간 창이었다.**
"""
import pytest

from app.llm.provider import _tool_call_rejected


# ─────────────────── ① 툴 거부 판별 ───────────────────

@pytest.mark.parametrize("body,expected", [
    ('{"error":{"message":"Tool call validation failed: tool call validation '
     'failed: attempted to call tool \'json\' which was not in request.tools",'
     '"code":"tool_use_failed"}}', True),
    ('{"error":{"message":"tool_use_failed"}}', True),
    ('{"error":{"message":"Invalid schema: parameters must be an object"}}', False),
    ('{"error":{"message":"model not found"}}', False),
    ("", False),
])
def test_tool_rejection_is_distinguished_from_a_real_bad_request(body, expected):
    """진짜 잘못된 요청까지 재시도하면 같은 400 을 두 번 받는다."""
    assert _tool_call_rejected(body) is expected


def test_reject_marks_came_from_a_measured_response():
    """🔴 문구를 상상해 넣지 않았다 — 실측 응답에서 왔다."""
    import inspect

    from app.llm import provider

    src = inspect.getsource(provider)
    assert "attempted to call tool" in src
    assert "openai/gpt-oss-120b" in src, "어느 모델에서 봤는지 남긴다"


def test_downgrade_path_exists_and_is_bounded():
    import inspect

    from app.llm.provider import OpenAICompatProvider

    src = inspect.getsource(OpenAICompatProvider._call)
    assert "json_schema" in src, "표준 구조화 출력으로 강등하지 않는다"
    assert "tool_left = 1" in src or "tool_left" in src, "강등 횟수 상한이 없다"


# ─────────────────── ② 429 는 중단 사유가 아니다 ───────────────────

def test_429_never_becomes_a_credit_error():
    """🔴 크레딧 소진은 **폴백 없이 즉시 중단**이다. 한도 초과는 그게 아니다.

    Gemini 무료 429 본문은 "quota"·"billing"을 말하지만 그것은 분당·일일
    한도이고 시간이 지나면 풀린다 — 실측: 같은 키가 몇 분 뒤 정상 응답.
    """
    import inspect

    from app.llm.provider import OpenAICompatProvider

    src = inspect.getsource(OpenAICompatProvider._call)
    # ⚠️ 주석에는 왜 고쳤는지가 적혀 있다(`ApiQuotaError` 라는 단어 포함).
    #    **실행되는 줄만** 본다 — 주석까지 금지하면 사고 기록을 지우게 된다.
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    idx = code.index("if r.status_code == 429:")
    tail = code[idx:idx + 400]
    assert "ApiQuotaError" not in tail, "429 가 다시 크레딧으로 승격됐다"
    assert "LLMError" in tail
    # 402 경로는 그대로 크레딧이다
    assert "r.status_code == 402" in src


def test_credit_marker_no_longer_hijacks_a_429():
    """본문에 'credit' 가 있어도 **429 면** 크레딧이 아니다."""
    import inspect

    from app.llm.provider import OpenAICompatProvider

    src = inspect.getsource(OpenAICompatProvider._call)
    assert 'r.status_code != 429' in src.replace(" ", "").replace(
        "r.status_code!=429", "r.status_code != 429") or \
        "r.status_code != 429" in src


# ─────────────────── ④ 경보 문구 ───────────────────

@pytest.mark.asyncio
async def test_alert_names_the_real_role_not_judge():
    """🔴 "판정이 멈춰 있다"는 거짓이었다 — 카드는 정상 발송되고 있었다."""
    from app.watchdog import check_llm

    class _R:
        async def get(self, k):
            return "narrator: 크레딧 소진 …" if k.endswith(":last") else "24"

    found = await check_llm(_R())
    assert len(found) == 1
    code, target, detail = found[0]
    assert code == "W-LLM-FAIL"
    assert target == "narrator", "역할을 'judge' 로 뭉뚱그리면 사람이 엉뚱한 데를 본다"
    assert "판정이 멈춰 있다" not in detail
    assert "무관" in detail, "매치업 판정과 무관함을 말해야 한다"


@pytest.mark.asyncio
async def test_alert_falls_back_to_a_generic_name_without_detail():
    from app.watchdog import check_llm

    class _R:
        async def get(self, k):
            return None if k.endswith(":last") else "5"

    code, target, detail = (await check_llm(_R()))[0]
    assert target == "aux"
    assert "보조 LLM" in detail
