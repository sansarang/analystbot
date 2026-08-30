"""종료 경기 점수 적재. 픽 채점은 하지 않는다 (2026-08-29 사용자 지시).

종목 분기는 여기 한 곳에만 둔다. 실사고(2026-08-27): 분기가 두 곳에 있어
KBO·NPB가 축구 수집기로 갔다.
"""

import logging

import asyncpg

from app.collectors.mlb import MLBClient, upsert_final_scores

logger = logging.getLogger(__name__)

STALE_AFTER_HOURS = 6


async def ingest_finals(pool: asyncpg.Pool, date: str, sport: str) -> None:
    """그 종목의 결과 적재 — games.status='final' + 점수."""
    from app.collectors.odds import upsert_final_scores as odds_finals

    if sport == "mlb":
        await upsert_final_scores(pool, date, client=MLBClient())
        return
    if sport == "kbo":
        try:
            from app.collectors.kbo import upsert_final_scores as kbo_finals

            await kbo_finals(pool, date, days=7)
        except Exception as exc:
            logger.warning("[finals] KBO 공식 기록실 실패, Odds 폴백: %s", exc)
            await odds_finals(pool, date, days=2, sport="kbo")
        return
    if sport == "npb":
        try:
            from app.collectors.yahoo_npb import upsert_final_scores as yahoo_finals

            await yahoo_finals(pool, date, days=3)
        except Exception as exc:
            logger.warning("[finals] Yahoo NPB 실패, Odds 폴백: %s", exc)
            await odds_finals(pool, date, days=2, sport="npb")
        return
    from app.collectors.football import (
        FootballDataClient,
        upsert_games_from_football_data,
    )

    await upsert_games_from_football_data(pool, date, client=FootballDataClient())


async def reconcile_stale_games(pool: asyncpg.Pool) -> dict:
    """시작 후 STALE_AFTER_HOURS 지났는데 final이 아닌 경기를 다시 받는다."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT sport, (starts_at AT TIME ZONE 'UTC')::date AS d
        FROM games
        WHERE status <> 'final'
          AND starts_at < now() - make_interval(hours => $1)
        ORDER BY 1, 2
        """,
        STALE_AFTER_HOURS,
    )
    fixed: dict[str, int] = {}
    for r in rows:
        sport, day = r["sport"], r["d"].strftime("%Y-%m-%d")
        count_sql = ("SELECT count(*) FROM games WHERE sport=$1 "
                     "AND (starts_at AT TIME ZONE 'UTC')::date = $2 AND status='final'")
        before = await pool.fetchval(count_sql, sport, r["d"])
        try:
            await ingest_finals(pool, day, sport)
        except Exception as exc:
            logger.warning("[finals] stale 정합 실패 %s %s: %s", sport, day, exc)
            continue
        after = await pool.fetchval(count_sql, sport, r["d"])
        fixed[sport] = fixed.get(sport, 0) + max(0, (after or 0) - (before or 0))
    if any(fixed.values()):
        logger.info("[finals] stale 경기 정합 — %s", fixed)
    return fixed
