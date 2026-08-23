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
    """배당 스냅샷 — 크레딧 예산 관리:

    경기가 있는 리그만 조회. 킥오프 3시간 전부터는 30분 간격(매 실행),
    그 외 시간대는 리그당 3시간 간격. 사용량·잔여량은 snapshot 시 로그·Redis 기록.
    """
    import redis.asyncio as aioredis

    from app.leagues import LEAGUES

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        rows = await pool.fetch(
            "SELECT sport, league, min(starts_at) AS next_kick FROM games "
            "WHERE status = 'scheduled' AND starts_at > now() - interval '1 hour' "
            "GROUP BY sport, league"
        )
        label_to_key = {c["label"]: c["odds_key"] for c in LEAGUES.values()}
        due: dict[str, list[str]] = {"mlb": [], "soccer": []}
        now = datetime.now(KST)
        for r in rows:
            key = "baseball_mlb" if r["sport"] == "mlb" else label_to_key.get(r["league"])
            if key is None:
                continue
            within_3h = (r["next_kick"].astimezone(KST) - now) <= timedelta(hours=3)
            last = await redis.get(f"oddsnap:{key}")
            stale = last is None or (now.timestamp() - float(last)) >= 3 * 3600
            if within_3h or stale:
                due[r["sport"]].append(key)
        total = 0
        for sport, keys in due.items():
            if not keys:
                continue
            total += await snapshot_odds(pool, sport, only_keys=sorted(set(keys)))
            for key in keys:
                await redis.set(f"oddsnap:{key}", str(now.timestamp()), ex=86400)
        logger.info("[scheduler] odds snapshot: %d rows (keys=%s)",
                    total, {s: sorted(set(k)) for s, k in due.items() if k})
    except ApiQuotaError as exc:
        logger.error("[scheduler] odds snapshot halted by quota: %s", exc)
        await notify_quota(exc.service, exc.detail)
    finally:
        await redis.aclose()


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
