"""🔴🔴 **날짜 창은 "지금부터 36시간 · UTC"다** — 사용자 지시 2026-10-04.

> 날짜 창을 **"지금부터 36시간, UTC 계산"** 으로 고치고 계약을 건다.
> 포르투갈–노르웨이로 확인한다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (포르투갈 vs 노르웨이)
══════════════════════════════════════════════════════════════════

사용자가 *"오늘 유에파 포르투갈 노르웨이"* 를 물었다. 봇은 그 경기를 **찾았는데
버렸다**:

```
[fotmob] 날짜가 다르다 — 페이지 2026-10-05 vs 물은 날짜 2026-10-04
         (https://www.fotmob.com/matches/portugal-vs-norway/2ck62b)
→ 🔴 match_not_found
```

⚠️ 까닭: 비교가 **KST 달력 날짜**였다. 🔴 **유럽 저녁 경기는 KST 로 내일이다**
   (유럽 20:45 = KST 다음날 03:45). 그래서 *"오늘의 유럽 경기"* 는 **구조적으로
   전부** 떨어진다 — 한 경기의 문제가 아니다.

🔴 **창으로 바꾼다**: `지금 ≤ 킥오프 < 지금 + 36시간`, **UTC 로 센다.**
   ⚠️ 36시간이면 *"오늘 저녁 유럽"* 과 *"내일 낮 아시아"* 가 **둘 다** 들어온다.
"""
from __future__ import annotations

import datetime as dt

import pytest

UTC = dt.timezone.utc
KST = dt.timezone(dt.timedelta(hours=9))


def test_w36_창이_36시간이다():
    """🔴 수를 **한 곳**에 둔다 — 두 곳에 적으면 사본이다."""
    from app import window
    assert window.HOURS == 36


def test_w36_UTC_로_센다():
    """🔴 *"UTC 계산"* — 시작·끝이 UTC 이고 길이가 정확히 36시간이다."""
    from app import window
    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    start, end = window.span(now=now)
    assert start == now
    assert end - start == dt.timedelta(hours=36)
    assert start.tzinfo is not None and end.tzinfo is not None
    assert start.utcoffset() == dt.timedelta(0), start
    assert end.utcoffset() == dt.timedelta(0), end


def test_w36_시간대_없는_값을_거부한다():
    """🔴 §8-7 — 시간대 없는 시각은 **거부**다(조용히 UTC 로 보지 않는다)."""
    from app import window
    with pytest.raises(ValueError):
        window.span(now=dt.datetime(2026, 10, 4, 12, 0))
    with pytest.raises(ValueError):
        window.inside(dt.datetime(2026, 10, 4, 12, 0),
                      now=dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC))


@pytest.mark.parametrize("hours,want", [
    (-1, False),      # 🔴 이미 지난 경기는 아니다
    (0, True),        # ✅ 지금 시작
    (20, True),       # ✅ 유럽 저녁(= KST 내일 새벽)
    (35.9, True),     # ✅ 창 안
    (36, False),      # 🔴 창 밖(끝은 포함하지 않는다)
    (40, False),
])
def test_w36_창_안인가(hours, want):
    from app import window
    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    when = now + dt.timedelta(hours=hours)
    assert window.inside(when, now=now) is want, (hours, when)


def test_w36_포르투갈_노르웨이가_창에_들어온다():
    """🔴🔴 **실측한 그 경기**로 확인한다 — 사용자가 그렇게 지시했다.

    ⚠️ fotmob 가 `2026-10-05`(KST) 로 적은 그 경기다. 🔴 유럽 저녁 킥오프를
       UTC 로 보면 **10-04** 이고, *"지금부터 36시간"* 안에 있다.
    """
    from app import window
    # 🔴 실측: fotmob 페이지가 KST `2026-10-05` 라고 적었다 → UTC 로는 10-04 밤
    kick = dt.datetime(2026, 10, 5, 3, 45, tzinfo=KST)
    assert kick.astimezone(UTC).date() == dt.date(2026, 10, 4), kick
    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert window.inside(kick, now=now) is True, (
        "🔴 유럽 저녁 경기가 창에 **안 들어온다** — KST 달력 날짜로 비교하면 "
        "이 경기가 버려진다(실측 2026-10-04)")
    # ⚠️ 그리고 **KST 달력 날짜 비교는 이것을 버린다**(그래서 바꾸는 것이다)
    assert kick.astimezone(KST).date() != now.astimezone(KST).date()


def test_w36_어댑터가_달력_날짜로_버리지_않는다():
    """🔴🔴 **모양을 막는다**(§11-1) — 한 어댑터만 고치면 나머지가 또 버린다.

    ⚠️ 실측: `fdorg`·`espn`·`nhl`·`fotmob` **넷 다** `astimezone(KST).date()
       != day` 로 걸렀다. 🔴 그래서 축구·하키의 유럽/북미 저녁 경기가 전부
       떨어진다.
    """
    import pathlib

    from tests._helpers import strip_docs
    root = pathlib.Path(__file__).resolve().parents[2]
    bad = []
    for p in sorted((root / "app" / "collect").rglob("*.py")):
        body = strip_docs(p.read_text(encoding="utf-8", errors="replace"))
        for i, ln in enumerate(body.splitlines(), 1):
            if "astimezone(KST).date()" in ln and "!=" in ln:
                bad.append(f"{p.relative_to(root)}:{i}")
    assert not bad, (
        "🔴 어댑터가 **KST 달력 날짜**로 경기를 버린다 — 창(`window.inside`)으로 "
        "바꿔라:\n  " + "\n  ".join(bad))


def test_w36_찾기가_창을_쓴다():
    """🔴 **배선**(#2) — 창을 만들고 `findgame` 이 안 쓰면 없는 코드다."""
    import inspect

    from app import findgame
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(findgame))
    assert "window" in body, (
        "🔴 `findgame` 이 창을 안 쓴다 — 여전히 하루만 본다(#2)")


def test_w36_슬레이트_창도_같은_수에서_온다():
    """🔴 `SLATE_DAYS` 와 36시간이 **따로 놀면** 한쪽이 버린다(사본 금지)."""
    from app import config, window
    # ⚠️ 창이 36시간이면 DB 조회는 **적어도** 그만큼 덮어야 한다
    assert config.SLATE_DAYS * 24 >= window.HOURS, (
        f"🔴 DB 조회 창({config.SLATE_DAYS}일)이 36시간보다 **짧다** — "
        f"쌓인 경기를 못 꺼낸다")


def test_w36_운영은_시계를_고정하지_않는다():
    """🔴🔴 `set_clock` 은 **시험만** 부른다 — 운영이 부르면 날짜가 거짓이 된다.

    ⚠️ `_CLOCK` 은 모듈 전역이다. 운영 어딘가가 그것을 세우면 **그 뒤 모든**
       창 판단이 그 시각 기준이 된다 — 조용히 틀린 슬레이트가 나온다.
    """
    import pathlib

    from tests._helpers import strip_docs
    root = pathlib.Path(__file__).resolve().parents[2]
    bad = []
    for p in sorted((root / "app").rglob("*.py")):
        if p.name == "window.py":
            continue                 # 🔴 선언한 자리다
        body = strip_docs(p.read_text(encoding="utf-8", errors="replace"))
        if "set_clock" in body:
            bad.append(str(p.relative_to(root)))
    assert not bad, (
        f"🔴 **운영 코드가 시계를 고정한다** — 그 뒤 모든 날짜 판단이 거짓이 "
        f"된다: {bad}")


def test_w36_창_밖_사유가_날짜가_다르다가_아니다():
    """🔴 §8-6 — **거짓 사유 금지.** 창 밖인지 이미 지났는지를 **가려** 적는다.

    ⚠️ 종전 사유는 *"날짜가 다르다"* 였다 — 날짜가 다른 것이 아니라 **창
       밖**이었고, 그래서 고칠 곳이 어디인지 알 수 없었다.
    """
    from app import window
    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    assert window.why_out(now + dt.timedelta(hours=10), now=now) == ""
    gone = window.why_out(now - dt.timedelta(hours=5), now=now)
    assert "이미 지났다" in gone, gone
    far = window.why_out(now + dt.timedelta(hours=50), now=now)
    assert "창 밖" in far and "36" in far, far


def test_w36_fdorg_도_창으로_거른다():
    """🔴🔴 **M93 이 통과했다** — `fdorg`(해외축구)에 계약이 없었다.

    ⚠️ 어댑터마다 **따로** 걸러서, 한 곳만 고치면 나머지가 그대로 샌다. 🔴 그
       모양을 글자 검사로만 막았고(`astimezone(KST).date() !=` 금지) **창을
       안 보는 것**은 못 잡았다.
    """
    import json

    from app.collect import fdorg
    from app.net import Fetched
    from app import window

    # 🔴 실측 모양(football-data.org `/matches`) — 한 경기만 둔다
    body = json.dumps({"matches": [{
        "id": 1, "utcDate": "2026-10-04T18:45:00Z", "status": "TIMED",
        "competition": {"name": "UEFA Nations League", "code": "UNL"},
        "homeTeam": {"id": 765, "name": "Portugal"},
        "awayTeam": {"id": 782, "name": "Norway"}}]})
    got = Fetched("https://api.football-data.org/v4/matches", True, 200, body)

    window.set_clock(dt.datetime(2026, 10, 4, 12, 0, tzinfo=UTC))
    try:
        rows = fdorg.parse_schedule(got, dt.date(2026, 10, 4))
    finally:
        window.set_clock(None)
    assert len(rows) == 1, (
        f"🔴 창 안 경기(6.75시간 뒤)를 **버렸다**: {rows}")

    # 🔴 창 밖(이미 지났다)이면 버린다
    window.set_clock(dt.datetime(2026, 10, 6, 12, 0, tzinfo=UTC))
    try:
        gone = fdorg.parse_schedule(got, dt.date(2026, 10, 4))
    finally:
        window.set_clock(None)
    assert gone == [], (
        f"🔴 **이미 지난 경기**를 슬레이트에 넣었다 — `fdorg` 가 창을 안 본다: "
        f"{gone}")
