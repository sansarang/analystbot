"""🔴🔴 **휴식일 재료**(후속 지시 2026-10-14g §3 — D1) — **컵·대륙 포함**.

```
PYTHONPATH=. python tools/fit_rest.py --league 48 --name league:ELC
```

⚠️ 실측 2026-10-14: 리그 덤프만으로 센 휴식일은 **걸린 경기 0건**이었다 —
   리그 경기 사이만 보니 간격이 과대 추정되고 컵·대륙 경기가 **안 보였다**.
🔴 그래서 **팀 페이지의 전 대회 일정**(`fixtures.allFixtures`)에서 날짜를 모은다.
🔴 판은 `data/rest/<리그>.yaml` — `{팀: [날짜…]}` 와 대회 이름이다(측정 전용).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


async def main(argv: list[str]) -> int:
    import yaml

    from app.collect import fotmob as fm
    from app.net import Net

    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append", required=True)
    ap.add_argument("--name", action="append", required=True)
    args = ap.parse_args(argv[1:])

    net = Net(cache=True, day_cache=True)
    for lid, name in zip(args.league, args.name):
        page = await net.get(fm.league_matches_url(lid, "x"))
        j = fm.payload(getattr(page, "text", "") or "") or {}
        pp = ((j.get("props") or {}).get("pageProps") or {})
        teams: dict[str, str] = {}
        for m in (((pp.get("fixtures") or {}).get("allMatches")) or []):
            for side in ("home", "away"):
                one = dict(m.get(side) or {})
                if one.get("name") and one.get("id"):
                    teams[str(one["name"])] = str(one["id"])
        print(f"리그 {lid}({name}) — 팀 {len(teams)}개", flush=True)
        out: dict[str, dict] = {}
        for i, (team, tid) in enumerate(sorted(teams.items()), 1):
            got = await net.get(fm.team_fixtures_url(tid, "x"))
            box = (((fm.payload(getattr(got, "text", "") or "") or {})
                    .get("props") or {}).get("pageProps") or {})
            said = ((box.get("fallback") or {}).get(f"team-{tid}") or {})
            rows = (((said.get("fixtures") or {}).get("allFixtures") or {})
                    .get("fixtures") or [])
            days = []
            for r in rows:
                st = dict(r.get("status") or {})
                if not st.get("finished") or st.get("cancelled"):
                    continue
                when = str(st.get("utcTime") or "")[:10]
                comp = str((r.get("tournament") or {}).get("name") or "")
                if when:
                    days.append({"day": when, "comp": comp})
            out[team] = {"id": tid, "n": len(days),
                         "days": sorted(days, key=lambda x: x["day"])}
            if i % 10 == 0:
                print(f"   … {i}/{len(teams)}", flush=True)
        path = ROOT / "data/rest" / f"{name.replace(':', '_')}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(out, allow_unicode=True,
                                       sort_keys=True), encoding="utf-8")
        comps = {d["comp"] for v in out.values() for d in v["days"]}
        print(f"🔴 판을 적었다 — `{path.relative_to(ROOT)}` · 경기 "
              f"{sum(v['n'] for v in out.values())}건 · 대회 {len(comps)}개"
              f"({' · '.join(sorted(comps)[:6])}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
