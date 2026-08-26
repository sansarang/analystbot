"""[백테스트] **운영 λ**(`mlb_lambdas`)를 과거 경기로 검증한다.

지금까지 검증된 것은 학습 GLM(§8-1)뿐이고, 실제 리포트에 쓰이는 휴리스틱 λ는
한 번도 채점된 적이 없다. 오늘 하루에만 λ 요소를 7개로 늘리고 리그평균 상수를
고쳤는데, 그것이 적중률을 올렸는지 내렸는지 알 방법이 없었다.

⚠️ 누수 방지: 각 경기의 피처는 **그 경기 이전** 데이터로만 만든다.
   features.py의 team_offense_prior / pitcher_prior / rolling_park_factors가
   이미 그 계약을 지킨다(§8-1 파크팩터 누수 사고의 산물).

⚠️ 한계 — 정직하게:
   - Perplexity 리서치는 과거 재현이 불가하다 → 결장·불펜 과소모·날씨 없이 돈다.
     즉 이 백테스트는 **λ의 Statcast 축만** 검증한다.
   - 배당 이력이 27경기뿐이라 수익률·EV는 계산하지 않는다. 확률 품질만 본다.
"""

import argparse
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def build_research(row, off_prior, sp_prior, park):
    """운영 파이프라인이 만드는 research 페이로드를 과거 시점으로 재현.

    ⚠️ 키 계약(2026-08-26 실사고): `{side}_pitcher`는 **그 side 팀의 선발**이다.
       `mlb_lambdas`가 `lam[side] *= _suppression(pit[opp])`로 쓰므로,
       상대 선발을 여기 넣으면 부호가 뒤집힌다.
    """
    res = {}
    for side in ("home", "away"):
        o = off_prior.get(side)
        if o and o.get("off_xwoba") is not None:
            res[f"{side}_offense"] = {"xwoba_30d": round(float(o["off_xwoba"]), 4)}
        p = sp_prior.get(side)
        if p and p.get("sp_xwoba_allowed") is not None:
            res[f"{side}_pitcher"] = {"xwoba_allowed": round(float(p["sp_xwoba_allowed"]), 4)}
    if park is not None:
        res["park_factor"] = round(float(park), 4)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True, help="Statcast 원본 pickle")
    ap.add_argument("--start", default="2026-05-01", help="검증 시작일(이전은 사전지표용)")
    ap.add_argument("--min-games", type=int, default=30)
    args = ap.parse_args()

    import pandas as pd

    from app.config import get_settings
    from app.engine.scoring import cap_probability, mlb_lambdas, mlb_market_probs
    from app.models import features as F

    print(f"원본 로드: {args.pickle}")
    df = pickle.load(open(args.pickle, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    sm = F.starters(d)                       # DataFrame — pitcher_game_stats가 요구
    pg = F.pitcher_game_stats(d, sm)
    # (game_pk, 팀) → 선발 id 조회용 dict. build_dataset과 같은 형태다.
    starter_map = {(int(r["game_pk"]), str(r["team"])): r["pitcher"]
                   for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     barrel=("is_barrel", "sum"), hardhit=("is_hardhit", "sum"),
                     bip=("ls", "count"), k=("is_k", "sum"), bb=("is_bb", "sum"),
                     pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=args.min_games)
    print(f"경기 {len(games)}건 · 투수-경기 {len(pg)}건 · 파크팩터 {len(parks)}개")

    s = get_settings()
    start = pd.Timestamp(args.start)
    rows = []
    for _, g in games.iterrows():
        if g["date"] < start:
            continue
        jg = {"home": g["home"], "away": g["away"]}
        off = {}
        sp = {}
        ok = True
        for side, team in (("home", g["home"]), ("away", g["away"])):
            off[side] = F.team_offense_prior(team_day, team, g["date"]) or {}
            # ⚠️ 그 팀의 **자기 선발**을 넣는다. 운영 정의가 그렇다
            #    (collectors/mlb.py: home_pitcher = 홈팀 probablePitcher).
            #    opp의 선발을 넣으면 mlb_lambdas가 pit[opp]를 쓰면서 각 팀 타선을
            #    **자기 팀 선발**로 억제하게 된다 — 부호가 뒤집힌다.
            pid = starter_map.get((int(g["game_pk"]), str(team)))
            sp[side] = (F.pitcher_prior(pg, pid, g["date"]) or {}) if pid else {}
            if not off[side].get("off_xwoba"):
                ok = False
        if not ok:
            continue
        res = build_research(g, off, sp, parks.get((g["game_pk"], g["home"])))
        lam = mlb_lambdas(jg, res, s)
        if not lam.usable:
            continue
        probs = mlb_market_probs(lam.home, lam.away, None, s.score_dispersion, settings=s)
        p_home, _ = cap_probability(probs["h2h"]["home"], "mlb", s)
        rows.append({
            "date": g["date"], "p_home": p_home,
            "home_won": int(g["home_runs"] > g["away_runs"]),
            "tie": int(g["home_runs"] == g["away_runs"]),
            "lam_sum": lam.home + lam.away,
            "total": g["home_runs"] + g["away_runs"],
        })

    if not rows:
        print("검증 가능한 경기가 없다"); return
    t = pd.DataFrame(rows)
    t = t[t["tie"] == 0]      # 무승부(서스펜디드 등) 제외
    n = len(t)
    pred = (t["p_home"] > 0.5).astype(int)
    acc = (pred == t["home_won"]).mean()
    brier = ((t["p_home"] - t["home_won"]) ** 2).mean()

    print()
    print(f"=== 운영 λ 백테스트 ({args.start} 이후, {n}경기) ===")
    print(f"  정확도  {acc:.4f}   (기준선 0.5000)")
    print(f"  Brier   {brier:.4f}   (기준선 0.2500)")
    print(f"  홈 실제 승률 {t['home_won'].mean():.4f} / 모델 평균 예측 {t['p_home'].mean():.4f}")
    print(f"  λ 합계 평균 {t['lam_sum'].mean():.2f} / 실제 총득점 평균 {t['total'].mean():.2f}")
    print()
    print("  캘리브레이션")
    bins = [(0.0, .45), (.45, .50), (.50, .55), (.55, .60), (.60, 1.0)]
    for lo, hi in bins:
        b = t[(t["p_home"] >= lo) & (t["p_home"] < hi)]
        if len(b) < 10:
            continue
        print(f"    {lo:.2f}~{hi:.2f}  n={len(b):>4}  예측 {b['p_home'].mean():.3f} "
              f"실제 {b['home_won'].mean():.3f}  gap {b['home_won'].mean()-b['p_home'].mean():+.3f}")
    hi = t[t["p_home"] >= 0.58]
    print()
    print(f"  추천 임계(58%) 이상: {len(hi)}경기 ({len(hi)/n:.1%})"
          + (f" · 적중률 {(hi['home_won']==1).mean():.1%}" if len(hi) else ""))


if __name__ == "__main__":
    main()
