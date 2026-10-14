"""🔴🔴 **공격 변수 1차 측정**(공격형 검증 v2 · 지시 2026-10-14f §5).

```
PYTHONPATH=. python tools/fit_attack.py            # 측정만
PYTHONPATH=. python tools/fit_attack.py --write     # 등급 승격까지 적는다
```

🔴 재료는 **재료 실은 덤프**(`var/judge/atk_*.json`)다 — 경기장 좌표(C3) ·
   팀 xG(B2·B4) · 선발(D4) · 골 시각과 스코어(F1·F2) · 날짜(D1).
🔴 **누설 금지** — 변수는 **그 경기 앞**의 경기들로만 만든다(C11). 그 경기 자신의
   xG·선발은 **쓰지 않는다**(쓰면 미래를 보고 공격하는 것이다).
🔴 재는 것 — 그 변수가 **걸린 경기**에서 봇 결론(방향)의 적중률이 **안 걸린 경기**
   보다 낮은가. 차이의 95% 구간이 **0 을 품으면 [관찰] 유지**(§5 마지막 줄).
⚠️ 문턱은 등록표(`config/attack_vars.yaml`)의 `cut` 이고 **시즌 교차로만** 고른다 —
   이 도구는 그 문턱으로 **재기만** 한다(여기서 문턱을 돌리지 않는다).
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as stat
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BACK = 10          # 🔴 "최근 10경기" — B2·B4 가 쓰는 창(등록표 cut.games)


def rows_all() -> list[dict]:
    """🔴 재료 실은 덤프만 — `extra` 가 있는 줄."""
    out, seen = [], set()
    for path in sorted((ROOT / "var/judge").glob("atk_*.json")):
        try:
            got = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for r in (got if isinstance(got, list) else []):
            if not isinstance(r, dict) or not r.get("extra"):
                continue
            key = (r.get("league"), r.get("day"), r.get("home"), r.get("away"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: (str(r.get("league")), str(r.get("day"))))
    return out


def km(a: dict, b: dict) -> float | None:
    """🔴 두 좌표의 거리(㎞ · 하버사인). 좌표가 없으면 `None`."""
    try:
        la1, lo1 = float(a["lat"]), float(a["lon"])
        la2, lo2 = float(b["lat"]), float(b["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    p = math.pi / 180.0
    h = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p)
         * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 12742.0 * math.asin(min(1.0, math.sqrt(max(h, 0.0))))


def ci_diff(a: list[int], b: list[int]) -> tuple[float, float, float]:
    """🔴 두 비율 차의 **95% 구간**(정규 근사). `(차, 하한, 상한)`."""
    if not a or not b:
        return (float("nan"),) * 3
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    se = math.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
    d = pa - pb
    return d, d - 1.96 * se, d + 1.96 * se


# ══════════════════════════════════════════════════════════════════
# 변수마다 — 그 경기에서 **걸렸나**(그 경기 앞 자료로만)
# ══════════════════════════════════════════════════════════════════

def build(rows: list[dict]) -> list[dict]:
    """🔴 경기마다 변수 깃발을 세운다. 봇 결론(`ours`)이 없는 줄은 뺀다."""
    prior: dict[tuple, list[dict]] = {}
    out: list[dict] = []
    for r in rows:
        lg, day = str(r.get("league")), str(r.get("day"))
        home, away = str(r.get("home")), str(r.get("away"))
        ex = dict(r.get("extra") or {})
        said = {"row": r, "flag": {}, "why": {}}
        ours = r.get("ours")
        hit = r.get("hit")
        if ours and hit is not None:
            pick = max(range(3), key=lambda i: float(ours[i]))
            said["pick"] = pick
            said["ok"] = int(pick == int(hit))
            side = "home" if pick == 0 else ("away" if pick == 2 else "")
            said["side"] = side
            # ── C3 이동 거리(원정 팀 — 직전 경기장 → 이 경기장)
            past_a = prior.get((lg, away)) or []
            if past_a and ex.get("venue"):
                got = km(dict((past_a[-1].get("extra") or {}).get("venue")
                              or {}), dict(ex.get("venue") or {}))
                if got is not None:
                    said["flag"]["C3"] = got >= 100.0
                    said["why"]["C3"] = f"{got:.0f}㎞"
            # ── D1 휴식일(양쪽 중 **결론 쪽**이 3일 미만)
            for who, key in (("home", (lg, home)), ("away", (lg, away))):
                past = prior.get(key) or []
                if not past:
                    continue
                try:
                    d0 = date.fromisoformat(str(past[-1].get("day"))[:10])
                    d1 = date.fromisoformat(day[:10])
                except ValueError:
                    continue
                said.setdefault("rest", {})[who] = (d1 - d0).days
            rest = dict(said.get("rest") or {})
            if side and rest.get(side) is not None:
                said["flag"]["D1"] = int(rest[side]) < 3
                said["why"]["D1"] = f"{rest[side]}일"
            # ── B2 xG 과대 / B4 수비 과대(결론 쪽 · 최근 10경기)
            if side:
                past = (prior.get((lg, home if side == "home" else away))
                        or [])[-BACK:]
                gf = ga = xg = xga = 0.0
                n = 0
                for one in past:
                    box = dict(one.get("extra") or {})
                    pair = list(box.get("xg") or [None, None])
                    mine_home = str(one.get("home")) == (home if side == "home"
                                                        else away)
                    if pair[0] is None or pair[1] is None:
                        continue
                    gf += float(one["hg"] if mine_home else one["ag"])
                    ga += float(one["ag"] if mine_home else one["hg"])
                    xg += float(pair[0] if mine_home else pair[1])
                    xga += float(pair[1] if mine_home else pair[0])
                    n += 1
                if n >= BACK:
                    said["flag"]["B2"] = (gf - xg) >= 1.5
                    said["why"]["B2"] = f"득점−xG {gf - xg:+.1f}({n}경기)"
                    said["flag"]["B4"] = (xga - ga) >= 1.5
                    said["why"]["B4"] = f"상대xG−실점 {xga - ga:+.1f}({n}경기)"
            # ── D4 로테이션(결론 쪽 · 직전 경기 선발과 겹침)
            if side:
                past = prior.get((lg, home if side == "home" else away)) or []
                if past:
                    box = dict(past[-1].get("extra") or {})
                    was = set((box.get("starters") or {}).get(
                        "home" if str(past[-1].get("home")) ==
                        (home if side == "home" else away) else "away") or [])
                    now = set((dict(ex.get("starters") or {})).get(side) or [])
                    if was and now:
                        changed = len(now - was)
                        said["flag"]["D4"] = changed >= 4
                        said["why"]["D4"] = f"바뀐 선발 {changed}"
            # ── F1 리드 유지력 / F2 추격력(결론 쪽 · 지난 경기들의 막판)
            if side:
                past = (prior.get((lg, home if side == "home" else away))
                        or [])[-BACK:]
                lost = chased = 0
                for one in past:
                    mine_home = str(one.get("home")) == (home if side == "home"
                                                         else away)
                    for g in (dict(one.get("extra") or {}).get("goals") or []):
                        try:
                            minute = int(g.get("minute") or 0)
                            bh, ba = (int(x) for x in (g.get("before")
                                                       or [0, 0]))
                        except (TypeError, ValueError):
                            continue
                        if minute < 75:
                            continue
                        mine, theirs = (bh, ba) if mine_home else (ba, bh)
                        got_home = bool(g.get("home"))
                        scored_mine = (got_home == mine_home)
                        if mine > theirs and not scored_mine:
                            lost += 1          # 🔴 리드 중 막판 실점
                        if mine < theirs and scored_mine:
                            chased += 1        # 🔴 뒤진 중 막판 득점
                said["flag"]["F1"] = lost >= 2
                said["why"]["F1"] = f"리드 뒤 막판 실점 {lost}회"
                said["flag"]["F2"] = chased >= 2
                said["why"]["F2"] = f"뒤진 뒤 막판 득점 {chased}회"
            out.append(said)
        # 🔴 **그 경기를 지난 목록에 더한다**(다음 경기의 prior)
        for key in ((lg, home), (lg, away)):
            prior.setdefault(key, []).append(r)
    return out


def main(argv: list[str]) -> int:
    import yaml

    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv[1:])

    rows = rows_all()
    box = build(rows)
    conf = yaml.safe_load((ROOT / "config/attack_vars.yaml")
                          .read_text(encoding="utf-8"))
    print(f"# 🔴🔴 공격 변수 1차 측정 — 재료 실은 덤프 **{len(rows)}경기** · "
          f"결론 있는 줄 {len(box)}건")
    print()
    lg_box: dict[str, int] = {}
    for r in rows:
        lg_box[str(r.get("league"))] = lg_box.get(str(r.get("league")), 0) + 1
    print("- 리그 — " + " · ".join(f"{k} {v}" for k, v in sorted(lg_box.items())))
    print()
    print("| 변수 | 걸린 경기 | 걸림 적중 | 안 걸림 적중 | 차이 | 95% 구간 "
          "| 시즌별 | 판정 |")
    print("|---|---|---|---|---|---|---|---|")
    moved: dict[str, dict] = {}
    for key in ("C3", "D1", "B2", "B4", "D4", "F1", "F2"):
        on = [x["ok"] for x in box if x["flag"].get(key) is True]
        off = [x["ok"] for x in box if x["flag"].get(key) is False]
        if len(on) < 30 or len(off) < 30:
            print(f"| **{key}** | {len(on)} | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | "
                  f"🔴 표본 부족(걸림 {len(on)} · 안 걸림 {len(off)}) → "
                  f"[관찰] 유지 |")
            continue
        d, lo, hi = ci_diff(on, off)
        seasons = {}
        for x in box:
            if x["flag"].get(key) is None:
                continue
            se = str(x["row"].get("season"))
            seasons.setdefault(se, {True: [], False: []})[
                bool(x["flag"][key])].append(x["ok"])
        said_se = " · ".join(
            f"{se} {100 * (sum(v[True]) / len(v[True])) if v[True] else float('nan'):.0f}"
            f"/{100 * (sum(v[False]) / len(v[False])) if v[False] else float('nan'):.0f}"
            for se, v in sorted(seasons.items()) if v[True] and v[False])
        ok_promote = hi < 0.0          # 🔴 구간이 **0 을 안 품고** 아래쪽
        print(f"| **{key}** | {len(on)} | {100 * sum(on) / len(on):.1f}% | "
              f"{100 * sum(off) / len(off):.1f}% | **{100 * d:+.1f}%p** | "
              f"[{100 * lo:+.1f}, {100 * hi:+.1f}] | {said_se or '⬜'} | "
              + ("✅ **[확정] 승격**" if ok_promote
                 else "🔴 구간이 0 을 품는다 → [관찰] 유지") + " |")
        moved[key] = {"n_on": len(on), "n_off": len(off),
                      "hit_on": round(sum(on) / len(on), 4),
                      "hit_off": round(sum(off) / len(off), 4),
                      "diff": round(d, 4), "lo": round(lo, 4),
                      "hi": round(hi, 4), "promote": bool(ok_promote)}
    # ── K1 무 구간(예측 vs 실측)
    print()
    print("| 무 구간 | 경기 | 예측 평균 | 실측 | 편차 |")
    print("|---|---|---|---|---|")
    for lo_b, hi_b, nm in ((0.20, 0.25, "20~25%"), (0.25, 0.30, "25~30%"),
                           (0.30, 1.01, "30%+")):
        part = [x for x in box
                if lo_b <= float(x["row"]["ours"][1]) < hi_b]
        if not part:
            continue
        pred = stat.mean(float(x["row"]["ours"][1]) for x in part)
        real = sum(1 for x in part if int(x["row"]["hit"]) == 1) / len(part)
        print(f"| {nm} | {len(part)} | {100 * pred:.1f}% | {100 * real:.1f}% | "
              f"**{100 * (real - pred):+.1f}%p** |")
    # ── 🔴🔴 **K1 재측정 — 등급 강등 판정**(§0 *"효과 없으면 강등·제거"*)
    #    무 구간 편차의 **부호가 표본 사이에서 뒤집히면** 그 편차로 무를 더하는
    #    공격은 근거가 없다. ⚠️ 실측 2026-10-14: 2,582경기 백필에서는 20~25%
    #    구간이 **+2.7%p 과소**였는데, 이 1,470경기에서는 **−4.1%p 과대**다.
    band_rows = []
    for lo_b, hi_b, nm in ((0.20, 0.25, "20~25%"), (0.25, 0.30, "25~30%"),
                           (0.30, 1.01, "30%+")):
        part = [x for x in box if lo_b <= float(x["row"]["ours"][1]) < hi_b]
        if len(part) < 50:
            continue
        pred = stat.mean(float(x["row"]["ours"][1]) for x in part)
        real = sum(1 for x in part if int(x["row"]["hit"]) == 1) / len(part)
        band_rows.append((nm, len(part), round(real - pred, 4)))
    old_dev = {"20~25%": +0.027, "25~30%": +0.007}      # 🔴 2,582경기 판의 편차
    flip = [nm for nm, _n, d in band_rows
            if old_dev.get(nm) is not None
            and (old_dev[nm] * d) < 0 and abs(d) >= 0.02]
    print()
    print("| K1 재측정 | 이 표본 편차 | 2,582경기 판 | 부호 |")
    print("|---|---|---|---|")
    for nm, n, d in band_rows:
        was = old_dev.get(nm)
        print(f"| {nm}({n}경기) | **{100*d:+.1f}%p** | "
              + (f"{100*was:+.1f}%p" if was is not None else "⬜")
              + " | " + ("🔴 **뒤집혔다**" if nm in flip else "같다") + " |")
    k1_down = bool(flip)
    print()
    print("- K1 판정 — "
          + ("🔴 **[확정] → [관찰] 강등**(편차 부호가 표본 사이에서 뒤집힌다 — "
             f"{', '.join(flip)})" if k1_down
             else "✅ [확정] 유지(부호가 같다)"))
    if args.write and k1_down:
        conf["vars"]["K1"]["grade"] = "관찰"
        conf["vars"]["K1"]["judge"] = False
        conf["vars"]["K1"]["fit"] = {
            "at": "2026-10-14", "표본": f"{len(rows)}경기",
            "bands": {nm: d for nm, _n, d in band_rows},
            "demote": True,
            "why": "무 구간 편차 부호가 표본 사이에서 뒤집힌다"}
    if args.write and moved:
        for key, one in moved.items():
            conf["vars"][key]["fit"] = {**one, "at": "2026-10-14",
                                        "표본": f"{len(rows)}경기"}
            if one["promote"]:
                conf["vars"][key]["grade"] = "확정"
                conf["vars"][key]["judge"] = True
        (ROOT / "config/attack_vars.yaml").write_text(
            "# 🔴 `tools/fit_attack.py --write` 가 `fit`·`grade` 를 적는다 "
            "(손으로 올리지 않는다)\n"
            + yaml.safe_dump(conf, allow_unicode=True, sort_keys=False,
                             width=100), encoding="utf-8")
        print()
        print(f"🔴 **등록표에 적었다** — 승격 "
              f"{[k for k, v in moved.items() if v['promote']] or '없다'}"
              + (" · **강등 K1**" if k1_down else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
