"""[백테스트] **p_claude 단독 성능** — 파이프라인에 예측력이 있는지 가르는 측정.

배경(§8-3 · §8-4):
  `p_final = 0.50*p_model + 0.50*p_claude`인데 **p_model은 기준선 이하로 확인됐다**
  (승패 51.5% vs 기준선 52.8%, 토탈은 균형 라인에서 +2%p·유의성 없음).
  판정의 절반이 잡음인 셈인데, **나머지 절반 p_claude는 한 번도 측정된 적이 없다.**

  이 측정이 기준선을 못 넘으면 파이프라인에 예측력이 없다는 뜻이고,
  넘으면 p_model 가중치를 내리면 된다. 그 갈림길을 여기서 정한다.

⚠️ **지식 누수 방지 — 이 백테스트의 생명줄**
  Claude는 과거 MLB 경기 결과를 학습했을 수 있다. 그러면 "예측"이 아니라 "기억"을
  측정하게 되고 수치가 통째로 무의미해진다. 두 겹으로 막는다:
    ① 기본 검증 구간을 **지식 컷오프 이후**로 둔다 (`--start`, 기본 2026-06-01).
    ② `--anonymize`로 팀명·날짜를 가린 대조군을 함께 돌린다. 실명 성적이 익명
       성적보다 뚜렷이 높으면 그 차이가 곧 누수량이다.
  두 값을 **반드시 함께 보고한다.** 실명 수치만 보고하지 마라.

⚠️ 한계 — 정직하게:
  - 리서치(결장·불펜·날씨·전문가 픽)는 과거 재현이 불가하다. p_claude는 λ와 **같은
    Statcast 입력만** 받는다. 즉 이것은 "같은 재료로 포아송과 Claude 중 누가 낫나"의
    측정이지, 운영 p_claude 전체의 측정이 아니다.
  - 배당·시장 확률도 넣지 않는다(운영 판정 철학과 동일 — judge는 배당을 안 본다).

비용: JUDGE_BATCH=4 → 경기 N건이면 호출 약 N/4회. `--dry-run`으로 먼저 확인하라.
"""

import argparse
import asyncio
import json
import pickle
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.backtest_lambda import build_research  # noqa: E402

# 익명화용 중립 라벨 — 실명 기억을 차단한다
ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def anonymize(games: list[dict]) -> list[dict]:
    """팀명·날짜를 중립 라벨로 치환. 지표는 그대로 둔다.

    Claude가 '기억'이 아니라 '주어진 숫자'로만 판단하게 만드는 대조군이다.
    """
    out = []
    for i, g in enumerate(games):
        h, a = f"팀-{ALPHA[(2*i) % 26]}{i}", f"팀-{ALPHA[(2*i+1) % 26]}{i}"
        gg = dict(g)
        gg["home"], gg["away"] = h, a
        gg["home_pitcher"] = f"{h} 선발"
        gg["away_pitcher"] = f"{a} 선발"
        gg["league"] = "리그"
        gg["starts_at"] = "2099-01-01T00:00:00+00:00"
        gg["starts_at_kst"] = "09:00"
        out.append(gg)
    return out


def build_games(pickle_path, start, end, limit, seed, min_games):
    """과거 슬레이트를 judge 페이로드 형태로 재현. 반환: (judge_games, 실제결과)."""
    import pandas as pd

    from app.config import get_settings
    from app.engine.scoring import cap_probability, mlb_lambdas, mlb_market_probs
    from app.models import features as F

    df = pickle.load(open(pickle_path, "rb"))
    d = F.prepare(df)
    games = F.game_frame(d)
    sm = F.starters(d)
    pg = F.pitcher_game_stats(d, sm)
    starter_map = {(int(r["game_pk"]), str(r["team"])): r["pitcher"]
                   for _i, r in sm.iterrows()}
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     barrel=("is_barrel", "sum"), hardhit=("is_hardhit", "sum"),
                     bip=("ls", "count"), k=("is_k", "sum"), bb=("is_bb", "sum"),
                     pa=("is_pa", "sum")))
    parks = F.rolling_park_factors(games, min_games=min_games)
    s = get_settings()

    lo, hi = pd.Timestamp(start), pd.Timestamp(end) if end else games["date"].max()
    pool = []
    for _, g in games.iterrows():
        if not (lo <= g["date"] <= hi):
            continue
        if g["home_runs"] == g["away_runs"]:
            continue                      # 무승부(서스펜디드) 제외
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
        lam = mlb_lambdas({"home": g["home"], "away": g["away"]}, res, s)
        if not lam.usable:
            continue
        pr = mlb_market_probs(lam.home, lam.away, None, s.score_dispersion, settings=s)
        p_model, _ = cap_probability(pr["h2h"]["home"], "mlb", s)
        pool.append({
            "jg": {
                "game_id": int(g["game_pk"]),
                "sport": "mlb",
                "home": g["home"], "away": g["away"], "league": "MLB",
                "home_pitcher": f"{g['home']} 선발", "away_pitcher": f"{g['away']} 선발",
                "starts_at": g["date"].isoformat(),
                "starts_at_kst": "09:00",
                "status": "scheduled",
                "research": res,
                "research_status": "refreshed",
                "lineup_status": "confirmed",
                "p_model": round(p_model, 4),
                "model_valid": True,
                # 배당·전문가 픽은 과거 재현 불가 — 넣지 않는다(판정 철학과도 일치)
                "p_market": None, "market_probs": None, "best_odds": None,
                "expert_picks": [], "consensus": {},
                "stats": {
                    "home_offense_xwoba_30d": res.get("home_offense", {}).get("xwoba_30d"),
                    "away_offense_xwoba_30d": res.get("away_offense", {}).get("xwoba_30d"),
                    "home_starter_xwoba_allowed": res.get("home_pitcher", {}).get("xwoba_allowed"),
                    "away_starter_xwoba_allowed": res.get("away_pitcher", {}).get("xwoba_allowed"),
                    "park_factor": res.get("park_factor"),
                },
            },
            "home_won": int(g["home_runs"] > g["away_runs"]),
            "date": str(g["date"].date()),
        })

    if limit and len(pool) > limit:
        random.Random(seed).shuffle(pool)
        pool = pool[:limit]
    pool.sort(key=lambda r: r["date"])
    return pool


async def run_judge(jgs: list[dict], batch: int) -> dict:
    """judge를 배치로 돌려 game_id → p_claude 를 모은다. 실패 배치는 건너뛴다."""
    from app.engine.judge import Judge

    j = Judge(mock=False)
    out: dict[int, float] = {}
    total = (len(jgs) + batch - 1) // batch
    for i in range(0, len(jgs), batch):
        chunk = jgs[i:i + batch]
        n = i // batch + 1
        try:
            v = await j.judge({"date": "backtest", "sport": "mlb",
                               "games": chunk, "breaking_news": []})
            got = 0
            for row in v.get("games") or []:
                p = row.get("p_claude")
                if p is None:
                    continue
                out[int(row["game_id"])] = float(p)
                got += 1
            print(f"  배치 {n}/{total}: {got}/{len(chunk)}건 판정", flush=True)
        except Exception as exc:                      # noqa: BLE001
            print(f"  배치 {n}/{total}: 실패 — {type(exc).__name__}: {exc}", flush=True)
    return out


def report(label, rows):
    """정확도·Brier·캘리브레이션. 기준선은 **다수클래스**(모델과 같은 자유도)."""
    import pandas as pd

    t = pd.DataFrame(rows)
    n = len(t)
    if not n:
        print(f"\n[{label}] 판정된 경기가 없다"); return None
    base = max(t["home_won"].mean(), 1 - t["home_won"].mean())
    print(f"\n=== [{label}] n={n} · 기준선(다수클래스) {base:.4f} ===")
    print(f"  {'축':>12} {'정확도':>8} {'vs기준':>8} {'Brier':>8} {'평균예측':>9}")
    for col, name in (("p_model", "p_model"), ("p_claude", "p_claude"),
                      ("p_final", "p_final(50:50)")):
        acc = ((t[col] > 0.5).astype(int) == t["home_won"]).mean()
        br = ((t[col] - t["home_won"]) ** 2).mean()
        print(f"  {name:>12} {acc:>8.4f} {acc-base:>+8.4f} {br:>8.4f} {t[col].mean():>9.4f}")

    print("\n  혼합 가중치 스윕 (w = p_claude 비중)")
    print(f"    {'w':>5} {'정확도':>8} {'vs기준':>8} {'Brier':>8}")
    best = None
    for w in [x / 10 for x in range(11)]:
        p = (1 - w) * t["p_model"] + w * t["p_claude"]
        acc = ((p > 0.5).astype(int) == t["home_won"]).mean()
        br = ((p - t["home_won"]) ** 2).mean()
        mark = ""
        if best is None or acc > best[1]:
            best, mark = (w, acc), ""
        print(f"    {w:>5.1f} {acc:>8.4f} {acc-base:>+8.4f} {br:>8.4f}{mark}")
    print(f"    → 최고 w={best[0]:.1f} 정확도 {best[1]:.4f} (기준선 {base:.4f})")

    print("\n  p_claude 캘리브레이션")
    for lo, hi in [(0, .45), (.45, .50), (.50, .55), (.55, .60), (.60, 1.01)]:
        b = t[(t["p_claude"] >= lo) & (t["p_claude"] < hi)]
        if len(b) < 8:
            continue
        print(f"    {lo:.2f}~{hi:.2f} n={len(b):>4} 예측 {b['p_claude'].mean():.3f} "
              f"실제 {b['home_won'].mean():.3f} gap {b['home_won'].mean()-b['p_claude'].mean():+.3f}")

    hi = t[t["p_claude"] >= 0.58]
    print(f"\n  추천 임계(58%↑) {len(hi)}경기 ({len(hi)/n:.1%})"
          + (f" · 적중 {(hi['home_won']==1).mean():.1%}" if len(hi) else ""))
    return {"n": n, "base": base,
            "acc_claude": float(((t["p_claude"] > 0.5).astype(int) == t["home_won"]).mean())}


async def amain():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", required=True)
    ap.add_argument("--start", default="2026-06-01",
                    help="검증 시작일. 기본값은 **지식 컷오프 이후** — 누수 방지의 핵심")
    ap.add_argument("--end", default=None)
    ap.add_argument("--limit", type=int, default=120, help="판정할 경기 수 (비용)")
    ap.add_argument("--seed", type=int, default=20260826)
    ap.add_argument("--min-games", type=int, default=30)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--anonymize", action="store_true",
                    help="팀명·날짜를 가린 **대조군**도 함께 돌린다(누수 측정)")
    ap.add_argument("--dry-run", action="store_true", help="호출 없이 표본·비용만 출력")
    ap.add_argument("--save", default=None, help="원자료 JSON 저장 경로")
    args = ap.parse_args()

    print(f"원본 로드: {args.pickle}")
    pool = build_games(args.pickle, args.start, args.end, args.limit,
                       args.seed, args.min_games)
    if not pool:
        print("검증 가능한 경기가 없다"); return
    calls = (len(pool) + args.batch - 1) // args.batch
    runs = 2 if args.anonymize else 1
    print(f"표본 {len(pool)}경기 ({pool[0]['date']} ~ {pool[-1]['date']})")
    print(f"judge 호출 예상 {calls}회 × {runs}회차 = {calls*runs}회 "
          f"(배치 {args.batch})")
    print(f"홈 실제 승률 {sum(r['home_won'] for r in pool)/len(pool):.4f}")
    if args.dry_run:
        print("\n--dry-run — 호출하지 않고 종료"); return

    results = {}
    for label, jgs in [("실명", [r["jg"] for r in pool])] + (
            [("익명 대조군", anonymize([r["jg"] for r in pool]))] if args.anonymize else []):
        print(f"\n▶ {label} 판정 시작 ({calls}배치)")
        pc = await run_judge(jgs, args.batch)
        rows = [{"date": r["date"], "home_won": r["home_won"],
                 "p_model": r["jg"]["p_model"],
                 "p_claude": pc[r["jg"]["game_id"]],
                 "p_final": 0.5 * r["jg"]["p_model"] + 0.5 * pc[r["jg"]["game_id"]]}
                for r in pool if r["jg"]["game_id"] in pc]
        results[label] = (report(label, rows), rows)

    if args.anonymize and all(v[0] for v in results.values()):
        a = results["실명"][0]["acc_claude"]
        b = results["익명 대조군"][0]["acc_claude"]
        print(f"\n=== 누수 점검 ===")
        print(f"  실명 {a:.4f} · 익명 {b:.4f} · 차이 {a-b:+.4f}")
        print("  차이가 크면 그만큼은 예측이 아니라 **기억**이다. "
              "실명 수치를 단독으로 인용하지 마라.")

    if args.save:
        Path(args.save).write_text(json.dumps(
            {k: v[1] for k, v in results.items()}, ensure_ascii=False, indent=1))
        print(f"\n원자료 저장: {args.save}")


if __name__ == "__main__":
    asyncio.run(amain())
