"""🔴🔴 **§8 합격표 1경기 실행기** — 실제 핸들러(`cmd_analyze`)를 부른다.

지시서 §8: *"실제 경기 3개를 **실제 핸들러**(`cmd_analyze`)로 돌린다."*
CLAUDE.md #12: *"프로브 금지 … 임시 스크립트가 필요하면 **실제 핸들러를
`import` 해서** 부른다."*

```
PYTHONPATH=. python tools/run_stage8.py "France vs Belgium" [--at 02:35]
```

🔴 `--at HH:MM`(KST)을 주면 **그 시각까지 기다렸다가** 돈다(T-70분 실행용).
🔴 비용·벽시계를 §8 상한(≤$0.5 · ≤6분)과 대조해 찍는다.
⚠️ 발송하지 않는다 — `cmd_analyze` 는 답을 **돌려주는** 경로다(§11-11 과 무관).
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


class _Msg:
    """🔴 `cmd_analyze` 가 받는 것의 **최소 모양** — `text` 와 `answer`."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.chunks: list[str] = []

    async def answer(self, body: str) -> None:        # noqa: D102
        self.chunks.append(str(body))
        print(str(body), flush=True)


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('쓰는 법: tools/run_stage8.py "<팀> vs <상대>" [--at HH:MM(KST)]')
        return 2
    arg = argv[1]
    at = ""
    if "--at" in argv:
        at = argv[argv.index("--at") + 1]
    if at:
        hh, mm = (int(x) for x in at.split(":"))
        now = datetime.now(KST)
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        print(f"[run_stage8] {target:%Y-%m-%d %H:%M} KST 까지 "
              f"{wait / 60:.1f}분 기다린다", flush=True)
        while True:
            left = (target - datetime.now(KST)).total_seconds()
            if left <= 0:
                break
            time.sleep(min(60.0, left))
        print(f"[run_stage8] 깨어났다 — {datetime.now(KST):%H:%M:%S} KST", flush=True)

    from app import solar
    from app.bot.main import cmd_analyze

    ok, why = solar.gate()
    mo0, d0 = solar.spent()
    print(f"[run_stage8] 예산 — 월 ${mo0:.4f} · 오늘(UTC) ${d0:.4f} · "
          f"게이트 {'열림' if ok else '닫힘: ' + why}", flush=True)
    if not ok:
        return 3
    t0 = time.monotonic()
    msg = _Msg(f"/analyze {arg}")
    await cmd_analyze(msg)                      # 🔴 **실제 핸들러**다
    secs = time.monotonic() - t0
    mo1, d1 = solar.spent()
    used = d1 - d0
    print("\n" + "=" * 66, flush=True)
    print(f"[§8 수치] 벽시계 {secs / 60:.1f}분 (상한 6분) "
          f"{'✓' if secs <= 360 else '🔴 ✗'}", flush=True)
    print(f"[§8 수치] 비용 ${used:.4f} (상한 $0.5) "
          f"{'✓' if used <= 0.5 else '🔴 ✗'}", flush=True)
    print(f"[§8 수치] 예산 뒤 — 월 ${mo1:.4f} · 오늘(UTC) ${d1:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(main(sys.argv)))
