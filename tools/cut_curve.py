"""🔴🔴 **문턱 곡선**(공격형 검증 v2 · 지시 2026-10-14f §6).

```
PYTHONPATH=. python tools/cut_curve.py
```

🔴 **단폴·다리 문턱별** 적중률과 **하루 출력 수**를 백필에서 센다 — 문턱은
   이 곡선으로만 고른다(§6 *"문턱은 시즌 교차로만 고른다"*).
🔴 줄은 운영 λ 에서 **같은 격자**로 만든다(`probfloor.markets_of` · 사본 금지).
⚠️ 다폴은 **다리끼리 독립**이라고 가정하지 않는다 — 같은 날 다른 경기의 다리를
   실제로 묶어 **그 날 전부 맞았나**로 센다(곱셈 가정 없음).
"""
from __future__ import annotations

import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

# 🔴 ⚠️ 실측 2026-10-14: 경기당 **최고 줄**은 거의 핸디 +1.5(≈87%)라 0.80 아래
#    문턱은 **전부 통과**한다(곡선이 평평했다) → 문턱 범위를 올려 잡는다.
CUTS = (0.70, 0.80, 0.85, 0.88, 0.90, 0.93, 0.95)


def lines_of(lam: list[float], hg: int, ag: int) -> list[tuple]:
    """🔴 그 경기의 **줄 후보** — `(이름, 확률, 맞았나)`."""
    from app.core import probfloor as _pf
    from app.core import sim as _sim
    box = _pf.markets_of(_pf.score_grid(lam_home=lam[0], lam_away=lam[1]))
    out = _sim.run(lam[0], lam[1])
    d, tot = hg - ag, hg + ag
    got = [("홈 승", out.home, d > 0), ("원정 승", out.away, d < 0),
           ("무", out.draw, d == 0)]
    for key, ok in (("home-0.5", d > 0), ("home+0.5", d >= 0),
                    ("home+1.5", d > -2), ("away+0.5", d <= 0),
                    ("away+1.5", d < 2)):
        p = dict(box.get("ah") or {}).get(key)
        if p is not None:
            got.append((f"핸디 {key}", float(p), ok))
    for x in (1.5, 2.5, 3.5):
        p = dict(box.get("over") or {}).get(x)
        if p is not None:
            got.append((f"오버 {x}", float(p), tot > x))
            got.append((f"언더 {x}", 1.0 - float(p), tot < x))
    p = box.get("btts_yes")
    if p is not None:
        got.append(("BTTS 예", float(p), hg > 0 and ag > 0))
    return got


def main() -> int:
    import replays

    rows, said = replays.load()
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None]
    print(f"# 🔴🔴 문턱 곡선 — {said}")
    print()
    days: dict[str, list] = {}
    best: list[tuple] = []
    for r in rows:
        got = lines_of([float(x) for x in r["lam"][:2]], int(r["hg"]),
                       int(r["ag"]))
        top = max(got, key=lambda x: x[1])
        best.append((top[1], top[2], str(r.get("day")), str(r.get("league")),
                     top[0]))
        days.setdefault(str(r.get("day")), []).append(top)
    print("| 문턱 | 단폴 수 | 적중 | 하루 평균 | 같은 줄 상위 3 |")
    print("|---|---|---|---|---|")
    n_days = len(days) or 1
    for cut in CUTS:
        part = [x for x in best if x[0] >= cut]
        if not part:
            print(f"| {cut:.2f} | 0 | ⬜ | 0.0 | ⬜ |")
            continue
        from collections import Counter
        top3 = Counter(x[4] for x in part).most_common(3)
        print(f"| **{cut:.2f}** | {len(part)} | "
              f"**{100 * sum(1 for x in part if x[1]) / len(part):.1f}%** | "
              f"{len(part) / n_days:.2f} | "
              + " · ".join(f"{k} {v}" for k, v in top3) + " |")
    print()
    print("| 다리 문턱 | 2폴 묶음 | 2폴 적중 | 3폴 묶음 | 3폴 적중 |")
    print("|---|---|---|---|---|")
    for cut in CUTS:
        two = three = ok2 = ok3 = 0
        for day, got in days.items():
            legs = [x for x in got if x[1] >= cut]
            # 🔴 **같은 경기 금지** — 경기당 한 줄만 들어 있다(`best`)
            if len(legs) >= 2:
                two += 1
                ok2 += int(all(x[2] for x in legs[:2]))
            if len(legs) >= 3:
                three += 1
                ok3 += int(all(x[2] for x in legs[:3]))
        print(f"| {cut:.2f} | {two} | "
              + (f"**{100 * ok2 / two:.1f}%**" if two else "⬜")
              + f" | {three} | "
              + (f"{100 * ok3 / three:.1f}%" if three else "⬜") + " |")
    # ── 🔴 줄 **종류별 보정**(예측 대비 실측) — 어느 줄이 믿을 만한가
    print()
    print("| 줄 종류 | 경기 | 예측 평균 | 실측 | 편차 | 0.70+ 적중 | 0.85+ 적중 |")
    print("|---|---|---|---|---|---|---|")
    fam: dict[str, list] = {}
    for r in rows:
        for nm, p, ok in lines_of([float(x) for x in r["lam"][:2]],
                                  int(r["hg"]), int(r["ag"])):
            key = ("승무패" if nm in ("홈 승", "원정 승", "무")
                   else ("핸디" if nm.startswith("핸디")
                         else ("오버·언더" if nm.startswith(("오버", "언더"))
                               else "BTTS")))
            fam.setdefault(key, []).append((p, ok))
    for key, xs in sorted(fam.items()):
        pred = stat.mean(p for p, _ok in xs)
        real = sum(1 for _p, ok in xs if ok) / len(xs)
        a = [ok for p, ok in xs if p >= 0.70]
        b = [ok for p, ok in xs if p >= 0.85]
        print(f"| {key} | {len(xs)} | {100 * pred:.1f}% | {100 * real:.1f}% | "
              f"**{100 * (real - pred):+.1f}%p** | "
              + (f"{100 * sum(a) / len(a):.1f}%({len(a)})" if a else "⬜")
              + " | " + (f"{100 * sum(b) / len(b):.1f}%({len(b)})" if b
                         else "⬜") + " |")
    print()
    print(f"- 날 수 {len(days)} · 경기 {len(rows)} · 경기당 최고 줄 확률 중앙값 "
          f"{100 * stat.median([x[0] for x in best]):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
