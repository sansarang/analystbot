"""🔴🔴 **대회 표기를 다시 잰다** — 사용자 지시 2026-10-09(4차) §1.

> 지금 등록된 리그 전부를 ESPN·fotmob·football-data 세 출처에서 **실제로 받아**
> 표기를 확인하고 채운다. **확인한 날짜를 적는다.**

```
PYTHONPATH=. python tools/check_competitions.py            # 전부 다시 잰다
PYTHONPATH=. python tools/check_competitions.py J1 KL1     # 둘만
```

🔴 이 도구는 `config/competitions.yaml` 의 **표기를 대조**한다 — 맞으면 ✅, 틀리거나
   못 받으면 🔴 이고 **무엇이 왔는지** 찍는다. ⚠️ 파일을 **고치지 않는다**(사람이
   보고 고친다 — 자동으로 덮으면 503 같은 일시 장애가 표를 지운다).
🔴 대조 방법은 표의 주석과 **같은 것**이다(사본 금지 — 거기 적힌 경로를 쓴다).
"""
from __future__ import annotations

import asyncio
import json
import sys


async def _espn(net, slug: str, want: list[str]) -> tuple[bool, str]:
    """🔴 ESPN — `scoreboard/_/league/{슬러그}` 본문에 그 리그 이름이 있나."""
    g = await net.get(f"https://www.espn.com/soccer/scoreboard/_/league/{slug}")
    t = (getattr(g, "text", "") or "").lower()
    if not t:
        return False, f"HTTP {getattr(g, 'status', None)}"
    hit = [w for w in want if w.lower() in t]
    return bool(hit), (f"이름 맞음 {hit[:1]}" if hit else "이름 안 맞음")


async def _fotmob(net, lid: object, want: list[str]) -> tuple[bool, str]:
    """🔴 fotmob — `leagues/{id}/table/x` 의 `leagueName`(+`ccode`)."""
    from app.collect import fotmob as fm
    g = await net.get(f"https://www.fotmob.com/leagues/{lid}/table/x")
    j = fm.payload(getattr(g, "text", "") or "")
    if not j:
        return False, f"HTTP {getattr(g, 'status', None)}"
    blk = (fm._page(j).get("table") or [])
    box = (blk[0].get("data") or {}) if blk else {}
    name = str(box.get("leagueName") or "")
    hit = [w for w in want if w.lower() in name.lower()]
    said = f"`{name}` ccode={box.get('ccode')}"
    return bool(hit), said


async def _fd(net, code: str, want: list[str]) -> tuple[bool, str]:
    """🔴 football-data — `competitions/{코드}` 의 `name`."""
    from app.collect import fdorg
    key = fdorg.api_key()
    if not key:
        return False, "키가 없다(`FOOTBALL_DATA_KEY`)"
    g = await net.get(f"https://api.football-data.org/v4/competitions/{code}",
                      headers={"X-Auth-Token": key})
    if not getattr(g, "ok", False):
        return False, f"HTTP {getattr(g, 'status', None)}"
    try:
        name = str(json.loads(getattr(g, "text", "") or "{}").get("name") or "")
    except ValueError:
        return False, "JSON 이 아니다"
    hit = [w for w in want if w.lower() in name.lower()]
    return bool(hit), f"`{name}`"


async def main(argv: list[str]) -> int:
    from app import net as _net_mod
    from app.core import competition as comp
    want_keys = {x.upper() for x in argv[1:] if not x.startswith("-")}
    net = _net_mod.Net()
    box = comp.rows()
    print(f"표의 `checked_at` — {comp.table().get('checked_at')}")
    bad = 0
    for key, row in box.items():
        short = comp.short_key(key)
        if want_keys and short.upper() not in want_keys:
            continue
        src = dict(row.get("sources") or {})
        # 🔴 기대 이름은 **표가 적어 둔 그 출처의 이름**이다(우리가 고르지 않는다)
        print(f"== {key}")
        for slug in [str(x) for x in (src.get("espn_slugs") or [])]:
            ok, why = await _espn(net, slug, [*(src.get("fotmob_names") or []),
                                              *(row.get("names") or [])])
            print(f"   espn   {slug:<8} {'✅' if ok else '🔴'} {why}")
            bad += 0 if ok else 1
        for slug in [str(x) for x in (src.get("espn_slugs_unverified") or [])]:
            ok, why = await _espn(net, slug, [*(src.get("fotmob_names") or []),
                                              *(row.get("names") or [])])
            mark = "✅ **이제 확인됐다 — 표를 고쳐라**" if ok else "⚠️ 여전히 못 받는다"
            print(f"   espn?  {slug:<8} {mark} {why}")
        for lid in (src.get("fotmob_ids") or []):
            ok, why = await _fotmob(net, lid, src.get("fotmob_names") or
                                    (row.get("names") or []))
            print(f"   fotmob {str(lid):<8} {'✅' if ok else '🔴'} {why}")
            bad += 0 if ok else 1
        if src.get("football_data"):
            ok, why = await _fd(net, str(src["football_data"]),
                                src.get("football_data_names") or [])
            print(f"   fd     {str(src['football_data']):<8} "
                  f"{'✅' if ok else '🔴'} {why}")
            bad += 0 if ok else 1
            # ⚠️ 무료 티어는 분당 10회다 — 하나씩 부르고 **기다린다**
            await asyncio.sleep(7)
    print(f"\n🔴 안 맞은 칸 {bad}개" if bad else "\n✅ 표의 모든 칸이 맞았다")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
