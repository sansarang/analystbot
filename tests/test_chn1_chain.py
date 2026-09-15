"""CHN-1 — 무료 사슬은 둘 이상이고, 429·401 에서 기다리지 않는다.

🔴 실측 2026-09-15 이 이 파일의 이유다:
     groq 무료 티어 x-ratelimit-limit-tokens = 8000(분당)
     429 한 번에 453초를 기다렸고 그동안 슬레이트 전체가 멈췄다
     ([triage] 실패 · [v3] 탈락 — 판정 실패 ×5)
"""
from __future__ import annotations

import time

import pytest

from app.llm import judge_route as JR
from app.llm import openai_compat as OC


def test_gemini는_무료_사슬에_든다():
    """PAID_LLM_ALLOWED=0 에서도 후보로 남아야 한다."""
    assert "gemini" in JR.FREE_PROVIDERS
    assert JR.is_free("gemini", "gemini-3.5-flash-lite") is True
    assert JR.is_paid_provider("gemini") is False


def test_유료_판정_규칙_자체는_그대로다():
    """⚠️ gemini 하나만 옮겼다. '모르면 유료' 는 유지된다(BUD-1)."""
    assert JR.is_paid_provider("anthropic") is True
    assert JR.is_paid_provider("처음보는provider") is True
    assert JR.is_free("openrouter", "foo/bar") is False          # :free 없으면 유료
    assert JR.is_free("openrouter", "foo/bar:free") is True


class _Resp:
    def __init__(self, code, text='{"error":{"message":"rate limit"}}'):
        self.status_code = code
        self.text = text
        self.headers = {"Retry-After": "600"}


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [429, 401])
async def test_429와_401은_기다리지_않는다(monkeypatch, code):
    """🔴 종전에는 4회 × 최대 60초를 잤다. 이제 **한 번 보고 즉시 나간다.**"""
    import httpx

    async def fake_post(self, *a, **k):
        return _Resp(code)

    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    monkeypatch.setenv("GROQ_API_KEY", "x")

    t = time.time()
    r = await OC.complete("groq", "openai/gpt-oss-120b", "hi", max_tokens=16)

    assert r["ok"] is False
    assert r["retries"] == 1, "재시도를 했다 — 즉시 나가야 한다"
    assert sum(slept) <= OC.MIN_INTERVAL_SEC.get("groq", 2.0), \
        f"{code} 에서 {sum(slept)}초를 잤다"
    assert time.time() - t < 5
    assert str(code) in str(r["error"])
    # 🔴 본문을 버리지 않는다(LLM-1 회귀 방지)
    assert "rate limit" in str(r["error"])


def test_판정_토큰이_무료_한도_안이다():
    """groq 무료 티어는 분당 8,000토큰이다. 출력 상한이 그 안이어야 한다."""
    from app.config import get_settings

    s = get_settings()
    assert int(s.matchup_max_tokens) <= 1500
    assert int(s.deepsearch_max_tokens) <= 1500


def test_5xx_는_여전히_기다린다():
    """⚠️ 반대 위험 — 429 만 즉시 나간다. 5xx 백오프를 같이 지우지 않았다."""
    import inspect

    src = inspect.getsource(OC.complete)
    i = src.index("if r.status_code >= 500")
    assert "await asyncio.sleep(wait)" in src[i:i + 900]
