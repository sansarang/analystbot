"""🔴🔴 **④ `llm_unavailable` 을 상태 코드별로 가른다** — 사용자 지시 2026-10-06.

> `llm_unavailable` 14건: **HTTP 상태 코드별로 집계**해 보고. 429면 Solar
> 동시 호출을 **2로 낮추고** `Retry-After` 를 따르는 재시도.

══════════════════════════════════════════════════════════════════
🔴 재서 찾은 것 (실측 2026-10-06 · 북아일랜드–조지아)
══════════════════════════════════════════════════════════════════

깔때기: `agent_vars 탈락: llm_unavailable 14`
로그  : 실제 전송 실패는 **1건** — `RemoteDisconnected`

🔴 `solar.chat` 이 **예산 거부도** `SolarUnavailable` 로 던지고 호출부가 전부
   `llm_unavailable` 로 셌다. §8-6 이 금지한 **거짓 사유**이고, CLAUDE.md #11
   (*"`llm_unavailable` 로 끊긴 실행은 오염된 것 — 다시 돌린다"*)을 **잘못
   발동**시켜 정상 종료를 재실행하게 만든다.
"""
from __future__ import annotations

import urllib.error

import pytest

from app import solar
from app.reasons import Reason


def _inp():
    import datetime as dt

    from app import agentloop
    return agentloop.AgentInput(
        match_key="fotmob:1", home="team:1", away="team:2",
        home_names=("A",), away_names=("B",), competition="L",
        sport="soccer",
        kickoff_utc=dt.datetime(2026, 10, 5, 18, 45, tzinfo=dt.timezone.utc),
        venue="V", langs=("en",))


def test_wo4_예산_거부는_llm_장애가_아니다():
    """🔴🔴 **사유가 갈린다** — 그러지 않으면 거짓 사유다(§8-6)."""
    from app import agentloop
    # 🔴 하위 클래스여야 한다 — 종전 `except SolarUnavailable` 자리가 그대로 돈다
    assert issubclass(solar.SolarBudgetCut, solar.SolarUnavailable)
    assert agentloop._why_of(solar.SolarBudgetCut("budget_cut: …")) \
        is Reason.BUDGET_CUT
    assert agentloop._why_of(solar.SolarUnavailable("llm_unavailable: …")) \
        is Reason.LLM_UNAVAILABLE


def test_wo4_예산이_막으면_budget_cut_으로_던진다():
    """🔴 `chat` 이 **실제로** 그 예외를 던지는가 — 선언만 있으면 없는 것이다(#2)."""
    b = solar.MatchBudget(subtask_out=8_000)
    b.output_tokens = 8_000           # 🔴 하위 상한을 다 썼다
    with pytest.raises(solar.SolarBudgetCut) as got:
        solar.chat([{"role": "user", "content": "x"}], budget=b,
                   _net=lambda *a, **k: {"usage": {}})
    assert "budget_cut" in str(got.value), got.value
    # 🔴 그리고 **그것은 llm_unavailable 이 아니다**
    assert "llm_unavailable" not in str(got.value)


def test_wo4_상태_코드별로_센다(monkeypatch):
    """🔴🔴 429·5xx·응답없음을 **가른다** — 고칠 곳이 다르다(속도/서버/망).

    ⚠️ 망에 안 나간다 — `urlopen` 을 대역으로 바꾼다.
    """
    solar.HTTP_FAILS.clear()
    saw = solar.SAW_429
    slept: list[float] = []
    try:
        solar.SAW_429 = False
        assert solar.http_fail_line() == "전송 실패 0건", solar.http_fail_line()
        monkeypatch.setattr(solar.time, "sleep", lambda x: slept.append(x))

        # ── ① 503 두 번(재시도 1회) → 상태 503 이 2 건
        def _503(*_a, **_k):
            raise urllib.error.HTTPError("u", 503, "nope", {}, None)  # type: ignore[arg-type]
        monkeypatch.setattr(solar.urllib.request, "urlopen", _503)
        with pytest.raises(solar.SolarUnavailable) as got:
            solar._post("https://x", "k", {}, 1, 1)
        assert got.value.status == 503, got.value.status
        assert solar.HTTP_FAILS.get(503) == 2, solar.HTTP_FAILS
        assert solar.SAW_429 is False, "🔴 503 인데 429 로 봤다"

        # ── ② 응답조차 못 받은 것은 **`None`** 이다(0 이 아니다 · #3)
        def _dead(*_a, **_k):
            raise urllib.error.URLError("nodename nor servname provided")
        monkeypatch.setattr(solar.urllib.request, "urlopen", _dead)
        with pytest.raises(solar.SolarUnavailable) as got2:
            solar._post("https://x", "k", {}, 1, 0)
        assert got2.value.status is None, got2.value.status
        assert solar.HTTP_FAILS.get(None) == 1, solar.HTTP_FAILS

        # ── ③ 429 → `SAW_429` 가 서고 `Retry-After` 만큼 쉰다
        def _429(*_a, **_k):
            raise urllib.error.HTTPError(
                "u", 429, "slow", {"Retry-After": "5"}, None)  # type: ignore[arg-type]
        monkeypatch.setattr(solar.urllib.request, "urlopen", _429)
        slept.clear()
        with pytest.raises(solar.SolarUnavailable):
            solar._post("https://x", "k", {}, 1, 1)
        assert solar.SAW_429 is True, "🔴 429 를 받고도 깃발이 안 섰다"
        assert slept == [5.0], f"🔴 `Retry-After` 를 안 따랐다: {slept}"

        # ── ④ 한 줄 보고가 **셋을 다 이름으로** 적는다(#3 조용한 0 금지)
        said = solar.http_fail_line()
        for word in ("503", "429", "응답없음"):
            assert word in said, (word, said)
        assert said.startswith("전송 실패 5건"), said
    finally:
        solar.SAW_429 = saw
        solar.HTTP_FAILS.clear()


def test_wo4_429를_받으면_동시_호출을_낮춘다():
    """🔴🔴 `solar_after_429` 가 **설정에 있었는데 아무도 읽지 않았다**(#2 배선)."""
    box = dict(solar.budget_cfg().get("concurrency") or {})
    assert int(box.get("solar") or 0) > int(box.get("solar_after_429") or 0), box
    saw = solar.SAW_429
    try:
        solar.SAW_429 = False
        before = solar.solar_concurrency()
        solar.SAW_429 = True
        after = solar.solar_concurrency()
        assert after == int(box["solar_after_429"]), after
        assert after < before, (before, after)
        # 🔴 **리드의 세마포어가 그 수를 쓴다** — 안 쓰면 선언만 있는 것이다
        from app.research import lead
        assert lead.limits()["solar"] == after, lead.limits()
    finally:
        solar.SAW_429 = saw


def test_wo4_Retry_After_를_따른다():
    """🔴 그 머리글은 **초**이거나 **HTTP 날짜**다. ⚠️ 못 읽으면 지수 대기."""
    class _E:
        headers = {"Retry-After": "7"}
    assert solar._retry_after(_E(), 1.0) == 7.0

    class _Big:
        headers = {"Retry-After": "99999"}
    # 🔴 서버가 큰 수를 줘도 **그대로 자지 않는다**(상한)
    assert solar._retry_after(_Big(), 1.0) <= 60.0

    class _None:
        headers = {}
    assert solar._retry_after(_None(), 3.0) == 3.0        # 🔴 없으면 지수 대기


def test_wo4_보고에_그_줄이_있다():
    """🔴 #2 배선 — 집계만 만들고 **적지 않으면** 없는 것이다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.gather))
    assert "http_fail_line" in src, (
        "🔴 카드가 전송 실패 집계를 **안 적는다** — 사용자 ④ 가 요구한 보고다")
