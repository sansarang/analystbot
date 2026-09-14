"""[D1-1] 북 간 비교 — 사설이 샤프보다 얼마나 후한가 (Phase D1).

🔴 **피나클을 이름으로 특정할 수 없다.** 오즈포털 북메이커 페이지에 id↔이름
   표가 없다(실측 2026-09-14: "Pinnacle" 문자열 0건, 이름은 링크 슬러그에만).
   그래서 기준은 `sharp_proxy` 다 — 그 스냅샷에서 환급률(`highestPayout`)이
   가장 높은 북. **피나클이라 단정하지 않는다.**

🔴 **없으면 NULL 이다.** 사설이든 샤프든 한쪽이 비면 `None` 을 돌려주고,
   게이트는 사전값 기준으로 폴백한다(문서 "하지 말 것": 평균으로 대체 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 이 이상이면 "사설이 강팀을 후하게 부른다" = 약팀 파생 시장 후보(지시문).
GAP_STRONG_PP = 3.0

#: 사설 기준. 🔴 [D1-3] ESPN 축구는 우리 IP 에서 403 이다(실측 2026-09-14:
#  site.api.espn.com ita.1·esp.1·eng.1 전부 Access Denied). 그래서 같은
#  오즈포털 스냅샷의 **마진 최대 북**을 사설 대용으로 쓴다.
#  ⚠️ ESPN 이 열리는 종목(야구)은 `draftkings` 가 그대로 사설 값이다.
SOFT_BOOK = "soft_proxy"
SOFT_BOOK_DK = "draftkings"
SHARP_BOOK = "sharp_proxy"


def _probs(odds: dict | None) -> dict | None:
    """마진 제거. 🔴 새로 만들지 않는다 — `market_edge.implied_probs` 가 원본."""
    from app.engine.market_edge import implied_probs

    return implied_probs(odds or {}) or None


def favored_side(p: dict | None) -> str | None:
    """강팀 쪽. 🔴 홈/원정 중 확률이 큰 쪽이고, 무승부는 세지 않는다."""
    if not p:
        return None
    h, a = p.get("home"), p.get("away")
    if h is None or a is None:
        return None
    return "home" if h >= a else "away"


def pinnacle_gap(soft: dict | None, sharp: dict | None, *,
                 sharp_absent: bool = False) -> dict | None:
    """`p_soft(강팀) − p_sharp_proxy(강팀)` (%p). 한쪽이라도 없으면 None.

    반환 `{"gap_pp", "side", "p_soft", "p_sharp", "label"}`.
    ⚠️ 이름은 지시문의 `pinnacle_gap` 을 그대로 쓰되, 기준은 `sharp_proxy` 다.
    """
    ps, pp = _probs(soft), _probs(sharp)
    if not ps or not pp:
        return None
    side = favored_side(pp) or favored_side(ps)
    if side is None:
        return None
    a, b = ps.get(side), pp.get(side)
    if a is None or b is None:
        return None
    gap = round((float(a) - float(b)) * 100, 2)
    if gap >= GAP_STRONG_PP:
        label = "사설 후함(약팀 파생 후보)"
    elif gap <= -GAP_STRONG_PP:
        label = "사설 짬(강팀 승패 후보)"
    else:
        label = "차이 없음"
    if sharp_absent:
        # 🔴 [D1-4] 값은 지우지 않는다. **해석을 막는다** — 비교 대상이
        #    샤프가 아니었다는 사실이 라벨을 타고 원장·카드까지 간다.
        label = f"샤프 부재 · {label}(소프트북끼리 비교)"
    return {"gap_pp": gap, "side": side, "p_soft": a, "p_sharp": b,
            "label": label, "sharp_absent": bool(sharp_absent)}
