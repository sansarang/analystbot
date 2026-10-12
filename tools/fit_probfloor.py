"""🔴🔴 **§3 λ 식 적합(포아송 최대우도)** — 지시서 2026-10-12(엔진 교체) §3.

```
PYTHONPATH=. python tools/fit_probfloor.py --league league:KL1 --fotmob 9080 \
    --rating pi --as-of 2026-07-01T00:00Z --seasons 2 --write
```

> `b0`·`b1`·`b2`·`h_league`·`ρ` **동시 적합**(시간 감쇠 가중 · §5), 판 저장
> `data/probfloor/<league>/<as_of>.yaml`.
> `h_league` 는 기존 홈 이점 실측 판과 **비교 기록**(따로 곱하지 않는다 —
> 이중 계산 금지).

🔴 목적함수는 **골 수의 포아송 로그우도**다(승무패가 아니다) — 그래야 같은 λ 가
   승무패·오버·핸디·BTTS 를 **한 격자**로 낸다(계약 P2).
🔴 Dixon-Coles ρ 는 같은 적합 안에서 **함께** 움직인다 — 네 칸(0-0·1-0·0-1·1-1)의
   우도에만 `τ` 가 곱해진다.
🔴 **E1** — `--as-of` **이전** 경기로만 적합한다. 그 뒤는 평가용이라 보지 않는다.
⚠️ `b2`(선수 차)는 **§4 전까지 0 으로 고정**이다 — 지시가 그렇게 정했다.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _as_of(said: str) -> datetime:
    from run_stage8 import _as_of as _one
    return _one(said)


def nll(params: list[float], rows: list[tuple]) -> float:
    """🔴 음의 로그우도 — `rows` 는 `(diff, 홈골, 원정골, 가중)`.

    🔴 λ 식은 `app/core/probfloor.lambdas` **하나다**(사본 금지).
    🔴 ρ 는 낮은 스코어 네 칸의 `τ` 로만 들어간다(Dixon-Coles).
    """
    from app.core import probfloor as pf
    b0, b1, h, rho = params
    coef = {"b0": b0, "b1": b1, "b2": 0.0, "h_league": h}
    out = 0.0
    for diff, hg, ag, w in rows:
        lam, _why = pf.lambdas(diff=diff, player_diff=0.0, coef=coef)
        lh, la = lam["home"], lam["away"]
        ll = (-lh + hg * math.log(lh) - math.lgamma(hg + 1)
              - la + ag * math.log(la) - math.lgamma(ag + 1))
        if (hg, ag) == (0, 0):
            tau = 1.0 - lh * la * rho
        elif (hg, ag) == (0, 1):
            tau = 1.0 + lh * rho
        elif (hg, ag) == (1, 0):
            tau = 1.0 + la * rho
        elif (hg, ag) == (1, 1):
            tau = 1.0 - rho
        else:
            tau = 1.0
        ll += math.log(max(1e-9, tau))
        out -= float(w) * ll
    return out


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True)
    ap.add_argument("--fotmob", required=True)
    ap.add_argument("--rating", default="pi")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--seasons", type=int, default=2)
    ap.add_argument("--half-life", type=float, default=365.0,
                    help="🔴 시간 감쇠 반감기(일) · §5 에서 적합한다")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])
    as_of = _as_of(args.as_of)
    import numpy as np
    from scipy.optimize import minimize

    from app.core import ratings as _r
    from app.net import Net
    from fit_ratings import games_of
    mod = __import__(f"app.core.ratings.{args.rating}", fromlist=["x"])
    net = Net(cache=True)
    games = await games_of(net, str(args.fotmob), seasons=int(args.seasons))
    print(f"[fit_probfloor] 끝난 경기 {len(games)}건 · as-of "
          f"{as_of:%Y-%m-%d}", flush=True)
    # 🔴 **있는 판을 먼저 읽어 보인다** — 덮어쓰기 전에 무엇이 바뀌는지 보인다
    #    (판은 날짜별이라 덮이지 않지만, 로더가 고를 **직전 판**이 이것이다).
    from app.core import probfloor as _pf
    said_old, why_old = _pf.load_coef(league=args.league, as_of=as_of)
    print(f"[fit_probfloor] 직전 계수 판 — "
          + (f"{said_old}" if said_old else why_old), flush=True)
    p = _r.load_params(args.rating, league=args.league, as_of=as_of)
    print(f"[fit_probfloor] 바닥 점수 `{args.rating}` 학습률 {p.values}"
          + (f" · {p.why}" if p.provisional else f" · {p.ver}"), flush=True)
    # 🔴 **E1** — 적합 구간은 `as_of` 이전이다
    rows: list[tuple] = []
    seen: list[dict] = []
    lam_ln2 = math.log(2.0) / max(1.0, float(args.half_life))
    for one in sorted(games, key=lambda g: str(g["utc"])):
        when = datetime.fromisoformat(str(one["utc"]).replace("Z", "+00:00"))
        if when >= as_of:
            break
        if len(seen) >= 20:
            table = mod.rate(seen, params=p, as_of=when)
            diff = float(mod.prob_input(one["home"], one["away"], table))
            age = (as_of - when).days
            rows.append((diff, int(one["hg"]), int(one["ag"]),
                         math.exp(-lam_ln2 * age)))
        seen.append(one)
    if len(rows) < 100:
        print(f"🔴 표본 {len(rows)}건 — **적합하지 않는다**(100 미만)")
        return 1
    start = np.array([0.2, 0.3, 0.1, -0.05])
    got = minimize(nll, start, args=(rows,), method="Nelder-Mead",
                   options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-9})
    b0, b1, h, rho = (float(v) for v in got.x)
    n = len(rows)
    print(f"\n🔴 **적합** b0 {b0:+.4f} · b1 {b1:+.4f} · h_league {h:+.4f} · "
          f"ρ {rho:+.4f} · 음의 로그우도 {float(got.fun) / n:.4f}/경기 · "
          f"{n}건 · 수렴 {got.success}")
    # ⚠️ **이중 계산 금지** — 기존 홈 이점 실측 판과 **견주어 적는다**(곱하지 않는다)
    from app import rules as _rules
    said = _rules.goal_baseline(str(args.league))
    per = _rules.goal_share(str(args.league))
    old = (float(said.get("home_share")) / float(per)
           if said.get("home_share") and per else None)
    print(f"⚠️ 홈 이점 비교 — 적합 `h_league` exp({h:+.4f}) = ×{math.exp(h):.4f}"
          + (f" vs 기존 실측 배율 ×{old:.4f}" if old else " vs 기존 실측 **없다**")
          + " — 🔴 **따로 곱하지 않는다**(계약 P3)")
    if args.write:
        from versions_write import write as _write
        body = {"b0": round(b0, 6), "b1": round(b1, 6), "b2": 0.0,
                "h_league": round(h, 6), "rho": round(rho, 6),
                "fit": {"n": n, "nll_per_game": round(float(got.fun) / n, 6),
                        "converged": bool(got.success),
                        "rating": args.rating,
                        "rating_params": dict(p.values),
                        "rating_provisional": bool(p.provisional),
                        "half_life_days": float(args.half_life),
                        "as_of": as_of.date().isoformat(),
                        "home_mul_fitted": round(math.exp(h), 6),
                        "home_mul_measured": (round(old, 6) if old else None),
                        "note": "b2(선수 차)는 §4 전까지 0 고정(지시 §3)"}}
        out = _write("probfloor", str(args.league).replace(":", "_"),
                     day=as_of.date(), body=body,
                     head=("# 🔴 `tools/fit_probfloor.py` 가 적었다 — 손으로 "
                           "고치지 않는다(지시서 §3)"))
        print(f"🔴 판을 적었다 — {out}")
    else:
        print("⚠️ `--write` 가 없다 — 판을 적지 않았다(화면만)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
