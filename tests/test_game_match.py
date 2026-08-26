"""[§8-37] 결과를 **예측이 붙은 경기 행**에 붙인다.

채점이 통째로 막혀 있던 진짜 이유가 여기였다: 같은 경기가 소스마다 다른
ext_id를 받아 두 행으로 갈라지고, 예측은 한쪽 행에·결과는 다른 행에 들어갔다.
채점기는 final 행에서 픽을 찾으므로 예측이 붙은 행은 영원히 미채점이었다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.collectors.game_match import (
    MATCH_WINDOW_HOURS,
    apply_result,
    merge_duplicate_games,
)

KICK = datetime(2026, 8, 26, 9, 30, tzinfo=UTC)


async def _mk_game(pool, ext_id, starts, status="scheduled", hs=None, aws=None):
    return await pool.fetchval(
        """INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                              status, home_score, away_score)
           VALUES ('kbo','KBO',$1,$2,'Kia Tigers','Lotte Giants',$3,$4,$5)
           RETURNING id""", ext_id, starts, status, hs, aws)


@pytest.mark.asyncio
async def test_result_updates_the_row_predictions_point_at(db_pool):
    """🔴 회귀 핵심 — 다른 ext_id로 와도 **기존 행을 갱신**해야 한다."""
    gid = await _mk_game(db_pool, "odds:abc123", KICK)
    kind = await apply_result(
        db_pool, sport="kbo", league="KBO", ext_id="kbo:2026-08-26:롯데:KIA",
        starts_at=KICK, home="Kia Tigers", away="Lotte Giants",
        status="final", home_score=16, away_score=11)
    assert kind == "updated", "새 행을 만들었다 — 예측이 붙은 행은 미채점으로 남는다"
    row = await db_pool.fetchrow(
        "SELECT status, home_score, away_score FROM games WHERE id=$1", gid)
    assert row["status"] == "final" and row["home_score"] == 16
    assert await db_pool.fetchval(
        "SELECT count(*) FROM games WHERE ext_id IN ($1,$2)",
        "odds:abc123", "kbo:2026-08-26:롯데:KIA") == 1


@pytest.mark.asyncio
async def test_unseen_game_is_inserted(db_pool):
    """예측이 없던 경기도 결과는 쌓여야 채점 표본이 된다."""
    kind = await apply_result(
        db_pool, sport="kbo", league="KBO", ext_id="kbo:only",
        starts_at=KICK + timedelta(days=3), home="Kia Tigers",
        away="Lotte Giants", status="final", home_score=3, away_score=2)
    assert kind == "inserted"


@pytest.mark.asyncio
async def test_night_game_crossing_utc_midnight_still_matches(db_pool):
    """🔴 UTC **날짜**로 맞추면 MLB 야간경기가 다음 날이 돼 못 찾는다.

    19:00 ET = 23:00 UTC, 서머타임에 따라 02:00 UTC(다음 날)가 된다.
    그래서 날짜가 아니라 **시각 근접**으로 찾는다.
    """
    late = datetime(2026, 8, 26, 23, 0, tzinfo=UTC)
    gid = await _mk_game(db_pool, "odds:night", late)
    kind = await apply_result(
        db_pool, sport="kbo", league="KBO", ext_id="src:next-day",
        starts_at=late + timedelta(hours=3),      # UTC 날짜가 넘어간다
        home="Kia Tigers", away="Lotte Giants",
        status="final", home_score=1, away_score=0)
    assert kind == "updated"
    assert await db_pool.fetchval(
        "SELECT home_score FROM games WHERE id=$1", gid) == 1


@pytest.mark.asyncio
async def test_different_day_is_a_different_game(db_pool):
    """연전 다음 경기까지 같은 경기로 묶으면 안 된다."""
    await _mk_game(db_pool, "odds:day1", KICK)
    kind = await apply_result(
        db_pool, sport="kbo", league="KBO", ext_id="src:day2",
        starts_at=KICK + timedelta(hours=MATCH_WINDOW_HOURS + 5),
        home="Kia Tigers", away="Lotte Giants",
        status="final", home_score=9, away_score=9)
    assert kind == "inserted", "다음 날 경기를 같은 경기로 덮어썼다"


@pytest.mark.asyncio
async def test_merge_keeps_the_row_with_predictions(db_pool):
    """🔴 병합은 **예측이 붙은 행**을 남겨야 한다 — 그것이 우리가 판정한 경기다."""
    keep = await _mk_game(db_pool, "odds:keep", KICK)
    dup = await _mk_game(db_pool, "kbo:dup", KICK, "final", 16, 11)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:Kia Tigers',0.55,'shadow')", keep)

    out = await merge_duplicate_games(db_pool, sport="kbo")
    assert out["merged"] >= 1
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE id=$1", dup) == 0
    row = await db_pool.fetchrow(
        "SELECT status, home_score FROM games WHERE id=$1", keep)
    assert row is not None, "예측이 붙은 행을 지웠다"
    assert row["status"] == "final" and row["home_score"] == 16, \
        "남긴 행에 점수를 옮기지 않았다 — 채점이 여전히 불가능하다"


@pytest.mark.asyncio
async def test_merge_moves_predictions_before_deleting(db_pool):
    """예측이 dup 쪽에만 있으면 그 행이 keep이 되거나 예측이 이관돼야 한다."""
    a = await _mk_game(db_pool, "odds:a", KICK)
    b = await _mk_game(db_pool, "kbo:b", KICK, "final", 5, 4)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:x',0.6,'shadow')", b)
    await merge_duplicate_games(db_pool, sport="kbo")
    survivors = await db_pool.fetch(
        "SELECT id FROM games WHERE id = ANY($1::int[])", [a, b])
    assert len(survivors) == 1
    left = survivors[0]["id"]
    assert await db_pool.fetchval(
        "SELECT count(*) FROM predictions WHERE game_id=$1", left) == 1, \
        "예측이 병합 과정에서 사라졌다"


@pytest.mark.asyncio
async def test_merge_is_idempotent(db_pool):
    """매일 채점 직전에 돈다 — 두 번 돌아도 아무 일이 없어야 한다."""
    await _mk_game(db_pool, "odds:x1", KICK)
    await _mk_game(db_pool, "kbo:x2", KICK, "final", 2, 1)
    first = await merge_duplicate_games(db_pool, sport="kbo")
    second = await merge_duplicate_games(db_pool, sport="kbo")
    assert first["merged"] >= 1 and second["merged"] == 0


def test_grading_job_self_heals_duplicates():
    """[§8-37] 중복은 한 번 고쳐두면 끝나는 문제가 아니다 — 매일 합쳐야 한다.

    소스가 늘어날 때마다 같은 경기가 다른 ext_id로 다시 갈라질 수 있고,
    그러면 채점이 **조용히** 멈춘다.
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    job = src[src.index("async def grading_job"):]
    job = job[:job.index("\nasync def ", 10)] if "\nasync def " in job[10:] else job
    assert "merge_duplicate_games" in job, "채점 잡에 중복 자가 복구가 없다"
    assert job.index("merge_duplicate_games") < job.index("grade_date"), \
        "병합이 채점보다 뒤에 있으면 그날 채점은 여전히 중복 상태로 돈다"
