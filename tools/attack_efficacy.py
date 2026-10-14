"""🔴🔴 **공격 계층 실효**(후속 지시 2026-10-14g §1·§2).

```
PYTHONPATH=. python tools/attack_efficacy.py
```

🔴 같은 백필에서 **세 판**을 비교한다 —
   (가) 문턱만(단폴 0.88 · 다리 0.90)
   (나) 문턱 + 공격(**살아남음만**)
   (다) 문턱 + 공격(**살아남음 + 약해짐**)
🔴 공격은 `core/attack.of` **그 함수**다(사본 금지). 재료는 재료 실은 덤프
   (`var/judge/atk_*.json`)에서 **그 경기 앞**의 것만 쓴다(C11 · 누설 금지).
🔴 규칙(T12·축3)은 `core/goals` 의 **실제 함수**로 다시 돌린다 — 백필이 규칙을
   덤프에 안 적었으므로 골 목록으로 **그 함수를 다시 부른다**(사본 금지).
⚠️ 덤프에 **없는 재료**는 그 공격을 **보류**로 둔다(J1 시장 · E1·E2 결장) —
   없는 것을 있다고 치지 않는다(#3).
"""
from __future__ import annotations

import json
import math
import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

CUT_SINGLE = 0.88
CUT_LEG = 0.90
BETA = 0.25
W = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}
BACK = 10


def rows_all() -> list[dict]:
    out, seen = [], set()
    for path in sorted((ROOT / "var/judge").glob("atk_*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")):
            if not isinstance(r, dict) or not r.get("extra") or not r.get("lam"):
                continue
            key = (r.get("league"), r.get("day"), r.get("home"), r.get("away"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: (str(r.get("league")), str(r.get("day"))))
    return out


def shaped(rows: list[dict], team: str) -> list[dict]:
    """🔴 `core/goals.profile_of` 가 받는 꼴로 되돌린다(그 함수를 그대로 쓴다)."""
    out = []
    for r in rows:
        mine = str(r.get("home")) == team
        out.append({"home_name": str(r.get("home")),
                    "away_name": str(r.get("away")), "mine_home": mine,
                    "goals": list((r.get("extra") or {}).get("goals") or []),
                    "stats": {}})
    return out


def t12_of(rows: list[dict], home: str, away: str) -> str:
    """🔴 그 경기 앞 경기들로 **T12 발동**을 다시 센다(실제 규칙 함수)."""
    from app.core import goals as _g
    said = ""
    for side, team in (("home", home), ("away", away)):
        past = rows[-BACK:]
        if len(past) < 3:
            continue
        prof = _g.profile_of(side, shaped(past, team))
        fired = _g.fire(prof, prof, rest={})
        for f in fired:
            if f.rule == "T12" and not f.watch_only and f.side == side:
                said += f"{side}:{team} "
    return said.strip()


def box_of(r: dict, prior: dict, scales: dict,
           ppg: dict | None = None) -> dict:
    """🔴 그 경기의 공격 재료 — 덤프에 있는 것만(없으면 빈 칸)."""
    lg = str(r.get("league"))
    home, away = str(r.get("home")), str(r.get("away"))
    gaps = {k: (None if v is None else float(v))
            for k, v in dict(r.get("gaps") or {}).items() if k in W}
    sigma = sum(W[k] * (v or 0.0) for k, v in gaps.items())
    lam = [float(x) for x in r["lam"][:2]]
    tilt = math.log(max(lam[0], 1e-9) / max(lam[1], 1e-9))
    home_part = tilt - 2 * BETA * sigma
    mul_h = math.sqrt(math.exp(home_part))         # 🔴 홈/원정 몫을 반반으로 가른다
    mul_a = 1.0 / mul_h
    base = [lam[0] / (mul_h * math.exp(BETA * sigma)),
            lam[1] / (mul_a * math.exp(-BETA * sigma))]
    ours = (r.get("ours") or [None, None, None])
    floor = r.get("floor")
    past_h = prior.get((lg, home)) or []
    past_a = prior.get((lg, away)) or []
    said_t12 = t12_of(past_h + past_a, home, away) if (past_h and past_a) else ""
    n_form = min(len(past_h), len(past_a))
    return {"pick": max(range(3), key=lambda i: float(ours[i])) if ours[0]
            is not None else 0,
            "ours": [float(x) for x in ours] if ours[0] is not None else None,
            "gaps": gaps, "mul": mul_h, "league_mul": mul_h,
            "away_mul": mul_a, "team_mul": 0.0, "base": base,
            "elo": [float(x) for x in floor] if floor else None,
            "market": None, "gaps_missing": [], "band_dev": None,
            "neutral": False, "t12": said_t12, "form_games": n_form,
            "xi_state": "확정", "absence_src": "A", "key_missing": [],
            "axis_why": {}, "axis0_sd": (scales.get(lg) or {}).get("axis0"),
            "discipline": True, "league_real": 1.20,
            # 🔴 H1 — 그 시즌 **누적** 승점/경기(그 경기 앞까지 · 누설 금지)
            "ppg": dict(ppg or {})}


def lines_of(lam: list[float], hg: int, ag: int) -> list[tuple]:
    from app.core import probfloor as _pf
    from app.core import sim as _sim
    mk = _pf.markets_of(_pf.score_grid(lam_home=lam[0], lam_away=lam[1]))
    out = _sim.run(lam[0], lam[1])
    d, tot = hg - ag, hg + ag
    got = [("홈 승", out.home, d > 0), ("원정 승", out.away, d < 0),
           ("무", out.draw, d == 0)]
    for key, ok in (("home-0.5", d > 0), ("home+0.5", d >= 0),
                    ("home+1.5", d > -2), ("away+0.5", d <= 0),
                    ("away+1.5", d < 2)):
        p = dict(mk.get("ah") or {}).get(key)
        if p is not None:
            got.append((f"핸디 {key}", float(p), ok))
    for x in (1.5, 2.5, 3.5):
        p = dict(mk.get("over") or {}).get(x)
        if p is not None:
            got.append((f"오버 {x}", float(p), tot > x))
            got.append((f"언더 {x}", 1.0 - float(p), tot < x))
    return got


def ci(a: list[int], b: list[int]) -> tuple[float, float, float]:
    if not a or not b:
        return (float("nan"),) * 3
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    se = math.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
    return pa - pb, pa - pb - 1.96 * se, pa - pb + 1.96 * se


def main() -> int:
    import yaml

    from app.core import attack as atk

    scales = {}
    for path in (ROOT / "data/axis_scale").glob("*.yaml"):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scales[path.stem.replace("_", ":", 1)] = {
            k: float((v or {}).get("sd") or 0.0) for k, v in got.items()}

    rows = rows_all()
    prior: dict[tuple, list] = {}
    pts: dict[tuple, dict] = {}
    out: list[dict] = []
    for r in rows:
        lg = str(r.get("league"))
        se = str(r.get("season"))
        home, away = str(r.get("home")), str(r.get("away"))
        said_ppg = {}
        for who, team in (("home", home), ("away", away)):
            one = pts.get((lg, se, team))
            if one and one["n"] >= 5:
                said_ppg[who] = one["p"] / one["n"]
        if r.get("ours") and r.get("hit") is not None:
            box = box_of(r, prior, scales, said_ppg)
            got = atk.of(box)
            lam = atk.lam_of(box, got)
            # 🔴🔴 **보드 줄만**(후속 지시 2026-10-14h §1)
            from app.core import picks as _pk
            want = set(_pk.BOARD_COMMON)
            got_l = [x for x in lines_of(lam, int(r["hg"]), int(r["ag"]))
                     if x[0] in want]
            got_b = [x for x in lines_of([float(x) for x in r["lam"][:2]],
                                         int(r["hg"]), int(r["ag"]))
                     if x[0] in want]
            if not got_l or not got_b:
                for key in ((lg, str(r.get("home"))),
                            (lg, str(r.get("away")))):
                    prior.setdefault(key, []).append(r)
                continue
            best = max(got_l, key=lambda x: x[1])
            base_best = max(got_b, key=lambda x: x[1])
            out.append({"day": str(r.get("day")), "league": lg,
                        "verdict": got.verdict(),
                        "broken": [s.key for s in got.broken()],
                        "p": best[1], "ok": bool(best[2]), "line": best[0],
                        "p0": base_best[1], "ok0": bool(base_best[2]),
                        "line0": base_best[0],
                        # 🔴 H1 단독 시험용 — 그 경기에서 H1 이 깨졌나
                        "h1": "H1" in [s.key for s in got.broken()],
                        "fam": ("승무패" if base_best[0] in ("홈 승", "무",
                                                             "원정 승")
                                else ("핸디" if base_best[0].startswith("핸디")
                                      else "오버·언더"))})
        hg, ag = int(r["hg"]), int(r["ag"])
        for team, mine_home in ((home, True), (away, False)):
            prior.setdefault((lg, team), []).append(r)
            got_p = (3 if ((hg > ag) == mine_home and hg != ag)
                     else (1 if hg == ag else 0))
            one = pts.setdefault((lg, se, team), {"p": 0, "n": 0})
            one["p"] += got_p
            one["n"] += 1

    print(f"# 🔴🔴 공격 계층 실효 — 재료 실은 덤프 **{len(out)}경기**")
    print()
    from collections import Counter
    print("- 판정 분포 — " + " · ".join(
        f"{k} {v}" for k, v in Counter(x["verdict"] for x in out).items()))
    print("- 깨뜨린 변수 — " + (" · ".join(
        f"{k} {v}" for k, v in Counter(
            k for x in out for k in x["broken"]).most_common()) or "없다"))
    print()
    plates = {
        "(가) 문턱만": [x for x in out if x["p0"] >= CUT_SINGLE],
        "(나) 문턱+공격(살아남음)": [x for x in out if x["p"] >= CUT_SINGLE
                                 and x["verdict"] == "살아남음"],
        "(다) 문턱+공격(살아남음+약해짐)": [x for x in out if x["p"] >= CUT_SINGLE
                                      and x["verdict"] in ("살아남음",
                                                           "약해짐")],
    }
    days = len({x["day"] for x in out}) or 1
    print("| 판 | 단폴 수 | 적중 | 하루 | (가) 대비 차 | 95% 구간 |")
    print("|---|---|---|---|---|---|")
    base_ok = [int(x["ok0"]) for x in plates["(가) 문턱만"]]
    for name, part in plates.items():
        if not part:
            print(f"| {name} | 0 | ⬜ | 0.0 | ⬜ | ⬜ |")
            continue
        ok = [int(x["ok"] if name != "(가) 문턱만" else x["ok0"])
              for x in part]
        d, lo, hi = ci(ok, base_ok)
        print(f"| **{name}** | {len(part)} | **{100*sum(ok)/len(ok):.1f}%** | "
              f"{len(part)/days:.2f} | "
              + ("—" if name.startswith("(가)")
                 else f"**{100*d:+.1f}%p**")
              + " | " + ("—" if name.startswith("(가)")
                         else f"[{100*lo:+.1f}, {100*hi:+.1f}]") + " |")
    # ── §2 **H1 단독 시험** — (가) vs (라) H1 깨짐 줄 제외 ──────────
    print()
    print("| 판 | 단폴 수 | 적중 | 하루 | (가) 대비 | 95% 구간 |")
    print("|---|---|---|---|---|---|")
    base = [x for x in out if x["p0"] >= CUT_SINGLE]
    la = [x for x in base if not x["h1"]]
    for name, part, key in (("(가) 문턱만", base, "ok0"),
                            ("(라) 문턱 + H1 깨짐 제외", la, "ok0")):
        ok = [int(x[key]) for x in part]
        d, lo, hi = ci(ok, [int(x["ok0"]) for x in base])
        print(f"| **{name}** | {len(part)} | **{100*sum(ok)/len(ok):.1f}%** | "
              f"{len(part)/days:.2f} | "
              + ("—" if name.startswith("(가)") else f"**{100*d:+.1f}%p**")
              + " | " + ("—" if name.startswith("(가)")
                         else f"[{100*lo:+.1f}, {100*hi:+.1f}]") + " |")
    print()
    print("| 줄 종류 | (가) 수 | (가) 적중 | (라) 수 | (라) 적중 | 차이 "
          "| 95% 구간 |")
    print("|---|---|---|---|---|---|---|")
    for fam in ("승무패", "핸디", "오버·언더"):
        a = [int(x["ok0"]) for x in base if x["fam"] == fam]
        b = [int(x["ok0"]) for x in la if x["fam"] == fam]
        if len(a) < 10:
            print(f"| {fam} | {len(a)} | ⬜ | {len(b)} | ⬜ | ⬜ | 표본 부족 |")
            continue
        d, lo, hi = ci(b, a)
        print(f"| {fam} | {len(a)} | {100*sum(a)/len(a):.1f}% | {len(b)} | "
              f"{100*sum(b)/len(b):.1f}% | **{100*d:+.1f}%p** | "
              f"[{100*lo:+.1f}, {100*hi:+.1f}] |")
    # 🔴 H1 이 깨뜨린 줄의 **실제 적중률**
    gone_h1 = [x for x in base if x["h1"]]
    if gone_h1:
        print()
        print(f"- H1 이 뺀 줄 **{len(gone_h1)}개** 의 실제 적중률 — "
              f"**{100*sum(1 for x in gone_h1 if x['ok0'])/len(gone_h1):.1f}%**"
              f"(남긴 줄 {100*sum(1 for x in la if x['ok0'])/max(1,len(la)):.1f}%)")

    # 🔴 공격으로 **빠진 줄**의 실제 적중률(공격이 틀린 결론을 걸렀나)
    gone = [x for x in out if x["p0"] >= CUT_SINGLE
            and not (x["p"] >= CUT_SINGLE and x["verdict"] == "살아남음")]
    print()
    if gone:
        print(f"- 공격이 **뺀 줄 {len(gone)}개** 의 실제 적중률 — "
              f"**{100*sum(1 for x in gone if x['ok0'])/len(gone):.1f}%**"
              f"(남긴 줄 {100*sum(1 for x in plates['(나) 문턱+공격(살아남음)'] if x['ok'])/max(1,len(plates['(나) 문턱+공격(살아남음)'])):.1f}%)")
    else:
        print("- 공격이 뺀 줄이 **없다**")
    # ── §2 약해짐 vs 살아남음 ──────────────────────────────────────
    print()
    print("| 판정 | 단폴 수 | 적중 | 살아남음 대비 | 95% 구간 |")
    print("|---|---|---|---|---|")
    keep = [int(x["ok"]) for x in out
            if x["p"] >= CUT_SINGLE and x["verdict"] == "살아남음"]
    for name in ("살아남음", "약해짐", "무너짐"):
        part = [int(x["ok"]) for x in out
                if x["p"] >= CUT_SINGLE and x["verdict"] == name]
        if not part:
            print(f"| {name} | 0 | ⬜ | ⬜ | ⬜ |")
            continue
        d, lo, hi = ci(part, keep)
        print(f"| **{name}** | {len(part)} | {100*sum(part)/len(part):.1f}% | "
              + ("—" if name == "살아남음" else f"{100*d:+.1f}%p")
              + " | " + ("—" if name == "살아남음"
                         else f"[{100*lo:+.1f}, {100*hi:+.1f}]") + " |")
    # ── 다폴 ────────────────────────────────────────────────────
    print()
    print("| 판 | 2폴 묶음 | 2폴 적중 | 3폴 묶음 | 3폴 적중 |")
    print("|---|---|---|---|---|")
    for name, part in plates.items():
        by_day: dict[str, list] = {}
        for x in part:
            if (x["p"] if not name.startswith("(가)") else x["p0"]) >= CUT_LEG:
                by_day.setdefault(x["day"], []).append(x)
        two = three = ok2 = ok3 = 0
        for day, legs in by_day.items():
            if len(legs) >= 2:
                two += 1
                ok2 += int(all((x["ok"] if not name.startswith("(가)")
                                else x["ok0"]) for x in legs[:2]))
            if len(legs) >= 3:
                three += 1
                ok3 += int(all((x["ok"] if not name.startswith("(가)")
                                else x["ok0"]) for x in legs[:3]))
        print(f"| {name} | {two} | "
              + (f"**{100*ok2/two:.1f}%**" if two else "⬜")
              + f" | {three} | " + (f"{100*ok3/three:.1f}%" if three
                                    else "⬜") + " |")
    print()
    print(f"- 날 수 {days} · 최고 줄 확률 중앙값 "
          f"{100*stat.median([x['p'] for x in out]):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
