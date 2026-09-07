"""[적합] 자료12 elo 파라미터를 **우리 경기로** 맞춘다. LLM 을 건드리지 않는다.

🔴 왜 (실측 2026-09-07):
   레이팅이 거의 벌어지지 않는다 — 폭 KBO 67.4 · NPB 68.1 · **MLB 49.7**
   (sd 22.3 / 21.3 / 14.0). 리그 최강 대 최약이 홈에서 붙어도 기대 승률이
   59.2%(MLB)라 자료12 가 만들 수 있는 최대 편차가 ±9.2%p 다.
   반면 시장은 일상적으로 70%대를 매긴다(MLB 우세팀 내재확률 최대 75.8%).
   `team_elo.py` 가 적은 "우리 p ↔ 시즌 실력 r=+0.279 vs 시장 +0.707" 의
   유력한 설명이 이것이다 — 축은 넣었는데 **진폭이 없다.**

   원인 후보는 감쇠다. `elo_decay=0.9`/일이면 14일 전 경기 가중치가 0.229,
   30일 전은 0.042 라 사실상 최근 2주만 반영된다. 팀당 유효 경기가 ~12경기고
   K=20 으로는 레이팅이 벌어질 시간이 없다.

🔴 관문 (실행 **전** 선언, 결과 보고 후 변경 금지):
   지표는 walk-forward **log-loss**. 앞 70%로 파라미터를 고르고 뒤 30%
   (선택에 쓰지 않은 구간)에서만 보고한다. 새 값이 현행 운영값 대비
   **세 리그 전부** 홀드아웃 log-loss 를 낮출 때만 변경을 검토한다.
   하나라도 못 낮추면 **변경 없음.**

⚠️ 누수 방지가 이 도구의 성패다. `team_elo.compute()` 는 감쇠 기준 시점을
   **마지막 경기**로 잡는다 — "오늘 시점 레이팅"에는 맞지만, 과거 경기 i 를
   예측할 때 그대로 쓰면 미래를 안고 가중치를 매기는 셈이다. 여기서는 매
   예측 시점마다 그 시점 기준으로 다시 리플레이한다(O(n²), n≤400 이라 싸다).

⚠️ 무승부는 log-loss 에서 0.5 로 채점하고 방향 채점에서는 뺀다
   (`elo_core.replay` 의 score 규약과 같다).

사용법:
    PYTHONPATH=. uv run python tools/fit_elo.py
    PYTHONPATH=. uv run python tools/fit_elo.py --sport mlb --holdout 0.3
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: 훑을 값. 현행 운영값이 반드시 포함돼야 비교가 성립한다.
DECAYS = (0.90, 0.95, 0.97, 0.99, 1.00)
KS = (10.0, 20.0, 32.0, 48.0)
HOME_ADVS = (15.0,)

_GAMES = """
    SELECT home, away, home_score, away_score, starts_at
      FROM games
     WHERE sport = $1 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
     ORDER BY starts_at, id
"""

EPS = 1e-9


def _res(hs, as_) -> str:
    return "H" if hs > as_ else "A" if as_ > hs else "D"


def ratings_asof(matches: list[dict], upto: int, decay: float, k: float,
                 home_adv: float) -> dict[str, float]:
    """`matches[:upto]` 만으로 만든 레이팅. 감쇠 기준은 **그 구간의 끝**이다.

    🔴 여기가 누수를 막는 자리다. `team_elo.compute` 를 그대로 부르면
       감쇠 기준이 전체 마지막 경기가 되어 미래 시점이 새어 들어온다.
    """
    from app.models.elo_core import replay
    from app.models.team_elo import _decay_weight

    if upto <= 0:
        return {}
    window = matches[:upto]
    latest = window[-1].get("ts")
    ratings, _ = replay(window, home_adv=home_adv, k=k,
                        weight=lambda m: _decay_weight(decay, latest, m.get("ts")))
    return ratings


def evaluate(matches: list[dict], *, decay: float, k: float, home_adv: float,
             min_games: int, start: int, end: int) -> dict:
    """`[start, end)` 구간을 walk-forward 로 채점. 반환 지표 dict.

    각 경기마다 **그 경기 이전** 행만으로 레이팅을 다시 만들어 예측한다.
    """
    from app.models.elo_core import expected_home

    played: dict[str, int] = {}
    for m in matches[:start]:
        played[m["home"]] = played.get(m["home"], 0) + 1
        played[m["away"]] = played.get(m["away"], 0) + 1

    ll, br, n = 0.0, 0.0, 0
    hit, dec_n = 0, 0
    ps: list[float] = []
    for i in range(start, end):
        m = matches[i]
        h, a = m["home"], m["away"]
        if played.get(h, 0) >= min_games and played.get(a, 0) >= min_games:
            r = ratings_asof(matches, i, decay, k, home_adv)
            if h in r and a in r:
                p = expected_home(r[h] + home_adv - r[a])
                p = min(max(p, EPS), 1 - EPS)
                y = 1.0 if m["res"] == "H" else 0.0 if m["res"] == "A" else 0.5
                ll += -(y * math.log(p) + (1 - y) * math.log(1 - p))
                br += (p - y) ** 2
                n += 1
                ps.append(p)
                if m["res"] != "D":
                    dec_n += 1
                    hit += int((p > 0.5) == (m["res"] == "H"))
        played[h] = played.get(h, 0) + 1
        played[a] = played.get(a, 0) + 1
    if not n:
        return {"n": 0}
    return {"n": n, "logloss": ll / n, "brier": br / n,
            "acc": (hit / dec_n) if dec_n else float("nan"), "dec_n": dec_n,
            "p_min": min(ps), "p_max": max(ps),
            "p_spread": max(ps) - min(ps)}


def baseline(matches: list[dict], start: int, end: int) -> dict:
    """비교선: **그 시점까지의 홈 승률 상수**. 이걸 못 이기면 축이 무의미하다."""
    ll, br, n = 0.0, 0.0, 0
    h_wins = h_n = 0
    for m in matches[:start]:
        if m["res"] != "D":
            h_n += 1
            h_wins += int(m["res"] == "H")
    for i in range(start, end):
        m = matches[i]
        p = (h_wins / h_n) if h_n else 0.5
        p = min(max(p, EPS), 1 - EPS)
        y = 1.0 if m["res"] == "H" else 0.0 if m["res"] == "A" else 0.5
        ll += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        br += (p - y) ** 2
        n += 1
        if m["res"] != "D":
            h_n += 1
            h_wins += int(m["res"] == "H")
    return {"n": n, "logloss": ll / n if n else float("nan"),
            "brier": br / n if n else float("nan")}


async def load(pool, sport: str) -> list[dict]:
    rows = await pool.fetch(_GAMES, sport)
    return [{"home": r["home"], "away": r["away"], "ts": r["starts_at"],
             "res": _res(r["home_score"], r["away_score"])} for r in rows]


def run_sport(sport: str, matches: list[dict], *, holdout: float,
              min_games: int, cur: tuple) -> None:
    n = len(matches)
    split = int(n * (1 - holdout))
    warm = min(split, max(30, min_games * 4))     # 선택 구간의 예열
    print(f"\n{'=' * 74}\n[{sport.upper()}] 종료 {n}경기 · "
          f"선택 구간 [{warm}, {split}) · 홀드아웃 [{split}, {n})")
    if n - split < 30 or split - warm < 30:
        print("   표본 부족 — 생략")
        return

    # ── 선택 구간에서 고른다 (홀드아웃은 보지 않는다)
    rows = []
    for d in DECAYS:
        for k in KS:
            for ha in HOME_ADVS:
                r = evaluate(matches, decay=d, k=k, home_adv=ha,
                             min_games=min_games, start=warm, end=split)
                if r["n"]:
                    rows.append(((d, k, ha), r))
    if not rows:
        print("   선택 구간 채점 0건 — 생략")
        return
    rows.sort(key=lambda x: x[1]["logloss"])
    best = rows[0][0]
    print(f"   {'decay':>6s} {'K':>5s} {'ha':>4s} {'n':>4s} "
          f"{'logloss':>9s} {'brier':>7s} {'방향':>6s} {'p폭':>6s}")
    for (d, k, ha), r in rows[:6]:
        mark = "★" if (d, k, ha) == best else " " if (d, k, ha) != cur else "▶"
        print(f" {mark} {d:6.2f} {k:5.0f} {ha:4.0f} {r['n']:4d} "
              f"{r['logloss']:9.5f} {r['brier']:7.4f} {r['acc']*100:5.1f}% "
              f"{r['p_spread']:6.3f}")
    cur_sel = next((r for p, r in rows if p == cur), None)
    if cur_sel and cur not in [p for p, _ in rows[:6]]:
        print(f" ▶ {cur[0]:6.2f} {cur[1]:5.0f} {cur[2]:4.0f} {cur_sel['n']:4d} "
              f"{cur_sel['logloss']:9.5f} {cur_sel['brier']:7.4f} "
              f"{cur_sel['acc']*100:5.1f}% {cur_sel['p_spread']:6.3f}  (현행)")

    # ── 홀드아웃에서만 보고한다
    print(f"\n   ── 홀드아웃 [{split}, {n}) — 선택에 쓰지 않은 구간")
    base = baseline(matches, split, n)
    out = {}
    for label, par in (("현행", cur), ("후보", best)):
        r = evaluate(matches, decay=par[0], k=par[1], home_adv=par[2],
                     min_games=min_games, start=split, end=n)
        out[label] = (par, r)
        if not r["n"]:
            print(f"      {label} {par} — 채점 0건")
            continue
        print(f"      {label:4s} decay={par[0]:.2f} K={par[1]:.0f} "
              f"n={r['n']:3d} logloss={r['logloss']:.5f} "
              f"brier={r['brier']:.4f} 방향={r['acc']*100:.1f}% "
              f"p폭={r['p_spread']:.3f}")
    print(f"      기준선(홈승률 상수) n={base['n']:3d} "
          f"logloss={base['logloss']:.5f} brier={base['brier']:.4f}")
    if out.get("현행") and out.get("후보") and out["현행"][1]["n"] and out["후보"][1]["n"]:
        d = out["현행"][1]["logloss"] - out["후보"][1]["logloss"]
        print(f"      → 후보가 현행보다 logloss {d:+.5f} "
              f"({'개선' if d > 0 else '악화'})")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="kbo,npb,mlb")
    ap.add_argument("--holdout", type=float, default=0.3)
    args = ap.parse_args()

    from app.config import get_settings
    from app.db import close_pool, get_pool
    from app.models.team_elo import HOME_ADV, K_FACTOR, MIN_GAMES

    s = get_settings()
    cur = (float(s.elo_decay), float(K_FACTOR), float(HOME_ADV))
    print(f"현행 운영값: decay={cur[0]} K={cur[1]:.0f} home_adv={cur[2]:.0f} "
          f"· MIN_GAMES={MIN_GAMES}")
    print("관문: 홀드아웃 logloss 를 **세 리그 전부** 낮춰야 변경을 검토한다.")
    pool = await get_pool()
    try:
        for sp in [x.strip() for x in args.sport.split(",") if x.strip()]:
            run_sport(sp, await load(pool, sp), holdout=args.holdout,
                      min_games=MIN_GAMES, cur=cur)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
