"""🔴🔴 **홈 배율 점검**(검증 지시 2026-10-14d ④ · 측정만).

```
PYTHONPATH=. python tools/home_mul_audit.py
```

🔴 아무 값도 바꾸지 않는다. 백필 덤프(`var/judge/replay_*.json`)의 실제 스코어로
   ① 기준율(홈/무/원정) ② **팀별 홈 효과를 엔진과 같은 식으로** 그 경기 **이전
   경기만** 써서 만들고, 그 배율이 **다음 홈 경기**를 맞히는지 ③ 리그 홈 이점
   ×1.120 이 실측 홈 승률·홈 득점 몫과 맞는지 센다.

🔴 엔진 식(카드에서 되읽었다) — `최종 = w·원값 + (1−w)·리그`, `w = min(1, n/8)`,
   `원값 = 홈 득점/경기 ÷ 원정 득점/경기`(그 팀의 그 시즌), `n = min(홈 수, 원정 수)`.
   ⚠️ 확인: 브리스톨 0.5·0.800 + 0.5·1.120 = **0.960**(카드와 같다) ·
      카디프 0.62·1.400 + 0.38·1.120 = **1.294**(카드 1.295).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

CAP = 1.4          # 🔴 카드에 보이는 팀별 홈 효과 상한(1.400 이 여러 번 나온다)
FULL = 8           # 🔴 수축이 1 이 되는 쌍 수


def rows_all() -> list[dict]:
    out, seen = [], set()
    for path in sorted((ROOT / "var/judge").glob("replay_*.json")):
        try:
            got = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        for r in (got if isinstance(got, list) else []):
            if not isinstance(r, dict) or r.get("hg") is None:
                continue
            key = (r.get("league"), r.get("day"), r.get("home"), r.get("away"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def main() -> int:
    rows = sorted(rows_all(), key=lambda r: str(r.get("day") or ""))
    print(f"# 🔴🔴 홈 배율 점검 — 백필 **{len(rows)}경기**")
    print()

    # ── ① 기준율 ──────────────────────────────────────────────────
    hw = sum(1 for r in rows if int(r["hg"]) > int(r["ag"]))
    dr = sum(1 for r in rows if int(r["hg"]) == int(r["ag"]))
    aw = len(rows) - hw - dr
    n = len(rows) or 1
    print(f"## ① 기준율 — 홈 승 **{100*hw/n:.1f}%** · 무 {100*dr/n:.1f}% · "
          f"원정 승 {100*aw/n:.1f}% · 홈 득점 몫 "
          f"{100*sum(int(r['hg']) for r in rows)/max(1, sum(int(r['hg'])+int(r['ag']) for r in rows)):.1f}%")
    gh = st.mean([int(r["hg"]) for r in rows])
    ga = st.mean([int(r["ag"]) for r in rows])
    print(f"- 경기당 홈 {gh:.3f}골 · 원정 {ga:.3f}골 → **실측 홈 배율 "
          f"{gh/ga:.3f}**(리그 표가 쓰는 ×1.120 과 비교)")

    # ── ② 팀별 홈 효과(그 경기 이전만) → 다음 홈 경기 ─────────────
    seen: dict[tuple, dict] = {}
    out: list[dict] = []
    for r in rows:
        lg, se = str(r.get("league")), str(r.get("season"))
        h, a = str(r.get("home")), str(r.get("away"))
        hg, ag = int(r["hg"]), int(r["ag"])
        kh = seen.setdefault((lg, se, h), {"hgf": 0, "hn": 0,
                                           "agf": 0, "an": 0})
        ka = seen.setdefault((lg, se, a), {"hgf": 0, "hn": 0,
                                           "agf": 0, "an": 0})
        # 🔴 **그 경기 이전 기록만**으로 배율을 만든다(누설 금지)
        pair = min(kh["hn"], kh["an"])
        if pair >= 2 and kh["agf"] > 0:
            raw = min(CAP, (kh["hgf"] / kh["hn"]) / (kh["agf"] / kh["an"]))
            w = min(1.0, pair / FULL)
            out.append({"mul": w * raw + (1 - w) * 1.120, "raw": raw,
                        "w": w, "n": pair,
                        "res": 0 if hg > ag else (1 if hg == ag else 2),
                        "league": lg, "home": h, "day": r.get("day")})
        kh["hgf"] += hg
        kh["hn"] += 1
        ka["agf"] += ag
        ka["an"] += 1
    print()
    print(f"## ② 팀별 홈 효과(이전 경기만) → **그 다음 홈 경기** "
          f"{len(out)}건")
    print()
    print("| 배율 구간 | 경기 | 평균 배율 | 홈 승 실측 | 무 | 원정 승 "
          "| 원값 평균 | 쌍 n 평균 |")
    print("|---|---|---|---|---|---|---|---|")
    ys = sorted(out, key=lambda x: x["mul"])
    k = max(1, len(ys) // 5)
    for i in range(5):
        part = ys[i * k:(i + 1) * k] if i < 4 else ys[4 * k:]
        if not part:
            continue
        m = len(part)
        print(f"| {i+1}분위({part[0]['mul']:.2f}~{part[-1]['mul']:.2f}) | {m} "
              f"| {st.mean([x['mul'] for x in part]):.3f} | "
              f"**{100*sum(1 for x in part if x['res']==0)/m:.1f}%** | "
              f"{100*sum(1 for x in part if x['res']==1)/m:.1f}% | "
              f"{100*sum(1 for x in part if x['res']==2)/m:.1f}% | "
              f"{st.mean([x['raw'] for x in part]):.3f} | "
              f"{st.mean([x['n'] for x in part]):.1f} |")
    top = ys[int(0.8 * len(ys)):]
    rest = ys[:int(0.8 * len(ys))]
    if top and rest:
        print()
        print(f"- **상위 20%**(배율 평균 {st.mean([x['mul'] for x in top]):.3f})"
              f" 홈 승 실측 **{100*sum(1 for x in top if x['res']==0)/len(top):.1f}%**"
              f" ↔ 나머지 80%(평균 {st.mean([x['mul'] for x in rest]):.3f}) "
              f"{100*sum(1 for x in rest if x['res']==0)/len(rest):.1f}%"
              f" → 차 **{100*(sum(1 for x in top if x['res']==0)/len(top) - sum(1 for x in rest if x['res']==0)/len(rest)):+.1f}%p**")
        # 🔴 시즌 초(쌍 4 이하)만 따로
        early = [x for x in ys if x["n"] <= 4]
        if early:
            e_top = sorted(early, key=lambda x: x["mul"])[int(0.8*len(early)):]
            print(f"- 시즌 초(쌍 ≤4 · {len(early)}건) 상위 20% 홈 승 "
                  f"**{100*sum(1 for x in e_top if x['res']==0)/max(1,len(e_top)):.1f}%**"
                  f" ↔ 그 구간 전체 "
                  f"{100*sum(1 for x in early if x['res']==0)/len(early):.1f}%")

    # ── ③ 리그 ×1.120 이 시즌별 실측과 맞나 ───────────────────────
    print()
    print("## ③ 리그 홈 이점 — 시즌별 실측")
    print()
    print("| 리그·시즌 | 경기 | 홈 승 | 원정 승 | 홈 득점 몫 | 실측 배율 |")
    print("|---|---|---|---|---|---|")
    box: dict[tuple, list] = {}
    for r in rows:
        box.setdefault((str(r.get("league")), str(r.get("season"))),
                       []).append(r)
    for key, part in sorted(box.items(), key=lambda kv: -len(kv[1]))[:10]:
        m = len(part)
        h = sum(int(x["hg"]) for x in part)
        a = sum(int(x["ag"]) for x in part)
        print(f"| {key[0]} {key[1]} | {m} | "
              f"{100*sum(1 for x in part if int(x['hg'])>int(x['ag']))/m:.1f}% | "
              f"{100*sum(1 for x in part if int(x['hg'])<int(x['ag']))/m:.1f}% | "
              f"{100*h/max(1,h+a):.1f}% | **{h/max(1,a):.3f}** |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
