"""🔴🔴 **§4-1 S2-Elo — 잔류율로 시즌 이월**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/elo_carry_trial.py
```

> 시즌 시작 시 `Elo_new = 리그 평균 + r·(Elo_old − 리그 평균)`,
> `r = r0 + r1·retention`(0~1 로 자름) · 승격팀은 **리그 하위 25%** 에서 시작 +
> 지난 시즌 하위 리그 성적 비례 보정 후보(`r_p`).
> 비교: **현행 이월(고정 r)** vs **잔류율 이월** · 적합: 시즌 교차.

🔴 **현행이 무엇인가** — 백필의 Elo 는 시즌 경계에서 **아무 것도 하지 않는다**
   (`r = 1`). 그것이 기준이다.
⚠️ **표본의 한계** — 이 704경기에는 **리그마다 시즌 경계가 하나**뿐이다
   (K1 2025→2026 · J1 2026→2026/27). 그래서 시즌 교차는 **리그 하나를 빼는 방식**
   (leave-one-league-out)이고, 그 사실을 보고가 **매번** 적는다.
🔴 승격팀의 `r_p` 는 **지난 시즌 하위 리그 자료가 없으므로**(J2·K2 덤프 없음)
   *"하위 25% 에서 시작"* 까지만 시험한다 — 비례 보정은 **안 짓는다**(#4).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 Elo 굴림 — 백필과 **같은 수**(사본 금지: 그 값과 다르면 비교가 깨진다)
KFACT = 20.0
START = 1500.0

#: 🔴 `(r0, r1)` 격자 — 교차가 고른다
GRID = tuple((r0, r1) for r0 in (0.4, 0.6, 0.8, 1.0)
             for r1 in (0.0, 0.2, 0.4))


def load() -> tuple[list[dict], str]:
    """🔴 경기 순서 + 결과 + **잔류율**(없으면 None)."""
    from seasonfix_trial import load as _load
    rows, why = _load()
    return rows, why


def run(rows: list[dict], *, r0: float | None, r1: float = 0.0,
        promoted_low: bool = False) -> tuple[list[list[float]], list[int]]:
    """🔴 Elo 를 굴리며 **바닥 승무패**를 낸다. `r0=None` 이면 **현행**(이월 그대로)."""
    from app.core import probfloor as pf
    elo: dict[str, float] = {}
    season_of: dict[str, str] = {}
    out: list[list[float]] = []
    hits: list[int] = []
    for r in sorted(rows, key=lambda x: str(x["day"])):
        league = str(r["league"])
        for side in ("home", "away"):
            team = str(r[side])
            was = season_of.get(team)
            if was is None:
                # 🔴 처음 보는 팀 — 승격 판에서는 **리그 하위 25%** 에서 시작
                if promoted_low and elo:
                    said = sorted(elo.values())
                    elo[team] = said[max(0, int(len(said) * 0.25) - 1)]
                else:
                    elo.setdefault(team, START)
            elif was != str(r["season"]) and r0 is not None:
                # 🔴 **시즌 경계** — 잔류율로 리그 평균 쪽으로 당긴다
                mean = st.fmean(elo.values()) if elo else START
                ret = r.get(f"ret_{side}")
                rate = (float(r0) + float(r1) * float(ret)) if ret is not None \
                    else float(r0)
                rate = max(0.0, min(1.0, rate))
                elo[team] = mean + rate * (elo.get(team, START) - mean)
            season_of[team] = str(r["season"])
        dr = elo[str(r["home"])] - elo[str(r["away"])]
        got, _why = pf.floor_of(kind=league, dr=dr)
        if got is None:
            continue
        out.append(list(got))
        hits.append(int(r["hit"]))
        exp_h = 1.0 / (1.0 + 10 ** (-dr / 400.0))
        res = (1.0 if r["hg"] > r["ag"]
               else (0.5 if r["hg"] == r["ag"] else 0.0))
        elo[str(r["home"])] += KFACT * (res - exp_h)
        elo[str(r["away"])] -= KFACT * (res - exp_h)
    return out, hits


def main(argv: list[str]) -> int:
    import judge_models as jm

    from app.core import metrics as me
    rows, why = load()
    print("# 🔴🔴 §4-1 S2-Elo — 잔류율로 시즌 이월")
    print()
    print(why)
    leagues = sorted({r["league"] for r in rows})
    print(f"리그 {leagues} · 시즌 경계는 **리그마다 하나**다"
          f"(교차 = leave-one-league-out)")
    print()

    def score(p, h) -> dict:
        lls = [me.logloss(pi, hi) for pi, hi in zip(p, h, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(p, h, strict=True)]
        said = me.bands([{"p": pi, "hit": hi}
                         for pi, hi in zip(p, h, strict=True)], keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}
    # 🔴 교차 — 한 리그에서 `(r0,r1)` 을 고르고 **다른 리그**에서 잰다
    base_p: list[list[float]] = []
    cand_p: list[list[float]] = []
    hits: list[int] = []
    picked: list[str] = []
    for league in leagues:
        train = [r for r in rows if r["league"] != league]
        test = [r for r in rows if r["league"] == league]
        if not train or not test:
            continue
        best = None
        for r0, r1 in GRID:
            p, h = run(train, r0=r0, r1=r1)
            if not h:
                continue
            got = score(p, h)
            if best is None or got["ll"] < best[0]:
                best = (got["ll"], r0, r1)
        picked.append(f"{league} ← r0 **{best[1]:g}** · r1 **{best[2]:g}**"
                      f"(훈련 로그 손실 {best[0]:.4f})")
        p0, h0 = run(test, r0=None)
        p1, h1 = run(test, r0=best[1], r1=best[2])
        n = min(len(h0), len(h1))
        base_p += p0[:n]
        cand_p += p1[:n]
        hits += h0[:n]
    print("- 교차로 고른 계수 — " + " · ".join(picked))
    print()
    base = score(base_p, hits)
    cand = score(cand_p, hits)
    diff = me.paired(cand["lls"], base["lls"])
    b = sum(1 for x, y in zip(cand["dirs"], base["dirs"], strict=True)
            if x and not y)
    c = sum(1 for x, y in zip(cand["dirs"], base["dirs"], strict=True)
            if y and not x)
    pv = jm.binom_two_sided(b, c)
    ok, _box, said = jm.passes(
        diff=diff, dir_rate=cand["dir"], base_dir=base["dir"], p_value=pv,
        bands=cand["bands"], base_bands=base["bands"],
        size={"ll": base["ll"] - cand["ll"], "dir": cand["dir"] - base["dir"],
              "top20": cand["bands"][0.20] - base["bands"][0.20]},
        rule="season")
    print("| 판 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% | 짝지은 차이(95%) |")
    print("|---|---|---|---|---|---|")
    for name, got in (("현행 이월(r=1)", base), ("잔류율 이월", cand)):
        cells = " / ".join(f"{got['bands'][f]:.2%}" for f in (0.30, 0.20, 0.10))
        print(f"| {name} | {len(hits)} | **{got['ll']:.4f}** | "
              f"{got['dir']:.2%} | {cells} | "
              + (f"{diff['mean']:+.4f} ({diff['lo']:+.4f}~{diff['hi']:+.4f}) |"
                 if name != "현행 이월(r=1)" else " — |"))
    print()
    print(("✅ **채택** " if ok else "🔴 **탈락** ") + said)
    # 🔴 승격팀 시작점 판(하위 25%)도 **따로** 본다
    p2: list[list[float]] = []
    h2: list[int] = []
    for league in leagues:
        test = [r for r in rows if r["league"] == league]
        p, h = run(test, r0=None, promoted_low=True)
        p2 += p
        h2 += h
    got2 = score(p2, h2)
    print()
    print(f"- **승격팀 하위 25% 시작** 판 — 로그 손실 {got2['ll']:.4f} · 방향 "
          f"{got2['dir']:.2%}(현행 {base['ll']:.4f} · {base['dir']:.2%})")
    print("  ⚠️ 이 판은 **처음 보는 팀**에만 다르다 — 그 수가 적으면 차이도 작다"
          "(지난 시즌 하위 리그 자료가 없어 **비례 보정은 안 지었다**).")
    print()
    print("🔴🔴 **판정 — " + ("채택: 잔류율 이월" if ok else "현행 유지") + "**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
