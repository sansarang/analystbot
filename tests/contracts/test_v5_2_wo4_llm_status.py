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


