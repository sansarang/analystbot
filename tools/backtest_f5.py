"""[백테스트] **F5(5이닝) 마켓** — λ가 어느 마켓을 맞히는지 가른다.

배경(2026-08-26 측정 + 딥서치):
  - 우리 λ는 승패에서 51.5%(기준선 52.8% 미달), 토탈에서 57.0%(기준선 52.4%)다.
  - 문헌: 베가스 배당조차 승패는 58.2%가 천장이고, 프로들은 **토탈에 엣지가 더 크다**고
    본다. 또 **F5는 북메이커가 가격 책정에 힘을 덜 써 비효율이 남는다**고 기록된다.
  - 절제 실험에서 선발 계수는 승패에 -3.6%p(해로움), 토탈에 +0.6%p였다. 선발은
    9이닝 전체가 아니라 **자기가 던지는 구간**에만 영향을 준다는 가설이 남는다.
    F5가 바로 그 구간이다.

이 스크립트가 재는 것:
  ① F5 승패(3-way) — λ 방향이 F5에서 살아나는가
  ② F5 토탈 — 전체 경기 토탈(+4.5%p)보다 나은가
  ③ 선발 담당 이닝 분모(game_innings) 스윕 — F5에서는 분모가 5에 가까워야 맞는가

⚠️ 토탈 라인은 **고정값**(F5 실전 라인 4.5·5.5)을 쓴다. λ에서 라인을 만들어 그 λ로
   예측하면 반올림 방향만 재게 되어 모델을 검증하지 못한다(초안의 설계 결함).

⚠️ 누수 방지: 피처는 그 경기 **이전** 데이터만 쓴다(features.py 계약).
⚠️ 한계: 리서치(결장·날씨·불펜)는 과거 재현 불가 — Statcast 축만 검증한다.
"""

import argparse
import copy
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.backtest_lambda import build_research  # noqa: E402


def f5_frame(d, games):
    """경기별 F5 실제 득점. `post_bat_score`는 그 타석 후 **공격 팀** 누적 점수다.

    5회말을 실제로 치른 경기만 남긴다(콜드·서스펜디드 제외) — F5 마켓의 정산 조건과
    같다. 검증: F5 득점이 최종 득점을 넘는 경기는 0건이어야 한다.
    """
    f5 = d[d["inning"] <= 5]
    piv = (f5.groupby(["game_pk", "bat_team"], as_index=False)
             .agg(f5_runs=("post_bat_score", "max")))
    g = games.merge(piv.rename(columns={"bat_team": "home", "f5_runs": "f5_home"}),
                    on=["game_pk", "home"], how="left")
    g = g.merge(piv.rename(columns={"bat_team": "away", "f5_runs": "f5_away"}),
                on=["game_pk", "away"], how="left")
    bot5 = d[(d["inning"] == 5)
             & (d["inning_topbot"].astype(str).str.startswith("Bot"))]["game_pk"]
    g = g[g["game_pk"].isin(set(bot5)) & g["f5_home"].notna() & g["f5_away"].notna()]
    return g.copy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-05-01")
    ap.add_argument("--min-games", type=int, default=30)
    ap.add_argument("--total-lines", default="4.5,5.5",
                    help="F5 토탈 고정 라인 (λ에서 유도하지 않는다)")
    ap.add_argument("--innings-sweep", default="5.0,6.0,7.0,9.0,1e9",
                    help="선발 담당 분모 후보 (1e9 = 선발 계수 사실상 제거)")
    args = ap.parse_args()

    import pandas as pd

    from app.config import get_settings
    from app.engine.scoring import mlb_lambdas, mlb_market_probs, score_pmf, MAX_RUNS
    from app.models import features as F

    print(f"원본 로드: {args.pickle}")
    df = pickle.load(open(args.pickle, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    gf5 = f5_frame(d, games)
    bad = gf5[(gf5["f5_home"] > gf5["home_runs"]) | (gf5["f5_away"] > gf5["away_runs"])]
    print(f"경기 {len(games)} · F5 정산 가능 {len(gf5)} · 정합성 위반 {len(bad)}건")
    if len(bad):
        print("⚠️ F5 득점이 최종을 넘는 경기가 있다 — 추출식이 틀렸다. 중단.")
        return

    sm = F.starters(d)
    pg = F.pitcher_game_stats(d, sm)
    starter_map = {(int(r["game_pk"]), str(r["team"])): r["pitcher"]
                   for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     barrel=("is_barrel", "sum"), hardhit=("is_hardhit", "sum"),
                     bip=("ls", "count"), k=("is_k", "sum"), bb=("is_bb", "sum"),
                     pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=args.min_games)

    s0 = get_settings()
    start = pd.Timestamp(args.start)
    innings = [float(x) for x in args.innings_sweep.split(",")]
    total_lines = [float(x) for x in args.total_lines.split(",")]
    variants = {inn: copy.copy(s0) for inn in innings}
    for inn, sv in variants.items():
        sv.game_innings = inn

    # 실제 F5 비중 — config f5_share가 맞는지 데이터로 확인한다
    share_actual = ((gf5["f5_home"] + gf5["f5_away"]).mean()
                    / (gf5["home_runs"] + gf5["away_runs"]).mean())
    print(f"실측 F5 득점 비중 {share_actual:.4f}  (config f5_share={s0.f5_share})")

    rows = []
    for _, g in gf5.iterrows():
        if g["date"] < start:
            continue
        jg = {"home": g["home"], "away": g["away"]}
        off, sp, ok = {}, {}, True
        for side, team in (("home", g["home"]), ("away", g["away"])):
            off[side] = F.team_offense_prior(team_day, team, g["date"]) or {}
            pid = starter_map.get((int(g["game_pk"]), str(team)))  # 자기 팀 선발
            sp[side] = (F.pitcher_prior(pg, pid, g["date"]) or {}) if pid else {}
            if not off[side].get("off_xwoba"):
                ok = False
        if not ok:
            continue
        res = build_research(g, off, sp, parks.get((g["game_pk"], g["home"])))
        row = {"f5_home": g["f5_home"], "f5_away": g["f5_away"],
               "f5_total": g["f5_home"] + g["f5_away"],
               "home_runs": g["home_runs"], "away_runs": g["away_runs"]}
        usable = True
        for inn, sv in variants.items():
            lam = mlb_lambdas(jg, res, sv)
            if not lam.usable:
                usable = False
                break
            pr = mlb_market_probs(lam.home, lam.away, None, sv.score_dispersion, settings=sv)
            row[f"h_{inn}"] = pr["f5"]["home"]
            row[f"a_{inn}"] = pr["f5"]["away"]
            row[f"d_{inn}"] = pr["f5"]["draw"]
            row[f"lam5_{inn}"] = pr["f5"]["lambda"]["home"] + pr["f5"]["lambda"]["away"]
            row[f"lam9_{inn}"] = lam.home + lam.away
            row[f"h9_{inn}"] = pr["h2h"]["home"]
            # F5 토탈 오버 확률 — F5 λ로 직접 합성(고정 라인)
            fh, fa = pr["f5"]["lambda"]["home"], pr["f5"]["lambda"]["away"]
            ph = score_pmf(fh, MAX_RUNS, sv.score_dispersion)
            pa = score_pmf(fa, MAX_RUNS, sv.score_dispersion)
            cdf = [0.0] * (2 * MAX_RUNS + 2)
            for i, x in enumerate(ph):
                for j, y in enumerate(pa):
                    cdf[i + j] += x * y
            for ln in total_lines:
                row[f"po{ln}_{inn}"] = sum(cdf[k] for k in range(int(ln) + 1, len(cdf)))
        if usable:
            rows.append(row)

    if not rows:
        print("검증 가능한 경기가 없다"); return
    t = pd.DataFrame(rows)
    n = len(t)

    # ---- 기준선: F5 3-way에서 가장 흔한 결과를 항상 고르는 전략
    res5 = pd.Series("draw", index=t.index)
    res5[t["f5_home"] > t["f5_away"]] = "home"
    res5[t["f5_home"] < t["f5_away"]] = "away"
    base3 = res5.value_counts(normalize=True).max()
    no_draw = t[t["f5_home"] != t["f5_away"]]
    base2 = max((no_draw["f5_home"] > no_draw["f5_away"]).mean(),
                (no_draw["f5_home"] < no_draw["f5_away"]).mean())

    print()
    print(f"=== F5 백테스트 ({args.start} 이후, {n}경기) ===")
    print(f"  F5 결과 분포: 홈승 {(res5=='home').mean():.4f} / "
          f"무 {(res5=='draw').mean():.4f} / 원정승 {(res5=='away').mean():.4f}")
    print(f"  기준선(3-way 최빈) {base3:.4f} · (무승부 제외 최빈) {base2:.4f}  n={len(no_draw)}")
    print()
    print(f"  {'선발 분모':>10} {'F5승패(무제외)':>14} {'F5 3-way':>10} "
          f"{'F5토탈':>8} {'전체승패':>9} {'Brier(F5홈)':>12}")
    for inn in innings:
        lab = "제거" if inn > 100 else f"{inn:.0f}이닝"
        # ① F5 승패 — 무승부 제외, 홈/원정 방향만
        m = t["f5_home"] != t["f5_away"]
        pick_home = t.loc[m, f"h_{inn}"] > t.loc[m, f"a_{inn}"]
        actual_home = t.loc[m, "f5_home"] > t.loc[m, "f5_away"]
        acc2 = (pick_home == actual_home).mean()
        # ② F5 3-way — 최대 확률 마켓 선택
        p3 = t[[f"h_{inn}", f"d_{inn}", f"a_{inn}"]]
        pick3 = p3.idxmax(axis=1).str[0].map({"h": "home", "d": "draw", "a": "away"})
        acc3 = (pick3 == res5).mean()
        # ③ F5 토탈 — **고정 라인**에서 오버 확률 vs 실제
        hit = []
        for ln in total_lines:
            po = t[f"po{ln}_{inn}"]
            hit.append(((po > 0.5) == (t["f5_total"] > ln)))
        acct = pd.concat(hit).mean()
        # ④ 대조군 — 같은 λ의 전체 경기 승패
        m9 = t["home_runs"] != t["away_runs"]
        acc9 = ((t.loc[m9, f"h9_{inn}"] > 0.5) ==
                (t.loc[m9, "home_runs"] > t.loc[m9, "away_runs"])).mean()
        brier = ((t.loc[m, f"h_{inn}"] - actual_home.astype(int)) ** 2).mean()
        print(f"  {lab:>10} {acc2:>14.4f} {acc3:>10.4f} {acct:>8.4f} "
              f"{acc9:>9.4f} {brier:>12.4f}")

    print()
    print(f"  λ5 합계 평균 {t[f'lam5_{innings[0]}'].mean():.2f} / "
          f"실제 F5 총득점 평균 {t['f5_total'].mean():.2f}")
    # F5 토탈 기준선 — 각 고정 라인에서 항상 오버/항상 언더 중 나은 쪽
    parts = [(t["f5_total"] > ln) for ln in total_lines]
    allov = pd.concat(parts)
    print(f"  F5 토탈 라인 {total_lines} · 기준선(항상 한쪽) "
          f"{max(allov.mean(), 1 - allov.mean()):.4f}  n={len(allov)}")
    for ln in total_lines:
        o = (t["f5_total"] > ln).mean()
        print(f"    {ln}: 실제 오버 {o:.4f} · 모델 평균 오버확률 "
              f"{t[f'po{ln}_{innings[0]}'].mean():.4f}")


if __name__ == "__main__":
    main()
