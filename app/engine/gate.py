"""[GATE-1] 괴리 게이트 — 딥서치를 **어디에 쓸지** 고른다. 지시문 Phase 3.

    gap = p_prior − p_market   (홈 기준, 축구는 세 값 중 **최대 절대값**)

    |gap| < 4      → 동의       딥서치 생략(층1 위성만)
    gap ≤ −4       → 시장 과대  딥서치 대상 · 구조 픽 후보
    gap ≥ +4       → 가치 의심  딥서치 대상 · 이유 없으면 사전값이 틀린 것
    둘 중 하나 없음 → 보드 고정  딥서치 생략 · 확신 하

🔴 **게이트는 확률을 바꾸지 않는다.** 고르는 일만 한다 — `p_code` 를 건드리면
   조정이 이중으로 반영된다(계약이 소스를 전수로 단언한다).
⚠️ 순수 함수 모듈이다. DB·HTTP 를 부르지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

AGREE = "동의"
OVER = "시장 과대"
DOUBT = "가치 의심"
BOARD = "보드 고정"

#: 경계(%p). 지시문 표 그대로 — **여기 한 곳에만 적는다.**
THRESHOLD_PP = 4.0

#: 딥서치 예산. 슬레이트당 상위 비율 · 최소 · 최대.
BUDGET_RATIO = 0.30
BUDGET_MIN = 2
BUDGET_MAX = 8

#: 축구 3-way 칸 이름. 부호의 방향을 이 이름으로 남긴다.
SIDES = ("home", "draw", "away")


@dataclass(frozen=True)
class Verdict:
    label: str
    gap_pp: float | None
    side: str | None
    reason: str

    @property
    def deepsearch(self) -> bool:
        return self.label in (OVER, DOUBT)


def _pairs(prior, market):
    """(칸이름, 사전값, 시장) 목록. 스칼라면 홈 한 칸이다."""
    if isinstance(prior, (tuple, list)) or isinstance(market, (tuple, list)):
        p = tuple(prior or ()) + (None,) * 3
        m = tuple(market or ()) + (None,) * 3
        return [(s, p[i], m[i]) for i, s in enumerate(SIDES)]
    return [("home", prior, market)]


def classify(prior, market, sport: str = "") -> Verdict:
    """사전값·시장 → 게이트 판정.

    🔴 한쪽이라도 없으면 **보드 고정**이다. 없는 것을 0 이나 0.5 로 읽지 않는다.
    🔴 축구는 **가장 크게 갈린 칸**을 쓴다. 빈 칸은 건너뛴다 — 0 으로 읽으면
       그 칸이 최대 괴리가 되어 엉뚱한 경기가 딥서치로 간다.
    """
    best = None
    for side, p, m in _pairs(prior, market):
        if p is None or m is None:
            continue
        gap = round((float(p) - float(m)) * 100, 2)
        if best is None or abs(gap) > abs(best[1]):
            best = (side, gap)
    if best is None:
        return Verdict(BOARD, None, None,
                       "사전값 또는 시장 확률이 없다 — 보드만, 확신 하")
    side, gap = best
    if abs(gap) < THRESHOLD_PP:
        return Verdict(AGREE, gap, side,
                       f"사전값과 시장이 {abs(gap):.1f}%p 차이 — 동의, 딥서치 생략")
    if gap <= -THRESHOLD_PP:
        return Verdict(OVER, gap, side,
                       f"시장이 {side} 를 {abs(gap):.1f}%p 높게 본다 — "
                       "방향은 시장, 가격은 안 잡힌다(구조 픽 후보)")
    return Verdict(DOUBT, gap, side,
                   f"우리가 {side} 를 {gap:.1f}%p 높게 본다 — "
                   "이유를 못 찾으면 사전값이 틀린 것")


def select(rows: list[dict]) -> list[dict]:
    """딥서치 대상 고르기. |gap| 큰 순, 상위 30%(최소 2·최대 8).

    ⚠️ "최소 2" 는 **대상 안에서** 최소다 — 대상이 1건이면 1건이다.
       없는 것을 만들어 예산을 채우지 않는다.
    """
    cand = [r for r in (rows or [])
            if r.get("label") in (OVER, DOUBT) and r.get("gap_pp") is not None]
    if not cand:
        return []
    cand.sort(key=lambda r: abs(float(r["gap_pp"])), reverse=True)
    n = max(BUDGET_MIN, round(len(rows) * BUDGET_RATIO))
    n = min(n, BUDGET_MAX, len(cand))
    logger.info("[gate] 슬레이트 %d경기 · 대상 %d · 딥서치 %d건",
                len(rows), len(cand), n)
    return cand[:n]
