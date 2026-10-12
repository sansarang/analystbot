"""🔴 **(a) Elo — 현행**(지시서 §2 후보 셋). 골 차를 **안 본다**.

🔴 식은 `app/collect/leagueelo.compute` 와 같은 꼴이다 — ⚠️ 그 함수는
   football-data 응답 꼴(`utcDate`)에 묶여 있고, 여기는 **어댑터 꼴 하나**
   (`rows_of`)를 받는다. 🔴 수를 짓지 않는다(K·시작 등급은 **판 파일**).
"""
from __future__ import annotations

from app.core.ratings import Params, RatingTable, rows_of

#: 🔴 격자 탐색이 흔드는 이름표(`tools/fit_ratings.py` 가 읽는다)
PARAMS: tuple[str, ...] = ("k",)


def rate(matches: list[dict], *, params: Params, as_of) -> RatingTable:
    """🔴 시간 순으로 Elo 를 굴린다. **`as_of` 이전만**(R1)."""
    k = params.get("k", 20.0)
    start = params.get("start", 1500.0)
    said = rows_of(matches, as_of=as_of)
    rate_now: dict[str, float] = {}
    for _when, home, away, hg, ag in said:
        ra = rate_now.setdefault(home, start)
        rb = rate_now.setdefault(away, start)
        we = 1.0 / (10.0 ** (-(ra - rb) / 400.0) + 1.0)
        got = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        rate_now[home] = ra + k * (got - we)
        rate_now[away] = rb - k * (got - we)
    return RatingTable(
        teams={t: {"home": round(v, 2), "away": round(v, 2),
                   "overall": round(v, 2)} for t, v in rate_now.items()},
        as_of=as_of, n_matches=len(said), kind="elo",
        params_ver=params.ver)


def prob_input(home: str, away: str, table: RatingTable) -> float:
    """🔴 `diff` — **등급 차 한 수**(Elo 점수 단위)."""
    a, _w1 = table.of(home)
    b, _w2 = table.of(away)
    return float(a) - float(b)
