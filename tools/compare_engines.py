"""🔴🔴 **§2·§3 판정 — 바닥 점수 × λ 식을 묶어서 견준다**(지시서 2026-10-12).

```
PYTHONPATH=. python tools/compare_engines.py --league league:KL1 --fotmob 9080 \
    --seasons 2 --split 2026-01-01T00:00Z
```

> 판정: 셋 중 **로그 손실 최선** 하나를 바닥으로(**3단계 변환까지 묶어서** 비교).
> 적합은 시즌 A, 평가는 시즌 B — **그리고 반대**(교차).

🔴 한 후보 = (바닥 점수 `elo|elog|pi`) × (§3 λ 식 계수). 둘을 **따로** 적합한 뒤
   **같은 평가 구간**에서 승무패를 만들어 로그 손실을 센다.
🔴 승무패는 **스코어 격자 하나**에서 나온다(`probfloor.markets_of` · 계약 P2) —
   오버·핸디도 같은 격자다.
🔴 **E1** — 적합 구간과 평가 구간은 `--split` 으로 갈린다. `metrics.check_split`
   이 그것을 센다. 🔴 양쪽 방향(A→B · B→A)을 **둘 다** 낸다.
⚠️ 기준선은 **운영 현 구조**가 아니라 *"그 평가 구간의 `Elo만`(교차 적합 바닥)"*
   이다 — 운영 비교는 §10 승격 때 `judge_models.py` 가 한다.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

RATINGS = ("elo", "elog", "pi")


def _as_of(said: str) -> datetime:
    from run_stage8 import _as_of as _one
    return _one(said)


def _hit(hg: int, ag: int) -> int:
    return 0 if hg > ag else (1 if hg == ag else 2)


def fit_coef(rows: list[tuple]) -> tuple[dict, float]:
    """🔴 §3 계수를 그 구간에서 적합한다 — 식·우도는 `fit_probfloor` 하나다."""
    import numpy as np
    from scipy.optimize import minimize

    from fit_probfloor import nll
    got = minimize(nll, np.array([0.2, 0.3, 0.1, -0.05]), args=(rows,),
                   method="Nelder-Mead",
                   options={"maxiter": 20000, "xatol": 1e-7, "fatol": 1e-8})
    b0, b1, h, rho = (float(v) for v in got.x)
    return ({"b0": b0, "b1": b1, "b2": 0.0, "h_league": h, "rho": rho},
            float(got.fun) / max(1, len(rows)))


def rows_for(mod, params, games: list[dict], *, lo: datetime, hi: datetime,
             half_life: float = 365.0) -> list[tuple]:
    """🔴 `[lo, hi)` 구간의 `(diff, 홈골, 원정골, 가중)` — 표는 늘 **그 경기 전**."""
    out: list[tuple] = []
    seen: list[dict] = []
    decay = math.log(2.0) / max(1.0, float(half_life))
    for one in sorted(games, key=lambda g: str(g["utc"])):
        when = datetime.fromisoformat(str(one["utc"]).replace("Z", "+00:00"))
        if when >= hi:
            break
        if when >= lo and len(seen) >= 20:
            table = mod.rate(seen, params=params, as_of=when)
            out.append((float(mod.prob_input(one["home"], one["away"], table)),
                        int(one["hg"]), int(one["ag"]),
                        math.exp(-decay * (hi - when).days)))
        seen.append(one)
    return out


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--fotmob", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--split", required=True,
                    help="🔴 이 시각 앞이 A 구간, 뒤가 B 구간이다")
    args = ap.parse_args(argv[1:])
    split = _as_of(args.split)
    from app.core import metrics as _me
    from app.core import probfloor as _pf
    from app.core import ratings as _r
    from app.net import Net
    from fit_ratings import games_of
    net = Net(cache=True)
    games = await games_of(net, str(args.fotmob), seasons=int(args.seasons))
    first = min(datetime.fromisoformat(str(g["utc"]).replace("Z", "+00:00"))
                for g in games)
    last = max(datetime.fromisoformat(str(g["utc"]).replace("Z", "+00:00"))
               for g in games)
    print(f"# 🔴🔴 §2·§3 판정 — `{args.league}`")
    print()
    print(f"끝난 경기 **{len(games)}건** · {first:%Y-%m-%d} ~ {last:%Y-%m-%d}"
          f" · 가름 {split:%Y-%m-%d}")
    print()
    spans = (("A→B", (first, split), (split, last + timedelta(days=1))),
             ("B→A", (split, last + timedelta(days=1)), (first, split)))
    out_rows: list[dict] = []
    for way, (f_lo, f_hi), (e_lo, e_hi) in spans:
        # 🔴🔴 **E1** — 적합·평가 구간이 겹치면 예외다
        _me.check_split(fit={f"{f_lo:%Y-%m-%d}~{f_hi:%Y-%m-%d}"},
                        eval={f"{e_lo:%Y-%m-%d}~{e_hi:%Y-%m-%d}"})
        print(f"## {way} — 적합 {f_lo:%Y-%m-%d}~{f_hi:%Y-%m-%d} · "
              f"평가 {e_lo:%Y-%m-%d}~{e_hi:%Y-%m-%d}")
        print()
        print("| 후보 | 적합 n | 평가 n | **로그 손실** | RPS | 방향 적중 | "
              "b1 | ρ | h_league |")
        print("|---|---|---|---|---|---|---|---|---|")
        got_ll: dict[str, list[float]] = {}
        for name in RATINGS:
            mod = __import__(f"app.core.ratings.{name}", fromlist=["x"])
            p = _r.load_params(name, league=args.league, as_of=f_hi)
            fit_rows = rows_for(mod, p, games, lo=f_lo, hi=f_hi)
            if len(fit_rows) < 80:
                print(f"| {name} | {len(fit_rows)} | — | 표본 부족 | — | — "
                      f"| — | — | — |")
                continue
            coef, _nll = fit_coef(fit_rows)
            ev = rows_for(mod, p, games, lo=e_lo, hi=e_hi)
            lls, rpss, hits = [], [], 0
            for diff, hg, ag, _w in ev:
                lam, _why = _pf.lambdas(diff=diff, player_diff=0.0, coef=coef)
                grid = _pf.score_grid(lam_home=lam["home"],
                                      lam_away=lam["away"],
                                      rho=float(coef["rho"]))
                mk = _pf.markets_of(grid)
                probs = [mk["home"], mk["draw"], mk["away"]]
                hit = _hit(hg, ag)
                lls.append(_me.logloss(probs, hit))
                rpss.append(_me.rps(probs, hit))
                hits += 1 if _me.direction_hit(probs, hit) else 0
            if not lls:
                continue
            got_ll[name] = lls
            print(f"| **{name}**{' 🔴임시학습률' if p.provisional else ''} | "
                  f"{len(fit_rows)} | {len(ev)} | **{sum(lls) / len(lls):.4f}**"
                  f" | {sum(rpss) / len(rpss):.4f} | {hits}/{len(ev)}"
                  f"({hits / len(ev):.1%}) | {coef['b1']:+.3f} | "
                  f"{coef['rho']:+.3f} | {coef['h_league']:+.3f} |")
            out_rows.append({"way": way, "name": name, "ll": lls})
        print()
        if len(got_ll) >= 2:
            print("| 짝지은 차이(로그 손실) | 평균 | 95% 구간 | 판정 |")
            print("|---|---|---|---|")
            base = "elo"
            for name in sorted(got_ll):
                if name == base or base not in got_ll:
                    continue
                said = _me.paired(got_ll[name], got_ll[base])
                print(f"| {name} − {base} | {said['mean']:+.4f} | "
                      f"{said['lo']:+.4f}~{said['hi']:+.4f} | "
                      f"**{_me.verdict_of(said)}** |")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
