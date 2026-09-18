"""[v1.4 STEP 9] ⑩ 재판정 — **하드 증거가 있을 때만, 한 번만.**

🔴 트리거는 폴러의 diff 원문이다 — 모델 자기보고를 쓰지 않는다.
     선발 변경   `starter_change_notes` 가 낸 줄
     라인업 확정 `lineup_confirmed` 판정
🔴 **최대 1회.** 두 번째 트리거는 무시하고 로그만 남긴다.
🔴 **잠정 카드가 없다.** 재판정 뒤 ⑬이 딱 한 번 보낸다(지시문 STEP 9 흔한 오류).
⚠️ 창: 킥오프 −90분 ~ −20분. 그 밖이면 발동하지 않는다.
⚠️ 이 노드는 **읽기만** 한다. 재실행은 `run.py` 의 `rerun_5_to_9` 가 한다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

NODE = "n10_rejudge"

WINDOW_MIN, WINDOW_MAX = 20, 90      # 킥오프 전 분


def _minutes_to_kickoff(state, ctx) -> float | None:
    """킥오프까지 남은 분. 모르면 None — 지어내지 않는다."""
    from datetime import datetime, timezone

    raw = state.kickoff_utc or ""
    if not raw:
        return None
    try:
        ko = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = ctx.now_kst or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (ko - now).total_seconds() / 60.0


async def run(state, ctx):
    """⑩ 재판정 트리거 판정."""
    if (state.n10_rejudge or {}).get("triggered"):
        logger.info("[flow:n10] game=%s 이미 재판정했다 — 두 번째는 무시",
                    state.game_id)
        state.n10_rejudge = dict(state.n10_rejudge, second_ignored=True)
        return state

    left = _minutes_to_kickoff(state, ctx)
    signals = (ctx.inject or {}).get("rejudge_signals") or {}
    in_window = left is not None and WINDOW_MIN <= left <= WINDOW_MAX

    trigger = None
    if in_window:
        if signals.get("starter_changed"):
            trigger = "starter_changed"
        elif signals.get("lineup_confirmed"):
            trigger = "lineup_confirmed"

    state.n10_rejudge = {"triggered": bool(trigger), "trigger": trigger,
                         "minutes_to_kickoff": None if left is None else round(left, 1),
                         "in_window": in_window}
    if trigger:
        logger.info("[flow:n10] game=%s 재판정 — %s (T%+.0f분)",
                    state.game_id, trigger, left)
    return state
