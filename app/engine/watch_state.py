"""[U10 2026-09-15] 관측 상태기계. **코드만 전이한다.**

    관측 ──(게이트 대상)──> 후보 ──(조건 A)──> 추천대기 ──(T-30)──> 추천
      └───────────────────── 취소 ─────────────────────┘
                              추천 ──(킥오프)──> 종료

🔴 **역방향 전이는 없다.** 추천에서 후보로 돌아가면 이미 나간 카드를 되돌려야
   한다. 나가는 길은 `취소`·`종료` 뿐이다.
🔴 LLM 이 상태를 바꾸지 않는다. 조건은 전부 코드 값이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

OBSERVE = "관측"
CANDIDATE = "후보"
PENDING = "추천대기"
PICKED = "추천"
CANCELLED = "취소"
DONE = "종료"

STATES = (OBSERVE, CANDIDATE, PENDING, PICKED, CANCELLED, DONE)

#: 허용 전이. 여기 없는 이동은 거부한다.
ALLOWED = {
    OBSERVE: (CANDIDATE, CANCELLED, DONE),
    CANDIDATE: (PENDING, CANCELLED, DONE),
    PENDING: (PICKED, CANCELLED, DONE),
    PICKED: (CANCELLED, DONE),
    CANCELLED: (DONE,),
    DONE: (),
}


@dataclass(frozen=True)
class Step:
    state: str
    reason: str
    changed: bool


def condition_a(*, gate_label: str | None, confirmed_n: int,
                sufficient: bool, swap_agree: bool | None,
                structure_n: int) -> dict:
    """조건 A — 후보 → 추천대기. **네 항목 전부**여야 한다.

    ① 게이트 대상(동의·보드 고정이 아니다)
    ② 확인이 문턱을 넘었다(`sufficient`)
    ③ 사이드 스왑이 일치했다(모르면 불가)
    ④ 구조 후보가 있다
    """
    from app.engine import gate as G

    checks = {
        "게이트 대상": gate_label in (G.OVER, G.DOUBT),
        "확인 충족": bool(sufficient) and confirmed_n > 0,
        "스왑 일치": swap_agree is True,
        "구조 후보": int(structure_n or 0) > 0,
    }
    return {"ok": all(checks.values()), "checks": checks,
            "missing": [k for k, v in checks.items() if not v]}


def next_state(current: str, want: str, *, reason: str = "") -> Step:
    """전이. 🔴 허용표에 없으면 **그대로 둔다**(예외를 던지지 않는다 —
    상태기계가 판정을 막으면 안 된다). 거부는 로그에 남는다."""
    cur = current if current in STATES else OBSERVE
    if want == cur:
        return Step(cur, reason or "변화 없음", False)
    if want not in ALLOWED.get(cur, ()):
        logger.warning("[watch] 허용되지 않은 전이 %s → %s — 그대로 둔다", cur, want)
        return Step(cur, f"거부: {cur} → {want}", False)
    logger.info("[watch] %s → %s · %s", cur, want, reason)
    return Step(want, reason, True)
