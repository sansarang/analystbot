"""🔴🔴 **P0 하루 캐시 예열**(수정 지시 2026-10-13 밤 P0).

```
PYTHONPATH=. python tools/warm_cache.py --comp league:ACLE --comp league:ACL2
```

> 캐시: 팀 과거 경기·대회 일정·순위표·신원표는 **하루 1회 미리 받아 둔다.**
> 카드 실행 때는 새로 받는 건 **XI·결장·72시간 기사만.**

🔴 받는 것 — ① 대회 일정(시즌 포함) ② 그 창의 **두 팀 페이지**(과거 경기·순위표·
   감독 이력이 한 장에 있다) ③ 팀 이름표(`teams.json`).
🔴 **같은 주소를 카드 실행이 다시 받지 않게** `Net(day_cache=True)` 로 받아
   `var/daycache/` 에 둔다(24시간 안의 파일만 쓴다 · `Net.DAY_TTL_SEC`).
⚠️ XI·결장·뉴스는 **담지 않는다** — 그 주소는 `Net.DAY_CACHE` 목록에 없다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


async def main(argv: list[str]) -> int:
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.core import discover as _d
    from app.net import Net
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", action="append", required=True)
    ap.add_argument("--hours", type=float, default=36.0)
    args = ap.parse_args(argv[1:])
    net = Net(cache=True, day_cache=True)
    now = datetime.now(timezone.utc)
    print("# 🔴🔴 P0 하루 캐시 예열")
    print()
    got_n = 0
    teams: set[str] = set()
    for comp in args.comp:
        ids = [str(x) for x in ((_cp.row_of(comp).get("sources") or {})
                                .get("fotmob_ids") or [])]
        if not ids:
            print(f"- 🔴 `{comp}` fotmob id 가 표에 없다")
            continue
        rows = await fm.league_matches(net, ids[0])
        got_n += 1
        said = 0
        for r in rows:
            one = str(r.get("utc") or "")
            if not one:
                continue
            when = datetime.fromisoformat(one.replace("Z", "+00:00"))
            if not (now - timedelta(hours=3) <= when
                    <= now + timedelta(hours=args.hours)):
                continue
            said += 1
            teams.add(str(r.get("home") or ""))
            teams.add(str(r.get("away") or ""))
        print(f"- `{comp}` 일정 {len(rows)}경기 · 창 안 {said}경기")
    idx = await fm.team_index(net)
    print(f"- 팀 이름표 {len(idx)}개")
    ok = 0
    for name in sorted(x for x in teams if x):
        rows = _d._slug_hit(idx, name)[:1]
        if not rows:
            print(f"  · 🔴 `{name}` 팀 번호를 못 찾았다")
            continue
        tid, slug = rows[0]
        page = await net.get(fm.team_fixtures_url(tid, slug))
        ok += 1 if getattr(page, "ok", False) else 0
        print(f"  · {name} → 팀 페이지 "
              + ("✅" if getattr(page, "ok", False) else "🔴"))
    box = Path(Net.DAY_DIR)
    files = sorted(box.glob("*.html")) if box.exists() else []
    print()
    print(f"🔴 **예열 끝** — 대회 {got_n}개 · 팀 {ok}/{len(teams)}개 · "
          f"캐시 파일 **{len(files)}개**(`{Net.DAY_DIR}` · 24시간)")
    print("⚠️ 카드 실행은 이제 **XI·결장·72시간 기사만** 새로 받는다 — "
          "팀 페이지·대회 일정·순위표는 이 캐시에서 온다")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
