"""🔴🔴 **라인업 폴링 → 확정 XI 즉시 실행**(예측 지시 2026-10-13 23:10 KST).

```
PYTHONPATH=. python tools/xi_watch.py --match 6050078 \
    --name "Al-Sadd vs Al Hilal" --board "승무패 5.00 4.40 1.53" \
    --fallback 00:29 --deadline 00:59
```

> 23:29(T−90분)부터 fotmob 라인업 **5분 폴링** → 두 팀 확정 XI 가 뜨는 **즉시**
> 분석 실행. 00:29(T−30분)까지 확정 XI 가 안 뜨면 그 시각에 **예상 XI 판**으로
> 실행하고, 이후 XI 가 뜨면 **바로 재분석**. 킥오프 이후 실행 금지.

🔴 실행은 **실제 핸들러**(`cmd_deep`)다(프로브 금지 · #12) · 보드 글은 질문
   **아래 줄**로 넣는다(그 핸들러가 읽는 꼴).
🔴 라인업 상태는 `fotmob.lineup_kind_of` 하나가 말한다(사본 금지).
⚠️ 킥오프를 지나면 **실행하지 않는다** — 그 사실을 적고 끝낸다(사후 카드 금지).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, time as _time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KST = timezone(timedelta(hours=9))
POLL_SEC = 300


def _at(said: str) -> datetime:
    """🔴 `00:29`(KST) → 오늘/내일 그 시각(UTC)."""
    h, m = (int(x) for x in str(said).split(":"))
    now = datetime.now(KST)
    got = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if got < now - timedelta(hours=6):
        got += timedelta(days=1)
    return got.astimezone(timezone.utc)


async def state_of(net, mid: str) -> tuple[str, list[int], str]:
    """🔴 그 경기의 라인업 상태 · 양 팀 선발 수 · 사유."""
    from app.collect import fotmob as fm
    got = await net.get(fm.match_url(str(mid)))
    j = fm.payload(getattr(got, "text", "") or "")
    if not j:
        return "", [], "🔴 경기 페이지를 못 읽었다"
    said = fm.lineup_kind_of(j)
    n = [len(fm._names(fm._side(j, w))) for w in ("homeTeam", "awayTeam")]
    return said, n, f"라인업 `{said}` · 선발 {n}"


async def run_card(name: str, board: str, *, tag: str) -> None:
    """🔴 **실제 핸들러**로 카드를 낸다(보드는 질문 아래 줄)."""
    import app.bot.main as _bm
    from app import cassette
    os.environ[cassette.MATCH_ENV] = name
    said = f"/자세히 {name}"
    if board:
        said += f"\n보드: {board}"

    class _Msg:
        text = said

        async def answer(self, text: str, **kw) -> None:
            print(text)
    print(f"\n▶ {tag} — {datetime.now(KST):%H:%M:%S} KST 실행", flush=True)
    try:
        await _bm.cmd_deep(_Msg())
    except Exception as exc:                                # noqa: BLE001
        print(f"🔴 카드가 터졌다: {exc!r:.300}")
    print(f"◀ {tag} — 끝 {datetime.now(KST):%H:%M:%S} KST", flush=True)


async def main(argv: list[str]) -> int:
    from app.net import Net
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--board", default="")
    ap.add_argument("--fallback", required=True, help="예상 판 퇴로 시각(KST)")
    ap.add_argument("--deadline", required=True, help="킥오프(KST)")
    args = ap.parse_args(argv[1:])
    fb, ko = _at(args.fallback), _at(args.deadline)
    net = Net(cache=False)
    print(f"# 🔴🔴 라인업 폴링 — {args.name}")
    print(f"- 퇴로 {fb.astimezone(KST):%H:%M} KST · 킥오프 "
          f"{ko.astimezone(KST):%H:%M} KST · {POLL_SEC // 60}분 간격")
    said_pre = False
    while True:
        now = datetime.now(timezone.utc)
        if now >= ko:
            print(f"🔴 **킥오프를 지났다**({now.astimezone(KST):%H:%M} KST) — "
                  f"실행하지 않는다(사후 카드 금지)")
            return 0
        said, n, why = await state_of(net, args.match)
        print(f"  · {now.astimezone(KST):%H:%M:%S} KST — {why}", flush=True)
        if said == "confirmed" and min(n or [0]) >= 11:
            await run_card(args.name, args.board, tag="확정 XI 판")
            return 0
        if now >= fb and not said_pre:
            # 🔴 퇴로 — **예상 XI 판**을 내고 폴링을 계속한다
            await run_card(args.name, args.board, tag="예상 XI 판(퇴로)")
            said_pre = True
        await asyncio.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
