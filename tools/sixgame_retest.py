"""🔴🔴 **10-14 챔피언십 6경기 재시험**(지시 2026-10-14e §3 · 시험용).

```
PYTHONPATH=. python tools/sixgame_retest.py
```

🔴 **새 정보를 넣지 않는다** — 재료는 그날 카드 로그(`var/accept/ch_*.log`,
   as_of 02:56~02:57 · 확정 XI)에서 **그대로 읽는다**: 축 원값·Σ·홈 배율
   원값/표본/수축·λ·발동 규칙과 그 **효과**.
🔴 판 — 운영 M1 · M1만(축 0) · 상성만(홈 배율 0) · 후보 단독 · 최종 조합 · 시장(Shin).
⚠️ **6경기는 판단 표본이 아니다**(§3 마지막 줄) — 이 표는 *"수정이 의도대로
   움직이나"* 를 보는 확인용이다. 채택은 백필 판정(`tools/judge_candidates.py`)만.
"""
from __future__ import annotations

import ast
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

BETA = 0.25
AWAY = 0.880            # 🔴 league:ELC 원정 몫(1.1233 ÷ 1.2771)
MEAN = 1.2771           # 🔴 league:ELC 한 팀 평균(표본 1209경기)
LEAGUE_MUL = 1.120      # 🔴 league:ELC 리그 홈 배율
W = {"axis0": 0.3, "axis1": 0.3, "axis2": 0.2, "axis3": 0.2}
PER_RULE = 0.15

#: 🔴 그날 여섯 경기 — 로그 열쇠 · 이름 · 보드(사용자 캡처) · 결과
GAMES = (
    ("bri", "브리스톨–블랙번", [2.15, 3.25, 3.40], (0, 1)),
    ("bur", "번리–찰턴", [1.60, 3.90, 5.40], (2, 2)),
    ("car", "카디프–왓포드", [1.58, 4.40, 4.90], (5, 1)),
    ("mil", "밀월–스완지", [2.30, 3.30, 3.05], (0, 1)),
    ("wol", "울브스–볼턴", [1.37, 4.90, 7.70], (1, 3)),
    ("wre", "렉섬–웨스트브롬", [2.20, 3.30, 3.30], (1, 2)),
)

AX = re.compile(r"^- \*\*(axis[0-3])\*\* 홈 (\S+) · 원정 (\S+) · 차 (\S+)")
MUL = re.compile(r"팀별 홈 효과 ×([0-9.]+)\(홈 ([0-9.]+)골 ÷ 원정 ([0-9.]+)골\)"
                 r" · 표본 (\d+)쌍")
RULE = re.compile(r"`(T\d+)` ([^—]+?) — .*?효과 (\{[^}]*\})")
LAM = re.compile(r"- \*\*λ\*\* — home ([0-9.]+) · away ([0-9.]+)")
#: 🔴 카드가 **낸** 승무패(상태 배율·후반 λ 가 들어간 수)
PUB = re.compile(r"^\| 확률 \| ([0-9.]+)% \| ([0-9.]+)% \| ([0-9.]+)% \|")


def read(key: str) -> dict:
    """🔴 카드 로그 하나에서 재료를 읽는다(지어내지 않는다)."""
    said = (ROOT / f"var/accept/ch_{key}.log").read_text(encoding="utf-8")
    out: dict = {"axes": {}, "rules": [], "names": []}
    for line in said.splitlines():
        got = AX.match(line.strip())
        if got:
            a, h, aw, gap = got.groups()
            out["axes"][a] = {
                "home": None if h == "None" else float(h),
                "away": None if aw == "None" else float(aw),
                "gap": None if gap == "None" else float(gap)}
        if "팀별 홈 효과 ×" in line and not out.get("mul"):
            m = MUL.search(line)
            if m:
                out["mul"] = {"raw": float(m.group(1)),
                              "gf_h": float(m.group(2)),
                              "gf_a": float(m.group(3)),
                              "n": int(m.group(4))}
        if out.get("lam") is None:
            m = LAM.search(line)
            if m:
                out["lam"] = [float(m.group(1)), float(m.group(2))]
        if out.get("pub") is None:
            m = PUB.match(line.strip())
            if m:
                out["pub"] = [float(x) / 100 for x in m.groups()]
    # 🔴 **발동 규칙과 효과** — 같은 규칙이 여러 번 적히니 중복을 지운다
    seen = set()
    for m in RULE.finditer(said):
        rule, team, eff = m.group(1), m.group(2).strip(), m.group(3)
        key2 = (rule, team, eff)
        if key2 in seen:
            continue
        seen.add(key2)
        try:
            box = ast.literal_eval(eff)
        except (ValueError, SyntaxError):
            continue
        out["rules"].append({"rule": rule, "team": team, "effect": dict(box)})
    # 🔴 홈·원정 팀 이름 — 기준 XI 줄에서
    for line in said.splitlines():
        m = re.match(r"- \*\*([^*]+)\*\* \d[-0-9]* \[확정\]", line.strip())
        if m and m.group(1) not in out["names"]:
            out["names"].append(m.group(1))
    return out


def axis3_signed(box: dict) -> float | None:
    """🔴 ①a — 규칙 **효과 부호**로 센 축3 차."""
    from app.core import m1v2 as _c
    if not box["rules"]:
        return 0.0
    names = box["names"]
    if len(names) < 2:
        return None
    val = {"home": 0.0, "away": 0.0}
    for one in box["rules"]:
        side = ("home" if one["team"] == names[0]
                else ("away" if one["team"] == names[1] else ""))
        if not side:
            continue
        val[side] += PER_RULE * _c.rule_sign(one["effect"])
    return round(val["home"] - val["away"], 4)


def sigma(box: dict, *, axis3: float | None = None, renorm: bool = False,
          scale: float | None = None, axis3_w: float | None = None) -> float:
    gaps = {a: (axis3 if (a == "axis3" and axis3 is not None)
                else box["axes"].get(a, {}).get("gap"))
            for a in W}
    got = {a: v for a, v in gaps.items() if v is not None}
    if scale:
        got = {a: (v / scale if a == "axis0" else v) for a, v in got.items()}
    use = dict(W)
    if axis3_w is not None:
        use["axis3"] = axis3_w
    if renorm:
        from app.core import m1v2 as _c
        use, _why = _c.weights_of(use, list(got))
    return sum(float(use.get(a) or 0.0) * v for a, v in got.items())


def triple(lh: float, la: float) -> list[float]:
    from app.core import sim
    out = sim.run(max(lh, 1e-6), max(la, 1e-6))
    return [out.home, out.draw, out.away]


def lines_of(lh: float, la: float) -> dict:
    from app.core import probfloor as _pf
    return _pf.markets_of(_pf.score_grid(lam_home=lh, lam_away=la))


def main() -> int:
    from app.core import divergence as dv
    from app.core import m1v2 as _c
    from app.core import metrics as _m

    sd, said_sd = _c.axis_sd("league:ELC", "axis0")
    print("# 🔴🔴 10-14 챔피언십 6경기 **재시험**(시험용 · 판단 표본 아니다)")
    print()
    print(f"- 축0 척도판(④a) — {said_sd}")
    print()
    box = {}
    plates: dict[str, list] = {}
    for key, name, board, res in GAMES:
        got = read(key)
        mul_now = None
        if got.get("mul"):
            w = min(got["mul"]["n"], 8) / 8.0
            mul_now = (1 - w) * LEAGUE_MUL + w * min(1.40, got["mul"]["raw"])
        else:
            mul_now = LEAGUE_MUL
        s_now = sigma(got)
        said = {}
        # 🔴 판마다 (홈 배율, Σ)
        said["운영 M1"] = (mul_now, s_now)
        said["M1만"] = (mul_now, 0.0)
        said["상성만"] = (1.0 * AWAY, s_now)      # 🔴 홈 배율 0(두 쪽 같은 몫)
        said["①a"] = (mul_now, sigma(got, axis3=axis3_signed(got)))
        said["①b"] = (mul_now, sigma(got, axis3_w=0.0))
        said["②a"] = (mul_now, sigma(got, renorm=True))
        said["④a"] = (mul_now, sigma(got, scale=sd) if sd else s_now)
        for v in ("a", "c", "d"):
            # ⚠️ ③b(대칭식)는 **실점**이 필요한데 카드가 안 적었다 → ⬜ 로 둔다
            #    (지어내지 않는다 · #3). 백필 판정에는 들어가 있다.
            games = ([{"side": "home", "gf": got["mul"]["gf_h"], "ga": 0.0}]
                     * max(1, got["mul"]["n"])
                     + [{"side": "away", "gf": got["mul"]["gf_a"], "ga": 0.0}]
                     * max(1, got["mul"]["n"])) if got.get("mul") else []
            mine, _why = _c.team_home(v, games, league=LEAGUE_MUL,
                                      prior=LEAGUE_MUL)
            said[f"③{v}"] = (mine, s_now)
        said["조합 ①a+②a+③?+④a"] = None          # 🔴 백필 판정 뒤에 채운다
        box[key] = {"name": name, "got": got, "res": res, "board": board,
                    "plates": said, "mul_now": mul_now, "s_now": s_now}
    # ── 경기별 표
    order = [k for k in box[next(iter(box))]["plates"] if k and
             box[next(iter(box))]["plates"][k]]
    print("| 경기 | 판 | 홈/무/원정 | 방향 | 핸디 −0.5 | 오버 2.5 | 결과 |")
    print("|---|---|---|---|---|---|---|")
    for key, one in box.items():
        hg, ag = one["res"]
        got_res = 0 if hg > ag else (1 if hg == ag else 2)
        mk, _why = dv.market_triple(one["board"])
        pub = one["got"].get("pub")
        if pub:
            print(f"| {one['name']} | **카드 그대로**(상태 배율 포함) | "
                  f"{100*pub[0]:.1f} / {100*pub[1]:.1f} / {100*pub[2]:.1f}% | "
                  f"{['홈','무','원정'][max(range(3), key=lambda i: pub[i])]} "
                  f"| ⬜ | ⬜ | {one['res'][0]}-{one['res'][1]} |")
            plates.setdefault("카드 그대로", []).append(
                {"p": list(pub), "hit": got_res, "hg": one["res"][0],
                 "ag": one["res"][1], "ah": 0.0, "ov": 0.0})
        # 🔴🔴 **카드 λ 를 바닥으로 쓴다**(T 규칙·상태 배율이 그 안에 있다) —
        #    바닥 = λ ÷ (배율 · e^이동). 후보는 **배율과 이동만** 갈아끼운다.
        lam0 = one["got"].get("lam")
        m0 = BETA * one["s_now"]
        base_h = float(lam0[0]) / (one["mul_now"] * math.exp(m0))
        base_a = float(lam0[1]) / (AWAY * math.exp(-m0))
        for nm in order:
            mul, sig = one["plates"][nm]
            m1 = BETA * sig
            if nm == "상성만":
                # 🔴 홈 배율 0 — 두 쪽에 **같은 몫**(기하평균)을 준다
                g = math.sqrt(one["mul_now"] * AWAY)
                lh, la = base_h * g * math.exp(m1), base_a * g * math.exp(-m1)
            else:
                lh, la = base_h * mul * math.exp(m1), base_a * AWAY * \
                    math.exp(-m1)
            t = triple(lh, la)
            d = max(range(3), key=lambda i: t[i])
            ah = dict(lines_of(lh, la).get("ah") or {}).get("home-0.5")
            ov = dict(lines_of(lh, la).get("over") or {}).get(2.5)
            plates.setdefault(nm, []).append(
                {"p": t, "hit": got_res, "hg": hg, "ag": ag,
                 "ah": float(ah or 0.0), "ov": float(ov or 0.0)})
            print(f"|  | {nm}"
                  + ("(재계산 · 상태 배율 제외)" if nm == "운영 M1" else "")
                  + " | "
                  f"{100*t[0]:.1f} / {100*t[1]:.1f} / {100*t[2]:.1f}% | "
                  f"{['홈','무','원정'][d]} | {100*float(ah or 0):.1f}% | "
                  f"{100*float(ov or 0):.1f}% | "
                  f"{hg}-{ag} {['홈 승','무','원정 승'][got_res]} |")
        print(f"| {one['name']} | **시장(Shin)** | "
              f"{100*mk[0]:.1f} / {100*mk[1]:.1f} / {100*mk[2]:.1f}% | "
              f"{['홈','무','원정'][max(range(3), key=lambda i: mk[i])]} | ⬜ "
              f"| ⬜ | {hg}-{ag} |")
        plates.setdefault("시장(Shin)", []).append(
            {"p": list(mk), "hit": got_res, "hg": hg, "ag": ag,
             "ah": 0.0, "ov": 0.0})
    # ── 합계
    print()
    print("| 판 | 방향 적중 | 평균 로그 손실 | 오버 2.5 적중 | 핸디 −0.5 적중 |")
    print("|---|---|---|---|---|")
    for nm, xs in plates.items():
        d = sum(1 for x in xs
                if max(range(3), key=lambda i: x["p"][i]) == x["hit"])
        ll = sum(_m.logloss(x["p"], x["hit"]) for x in xs) / len(xs)
        ov = sum(1 for x in xs if x["ov"] and
                 ((x["ov"] >= 0.5) == ((x["hg"] + x["ag"]) > 2.5)))
        ah = sum(1 for x in xs if x["ah"] and
                 ((x["ah"] >= 0.5) == (x["hg"] > x["ag"])))
        print(f"| {nm} | **{d}/6** | {ll:.4f} | "
              + (f"{ov}/6" if any(x['ov'] for x in xs) else "⬜")
              + " | " + (f"{ah}/6" if any(x['ah'] for x in xs) else "⬜")
              + " |")
    # ── 분해 전후
    print()
    print("| 경기 | 홈 배율 몫(지금) | 축 몫(지금) | 정한 것 | ③c 배율 "
          "| 홈 몫(③c) | ④a 축 몫 | 정한 것(③c+④a) |")
    print("|---|---|---|---|---|---|---|---|")
    for key, one in box.items():
        h0 = math.log(one["mul_now"] / AWAY)
        a0 = 2 * BETA * one["s_now"]
        mul_c = one["plates"]["③c"][0]
        h1 = math.log(mul_c / AWAY)
        a1 = 2 * BETA * one["plates"]["④a"][1]
        print(f"| {one['name']} | {h0:+.3f} | {a0:+.3f} | "
              f"**{'홈 배율' if abs(h0) > abs(a0) else '축'}** | ×{mul_c:.3f} | "
              f"{h1:+.3f} | {a1:+.3f} | "
              f"**{'홈 배율' if abs(h1) > abs(a1) else '축'}** |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
