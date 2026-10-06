"""🔴🔴 **M109 — `date_missing` 전에 htmldate 가 반드시 돈다**.

지시서 `docs/fable/archive/2026-10-05_workorder_idn_tha_fixes.md` §4-1·M109.

> `date_missing` 판정 전에 `htmldate` 가 **반드시 호출된다**(호출 기록 없이
> `date_missing` 이 찍히면 실패).

══════════════════════════════════════════════════════════════════
🔴 §4-1 진단 — 재서 찾은 것 (2026-10-05)
══════════════════════════════════════════════════════════════════

it5 로그에서 `[cell] 발행일 —` 줄이 **0건**이었다. 두 가지가 겹쳤다:

| 자리 | 무엇 |
|---|---|
| 세포 경로 | 결정 ③으로 **꺼져 있다**(`cell_search_off 74`) — `pick_published` 가 거기 있어 안 돈다 |
| 하위 에이전트 경로 | `Tools._open` 이 `readtext.read` 의 발행일을 **`_when` 으로 버린다** |
| 변수 조립 | `published_at` 을 **모델이 적은 값**에서만 읽는다 — ③층이 뽑은 날짜가 안 쓰인다 |

🔴 그래서 `htmldate` 는 **돌았지만 그 결과가 검증층에 닿지 않았다** —
   배선 끊김이다(지시서가 의심한 그대로).
"""
from __future__ import annotations

import ast
import inspect
















def test_M109_세포_경로도_날짜를_싣는다():
    """🔴 #2 배선 — **돌려서** 본다(글자 검사는 §9-5 가 무효로 본다)."""
    from app import cells
    seen = cells.Seen()
    html = ('<html><head><meta property="article:published_time" '
            'content="2026-10-04T12:00:00+00:00"></head><body>'
            '<article><p>Bradley is unavailable for Northern Ireland because '
            'of a hamstring injury picked up last week.</p></article>'
            '</body></html>')

    class _Got:
        text = html
        ok = True
        url = "https://news.test/a"

    cell = cells.Cell.__new__(cells.Cell)      # 🔴 입구를 안 지난다(이 함수만 본다)
    cell.seen = seen
    cells.Cell._remember_body(cell, "https://news.test/a", _Got())
    assert seen.bodies.get("https://news.test/a"), seen.docs
    when = seen.dates.get("https://news.test/a")
    assert when is not None, (
        f"🔴 세포가 받은 본문에 **발행일이 안 실렸다** — 실측 2026-10-06 에 "
        f"그 때문에 `date_missing` 이 20건이었다: {seen.docs}")
    assert seen.date_sources.get("https://news.test/a"), seen.docs
