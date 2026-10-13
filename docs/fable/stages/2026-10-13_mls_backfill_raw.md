리그 130(league:MLS) — 끝난 경기 500건 · 시즌 ['2026', '2025']
   … 25/500
   … 50/500
   … 75/500
   … 100/500
   … 125/500
   … 150/500
   … 175/500
   … 200/500
   … 225/500
   … 250/500
   … 275/500
   … 300/500
   … 325/500
   … 350/500
   … 375/500
   … 400/500
   … 425/500
   … 450/500
   … 475/500
   … 500/500
🔴 재생한 500줄을 적었다 — var/judge/replay_mls.json

재생한 경기 **500건** · 확률을 만든 경기 **500건**(앞 경기가 모자라면 못 만든다)
그 표본 실제 비율 — 홈 47.0% · 무 25.2% · 원정 27.8%

| 모형 | n | **방향 적중률** |
|---|---|---|
| 봇(옛 구조 · 네 축) | 500 | **47.8%** |
| Elo만 | 500 | **47.0%** |
| 리그 기본률 | 500 | **47.0%** |
| 균등 33/33/33 | 500 | **47.0%** |

| 모형 | n | **로그 손실** | 95% 구간 | RPS | 브라이어 |
|---|---|---|---|---|---|
Traceback (most recent call last):
  File "/Users/youngjinjung/Desktop/analystbot/tools/backfill_score.py", line 346, in <module>
    asyncio.run(main())
  File "/Users/youngjinjung/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/python3.12/asyncio/runners.py", line 195, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/Users/youngjinjung/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/youngjinjung/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/lib/python3.12/asyncio/base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/Users/youngjinjung/Desktop/analystbot/tools/backfill_score.py", line 260, in main
    print(f"| {name} | {len(box)} | **{sum(ll) / len(ll):.4f}** | "
                                       ~~~~~~~~^~~~~~~~~
ZeroDivisionError: division by zero
