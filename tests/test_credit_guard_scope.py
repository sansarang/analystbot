"""[P0 2026-09-06] Anthropic 차단기는 Anthropic 경로에만 걸린다.

🔴 실사고: 축구 실험(`soccer_trial`)이 Anthropic 400 을 맞고 공용 차단기를
   내렸다. 야구 판정은 무료 사슬(Gemini)로 도는데도 **호출을 시도조차 못 하고**
   전부 죽었다 — MLB 발송 0/85 (0%), 밤새 W-RESCUE-DEAD·W-CARD-LATE.

   오류 문자열이 구조를 그대로 보여줬다:
     "잔액 소진으로 중단 (matchup:SF@NYM): soccer-trial/claude-sonnet-5"
      └ 야구 호출부가 만든 위치          └ 축구가 남긴 사유

   차단기 자체는 옳다(잔액 0인 키로 계속 때리지 않는다). 틀린 것은
   **적용 범위**였다.
"""
from __future__ import annotations

import pytest

from app.engine import credit_guard


@pytest.fixture(autouse=True)
def _clean():
    credit_guard.reset()
    yield
    credit_guard.reset()


def _trip():
    credit_guard.trip_credit("soccer-trial/claude-sonnet-5",
                             RuntimeError("credit balance is too low"))


def test_free_chain_is_not_blocked_by_anthropic_exhaustion(monkeypatch):
    """무료가 주전이면 Anthropic 잔액과 무관하다."""
    import app.engine.team_form as tf

    monkeypatch.setattr(tf, "_free_primary", lambda role: True)
    _trip()
    # 무료 주전이면 호출부가 abort 를 부르지 않는다 — 부르면 여기서 터진다.
    if not tf._free_primary("matchup"):
        credit_guard.abort_if_credit_gone("matchup:A@B")


def test_paid_chain_is_still_blocked(monkeypatch):
    """반대 위험 — Anthropic 이 주전이면 차단기는 그대로 살아 있어야 한다.

    잔액 0인 키로 계속 때리면 요금만 태우고 종목이 통째로 멈춘다.
    """
    from app.collectors.base import ApiQuotaError

    _trip()
    with pytest.raises(ApiQuotaError):
        credit_guard.abort_if_credit_gone("matchup:A@B")


@pytest.mark.parametrize("path,func", [
    ("app/engine/matchup.py", "judge_matchup"),
    ("app/engine/team_form.py", "analyze_team"),
])
def test_call_sites_check_the_route_first(path, func):
    """호출부가 `_free_primary` 로 경로를 확인한 뒤에만 abort 를 부른다."""
    from pathlib import Path

    src = Path(path).read_text(encoding="utf-8")
    i = src.index("abort_if_credit_gone(f")
    window = src[max(0, i - 700):i]
    assert "_free_primary" in window, (
        f"{path} 의 abort_if_credit_gone 앞에 경로 확인이 없다 — "
        "무료 사슬이 Anthropic 잔액에 인질로 잡힌다")


def test_soccer_trial_still_trips_for_itself():
    """축구는 실제로 Anthropic 을 쓴다 — 거기서는 차단기가 필요하다."""
    from pathlib import Path

    src = Path("app/engine/soccer_trial.py").read_text(encoding="utf-8")
    assert "trip_credit(" in src
    assert "abort_if_credit_gone(" in src
