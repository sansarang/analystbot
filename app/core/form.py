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
    #: 🔴🔴 **실제로 뺀 골 수**(사용자 지시 2026-10-11 ②) — 계약이 이 수를 센다
    luck_cut_goals: float = 0.0
    #: 🔴 한 원천에서 자른 두 창(`{"5": {...}, "10": {...}}`) — 카드가 그대로 적는다
    windows: dict = field(default_factory=dict)
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


#: 🔴🔴 **창 둘** — 카드의 폼 블록(5)과 축1(10). 한 목록에서 **둘 다** 자른다.
WINDOWS = (5, 10)


def window_sums(games: list[dict], n: int) -> dict:
    """🔴🔴 ① — **한 경기 목록에서 최근 n경기**를 잘라 득·실을 센다.

    > 폼 블록(5경기)과 축1(10경기)의 경기 목록을 날짜·대회·스코어로 나란히 찍어라.
    > **한 원천(같은 경기 목록)에서 두 창을 자른다.** — 사용자 지시 2026-10-11 ①

    한 줄 꼴은 `s2e_matchup.games_of` 가 만드는 것이다 —
    `{date, league, opp, side, score, gf, ga}`. ⚠️ 목록이 n 보다 짧으면 **있는
    만큼**이고 `n` 칸에 그 수를 적는다(모자란 것을 0 으로 채우지 않는다 · #3).
    """
    rows = [dict(g) for g in (games or [])][-int(n):]
    return {"n": len(rows),
            "gf": sum(float(g.get("gf") or 0.0) for g in rows),
            "ga": sum(float(g.get("ga") or 0.0) for g in rows),
            "games": rows}


def sums_bad(small: dict, big: dict) -> str:
    """🔴🔴 ① 계약 — **최근 n경기 합 ≤ 최근 m경기 합**(n<m, 득·실 각각).

    어겼으면 **사유 글자**를 낸다(운영자 알림의 재료). 지켰으면 빈 글자다.
    ⚠️ 실사고 2026-10-11: *"밴쿠버 최근5 실점 10인데 최근10 실점 9"* — 두 블록이
       **다른 원천**을 읽어 생긴 수다. 한 목록에서 자르면 이 검사는 늘 통과한다
       (그래서 이 검사가 빨개지면 **원천이 또 갈라진 것**이다).
    """
    n, m = int(small.get("n") or 0), int(big.get("n") or 0)
    if not n or not m or n >= m:
        return ""
    out = []
    for key, name in (("gf", "득"), ("ga", "실")):
        a, b = float(small.get(key) or 0.0), float(big.get(key) or 0.0)
        if a > b + 1e-9:
            out.append(f"🔴 최근 {n}경기 {name}점 {a:g} > 최근 {m}경기 "
                       f"{name}점 {b:g} — 불가능하다(원천이 둘이다)")
    return " · ".join(out)


def windows_bad(games: list[dict]) -> str:
    """🔴 ① — 한 목록의 **모든 창 짝**을 검사한다(5 ≤ 10). 지켰으면 빈 글자."""
    out = []
    for i, n in enumerate(WINDOWS):
        for m in WINDOWS[i + 1:]:
            said = sums_bad(window_sums(games, n), window_sums(games, m))
            if said:
                out.append(said)
    return " · ".join(out)


def form_of(team: str, rows: list[dict], *, elo: dict | None = None,
            luck_goals: float | None = None,
            games: list[dict] | None = None) -> TeamForm:
    """🔴🔴 §1 — **경기 목록 → 보정 폼**.

    `rows` 한 줄: `{"home_name","away_name","gf","ga","opp"}` —
    `gf`·`ga` 는 **우리 기준** 득점·실점이고 `opp` 는 상대 이름이다.
    `elo` 는 `{팀 이름: 등급}`(`leagueelo` 가 준 것).
    `luck_goals` 는 §3 T12 가 센 **운 요소 골 수**(k) — 있으면 그만큼의 골을
    공격 지수에서 뺀다. 🔴 **비율이 아니다**(사용자 지시 2026-10-11 ②:
    *"빼는 골은 최대 k. ×0.5 일괄 할인 삭제"*).
    `games` 는 **그 팀의 한 경기 목록**(`window_sums` 가 읽는 꼴) — 주면 두 창
    (5·10)을 여기서 잘라 `windows` 에 적는다.
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **운 할인은 골 수다** — 사용자 지시 2026-10-11 ②
    # ══════════════════════════════════════════════════════════════════
    #
    #  > T12 "운 요소 득점 k/n"이면 빼는 골은 **최대 k**. ×0.5 일괄 할인 삭제.
    #  > LAFC 10골 중 3골이면 **7**.
    #
    #  🔴 보정 득점(`adj_gf`)에서 뺄 때는 **골 하나의 보정 몫**만큼 뺀다 —
    #     원골 10 중 3 을 빼면 보정도 30% 가 줄어든다(같은 골을 두 자로 세지 않게).
    #  ⚠️ k 가 원골보다 많으면 **원골까지만** 뺀다(계약: 할인 골 수 ≤ 운 골 수).
    if luck_goals is not None and got.n:
        k = max(0.0, min(float(luck_goals), float(got.gf)))
        got.luck_cut_goals = round(k, 3)
        per = (got.adj_gf / got.gf) if got.gf else 0.0
        got.gf_after_luck = round(max(0.0, got.adj_gf - k * per), 3)
        said.append(f"운 요소 골 {k:g}개를 뺐다(T12) — "
                    f"득점 {got.gf:.0f} → {got.gf - k:.0f}")
    if games:
        # 🔴 ① — **두 창을 여기서 자른다**(카드와 축1 이 같은 수를 본다)
        got.windows = {str(n): window_sums(games, n) for n in WINDOWS}
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
