"""🔴🔴 **v5-A §2 — 단가는 시각이 고른다.** DeepSeek 는 피크가 **두 배**다.

공식 문서(2026-10-04 · 봇이 직접 읽었다):

> **Off-peak rates are half of the peak rates.** Peak hours are
> **01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday**, excluding
> Chinese public holidays. All other hours are off-peak, **including
> weekends** and Chinese public holidays in full.

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — **단가를 하나로 적으면 절반 틀린다**
══════════════════════════════════════════════════════════════════

⚠️ Solar 는 단가가 하나다(§2). DeepSeek 는 **둘**이고 시각이 고른다. 🔴 그
   선택이 코드에 숨으면 원장의 `usd` 가 절반 틀리고, 그 수로 하루 $3 가드가
   돈다 — 가드가 거짓이 된다.

🔴 **중국 공휴일은 모른다.** 문서가 그 날은 오프피크라고 했지만 우리에게 그
   달력이 없다. ⚠️ 그래서 **피크로 본다**(fail-closed: 비싸게 세는 쪽이
   안전하다 — 가드가 일찍 멈추는 것이 늦게 멈추는 것보다 낫다).
"""
from __future__ import annotations

from datetime import datetime, timezone




