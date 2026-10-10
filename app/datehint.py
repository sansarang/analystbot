"""🔴🔴 **fetch 전 날짜 거름** — 사용자 지시 2026-10-05 (②층).

> **fetch 전 거르기**: URL 날짜 패턴과 스니펫 날짜 표현(영·한·일·스페인어)을
> 파싱해 **7일 밖이 확실하면 받지 않는다. 날짜 힌트가 없으면 받는다.**

══════════════════════════════════════════════════════════════════
🔴 왜 이 층이 생겼나 — 실측 2026-10-05
══════════════════════════════════════════════════════════════════

SearXNG 이 **발행 시각을 주지 않는다**(엔진 전부 `publishedDate` 0건). 그래서
종전 경로는 *"받아 본 뒤에"* 날짜를 알았고, 7일 밖 문서에 예산을 썼다.

```
프랑스–벨기에 실측: verified_vars 탈락 … date_missing 10건
```

🔴 **fail-open 이다** — 지시 원문이 *"날짜 힌트가 **없으면 받는다**"* 라고 적었다.
   ⚠️ 모르는 것을 버리면 **당일 기사도 함께** 버린다. 버리는 것은 *"오래됐다고
   스스로 말하는"* 문서뿐이다.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

logger = logging.getLogger(__name__)

#: 🔴 며칠 안이면 받나. ⚠️ GDELT 색인 창(`7d`)과 같은 수다 — 두 벌로 갈리지
#   않게 **같은 뜻의 수를 한 군데**서만 바꾼다.
FRESH_DAYS = 7

#: 🔴 URL 안의 날짜 — 매체가 **주소에 날짜를 박는다**(`/2026/10/04/`).
#  ⚠️ 긴 것부터 본다. `20261004` 가 `2026` 보다 먼저 맞아야 한다.
_URL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"/(20\d{2})[/\-_](\d{1,2})[/\-_](\d{1,2})(?:[/\-_]|$)"),
    re.compile(r"[/\-_](20\d{2})(\d{2})(\d{2})(?:[/\-_]|$)"),
)

#: 🔴 달 이름 — 영어·스페인어. ⚠️ **사전이다**(사실이 아니다 · `search_words`
#   머리글의 구분).
_MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "ene": 1, "abr": 4, "ago": 8, "dic": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

#: 🔴 스니펫 날짜 — 네 언어. ⚠️ 순서가 뜻이다(구체적인 것부터).
_SNIP: tuple[tuple[re.Pattern, str], ...] = (
    # ISO — 어디서나 쓴다
    (re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})"), "ymd"),
    # 한국어 · 일본어 — `2026년 10월 4일` · `2026年10月4日`
    (re.compile(r"(20\d{2})\s*[년年]\s*(\d{1,2})\s*[월月]\s*(\d{1,2})\s*[일日]"),
     "ymd"),
    # 스페인어 — `4 de octubre de 2026`
    (re.compile(r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(20\d{2})",
                re.I), "dmy_name"),
    # 영어 — `October 4, 2026` · `Oct 4 2026`
    (re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d{2})"), "mdy_name"),
    # 영어 역순 — `4 October 2026`
    (re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(20\d{2})"), "dmy_name"),
)


def _safe(y: object, m: object, d: object) -> dt.date | None:
    """🔴 숫자 셋 → 날짜. ⚠️ 말이 안 되면 **`None`**(지어내지 않는다)."""
    try:
        got = dt.date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None
    # 🔴 **미래 10년·과거 30년 밖은 날짜가 아니다** — 주소 안의 상품 번호를
    #    날짜로 읽는 것을 막는다(실측: `/20261004/` 는 날짜, `/19999999/` 는 아니다)
    if not (2000 <= got.year <= 2100):
        return None
    return got


def from_url(url: object) -> dt.date | None:
    """🔴 주소 안의 날짜. ⚠️ 없으면 `None` — **힌트가 없다는 뜻**이다."""
    said = str(url or "")
    for pat in _URL_PATTERNS:
        m = pat.search(said)
        if m:
            got = _safe(m.group(1), m.group(2), m.group(3))
            if got:
                return got
    return None


def _month_of(name: object) -> int | None:
    low = str(name or "").strip().lower().rstrip(".")
    if low in _MONTHS:
        return _MONTHS[low]
    return _MONTHS.get(low[:3])


def from_snippet(text: object) -> dt.date | None:
    """🔴 스니펫 글의 날짜 — **영·한·일·스페인어**(지시 원문의 네 언어).

    ⚠️ 여러 날짜가 있으면 **처음 맞은 것**이다 — 매체가 발행일을 앞에 적는다.
    🔴 못 읽으면 `None` — 그것은 *"힌트가 없다"* 이고 **받는다**(fail-open).
    """
    said = str(text or "")
    for pat, kind in _SNIP:
        m = pat.search(said)
        if not m:
            continue
        a, b, c = m.group(1), m.group(2), m.group(3)
        if kind == "ymd":
            got = _safe(a, b, c)
        elif kind == "mdy_name":
            mon = _month_of(a)
            got = _safe(c, mon, b) if mon else None
        else:                                     # dmy_name
            mon = _month_of(b)
            got = _safe(c, mon, a) if mon else None
        if got:
            return got
    return None


def hint_of(url: object, snippet: object = "") -> tuple[dt.date | None, str]:
    """🔴 둘을 합친 **날짜 힌트**. `(날짜, 어디서 왔나)`.

    ⚠️ 주소가 먼저다 — 매체가 주소에 박는 날짜는 **발행일**이고, 스니펫의
       날짜는 기사가 *말하는* 날짜(경기 날짜 등)일 수 있다.
    """
    got = from_url(url)
    if got:
        return got, f"주소 날짜 {got.isoformat()}"
    got = from_snippet(snippet)
    if got:
        return got, f"스니펫 날짜 {got.isoformat()}"
    return None, "날짜 **힌트가 없다**"


def too_old(url: object, snippet: object = "", *, now: dt.datetime | None = None,
            days: int = FRESH_DAYS) -> tuple[bool, str]:
    """🔴🔴 **받지 않을 것인가.** `(버린다, 사유)` — 지시 ② (2026-10-05).

    🔴 **`True` 는 "오래됐다고 스스로 말한다"는 뜻뿐이다.** 힌트가 없으면
       `False`(받는다) — 지시 원문: *"날짜 힌트가 없으면 받는다."*
    ⚠️ 미래 날짜는 **버리지 않는다** — 예고 기사·일정 페이지가 그렇다.
    """
    # 🔴 "지금"은 `app/window.now_utc` 하나다(§4 `--as-of` 가 그것을 고정한다)
    from app import window as _w
    when = (now or _w.now_utc())
    if when.tzinfo is None:                     # §8-7 — naive 는 안 받는다
        when = when.replace(tzinfo=dt.timezone.utc)
    got, why = hint_of(url, snippet)
    if got is None:
        return False, f"{why} — **받는다**(모르는 것을 버리지 않는다)"
    gap = (when.date() - got).days
    if gap > int(days):
        return True, (f"🔴 **{days}일 밖이다** — {why}, 지금보다 {gap}일 전 "
                      f"(받지 않는다)")
    return False, f"{why} — {gap}일 전이라 창 안이다(받는다)"
