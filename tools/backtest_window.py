"""[0단계] **관측 창 길이 비교** — "지난 3경기만 본다"가 30일보다 나쁜가.

재설계 지시 2번("오로지 지난 3경기로만 분석")을 채택하기 전에 반드시 재는 값이다.
과거 데이터를 버리고 나면 이 비교는 **영원히 불가능**해진다. 그래서 폐기 전에 한 번
돌린다. API 호출 0회 — 이미 받아둔 Statcast 원본만 쓴다.

배경 실측(§8-3 · §8-4 · offense_metrics):
  - 30일 창(팀당 약 1,000타석, 안정화 한참 넘김)에서도 타선 지표 상관은 r≈0.025였다.
  - 즉 **안정화가 부족해서 신호가 없는 게 아니다.** 팀 단위 집계 자체가 약하다.
  - 그렇다면 창을 3경기로 줄여도 잃을 신호가 별로 없을 수 있다 — 그것을 여기서 잰다.

⚠️ 표본 하한을 창마다 낮춘다 — 이건 결과 조작이 아니라 **측정의 전제**다.
   현행 `MIN_PRIOR_PA = 120`은 3경기(약 115타석)를 통째로 탈락시킨다. 3경기 창을
   재려면 하한을 내려야 하고, 그 대가로 지표가 더 시끄러워진다. 그 시끄러움까지
   포함해서 비교하는 것이 이 측정의 목적이다.

⚠️ 누수 방지: 모든 사전 지표는 그 경기 **이전** 경기만 쓴다 (`game_date < date`).
⚠️ 기준선은 모델과 **같은 자유도**로 낸다 — 토탈은 라인별 층화, 풀링 단독 보고 금지(§8-4).
"""

import argparse
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 비교할 창. ("라벨", 팀 최근 N경기, 선발 최근 N등판, 최소 타석)
WINDOWS = [
    ("3경기",  3,  3,  40),
    ("7경기",  7,  5,  90),
    ("15경기", 15, 8,  120),
    ("30경기", 30, 12, 120),
    ("30일(현행)", None, None, 120),
]
TOTAL_LINES = (7.5, 8.5, 9.5)


def team_prior_by_games(team_day, team, date, n_games, min_pa):
    """팀 타선 사전 지표 — **최근 n_games 경기**(일수 아님). None이면 30일 창."""
    import pandas as pd

    sub = team_day[(team_day["bat_team"] == team) & (team_day["game_date"] < date)]
    if sub.empty:
        return None
    if n_games is None:
        sub = sub[sub["game_date"] >= date - pd.Timedelta(days=30)]
    else:
        sub = sub.sort_values("game_date").tail(n_games)
    if sub.empty:
        return None
    s = sub[["xw_sum", "xw_n", "pa"]].sum()
    if s["xw_n"] < min_pa:
        return None
    return {"off_xwoba": s["xw_sum"] / s["xw_n"], "pa": float(s["pa"])}


def pitcher_prior_by_starts(pg, pitcher_id, date, n_starts, min_bf):
    """선발 사전 지표 — **최근 n_starts 등판**. None이면 45일 창(현행)."""
    import pandas as pd

    hist = pg[(pg["pitcher"] == pitcher_id) & (pg["game_date"] < date)]
    if hist.empty:
        return None
    hist = hist.sort_values("game_date")
    w = (hist[hist["game_date"] >= date - pd.Timedelta(days=45)] if n_starts is None
         else hist.tail(n_starts))
    if w.empty or w["xw_n"].sum() < min_bf:
        return None
    return {"sp_xwoba_allowed": w["xw_sum"].sum() / max(1, w["xw_n"].sum()),
            "bf": float(w["xw_n"].sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--min-games", type=int, default=30, help="파크팩터 최소 표본")
    args = ap.parse_args()

    import pandas as pd

    from app.config import get_settings
    from app.engine.scoring import cap_probability, mlb_lambdas, mlb_market_probs
    from app.models import features as F

    print(f"원본 로드: {args.pickle}")
    df = pickle.load(open(args.pickle, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    sm = F.starters(d)
    pg = F.pitcher_game_stats(d, sm)
    starter_map = {(int(r["game_pk"]), str(r["team"])): r["pitcher"]
                   for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=args.min_games)
    s = get_settings()
    start = pd.Timestamp(args.start)
    target = games[(games["date"] >= start) & (games["home_runs"] != games["away_runs"])]
    print(f"대상 경기 {len(target)}건 ({args.start} 이후, 무승부 제외)\n")

    summary = []
    for label, ng, ns, min_pa in WINDOWS:
        h2h, tot, skipped = [], [], 0
        for _, g in target.iterrows():
            res, ok = {}, True
            for side, team in (("home", g["home"]), ("away", g["away"])):
                o = team_prior_by_games(team_day, team, g["date"], ng, min_pa)
                if o is None:
                    ok = False
                    break
                res[f"{side}_offense"] = {"xwoba_30d": round(float(o["off_xwoba"]), 4)}
                # ⚠️ 그 팀의 **자기 선발**을 넣는다 — `{side}_pitcher`의 운영 정의다.
                #    상대 선발을 넣으면 mlb_lambdas가 pit[opp]를 쓰면서 부호가 뒤집힌다.
                pid = starter_map.get((int(g["game_pk"]), str(team)))
                p = (pitcher_prior_by_starts(pg, pid, g["date"], ns, 20) if pid else None)
                if p is not None:
                    res[f"{side}_pitcher"] = {
                        "xwoba_allowed": round(float(p["sp_xwoba_allowed"]), 4)}
            if not ok:
                skipped += 1
                continue
            park = parks.get((g["game_pk"], g["home"]))
            if park is not None:
                res["park_factor"] = round(float(park), 4)
            lam = mlb_lambdas({"home": g["home"], "away": g["away"]}, res, s)
            if not lam.usable:
                skipped += 1
                continue
            pm = mlb_market_probs(lam.home, lam.away, {"totals": list(TOTAL_LINES)},
                                  s.score_dispersion, settings=s)
            ph, _ = cap_probability(pm["h2h"]["home"], "mlb", s)
            h2h.append((ph, int(g["home_runs"] > g["away_runs"])))
            t = g["home_runs"] + g["away_runs"]
            for ln in TOTAL_LINES:
                po = (pm.get("totals") or {}).get(ln, {}).get("Over")
                if po is not None:
                    tot.append((ln, po, int(t > ln)))

        if not h2h:
            print(f"{label:>12}  산출 가능 경기 0건 (표본 하한 미달)")
            continue
        H = pd.DataFrame(h2h, columns=["p", "y"])
        T = pd.DataFrame(tot, columns=["line", "p", "y"])
        h_acc = ((H.p > .5).astype(int) == H.y).mean()
        h_base = max(H.y.mean(), 1 - H.y.mean())
        h_brier = ((H.p - H.y) ** 2).mean()
        # 토탈: 라인별 기준선을 표본 가중 평균 (모델과 같은 자유도) — §8-4
        gb = T.groupby("line")["y"]
        w = gb.size()
        t_base = float((gb.mean().combine(1 - gb.mean(), max) * w).sum() / w.sum())
        t_acc = ((T.p > .5).astype(int) == T.y).mean()
        summary.append({
            "label": label, "n": len(H), "skipped": skipped,
            "h_acc": h_acc, "h_base": h_base, "h_brier": h_brier,
            "t_acc": t_acc, "t_base": t_base,
            "t85_acc": ((T[T.line == 8.5].p > .5).astype(int) == T[T.line == 8.5].y).mean(),
            "t85_base": max(T[T.line == 8.5].y.mean(), 1 - T[T.line == 8.5].y.mean()),
        })

    print(f"{'창':>12} {'n':>6} {'제외':>6} | {'승패':>8} {'기준선':>8} {'차이':>8} "
          f"{'Brier':>8} | {'토탈':>8} {'기준선':>8} {'차이':>8} | {'토탈8.5':>8} {'차이':>8}")
    print("-" * 118)
    for r in summary:
        print(f"{r['label']:>12} {r['n']:>6} {r['skipped']:>6} | "
              f"{r['h_acc']:>8.4f} {r['h_base']:>8.4f} {r['h_acc']-r['h_base']:>+8.4f} "
              f"{r['h_brier']:>8.4f} | "
              f"{r['t_acc']:>8.4f} {r['t_base']:>8.4f} {r['t_acc']-r['t_base']:>+8.4f} | "
              f"{r['t85_acc']:>8.4f} {r['t85_acc']-r['t85_base']:>+8.4f}")
    print()
    print("판정 기준: '차이'가 0보다 커야 그 창이 기준선을 이긴 것이다.")
    print("           3경기 창의 차이가 30일 창보다 나쁘지 않으면 지시 2번은 방어된다.")


if __name__ == "__main__":
    main()
