"""🔴🔴 **사용자에게 보이는 시각은 KST 다** — 그 변환이 사는 **한 곳**.

절대규칙 2(= v4 §14-2): *"DB 는 UTC 저장, **표시만 KST**."*

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — **같은 결함을 두 번 냈다**
══════════════════════════════════════════════════════════════════

실측 2026-09-27: `timestamptz` 를 그대로 `strftime` 하면 asyncpg 가 **UTC** 로
돌려주므로 18:05 경기가 `09:05` 로 찍혔다. 그때 `run.kst_label` 을 만들어 고쳤다.

🔴 **그런데 그 뒤에 새로 쓴 코드 둘이 같은 실수를 다시 했다** — 실측 2026-10-03
   (엘살바도르 vs 자메이카):

```
findgame 로그   2026-10-03 11:00:00+09:00 KST     ← 맞다
카드 머리글      10-03 02:00 KST                  ← 🔴 9시간 틀렸다
```

⚠️ 까닭은 똑같다. `analyze.answer` 와 `findgame` 의 렌더러가 `starts_kst` 를
   `.astimezone()` 없이 `strftime` 했다. 고친 자리가 하나였고, **같은 일을 하는
   자리가 넷**이었다(CLAUDE.md #1 — 사본 금지).

🔴 그래서 **형식화는 여기 하나다.** 계약이 `app/` 전체를 훑어 *"KST 라고 적는
   `strftime`"* 이 이 함수를 거치는지 본다(`tests/test_timefmt.py`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: 🔴 한국 표준시. **고정 오프셋**이다 — 한국은 일광절약시를 쓰지 않는다.
#   ⚠️ `app/` 의 다른 모듈에도 같은 상수가 있다. 그것은 **값이 틀릴 수 없는**
#      상수라 해롭지 않다 — 다친 자리는 늘 **변환을 빠뜨린 형식화**였다.
KST = timezone(timedelta(hours=9))

#: 카드·슬레이트가 쓰는 기본 꼴. 🔴 꼴을 바꿀 자유는 두고, **변환은 못 건너뛴다.**
FMT = "%m-%d %H:%M"


def kst_label(when: datetime, *, fmt: str = FMT, suffix: str = " KST") -> str:
    """🔴 `when` 을 **KST 로 바꿔** 적는다. 라벨까지 여기서 붙인다.

    ⚠️ **naive(시간대 없는) 값은 거부한다.** 그것을 KST 라고 적는 순간 몇 시간이
       조용히 틀어지고, 그 거짓은 카드를 읽는 사람이 알아낼 방법이 없다
       (#3 조용한 0 금지의 시각판이다). 🔴 모르면 멈추는 것이 맞다.
    """
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(
            f"시간대 없는 값을 KST 로 적을 수 없다: {when!r} — "
            f"어느 시간대인지 모르는 수에 `KST` 를 붙이면 그것이 거짓이 된다")
    return when.astimezone(KST).strftime(fmt) + suffix


def kst(when: datetime) -> datetime:
    """🔴 KST 로 옮긴 값. 날짜만 쓸 때(`.date()`)·비교할 때 쓴다."""
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(f"시간대 없는 값이다: {when!r}")
    return when.astimezone(KST)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **5단계 시간 계약** — tz 없는 값은 들어오지 못한다
# ══════════════════════════════════════════════════════════════════
#
# 사용자 설계 2026-10-03:
#
# > **시간 계약**: `datetime` 비교에 **tz 없는 값이 들어오면 실패**.
#
# ⚠️ 왜 — 실측 2026-10-03: `16:00Z` 와 `01:00 KST` 를 섞어 비교해 **경기를 잃었다**
#    (`크로아티아 - 잉글랜드` 가 "오늘"에 안 걸렸다). 🔴 naive 값은 **조용히
#    서버 시간대로 가정**되고, 그 가정이 어긋나도 아무 데도 안 적힌다.


def aware(when, *, assume=None, where: str = ""):
    """🔴 **tz 를 붙여 돌려준다.** 못 붙이면 `None` 과 **경고**.

    `assume` 을 주면 그 시간대로 본다(그 자리에서 **아는 경우에만** 준다 —
    예: 리그 일정이 늘 현지 시각으로 오는 어댑터).
    ⚠️ `assume` 없이 naive 가 오면 **버린다.** 🔴 조용히 UTC 로 가정하지 않는다 —
       그 가정이 틀리면 경기를 잃고, 잃은 것이 아무 데도 안 적힌다.
    """
    if not isinstance(when, datetime):
        return None
    if when.tzinfo is not None and when.tzinfo.utcoffset(when) is not None:
        return when
    if assume is not None:
        return when.replace(tzinfo=assume)
    logger.warning("[timefmt] 시간대 없는 값을 버린다: %r%s", when,
                   f" ({where})" if where else "")
    return None


def before(a, b) -> bool:
    """🔴 `a < b` — **둘 다 tz 가 있어야** 한다. 없으면 `ValueError`.

    ⚠️ 파이썬은 naive 와 aware 를 비교하면 `TypeError` 를 낸다. 🔴 그런데
       **naive 끼리는 조용히 비교된다** — 그때 서버 시간대가 끼어든다.
       그 자리가 이 저장소를 다치게 한 자리다.
    """
    for x, nm in ((a, "a"), (b, "b")):
        if not isinstance(x, datetime):
            raise ValueError(f"시각이 아니다({nm}): {x!r}")
        if x.tzinfo is None or x.tzinfo.utcoffset(x) is None:
            raise ValueError(
                f"🔴 시간대 없는 값을 비교에 넣었다({nm}): {x!r} — "
                f"서버 시간대가 조용히 끼어든다(5단계 시간 계약)")
    return a < b
