"""[4단계] 득점 **분포 형태** 캘리브레이션 — 포아송이 맞는가, 과분산인가.

배경(2026-08-26 실측): λ 합계 평균 8.65인데 실제 총득점 평균 8.92였고,
동시에 라인 7.5에서 모델 오버확률 0.6177 vs 실제 0.5551이었다.
**평균은 낮은데 오버는 과다 예측**한다 — 평균 편차만으로는 설명되지 않는다.
분포 **형태**가 어긋났다는 신호다.

여기서 재는 것:
  ① λ 합계 vs 실제 총득점 (평균 편차)
  ② 포아송 vs 음이항(과분산) — 라인별 캘리브레이션과 Brier
  ③ 실측 F5 득점 비중 (config `f5_share` 검증)

⚠️ 운영과 같은 조건으로 잰다 — `recent_window_games`(경기 수 창)와
   `offense_symmetric`(대칭 타선)을 config에서 그대로 읽어 쓴다. 백테스트가
   운영과 다른 설정으로 돌면 그 수치는 운영을 설명하지 못한다.
⚠️ 기준선은 모델과 같은 자유도로 — 토탈은 **라인별** 보고(§8-4).
"""

import argparse
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.backtest_window import pitcher_prior_by_starts, team_prior_by_games  # noqa: E402

TOTAL_LINES = (7.5, 8.5, 9.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--dispersions", default="none,4,6,8,12,20",
                    help="음이항 r 후보. none=포아송")
    args = ap.parse_args()

    import pandas as pd

    from app.config import get_settings
    from app.engine.scoring import MAX_RUNS, mlb_lambdas, score_pmf
    from app.models import features as F

    s = get_settings()
    print(f"원본 로드: {args.pickle}")
    print(f"운영 설정 — 창 {s.recent_window_games}경기 / 선발 {s.recent_window_starts}등판 "
          f"/ 대칭타선 {s.offense_symmetric} / f5_share {s.f5_share}")

    df = pickle.load(open(args.pickle, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    sm = F.starters(d)
    pg = F.pitcher_game_stats(d, sm)
    smap = {(int(r["game_pk"]), str(r["team"])): r["pitcher"] for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"), pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=30)

    # F5 실제 득점 (§8-4에서 검증한 추출식)
    f5 = d[d["inning"] <= 5]
    piv = f5.groupby(["game_pk", "bat_team"], as_index=False).agg(f5=("post_bat_score", "max"))
    bot5 = set(d[(d["inning"] == 5)
                 & (d["inning_topbot"].astype(str).str.startswith("Bot"))]["game_pk"])

    start = pd.Timestamp(args.start)
    rows = []
    for _, g in games.iterrows():
        if g["date"] < start:
            continue
        res, ok = {}, True
        for side, team in (("home", g["home"]), ("away", g["away"])):
            o = team_prior_by_games(team_day, team, g["date"], s.recent_window_games, 120)
            if o is None:
                ok = False
                break
            res[f"{side}_offense"] = {"xwoba_30d": round(float(o["off_xwoba"]), 4)}
            pid = smap.get((int(g["game_pk"]), str(team)))     # 자기 팀 선발
            p = pitcher_prior_by_starts(pg, pid, g["date"], s.recent_window_starts, 20) if pid else None
            if p is not None:
                res[f"{side}_pitcher"] = {"xwoba_allowed": round(float(p["sp_xwoba_allowed"]), 4)}
        if not ok:
            continue
        park = parks.get((g["game_pk"], g["home"]))
        if park is not None:
            res["park_factor"] = round(float(park), 4)
        lam = mlb_lambdas({"home": g["home"], "away": g["away"]}, res, s)
        if not lam.usable:
            continue
        r = {"lam": lam.home + lam.away, "lh": lam.home, "la": lam.away,
             "total": g["home_runs"] + g["away_runs"],
             "home_won": int(g["home_runs"] > g["away_runs"]),
             "tie": int(g["home_runs"] == g["away_runs"])}
        if int(g["game_pk"]) in bot5:
            sub = piv[piv["game_pk"] == g["game_pk"]]
            if len(sub) == 2:
                r["f5_total"] = float(sub["f5"].sum())
        rows.append(r)

    t = pd.DataFrame(rows)
    n = len(t)
    print(f"\n표본 {n}경기")
    print(f"① λ 합계 평균 {t['lam'].mean():.3f} / 실제 총득점 평균 {t['total'].mean():.3f} "
          f"→ 편차 {t['lam'].mean() - t['total'].mean():+.3f} "
          f"({(t['lam'].mean() / t['total'].mean() - 1) * 100:+.1f}%)")
    print(f"   실제 총득점 분산 {t['total'].var():.3f} / 평균 {t['total'].mean():.3f} "
          f"→ 분산/평균 {t['total'].var() / t['total'].mean():.3f}  (1.0=포아송)")

    f5t = t["f5_total"].dropna()
    if len(f5t):
        share = f5t.mean() / t.loc[f5t.index, "total"].mean()
        print(f"③ 실측 F5 비중 {share:.4f}  (config f5_share={s.f5_share} · "
              f"차이 {share - s.f5_share:+.4f})  n={len(f5t)}")

    print("\n② 분포 형태 비교 — **운영과 동일하게** λ_home·λ_away를 따로 합성한다")
    cands = [None if x.strip().lower() == "none" else float(x)
             for x in args.dispersions.split(",")]
    nd = t["tie"] == 0                      # 승패는 무승부 제외
    h_base = max(t.loc[nd, "home_won"].mean(), 1 - t.loc[nd, "home_won"].mean())
    print(f"  (승패 기준선 {h_base:.4f} · n={int(nd.sum())})")
    print(f"  {'분산모수':>10} {'토탈Brier합':>11} {'승패Brier':>10} {'승패정확도':>11} | "
          + " | ".join(f"{f'{ln} 예측/실제/적중':>22}" for ln in TOTAL_LINES))
    for disp in cands:
        label = "포아송" if disp is None else f"음이항 r={disp:g}"
        overs = {ln: [] for ln in TOTAL_LINES}
        pwin = []
        for lh, la in zip(t["lh"], t["la"]):
            ph = score_pmf(lh, MAX_RUNS, disp)
            pa = score_pmf(la, MAX_RUNS, disp)
            cdf = [0.0] * (2 * MAX_RUNS + 2)
            w = 0.0
            for i, x in enumerate(ph):
                for j, y in enumerate(pa):
                    cdf[i + j] += x * y
                    if i > j:
                        w += x * y
            # 무승부(연장) 몫을 승/패에 비례 배분 — mlb_market_probs와 같은 처리
            tie = sum(ph[k] * pa[k] for k in range(len(ph)))
            pwin.append(w / (1 - tie) if tie < 1 else 0.5)
            for ln in TOTAL_LINES:
                overs[ln].append(sum(cdf[k] for k in range(int(ln) + 1, len(cdf))))
        cells, brier_sum = "", 0.0
        for ln in TOTAL_LINES:
            po = pd.Series(overs[ln], index=t.index)
            act = (t["total"] > ln).astype(int)
            brier_sum += float(((po - act) ** 2).mean())
            acc = float(((po > 0.5).astype(int) == act).mean())
            cells += f" | {po.mean():>7.4f}/{act.mean():.4f}/{acc:.4f}"
        pw = pd.Series(pwin, index=t.index)[nd]
        hb = float(((pw - t.loc[nd, "home_won"]) ** 2).mean())
        ha = float(((pw > 0.5).astype(int) == t.loc[nd, "home_won"]).mean())
        print(f"  {label:>10} {brier_sum:>11.4f} {hb:>10.4f} {ha:>11.4f}{cells}")
    print("\n  토탈 Brier합이 낮을수록 확률이 정직하다 — EV 계산의 근간이다.")
    print("  ⚠️ 승패 정확도가 함께 나빠지면 채택하지 마라(분포는 전 마켓 공용이다).")


if __name__ == "__main__":
    main()
