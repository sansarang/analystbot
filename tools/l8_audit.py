"""🔴🔴 **(나) L8 부호 조사** — 사용자 결정 2026-10-13(밤).

```
PYTHONPATH=. python tools/l8_audit.py
```

> B+L8 에서 확률이 **≥3%p 움직인 43경기** 표: 경기·팀·빠진 usual 선수(점수·사유)·
> 대신 들어온 선수(점수)·L8 값·확률 이동 방향·결과.
> 확인: **부호**(빠진 팀의 λ 가 내려가는가) · **로테이션/교체 출전**을 결장으로
> 세는지 · **대체 선수 점수 차감 방향** · `usual_xi` 가 **지난 시즌 선수**를 포함하는지.

🔴 재료·적합은 비교 도구와 **같은 것**을 쓴다(사본 금지) — `lineup_trial2` 의
   `load`·`tables_of`·`signals_of`·`fit_ortho`·`fit_g` 를 그대로 부른다.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KEYS = ("L8",)


def main(argv: list[str]) -> int:
    import lineup_trial2 as lt

    from app.core import lineupfix as lf
    from app.core import probfloor as pf
    rows, why = lt.load()
    print("# 🔴🔴 (나) L8 부호 조사")
    print()
    print(why)
    rows.sort(key=lambda r: r["utc"])
    tables = lt.tables_of(rows)
    lt.signals_of(rows, tables)
    live = [r for r in rows if r.get("raw")]
    seasons = sorted({r["season"] for r in live})
    picked: list[dict] = []
    for s in seasons:
        train = [r for r in live if r["season"] != s]
        test = [r for r in live if r["season"] == s]
        if len(train) < 100 or not test:
            continue
        ortho = lt.fit_ortho(train, KEYS)
        if not ortho:
            continue
        best = None
        for ridge in lt.GS:
            g = lt.fit_g(train, KEYS, ridge=ridge, ortho=ortho)
            val = lt._nll(g, train, KEYS, 0.0, ortho) / max(1, len(train))
            if best is None or val < best[0]:
                best = (val, g, ridge)
        g = best[1]
        for r in test:
            pair = []
            for which in ("raw", "raw_usual"):
                said, _w = lf.ortho({k: r[which][k] for k in KEYS
                                     if k in r[which]},
                                    axis0=r["axis0"], plate={"ortho": ortho})
                move = sum(float(g.get(k) or 0.0) * float(v)
                           for k, v in said.items())
                mk = pf.markets_of(pf.score_grid(
                    lam_home=float(r["lam"][0]) * math.exp(move),
                    lam_away=float(r["lam"][1]) * math.exp(-move), rho=0.0))
                pair.append((mk["home"], move))
            d = pair[0][0] - pair[1][0]
            if abs(d) >= 0.03:
                picked.append({**r, "g": float(g.get("L8") or 0.0),
                               "move": pair[0][1], "dp": d,
                               "table": tables.get((r["league"], r["month"]))})
    print()
    print(f"🔴 확률이 **≥3%p 움직인 경기 {len(picked)}건** · 계수 `g(L8)` 는 "
          f"시즌별로 {min(p['g'] for p in picked):+.3f}~"
          f"{max(p['g'] for p in picked):+.3f}")
    print()
    print("| 날짜 | 홈 vs 원정 | L8 | g·L8⊥ | 확률 이동 | 결과 | 홈 빠진(점수) | "
          "홈 들어온(점수) | 원정 빠진 | 원정 들어온 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    stat = {"표에 없는 대체": 0, "대체 총수": 0, "표에 없는 빠짐": 0,
            "빠짐 총수": 0, "직전 경기에 뛴 빠짐": 0}
    fit_sign = []
    for one in sorted(picked, key=lambda x: -abs(x["dp"]))[:60]:
        table = one["table"]
        value = dict(getattr(table, "value", None) or {})
        kind = dict(getattr(table, "kind", None) or {})

        def _show(ids, box=value) -> str:
            got = []
            for p in ids:
                if str(p) in box:
                    got.append(f"{str(p)[-4:]} {float(box[str(p)]):.2f}"
                               + ("" if kind.get(str(p)) == "공격" else "(뒷선)"))
                else:
                    got.append(f"{str(p)[-4:]} ⬜표없음")
            return ", ".join(got[:4]) or "—"

        cells = []
        for side in ("home", "away"):
            usual = list(one["usual"][side])
            today = list(one[f"{side}_ids"])
            gone = [p for p in usual if p not in set(today)]
            came = [p for p in today if p not in set(usual)]
            stat["빠짐 총수"] += len(gone)
            stat["대체 총수"] += len(came)
            stat["표에 없는 빠짐"] += sum(1 for p in gone if p not in value)
            stat["표에 없는 대체"] += sum(1 for p in came if p not in value)
            cells += [_show(gone), _show(came)]
        got_res = ("홈승" if one["hg"] > one["ag"]
                   else ("무" if one["hg"] == one["ag"] else "원정승"))
        fit_sign.append((float(one["raw"].get("L8") or 0.0),
                         int(one["hg"]) - int(one["ag"])))
        print(f"| {str(one['utc'])[:10]} | {one['home']} vs {one['away']} | "
              f"{float(one['raw'].get('L8') or 0.0):+.2f} | "
              f"{float(one['move']):+.4f} | "
              + ("홈 ↑" if one["dp"] > 0 else "홈 ↓")
              + f" {one['dp'] * 100:+.1f}%p | {got_res} "
                f"({one['hg']}-{one['ag']}) | " + " | ".join(cells) + " |")
    print()
    print("## 🔴 확인 넷")
    print()
    import statistics as stt
    xs = [a for a, _b in fit_sign]
    ys = [float(b) for _a, b in fit_sign]
    r_sign = (stt.correlation(xs, ys) if len(set(xs)) > 1 and len(set(ys)) > 1
              else float("nan"))
    print(f"1. **부호** — 계수 `g(L8)` 가 **양수**면 *\"홈이 더 많이 빠졌을 때 홈 λ 를"
          f" 올린다\"* 는 뜻이다. 적합이 고른 범위: "
          f"{min(p['g'] for p in picked):+.3f}~{max(p['g'] for p in picked):+.3f}"
          f" · 이 경기들에서 L8 과 실제 득실차의 상관 **{r_sign:+.2f}**")
    print(f"2. **대체 선수 점수** — 들어온 선수 {stat['대체 총수']}명 중 "
          f"**{stat['표에 없는 대체']}명({stat['표에 없는 대체'] / max(1, stat['대체 총수']):.0%})"
          f"이 가치 표에 없다** → `_sum` 이 그들을 **0 으로** 센다(그만큼 L8 이 "
          f"커진다)")
    print(f"3. **빠진 선수 점수** — 빠진 선수 {stat['빠짐 총수']}명 중 "
          f"{stat['표에 없는 빠짐']}명이 표에 없다")
    # ── 🔴 4. **로테이션인가** — 빠진 선수가 그 팀 **다음 경기**에 선발로 돌아오나
    #    ⚠️ 이것은 **사후 진단**이다(다음 경기를 본다) — 신호로는 쓸 수 없다(L1 누설).
    nxt: dict[str, list[dict]] = {}
    for r in sorted(live, key=lambda x: x["utc"]):
        for side in ("home", "away"):
            nxt.setdefault(r[side], []).append({"utc": r["utc"],
                                                "xi": r[f"{side}_ids"]})
    back = gone_all = 0
    for one in picked:
        for side in ("home", "away"):
            usual = list(one["usual"][side])
            today = set(one[f"{side}_ids"])
            gone = [p for p in usual if p not in today]
            said = [x for x in nxt.get(one[side], [])
                    if x["utc"] > one["utc"]]
            if not said:
                continue
            after = set(said[0]["xi"])
            gone_all += len(gone)
            back += sum(1 for p in gone if p in after)
    print(f"4. **로테이션** — 그 경기에서 빠진 선수 {gone_all}명 중 "
          f"**{back}명({back / max(1, gone_all):.0%})이 그 팀 다음 경기에 "
          f"선발로 돌아왔다** → 그만큼은 **부상 결장이 아니라 로테이션**이다"
          f"(⚠️ 사후 진단이다 — 신호로는 쓸 수 없다 · L1)")
    # ── 🔴 5. 표본 **전체**에서 L8 과 득실차의 상관(43경기만 보면 안 된다)
    xa = [float(r["raw"].get("L8") or 0.0) for r in live if "L8" in r["raw"]]
    ya = [float(r["hg"] - r["ag"]) for r in live if "L8" in r["raw"]]
    r_all = (stt.correlation(xa, ya) if len(set(xa)) > 1 else float("nan"))
    print(f"5. **표본 전체 상관**(L8 ↔ 홈 득실차 · {len(xa)}경기) — "
          f"**{r_all:+.3f}** · ⚠️ 적합이 양수 계수를 고른 것은 이 수와 "
          f"**부호가 같다면** 자료 때문이고, 다르면 **적합이 틀린 것**이다")
    # ── 🔴 6. 표에 없는 선수를 **평균으로** 메우면 L8 이 어떻게 바뀌나(PL2)
    fixed_x: list[float] = []
    for r in [x for x in live if "L8" in x["raw"]]:   # 🔴 같은 표본이어야 한다
        table = tables.get((r["league"], r["month"]))
        value = dict(getattr(table, "value", None) or {})
        kind = dict(getattr(table, "kind", None) or {})
        front = [v for k, v in value.items() if kind.get(k) == "공격"]
        mid = (sum(front) / len(front)) if front else 0.0

        def _sum2(ids, value=value, kind=kind, mid=mid) -> float:
            got = 0.0
            for p in ids:
                if str(p) in value:
                    if kind.get(str(p)) == "공격":
                        got += float(value[str(p)])
                else:
                    got += mid          # 🔴 **PL2** — 모르면 0 이 아니라 평균
            return got

        said = 0.0
        for side, sign in (("home", 1.0), ("away", -1.0)):
            usual = list(r["usual"][side])
            today = list(r[f"{side}_ids"])
            gone = [p for p in usual if p not in set(today)]
            came = [p for p in today if p not in set(usual)]
            said += sign * (_sum2(gone) - _sum2(came))
        fixed_x.append(said)
    r_fix = (stt.correlation(fixed_x, ya) if len(set(fixed_x)) > 1
             else float("nan"))
    print(f"6. **표에 없는 선수를 평균으로 메우면**(PL2) — 같은 표본 상관 "
          f"**{r_fix:+.3f}**(지금 {r_all:+.3f}) · L8 평균 "
          f"{stt.fmean(fixed_x):+.3f}(지금 {stt.fmean(xa):+.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
