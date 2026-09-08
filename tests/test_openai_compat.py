"""[무료 전환] 어댑터 — **503·429 는 영구 실패가 아니다.**

🔴 실측 2026-09-04 프리페치 첫 실전:
     nvidia  3건 성공 → 4번째 `503 Service temporarily overloaded`
     mistral 폴백 → `429 rate limited` (RPM 2)
   둘 다 기다리면 풀리는데 재시도도 간격도 없어서 **팀 폼 0/10** 이 됐다.
   Mistral RPM 2 는 가입 조사 때 내가 직접 적어놓고도 무시했다.
"""
from pathlib import Path

import httpx
import pytest

from app.llm import openai_compat as OC

SRC = Path("app/llm/openai_compat.py").read_text(encoding="utf-8")


def _t(handler):
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _reset():
    OC._last_call.clear()
    yield
    OC._last_call.clear()


def test_intervals_match_measured_limits():
    """Mistral RPM 2 → 30초 이상. 이 숫자가 없어서 429 를 맞았다."""
    assert OC.MIN_INTERVAL_SEC["mistral"] >= 30.0
    assert OC.MIN_INTERVAL_SEC["nvidia"] <= 3.0


@pytest.mark.asyncio
async def test_503_is_retried(monkeypatch):
    """🔴 잠깐 밀린 것이지 거절이 아니다."""
    calls = {"n": 0}
    slept = []

    async def no_sleep(x):
        slept.append(x)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    monkeypatch.setenv("NVIDIA_API_KEY", "k")

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json={"choices": [
            {"message": {"content": '{"p_home":0.5}'}}]})

    monkeypatch.setattr(OC, "ENDPOINTS",
                        {**OC.ENDPOINTS, "nvidia": ("http://localhost/v1",
                                                    "NVIDIA_API_KEY")})
    import httpx as _h

    orig = _h.AsyncClient

    class C(orig):
        def __init__(self, *a, **kw):
            kw["transport"] = _t(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_h, "AsyncClient", C)
    r = await OC.complete("nvidia", "m", "p")
    assert r["ok"] is True and calls["n"] == 3
    # ⚠️ `slept` 에는 **스로틀 대기도 섞인다**(nvidia ~2초, 정확히 2.0 이 아니다).
    #    크기로 가른다 — 백오프는 3초 이상이다.
    backoffs = [x for x in slept if x >= 3.0]
    assert backoffs == [4.0, 8.0], f"백오프가 지수가 아니다: {slept}"


@pytest.mark.asyncio
async def test_429_waits_and_retries(monkeypatch):
    calls = {"n": 0}
    slept = []

    async def no_sleep(x):
        slept.append(x)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"choices": [
            {"message": {"content": "ok"}}]})

    monkeypatch.setattr(OC, "ENDPOINTS",
                        {**OC.ENDPOINTS, "mistral": ("http://localhost/v1",
                                                     "MISTRAL_API_KEY")})
    import httpx as _h

    orig = _h.AsyncClient

    class C(orig):
        def __init__(self, *a, **kw):
            kw["transport"] = _t(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_h, "AsyncClient", C)
    r = await OC.complete("mistral", "m", "p")
    assert r["ok"] is True and calls["n"] == 2
    assert 7.0 in slept, f"Retry-After 를 안 따랐다: {slept}"


@pytest.mark.asyncio
async def test_throttle_enforces_the_gap(monkeypatch):
    """호출부가 잊어도 간격이 지켜진다."""
    slept = []

    async def no_sleep(x):
        slept.append(x)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    OC._last_call["mistral"] = __import__("time").monotonic()
    await OC._throttle("mistral")
    assert slept and slept[0] > 25, f"간격을 안 지켰다: {slept}"


def test_no_bypass():
    """429 를 우회하지 않는다 — **기다린다.**"""
    assert "우회하지 않는다" in SRC
    assert "기다린다" in SRC
    assert "random" not in SRC and "User-Agent" not in SRC


# ═══════════════ [LLM-1 2026-09-08] 429 본문을 버려 진짜 원인이 가려졌다
#
# 🔴 실사고 2026-09-08: 운영 gemini 잔액이 소진돼 **11경기 판정이 0건**이 됐는데
#    아무도 몰랐다. 응답 본문은 이렇게 말하고 있었다:
#      429 {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
#           "message": "Your prepayment credits are depleted. Please go to
#                       AI Studio ... to manage your project and billing."}}
#    그런데 어댑터가 `out["error"] = "429 rate limited"` 로 **덮어썼다.**
#    바로 아래 5xx 분기는 `r.text[:160]` 을 보존하는데 429 만 버린다.
#    로그를 본 사람은 "한도니까 기다리면 풀린다"고 읽었고, 잔액이 0인 채로
#    슬레이트가 통째로 지나갔다.
#
# ⚠️ **분류를 바꾸지 않는다.** 429 를 credit 으로 승격시키면 반대 사고가 난다 —
#    실측 2026-09-05: 툴 호출 결함으로 narrator·interpreter·intent 가 gemini 로
#    몰려 429 가 났고, 그 429 가 credit 으로 오분류돼 **체인이 통째로 멈췄다**
#    (W-LLM-FAIL 24회, `provider.py` 주석). 재시도도 차단기도 그대로 둔다.
#    고치는 것은 **보이게 하는 것** 하나다.

_DEPLETED = ('{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": '
             '"Your prepayment credits are depleted. Please go to AI Studio."}}')


def _mock_client(monkeypatch, handler):
    import httpx as _h

    orig = _h.AsyncClient

    class C(orig):
        def __init__(self, *a, **kw):
            kw["transport"] = _t(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(_h, "AsyncClient", C)


@pytest.mark.asyncio
async def test_429_본문이_error_에_남는다(monkeypatch):
    """🔴 잔액 소진이 '한도'로 읽히면 아무도 충전하지 않는다."""
    async def no_sleep(x):
        pass

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setattr(OC, "ENDPOINTS",
                        {**OC.ENDPOINTS, "mistral": ("http://localhost/v1",
                                                     "MISTRAL_API_KEY")})
    _mock_client(monkeypatch, lambda req: httpx.Response(429, text=_DEPLETED))
    r = await OC.complete("mistral", "m", "p")
    assert r["ok"] is False
    assert "depleted" in (r["error"] or ""), (
        f"본문이 버려졌다 — 진짜 원인을 못 본다: {r['error']!r}")


@pytest.mark.asyncio
async def test_429_는_여전히_기다리고_재시도한다(monkeypatch):
    """⚠️ 반대 위험 — 본문을 살렸다고 재시도를 없애면 진짜 한도에서 손해다."""
    calls = {"n": 0}
    slept = []

    async def no_sleep(x):
        slept.append(x)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setattr(OC, "ENDPOINTS",
                        {**OC.ENDPOINTS, "mistral": ("http://localhost/v1",
                                                     "MISTRAL_API_KEY")})

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"},
                                  text="rate limit exceeded")
        return httpx.Response(200, json={"choices": [
            {"message": {"content": "ok"}}]})

    _mock_client(monkeypatch, handler)
    r = await OC.complete("mistral", "m", "p")
    assert r["ok"] is True and calls["n"] == 2
    assert 7.0 in slept, f"Retry-After 를 안 따랐다: {slept}"


def test_429_분류를_바꾸지_않는다():
    """⚠️ 반대 위험 — 429 를 credit 으로 승격시키면 2026-09-05 사고가 재발한다.

    어댑터는 **분류하지 않는다.** 본문을 보존해 넘길 뿐이다.
    """
    assert "trip_credit" not in SRC and "ApiQuotaError" not in SRC
    assert "우회하지 않는다" in SRC and "기다린다" in SRC
