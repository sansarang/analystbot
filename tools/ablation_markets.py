"""[검증] 각 λ 입력이 **마켓별로** 유효한지 측정한다.

§8-1에서 파크팩터가 "승패엔 무의미, 토탈엔 유효"로 판정된 전례가 있다.
같은 방식으로 모든 입력을 승패·토탈 두 축에서 각각 재고, 음수 기여는
해당 마켓에서 뺀다. 추측이 아니라 절제 실험으로 정한다(DISCIPLINE 5-2).
"""
import argparse, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TOTAL_LINES = (7.5, 8.5, 9.5)


def load(pkl, start):
    import pandas as pd
    from app.models import features as F
    df = pickle.load(open(pkl, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    sm = F.starters(d)
    pg = F.pitcher_game_stats(d, sm)
    smap = {(int(r["game_pk"]), str(r["team"])): r["pitcher"] for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     barrel=("is_barrel", "sum"), hardhit=("is_hardhit", "sum"),
                     bip=("ls", "count"), k=("is_k", "sum"), bb=("is_bb", "sum"),
                     pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=30)
    st = pd.Timestamp(start)
    recs = []
    for _, g in games.iterrows():
        if g["date"] < st:
            continue
        off, sp, ok = {}, {}, True
        for side, team, opp in (("home", g["home"], g["away"]), ("away", g["away"], g["home"])):
            o = F.team_offense_prior(team_day, team, g["date"])
            pid = smap.get((int(g["game_pk"]), str(team)))   # 자기 팀 선발
            p = F.pitcher_prior(pg, pid, g["date"]) if pid else None
            if not o or not p or p.get("sp_xwoba_allowed") is None:
                ok = False
            off[side], sp[side] = o, p
        if ok:
            recs.append({"home": g["home"], "away": g["away"], "off": off, "sp": sp,
                         "park": parks.get((g["game_pk"], g["home"])),
                         "hr": g["home_runs"], "ar": g["away_runs"]})
    return recs


def evaluate(recs, use_off, use_sp, use_park, s, sym_off=False):
    """sym_off=True면 양 팀 타선 지표를 **평균 내 둘 다에 적용**한다.

    근거(2026-08-26 실측): 타선 지표는 승패에 해롭고(-0.83%p) 토탈에 유익하다(+0.30%p).
    즉 두 팀의 **차이**는 잘못 잡고 **합계**는 맞게 잡는다. 대칭 적용은 차이만 죽이고
    합계를 살리는 시도다 — λ 하나로 전 마켓을 내는 원칙도 유지된다.
    """
    import pandas as pd
    from app.engine.scoring import cap_probability, mlb_lambdas, mlb_market_probs
    h2h, tot = [], []
    for r in recs:
        res = {}
        avg_off = (r["off"]["home"]["off_xwoba"] + r["off"]["away"]["off_xwoba"]) / 2
        for side in ("home", "away"):
            if use_off:
                res[f"{side}_offense"] = {
                    "xwoba_30d": avg_off if sym_off else r["off"][side]["off_xwoba"]}
            if use_sp:
                res[f"{side}_pitcher"] = {"xwoba_allowed": r["sp"][side]["sp_xwoba_allowed"]}
        if use_park and r["park"] is not None:
            res["park_factor"] = r["park"]
        lam = mlb_lambdas({"home": r["home"], "away": r["away"]}, res, s)
        if not lam.usable:
            continue
        lines = {"totals": list(TOTAL_LINES)}
        pm = mlb_market_probs(lam.home, lam.away, lines, s.score_dispersion, settings=s)
        if r["hr"] != r["ar"]:
            ph, _ = cap_probability(pm["h2h"]["home"], "mlb", s)
            h2h.append((ph, int(r["hr"] > r["ar"])))
        total = r["hr"] + r["ar"]
        for ln in TOTAL_LINES:
            p_over = (pm.get("totals") or {}).get(ln, {}).get("Over")
            if p_over is None:
                continue
            tot.append((ln, p_over, int(total > ln)))
    return pd.DataFrame(h2h, columns=["p", "y"]), pd.DataFrame(tot, columns=["line", "p", "y"])


def score(t, by=None):
    """정확도와 기준선. `by`가 있으면 그 컬럼으로 **층화**한다.

    ⚠️ 실사고(2026-08-26, §8-4): 토탈 라인 3개를 합쳐 놓고 기준선만 전역 한쪽으로
       고정해 **없는 엣지 +4.51%p를 만들어냈다.** 모델은 라인마다 다른 방향을 고를
       수 있는데 기준선은 못 고르게 한 불공정 비교였다. 쏠린 라인(9.5는 언더 60.6%)의
       기준선 우위가 통째로 모델 성과로 계상됐다.
       → 기준선은 **모델과 같은 자유도**로 계산한다. 층화 지표는 층별로 보고한다.
    """
    if t.empty:
        return None
    acc = ((t.p > .5).astype(int) == t.y).mean()
    brier = ((t.p - t.y) ** 2).mean()
    if by is None:
        base_acc = max(t.y.mean(), 1 - t.y.mean())
        base_brier = t.y.mean() * (1 - t.y.mean())
    else:
        # 층별 다수클래스를 표본 수로 가중 평균 — 모델과 같은 선택 자유도
        g = t.groupby(by)["y"]
        w = g.size()
        base_acc = float((g.mean().combine(1 - g.mean(), max) * w).sum() / w.sum())
        base_brier = float(((g.mean() * (1 - g.mean())) * w).sum() / w.sum())
    return acc, brier, base_acc, base_brier, len(t)


def per_line(t):
    """라인별 분해 — 풀링 값 단독 보고 금지(§8-4)."""
    out = []
    for ln, b in t.groupby("line"):
        base = max(b.y.mean(), 1 - b.y.mean())
        acc = ((b.p > .5).astype(int) == b.y).mean()
        out.append((ln, len(b), b.y.mean(), b.p.mean(), base, acc, acc - base))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-05-01")
    args = ap.parse_args()
    from app.config import get_settings
    s = get_settings()
    recs = load(args.pickle, args.start)
    print(f"표본 {len(recs)}경기 (양 팀 타선·선발 지표 보유)\n")

    variants = [
        ("전체 (타선+선발+구장)", True, True, True, False),
        ("선발 제거", True, False, True, False),
        ("타선 제거", False, True, True, False),
        ("구장 제거", True, True, False, False),
        ("타선만", True, False, False, False),
        ("★ 타선 대칭적용", True, True, True, True),
        ("★ 타선 대칭 + 구장 제거", True, True, False, True),
    ]
    print(f"{'구성':<22} {'승패 정확도':>11} {'vs기준':>8} {'토탈 정확도':>11} {'vs기준':>8}")
    print("-" * 66)
    for name, uo, up, upk, sym in variants:
        h, t = evaluate(recs, uo, up, upk, s, sym_off=sym)
        hs, ts = score(h), score(t, by="line")
        if hs is None or ts is None:
            print(f"{name:<22} 산출 불가"); continue
        print(f"{name:<22} {hs[0]:>10.4f} {hs[0]-hs[2]:>+8.4f} "
              f"{ts[0]:>10.4f} {ts[0]-ts[2]:>+8.4f}")
    h, t = evaluate(recs, True, True, True, s)
    hs, ts = score(h), score(t, by="line")
    print()
    print(f"  승패 기준선(다수클래스) {hs[2]:.4f} · n={hs[4]}")
    print(f"  토탈 기준선(**라인별 층화** 다수클래스) {ts[2]:.4f} · n={ts[4]}")
    print()
    print("  토탈 라인별 분해 (전체 구성) — 풀링 값만 보면 안 된다(§8-4)")
    print(f"    {'라인':>6} {'n':>6} {'실제오버':>9} {'모델오버':>9} "
          f"{'기준선':>8} {'모델':>8} {'차이':>8}")
    for ln, n, ay, ap_, base, acc, diff in per_line(t):
        print(f"    {ln:>6} {n:>6} {ay:>9.4f} {ap_:>9.4f} "
              f"{base:>8.4f} {acc:>8.4f} {diff:>+8.4f}")


if __name__ == "__main__":
    main()
