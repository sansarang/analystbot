"""[OBS-1] 상시 관측 모드 — 24시간 보되 대부분 침묵한다 (Part 4).

지금 봇은 슬레이트 전체를 시각에 맞춰 한 번 판정하고 발송한다. 페이블
방식은 반대다 — **모든 경기를 계속 보되 대부분은 침묵하고, 조건이 갖춰진
소수만 단계적으로 올려서, 라인업 확정 후에 최종 한 번 말한다.**

🔴 **상태 전이는 코드만 한다.** LLM 출력은 조건 A·B 의 **입력일 뿐**이다.
   여기서 LLM 을 부르면 그 자리가 판정이 된다(계약이 임포트를 잠근다).
🔴 **최종은 경기당 한 번.** 재판정 카드·수정 카드가 없다.
🔴 **라인업 확정 전엔 말하지 않는다.** 잠정 발송이 없다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 [OBS-2 2026-09-20] **사본 금지 — 목록을 여기서 다시 적지 않는다.**
#   종전에는 `watch_state.py` 와 이 파일이 같은 6개를 각자 선언했고, 둘 다
#   호출부가 0건이라 아무도 몰랐다. 상태·전이의 원본은 **전이 허용표를 가진**
#   `watch_state` 하나다(`db/schema.sql:566` "코드만 전이한다").
from app.engine.watch_state import CANCELLED, DONE  # noqa: E402
from app.engine.watch_state import STATES  # noqa: E402

#: 되돌아가지 않는 상태.
TERMINAL = (CANCELLED, DONE)

#: 상시 루프 주기(초). 지시문 7-3.
TICK_SEC = 60        # due 트리거
SNAP_SEC = 600       # 후보·추천대기 경기의 배당 재스냅
RECHECK_SEC = 3600   # 관측 경기 일정·상태 재확인

#: 🔴 사본 금지 — 상한은 `triggers` 가 원본이다. 같은 객체를 참조한다.
from app.engine.triggers import MAX_CONCURRENT  # noqa: E402

#: 검색·LLM 이 도는 상태. 🔴 24시간 도는 것은 **트리거와 배당 스냅**이지
#  검색이 아니다 — 그래야 예산이 유지된다(지시문 7-3).
_SEARCH_STATES = ("후보", "추천대기")

#: 게이트 임계. 🔴 `gate.THRESHOLD_PP` 가 원본이다.
from app.engine.gate import THRESHOLD_PP  # noqa: E402

#: 구조 픽 채택 하한(%p). 지시문 5-2·7-2.
EDGE_MIN_PP = 6.0


def uses_search(state: str) -> bool:
    return state in _SEARCH_STATES


def next_state(state: str, *, move_class: str | None = None) -> str:
    """🔴 어떤 상태에서든 `contra` 이동이 잡히면 **즉시 취소**(지시문 7-1)."""
    if state in TERMINAL:
        return state
    if move_class == "contra":
        return "취소"
    return state


def cond_a(ctx: dict) -> tuple[bool, str]:
    """후보 → 추천대기. **넷을 전부** 충족해야 한다(지시문 7-2 A)."""
    c = ctx or {}
    if c.get("gate") not in ("시장 과대", "가치 의심"):
        return False, f"게이트가 대상이 아니다: {c.get('gate')!r}"
    gap = c.get("gap_pp")
    if gap is None or abs(float(gap)) < THRESHOLD_PP:
        return False, f"괴리가 {THRESHOLD_PP}%p 미만이다"
    f = c.get("facts") or {}
    if not (f.get("out") or f.get("last3") or f.get("midweek")):
        return False, "결장·일정·폼 사실이 하나도 없다 — 이유 없는 괴리"
    if c.get("market_view") != {"시장 과대": "과대",
                                "가치 의심": "과소"}.get(c.get("gate")):
        return False, "분석 LLM 판단이 게이트와 다른 방향이다"
    if not c.get("swap_agree"):
        return False, "스왑이 갈렸다"
    edge = c.get("pick_edge_pp")
    if edge is None or float(edge) < EDGE_MIN_PP:
        return False, f"픽 우위가 {EDGE_MIN_PP}%p 미만이다"
    return True, ""


def cond_b(ctx: dict) -> tuple[bool, str]:
    """추천대기 → 추천(최종). **여섯을 전부** 충족해야 한다(지시문 7-2 B)."""
    c = ctx or {}
    if c.get("xi_status") != "official":
        return False, "공식 라인업이 없다 — 잠정 발송은 하지 않는다"
    if c.get("diff_adverse"):
        return False, "T-60 diff 에 픽에 불리한 변화가 있다"
    mv = c.get("move_class")
    if mv == "contra":
        return False, "라인업 스냅샷이 역이동(contra)이다"
    if not c.get("axis_kept"):
        return False, "재실행한 분석의 결정축 방향이 바뀌었다"
    if not c.get("swap_agree"):
        return False, "재실행에서 스왑이 갈렸다"
    edge = c.get("edge_pp")
    if edge is None or float(edge) < EDGE_MIN_PP:
        return False, f"새 라인에서 우위가 {EDGE_MIN_PP}%p 미만이다"
    if c.get("confidence") not in ("중", "상"):
        return False, f"확신이 {c.get('confidence')!r} 다 — 하는 발송하지 않는다"
    return True, ""


def dispatch_for(frm: str, to: str) -> str | None:
    """상태 전이 → 발송(지시문 7-4). **침묵이 기본이다.**

    🔴 최종은 경기당 한 번. 같은 상태에 머무르면 아무것도 안 보낸다.
    """
    if frm == to:
        return None
    if to == "추천":
        return "최종"
    if to == "취소" and frm in ("추천대기", "추천"):
        return "취소"
    return None
