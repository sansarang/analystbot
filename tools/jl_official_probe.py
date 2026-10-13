"""🔴🔴 **§6-6 전용 통로 — 지금 무엇을 주나**(지시서 2026-10-13 밤 셋째).

```
PYTHONPATH=. python tools/jl_official_probe.py
```

🔴 **L2** — 이 공시는 **현재 값**이다(오늘의 정지 목록) → **운영 전용**이고
   백필·재현에는 쓰지 않는다. 그래서 **얻는 이득은 앞으로 쌓이는 운영 카드로만**
   잴 수 있다(과거 카드에 소급해 쓸 수 없다 · 그 사실을 보고가 적는다).
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


async def main(argv: list[str]) -> int:
    from app.collect import jl_official as jo
    from app.core.search import sources as sr
    from app.net import Net
    net = Net(cache=True)
    print("# 🔴🔴 §6-6 J리그 전용 통로 — 지금 받은 것")
    print()
    page = await net.get(jo.SUSPEND)
    rows, why = jo.suspensions(getattr(page, "text", "") or "")
    print(f"- {why} · 주소 `{jo.SUSPEND}`")
    grade, why_g = sr.grade_of(jo.SUSPEND, league="league:J1")
    ok, why_h = sr.hard_ok([grade], league="league:J1")
    print(f"- 원천 등급 **{grade}** · {why_g} → hard 로 쓸 수 있나: "
          f"{'✅' if ok else '🔴'} {why_h}")
    print()
    if rows:
        print("| 선수 | 팀 | 정지 | 대상 경기(날짜) |")
        print("|---|---|---|---|")
        for one in rows:
            print(f"| {one['player']} | {one['team']} | {one['kind']} | "
                  f"{one['day']} |")
        print()
        box = Counter(r["team"] for r in rows)
        print("- 팀별 — " + " · ".join(f"{k} {v}명"
                                       for k, v in box.most_common()))
        # 🔴 **경기 단위로 고르는 문**도 실제로 지난다(팀 별칭 + 날짜)
        said_team = box.most_common(1)[0][0]
        said_day = rows[0]["day"]
        got, why2 = jo.for_match(rows, team_names=[said_team],
                                 day=said_day)
        print(f"- 경기 단위 고르기 — `{said_team}` · {said_day} → {why2}")
        del got
    print()
    print("⚠️ **L2** — 과거 카드에 **소급해 쓸 수 없다**(현재 값이다). 이득은"
          " 앞으로 쌓이는 운영 카드의 §6-7 재현율로만 잰다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
