"""🔴🔴 **보드 사다리 실측**(의심 검증 통합본 v2 · 2026-10-14i §1 보고 1번).

```
PYTHONPATH=. uv run python tools/board_ladder.py --comp league:ELC --comp league:UCL \
    --comp league:ACLE --hours 36
PYTHONPATH=. uv run python tools/board_ladder.py --comp league:UCL --feed   # ③ 까지
```

> 사다리 ① 캡처 → ② 공개 페이지 → ③ 배당 API → ④(통로 없음) 가 **그날 슬레이트
> 전부**에서 어디까지 가는가. 출처별 성공률을 센다.

🔴 일정은 `tools/slate_queue.fixtures` **그 함수**를 부른다(사본 금지).
🔴 보드는 `app/core/boardfeed.of` **그 함수**다 — 여기서 다시 짜지 않는다.
⚠️ `--feed`(③)는 **크레딧을 쓴다**(경기당 1 · 월 500) → ② 가 실패한 경기에만 건다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KST = timezone(timedelta(hours=9))


def _feed_why(comp: str) -> str:
    """🔴 그 대회가 **배당 피드의 종목 표에 없는 까닭**. 있으면 빈 글자.

    ⚠️ 없으면 ③ 는 영원히 0건이다 — 실측 2026-10-06: 이 피드에 **AFC·대표팀
       친선·CONCACAF 가 없다**. 그 자리는 ④(공개 비교 사이트)가 메워야 한다.
    🔴 표를 읽는 곳은 `odds.sport_key_for` **하나**다(사본 금지).
    """
    from app.core import competition as _cp
    from app.core import odds as _od
    said = str(((_cp.row_of(comp).get("sources") or {})
                .get("fotmob_names") or [comp])[0])
    feeds, whys = _od.ready_feeds()
    if not feeds:
        return "피드 키가 없다 — " + " · ".join(whys)
    out = []
    for f in feeds:
        got, why = _od.sport_key_for(f, said, label=said)
        if got:
            return ""
        out.append(f"{f.get('name')}: {why}")
    return " · ".join(out)


def _cell(board, market: str) -> str:
    """🔴 그 마켓 줄을 한 칸으로. 없으면 ⬜(조용한 0 금지 — 빈 칸을 적는다)."""
    got = [r for r in board.rows if r.market in (("win", "draw")
                                                 if market == "win"
                                                 else (market,))]
    if not got:
        return "⬜"
    if market == "win":
        by = {r.side: r for r in got}
        return " / ".join(f"{by[s].price:g}" if by.get(s) and by[s].price
                          else "⬜" for s in ("home", "draw", "away"))
    point = next((r.point for r in got if r.point is not None), None)
    by = {r.side: r for r in got}
    sides = ("home", "away") if market == "handicap" else ("over", "under")
    said = " / ".join(f"{by[s].price:g}" if by.get(s) and by[s].price
                      else "⬜" for s in sides)
    return f"{abs(float(point or 0)):g}({said})"


async def _feed_board(one: dict, comp: str, *, pool, net):
    """🔴 ③ — 배당 API 로 그 경기 보드. 쓰이는 길은 `odds.from_feed` 하나다."""
    from app import teamref
    from app.core import boardfeed as _bf
    from app.core import competition as _cp
    from app.core import odds as _od
    from app.core.schema import MatchRef
    from app.core.state import RunState
    names = [x.strip() for x in str(one["name"]).split(" vs ")]
    if len(names) < 2:
        return None, "이름을 둘로 못 갈랐다"
    hk, _ = teamref.key_or_issue(names[0], sport="soccer", league=comp)
    ak, _ = teamref.key_or_issue(names[1], sport="soccer", league=comp)
    said = ((_cp.row_of(comp).get("sources") or {}).get("fotmob_names")
            or [comp])[0]
    ref = MatchRef(id=f"ladder:{comp}:{one['name']}", sport="soccer",
                   competition=str(said), competition_short=str(said),
                   home=hk, away=ak,
                   home_name=names[0], away_name=names[1],
                   kickoff_utc=one["kickoff"])
    st = RunState(match_key="board_ladder")
    got = await _od.from_feed(ref, pool=pool, net=net, state=st)
    if not (getattr(got, "quotes", None) or []):
        return None, str(getattr(got, "why", "") or "피드 0줄")
    board = _bf.from_feed(got)
    return (_bf.pick_domestic(board) if board else None), ""


async def main(argv: list[str]) -> int:
    from app.core import boardfeed as _bf
    from app.net import Net
    from slate_queue import fixtures as _fx
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", action="append", required=True)
    ap.add_argument("--hours", type=float, default=36.0)
    ap.add_argument("--back", type=float, default=3.0,
                    help="뒤로 몇 시간까지 — 그날 끝난 슬레이트까지 세려면 늘린다")
    ap.add_argument("--feed", action="store_true",
                    help="② 가 실패한 경기에 ③ 배당 API 를 건다(크레딧 1/경기)")
    args = ap.parse_args(argv[1:])
    net = Net(cache=True)
    rows_fx, why = await _bf.fixtures_rows(net)
    codes = sorted({str(r.get("Div") or "?") for r in rows_fx})
    print("# 🔴🔴 보드 사다리 실측 — 별칭표·여자팀 가름 **넣은 뒤**")
    print()
    print(f"- 지금 {datetime.now(KST):%Y-%m-%d %H:%M} KST")
    print(f"## ② 공개 페이지 — {why}")
    print(f"- 리그 코드 {codes}")
    print()
    pool = None
    if args.feed:
        from app.config import get_settings
        from app.db import get_pool
        pool = await get_pool(get_settings().database_url)
    games: list[dict] = []
    for comp in args.comp:
        got, said = await _fx(comp, hours=args.hours, back=args.back)
        print(f"- `{comp}` — {said}")
        for one in got:
            one["comp"] = comp
        games += got
    print()
    by_day: dict[str, list[dict]] = {}
    for one in games:
        by_day.setdefault(f"{one['kickoff'].astimezone(KST):%m-%d}",
                          []).append(one)
    tally: dict[str, int] = {}
    for day in sorted(by_day):
        box = sorted(by_day[day], key=lambda x: (x["comp"], x["name"]))
        print(f"### {day} — {len(box)}경기")
        print()
        print("| 경기 | 대회 | 출처 | 줄 수 | 승무패 | 핸디 | 언오버 | 비고 |")
        print("|---|---|---|---|---|---|---|---|")
        for one in box:
            board = await _bf.of(one["name"], net=net, fixtures=rows_fx)
            note = board.alarm or " · ".join(str(x) for x in board.extra[:2])
            if not board.rows and args.feed and pool is not None:
                got, why3 = await _feed_board(one, one["comp"], pool=pool,
                                              net=net)
                if got is not None and got.rows:
                    board, note = got, " · ".join(
                        str(x) for x in got.extra[:2])
                else:
                    note = f"🔴 ② 없음 · ③ {why3}"
            src = board.source or "🔴 실패"
            # 🔴🔴 **사후는 실패가 아니다** — 배당 API 는 **다가오는 이벤트만**
            #    목록에 둔다(킥오프를 지나면 사라진다 · 실측 2026-10-14). 그래서
            #    끝난 경기의 ③ 실패를 "예측 시점 실패"로 세면 성공률이 거짓이 된다.
            #    ⚠️ 그런데 **대회 자체가 피드에 없는 것**(AFC·대표팀 친선)은
            #       사후가 아니라 **진짜 구멍**이다 — ④ 가 필요한 자리다.
            late = one["kickoff"] < datetime.now(timezone.utc)
            if not board.rows:
                why_feed = _feed_why(one["comp"])
                if why_feed:
                    src = "🔴 실패(③ 에 그 대회가 없다 → ④ 필요)"
                    note = why_feed
                elif late:
                    src = "⏸ 사후(③ 목록에서 빠졌다)"
                    note = "킥오프를 지났다 — 피드 이벤트 목록에서 빠진다"
            tally[src] = tally.get(src, 0) + 1
            comp_short = str(one["comp"]).split(":")[-1]
            print(f"| {one['name'][:34]} | {comp_short} | {src} | "
                  f"{len(board.rows)} | {_cell(board, 'win')} | "
                  f"{_cell(board, 'handicap')} | {_cell(board, 'total')} | "
                  f"{note[:60]} |")
        print()
    print("## 출처별 — 전체")
    print()
    total = sum(tally.values()) or 1
    for src, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"- {src} — **{n}건**({n / total:.0%})")
    late = sum(n for k, n in tally.items() if k.startswith("⏸"))
    bad = sum(n for k, n in tally.items() if k.startswith("🔴"))
    ok = total - bad - late
    live = total - late or 1
    print()
    print(f"🔴 **보드 확보 {ok}/{total}({ok / total:.0%})** · "
          f"실패 {bad}건 · 사후 제외하면 **{ok}/{live}({ok / live:.0%})**")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
