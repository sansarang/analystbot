"""🔴🔴 **P0 슬레이트 스케줄러**(수정 지시 2026-10-13 밤 P0).

```
PYTHONPATH=. python tools/slate_queue.py --comp league:ACLE
PYTHONPATH=. python tools/slate_queue.py --comp league:ACLE --run
```

> 슬레이트 스케줄러: 그날 대상 경기 **전부를 킥오프 순으로 큐에 올리고** 각 단계
> 시각을 카드 머리에 찍는다(T−24h/T−3h/XI 확정 판 각각).
> 사전 실행: T−24h 기본 → T−3h 갱신 → 확정 XI 뜨면 즉시 ⑲.

🔴 단계 시각을 세는 곳은 `app/core/slate.py` **하나**다(사본 금지).
🔴 `--run` 은 **실제 핸들러**(`cmd_deep`)를 부른다(CLAUDE.md #12 프로브 금지) ·
   카드 한 장에 **15분 상한**(`core/deadline.CARD_CAP_MIN`)을 건다.
⚠️ 킥오프를 지난 경기는 **돌리지 않는다**(사후 기록용 카드를 새로 만들지 않는다) —
   그 사실을 큐에 적는다.
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


async def fixtures(comp: str, *, hours: float) -> tuple[list[dict], str]:
    """🔴 그 대회의 **다가오는 경기**(지금부터 `hours` 안) — 일정 한 장에서."""
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.net import Net
    ids = [str(x) for x in ((_cp.row_of(comp).get("sources") or {})
                            .get("fotmob_ids") or [])]
    if not ids:
        return [], f"🔴 `{comp}` 의 fotmob id 가 표에 없다"
    net = Net(cache=True)
    rows = await fm.league_matches(net, ids[0])
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for r in rows:
        said = str(r.get("utc") or "")
        if not said:
            continue
        when = datetime.fromisoformat(said.replace("Z", "+00:00"))
        if not (now - timedelta(hours=3) <= when
                <= now + timedelta(hours=hours)):
            continue
        out.append({"name": f"{r.get('home')} vs {r.get('away')}",
                    "kickoff": when, "finished": bool(r.get("finished"))})
    return out, f"일정 {len(rows)}경기 중 창 안 **{len(out)}경기**"


async def main(argv: list[str]) -> int:
    from app.core import deadline as _dl
    from app.core import slate as _sl
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", action="append", required=True)
    ap.add_argument("--hours", type=float, default=36.0)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv[1:])
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    print("# 🔴🔴 P0 슬레이트 큐")
    print()
    for comp in args.comp:
        got, why = await fixtures(comp, hours=args.hours)
        print(f"- `{comp}` — {why}")
        for one in got:
            one["comp"] = comp
        rows += got
    box = _sl.queue(rows, now=now)
    print()
    print("| 킥오프(KST) | 경기 | 대회 | 지금 단계 | 기본 T−24h | 갱신 T−3h | "
          "XI T−1h |")
    print("|---|---|---|---|---|---|---|")
    for one in box:
        t = one["times"]
        src = next((r["comp"] for r in rows
                    if r["name"] == one["name"]), "")
        print(f"| {one['kickoff'].astimezone(KST):%m-%d %H:%M} | "
              f"{one['name']} | `{src}` | **{one['stage']}** | "
              + " | ".join(f"{t[k].astimezone(KST):%m-%d %H:%M}"
                           for k in ("기본", "갱신", "XI")) + " |")
    print()
    due = [one for one in box if one["stage"] in ("기본", "갱신", "XI")]
    print(f"🔴 **지금 돌릴 경기 {len(due)}건** — "
          + (" · ".join(f"{x['name']}({x['stage']})" for x in due)
             if due else "없다"))
    gone = [one for one in box if one["stage"] == "사후"]
    if gone:
        print(f"⚠️ **킥오프를 지났다 {len(gone)}건** — 새 카드를 만들지 않는다"
              f"(사후 기록용) — " + " · ".join(x["name"] for x in gone))
    if not args.run:
        print()
        print("⏸ `--run` 을 주면 **실제 핸들러**(`cmd_deep`)로 차례로 돈다 "
              f"· 카드 한 장 상한 **{_sl.CARD_CAP_MIN:g}분**")
        return 0
    # ── 🔴 실제 핸들러로 차례로 돈다(프로브 금지 · #12)
    import app.bot.main as _bm
    from app import cassette
    import os
    for one in due:
        said = one["name"]
        print(f"\n▶ {said} — {one['stage']} 단계 시작 "
              f"{datetime.now(KST):%H:%M:%S} KST", flush=True)
        os.environ[cassette.MATCH_ENV] = said
        clock = _dl.Deadline(_sl.CARD_CAP_MIN)

        class _Msg:
            text = f"/자세히 {said}"

            async def answer(self, text: str, **kw) -> None:
                print(text)
        try:
            await _bm.cmd_deep(_Msg())
        except Exception as exc:                            # noqa: BLE001
            print(f"🔴 {said} — 카드가 터졌다: {exc!r:.200}")
        print(f"◀ {said} — {clock.said_of()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
