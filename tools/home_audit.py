"""🔴🔴 **5번 M1 팀별 홈 효과 감사**(검증만 · 얼린 코드 수정 금지).

```
PYTHONPATH=. python tools/home_audit.py var/judge/replay_fix.json
```

> 팀별 홈 배율의 **표본 쌍 수 분포** · **표본 < 5쌍 경기 비율** · 그 경기들의
> **적중률**(검증만 — 얼린 코드 수정 금지 · 3-3 손값 적합 때 반영).

🔴 팀별 홈 효과는 `legacy/old_engine.team_home_mul` 이 센다(얼린 코드 · K0):
   `홈 평균 득점 ÷ 원정 평균 득점`을 `TEAM_HOME_LO~HI`(0.80~1.40)로 자르고,
   표본 쌍 수 `n` 으로 **리그 배율 쪽으로 수축**한다(`min(n, 8)/8`).
   ⚠️ 그래서 `n` 이 작으면 그 경기의 홈 배율은 **거의 리그값**이다 — 그런데 실측
   코모–로마에서는 `n=3` 인데 ×1.179 가 나왔다(수축 가중 38%). 🔴 이 도구는 그런
   경기가 **얼마나 많고 그때 더 틀렸나**를 센다.
🔴 **고치지 않는다** — 재생 표본으로 **세기만** 한다(지시 5번).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 "표본이 적다"고 보는 쌍 수(지시 5번의 그 수)
FEW = 5


def main(argv: list[str]) -> int:
    said = [a for a in argv[1:] if not a.startswith("-")]
    raw = json.loads((ROOT / (said[0] if said
                              else "var/judge/replay_fix.json")
                      ).read_text(encoding="utf-8"))
    from app.core import metrics as _me
    rows = [r for r in raw if r.get("hit") is not None and r.get("hg")
            is not None]
    print("# 🔴🔴 5번 M1 팀별 홈 효과 감사(검증만)")
    print()
    print(f"재생 {len(rows)}경기 · 0-0 **{sum(1 for r in rows if int(r['hg']) == 0 and int(r['ag']) == 0)}경기**")
    print()
    # 🔴 그 경기 **앞**의 홈/원정 쌍을 센다(얼린 함수가 보는 그 목록과 같은 꼴)
    hist: dict[str, list[dict]] = {}
    pairs: list[int] = []
    for r in sorted(rows, key=lambda x: str(x.get("day") or "")):
        home = str(r.get("home") or "")
        said_rows = hist.get(home, [])
        n_home = sum(1 for x in said_rows if x["side"] == "home")
        n_away = sum(1 for x in said_rows if x["side"] == "away")
        r["pairs"] = min(n_home, n_away)
        pairs.append(r["pairs"])
        for team, side, gf, ga in (
                (home, "home", int(r["hg"]), int(r["ag"])),
                (str(r.get("away") or ""), "away", int(r["ag"]),
                 int(r["hg"]))):
            hist.setdefault(team, []).append({"side": side, "gf": gf,
                                              "ga": ga})
    print("| 표본 쌍 수 | 경기 | 비율 |")
    print("|---|---|---|")
    got = Counter(min(p, 8) for p in pairs)
    for k in sorted(got):
        print(f"| {k}{'+' if k == 8 else ''} | {got[k]} | "
              f"{got[k] / len(pairs):.1%} |")
    few = [r for r in rows if int(r.get("pairs") or 0) < FEW]
    print()
    print(f"🔴 **표본 {FEW}쌍 미만 경기 {len(few)}건 "
          f"({len(few) / len(rows):.1%})**")
    print()
    print("| 묶음 | 경기 | M1 방향 적중률 | 홈 승 실제 |")
    print("|---|---|---|---|")
    for name, box in (("표본 < 5쌍", few),
                      ("표본 ≥ 5쌍", [r for r in rows
                                    if int(r.get("pairs") or 0) >= FEW])):
        if not box:
            print(f"| {name} | 0 | — | — |")
            continue
        hit = sum(1 for r in box
                  if _me.direction_hit(list(r["ours"]), int(r["hit"])))
        home_win = sum(1 for r in box if int(r["hit"]) == 0)
        print(f"| {name} | {len(box)} | {hit / len(box):.1%} | "
              f"{home_win / len(box):.1%} |")
    print()
    print("⚠️ `ours` 는 재생의 **옛 구조(네 축)** 수다 — 운영 M1 과 같은 식이다.")
    print("🔴 이 표는 **세기만** 한다(얼린 코드 수정 금지 · 3-3 에서 반영).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
