"""🔴🔴 **5번 M1 무승부 보정** — 사용자 지시 2026-10-12(비교 확인).

```
PYTHONPATH=. python tools/m1_draw.py var/judge/replay_big2.json
```

> M1 무승부 과대(**26.9 vs 20.9**) — Dixon-Coles ρ 또는 **무승부 스케일**을 교차
> 적합해 보정 판 비교(**방향 적중률 손상 없을 때만**).

🔴 두 길을 **둘 다** 센다:
   · `rho` — Dixon-Coles τ(0-0·1-0·0-1·1-1 네 칸)
   · `draw` — **대각선 전체**에 `exp(d)` 를 곱하고 다시 정규화(무승부 스케일)
🔴 계수는 **평가 시즌 밖**에서 포아송/다항 우도로 적합한다(E1 · `check_split`).
🔴 채택 조건은 사용자 말 그대로다: **방향 적중률이 손상되지 않을 때만**.
⚠️ M1 의 λ 는 **얼린 경로의 식**으로 되살린다(`legacy.sides_move` + 리그 평균·
   홈/원정 배율) — 그 수를 다시 짓지 않는다(K0).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _grid_of(row, *, mean, mul_h, mul_a, weights, beta, cap):
    from app.core import sim as _sim
    from app.core.legacy import old_engine as _oe
    box = {}
    for name in ("axis0", "axis1", "axis2", "axis3"):
        got = float(dict(row.get("gaps") or {}).get(name) or 0.0)
        if got:
            box[name] = {"att": {"home": got / 2.0, "away": -got / 2.0},
                         "dfn": {"home": got / 2.0, "away": -got / 2.0}}
    move = _oe.sides_move(box, weights, beta=beta, cap=cap)
    out = _sim.run(mean * mul_h * math.exp(move["home"]),
                   mean * mul_a * math.exp(move["away"]))
    return {k: float(v) for k, v in dict(out.scores).items()}


def _bend(grid: dict, *, kind: str, val: float) -> list[float]:
    """🔴 `rho`(네 칸) 또는 `draw`(대각선 전체)를 걸고 승무패를 센다."""
    got = {}
    for key, p in grid.items():
        h, a = (int(key[0]), int(key[1]))
        mul = 1.0
        if kind == "draw" and h == a:
            mul = math.exp(val)
        elif kind == "rho":
            if (h, a) == (1, 1):
                mul = 1.0 - val
            elif (h, a) == (0, 0):
                mul = 1.0 - val
            elif (h, a) in ((1, 0), (0, 1)):
                mul = 1.0 + val
        got[(h, a)] = max(0.0, p * mul)
    tot = sum(got.values()) or 1.0
    home = sum(v for (h, a), v in got.items() if h > a) / tot
    draw = sum(v for (h, a), v in got.items() if h == a) / tot
    away = sum(v for (h, a), v in got.items() if h < a) / tot
    return [home, draw, away]


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    raw = json.loads((ROOT / (said[0] if said
                              else "var/judge/replay_big2.json")
                      ).read_text(encoding="utf-8"))
    from app import rules as _rules
    from app.core import matchup as _mu
    from app.core import metrics as _me
    from app.core import probmodel as _pm
    conf = dict(_mu.table().get("weights") or {})
    beta = float(dict(_mu.table().get("lambda_model") or {}).get("beta") or 0.25)
    cap = float(dict(_mu.table().get("lambda_model") or {}).get("cap_pct")
                or 35.0) / 100.0
    rows = [r for r in raw if r.get("hit") is not None and r.get("gaps")]
    seasons = sorted({str(r.get("season") or "") for r in rows})
    print("# 🔴🔴 5번 M1 무승부 보정")
    print()
    print(f"재생 {len(rows)}줄 · 시즌 {seasons}")
    print()
    # ── 격자를 한 번만 만든다(λ 는 리그 평균·배율·축 차로 정해진다)
    cache: dict[str, tuple[float, float, float]] = {}
    for r in rows:
        kind = r["league"]
        if kind not in cache:
            mean = float(_rules.goal_share(kind) or 1.3)
            box = _rules.goal_baseline(kind)
            mul_a, _w = _pm.away_mul(home_share=box.get("home_share"),
                                     per_team=mean)
            mul_h = (float(box["home_share"]) / mean
                     if box.get("home_share") else 1.0)
            cache[kind] = (mean, mul_h, mul_a)
        mean, mul_h, mul_a = cache[kind]
        r["grid"] = _grid_of(r, mean=mean, mul_h=mul_h, mul_a=mul_a,
                             weights=conf, beta=beta, cap=cap)
    print("| 보정 | 고른 값 | 로그 손실 | 방향 적중률 | 무승부 예측 평균 | 판정 |")
    print("|---|---|---|---|---|---|")
    base_ll: list[float] = []
    base_hit = 0
    base_draw = 0.0
    out_rows: dict[str, dict] = {}
    for kind, grid_vals in (("none", (0.0,)),
                            ("rho", (-0.2, -0.1, -0.05, 0.05, 0.1, 0.2)),
                            ("draw", (-0.4, -0.3, -0.2, -0.1, 0.1, 0.2))):
        ll: list[float] = []
        hits = 0
        draw_pred = 0.0
        n = 0
        picked: list[float] = []
        for s in seasons:
            ev = [r for r in rows if str(r.get("season") or "") == s]
            fi = [r for r in rows if str(r.get("season") or "") != s]
            if len(ev) < 30 or len(fi) < 100:
                continue
            _me.check_split(fit={str(r.get("season") or "") for r in fi},
                            eval={s})
            # 🔴 바깥 시즌에서 **로그 손실 최소**인 값을 고른다(교차 적합)
            best = None
            for val in grid_vals:
                got = sum(_me.logloss(_bend(r["grid"], kind=kind, val=val),
                                      int(r["hit"])) for r in fi) / len(fi)
                if best is None or got < best[0]:
                    best = (got, val)
            val = best[1]
            picked.append(val)
            for r in ev:
                p = _bend(r["grid"], kind=kind, val=val)
                ll.append(_me.logloss(p, int(r["hit"])))
                hits += 1 if _me.direction_hit(p, int(r["hit"])) else 0
                draw_pred += p[1]
                n += 1
        if not n:
            print(f"| {kind} | — | — | — | — | 표본 없음 |")
            continue
        if kind == "none":
            base_ll, base_hit, base_draw = list(ll), hits, draw_pred / n
            print(f"| 없음(기준 M1) | — | **{sum(ll) / n:.4f}** | "
                  f"{hits / n:.1%} | {draw_pred / n:.1%} | 기준 |")
            continue
        diff = _me.paired(ll, base_ll)
        ok_dir = hits >= base_hit
        verdict = ("✅ **채택**" if (diff["mean"] < 0 and diff["lo"] < 0
                                 and ok_dir)
                   else ("🔴 방향 손상" if not ok_dir else "⚠️ 유지(이득 불확실)"))
        out_rows[kind] = {"ll": sum(ll) / n, "hit": hits / n}
        print(f"| {kind} | {picked} | **{sum(ll) / n:.4f}**"
              f"({diff['mean']:+.4f} · {diff['lo']:+.4f}~{diff['hi']:+.4f}) | "
              f"{hits / n:.1%} | {draw_pred / n:.1%} | {verdict} |")
    print()
    print(f"⚠️ 실제 무승부율은 "
          f"{sum(1 for r in rows if int(r['hit']) == 1) / len(rows):.1%} 다 — "
          f"기준 M1 의 예측 평균은 {base_draw:.1%}.")
    print("🔴 **방향 적중률이 손상되면 채택하지 않는다**(사용자 조건).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
