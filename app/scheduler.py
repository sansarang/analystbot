"""APScheduler 잡 — 04:00 KST 프리페치, 30분마다 배당 스냅샷, 13:00 KST 전날 채점.

실행: python -m app.scheduler
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.collectors.base import ApiQuotaError
from app.collectors.odds import snapshot_odds
from app.config import get_settings
from app.db import get_pool
from app.grader import grade_date
from app.notify import notify_quota
from app.pipeline import run_pipeline, today_kst

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


async def prefetch_job() -> None:
    """오늘 슬레이트 프리페치 — 수집+딥서치+판정까지 캐시에 적재."""
    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        for sport in ("mlb", "soccer"):
            try:
                report = await run_pipeline(
                    pool, redis, sport=sport, date=today_kst(), force_refresh=True
                )
                logger.info("[scheduler] prefetched %s report (%d chars)", sport, len(report))
            except ApiQuotaError as exc:
                logger.error("[scheduler] prefetch %s halted by quota: %s", sport, exc)
                await notify_quota(exc.service, exc.detail)
    finally:
        await redis.aclose()


async def odds_snapshot_job() -> None:
    """30분마다 배당 스냅샷 적재 (라인 무브먼트 추적)."""
    pool = await get_pool()
    try:
        n = await snapshot_odds(pool, "mlb")
        logger.info("[scheduler] odds snapshot: %d rows", n)
    except ApiQuotaError as exc:
        logger.error("[scheduler] odds snapshot halted by quota: %s", exc)
        await notify_quota(exc.service, exc.detail)


async def elo_refresh_job() -> None:
    """주 1회 축구 Elo 데이터 갱신 (football-data.co.uk CSV + 재피팅). 리포트 발송 없음."""
    from app.models.soccer_elo import refresh

    params = await asyncio.to_thread(refresh)
    logger.info("[scheduler] elo refreshed: %s", list(params))


async def grading_job() -> None:
    """전날 결과 채점 — expert_ledger는 뷰라 자동 갱신."""
    pool = await get_pool()
    try:
        counts = await grade_date(pool, yesterday_kst(), "mlb")
        logger.info("[scheduler] graded yesterday: %s", counts)
    except ApiQuotaError as exc:
        logger.error("[scheduler] grading halted by quota: %s", exc)
        await notify_quota(exc.service, exc.detail)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=KST)
    scheduler.add_job(prefetch_job, CronTrigger(hour=4, minute=0, timezone=KST),
                      id="prefetch_daily")
    scheduler.add_job(odds_snapshot_job, IntervalTrigger(minutes=30),
                      id="odds_snapshot_30m")
    scheduler.add_job(grading_job, CronTrigger(hour=13, minute=0, timezone=KST),
                      id="grade_yesterday")
    scheduler.add_job(elo_refresh_job,
                      CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=KST),
                      id="elo_refresh_weekly")
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    get_settings().log_mock_status()
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler started: %s", [j.id for j in scheduler.get_jobs()])
    await asyncio.Event().wait()  # 종료 시그널까지 대기


if __name__ == "__main__":
    asyncio.run(main())
