"""🔴🔴 **§4-2 S2-M1 시험 — 시즌 초 수축**(통합 지시서 2026-10-13 밤).

```
PYTHONPATH=. python tools/seasonfix_trial.py
```

판 — `B`(M1 그대로) vs `B+seasonfix`(k 는 **시즌 교차**로 고른다).
판정은 **실행 전 커밋된** `judge_models.passes(rule="season")`((a)~(d)).

🔴 재료는 이미 적어 둔 것이다(다시 받지 않는다): `var/judge/replay_big2.json`
   (M1 의 **λ**·결과) · `var/judge/lineup_rows2.json` + `events.json`(출전 분 →
   잔류율). 🔴 S1 이 **탈락**했으므로 기준은 **B** 그대로다(§7 전진 선택).
🔴 **L1** — 경기 수·잔류율은 그 경기 **앞**만 본다(문은 `before_as_of` 하나).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 `k` 격자 — 시즌 교차가 고른다(손값 금지)
KS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)

#: 🔴 시즌 초의 뜻(보고용) — 이번 시즌 경기 수 ≤ 이 수
EARLY = 6


def load() -> tuple[list[dict], str]:
    """🔴 λ·결과 + **이번 시즌 경기 수**·**잔류율** 을 한 꼴로 잇는다."""
    from app.core import season as se
    from app.core.ratings import retention as rt
    back = json.loads((ROOT / "var/judge/replay_big2.json").read_text(
        encoding="utf-8"))
    rows = json.loads((ROOT / "var/judge/lineup_rows2.json").read_text(
        encoding="utf-8"))
    ev = json.loads((ROOT / "var/judge/events.json").read_text(
        encoding="utf-8"))
    # 🔴 출전 분 줄(잔류율 재료) — `season_prep` 과 **같은 꼴**이다
    mins: list[dict] = []
    for r in rows:
        one = dict(ev.get(f"{r['utc']}|{r['home']}|{r['away']}") or {})
        pstat = dict(one.get("pstat") or {})
        side = {}
        for key in ("home", "away"):
            ids = set(r[f"{key}_ids"]) | set(r[f"{key}_bench"])
            side[f"{key}_minutes"] = {
                p: float(dict(v).get("minutes_played") or 0.0)
                for p, v in pstat.items() if str(p) in ids}
        mins.append({"utc": r["utc"], "league": r["league"],
                     "home": r["home"], "away": r["away"], **side})
    got: list[dict] = []
    seen: dict[str, list[dict]] = {}
    gone = {"λ 없다": 0, "시즌 모른다": 0}
    for r in sorted(back, key=lambda x: str(x.get("day"))):
        if not r.get("lam"):
            gone["λ 없다"] += 1
            continue
        league = str(r.get("league") or "")
        at = datetime.fromisoformat(f"{r['day']}T12:00:00+00:00")
        season, _w = se.id_of(league=league, when=at)
        if not season:
            gone["시즌 모른다"] += 1
            continue
        box = seen.setdefault(league, [])
        games = {}
        for side in ("home", "away"):
            team = str(r[side])
            games[side] = sum(
                1 for x in box
                if x["season"] == season
                and team in (x["home"], x["away"]))
        rets = {}
        for side in ("home", "away"):
            val, _w2 = rt.of(mins, team=str(r[side]), as_of=at, league=league)
            rets[side] = val
        said = [v for v in rets.values() if v is not None]
        got.append({**r, "season": season, "at": at,
                    "games": min(games["home"], games["away"]),
                    "games_home": games["home"], "games_away": games["away"],
                    "retention": (sum(said) / len(said)) if said else None,
                    "ret_home": rets["home"], "ret_away": rets["away"]})
        box.append({"season": season, "home": str(r["home"]),
                    "away": str(r["away"])})
    why = (f"이은 경기 **{len(got)}건** · 버린 것 — "
           + " · ".join(f"{k} {v}건" for k, v in gone.items())
           + f" · 잔류율을 못 쟨 경기 "
             f"{sum(1 for x in got if x['retention'] is None)}건")
    return got, why


def probs_of(rows: list[dict], *, k: float | None) -> list[list[float]]:
    """🔴 그 판의 확률 — `k` 가 `None` 이면 **B**(수축 없음)."""
    from app.core import probfloor as pf
    from app.core import seasonfix as sf
    out: list[list[float]] = []
    for r in rows:
        lam = {"home": float(r["lam"][0]), "away": float(r["lam"][1])}
        if k is not None and r["retention"] is not None:
            lam, _why = sf.bend(lam, games=int(r["games"]),
                                mean_retention=float(r["retention"]),
                                plate={"k": float(k)})
        mk = pf.markets_of(pf.score_grid(lam_home=lam["home"],
                                         lam_away=lam["away"], rho=0.0))
        out.append([mk["home"], mk["draw"], mk["away"]])
    return out


def main(argv: list[str]) -> int:
    import judge_models as jm

    from app.core import metrics as me
    rows, why = load()
    print("# 🔴🔴 §4-2 S2-M1 — 시즌 초 수축(seasonfix)")
    print()
    print(why)
    seasons = sorted({r["season"] for r in rows})
    early = [r for r in rows if r["games"] <= EARLY]
    print(f"시즌 {len(seasons)}개 — {' · '.join(seasons)} · "
          f"시즌 초(≤{EARLY}경기) **{len(early)}건**")
    print()

    def score(p: list[list[float]], h: list[int]) -> dict:
        lls = [me.logloss(pi, hi) for pi, hi in zip(p, h, strict=True)]
        dirs = [bool(me.direction_hit(pi, hi))
                for pi, hi in zip(p, h, strict=True)]
        said = me.bands([{"p": pi, "hit": hi}
                         for pi, hi in zip(p, h, strict=True)], keys=("p",))
        return {"ll": sum(lls) / len(lls), "lls": lls,
                "dir": sum(dirs) / len(dirs), "dirs": dirs,
                "bands": {f: said[f]["p"]["rate"] for f in said}}

    # 🔴 **시즌 교차** — 한 시즌을 빼고 `k` 를 고른 뒤 그 시즌에서 잰다
    probs: list[list[float]] = []
    base_p: list[list[float]] = []
    hits: list[int] = []
    picked: list[str] = []
    for s in seasons:
        train = [r for r in rows if r["season"] != s]
        test = [r for r in rows if r["season"] == s]
        if len(train) < 100 or not test:
            continue
        h_tr = [int(r["hit"]) for r in train]
        best = None
        for k in KS:
            got = score(probs_of(train, k=k), h_tr)
            if best is None or got["ll"] < best[0]:
                best = (got["ll"], k)
        picked.append(f"{s} → k **{best[1]:g}**(훈련 로그 손실 {best[0]:.4f})")
        probs += probs_of(test, k=best[1])
        base_p += probs_of(test, k=None)
        hits += [int(r["hit"]) for r in test]
    print("- 시즌 교차로 고른 `k` — " + " · ".join(picked))
    # 🔴 **SF2** — 운영에 깔린 판이 있나(없으면 운영은 수축하지 않는다)
    from app.core import seasonfix as sf0
    for league in sorted({r["league"] for r in rows}):
        at = max(r["at"] for r in rows if r["league"] == league)
        got_plate, why_plate = sf0.plate_of(league=league, as_of=at)
        print(f"- **{league}** 운영 판 — "
              + (f"k {got_plate.get('k')} · {why_plate}" if got_plate
                 else why_plate))
    print()
    base = score(base_p, hits)
    cand = score(probs, hits)
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
    print("| 판 | 경기 | 로그 손실 | 방향 | 상위 30/20/10% | 짝지은 차이(95%) |"
          " 맥니마 p |")
    print("|---|---|---|---|---|---|---|")
    for name, got in (("B", base), ("B+seasonfix", cand)):
        cells = " / ".join(f"{got['bands'][f]:.2%}" for f in (0.30, 0.20, 0.10))
        print(f"| {name} | {len(hits)} | **{got['ll']:.4f}** | "
              f"{got['dir']:.2%} | {cells} | "
              + (f"{diff['mean']:+.4f} ({diff['lo']:+.4f}~{diff['hi']:+.4f})"
                 f" | {pv:.4f} |" if name != "B" else " — | — |"))
    print()
    print(("✅ **채택** " if ok else "🔴 **탈락** ") + said)
    # 🔴 시즌 초만 따로(이 수정이 노리는 구간)
    idx = [i for i, r in enumerate(
        [r for s in seasons for r in rows if r["season"] == s]) if False]
    del idx
    print()
    print("## 🔴 시즌 초(≤6경기)만")
    print()
    e_rows = [r for r in rows if r["games"] <= EARLY]
    e_h = [int(r["hit"]) for r in e_rows]
    if e_rows:
        e_base = score(probs_of(e_rows, k=None), e_h)
        k_all = float(picked[0].split("k **")[1].split("**")[0]) if picked \
            else 0.0
        e_cand = score(probs_of(e_rows, k=k_all), e_h)
        print(f"| 판 | 경기 | 로그 손실 | 방향 |")
        print("|---|---|---|---|")
        print(f"| B | {len(e_h)} | {e_base['ll']:.4f} | {e_base['dir']:.2%} |")
        print(f"| B+seasonfix(k {k_all:g}) | {len(e_h)} | {e_cand['ll']:.4f} |"
              f" {e_cand['dir']:.2%} |")
        print()
        print("⚠️ 이 칸의 `k` 는 **첫 시즌 교차가 고른 값**이다(구간을 보려는 표 ·"
              " 판정은 위 표가 한다).")
    print()
    print("🔴🔴 **판정 — " + ("채택: B+seasonfix" if ok else "B 유지") + "**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
