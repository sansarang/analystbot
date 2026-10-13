"""🔴🔴 **무 보정 후보 시험 D1·D2**(수정 지시 2026-10-13 밤 2-③).

```
PYTHONPATH=. python tools/draw_trial.py
```

> ③ 후보 시험 (ρ 는 **폐기 상태** — 다시 쓰지 않는다)
>   D1: 구간별 무 보정(교차 판 적합 · 시즌 밖 검증) — 늘린 무 몫은 승·패에서
>       비례로 뺀다.
>   D2: 저득점 칸(0-0·1-1) 질량 보정 — 스코어 격자에서 직접.
>   판정 = 규칙 v2 (a)(b)(c)(d) + **무 구간 보정 오차 절댓값 감소**. 둘 다
>   탈락이면 경로 그대로.

🔴 **시즌 교차**다 — 보정값은 **평가 시즌 밖**에서만 적합한다(누설 금지 · EN5).
🔴 판정 규칙은 **실행 전 커밋된** `judge_models.passes(rule="season")` 그대로다
   (결과를 보고 고치지 않는다). 거기에 **무 구간 오차**를 하나 더 본다.
⚠️ ρ(Dixon-Coles)는 **쓰지 않는다** — 그 판은 0-0 빠진 표본에서 적합돼 무효다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 D1 이 무를 밀 수 있는 한계(그 밖은 보정하지 않는다 — 폭주 방지)
D1_CAP = 0.06

#: 🔴 D2 가 저득점 두 칸에 걸 배율 격자
D2_GRID = tuple(round(0.8 + 0.05 * i, 2) for i in range(17))

#: 🔴 D2 가 손대는 칸(지시의 그 둘)
LOW_CELLS = ((0, 0), (1, 1))


def triple_of(grid: dict) -> list[float]:
    from app.core import probfloor as _pf
    mk = _pf.markets_of(grid)
    return [float(mk["home"]), float(mk["draw"]), float(mk["away"])]


def d1_fit(rows: list[dict]) -> dict:
    """🔴 구간별 `실측 − 예측` 평균(그만큼 무를 민다 · 상한 `D1_CAP`)."""
    from draw_audit import DRAW_BANDS, band_of
    out: dict[str, float] = {}
    for name, _lo, _hi in DRAW_BANDS:
        box = [r for r in rows if band_of(r["_t"][1], DRAW_BANDS) == name]
        if len(box) < 100:
            out[name] = 0.0
            continue
        p = sum(r["_t"][1] for r in box) / len(box)
        y = sum(1 for r in box if r["hg"] == r["ag"]) / len(box)
        out[name] = max(-D1_CAP, min(D1_CAP, y - p))
    return out


def d1_apply(one: list[float], plate: dict) -> list[float]:
    """🔴 무를 `plate` 만큼 밀고 **승·패에서 비례로** 뺀다."""
    from draw_audit import DRAW_BANDS, band_of
    said = float(plate.get(band_of(one[1], DRAW_BANDS)) or 0.0)
    draw = max(0.01, min(0.60, one[1] + said))
    rest = 1.0 - draw
    tot = one[0] + one[2]
    if tot <= 0:
        return [rest / 2, draw, rest / 2]
    return [one[0] / tot * rest, draw, one[2] / tot * rest]


def d2_fit(rows: list[dict]) -> float:
    """🔴 저득점 두 칸 배율 — 훈련 줄 **로그 손실 최소**(격자 탐색)."""
    from app.core import metrics as me
    best = (1.0, None)
    for k in D2_GRID:
        tot = 0.0
        for r in rows:
            said = triple_of(d2_apply(r["grid"], k))
            tot += me.logloss(said, r["hit"])
        got = tot / max(1, len(rows))
        if best[1] is None or got < best[1]:
            best = (k, got)
    return float(best[0])


def d2_apply(grid: dict, k: float) -> dict:
    """🔴 `0-0`·`1-1` 칸에 배율 → **다시 정규화**(질량 보존)."""
    out = {kk: (v * float(k) if kk in LOW_CELLS else v)
           for kk, v in dict(grid).items()}
    tot = sum(out.values()) or 1.0
    return {kk: v / tot for kk, v in out.items()}


def band_err(rows: list[dict], probs: list[list[float]]) -> tuple[float, str]:
    """🔴 **무 구간 보정 오차** — 구간마다 |예측−실측| 을 경기 수로 가중 평균."""
    from draw_audit import DRAW_BANDS, band_of
    box: dict[str, list] = {}
    for r, p in zip(rows, probs, strict=True):
        box.setdefault(band_of(p[1], DRAW_BANDS), []).append((p[1], r))
    tot, n, said = 0.0, 0, []
    for name, _lo, _hi in DRAW_BANDS:
        mine = box.get(name) or []
        if not mine:
            continue
        pp = sum(x[0] for x in mine) / len(mine)
        yy = sum(1 for _p, r in mine if r["hg"] == r["ag"]) / len(mine)
        tot += abs(pp - yy) * len(mine)
        n += len(mine)
        said.append(f"{name} {pp - yy:+.1%}({len(mine)})")
    return (tot / max(1, n)), " · ".join(said)


def main(argv: list[str]) -> int:
    import judge_models as jm
    from draw_audit import load

    from app.core import metrics as me
    rows, why = load()
    print("# 🔴🔴 무 보정 후보 시험 — D1 · D2(2-③)")
    print()
    print(f"- {why}")
    for r in rows:
        r["_t"] = triple_of(r["grid"])
    seasons = sorted({r["season"] for r in rows})
    order: list[dict] = []
    cand: dict[str, list[list[float]]] = {"B": [], "D1": [], "D2": []}
    picks: list[str] = []
    for s in seasons:
        train = [r for r in rows if r["season"] != s]
        test = [r for r in rows if r["season"] == s]
        if len(train) < 100 or not test:
            continue
        me.check_split(fit={x["season"] for x in train}, eval={s})
        p1 = d1_fit(train)
        k2 = d2_fit(train)
        picks.append(f"{s} → D1 " + " · ".join(
            f"{k} {v:+.3f}" for k, v in p1.items() if v) + f" / D2 ×{k2:.2f}")
        order += test
        cand["B"] += [list(r["_t"]) for r in test]
        cand["D1"] += [d1_apply(r["_t"], p1) for r in test]
        cand["D2"] += [triple_of(d2_apply(r["grid"], k2)) for r in test]
    hits = [r["hit"] for r in order]
    print("- 교차로 고른 보정")
    for one in picks:
        print(f"  · {one}")

    def score(p):
        lls = [me.logloss(x, h) for x, h in zip(p, hits, strict=True)]
        dirs = [bool(me.direction_hit(x, h))
                for x, h in zip(p, hits, strict=True)]
        said = me.bands([{"p": x, "hit": h}
                         for x, h in zip(p, hits, strict=True)], keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}

    base = score(cand["B"])
    err0, said0 = band_err(order, cand["B"])
    print()
    print(f"- **기준 B**(M1 격자) — 로그 손실 {base['ll']:.4f} · 방향 "
          f"{base['dir']:.2%} · 무 구간 오차 **{err0:.2%}** ({said0})")
    print()
    print("| 후보 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% | 짝지은 차이(95%)"
          " | 맥니마 p | 무 구간 오차 | 판정 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name in ("D1", "D2"):
        got = score(cand[name])
        err, said = band_err(order, cand[name])
        diff = me.paired(got["lls"], base["lls"])
        b = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if x and not y)
        c = sum(1 for x, y in zip(got["dirs"], base["dirs"], strict=True)
                if y and not x)
        pv = jm.binom_two_sided(b, c)
        ok, _box, why_r = jm.passes(
            diff=diff, dir_rate=got["dir"], base_dir=base["dir"], p_value=pv,
            bands=got["bands"], base_bands=base["bands"],
            size={"ll": base["ll"] - got["ll"],
                  "dir": got["dir"] - base["dir"],
                  "top20": got["bands"][0.20] - base["bands"][0.20]},
            rule="season")
        ok_err = err < err0
        cells = " / ".join(f"{got['bands'][f]:.1%}" for f in (0.30, 0.20, 0.10))
        print(f"| {name} | {len(hits)} | {got['ll']:.4f} | {got['dir']:.2%} | "
              f"{cells} | {diff['mean']:+.4f}"
              f"({diff['lo']:+.4f}~{diff['hi']:+.4f}) | {pv:.4f} | "
              f"**{err:.2%}**{' ✅' if ok_err else ' 🔴'} | "
              + ("✅ **채택**" if (ok and ok_err) else "🔴 탈락")
              + f" — {why_r}"
              + ("" if ok_err else " · 🔴 무 구간 오차가 안 줄었다") + " |")
        print(f"|  |  |  |  |  |  |  | {said} |  |")
    print()
    print("🔴 **규칙**: v2 (a)~(d) **그리고** 무 구간 오차 감소 — 둘 다여야 "
          "채택이다. 둘 다 탈락이면 **경로 그대로**(ρ 는 폐기 유지).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
