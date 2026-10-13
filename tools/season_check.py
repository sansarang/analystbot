"""🔴🔴 **달력 규칙 검증** — 덤프의 **fotmob 시즌 글자**와 맞나(2026-10-13).

```
PYTHONPATH=. python tools/season_check.py
```

🔴 `config/season_rules.yaml` 의 추춘제/단일 연도 판단을 **받아 둔 자료로** 검증한다
   (fotmob 이 `2025/2026` 이라고 적으면 추춘제 · `2025` 면 단일 연도).
⚠️ 실사고 2026-10-13: 열쇠를 지어내고(`league:LL`) 챔피언십을 빼먹어 격자에서
   **500경기가 떨어졌다**. 그 뒤로 이 검증을 **표를 고칠 때마다** 돌린다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUMPS = ("replay_big2", "replay_mls", "replay_elc", "replay_sa", "replay_pl")


def main(argv: list[str]) -> int:
    from app.core import season as se
    print("# 🔴🔴 달력 규칙 검증 — 규칙 vs fotmob 시즌 글자")
    print()
    print("| 리그 | 경기 | 규칙이 낸 시즌 | fotmob 글자 | 맞나 |")
    print("|---|---|---|---|---|")
    bad = 0
    for name in DUMPS:
        path = ROOT / f"var/judge/{name}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        by: dict[str, Counter] = {}
        for r in rows:
            league = str(r.get("league") or "")
            at = datetime.fromisoformat(f"{r['day']}T12:00:00+00:00")
            got, _w = se.id_of(league=league, when=at)
            by.setdefault(league, Counter())[(got, str(r.get("season") or ""))] += 1
        for league, box in by.items():
            for (got, said), n in box.most_common(3):
                # 🔴 추춘제면 글자에 `/` 가 있어야 하고, 단일 연도면 없어야 한다
                ok = (("/" in got) == ("/" in said)) and bool(got)
                bad += 0 if ok else n
                print(f"| {league} | {n} | `{got or '⬜'}` | `{said or '⬜'}` | "
                      + ("✅" if ok else "🔴 **어긋난다**") + " |")
    print()
    print(("🔴 **어긋난 경기 %d건** — 규칙 표를 고쳐야 한다" % bad) if bad
          else "✅ **전부 맞는다**(추춘제/단일 연도가 fotmob 글자와 같다)")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
