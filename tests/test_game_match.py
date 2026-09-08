"""[§8-37] 결과를 **예측이 붙은 경기 행**에 붙인다.

같은 경기가 소스마다 다른 ext_id를 받아 두 행으로 갈라지면, 예측은 한쪽·점수는
다른 쪽에 들어간다. 점수는 예측이 붙은 행에 옮겨야 한다.
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


def test_finals_job_self_heals_duplicates():
    """중복 행은 점수 적재 전에 합친다 — 예측과 결과가 다른 행에 붙지 않게."""
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    job = src[src.index("async def finals_job"):]
    job = job[:job.index("\nasync def ", 10)] if "\nasync def " in job[10:] else job
    assert "merge_duplicate_games" in job, "점수 적재 잡에 중복 자가 복구가 없다"
    assert job.index("merge_duplicate_games") < job.index("ingest_finals"), \
        "병합이 점수 적재보다 뒤에 있으면 그날도 중복 상태로 돈다"


# ═══════════════ [GM-2 2026-09-08] CASCADE 12표 중 3표만 이관했다
#
# 🔴 `db/schema.sql` 이 아니라 **`information_schema` 에서 세었다** (사본 금지):
#      games 삭제 시 ON DELETE CASCADE 로 함께 지워지는 표 — **12개**
#      merge_duplicate_games 가 이관하는 표 — **3개**
#        predictions · expert_picks · pick_ledger
#      → 이관 없이 DELETE 로 사라지는 표 **9개**
#        cell_verdicts · game_trace · lineup_events · lineup_verdicts · lineups
#        market_baseline_ledger · odds_snapshots · pitcher_appearances · variable_ledger
#
# 가장 무거운 것은 `pitcher_appearances` 다 — 자료4·9·10·14 의 원천이다.
# 병합으로 그 경기 행이 지워지면 **그 등판이 모든 투수의 이력에서 영구히
# 사라진다.** 다음 날 그 투수의 "최근 5등판"은 4등판이 되고, 리그 표본
# (`_PEERS`·`_REGRESSION`)도 그만큼 줄어든다. 어디에도 로그가 남지 않는다.
#
# 🔴 모듈이 이 규칙을 **자기 손으로 적어 두었다**:
#      "새 표를 만들면 **이 목록에 반드시 추가한다.**"
#    2026-08-27 predictions · 08-31 pick_ledger 를 넣으며 못박았고, 그 뒤
#    만들어진 표 아홉 중 **하나도 추가되지 않았다**. 문장에는 강제력이 없다.
#    이 테스트가 그 강제력이다 — 표 목록을 손으로 적지 않고 카탈로그에서 읽는다.

#: 이관되면 살아남아야 하는 한 행씩. **표 목록은 여기 적지 않는다** —
#  아래 테스트가 information_schema 로 읽어 이 사전과 대조한다.
#  (사전에 없는 표가 나오면 그 자체가 실패다 — 새 표가 생겼다는 뜻이다.)
_SEED = {
    "cell_verdicts": ("INSERT INTO cell_verdicts (game_id, side, cell, symbol) "
                      "VALUES ($1,'home','불펜','O')"),
    "game_trace": ("INSERT INTO game_trace (game_id, sport, slate_date, stage, summary) "
                   "VALUES ($1,'kbo','2026-08-26','판정','GM-2 재현')"),
    "lineup_events": ("INSERT INTO lineup_events (game_id, side, batting_order) "
                      "VALUES ($1,'home','[]'::jsonb)"),
    "lineup_verdicts": ("INSERT INTO lineup_verdicts (game_id, side, change_type, cell, symbol) "
                        "VALUES ($1,'home','타순','타선','O')"),
    "lineups": ("INSERT INTO lineups (game_id, side, status, source) "
                "VALUES ($1,'home','confirmed','crawler')"),
    "market_baseline_ledger": ("INSERT INTO market_baseline_ledger "
                               "(game_id, sport, slate_date) VALUES ($1,'kbo','2026-08-26')"),
    "odds_snapshots": ("INSERT INTO odds_snapshots (game_id, book, market, side, odds) "
                       "VALUES ($1,'bk','h2h','home',1.85)"),
    "pitcher_appearances": ("INSERT INTO pitcher_appearances "
                            "(game_id, sport, team, opponent, pitcher, is_starter, "
                            " innings, source) "
                            "VALUES ($1,'kbo','Kia Tigers','Lotte Giants','P',true,6.0,'box')"),
    "variable_ledger": ("INSERT INTO variable_ledger (game_id, sport, raw) "
                        "VALUES ($1,'kbo','GM-2 재현용 변수')"),
}

_CASCADE_SQL = """
SELECT DISTINCT tc.table_name
  FROM information_schema.table_constraints tc
  JOIN information_schema.referential_constraints rc
    ON rc.constraint_name = tc.constraint_name
  JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
 WHERE tc.constraint_type = 'FOREIGN KEY'
   AND ccu.table_name = 'games' AND rc.delete_rule = 'CASCADE'
 ORDER BY 1
"""


@pytest.mark.asyncio
async def test_카탈로그가_아는_표를_이_테스트도_안다(db_pool):
    """🔴 새 표가 생기면 **여기서 먼저 운다.** 목록을 손으로 관리하지 않는다."""
    known = {r["table_name"] for r in await db_pool.fetch(_CASCADE_SQL)}
    moved_by_hand = {"predictions", "expert_picks", "pick_ledger"}
    unseeded = known - moved_by_hand - set(_SEED)
    assert not unseeded, (
        f"CASCADE 표가 새로 생겼는데 GM-2 재현이 그것을 모른다: {sorted(unseeded)}. "
        "merge_duplicate_games 의 이관 대상인지 확인하고 _SEED 에 한 행을 더하라.")


@pytest.mark.asyncio
async def test_병합이_CASCADE_표를_통째로_지운다(db_pool):
    """🔴 GM-2 — 이관되지 않은 9개 표가 DELETE 로 조용히 사라진다."""
    keep = await _mk_game(db_pool, "odds:keep-gm2", KICK)
    dup = await _mk_game(db_pool, "kbo:dup-gm2", KICK, "final", 7, 3)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:Kia Tigers',0.55,'shadow')", keep)
    for sql in _SEED.values():
        await db_pool.execute(sql, dup)

    out = await merge_duplicate_games(db_pool, sport="kbo")
    assert out["merged"] >= 1
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE id=$1", dup) == 0

    lost = []
    for tbl in _SEED:
        n = await db_pool.fetchval(
            f"SELECT count(*) FROM {tbl} WHERE game_id = $1", keep)
        if n == 0:
            lost.append(tbl)
    assert not lost, (
        f"병합이 {len(lost)}개 표의 행을 이관하지 않고 지웠다: {sorted(lost)}. "
        "가장 무거운 것은 pitcher_appearances — 그 등판이 모든 투수의 "
        "이력에서 영구히 사라진다(자료4·9·10·14 의 원천).")


@pytest.mark.asyncio
async def test_이관은_기존_세_표를_계속_옮긴다(db_pool):
    """⚠️ 반대 위험 — 새 이관이 기존 세 표의 처리를 깨뜨리면 안 된다."""
    keep = await _mk_game(db_pool, "odds:keep-gm2b", KICK)
    dup = await _mk_game(db_pool, "kbo:dup-gm2b", KICK, "final", 1, 0)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:a',0.55,'shadow')", keep)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:b',0.60,'shadow')", dup)
    await db_pool.execute(
        "INSERT INTO expert_picks (game_id, expert, site, pick) "
        "VALUES ($1,'kim','naver','Kia')", dup)

    await merge_duplicate_games(db_pool, sport="kbo")
    assert await db_pool.fetchval(
        "SELECT count(*) FROM predictions WHERE game_id=$1", keep) == 2
    assert await db_pool.fetchval(
        "SELECT count(*) FROM expert_picks WHERE game_id=$1", keep) == 1


@pytest.mark.asyncio
async def test_못_옮긴_행은_수를_세어_시끄럽게_남긴다(db_pool, caplog):
    """🔴 유니크 충돌로 못 옮기는 행은 **여전히 CASCADE 로 사라진다.**

    그것을 없앨 수는 없다 — 없애려면 어느 쪽을 버릴지 표마다 정해야 하고,
    그 판단은 표의 의미를 아는 사람의 몫이다. 대신 **조용한 삭제를 시끄러운
    삭제로 바꾼다.** 세지 않으면 다음에도 아무도 모른다.
    """
    keep = await _mk_game(db_pool, "odds:keep-gm2c", KICK)
    dup = await _mk_game(db_pool, "kbo:dup-gm2c", KICK, "final", 2, 1)
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, method) "
        "VALUES ($1,'h2h:a',0.55,'shadow')", keep)
    # 같은 (game_id, team, pitcher) — 양쪽에 같은 등판이 적혀 있다
    for gid in (keep, dup):
        await db_pool.execute(
            "INSERT INTO pitcher_appearances "
            "(game_id, sport, team, opponent, pitcher, is_starter, innings, source) "
            "VALUES ($1,'kbo','Kia Tigers','Lotte Giants','P',true,6.0,'box')", gid)
    # 충돌하지 않는 행도 하나 — 이건 옮겨져야 한다
    await db_pool.execute(
        "INSERT INTO pitcher_appearances "
        "(game_id, sport, team, opponent, pitcher, is_starter, innings, source) "
        "VALUES ($1,'kbo','Lotte Giants','Kia Tigers','Q',false,1.0,'box')", dup)

    with caplog.at_level("WARNING"):
        out = await merge_duplicate_games(db_pool, sport="kbo")

    assert out.get("cascade_dropped", 0) >= 1, "못 옮긴 행을 세지 않았다"
    assert any("옮기지 못했다" in r.getMessage() for r in caplog.records), \
        "조용히 사라졌다 — 로그가 없으면 다음에도 아무도 모른다"
    # 충돌하지 않은 행은 살아남는다
    assert await db_pool.fetchval(
        "SELECT count(*) FROM pitcher_appearances WHERE game_id=$1 AND pitcher='Q'",
        keep) == 1
    # keep 쪽 원본은 그대로다 (덮어쓰지 않는다)
    assert await db_pool.fetchval(
        "SELECT count(*) FROM pitcher_appearances WHERE game_id=$1 AND pitcher='P'",
        keep) == 1


@pytest.mark.asyncio
async def test_손수_처리하는_세_표는_일반_경로가_건드리지_않는다():
    """⚠️ 픽은 겹치면 지우고 레저는 이력으로 강등한다 — 정책이 서로 다르다.
    일반 규칙이 그 위를 덮으면 판정 기록이 지워진다."""
    from app.collectors.game_match import _HAND_MOVED

    assert set(_HAND_MOVED) == {"predictions", "expert_picks", "pick_ledger"}
