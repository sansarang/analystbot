"""절제 실험 — 어느 요소가 승패 예측을 망치는가."""
import pickle, sys
sys.path.insert(0, '.')
import pandas as pd
from app.config import get_settings
from app.engine.scoring import mlb_lambdas, mlb_market_probs, cap_probability
from app.models import features as F

df = pickle.load(open('/private/tmp/claude-501/-Users-youngjinjung-Desktop-analystbot/e226050e-524c-4005-bed1-14840ce6af7d/scratchpad/statcast_raw.pkl','rb'))
d = F.prepare(df)
games = F.game_frame(d)
sm = F.starters(d)
pg = F.pitcher_game_stats(d, sm)
starter_map = {(int(r["game_pk"]), str(r["team"])): r["pitcher"] for _i, r in sm.iterrows()}
team_day = (d.groupby(["bat_team","game_date"], as_index=False)
            .agg(xw_sum=("xwoba","sum"), xw_n=("xwoba","count"), barrel=("is_barrel","sum"),
                 hardhit=("is_hardhit","sum"), bip=("ls","count"), k=("is_k","sum"),
                 bb=("is_bb","sum"), pa=("is_pa","sum")))
parks = F.rolling_park_factors(games, min_games=30)
s = get_settings()
start = pd.Timestamp('2026-05-01')

recs = []
for _, g in games.iterrows():
    if g["date"] < start: continue
    if g["home_runs"] == g["away_runs"]: continue
    off, sp = {}, {}
    ok = True
    for side, team, opp in (("home", g["home"], g["away"]), ("away", g["away"], g["home"])):
        o = F.team_offense_prior(team_day, team, g["date"])
        pid = starter_map.get((int(g["game_pk"]), str(opp)))
        p = F.pitcher_prior(pg, pid, g["date"]) if pid else None
        if not o: ok = False
        off[side], sp[side] = o, p
    if not ok: continue
    recs.append({"g": g, "off": off, "sp": sp,
                 "park": parks.get((g["game_pk"], g["home"])),
                 "won": int(g["home_runs"] > g["away_runs"])})

print(f"표본 {len(recs)}경기\n")

def run(name, use_off, use_sp, use_park):
    rows = []
    for r in recs:
        g = r["g"]
        res = {}
        for side in ("home","away"):
            if use_off and r["off"][side]:
                res[f"{side}_offense"] = {"xwoba_30d": r["off"][side]["off_xwoba"]}
            if use_sp and r["sp"][side] and r["sp"][side].get("sp_xwoba_allowed") is not None:
                res[f"{side}_pitcher"] = {"xwoba_allowed": r["sp"][side]["sp_xwoba_allowed"]}
        if use_park and r["park"] is not None:
            res["park_factor"] = r["park"]
        lam = mlb_lambdas({"home": g["home"], "away": g["away"]}, res, s)
        if not lam.usable: continue
        pm = mlb_market_probs(lam.home, lam.away, None, s.score_dispersion, settings=s)
        ph, _ = cap_probability(pm["h2h"]["home"], "mlb", s)
        rows.append((ph, r["won"]))
    if not rows:
        print(f"  {name:<28} 산출 불가"); return
    t = pd.DataFrame(rows, columns=["p","won"])
    acc = ((t.p > .5).astype(int) == t.won).mean()
    brier = ((t.p - t.won)**2).mean()
    hi = t[t.p >= 0.58]
    print(f"  {name:<28} n={len(t):>4}  정확도 {acc:.4f}  Brier {brier:.4f}"
          + (f"  · 58%↑ {len(hi)}건 적중 {(hi.won==1).mean():.1%}" if len(hi) >= 20 else ""))

base = pd.DataFrame([(r["won"],) for r in recs], columns=["won"])
print(f"  {'[기준] 항상 홈팀':<28} n={len(base):>4}  정확도 {base.won.mean():.4f}  Brier {(0.5-base.won).pow(2).mean():.4f}")
print(f"  {'[기준] 항상 50%':<28}              정확도 0.5000  Brier 0.2500")
print()
run("현행 (타선+선발+구장)", True, True, True)
run("타선 제거 (선발+구장)", False, True, True)
run("선발 제거 (타선+구장)", True, False, True)
run("구장 제거 (타선+선발)", True, True, False)
run("선발만", False, True, False)
