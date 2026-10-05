"""🔴🔴 **경기 창 — 지금부터 36시간, UTC 로 센다.** (사용자 지시 2026-10-04)

> 날짜 창을 **"지금부터 36시간, UTC 계산"** 으로 고치고 계약을 건다.

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — 실측 2026-10-04 (포르투갈 vs 노르웨이)
══════════════════════════════════════════════════════════════════

사용자가 *"오늘 유에파 포르투갈 노르웨이"* 를 물었고, 봇은 그 경기를 **찾고도
버렸다**:

```
[fotmob] 날짜가 다르다 — 페이지 2026-10-05 vs 물은 날짜 2026-10-04
→ 🔴 match_not_found
```

⚠️ 비교가 **KST 달력 날짜**였다. 🔴 유럽 저녁 경기는 KST 로 **내일**이다
   (유럽 20:45 = KST 다음날 03:45). 그래서 *"오늘의 유럽 경기"* 는 한 경기가
   아니라 **구조적으로 전부** 떨어졌다. 북미 경기도 같다.

🔴 **달력을 버리고 창을 쓴다** — `지금 ≤ 킥오프 < 지금 + 36시간`.
⚠️ 왜 36인가: 사용자가 그 수를 정했다. 그 길이면 *"오늘 저녁 유럽"* 과
   *"내일 낮 아시아"* 가 **둘 다** 들어온다. 🔴 **여기 한 곳**에만 적는다.
"""
from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc

#: 🔴🔴 **창의 길이(시간).** 사용자 지시 2026-10-04. ⚠️ 두 곳에 적지 않는다.
HOURS = 36


#: 🔴🔴 **고정된 시계** — 시험만 쓴다. ⚠️ 운영에서는 **늘 `None`** 이다.
#
#  🔴 왜 필요한가: 기록해 둔 고정물(카세트)은 **지난 날짜**다. 창이 "지금부터
#     36시간"이므로 그 고정물들은 전부 창 밖이고, 시계를 못 고정하면 **창을
#     시험할 수가 없다**(실측 2026-10-04: 고정물 58건이 창 밖으로 떨어졌다).
#  ⚠️ `app/` 에서 `set_clock` 을 부르면 계약이 빨개진다 — 운영이 시계를 바꾸면
#     그 순간 모든 날짜 판단이 거짓이 된다.
_CLOCK: dt.datetime | None = None


def set_clock(ts: dt.datetime | None) -> None:
    """🔴 **시험용** — 시계를 고정한다. `None` 이면 실시간으로 돌아간다."""
    global _CLOCK
    _CLOCK = _aware(ts, "고정 시계") if ts is not None else None


def now_utc() -> dt.datetime:
    """🔴 지금(UTC). ⚠️ 시험이 시각을 넣을 수 있게 **한 곳**으로 모은다."""
    return _CLOCK or dt.datetime.now(UTC)


def _aware(when: dt.datetime, what: str) -> dt.datetime:
    """🔴 §8-7 — **시간대 없는 시각은 거부**다(조용히 UTC 로 보지 않는다).

    ⚠️ 조용히 UTC 로 보면 KST 로 적힌 시각이 **9시간 어긋난 채** 통과한다 —
       그것이 바로 이 파일이 고치는 종류의 버그다.
    """
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError(f"🔴 **시간대 없는** {what}다(§8-7): {when!r}")
    return when.astimezone(UTC)


def span(*, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    """🔴 `(시작, 끝)` — **UTC** 로 `지금` ~ `지금 + HOURS`."""
    start = _aware(now or now_utc(), "지금")
    return start, start + dt.timedelta(hours=HOURS)


def inside(when: dt.datetime, *, now: dt.datetime | None = None) -> bool:
    """🔴 그 킥오프가 창 안인가. ⚠️ **끝은 포함하지 않는다**(`[시작, 끝)`).

    🔴 이미 지난 경기는 **아니다** — 분석은 시작 전에만 뜻이 있다.
    """
    k = _aware(when, "킥오프")
    start, end = span(now=now)
    return start <= k < end


def why_out(when: dt.datetime, *, now: dt.datetime | None = None) -> str:
    """🔴 창 밖인 **까닭을 글로** — 조용히 버리지 않는다(#3).

    ⚠️ *"날짜가 다르다"* 는 거짓 사유였다 — 날짜가 다른 것이 아니라 **창 밖**
       이거나 **이미 지났다**. 고칠 곳이 다르다(§8-6).
    """
    if inside(when, now=now):
        return ""                 # 🔴 판단은 `inside` **한 곳**이다(사본 금지)
    k = _aware(when, "킥오프")
    start, end = span(now=now)
    if k < start:
        gone = (start - k).total_seconds() / 3600
        return (f"**이미 지났다** — 킥오프 {k:%Y-%m-%d %H:%M}Z 가 지금보다 "
                f"{gone:.1f}시간 전이다")
    if k >= end:
        ahead = (k - start).total_seconds() / 3600
        return (f"**창 밖이다** — 킥오프 {k:%Y-%m-%d %H:%M}Z 가 지금부터 "
                f"{ahead:.1f}시간 뒤다(창 {HOURS}시간)")
    return ""


def days(*, now: dt.datetime | None = None,
         tz: dt.tzinfo | None = None) -> list[dt.date]:
    """🔴 창이 **걸치는 달력 날짜들**(그 시간대 기준).

    ⚠️ 쓰는 곳이 있다 — 월간 일정 페이지·일별 API 는 **날짜로** 받는다
       (`npb.jp/games/{연}/schedule_{월}_detail.html`). 🔴 그 자리에서는 날짜가
       필요하고, **버릴지 말지는 `inside` 가** 정한다(두 일을 섞지 않는다).
    """
    start, end = span(now=now)
    zone = tz or UTC
    a, b = start.astimezone(zone).date(), end.astimezone(zone).date()
    out, d = [], a
    while d <= b:
        out.append(d)
        d += dt.timedelta(days=1)
    return out


#: 🔴 **같은 경기로 볼 시각 차이**(시간). ⚠️ 페이지가 적는 킥오프는 분 단위로
#   흔들리고(TBD·중계 편성), 어떤 페이지는 **현지 자정 기준**으로 적는다.
SAME_MATCH_HOURS = 8


def same_match_time(a: dt.datetime, b: dt.datetime, *,
                    hours: int | None = None) -> bool:
    """🔴🔴 **이 페이지가 그 경기인가** — 두 킥오프가 같은 순간인가.

    ══════════════════════════════════════════════════════════════════
    🔴 창과 **다른 질문**이다 (실측 2026-10-04 · 내가 섞었다)
    ══════════════════════════════════════════════════════════════════

    ⚠️ `inside` 는 *"이 경기가 분석 범위인가"* 를 묻는다(슬레이트). 🔴 여기서
       묻는 것은 *"이 **페이지**가 내가 물은 그 경기인가"* 다(신원).
    🔴 둘을 섞으면 **지난 경기의 페이지를 못 읽는다** — 실측: 창으로 신원을
       보게 바꾸자 고정물 58건이 터졌다(기록해 둔 10-01~10-04 경기들).

    ⚠️ 그리고 **달력 날짜로 비교하지 않는다** — 그것이 원래 버그였다
       (유럽 저녁 = KST 다음날). 🔴 **UTC 순간**을 비교한다.
    """
    x = _aware(a, "페이지 킥오프")
    y = _aware(b, "물은 킥오프")
    gap = abs((x - y).total_seconds()) / 3600
    return gap <= float(hours if hours is not None else SAME_MATCH_HOURS)
