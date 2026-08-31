"""[축구 채점] 유럽 킥오프의 KST/UTC 날짜 경계.

🔴 실측 2026-08-31: 유럽 경기는 KST 새벽(= UTC 전날 저녁)에 열린다.
   KST 09/01 01:30 경기의 UTC 날짜는 08/31 이다. 축구 수집기는 **KST 날짜**로
   거르는데 reconcile_stale_games 가 **UTC 날짜**를 넘기고 있었고,
   finals_job 은 yesterday_kst() 만 훑었다. 두 경로 모두 그 경기를 놓쳐
   영원히 final 이 되지 않는다 — 그러면 픽 레저도 영원히 미채점이다.
"""

from pathlib import Path

import pytest


def test_reconcile_uses_kst_date_for_soccer():
    """축구만 KST 날짜로 그룹핑한다 — 수신부가 KST 필터이기 때문이다."""
    src = Path("app/collectors/finals.py").read_text(encoding="utf-8")
    body = src[src.index("async def reconcile_stale_games"):]
    assert "sport = 'soccer'" in body and "Asia/Seoul" in body, \
        "축구에 UTC 날짜를 넘기면 유럽 경기가 통째로 어긋난다"
    # 다른 종목은 종전대로 UTC — 그 계약을 바꾸지 않았는지 확인
    assert "ELSE (starts_at AT TIME ZONE 'UTC')::date END" in body


def test_finals_job_also_ingests_today_for_soccer():
    """오늘 새벽에 끝난 유럽 경기를 회수한다 — yesterday 만으로는 못 잡는다."""
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def finals_job"):]
    body = body[:body.index("\nasync def ")]
    assert 'sport == "soccer"' in body and "today_kst()" in body


async def test_stale_soccer_game_is_grouped_by_kst_date(db_pool):
    """실제 쿼리로 확인 — KST 09/01 새벽 경기가 9/1로 묶인다."""
    await db_pool.execute(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('soccer','EPL','eu1','2026-08-31 19:00+00','Villa','Arsenal',"
        "         'scheduled')")
    row = await db_pool.fetchrow(
        """SELECT CASE WHEN sport = 'soccer'
                       THEN (starts_at AT TIME ZONE 'Asia/Seoul')::date
                       ELSE (starts_at AT TIME ZONE 'UTC')::date END AS d,
                  (starts_at AT TIME ZONE 'UTC')::date AS utc_d
             FROM games WHERE ext_id = 'eu1'""")
    assert row["d"].isoformat() == "2026-09-01", "KST 날짜로 묶이지 않았다"
    assert row["utc_d"].isoformat() == "2026-08-31", "UTC 날짜는 하루 이르다"
