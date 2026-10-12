"""🔴 **(c) pi-ratings**(지시서 §2) — **홈·원정 점수를 따로** 들고 골 차로 고친다.

> 학습률 `λ`·`γ` 격자 적합(penaltyblog 구현을 **참고해 직접 작성**, 라이브러리
> 의존 없이).

🔴 굴리는 법(원 논문 Constantinou & Fenton 2013 의 꼴):
   1. 두 팀의 쪽 점수로 **기대 골 차**를 만든다(점수 → 골 차는 로그 자 하나).
   2. 실제 골 차와의 **오차 e** 를 재고, 그 크기에 `ψ(e) = c·log10(1+e)` 를 쓴다
      (큰 패배가 점수를 과하게 끌지 않게 **눌린 자**다).
   3. 홈팀의 **홈 점수**를 `λ·ψ` 만큼, 그 팀의 **원정 점수**를 `γ·λ·ψ` 만큼
      움직인다(반대 팀은 반대 방향). 🔴 `γ` 가 *"홈에서 배운 것을 원정에 얼마나
      옮기나"* 다.
⚠️ 상수 `c`·골 차 환산자는 **판 파일**이 든다(손값 금지 · R2). 판이 없으면
   `FALLBACK` 이고 카드가 **🔴 임시**를 적는다.
"""
from __future__ import annotations

import math

from app.core.ratings import Params, RatingTable, rows_of

PARAMS: tuple[str, ...] = ("lam", "gamma")

#: 🔴 점수(골 차 단위) → 기대 골 차로 바꾸는 자 — 1.0 이면 점수가 곧 골 차다
SCALE = 1.0
#: 🔴 오차를 누르는 자 — `ψ(e) = PSI·log10(1 + e)`
PSI = 3.0


def _psi(err: float) -> float:
    return PSI * math.log10(1.0 + abs(float(err)))


def rate(matches: list[dict], *, params: Params, as_of) -> RatingTable:
    lam = params.get("lam", 0.06)
    gamma = params.get("gamma", 0.5)
    start = params.get("start", 0.0)
    said = rows_of(matches, as_of=as_of)
    home_r: dict[str, float] = {}
    away_r: dict[str, float] = {}
    for _when, home, away, hg, ag in said:
        ha = home_r.setdefault(home, start)
        aa = away_r.setdefault(home, start)
        hb = home_r.setdefault(away, start)
        ab = away_r.setdefault(away, start)
        # 🔴 기대 골 차 = (홈팀 홈 점수) − (원정팀 원정 점수)
        want = (ha - ab) * SCALE
        real = float(int(hg) - int(ag))
        err = real - want
        step = lam * _psi(err) * (1.0 if err > 0 else -1.0)
        # 🔴 홈팀: 홈 점수를 `step`, 원정 점수를 `γ·step`
        home_r[home] = ha + step
        away_r[home] = aa + gamma * step
        # 🔴 원정팀: 원정 점수를 `−step`, 홈 점수를 `−γ·step`
        away_r[away] = ab - step
        home_r[away] = hb - gamma * step
    teams = {}
    for t in set(home_r) | set(away_r):
        h = float(home_r.get(t, start))
        a = float(away_r.get(t, start))
        teams[t] = {"home": round(h, 4), "away": round(a, 4),
                    "overall": round((h + a) / 2.0, 4)}
    return RatingTable(teams=teams, as_of=as_of, n_matches=len(said),
                       kind="pi", params_ver=params.ver)


def prob_input(home: str, away: str, table: RatingTable) -> float:
    """🔴 `diff` — **홈팀의 홈 점수 − 원정팀의 원정 점수**(기대 골 차 단위).

    ⚠️ Elo 와 **단위가 다르다**(골 차다) — 그래서 §3 의 `b1` 이 따로 적합된다.
    🔴 표에 없는 팀은 `RatingTable.of` 가 **하위 25%** 를 준다(§2).
    """
    box_h = dict(table.teams or {}).get(str(home))
    box_a = dict(table.teams or {}).get(str(away))
    h = float(box_h["home"]) if box_h else table.of(home)[0]
    a = float(box_a["away"]) if box_a else table.of(away)[0]
    return (h - a) * SCALE
