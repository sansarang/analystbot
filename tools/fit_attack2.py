"""🔴🔴 **교란 통제 재측정 + 2차 변수**(후속 지시 2026-10-14g §3·§4).

```
PYTHONPATH=. python tools/fit_attack2.py
```

🔴 §3 — **체급(Elo 차) 3구간**으로 나눠 걸림/안 걸림 적중 차를 다시 잰다.
   · F1 은 *"리드를 잡은 횟수 대비 **날린 비율**"* 로 **재정의**한다.
   · C3 은 문턱 대신 **이동 거리 4분위**.
   · D1 은 **컵·대륙 포함 실제 직전 경기일**(`data/rest/`)로 다시 센다.
🔴 §4 — G2 심판 · H1 순위 동기 · C5 관중. ⚠️ G1 퇴장 · I1 날씨 · F5 세트피스는
   **재료가 덤프에 없다** — 그 사실을 적고 넘긴다(지어내지 않는다 · #3).
🔴 누설 금지 — 모든 변수는 **그 경기 앞**의 자료로만 만든다(C11).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BACK = 10
TIERS = (("약(|Δ|<30)", 0.0, 30.0), ("중(30~100)", 30.0, 100.0),
         ("강(>100)", 100.0, 1e9))


def rows_all() -> list[dict]:
    out, seen = [], set()
    for path in sorted((ROOT / "var/judge").glob("atk_*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")):
            if not isinstance(r, dict) or not r.get("extra"):
                continue
            key = (r.get("league"), r.get("day"), r.get("home"), r.get("away"))
            if key in seen or not r.get("ours") or r.get("hit") is None:
                continue
            seen.add(key)
            out.append(r)
    out.sort(key=lambda r: (str(r.get("league")), str(r.get("day"))))
    return out


def rest_plates() -> dict:
    import yaml
    out: dict[str, dict] = {}
    box = ROOT / "data/rest"
    for path in sorted(box.glob("*.yaml")) if box.is_dir() else []:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out[path.stem.replace("_", ":", 1)] = got
    return out


def km(a: dict, b: dict) -> float | None:
    try:
        la1, lo1, la2, lo2 = (float(a["lat"]), float(a["lon"]),
                              float(b["lat"]), float(b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    p = math.pi / 180.0
    h = (0.5 - math.cos((la2 - la1) * p) / 2
         + math.cos(la1 * p) * math.cos(la2 * p)
         * (1 - math.cos((lo2 - lo1) * p)) / 2)
    return 12742.0 * math.asin(min(1.0, math.sqrt(max(h, 0.0))))


def ci(a: list[int], b: list[int]) -> tuple[float, float, float]:
    if len(a) < 2 or len(b) < 2:
        return (float("nan"),) * 3
    pa, pb = sum(a) / len(a), sum(b) / len(b)
    se = math.sqrt(pa * (1 - pa) / len(a) + pb * (1 - pb) / len(b))
    return pa - pb, pa - pb - 1.96 * se, pa - pb + 1.96 * se


def lead_rate(past: list[dict], team: str) -> tuple[int, float]:
    """🔴 F1 재정의 — `(리드 잡은 경기 수, 날린 비율)`.

    🔴 "날렸다" = 리드를 잡은 뒤 **동점 또는 역전을 허용**했다(그 경기 안에서).
    """
    got = lost = 0
    for r in past:
        mine_home = str(r.get("home")) == team
        rows = sorted((dict(r.get("extra") or {}).get("goals") or []),
                      key=lambda g: (int(g.get("minute") or 0),
                                     int(g.get("added") or 0)))
        led = False
        gone = False
        for g in rows:
            after = list(g.get("after") or [])
            if len(after) != 2:
                continue
            mine, theirs = ((after[0], after[1]) if mine_home
                            else (after[1], after[0]))
            if mine > theirs:
                led = True
            elif led and mine <= theirs:
                gone = True
        if led:
            got += 1
            lost += int(gone)
    return got, (lost / got if got else 0.0)


def main() -> int:
    rows = rows_all()
    rest = rest_plates()
    prior: dict[tuple, list] = {}
    pts: dict[tuple, dict] = {}
    ref_hist: dict[str, list] = {}
    box: list[dict] = []
    for r in rows:
        lg, day = str(r.get("league")), str(r.get("day"))
        se = str(r.get("season"))
        home, away = str(r.get("home")), str(r.get("away"))
        ex = dict(r.get("extra") or {})
        ours = [float(x) for x in r["ours"]]
        pick = max(range(3), key=lambda i: ours[i])
        side = "home" if pick == 0 else ("away" if pick == 2 else "")
        ok = int(pick == int(r["hit"]))
        dr = abs(float(r.get("dr") or 0.0))
        said: dict = {"ok": ok, "dr": dr, "side": side, "flag": {},
                      "season": se, "league": lg}
        mine = home if side == "home" else away
        past = (prior.get((lg, mine)) or [])[-BACK:]
        # ── F1 재정의 ─────────────────────────────────────────────
        if side and len(past) >= 5:
            n_led, share = lead_rate(past, mine)
            if n_led >= 3:
                said["flag"]["F1b"] = share >= 0.5
        # ── B2 xG 과대 ────────────────────────────────────────────
        if side and len(past) >= BACK:
            gf = xg = 0.0
            n = 0
            for one in past:
                pair = list((dict(one.get("extra") or {}).get("xg")
                             or [None, None]))
                if pair[0] is None or pair[1] is None:
                    continue
                h = str(one.get("home")) == mine
                gf += float(one["hg"] if h else one["ag"])
                xg += float(pair[0] if h else pair[1])
                n += 1
            if n >= BACK:
                said["flag"]["B2"] = (gf - xg) >= 1.5
        # ── C3 이동 거리(원정 팀) ─────────────────────────────────
        past_a = prior.get((lg, away)) or []
        if past_a and ex.get("venue"):
            got = km(dict((past_a[-1].get("extra") or {}).get("venue") or {}),
                     dict(ex.get("venue") or {}))
            if got is not None:
                said["km"] = got
        # ── D1 휴식일(컵 포함) ───────────────────────────────────
        if side:
            days = [d["day"] for d in
                    ((rest.get(lg) or {}).get(mine) or {}).get("days") or []
                    if str(d["day"]) < day]
            if days:
                try:
                    said["rest"] = (date.fromisoformat(day[:10])
                                    - date.fromisoformat(max(days))).days
                except ValueError:
                    pass
        # ── D4 로테이션 ──────────────────────────────────────────
        if side and past:
            was = set(((dict(past[-1].get("extra") or {}).get("starters")
                        or {}).get("home" if str(past[-1].get("home")) == mine
                                   else "away")) or [])
            now = set((dict(ex.get("starters") or {})).get(side) or [])
            if was and now:
                said["flag"]["D4"] = len(now - was) >= 4
        # ── G2 심판(앞선 경기들의 홈 승률) ────────────────────────
        ref = str(ex.get("referee") or "")
        if ref and len(ref_hist.get(ref) or []) >= 10:
            mine_r = ref_hist[ref]
            said["flag"]["G2"] = (sum(mine_r) / len(mine_r)) >= 0.50
        # ── H1 순위 동기(승점/경기) ──────────────────────────────
        a = dict(pts.get((lg, se, home)) or {"p": 0, "n": 0})
        b = dict(pts.get((lg, se, away)) or {"p": 0, "n": 0})
        if a["n"] >= 5 and b["n"] >= 5 and side:
            ppg = {"home": a["p"] / a["n"], "away": b["p"] / b["n"]}
            other = "away" if side == "home" else "home"
            said["flag"]["H1"] = ppg[side] < ppg[other]   # 🔴 표와 반대 결론
        # ── C5 관중(수용률) ─────────────────────────────────────
        try:
            att = float(ex.get("attendance") or 0)
            cap = float((ex.get("venue") or {}).get("capacity") or 0)
            if att and cap:
                said["fill"] = att / cap
        except (TypeError, ValueError):
            pass
        box.append(said)
        # ── 지난 목록 갱신 ──────────────────────────────────────
        hg, ag = int(r["hg"]), int(r["ag"])
        for team, mine_home in ((home, True), (away, False)):
            prior.setdefault((lg, team), []).append(r)
            got_p = (3 if ((hg > ag) == mine_home and hg != ag)
                     else (1 if hg == ag else 0))
            one = pts.setdefault((lg, se, team), {"p": 0, "n": 0})
            one["p"] += got_p
            one["n"] += 1
        if ref:
            ref_hist.setdefault(ref, []).append(int(hg > ag))

    # ── 4분위 깃발(C3·C5) ──────────────────────────────────────
    for key, field in (("C3", "km"), ("C5", "fill")):
        vals = sorted(x[field] for x in box if x.get(field) is not None)
        if len(vals) >= 40:
            cut = vals[int(0.75 * len(vals))]
            for x in box:
                if x.get(field) is not None:
                    x["flag"][key] = x[field] >= cut
    for x in box:
        if x.get("rest") is not None:
            x["flag"]["D1"] = int(x["rest"]) < 3

    print(f"# 🔴🔴 교란 통제 재측정 + 2차 변수 — **{len(box)}경기**")
    print()
    print("| 변수 | 구간 | 걸림 | 걸림 적중 | 안 걸림 적중 | 차이 | 95% 구간 |")
    print("|---|---|---|---|---|---|---|")
    for key in ("F1b", "B2", "C3", "D1", "D4", "G2", "H1", "C5"):
        for name, lo, hi in (("전체", 0.0, 1e9), *TIERS):
            part = [x for x in box if lo <= x["dr"] < hi
                    and x["flag"].get(key) is not None]
            on = [x["ok"] for x in part if x["flag"][key]]
            off = [x["ok"] for x in part if not x["flag"][key]]
            if len(on) < 20 or len(off) < 20:
                print(f"| {'**' + key + '**' if name == '전체' else ''} "
                      f"| {name} | {len(on)} | ⬜ | ⬜ | ⬜ | 표본 부족 |")
                continue
            d, l2, h2 = ci(on, off)
            mark = "🔴" if (h2 < 0 or l2 > 0) else ""
            print(f"| {'**' + key + '**' if name == '전체' else ''} | {name} "
                  f"| {len(on)} | {100*sum(on)/len(on):.1f}% | "
                  f"{100*sum(off)/len(off):.1f}% | **{100*d:+.1f}%p** | "
                  f"[{100*l2:+.1f}, {100*h2:+.1f}] {mark} |")
    print()
    got_km = [x["km"] for x in box if x.get("km") is not None]
    got_fill = [x["fill"] for x in box if x.get("fill") is not None]
    got_rest = [x["rest"] for x in box if x.get("rest") is not None]
    print(f"- 재료 — 이동거리 {len(got_km)}건(중앙값 "
          f"{sorted(got_km)[len(got_km)//2]:.0f}㎞ · 4분위 문턱 "
          f"{sorted(got_km)[int(0.75*len(got_km))]:.0f}㎞) · 수용률 "
          f"{len(got_fill)}건 · 휴식일 {len(got_rest)}건"
          + (f"(3일 미만 {sum(1 for x in got_rest if x < 3)}건)"
             if got_rest else ""))
    print("- ⬜ **재료 없음** — G1 퇴장(통로 미확인) · I1 날씨(축구 통로 없음) · "
          "F5 세트피스(골 유형 `situation` 을 이번 덤프가 안 담았다 — 추출기는 "
          "고쳤고 다음 수집부터 들어온다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
