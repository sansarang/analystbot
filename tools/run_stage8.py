"""🔴🔴 **§8 합격표 1경기 실행기** — 실제 핸들러(`cmd_analyze`)를 부른다.

지시서 §8: *"실제 경기 3개를 **실제 핸들러**(`cmd_analyze`)로 돌린다."*
CLAUDE.md #12: *"프로브 금지 … 임시 스크립트가 필요하면 **실제 핸들러를
`import` 해서** 부른다."*

```
PYTHONPATH=. python tools/run_stage8.py "France vs Belgium" [--at 02:35]
PYTHONPATH=. python tools/run_stage8.py "북아일랜드 vs 조지아" --record r1
PYTHONPATH=. python tools/run_stage8.py "북아일랜드 vs 조지아" --replay r1
PYTHONPATH=. python tools/run_stage8.py "북아일랜드 vs 조지아" --replay r1 \
        --replay-fallthrough
```

🔴 `--at HH:MM`(KST)을 주면 **그 시각까지 기다렸다가** 돈다(T-70분 실행용).
🔴 비용·벽시계를 §8 상한(≤$0.5 · ≤6분)과 대조해 찍는다.
⚠️ 발송하지 않는다 — `cmd_analyze` 는 답을 **돌려주는** 경로다(§11-11 과 무관).

══════════════════════════════════════════════════════════════════
🔴🔴 **녹화·재생** — 지시서 2026-10-06 §5
══════════════════════════════════════════════════════════════════

> 라이브는 **검수에만**. 그 전 확인은 전부 재생·fallthrough 로.

| 플래그 | 무엇 |
|---|---|
| `--record <실행 id>` | 외부 호출을 **전부** 녹화한다(검색·fetch·Solar·DeepSeek) |
| `--replay <실행 id>` | 망에 **안 간다**. 없는 요청은 `replay_miss` 로 실패 |
| `--replay-fallthrough` | 없는 요청만 라이브로 보내고 카세트에 **추가** |

🔴 **왜** — 2026-10-06 에 하루 예산 $5 중 **$4.88** 을 수정 확인용 재실행에
   썼다(한 번에 $0.34 · 26분). 이 문서의 수정 대부분은 같은 입력으로 **공짜로**
   확인할 수 있다.
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


def _as_of(said: str) -> datetime:
    """🔴 §4 — `YYYY-MM-DDTHH:MMZ`(또는 `...:SSZ`·오프셋) → tz 있는 시각.

    ⚠️ 시간대가 없으면 **거부한다** — 조용히 UTC 로 보면 KST 로 적은 시각이
       9시간 어긋난 채 통과하고, 그것이 이 기능이 막으려는 종류의 버그다.
    """
    got = str(said or "").strip().replace("Z", "+00:00")
    when = datetime.fromisoformat(got)
    if when.tzinfo is None:
        raise SystemExit(f"🔴 `--as-of` 에 시간대가 없다: `{said}` "
                         f"(`2026-10-10T05:00Z` 꼴로 적는다)")
    return when


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('쓰는 법: tools/run_stage8.py "<팀> vs <상대>" [--at HH:MM(KST)]'
              ' [--as-of 2026-10-10T05:00Z]')
        return 2
    arg = argv[1]
    at = ""
    if "--at" in argv:
        at = argv[argv.index("--at") + 1]
    # ══════════════════════════════════════════════════════════════
    # 🔴 **녹화·재생**(지시서 §5) — `app.cassette` 의 환경변수로 켠다.
    #    ⚠️ 새 통로를 만들지 않는다(사본 금지) — 카세트가 이미 그 칸을 읽는다.
    # ══════════════════════════════════════════════════════════════
    from app import cassette
    import os as _os
    for flag, mode in (("--record", cassette.RECORD),
                       ("--replay", cassette.REPLAY)):
        if flag in argv:
            run = argv[argv.index(flag) + 1]
            _os.environ[cassette.MODE_ENV] = mode
            _os.environ[cassette.RUN_ENV] = run
            print(f"[run_stage8] 카세트 {mode} · 실행 id `{run}`", flush=True)
    if "--replay-fallthrough" in argv:
        _os.environ[cassette.FALLTHROUGH_ENV] = "1"
        print("[run_stage8] 🔴 fallthrough — 없는 요청만 라이브로 간다",
              flush=True)
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **`--as-of` — 재현 모드**(사용자 지시 2026-10-10(재작성) §4)
    # ══════════════════════════════════════════════════════════════
    #
    #  > 모든 창(경기 찾기·72시간·라인업 상태·"이미 시작")은 현재 시각 기준.
    #  > 테스트용 `--as-of "YYYY-MM-DDTHH:MMZ"` 를 붙이면 **그 시각 기준**.
    #
    #  🔴 시계는 `app/window.set_clock` 하나다 — 운영 코드(`app/`)가 그것을
    #     부르면 계약이 빨개진다. 🔴 **도구 입구만** 부른다(여기가 그 자리다).
    if "--as-of" in argv:
        said = argv[argv.index("--as-of") + 1]
        from app import window as _w
        _w.set_clock(_as_of(said))
        print(f"[run_stage8] 🕒 `--as-of` {_w.now_utc():%Y-%m-%d %H:%M}Z — "
              f"모든 창이 이 시각 기준이다", flush=True)
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
    # 🔴 **경기 칸** — 입구가 열쇠를 정하기 전이라 질문 글자로 칸을 만든다.
    #    ⚠️ 같은 질문이면 같은 칸이다(그래서 재생이 맞는다).
    import os as _os2
    _os2.environ.setdefault(cassette.MATCH_ENV, arg)
    t0 = time.monotonic()
    # 🔴 `--deep` 이면 **긴 카드**(열네 블록)를 낸다 — 1겹은 `/analyze` 가 기본이고
    #    긴 카드는 `/자세히` 다(지시 2026-10-09(3차) §1). ⚠️ 같은 핸들러를 쓴다.
    if "--deep" in argv:
        from app.bot.main import cmd_deep
        msg = _Msg(f"/자세히 {arg}")
        await cmd_deep(msg)
    else:
        msg = _Msg(f"/analyze {arg}")
        await cmd_analyze(msg)                  # 🔴 **실제 핸들러**다
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
