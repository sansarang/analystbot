"""🔴🔴 **어제(10-14) 챔피언십 6경기 공격**(지시 2026-10-14f §3·§4·§7).

```
PYTHONPATH=. python tools/attack_sixgame.py
```

🔴 재료는 그날 카드 로그(`var/accept/ch_*.log`)에서만 읽는다 — **새 정보 0건**.
🔴 공격은 `app/core/attack.py` **하나**가 한다(사본 금지) · 재계산은 운영과 같은
   식(`attack.lam_of` → `sim.run` → `probfloor.markets_of`).
🔴 문턱은 **문턱 곡선**(`var/accept/cut_curve.log`)에서 고른 수다 —
   단폴 **0.88**(백필 적중 94.7% · 하루 4.4개) · 다리 **0.90**(2폴 92.1%).
⚠️ 6경기는 **판단 표본이 아니다** — 공격이 의도대로 도는지 보는 표다.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

CUT_SINGLE = 0.88
CUT_LEG = 0.90
AWAY = 0.880
LEAGUE_MUL = 1.120
BETA = 0.25

GAMES = (
    ("bri", "브리스톨–블랙번", [2.15, 3.25, 3.40], (0, 1)),
    ("bur", "번리–찰턴", [1.60, 3.90, 5.40], (2, 2)),
    ("car", "카디프–왓포드", [1.58, 4.40, 4.90], (5, 1)),
    ("mil", "밀월–스완지", [2.30, 3.30, 3.05], (0, 1)),
    ("wol", "울브스–볼턴", [1.37, 4.90, 7.70], (1, 3)),
    ("wre", "렉섬–웨스트브롬", [2.20, 3.30, 3.30], (1, 2)),
)


def read(key: str) -> dict:
    """🔴 카드 로그에서 **공격 재료**를 읽는다(지어내지 않는다)."""
    said = (ROOT / f"var/accept/ch_{key}.log").read_text(encoding="utf-8")
    out: dict = {"gaps": {}, "axis_why": {}}
    for line in said.splitlines():
        t = line.strip()
        m = re.match(r"- \*\*(axis[0-3])\*\* 홈 (\S+) · 원정 (\S+) · 차 (\S+)", t)
        if m:
            out["gaps"][m.group(1)] = (None if m.group(4) == "None"
                                       else float(m.group(4)))
        m = re.match(r"^\| 확률 \| ([0-9.]+)% \| ([0-9.]+)% \| ([0-9.]+)% \|$", t)
        if m and not out.get("ours"):
            out["ours"] = [float(x) / 100 for x in m.groups()]
        m = re.search(r"- \*\*λ\*\* — home ([0-9.]+) · away ([0-9.]+)", t)
        if m and not out.get("lam"):
            out["lam"] = [float(m.group(1)), float(m.group(2))]
        m = re.search(r"팀별 홈 효과 ×([0-9.]+)\(.*?표본 (\d+)쌍 → 수축 가중 "
                      r"(\d+)%", t)
        if m and not out.get("team_mul"):
            w = float(m.group(3)) / 100
            out["team_mul"] = round(w * min(1.40, float(m.group(1)))
                                    + (1 - w) * LEAGUE_MUL, 4)
        m = re.search(r"Elo: .*?차 ([+-][0-9]+) → 승 (\d+)% · 무 (\d+)% · 패 "
                      r"(\d+)%", t)
        if m and not out.get("elo"):
            out["elo"] = [float(m.group(2)) / 100, float(m.group(3)) / 100,
                          float(m.group(4)) / 100]
        if "구간(**" in t and "예측" in t and not out.get("band_dev"):
            m = re.search(r"편차 ([+-][0-9.]+)%", t)
            if m:
                out["band_dev"] = float(m.group(1)) / 100
        if "무 구간 실측 없음" in t:
            out["band_dev"] = None
        if "⬜ 입력 — " in t and not out.get("gaps_missing"):
            m = re.search(r"⬜ 입력 — ([^→·]+)", t)
            if m:
                out["gaps_missing"] = [x.strip() for x in
                                       m.group(1).split("·") if x.strip()]
        if "`T12`" in t and "효과" in t:
            out.setdefault("t12_rows", []).append(t)
        m = re.match(r"- \*\*([^*]+)\*\* — 최근 (\d+)경기", t)
        if m:
            out.setdefault("form_n", []).append(int(m.group(2)))
        m = re.match(r"- \*\*([^*]+)\*\* \d[-0-9]* \[(확정|예상)\]", t)
        if m:
            out.setdefault("names", []).append(m.group(1))
            out["xi_state"] = m.group(2)
        if re.match(r"^[A-Z][a-zÀ-ÿ'.\- ]+\(\?\) — 부상", t):
            out.setdefault("absent", []).append(t.split("(?)")[0].strip())
    out["absence_src"] = "B" if out.get("absent") else ""
    return out


def box_of(key: str, board: list, got: dict) -> dict:
    from app.core import divergence as dv
    mk, _why = dv.market_triple(board)
    pick = max(range(3), key=lambda i: got["ours"][i])
    side = "home" if pick == 0 else ("away" if pick == 2 else "")
    names = list(got.get("names") or ["", ""])
    t12 = ""
    for row in (got.get("t12_rows") or []):
        who = row.split("`T12`")[-1].split("—")[0].strip()
        mine = ("home" if who == names[0]
                else ("away" if len(names) > 1 and who == names[1] else ""))
        if mine:
            t12 += f"{mine}:{who} "
    lam = [float(x) for x in got["lam"]]
    mul = float(got.get("team_mul") or LEAGUE_MUL)
    sigma0 = sum({"axis0": .3, "axis1": .3, "axis2": .2, "axis3": .2}.get(k, 0)
                 * (v or 0) for k, v in got["gaps"].items())
    base = [lam[0] / (mul * math.exp(BETA * sigma0)),
            lam[1] / (AWAY * math.exp(-BETA * sigma0))]
    return {"pick": pick, "side": side, "gaps": dict(got["gaps"]),
            # 🔴 ⚠️ 실측 2026-10-14: 이 칸을 안 실어 A1 이 전부 "기준 없다"로
            #    깨졌다(카드엔 Elo 가 있었다) — 재료를 **빠뜨리면 공격이 거짓말**을 한다
            "elo": got.get("elo"),
            "ours": list(got["ours"]), "market": list(mk) if mk else None,
            "mul": mul, "team_mul": 0.0,          # 🔴 ③a — 팀 배율 **안 쓴다**
            "league_mul": LEAGUE_MUL, "away_mul": AWAY, "league_real": 1.200,
            "base": base, "xi_state": got.get("xi_state"),
            "absence_src": got.get("absence_src"),
            "key_missing": [],                     # 🔴 축0 상위 3 대조 ⬜
            "gaps_missing": got.get("gaps_missing") or [],
            "band_dev": got.get("band_dev"), "neutral": False,
            "t12": t12.strip(), "form_games": min(got.get("form_n") or [9]),
            "axis_why": dict(got.get("axis_why") or {}),
            "axis0_sd": 0.935, "discipline": None}


def main() -> int:
    from app.core import attack as atk
    from app.core import probfloor as pf
    from app.core import sim

    print("# 🔴🔴 어제 6경기 **공격표**(지시 2026-10-14f §3 · 시험용)")
    print()
    print(f"- 문턱(문턱 곡선에서 고름) — 단폴 **{CUT_SINGLE:.2f}** · "
          f"다리 **{CUT_LEG:.2f}**")
    print()
    print("| 경기 | 원래 결론 | 깨짐 | 반격 | 살아남은 변수 | 살아남은 결론 "
          "| 판정 |")
    print("|---|---|---|---|---|---|---|")
    legs: list[dict] = []
    for key, name, board, res in GAMES:
        got = read(key)
        box = box_of(key, board, got)
        out = atk.of(box)
        lam = atk.lam_of(box, out)
        three = sim.run(lam[0], lam[1])
        new = [three.home, three.draw, three.away]
        pick0 = box["pick"]
        pick1 = max(range(3), key=lambda i: new[i])
        hg, ag = res
        real = 0 if hg > ag else (1 if hg == ag else 2)
        said_broken = " · ".join(f"**{s.key}** {s.why[:38]}"
                                 for s in out.broken()) or "없다"
        said_counter = " · ".join(f"**{s.key}** {s.why[:30]}"
                                  for s in out.counters()) or "없다"
        said_hold = " · ".join(s.key for s in out.shots
                               if s.verdict == "버팀") or "없다"
        print(f"| {name} | {['홈','무','원정'][pick0]} "
              f"{100*box['ours'][pick0]:.1f}% | {said_broken} | {said_counter} "
              f"| {said_hold} | {['홈','무','원정'][pick1]} "
              f"{100*new[pick1]:.1f}%"
              + (f" · 무 +{100*out.draw_add:.1f}%p" if out.draw_add else "")
              + f" | **{out.verdict()}**"
              + (f" · 결과 {hg}-{ag}" if True else "") + " |")
        # 🔴 §4 — 살아남은 결론의 **줄**만 단폴 후보로 본다
        mk = pf.markets_of(pf.score_grid(lam_home=lam[0], lam_away=lam[1]))
        rows = [("홈 승", new[0], hg > ag), ("원정 승", new[2], hg < ag),
                ("무", new[1], hg == ag)]
        for k, ok in (("home-0.5", hg > ag), ("home+0.5", hg >= ag),
                      ("home+1.5", hg - ag > -2), ("away+0.5", hg <= ag),
                      ("away+1.5", ag - hg > -2)):
            p = dict(mk.get("ah") or {}).get(k)
            if p is not None:
                rows.append((f"핸디 {k}", float(p), ok))
        for x in (1.5, 2.5, 3.5):
            p = dict(mk.get("over") or {}).get(x)
            if p is not None:
                rows.append((f"오버 {x}", float(p), (hg + ag) > x))
                rows.append((f"언더 {x}", 1 - float(p), (hg + ag) < x))
        top = max(rows, key=lambda r: r[1])
        legs.append({"name": name, "line": top[0], "p": top[1], "ok": top[2],
                     "verdict": out.verdict(), "board": board,
                     "res": f"{hg}-{ag}", "real": real})
        print(f"|  | 🧷 이 결론은 **{len(out.broken())}개 깨짐 / "
              f"{len([s for s in out.shots if s.verdict == '버팀'])}개 버팀**에 "
              f"걸려 있다 — 공격 {len(out.shots)}발 | | | | | |")
    # ── §4 단폴·다폴 ────────────────────────────────────────────
    print()
    print("| 경기 | 최고 줄 | 확률 | 문턱 통과 | 판정 | 보드 | 결과 | 맞았나 |")
    print("|---|---|---|---|---|---|---|---|")
    for one in legs:
        print(f"| {one['name']} | {one['line']} | {100*one['p']:.1f}% | "
              + ("✅" if one["p"] >= CUT_SINGLE else "🔴 미달")
              + f" | {one['verdict']} | {one['board']} | {one['res']} | "
              + ("✅" if one["ok"] else "🔴") + " |")
    picks = [x for x in legs
             if x["p"] >= CUT_SINGLE and x["verdict"] != "무너짐"]
    print()
    if not picks:
        print("- **오늘 단폴 없음**(문턱 통과 0 또는 전부 무너짐)")
    else:
        for x in picks:
            print(f"- 단폴 — {x['name']} **{x['line']}** {100*x['p']:.1f}% → "
                  + ("✅ 적중" if x["ok"] else "🔴 빗나감"))
    legs2 = [x for x in legs if x["p"] >= CUT_LEG
             and x["verdict"] == "살아남음"]
    print()
    if len(legs2) < 2:
        print(f"- **다폴 없음** — 다리 문턱 {CUT_LEG:.2f} 통과 "
              f"{len(legs2)}개(2개 미만)")
    else:
        pair = legs2[:2]
        print(f"- 2폴 — " + " + ".join(f"{x['name']} {x['line']}"
                                       for x in pair)
              + " → " + ("✅ 둘 다 적중" if all(x["ok"] for x in pair)
                         else "🔴 깨짐"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
