"""[U12 2026-09-15] 조건 B — **최종 1회 발송**의 문턱과 취소.

🔴 잠정 카드를 폐지하고 **한 번만** 낸다. 그 한 번이 만족해야 할 것이 조건 B다:

    ① 라인업이 official 이다
    ② 불리한 diff 가 없다(우리 쪽 핵심이 빠지지 않았다)
    ③ 시장 흐름이 contra 가 아니다
    ④ edge 가 유지됐다(재판정 뒤에도 문턱 위)
    ⑤ 등급이 중 이상이다

🔴 **이 모듈은 발송하지 않는다.** 판정만 한다 — 실제 경로 전환은 U14 다.
⚠️ 순수 함수다. DB·HTTP 를 부르지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 라인업이 이 상태여야 최종이다. 원본은 `collectors.lineups.STATUS_CONFIRMED`.
def _confirmed() -> str:
    from app.collectors.lineups import STATUS_CONFIRMED

    return STATUS_CONFIRMED


def condition_b(*, lineup_status: str | None, diff_adverse: bool,
                flow_label: str | None, edge_pp: float | None,
                grade: str | None) -> dict:
    """조건 B. `{ok, checks, missing}` — **왜 안 되는지가 항상 남는다.**"""
    from app.engine import confidence as C
    from app.engine import odds_move as M
    from app.engine.structure import EDGE_MIN_PP

    checks = {
        "official": (lineup_status or "") == _confirmed(),
        "불리 diff 없음": not bool(diff_adverse),
        "흐름 contra 아님": flow_label != M.CONTRA,
        "edge 유지": edge_pp is not None and float(edge_pp) >= EDGE_MIN_PP,
        "등급 중 이상": grade in (C.HIGH, C.MID),
    }
    return {"ok": all(checks.values()), "checks": checks,
            "missing": [k for k, v in checks.items() if not v]}


def cancel_notice(*, flow_label: str | None, diff_adverse: bool,
                  was_sent: bool) -> dict:
    """취소 통지가 필요한가. 🔴 **이미 나간 카드에만** 보낸다.

    안 나갔으면 그냥 안 내면 된다 — 통지가 오히려 소음이다.
    """
    from app.engine import odds_move as M

    why = []
    if flow_label == M.CONTRA:
        why.append("시장이 우리 반대로 크게 움직였다")
    if diff_adverse:
        why.append("확정 라인업에서 핵심이 빠졌다")
    need = bool(why) and bool(was_sent)
    return {"cancel": bool(why), "notify": need,
            "why": " · ".join(why) or "취소 사유 없음"}
