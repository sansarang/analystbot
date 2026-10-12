"""🔴 **(b) ELOg — 골 차 반영**(지시서 §2): `k = k0·(1+δ)^λ`(δ = 절대 골 차).

🔴 왜 — Elo 는 5-0 과 1-0 을 **같게** 센다. ⚠️ 그 가중이 좋은지는 **백필이
   말한다**(§1 판정) — `k0`·`λ` 는 격자 적합으로 판에 적는다(손값 금지 · R2).
"""
from __future__ import annotations

from app.core.ratings import Params, RatingTable, rows_of

PARAMS: tuple[str, ...] = ("k0", "lam")


def rate(matches: list[dict], *, params: Params, as_of) -> RatingTable:
    k0 = params.get("k0", 10.0)
    lam = params.get("lam", 1.0)
    start = params.get("start", 1500.0)
    said = rows_of(matches, as_of=as_of)
    rate_now: dict[str, float] = {}
    for _when, home, away, hg, ag in said:
        ra = rate_now.setdefault(home, start)
        rb = rate_now.setdefault(away, start)
        we = 1.0 / (10.0 ** (-(ra - rb) / 400.0) + 1.0)
        got = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        # 🔴 골 차가 커지면 **K 가 커진다**(지시의 식 그대로)
        k = k0 * ((1.0 + abs(int(hg) - int(ag))) ** lam)
        rate_now[home] = ra + k * (got - we)
        rate_now[away] = rb - k * (got - we)
    return RatingTable(
        teams={t: {"home": round(v, 2), "away": round(v, 2),
                   "overall": round(v, 2)} for t, v in rate_now.items()},
        as_of=as_of, n_matches=len(said), kind="elog",
        params_ver=params.ver)


def prob_input(home: str, away: str, table: RatingTable) -> float:
    a, _w1 = table.of(home)
    b, _w2 = table.of(away)
    return float(a) - float(b)
