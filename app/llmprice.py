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


def deepseek_band(now: datetime | None = None) -> str:
    """🔴 그 시각이 `peak` 인가 `off_peak` 인가.

    ⚠️ 시각은 **UTC** 로 본다 — 문서가 UTC 로 적었다. 🔴 시간대 없는 시각은
       받지 않는다(§8-7: 그것이 UTC 인지 KST 인지 아무도 모른다).
    """
    from app import rules
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None or at.tzinfo.utcoffset(at) is None:
        raise ValueError(f"🔴 시간대 없는 시각이다(§8-7): {at!r}")
    at = at.astimezone(timezone.utc)
    pr = rules.deepseek_cfg()["price_usd_per_1m"]
    days = {int(x) for x in (pr.get("peak_weekdays") or [])}
    if at.weekday() not in days:
        # 🔴 주말은 **전부** 오프피크다(문서가 그렇게 적었다)
        return "off_peak"
    for lo, hi in (pr.get("peak_hours_utc") or []):
        if int(lo) <= at.hour < int(hi):
            return "peak"
    return "off_peak"


def deepseek_cost(usage: dict, *, now: datetime | None = None) -> float:
    """🔴 그 호출의 **비용**(USD). ⚠️ 캐시는 **따로 센다**(단가가 다르다).

    🔴 추론 토큰(`reasoning_tokens`)은 **출력에 이미 들어 있다** — 두 번 세지
       않는다(§2 가 Solar 에서 같은 함정을 적었다).
    """
    from app import rules
    u = dict(usage or {})
    band = deepseek_band(now)
    pr = rules.deepseek_cfg()["price_usd_per_1m"][band]
    cached = int((u.get("prompt_tokens_details") or {})
                 .get("cached_tokens") or 0)
    fresh = max(0, int(u.get("prompt_tokens") or 0) - cached)
    out = int(u.get("completion_tokens") or 0)
    got = (fresh * float(pr["input"]) + cached * float(pr["cached_input"])
           + out * float(pr["output"])) / 1_000_000
    return round(got, 8)
