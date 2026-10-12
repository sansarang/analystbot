"""🔴🔴 **2번 M3 < M2 원인 · 3번 M4 측정** — 사용자 지시 2026-10-12(비교 확인).

```
PYTHONPATH=. python tools/why_m3.py var/judge/replay_big2.json
```

> 2. M3 < M2 원인: 엔진 v2 에서 **채택된 항별로 하나씩 빼며** 같은 460경기 로그
>    손실 표. 채택 시험 표본·시즌 교차 여부 **재확인**. 해로운 항은 **채택 취소**.
> 3. M4 측정: 못 잰 사유와 함께 **지금 잰다**(M3 + 축2·축3 연속값, 교차 적합).

🔴 M2 = 바닥 + 축0·축1 을 **승무패 수준에서** 섞은 수(`legacy_blend`).
🔴 M3 = 바닥을 **λ 로 번역**하고 그 위에 같은 잔차를 얹은 수(`probfloor`).
   ⚠️ 두 수가 다른 까닭은 **항이 아니라 섞는 자리**일 수 있다 — 그래서 이 도구는
   항을 빼는 표와 **자리를 바꾼 표**를 함께 낸다(없는 원인을 지어내지 않는다).
🔴 축2·축3 은 백필 덤프의 `gaps` 에 **연속값으로 있다** → M4 를 **지금** 잴 수 있다
   (비교 시험에서 못 쟀다고 적은 까닭은 `compare_paths` 가 그 항을 식에 안 넣었기
   때문이다 · 그 사실을 보고가 적는다).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    path = ROOT / (said[0] if said else "var/judge/replay_big2.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    from app import rules as _rules
    from app.core import base as _base
    from app.core import matchup as _mu
    from app.core import metrics as _me
    from app.core import probfloor as _pf
    from app.core import probmodel as _pm
    from app.core import sim as _sim
    from backfill_score import legacy_blend as _blend
    from fit_base_model import _fit_rows
    conf = dict(_mu.table().get("weights") or {})
    beta = float(dict(_mu.table().get("lambda_model") or {}).get("beta") or 0.25)
    cap = float(dict(_mu.table().get("lambda_model") or {}).get("cap_pct")
                or 35.0) / 100.0
    rows = [r for r in raw if r.get("hg") is not None and r.get("dr") is not None
            and r.get("gaps")]
    seasons = sorted({str(r.get("season") or "") for r in rows})
    print("# 🔴🔴 2번 M3<M2 원인 · 3번 M4 측정")
    print()
    print(f"재생 {len(rows)}줄 · 시즌 {seasons}")
    print()
    # ── 모형 정의: 이름 → (섞는 자리, 쓰는 축)
    MIX = {
        "M2 승무패 섞기 · 축0·축1": ("probs", ("axis0", "axis1")),
        "M2′ 승무패 섞기 · 축0만": ("probs", ("axis0",)),
        "M2″ 승무패 섞기 · 축1만": ("probs", ("axis1",)),
        "M2‴ 승무패 섞기 · 네 축": ("probs", ("axis0", "axis1", "axis2",
                                           "axis3")),
        "M3 λ 섞기 · 축0·축1": ("lambda", ("axis0", "axis1")),
        "M3′ λ 섞기 · 축0만": ("lambda", ("axis0",)),
        "M3″ λ 섞기 · 축1만": ("lambda", ("axis1",)),
        "M3‴ λ 섞기 · 잔차 0(바닥만)": ("lambda", ()),
        "M4 λ 섞기 · 네 축(축2·축3 연속값)": ("lambda", ("axis0", "axis1",
                                                 "axis2", "axis3")),
    }
    # 🔴 `solve_move` 는 **이분법 40번 × 시뮬**이다 — 같은 (바닥, 평균, 배율)
    #    이면 같은 답이므로 **기억해 둔다**(수는 안 바뀐다 · 속도만 바뀐다).
    memo: dict[tuple, float | None] = {}

    def _move(floor_triple, mean, mul_h, mul_a):
        key = (round(float(floor_triple[0]), 4), round(float(mean), 4),
               round(float(mul_h), 4), round(float(mul_a), 4))
        if key not in memo:
            got, _why = _pf.solve_move(list(floor_triple), mean=mean,
                                       mul_home=mul_h, mul_away=mul_a)
            memo[key] = got
        return memo[key]

    ll: dict[str, list[float]] = {k: [] for k in MIX}
    hit_n: dict[str, int] = {k: 0 for k in MIX}
    keep: list[dict] = []
    for s in seasons:
        ev = [r for r in rows if str(r.get("season") or "") == s]
        fi = [r for r in rows if str(r.get("season") or "") != s]
        if len(ev) < 30 or len(fi) < 100:
            print(f"- ⚠️ 시즌 `{s}` — 바깥 {len(fi)}경기(100 미만) → **뺀다**")
            continue
        _me.check_split(fit={str(r.get("season") or "") for r in fi}, eval={s})
        by_kind = {}
        for kind in sorted({r["league"] for r in fi}):
            said_rows = [(float(r["dr"]), 2 - int(r["hit"])) for r in fi
                         if r["league"] == kind]
            if len(said_rows) >= 100:
                by_kind[kind] = _fit_rows(said_rows)
        for one in ev:
            kind = one["league"]
            co = by_kind.get(kind)
            if not co:
                continue
            floor = _base.triple_from(c1=co["c1"], c2=co["c2"],
                                      b_dr=co["b_dr"], dr=float(one["dr"]))
            mean = float(_rules.goal_share(kind) or 1.3)
            base_box = _rules.goal_baseline(kind)
            mul_a, _w = _pm.away_mul(home_share=base_box.get("home_share"),
                                     per_team=mean)
            mul_h = (float(base_box["home_share"]) / mean
                     if base_box.get("home_share") else 1.0)
            hit = int(one["hit"])
            keep.append(one)
            for name, (where, axes) in MIX.items():
                w = {k: float(conf.get(k) or 0.0) for k in axes}
                if where == "probs":
                    got, _why = _blend([floor.home, floor.draw, floor.away],
                                       gaps=one["gaps"], weights=w, beta=beta)
                    p = list(got or [floor.home, floor.draw, floor.away])
                else:
                    m0 = _move([floor.home, floor.draw, floor.away], mean,
                               mul_h, mul_a)
                    if m0 is None:
                        p = [floor.home, floor.draw, floor.away]
                    else:
                        res = sum(float(w.get(k) or 0.0)
                                  * float(dict(one["gaps"]).get(k) or 0.0)
                                  for k in axes)
                        rmove = max(-cap, min(cap, beta * res))
                        out = _sim.run(mean * mul_h * math.exp(m0 + rmove),
                                       mean * mul_a * math.exp(-(m0 + rmove)))
                        p = [out.home, out.draw, out.away]
                ll[name].append(_me.logloss(p, hit))
                hit_n[name] += 1 if _me.direction_hit(p, hit) else 0
    n = len(keep)
    print()
    print(f"🔴 **짝지은 표본 {n}경기**")
    print()
    print("| 모형(섞는 자리 · 축) | **로그 손실** | 방향 적중률 | M3 와의 차 |")
    print("|---|---|---|---|")
    base_name = "M3 λ 섞기 · 축0·축1"
    for name in MIX:
        if not ll[name]:
            print(f"| {name} | — | — | 표본 없음 |")
            continue
        diff = _me.paired(ll[name], ll[base_name])
        print(f"| {name} | **{sum(ll[name]) / n:.4f}** | "
              f"{hit_n[name] / n:.1%} | {diff['mean']:+.4f}"
              f"({diff['lo']:+.4f}~{diff['hi']:+.4f}) |")
    print()
    print("## 읽는 법")
    print()
    print("- **M2 vs M3** 는 *같은 축·같은 바닥*이고 **섞는 자리만** 다르다 — "
          "승무패 수준이냐 λ 수준이냐.")
    print("- **M3‴**(잔차 0)은 **바닥만**이다. M3 가 그보다 나쁘면 *잔차 자체가* "
          "해롭다는 뜻이고, 비슷하면 차이는 **섞는 자리**에서 온다.")
    print("- **M4** 는 축2·축3 **연속값**을 같은 λ 식에 넣은 수다(교차 적합 바닥).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
