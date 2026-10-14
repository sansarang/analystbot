"""🔴🔴 **후보 판 백필 판정**(수정·검증 지시 2026-10-14e §2).

```
PYTHONPATH=. python tools/judge_candidates.py              # 1단계 단독
PYTHONPATH=. python tools/judge_candidates.py --combo      # 2단계 조합
PYTHONPATH=. python tools/judge_candidates.py --league league:ELC
```

🔴 **같은 표본·같은 재생**이다 — `var/judge/replay_*.json` 을 한 번 읽어 λ 쌍과
   축 차로 후보별 λ 를 **복원**한다(다시 재생하면 Elo 굴림이 달라 비교가 깨진다).
🔴 되돌리는 식 — 덤프는 `λh = 바닥h·e^move · λa = 바닥a·e^-move`,
   `move = clamp(β·Σ, ±0.35)` 로 만들었다. 그래서
   `바닥h = λh·e^-move` · `바닥a = λa·e^+move` 이고, 후보는 **Σ 와 홈 배율**만
   갈아끼운다.
🔴 판정은 `tools/judge_models.passes(rule="season")`(v2+(d)) **그 함수**다(사본 금지).
⚠️ ③(팀 홈 배율)은 **덤프에 없던 층**이다 — 백필 λ 는 리그 배율만 썼다. 그래서
   ③ 는 *"팀 배율을 켜는 것이 이득이냐"* 를 재는 비교이고, ③a(끄기)가 **기준**과
   같다(그 사실을 표에 적는다).
⚠️ ①a 는 `gaps["axis3_sign"]` 이 있는 덤프에서만 잴 수 있다(그 칸을 적기 시작한
   뒤의 재생). 없는 줄은 **그 후보의 표본에서 빠진다** — 수를 지어내지 않는다.
"""
from __future__ import annotations

import argparse
import math
import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BETA = 0.25
MOVE_CAP = 0.35
W = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}
AXES = tuple(W)
AH = ("home-0.5", "home-1.5", "home+1.5")
OU = (1.5, 2.5, 3.5)


# ══════════════════════════════════════════════════════════════════
# 후보 — 한 줄의 Σ 와 홈 배율을 어떻게 바꾸나
# ══════════════════════════════════════════════════════════════════

def sigma(row: dict, *, weights: dict | None = None,
          axis3_key: str = "axis3", renorm: bool = False,
          scale: dict | None = None) -> float | None:
    """🔴 그 줄의 축 종합. `None` 이면 **그 후보로 못 센다**(표본에서 뺀다)."""
    gaps = dict(row.get("gaps") or {})
    base = dict(weights or W)
    got: dict[str, float] = {}
    for a in AXES:
        key = axis3_key if a == "axis3" else a
        val = gaps.get(key)
        if val is None:
            continue
        num = float(val)
        if scale:
            sd = float(dict(scale).get(a) or 0.0)
            if sd > 0:
                num = num / sd
        got[a] = num
    if not got:
        return None
    if axis3_key != "axis3" and "axis3" not in got:
        return None
    use = dict(base)
    if renorm:
        from app.core import m1v2 as _c
        use, _why = _c.weights_of(base, list(got))
    return sum(float(use.get(a) or 0.0) * got[a] for a in got)


def lam_of(row: dict, *, sig: float | None, home_ratio: float = 1.0
           ) -> list[float] | None:
    """🔴 후보 λ — 바닥에서 **새 move** 와 **새 홈 배율 비**로 다시 세운다."""
    lam = row.get("lam")
    if not lam:
        return None
    s0 = sigma(row)
    if s0 is None or sig is None:
        return None
    m0 = max(-MOVE_CAP, min(MOVE_CAP, BETA * s0))
    m1 = max(-MOVE_CAP, min(MOVE_CAP, BETA * sig))
    base_h = float(lam[0]) * math.exp(-m0)
    base_a = float(lam[1]) * math.exp(+m0)
    return [base_h * float(home_ratio) * math.exp(m1),
            base_a * math.exp(-m1)]


def triple(lam: list[float]) -> list[float]:
    from app.core import sim
    out = sim.run(max(lam[0], 1e-6), max(lam[1], 1e-6))
    return [out.home, out.draw, out.away]


# ══════════════════════════════════════════════════════════════════
# ③ 팀 홈 배율 — 그 경기 **이전** 경기만으로(누설 금지)
# ══════════════════════════════════════════════════════════════════

def home_ratios(rows: list[dict], variant: str) -> dict[int, float]:
    """🔴 줄 번호 → **리그 배율 대비 팀 배율 비**(λh 에 곱할 수). 누설 금지."""
    from app import rules
    from app.core import m1v2 as _c
    out: dict[int, float] = {}
    seen: dict[tuple, list[dict]] = {}
    last: dict[tuple, float] = {}
    for i, r in enumerate(rows):
        lg, se = str(r.get("league")), str(r.get("season"))
        home, away = str(r.get("home")), str(r.get("away"))
        box = dict(rules.goal_baseline(lg) or {})
        per = rules.goal_share(lg)
        mul_lg = (float(box["home_share"]) / float(per)
                  if box.get("home_share") and per else 1.0)
        games = list(seen.get((lg, se, home)) or [])
        prior = last.get((lg, home))
        if variant == "now":
            # 🔴🔴 **지금 운영이 쓰는 식**을 백필에 켜 본다 — 그 함수 그대로
            #    부른다(사본 금지). ⚠️ 백필 λ 에는 팀 배율이 **없었다** — 그래서
            #    이 비교가 *"팀 배율을 켜는 것이 이득이냐"* 의 답이다.
            from app.core import probmodel as _pm
            got, _why = _pm.team_home_mul(games, league=mul_lg)
        else:
            got, _why = _c.team_home(variant, games, league=mul_lg,
                                     prior=prior)
        out[i] = float(got) / mul_lg if mul_lg else 1.0
        hg, ag = int(r["hg"]), int(r["ag"])
        seen.setdefault((lg, se, home), []).append(
            {"side": "home", "gf": hg, "ga": ag})
        seen.setdefault((lg, se, away), []).append(
            {"side": "away", "gf": ag, "ga": hg})
        # 🔴 ③d — 시즌이 바뀌면 **지난 시즌 배율**이 사전값이 된다
        for team in (home, away):
            mine = seen.get((lg, se, team)) or []
            if len(mine) >= 6:
                got2, _w2 = _c.team_home("", mine, league=mul_lg)
                last[(lg, team)] = float(got2) if got2 else mul_lg
    return out


# ══════════════════════════════════════════════════════════════════
# 지표
# ══════════════════════════════════════════════════════════════════

def metrics_of(rows: list[dict], probs: list[list[float]]) -> dict:
    """🔴 승무패 지표 — 로그 손실 · 방향 · 상위 30/20/10% · 무 구간."""
    from app.core import metrics as _m
    ll = [_m.logloss(p, int(r["hit"])) for r, p in zip(rows, probs)]
    best = [max(range(3), key=lambda i: p[i]) for p in probs]
    dir_ok = [int(b == int(r["hit"])) for r, b in zip(rows, best)]
    order = sorted(range(len(rows)), key=lambda i: -max(probs[i]))
    top = {}
    for q in (0.30, 0.20, 0.10):
        k = max(1, int(q * len(rows)))
        top[q] = sum(dir_ok[i] for i in order[:k]) / k
    bands: dict[str, list[int]] = {}
    for r, p in zip(rows, probs):
        key = ("20~25" if 0.20 <= p[1] < 0.25
               else ("25~30" if 0.25 <= p[1] < 0.30
                     else ("30%+" if p[1] >= 0.30 else "")))
        if not key:
            continue
        bands.setdefault(key, [0, 0])
        bands[key][0] += 1
        bands[key][1] += int(int(r["hg"]) == int(r["ag"]))
    return {"ll": stat.mean(ll), "ll_rows": ll,
            "dir": sum(dir_ok) / len(rows), "dir_rows": dir_ok,
            "top": top, "best": best,
            # 🔴 무 구간 — (실측 적중, 경기 수)
            "bands": {k: (v[1] / v[0], v[0]) for k, v in bands.items()}}


def lines_of(rows: list[dict], lams: list[list[float]]) -> dict:
    """🔴 줄(핸디·오버·BTTS) 적중률·브라이어 — 격자는 `probfloor` 하나가 만든다."""
    from app.core import probfloor as _pf
    got: dict[str, list] = {}
    for r, lam in zip(rows, lams):
        box = _pf.markets_of(_pf.score_grid(lam_home=lam[0], lam_away=lam[1]))
        hg, ag = int(r["hg"]), int(r["ag"])
        d, tot = hg - ag, hg + ag
        want = {f"AH {k}": (float(dict(box.get('ah') or {}).get(k) or 0.0),
                            {"home-0.5": d > 0, "home-1.5": d > 1,
                             "home+1.5": d > -2}[k]) for k in AH}
        want.update({f"O{x}": (float(dict(box.get('over') or {}).get(x) or 0.0),
                               tot > x) for x in OU})
        want["BTTS"] = (float(box.get("btts_yes") or 0.0), hg > 0 and ag > 0)
        for name, (p, ok) in want.items():
            got.setdefault(name, []).append((p, bool(ok)))
    out = {}
    for name, xs in got.items():
        hit = sum(1 for p, ok in xs if (p >= 0.5) == ok) / len(xs)
        brier = sum((p - (1.0 if ok else 0.0)) ** 2 for p, ok in xs) / len(xs)
        out[name] = (hit, brier)
    return out


def judge(base: dict, cand: dict, rows: list[dict]) -> tuple[bool, str]:
    from app.core import metrics as _m
    import judge_models as jm
    diff = _m.paired(cand["ll_rows"], base["ll_rows"])
    b = sum(1 for x, y in zip(cand["dir_rows"], base["dir_rows"])
            if x and not y)
    c = sum(1 for x, y in zip(cand["dir_rows"], base["dir_rows"])
            if y and not x)
    p = jm.binom_two_sided(b, c)
    size = {"ll": base["ll"] - cand["ll"], "dir": cand["dir"] - base["dir"],
            "top20": cand["top"][0.20] - base["top"][0.20]}
    # 🔴 (c) 가 보는 `bands` 는 **상위 30/20/10% 적중률**이다(`judge_models.BANDS`
    #    = (0.30, 0.20, 0.10)). ⚠️ 실측 2026-10-14: 무 구간을 넘겨 `nan` 이 났다.
    ok, _box, said = jm.passes(
        diff=diff, dir_rate=cand["dir"], base_dir=base["dir"], p_value=p,
        bands=dict(cand["top"]), base_bands=dict(base["top"]),
        size=size, rule="season")
    return ok, (f"{said} · 맥니마 b/c {b}/{c} p {p:.4f} · 95% 구간 "
                f"[{diff.get('lo', 0):+.4f}, {diff.get('hi', 0):+.4f}]")


# ══════════════════════════════════════════════════════════════════
# 본체
# ══════════════════════════════════════════════════════════════════

def plates() -> dict:
    """🔴 ④a 척도 판 — 리그마다 축 표준편차(없으면 빈 표)."""
    import yaml
    out: dict[str, dict] = {}
    box = ROOT / "data/axis_scale"
    for path in sorted(box.glob("*.yaml")) if box.is_dir() else []:
        got = dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        out[path.stem.replace("_", ":", 1)] = {
            a: float((got.get(a) or {}).get("sd") or 0.0) for a in AXES}
    return out


def build(rows: list[dict], name: str, *, scales: dict) -> tuple[list, list]:
    """🔴 후보 하나 → `(쓴 줄, λ 목록)`. 못 세는 줄은 **뺀다**(지어내지 않는다)."""
    ratios = home_ratios(rows, name[1:]) if name.startswith("③") else {}
    keep, lams = [], []
    for i, r in enumerate(rows):
        if name == "운영":
            sig = sigma(r)
        elif name == "①a":
            sig = sigma(r, axis3_key="axis3_sign")
        elif name == "①b":
            sig = sigma(r, weights={**W, "axis3": 0.0})
        elif name == "②a":
            sig = sigma(r, renorm=True)
        elif name == "조합":
            # 🔴 2단계 조합 — ①a(축3 부호) + ②a(가중 재배분) + ③a(팀 배율 끄기)
            #    ⚠️ ③a 는 백필 λ 와 **같다**(백필에 팀 배율이 없었다) → 비율 1.0
            sig = sigma(r, axis3_key="axis3_sign", renorm=True)
        elif name == "④a":
            sig = sigma(r, scale=scales.get(str(r.get("league")) or "") or None)
        elif name.startswith("③"):
            sig = sigma(r)
        else:
            raise SystemExit(f"후보 `{name}` 를 모른다")
        got = lam_of(r, sig=sig, home_ratio=ratios.get(i, 1.0))
        if got is None:
            continue
        keep.append(r)
        lams.append(got)
    return keep, lams


def one_table(rows: list[dict], names: list[str], *, lines: bool = True,
              base: str = "운영") -> None:
    """🔴 기준을 `base` 로 둔다 — `③now` 로 두면 **지금 운영 설정**이 기준이다.

    ⚠️ 이름이 `base_name` 인 까닭 — 아래에서 `base` 를 **지표 표**로 다시 쓴다
       (실측 2026-10-14: 표 머리에 지표 표가 통째로 찍혔다).
    """
    base_name = str(base)
    scales = plates()
    base_rows, base_lams = build(rows, base_name, scales=scales)
    base = metrics_of(base_rows, [triple(x) for x in base_lams])
    base_key = {(r.get("league"), r.get("day"), r.get("home")): i
                for i, r in enumerate(base_rows)}
    print("| 판 | 표본 | 로그 손실 | 방향 | 상위 30/20/10% | 무 구간(예측 대비) "
          "| v2+(d) | 사유 |")
    print("|---|---|---|---|---|---|---|---|")
    said_base = (f"| **기준 {base_name}** | {len(base_rows)} | "
                 f"{base['ll']:.4f} | {100*base['dir']:.2f}% | "
                 + " / ".join(f"{100*base['top'][q]:.1f}" for q in
                              (0.30, 0.20, 0.10))
                 + " | " + " · ".join(
                     f"{k} {100*v[0]:.1f}%({v[1]})"
                     for k, v in sorted(base["bands"].items()))
                 + " | — | — |")
    print(said_base)
    out = []
    for name in names:
        keep, lams = build(rows, name, scales=scales)
        if not keep:
            print(f"| {name} | **0** | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | 🔴 그 후보로 "
                  f"셀 수 있는 줄이 없다 |")
            continue
        got = metrics_of(keep, [triple(x) for x in lams])
        # 🔴 **같은 줄끼리** 비교한다(후보가 뺀 줄은 기준에서도 뺀다)
        idx = [base_key.get((r.get("league"), r.get("day"), r.get("home")))
               for r in keep]
        pair = {k: [v[i] for i in idx if i is not None]
                for k, v in (("ll_rows", base["ll_rows"]),
                             ("dir_rows", base["dir_rows"]))}
        base_cut = {**base, **pair,
                    "ll": stat.mean(pair["ll_rows"]),
                    "dir": sum(pair["dir_rows"]) / len(pair["dir_rows"])}
        ok, said = judge(base_cut, got, keep)
        moved = sum(1 for a, b in zip(lams, [base_lams[i] for i in idx
                                             if i is not None])
                    if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9)
        split = sum(1 for a, b in zip(got["best"],
                                      [base["best"][i] for i in idx
                                       if i is not None]) if a != b)
        hit_split = (sum(1 for j, (a, b) in enumerate(
            zip(got["best"], [base["best"][i] for i in idx if i is not None]))
            if a != b and a == int(keep[j]["hit"])) / split) if split else 0.0
        print(f"| {name} | {len(keep)} | {got['ll']:.4f}"
              f"({base_cut['ll'] - got['ll']:+.4f}) | "
              f"{100*got['dir']:.2f}%({100*(got['dir']-base_cut['dir']):+.2f}) | "
              + " / ".join(f"{100*got['top'][q]:.1f}" for q in
                           (0.30, 0.20, 0.10))
              + " | " + " · ".join(f"{k} {100*v[0]:.1f}%({v[1]})"
                                   for k, v in sorted(got["bands"].items()))
              + f" | {'✅ **통과**' if ok else '🔴 탈락'} | {said} |")
        out.append({"name": name, "ok": ok, "ll": got["ll"], "moved": moved,
                    "split": split, "hit_split": hit_split})
    print()
    for r in out:
        print(f"- {r['name']} — **수가 바뀐 줄 {r['moved']}건** · 방향 갈린 경기 "
              f"{r['split']}건 · 그 경기 적중 {100*r['hit_split']:.1f}%")
    if lines:
        print()
        print("| 판 | " + " | ".join(
            [f"AH {k}" for k in AH] + [f"O{x}" for x in OU] + ["BTTS"])
            + " |")
        print("|---" * (len(AH) + len(OU) + 2) + "|")
        for nm, rr, ll in [("운영", base_rows, base_lams)] + [
                (n, *build(rows, n, scales=scales)) for n in names]:
            if not rr:
                continue
            got = lines_of(rr, ll)
            print(f"| {nm} | " + " | ".join(
                f"{100*got[k][0]:.1f}% / {got[k][1]:.3f}"
                for k in [f"AH {x}" for x in AH] + [f"O{x}" for x in OU]
                + ["BTTS"]) + " |")


def main(argv: list[str]) -> int:
    import replays

    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="")
    ap.add_argument("--only", default="")
    # 🔴 `--dump` — 덤프 **하나만** 읽는다(①a 는 `axis3_sign` 을 적기 시작한
    #    재생에만 있다 · `replays.load` 는 큰 덤프를 먼저 골라 그 줄을 지운다)
    ap.add_argument("--dump", default="")
    ap.add_argument("--base", default="운영")
    args = ap.parse_args(argv[1:])

    if args.dump:
        import json
        rows = json.loads(Path(args.dump).read_text(encoding="utf-8"))
        said = f"덤프 하나 `{Path(args.dump).name}` — {len(rows)}줄"
    else:
        rows, said = replays.load(league=args.league)
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None]
    rows.sort(key=lambda r: str(r.get("day") or ""))
    print(f"# 🔴🔴 후보 판정 — {said}")
    print()
    print(f"- 쓸 수 있는 줄 **{len(rows)}경기**(λ 와 결과가 있는 줄)")
    print()
    names = (args.only.split(",") if args.only
             else ["①a", "①b", "②a", "③now", "③a", "③b", "③c", "③d",
                   "④a"])
    one_table(rows, names, base=args.base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
