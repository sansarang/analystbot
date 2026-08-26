"""[검증] 타선 지표 후보 비교 — 어느 것이 승패·득점을 예측하는가.

현행 팀 30일 xwOBA는 실측 상관 +0.018로 사실상 무력했다(§8-3).
대안을 같은 누수 방지 조건(그 경기 이전 30일)에서 만들어 비교한다.
"""
import argparse, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WINDOW = 30


def build(pkl, start):
    import pandas as pd
    from app.models import features as F

    df = pickle.load(open(pkl, "rb"))
    d = F.prepare(df)
    # 실제 wOBA 재료 — 삼진·볼넷 포함
    d["wv"] = pd.to_numeric(df.loc[d.index, "woba_value"], errors="coerce")
    d["wd"] = pd.to_numeric(df.loc[d.index, "woba_denom"], errors="coerce")
    games = F.game_frame(d)

    # 팀-일자 집계: xwOBA / 실제 wOBA / 득점
    td = (d.groupby(["bat_team", "game_date"], as_index=False)
          .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
               wv_sum=("wv", "sum"), wd_sum=("wd", "sum")))
    runs = pd.concat([
        games[["date", "home", "home_runs"]].rename(
            columns={"date": "game_date", "home": "bat_team", "home_runs": "runs"}),
        games[["date", "away", "away_runs"]].rename(
            columns={"date": "game_date", "away": "bat_team", "away_runs": "runs"}),
    ])
    rd = runs.groupby(["bat_team", "game_date"], as_index=False).agg(
        runs=("runs", "sum"), gp=("runs", "size"))
    td = td.merge(rd, on=["bat_team", "game_date"], how="outer").fillna(0)

    st = pd.Timestamp(start)
    rows = []
    for _, g in games.iterrows():
        if g["date"] < st:
            continue
        rec = {"home": g["home"], "away": g["away"],
               "hr": g["home_runs"], "ar": g["away_runs"]}
        ok = True
        for side, team in (("home", g["home"]), ("away", g["away"])):
            lo = g["date"] - pd.Timedelta(days=WINDOW)
            sub = td[(td.bat_team == team) & (td.game_date < g["date"]) & (td.game_date >= lo)]
            if sub["xw_n"].sum() < 300 or sub["gp"].sum() < 8:
                ok = False
                break
            rec[f"{side}_xwoba"] = sub["xw_sum"].sum() / sub["xw_n"].sum()
            rec[f"{side}_woba"] = (sub["wv_sum"].sum() / sub["wd_sum"].sum()
                                   if sub["wd_sum"].sum() else None)
            rec[f"{side}_rpg"] = sub["runs"].sum() / sub["gp"].sum()
        if ok and all(rec.get(f"{s}_woba") for s in ("home", "away")):
            rows.append(rec)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-05-01")
    args = ap.parse_args()
    import pandas as pd

    t = build(args.pickle, args.start)
    print(f"표본 {len(t)}경기\n")

    # ── 1) 팀 지표 ↔ 그 팀 득점 상관 ─────────────────────────
    long = pd.concat([
        t[["home_xwoba", "home_woba", "home_rpg", "hr"]].rename(
            columns=lambda c: c.replace("home_", "").replace("hr", "runs")),
        t[["away_xwoba", "away_woba", "away_rpg", "ar"]].rename(
            columns=lambda c: c.replace("away_", "").replace("ar", "runs")),
    ])
    print("=== 지표 ↔ 실제 득점 상관 (높을수록 좋다) ===")
    for col, label in (("xwoba", "팀 30일 xwOBA (현행)"),
                       ("woba", "팀 30일 실제 wOBA"),
                       ("rpg", "팀 30일 득점/경기")):
        r = long["runs"].corr(long[col])
        q = pd.qcut(long[col], 4, labels=False, duplicates="drop")
        means = long.groupby(q, observed=True)["runs"].mean().round(2).tolist()
        mono = "단조" if means == sorted(means) else "비단조"
        print(f"  {label:<24} r={r:+.4f}   사분위 {means}  ({mono})")

    # ── 2) 지표 차이 ↔ 승패 상관 ─────────────────────────────
    print()
    print("=== 홈-원정 지표 차이 ↔ 홈 승리 상관 (승패 예측력) ===")
    d2 = t[t.hr != t.ar].copy()
    d2["won"] = (d2.hr > d2.ar).astype(int)
    for col, label in (("xwoba", "xwOBA 차"), ("woba", "실제 wOBA 차"), ("rpg", "득점/경기 차")):
        diff = d2[f"home_{col}"] - d2[f"away_{col}"]
        r = d2["won"].corr(diff)
        hi = d2[diff > diff.quantile(.75)]["won"].mean()
        lo = d2[diff < diff.quantile(.25)]["won"].mean()
        print(f"  {label:<16} r={r:+.4f}   상위25% 홈승률 {hi:.3f} / 하위25% {lo:.3f}"
              f"   격차 {hi-lo:+.3f}")
    print(f"\n  참고: 전체 홈 승률 {d2['won'].mean():.4f} (n={len(d2)})")


if __name__ == "__main__":
    main()
