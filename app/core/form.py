"""🔴🔴 **축1 — 보정 폼 지수**. 사용자 지시 2026-10-10(셋째) §1.

> 최근 10경기 득점·실점(가능하면 xG·xGA)을 **상대 전력**(Elo/리그 내 순위)으로
> 보정. **약팀 상대 대승은 깎고 강팀 상대 결과는 올린다.**
> 같은 리그 팀 대비 **백분위**로 표시.
> 3번(골 내용)의 **"운 요소 할인"** 을 여기에 반영한다.

🔴 보정 식은 **하나**다(`adjust_one`) — 두 곳에서 보정하면 한쪽만 고쳐진다.
🔴 백분위는 **같은 리그 팀들**과 비교해야 뜻이 있다 — 비교 대상을 못 받으면
   백분위를 **비운다**(지어내지 않는다 · #3).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 §1 — 최근 몇 경기(지시서가 적은 10)
RECENT = 10
#: 🔴🔴 **Elo 차 → 보정 배율**의 기울기. ⚠️ **임시값**이다 — 적합 전이다.
#
#  뜻: 상대가 우리보다 Elo 100 점 낮으면 그 경기의 득점을 `1 - 0.15` 배로 깎고,
#      100 점 높으면 `1 + 0.15` 배로 올린다.
#  🔴 **왜 임시값인가**: 적합에는 *"리그 경기마다 양 팀 Elo + 결과"* 가 필요하다.
#     Elo 는 `app/collect/leagueelo.py` 가 **경기 전 등급**으로 만들어 두므로
#     재료는 있다 — 다만 그 적합을 아직 돌리지 않았다(`tools/fit_form_adjust.py`).
ELO_SLOPE = 0.15
PROVISIONAL = "🔴 **임시값**(적합 전)"


@dataclass
class TeamForm:
    """🔴 한 팀의 보정 폼. ⚠️ 못 잰 칸은 **`None`**(0 이 아니다)."""

    team: str = ""
    n: int = 0
    gf: float = 0.0
    ga: float = 0.0
    adj_gf: float = 0.0
    adj_ga: float = 0.0
    #: 🔴 §1 마지막 줄 — 운 요소 할인을 반영한 뒤의 공격 지수
    gf_after_luck: float | None = None
    #: 🔴 같은 리그 팀 대비 백분위(0~1) — 비교 대상이 없으면 `None`
    pct_att: float | None = None
    pct_def: float | None = None
    why: str = ""

    def index(self) -> float | None:
        """🔴 한 수로 본 폼 — `보정 득점 − 보정 실점`(경기당). 표본 0 이면 `None`."""
        if not self.n:
            return None
        got = self.gf_after_luck if self.gf_after_luck is not None else self.adj_gf
        return round((got - self.adj_ga) / self.n, 3)


def adjust_one(goals: float, *, mine_elo: float | None,
               their_elo: float | None) -> tuple[float, str]:
    """🔴🔴 §1 — 한 경기 득점을 **상대 전력으로 보정**. `(보정값, 사유)`.

    > 약팀 상대 대승은 **깎고** 강팀 상대 결과는 **올린다**.

    ⚠️ Elo 를 못 받으면 **보정하지 않는다**(원값 그대로 · 사유에 적는다).
    """
    if mine_elo is None or their_elo is None:
        return float(goals), "Elo 를 못 받아 **보정 안 했다**"
    gap = (float(their_elo) - float(mine_elo)) / 100.0
    mul = 1.0 + ELO_SLOPE * gap
    mul = max(0.5, min(1.5, mul))       # 🔴 극단을 자른다(보정이 결과를 덮지 않게)
    return round(float(goals) * mul, 3), (
        f"상대 Elo {their_elo:.0f} vs 우리 {mine_elo:.0f} → ×{mul:.2f} "
        f"({PROVISIONAL} · 기울기 {ELO_SLOPE})")


def form_of(team: str, rows: list[dict], *, elo: dict | None = None,
            luck_discount: float | None = None) -> TeamForm:
    """🔴🔴 §1 — **경기 목록 → 보정 폼**.

    `rows` 한 줄: `{"home_name","away_name","gf","ga","opp"}` —
    `gf`·`ga` 는 **우리 기준** 득점·실점이고 `opp` 는 상대 이름이다.
    `elo` 는 `{팀 이름: 등급}`(`leagueelo` 가 준 것).
    `luck_discount` 는 §3 T12 가 준 할인 비율(0~1) — 있으면 공격 지수를 깎는다.
    """
    got = TeamForm(team=str(team or ""))
    box = dict(elo or {})
    mine = box.get(str(team))
    said: list[str] = []
    for row in (rows or [])[-RECENT:]:
        one = dict(row)
        gf, ga = float(one.get("gf") or 0.0), float(one.get("ga") or 0.0)
        their = box.get(str(one.get("opp") or ""))
        a, why_a = adjust_one(gf, mine_elo=mine, their_elo=their)
        b, _why_b = adjust_one(ga, mine_elo=their, their_elo=mine)
        got.n += 1
        got.gf += gf
        got.ga += ga
        got.adj_gf += a
        got.adj_ga += b
        if len(said) < 2:
            said.append(why_a)
    if luck_discount is not None and got.n:
        # 🔴 §1 마지막 줄 — **운 요소 비중이 큰 득점은 폼에서 일부 할인**
        got.gf_after_luck = round(got.adj_gf * (1.0 - float(luck_discount)), 3)
        said.append(f"운 요소 할인 ×{1.0 - float(luck_discount):.2f}(T12)")
    got.why = (f"최근 {got.n}경기 — 득점 {got.gf:.0f}→보정 {got.adj_gf:.1f} · "
               f"실점 {got.ga:.0f}→보정 {got.adj_ga:.1f}"
               + (" · " + " · ".join(said) if said else ""))
    return got


def percentile(value: float | None, pool: list[float]) -> float | None:
    """🔴 §1 — **같은 리그 팀 대비 백분위**. 비교 대상이 없으면 `None`.

    ⚠️ 비교 대상이 **3팀 미만이면 비운다** — 두 팀만으로 백분위를 적으면 늘
       0% 아니면 100% 다(그 수는 사람을 속인다).
    """
    rows = [float(x) for x in (pool or []) if x is not None]
    if value is None or len(rows) < 3:
        return None
    n = sum(1 for x in rows if x < float(value))
    return round(n / len(rows), 3)
