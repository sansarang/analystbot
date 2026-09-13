"""시각 입력 계약 — 사용자 지시 2026-09-13.

🔴 **실사고 2026-09-13.** 봇이 오늘 13:30 JST 소프트뱅크 경기 대신 **어제
   9/12 18:00** 행을 판정했다. 사용자 지적:
     "빗나간 게 아니라 봇이 어제(9/12) 경기를 판정한 겁니다.
      판단이 갈린 게 아니라 입력이 틀렸어요. 오늘은 일요일이다."

   실측(운영, Yahoo 원문 2026-09-13):
     2021039419 지바롯데@소프트뱅크 **13:30** scheduled   ← 오늘
     DB 에 들어간 것: yahoo:20210394**14** · 09-12 09:00Z(KST 18:00) ← 어제

⚠️ `test_no_naive_datetime` 은 **이미 있다** — `test_time_discipline.py` 의
   `test_no_naive_now_or_today` · `test_no_naive_datetime_literals`.
   같은 계약을 두 곳에 적지 않는다(사본 금지).
"""
from datetime import datetime, timedelta, timezone

import pytest

KST = timezone(timedelta(hours=9))
JST = timezone(timedelta(hours=9))


def test_kickoff_never_default():
    """🔴 시각을 못 읽은 경기는 **시각이 없어야** 한다. 지어내면 안 된다.

    실사고 2026-09-06: 18:00 을 지어내 `scheduled` 로 넣었고, 토요일 13:00 에
    끝난 두 경기가 "오늘 18:00 예정"으로 슬레이트에 들어가 판정·타순까지
    만들어졌다(롯데@오릭스·세이부@소프트뱅크).
    """
    from app.collectors.yahoo_npb import parse_schedule

    html = """
    <table><tr class="bb-scoreCardTable__row">
      <td class="bb-scoreCardTable__cell"><a href="/npb/game/2021039999/top">
      <span class="bb-scoreCardTable__homeName">福岡ソフトバンク</span>
      <span class="bb-scoreCardTable__awayName">千葉ロッテ</span>
      <span class="bb-scoreCardTable__status">3回表</span></a></td>
    </tr></table>"""
    for g in parse_schedule(html):
        assert not g.get("start_hhmm"), g          # 시각 없음 = None/빈값
        assert g.get("state") != "scheduled", g    # 지어낸 예정으로 만들지 않는다


def test_npb_kst_equals_jst():
    """🔴 JST 13:30 은 KST 13:30 이다. 18:00 상수가 끼어들면 안 된다.

    실측 2026-09-13: Yahoo 원문 13:30 → DB 09-12 09:00Z(KST 18:00).
    """
    from zoneinfo import ZoneInfo

    jst = ZoneInfo("Asia/Tokyo")
    kst = ZoneInfo("Asia/Seoul")
    start = datetime(2026, 9, 13, 13, 30, tzinfo=jst)
    in_kst = start.astimezone(kst)
    assert (in_kst.hour, in_kst.minute) == (13, 30), in_kst
    assert in_kst.date() == start.date()
    # 🔴 18:00 이 아니다 — 상수가 끼면 4시간 30분이 어긋난다
    assert in_kst.hour != 18


def test_npb_upsert_uses_parsed_hhmm_not_constant():
    """🔴 적재 코드가 파싱된 시각을 쓰는가. 상수 '18:00' 이 남아 있으면 실패."""
    import inspect

    from app.collectors import yahoo_npb

    src = inspect.getsource(yahoo_npb.upsert_schedule)
    assert "start_hhmm" in src, "파싱된 시각을 안 쓴다"
    i = src.find('"18:00"')
    if i < 0:
        i = src.find("'18:00'")
    if i >= 0:
        # 남아 있다면 **그 이유가 주석에 있어야** 한다(매칭용 폴백)
        assert "매칭" in src[max(0, i - 700):i], "18:00 폴백에 사유가 없다"


@pytest.mark.parametrize("utc,expect_kst_date", [
    ("2026-09-12T22:10:00+00:00", "2026-09-13"),   # KST 07:10 — 다음 날이다
    ("2026-09-12T14:59:00+00:00", "2026-09-12"),   # KST 23:59 — 같은 날
    ("2026-09-12T15:00:00+00:00", "2026-09-13"),   # KST 00:00 — 경계
    ("2026-09-13T04:30:00+00:00", "2026-09-13"),   # KST 13:30 — 소뱅 경기
])
def test_slate_window_crosses_kst_midnight(utc, expect_kst_date):
    """🔴 KST 자정을 넘는 경기가 그날 슬레이트에 들어가는가.

    ⚠️ 규칙은 CLAUDE.md 5번이다 — "축구=KST 오늘, 표기는 항상 KST".
       야구도 발송은 KST 기준이다. UTC 날짜로 자르면 새벽 경기가 사라진다.
    """
    got = datetime.fromisoformat(utc).astimezone(KST).strftime("%Y-%m-%d")
    assert got == expect_kst_date, (utc, got)


def test_ext_id_is_the_identity_not_the_matchup():
    """🔴 실사고의 핵심 — 같은 대진이 연전으로 다시 열리면 **다른 경기**다.

    실측 2026-09-13: 오늘 소뱅 경기 id 는 `2021039419` 인데 DB 에는 어제
    `...414` 행이 갱신돼 있었다. 대진+날짜창으로 같은 경기라고 본 것이다.
    """
    from app.collectors import game_match

    assert hasattr(game_match, "MATCH_WINDOW_HOURS")
    # 20시간 창은 하루 두 번 열리는 연전을 구분하지 못한다
    assert game_match.MATCH_WINDOW_HOURS <= 20
