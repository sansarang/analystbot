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

from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError
from app.collectors.odds import snapshot_odds
from app.config import get_settings
from app.db import get_pool
from app.grader import grade_date
from app.notify import notify_api_error
from app.pipeline import run_pipeline, today_kst

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


async def prefetch_job() -> None:
    """[1] 새벽 프리페치 = 심층 리서치 파이프라인.

    전 경기 심층 리서치(경기당 Perplexity 1콜) + 2단 판정(잠정 결론 → 반박 검증)까지
    실행해 캐시. 실패 경기는 '리서치 미완' 마킹 — 첫 요청 시 신선도 게이트가 온디맨드 보완.

    레이트리밋 방어(실사고: MLB 10경기 + 축구 17경기 동시 리서치 → 429 폭주):
    종목(리그) 단위로 순차 실행하고, 종목 안에서도 경기 단위 순차 처리한다.
    마지막에 429로 실패해 큐에 쌓인 경기를 한 번 더 순차 재시도한다.
    """
    import time

    from app.pipeline import default_date
    from app.research.deep import (
        drain_retry_queue,
        log_cost_summary,
        research_calls_today,
        research_failure_report,
    )

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    t0 = time.monotonic()
    try:
        for sport in ("mlb", "soccer"):   # 종목 단위 순차 (동시 실행 금지)
            try:
                report = await run_pipeline(
                    pool, redis, sport=sport, date=default_date(sport),
                    force_refresh=True, sequential_research=True,
                )
                logger.info("[scheduler] prefetched %s report (%d chars)", sport, len(report))
            except ApiRateLimitError as exc:   # 알림 대상 아님 — 큐 재시도로 흡수
                logger.warning("[scheduler] prefetch %s 레이트리밋 — 큐 재시도 예정: %s", sport, exc)
            except (ApiQuotaError, ApiAuthError) as exc:
                logger.error("[scheduler] prefetch %s halted (%s): %s",
                             sport, type(exc).__name__, exc)
                await notify_api_error(exc)
        recovered = await drain_retry_queue(redis)
        calls = await research_calls_today(redis)
        fails = await research_failure_report(redis, today_kst())
        logger.info("[scheduler] prefetch 총 소요 %.1fs · 금일 리서치 %d콜 (상한 60) · "
                    "큐 복구 %d경기 · 실패 %s",
                    time.monotonic() - t0, calls, recovered, fails or "없음")
        await log_cost_summary(redis)
    finally:
        await redis.aclose()


async def research_retry_job() -> None:
    """[6] 레이트리밋으로 밀린 리서치를 다음 사이클에 순차 재시도."""
    from app.research.deep import drain_retry_queue

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        recovered = await drain_retry_queue(redis)
        if recovered:
            logger.info("[scheduler] research retry: %d경기 복구", recovered)
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
    except (ApiQuotaError, ApiAuthError) as exc:
        logger.error("[scheduler] odds snapshot halted (%s): %s", type(exc).__name__, exc)
        await notify_api_error(exc)
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
    except (ApiQuotaError, ApiAuthError) as exc:
        logger.error("[scheduler] grading halted (%s): %s", type(exc).__name__, exc)
        await notify_api_error(exc)


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=KST)
    scheduler.add_job(prefetch_job, CronTrigger(hour=4, minute=0, timezone=KST),
                      id="prefetch_daily")
    scheduler.add_job(odds_snapshot_job, IntervalTrigger(minutes=30),
                      id="odds_snapshot_30m")
    scheduler.add_job(grading_job, CronTrigger(hour=13, minute=0, timezone=KST),
                      id="grade_yesterday")
    scheduler.add_job(research_retry_job, IntervalTrigger(minutes=45),
                      id="research_retry_45m")
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
