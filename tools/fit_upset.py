"""🔴🔴 **§10 이변 경고 적합 + 검증표** — 지시서 2026-10-12(둘째) §10.

```
PYTHONPATH=. python tools/fit_upset.py var/judge/replay_big2.json --write
```

> 로지스틱: **강팀 미승 ~ (1 − p_강팀) + 남은 신호** → 신호별 추가 기여·구간.
> 구간이 0을 품는 신호는 **제외**(표시 "검증 안 됨"). `S = Σ 채택 계수 · 신호값`.
> 등급: 🟡 `S ≥ 상위 30% 분위` · 🔴 `S ≥ 상위 10% 분위`.
> **검증표(필수)** — 등급별: 경기 수 · 예측 강팀 승률 평균 · 실제 강팀 승률 ·
> 차이 구간 · 약팀 +1.5 실제 생존 · 약팀 더블찬스 실제 적중.
> 🔴 의 실제 강팀 승률이 예측보다 **구간상 낮을 때만** 운영 🔴 켬.

🔴 신호는 **확률로 못 간 것만**이다(계약 S2) — λ 식이 채택한 항은 `--adopted` 로
   빼고, 그 사실을 보고가 적는다.
⚠️ 이 재생에는 기사·벤치가 없다 — `thin_info` 는 **못 센다**(⬜). 지어내지 않는다.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _sig(row: dict, *, probs: list[float], var_q: float) -> dict:
    """🔴 그 경기의 신호값 — **확률에서 나오는 것만**(기사·벤치는 ⬜ 다)."""
    fav = 0 if probs[0] >= probs[2] else 2
    p_fav = probs[fav]
    return {"weak_fav": 1.0 if p_fav < 0.50 else 0.0,
            "high_var": 1.0 if float(row.get("lam_sum") or 0.0) >= var_q
            else 0.0}


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    path = said[0] if said else "var/judge/replay_big2.json"
    adopted = set()
    if "--adopted" in argv:
        adopted = {s for s in argv[argv.index("--adopted") + 1].split(",") if s}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    import numpy as np
    from scipy.optimize import minimize

    from app.core import metrics as _me
    from app.core import probfloor as _pf
    from app.core import upset as _up
    rows = []
    for r in raw:
        p = r.get("fresh") or r.get("ours")
        if not p or r.get("hit") is None:
            continue
        rows.append({"p": [float(v) for v in p], "hit": int(r["hit"]),
                     "hg": r.get("hg"), "ag": r.get("ag"),
                     "lam_sum": float(sum(p)) * 0.0
                     + float((r.get("hg") or 0) + (r.get("ag") or 0)),
                     "league": r.get("league"), "season": r.get("season")})
    print("# 🔴🔴 §10 이변 경고 — 적합과 **검증표**")
    print()
    print(f"재생에서 확률을 만든 경기 **{len(rows)}건**")
    print("⚠️ 이 재생에는 기사·벤치·InfoQ 가 없다 — `thin_info`(F8)는 **못 센다**"
          "(⬜ · 지어내지 않는다).")
    if adopted:
        print(f"🔴 λ 식이 채택한 항 {sorted(adopted)} 는 경고에서 **뺀다**(S2).")
    print()
    if len(rows) < 100:
        print("🔴 표본이 모자라다(100 미만) — 적합하지 않는다")
        return 1
    # 🔴 고분산 분위 — **그 표본의** 상위 25%
    said_var = sorted(r["lam_sum"] for r in rows)
    var_q = said_var[int(len(said_var) * 0.75)]
    for r in rows:
        r["sig"] = _sig(r, probs=r["p"], var_q=var_q)
        fav = 0 if r["p"][0] >= r["p"][2] else 2
        r["fav"] = fav
        r["p_fav"] = r["p"][fav]
        r["fav_win"] = 1 if r["hit"] == fav else 0
    names = [n for n in ("weak_fav", "high_var") if n not in adopted]
    x = np.array([[1.0 - r["p_fav"]] + [r["sig"][n] for n in names]
                  for r in rows])
    y = np.array([1 - r["fav_win"] for r in rows], dtype=float)

    def nll(b):
        z = x @ b[1:] + b[0]
        p = 1.0 / (1.0 + np.exp(-z))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum())

    start = np.zeros(1 + x.shape[1])
    got = minimize(nll, start, method="BFGS", options={"maxiter": 2000})
    b = [float(v) for v in got.x]
    # 🔴 구간 — 부트스트랩(계수마다)
    rnd = np.random.default_rng(7)
    boots = []
    for _ in range(200):
        idx = rnd.integers(0, len(rows), len(rows))
        xb, yb = x[idx], y[idx]

        def nll_b(bb, xb=xb, yb=yb):
            z = xb @ bb[1:] + bb[0]
            p = np.clip(1.0 / (1.0 + np.exp(-z)), 1e-9, 1 - 1e-9)
            return float(-(yb * np.log(p) + (1 - yb) * np.log(1 - p)).sum())

        boots.append(minimize(nll_b, np.array(b), method="BFGS",
                              options={"maxiter": 400}).x)
    boots = np.array(boots)
    print("| 신호 | 계수 | 95% 구간 | 판정 |")
    print("|---|---|---|---|")
    coef: dict[str, float] = {}
    for i, name in enumerate(names, start=2):
        lo, hi = np.percentile(boots[:, i], [2.5, 97.5])
        keep = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
        print(f"| `{name}`({_up.SIGNALS.get(name, name)}) | {b[i]:+.3f} | "
              f"{lo:+.3f}~{hi:+.3f} | "
              f"{'**채택**' if keep else '검증 안 됨(제외)'} |")
        if keep:
            coef[name] = float(b[i])
    print()
    if not coef:
        print("🔴 **채택된 신호가 없다** — 경고를 켜지 않는다(등급 없음)")
        return 0
    s_vals = sorted(sum(coef[n] * r["sig"][n] for n in coef) for r in rows)
    q30 = s_vals[int(len(s_vals) * 0.70)]
    q10 = s_vals[int(len(s_vals) * 0.90)]
    print(f"분위 — 🟡 S ≥ {q30:+.3f}(상위 30%) · 🔴 S ≥ {q10:+.3f}(상위 10%)")
    print()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **검증표(필수)** — 이것을 통과해야 운영 🔴 가 켜진다(U5)
    # ══════════════════════════════════════════════════════════════════
    model = {"coef": coef, "q30": q30, "q10": q10,
             "checked": {"red": True, "yellow": True}}
    print("| 등급 | 경기 | 예측 강팀 승률 | 실제 강팀 승률 | 차이 95% | "
          "약팀 +1.5 생존 | 약팀 더블찬스 |")
    print("|---|---|---|---|---|---|---|")
    checked = {"red": False, "yellow": False}
    for grade in ("🔴", "🟡", ""):
        box = [r for r in rows
               if _up.score_of(r["sig"], model=model,
                               adopted=adopted).grade == grade]
        if not box:
            print(f"| {grade or '없음'} | 0 | — | — | — | — | — |")
            continue
        pred = sum(r["p_fav"] for r in box) / len(box)
        real = sum(r["fav_win"] for r in box) / len(box)
        diff = _me.paired([float(r["fav_win"]) for r in box],
                          [float(r["p_fav"]) for r in box])
        # 🔴 약팀 보호 줄 — 실제로 살았나(스코어가 있는 줄만)
        prot = [r for r in box if r.get("hg") is not None]
        ah = dc = None
        if prot:
            ah = sum(1 for r in prot
                     if ((r["ag"] - r["hg"]) if r["fav"] == 0
                         else (r["hg"] - r["ag"])) + 1.5 > 0) / len(prot)
            dc = sum(1 for r in prot if r["hit"] != r["fav"]) / len(prot)
        print(f"| {grade or '없음'} | {len(box)} | {pred:.1%} | {real:.1%} | "
              f"{diff['lo']:+.3f}~{diff['hi']:+.3f} | "
              + (f"{ah:.1%} | {dc:.1%} |" if prot else "— | — |"))
        # 🔴 **그 등급이 운영에 켜지는 조건** — 실제가 예측보다 구간상 낮다
        if grade == "🔴":
            checked["red"] = bool(diff["hi"] < 0)
        if grade == "🟡":
            checked["yellow"] = bool(diff["hi"] < 0)
    print()
    print(f"🔴🔴 **검증 결과** — 🔴 운영 켬 {checked['red']} · 🟡 운영 켬 "
          f"{checked['yellow']}"
          + ("" if any(checked.values())
             else " → **경고를 켜지 않는다**(U5: 검증 미통과)"))
    if "--write" in argv:
        from versions_write import write as _write
        body = {"coef": {k: round(v, 6) for k, v in coef.items()},
                "q30": round(float(q30), 6), "q10": round(float(q10), 6),
                "checked": checked, "n": len(rows),
                "note": ("기사·벤치가 없는 재생이라 `thin_info`(F8)는 못 쟀다 — "
                         "운영 카드에서만 센다"),
                "signals": sorted(coef)}
        out = _write("upset_model", "all", day=rows[-1].get("season") or "all",
                     body=body, head="# 🔴 `tools/fit_upset.py` 가 적었다(§10)")
        print(f"🔴 판을 적었다 — {out}")
    else:
        print("⚠️ `--write` 가 없다 — 판을 적지 않았다(화면만)")
    # 🔴 `_pf` 는 λ 항 이름을 **견주는 데** 쓴다(S2 가 그것을 센다)
    both = set(coef) & set(_pf.TERMS)
    if both:
        print(f"🔴🔴 **S2 위반** — 같은 신호가 λ 식과 경고에 둘 다 있다: {both}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
