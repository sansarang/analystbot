"""🔴🔴 **축이 방향을 못 바꾼 원인**(검증 지시 2026-10-14d · 측정만).

```
PYTHONPATH=. python tools/axis_audit.py
```

🔴 **아무 계수도 바꾸지 않는다** — 백필 덤프(`var/judge/replay_*.json`)의
   `gaps`(축 차) · `lam`(최종 λ 쌍) · `hit`(결과) 로 세 판을 **복원해** 센다:
   · **운영 M1**  : `lam` 그대로
   · **M1만**     : λ 에서 **축 이동을 빼낸다**(홈 배율만 남는다)
   · **상성만**   : 두 λ 의 기하평균에 **축 이동만** 얹는다(홈 배율 0)
🔴 방향은 λ 비율만으로 갈린다 — 그래서 상성만 판의 총골 눈금은 방향에 영향이 없다
   (기하평균을 써도 방향·적중은 같다).
🔴 **β 역산** — 최종 기울기 `log(λh/λa) = 홈몫 + 2·β·Σ` 에서 홈몫을 떼어내고,
   방향이 뒤집히는 β\* = −홈몫 / (2Σ) 를 센다. Σ 부호가 홈몫과 같으면 **어떤 β
   로도 안 뒤집힌다**(β\* < 0).
⚠️ `move = β·Σ` 로 되돌린다 — 카드의 T 규칙(±5~12%)은 이 되돌림에 안 들어간다
   (실측 차이: 브리스톨 0.069 vs 카드 0.062). 그 사실을 표에 적는다.
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BETA = 0.25
W = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}
AXES = ("axis0", "axis1", "axis2", "axis3")


def rows_all() -> list[dict]:
    """🔴 백필 덤프 전부 — `gaps`·`lam`·`hit` 를 든 줄만."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted((ROOT / "var/judge").glob("replay_*.json")):
        try:
            got = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for r in (got if isinstance(got, list) else []):
            if not isinstance(r, dict) or not r.get("lam"):
                continue
            key = (r.get("league"), r.get("day"), r.get("home"), r.get("away"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def sigma_of(r: dict) -> tuple[float, dict]:
    """🔴 축 종합 — 빈 축은 **0 으로 들어간다**(가중 재배분 없다)."""
    gaps = dict(r.get("gaps") or {})
    said = {a: (float(gaps[a]) if gaps.get(a) is not None else None)
            for a in AXES}
    got = sum(W[a] * (said[a] or 0.0) for a in AXES)
    return got, said


def triple(lh: float, la: float) -> list[float]:
    from app.core import sim
    out = sim.run(max(lh, 1e-6), max(la, 1e-6))
    return [out.home, out.draw, out.away]


def pick(t: list[float]) -> int:
    """🔴 방향 — 0 홈 · 1 무 · 2 원정(가장 높은 줄)."""
    return max(range(3), key=lambda i: t[i])


def quant(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, int(round(p * (len(ys) - 1)))))
    return ys[i]


def main() -> int:
    rows = rows_all()
    print(f"# 🔴🔴 축 감사 — 백필 **{len(rows)}경기**(`var/judge/replay_*.json`)")
    print()

    # ── ① 축 유효율과 차의 분포 ────────────────────────────────────
    print("## ① 축이 **있나** · 차는 **얼마나 큰가**")
    print()
    print("| 축 | 값 있는 경기 | 비율 | 차 중앙값 | p10 | p90 | |차| 중앙값 "
          "| 가중 × |차| 중앙값 |")
    print("|---|---|---|---|---|---|---|---|")
    for a in AXES:
        xs = [float(dict(r.get("gaps") or {})[a])
              for r in rows if dict(r.get("gaps") or {}).get(a) is not None]
        if not xs:
            print(f"| `{a}` | **0** | 0.0% | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |")
            continue
        ab = [abs(x) for x in xs]
        print(f"| `{a}` | {len(xs)} | {100*len(xs)/len(rows):.1f}% | "
              f"{st.median(xs):+.3f} | {quant(xs, 0.1):+.3f} | "
              f"{quant(xs, 0.9):+.3f} | {st.median(ab):.3f} | "
              f"**{W[a]*st.median(ab):.3f}** |")
    sig = [sigma_of(r)[0] for r in rows]
    print()
    print(f"- 축 종합 Σ — 중앙값 {st.median(sig):+.3f} · |Σ| 중앙값 "
          f"{st.median([abs(x) for x in sig]):.3f} · p10 {quant(sig, 0.1):+.3f}"
          f" · p90 {quant(sig, 0.9):+.3f}")
    four = sum(1 for r in rows
               if all(dict(r.get("gaps") or {}).get(a) is not None
                      for a in AXES))
    print(f"- 네 축이 **다 찬 경기** — {four}건({100*four/len(rows):.1f}%)")

    # ── ② 방향: 운영 vs M1만 vs 상성만 ─────────────────────────────
    print()
    print("## ② 방향이 **갈리나** · 갈린 데서 누가 맞나")
    split = hit = {}
    box = {"운영": [0, 0], "M1만": [0, 0], "상성만": [0, 0]}
    splits: list[dict] = []
    for r in rows:
        lh, la = (float(x) for x in r["lam"][:2])
        s, _said = sigma_of(r)
        move = BETA * s
        one = triple(lh, la)
        two = triple(lh * math.exp(-move), la * math.exp(move))
        g = math.sqrt(max(lh * la, 1e-9))
        three = triple(g * math.exp(move), g * math.exp(-move))
        got = r.get("hit")
        if got is None:
            continue
        for name, t in (("운영", one), ("M1만", two), ("상성만", three)):
            box[name][1] += 1
            box[name][0] += int(pick(t) == int(got))
        if pick(one) != pick(two):
            splits.append({"r": r, "one": one, "two": two, "three": three,
                           "hit": int(got), "sigma": s})
    print()
    print(f"- 운영 ↔ M1만 **방향이 갈린 경기 {len(splits)}건 / "
          f"{box['운영'][1]}건 = {100*len(splits)/max(1,box['운영'][1]):.1f}%**")
    print()
    print("| 판 | 전체 방향 적중 | 갈린 경기에서만 |")
    print("|---|---|---|")
    for name in ("운영", "M1만", "상성만"):
        a, n = box[name]
        key = {"운영": "one", "M1만": "two", "상성만": "three"}[name]
        sa = sum(1 for s in splits if pick(s[key]) == s["hit"])
        print(f"| {name} | {a}/{n} = **{100*a/max(1,n):.1f}%** | "
              f"{sa}/{len(splits)} = {100*sa/max(1,len(splits)):.1f}% |")

    # ── ②-b 축마다 **혼자서** 방향을 맞히나 ───────────────────────
    print()
    print("## ②-b 축 **하나씩** — 그 축의 부호가 결과를 맞히나")
    print()
    print("| 축 | 부호 있는 경기 | 홈 쪽 가리킴 | 그때 홈 승 | 원정 쪽 가리킴 "
          "| 그때 원정 승 | 부호 적중(무 제외) |")
    print("|---|---|---|---|---|---|---|")
    for a in AXES:
        hs = ha = as_ = aa = 0
        for r in rows:
            v = dict(r.get("gaps") or {}).get(a)
            got = r.get("hit")
            if v is None or got is None or abs(float(v)) < 1e-9:
                continue
            if float(v) > 0:
                hs += 1
                ha += int(int(got) == 0)
            else:
                as_ += 1
                aa += int(int(got) == 2)
        tot = hs + as_
        ok = ha + aa
        print(f"| `{a}` | {tot} | {hs} | {ha}({100*ha/max(1,hs):.1f}%) | "
              f"{as_} | {aa}({100*aa/max(1,as_):.1f}%) | "
              f"**{100*ok/max(1,tot):.1f}%** |")
    # 🔴 축0 이 Σ 를 **지배하는** 비율 — |w0·Δ0| 가 나머지 셋 합보다 큰가
    rule = 0
    both = 0
    for r in rows:
        _s, said = sigma_of(r)
        if said["axis0"] is None:
            continue
        both += 1
        mine = abs(W["axis0"] * said["axis0"])
        rest = sum(abs(W[a] * (said[a] or 0.0)) for a in AXES[1:])
        rule += int(mine > rest)
    print()
    print(f"- 축0 이 Σ 를 **지배한 경기**(|w0·Δ0| > 나머지 셋 합) — {rule}/{both}"
          f" = **{100*rule/max(1,both):.1f}%**")

    # ── ③ β 역산 ──────────────────────────────────────────────────
    print()
    print("## ③ β 역산 — **어떤 β 로도 안 뒤집히는 경기**가 얼마나 되나")
    never = 0
    needs: list[float] = []
    for r in rows:
        lh, la = (float(x) for x in r["lam"][:2])
        s, _said = sigma_of(r)
        tilt = math.log(lh / la)                  # 최종 기울기
        home_part = tilt - 2 * BETA * s           # 홈 배율이 낸 몫
        if abs(s) < 1e-9 or home_part * s >= 0:
            never += 1
            continue
        needs.append(-home_part / (2 * s))
    ok = [x for x in needs if x > 0]
    print()
    print(f"- Σ 부호가 홈몫과 **같아 못 뒤집는 경기** — {never}건"
          f"({100*never/len(rows):.1f}%)")
    if ok:
        print(f"- 뒤집히려면 필요한 β — 중앙값 **{st.median(ok):.2f}**"
              f"(지금 {BETA}) · p10 {quant(ok, 0.1):.2f} · p90 "
              f"{quant(ok, 0.9):.2f} · β {BETA} 로 이미 뒤집히는 경기 "
              f"{sum(1 for x in ok if x <= BETA)}건")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
