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


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


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
    from app.research.crosscheck import crosscheck_report
    from app.research.deep import (
        drain_retry_queue,
        fill_report,
        log_cost_summary,
        research_calls_today,
        research_failure_report,
    )

    from app.alerts import (
        StageResult,
        crashed,
        overall_verdict,
        prefetch_report,
    )

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    t0 = time.monotonic()
    all_stages: list[StageResult] = []
    try:
        for sport in ("mlb", "soccer"):   # 종목 단위 순차 (동시 실행 금지)
            sport_kr = "MLB" if sport == "mlb" else "축구"
            stages: list[StageResult] = []
            try:
                report = await run_pipeline(
                    pool, redis, sport=sport, date=default_date(sport),
                    force_refresh=True, sequential_research=True,
                    stages_out=stages,
                )
                logger.info("[scheduler] prefetched %s report (%d chars)", sport, len(report))
            except ApiRateLimitError as exc:   # 알림 대상 아님 — 큐 재시도로 흡수
                logger.warning("[scheduler] prefetch %s 레이트리밋 — 큐 재시도 예정: %s", sport, exc)
                stages.append(StageResult(name=f"{sport_kr} 파이프라인", ok=0, total=1,
                                          cause="rate_limit", detail=str(exc)[:150],
                                          impact="45분 뒤 재시도 큐가 보완합니다"))
            except (ApiQuotaError, ApiAuthError) as exc:
                logger.error("[scheduler] prefetch %s halted (%s): %s",
                             sport, type(exc).__name__, exc)
                await notify_api_error(exc)
                stages.append(StageResult(
                    name=f"{sport_kr} 파이프라인", ok=0, total=1,
                    cause="credit" if isinstance(exc, ApiQuotaError) else "auth",
                    detail=str(exc)[:150], impact=f"오늘 {sport_kr} 리포트가 없습니다"))
            except Exception as exc:
                # 한 종목의 예상 못 한 실패가 다른 종목까지 죽이면 안 된다.
                # (실사고: Anthropic 크레딧 소진이 400으로 와 분류를 빠져나가
                #  축구 judge에서 prefetch_job 전체가 크래시했다)
                logger.exception("[scheduler] prefetch %s 예기치 못한 실패 — 다음 종목 계속: %s",
                                 sport, exc)
                # [7-3] 크래시는 억제 없이 즉시 발송 (스택 트레이스 포함)
                await crashed(f"프리페치 {sport_kr}", exc, next_retry="내일 04:00 KST")
                from app.alerts import classify_exception, our_frames

                stages.append(StageResult(
                    name=f"{sport_kr} 파이프라인", ok=0, total=1,
                    cause=classify_exception(exc),
                    detail=f"{type(exc).__name__}: {exc}"[:150],
                    frames=our_frames(exc),
                    impact=f"오늘 {sport_kr} 리포트가 없습니다"))
            all_stages += [StageResult(name=f"[{sport_kr}] {st.name}", ok=st.ok,
                                       total=st.total, cause=st.cause, detail=st.detail,
                                       frames=st.frames, impact=st.impact)
                           for st in stages]
        recovered = await drain_retry_queue(redis)
        calls = await research_calls_today(redis)
        fails = await research_failure_report(redis, today_kst())
        logger.info("[scheduler] prefetch 총 소요 %.1fs · 금일 리서치 %d콜 (상한 60) · "
                    "큐 복구 %d경기 · 실패 %s",
                    time.monotonic() - t0, calls, recovered, fails or "없음")
        # [감시] 채움률·무효율 — 금지문 과잉(채움률 급락)·지어내기(교차검증 불일치) 신호
        today = today_kst()
        fill = await fill_report(redis, today)
        cross = await crosscheck_report(redis, today)
        logger.info(
            "[scheduler] 리서치 품질 · 경기 %s건 무효율 %s · 채움률 form %s / absences %s / "
            "splits %s / bullpen %s / form_reversal %s · 교차검증 %s항목 불일치 %s",
            fill["games"], _pct(fill["invalid_rate"]), _pct(fill["form_rate"]),
            _pct(fill["absences_rate"]), _pct(fill["splits_rate"]),
            _pct(fill["bullpen_rate"]), _pct(fill["form_reversal_rate"]),
            cross["checked"], cross["mismatch"])
        if fill["invalid_rate"] is not None and fill["invalid_rate"] > 0.30:
            logger.warning("[scheduler] ⚠️ 무효율 %s > 30%% — 무효 키워드 과잉 의심 "
                           "(docs/RESEARCH_VALIDATION.md 튜닝 기준)", _pct(fill["invalid_rate"]))
        if cross["mismatch"]:
            logger.warning("[scheduler] ⚠️ 교차검증 불일치 %d건 — 지어내기 의심, "
                           "반복되면 프롬프트 금지문 롤백 검토", cross["mismatch"])
        await log_cost_summary(redis)
    finally:
        # [7-1] 성공·실패 무관하게 **항상** 실행 리포트를 보낸다.
        #       조용한 실패 금지 — 이 발송이 실패해도 잡은 끝나야 한다.
        try:
            await prefetch_report(all_stages, time.monotonic() - t0,
                                  overall_verdict(all_stages))
        except Exception as exc:
            logger.warning("[scheduler] 프리페치 리포트 발송 실패: %s", exc)
        await redis.aclose()


async def park_refresh_job() -> None:
    """[§2] 파크팩터 주 1회 갱신 — statsapi 날짜범위 1콜. 구장 득점환경은 천천히 변한다."""
    from app.collectors.park import refresh

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        result = await refresh(redis)
        logger.info("[scheduler] 파크팩터 갱신: %s", result)
        return result
    finally:
        await redis.aclose()


async def statcast_refresh_job() -> None:
    """[2-1] Statcast 일 1회 갱신 — 조회가 무거워 프리페치 직전에만 돌린다."""
    from app.collectors.statcast import refresh
    from app.pipeline import mlb_slate_date

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        result = await refresh(redis, mlb_slate_date())
        logger.info("[scheduler] statcast 갱신: %s", result)
    finally:
        await redis.aclose()


async def soccer_stats_refresh_job() -> None:
    """[§2-3] Understat xG + Club Elo 일 1회 갱신. 스크래핑이라 느려 새벽에만 돈다."""
    from app.collectors.soccer_stats import UNSUPPORTED, refresh_elo, refresh_league
    from app.pipeline import today_kst

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    date = today_kst()
    try:
        pool = await get_pool()
        labels = [r["league"] for r in await pool.fetch(
            "SELECT DISTINCT league FROM games WHERE sport = 'soccer' "
            "AND starts_at > now() - interval '1 day'")]
        results = {}
        for label in labels:
            results[label] = await refresh_league(redis, label, date)
        results["elo"] = await refresh_elo(redis, date)
        skipped = [l for l in labels if l in UNSUPPORTED]
        logger.info("[scheduler] soccerdata 갱신: %s%s", results,
                    f" · 미지원(Perplexity 유지) {skipped}" if skipped else "")
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


async def lineup_poll_job() -> None:
    """[2-2] 확정 라인업 폴링 — 경기 4시간 전부터 30분 간격, 확정되면 중단.

    확정을 수신하면 그 경기만 재판정해 예비 픽을 최종 픽으로 갱신한다.
    """
    from app.collectors.lineups import STATUS_CONFIRMED, MLBLineupClient, refresh_mlb_lineup
    from app.pipeline import rejudge_after_lineup

    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, ext_id, sport, home, away, home_pitcher, away_pitcher,
               lineup_status, starts_at
        FROM games
        WHERE sport = 'mlb' AND status = 'scheduled'
          AND starts_at BETWEEN now() AND now() + interval '4 hours'
          AND lineup_status IS DISTINCT FROM 'confirmed'
        ORDER BY starts_at
        """
    )
    if not rows:
        return
    client = MLBLineupClient()
    updated = []
    for r in rows:
        res = await refresh_mlb_lineup(pool, dict(r), client)
        if res["changed"]:
            updated.append((dict(r), res))
    logger.info("[scheduler] 라인업 폴링 %d경기 확인 · 변경 %d건", len(rows), len(updated))
    for game, res in updated:
        try:
            await rejudge_after_lineup(game, res)
        except Exception as exc:
            logger.warning("[scheduler] 라인업 재판정 실패 game=%s: %s", game["id"], exc)
    confirmed = sum(1 for _g, r in updated if r["status"] == STATUS_CONFIRMED)
    if confirmed:
        logger.info("[scheduler] 라인업 확정 %d경기 — 최종 픽으로 갱신", confirmed)


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
    """전날 결과 채점 — expert_ledger는 뷰라 자동 갱신.

    **야구·축구 둘 다 채점한다.** 이전에는 "mlb" 고정이라 축구 픽이
    영원히 미채점으로 남았다(2026-08-25 발견: 축구 픽 result 전부 NULL).
    한 종목이 실패해도 다른 종목은 계속 채점한다.
    """
    from app.grader import reconcile_stale_games

    pool = await get_pool()
    # 상태가 밀린 경기를 먼저 정합한다 — 채점은 status='final'만 보기 때문에
    # 이걸 건너뛰면 밀린 날짜의 픽이 영원히 미채점으로 남는다.
    try:
        await reconcile_stale_games(pool)
    except Exception as exc:
        logger.warning("[scheduler] stale 정합 실패 — 채점은 계속: %s", exc)
    # [§8-37] 중복 경기 행 자가 복구. **한 번 고쳐두면 끝나는 문제가 아니다** —
    #   소스가 늘어날 때마다 같은 경기가 다른 ext_id로 다시 갈라질 수 있고,
    #   그러면 예측이 붙은 행과 결과가 들어온 행이 또 남남이 돼 채점이 조용히
    #   멈춘다(실측 2026-08-27: KBO 5 · MLB 10 · NPB 6 중복).
    #   매일 채점 직전에 합쳐서 그 상태가 하루 이상 지속되지 않게 한다.
    try:
        from app.collectors.game_match import merge_duplicate_games

        merged = await merge_duplicate_games(pool)
        if merged.get("merged"):
            logger.warning("[scheduler] 중복 경기 %d행 재발 — 병합함 (예측 %d건 이관)",
                           merged["merged"], merged.get("moved_predictions", 0))
    except Exception as exc:
        logger.warning("[scheduler] 중복 병합 실패 — 채점은 계속: %s", exc)
    totals: dict[str, dict] = {}
    for sport in ("mlb", "soccer", "kbo", "npb"):
        try:
            totals[sport] = await grade_date(pool, yesterday_kst(), sport)
        except (ApiQuotaError, ApiAuthError) as exc:
            logger.error("[scheduler] grading %s halted (%s): %s",
                         sport, type(exc).__name__, exc)
            await notify_api_error(exc)
        except Exception as exc:
            logger.exception("[scheduler] grading %s 실패 — 다음 종목 계속: %s", sport, exc)
    logger.info("[scheduler] graded yesterday: %s", totals)
    return totals


async def heartbeat_job() -> None:
    """[7-5] 스케줄러가 살아있음을 Redis에 남긴다 — /health가 이걸 본다.

    실사고(2026-08-25): 스케줄러가 꺼져 있었는데 알 방법이 없었다.
    """
    from app.health import touch_heartbeat

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await touch_heartbeat(redis)
    finally:
        await redis.aclose()


def _instrument(job_id: str, fn):
    """잡 실행 결과를 기록하고, 실패하면 [7-3] 알림까지 보낸다."""
    import functools

    @functools.wraps(fn)
    async def wrapper():
        from app.alerts import job_failed
        from app.health import record_job_run

        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        note, ok = "", True
        try:
            result = await fn()
            note = str(result)[:200] if result is not None else ""
            return result
        except Exception as exc:
            ok = False
            note = f"{type(exc).__name__}: {exc}"[:200]
            logger.exception("[scheduler] 잡 %s 실패: %s", job_id, exc)
            nxt = ""
            try:
                from datetime import datetime as _dt

                trig = _JOB_TRIGGERS.get(job_id)
                if trig is not None:
                    t = trig.get_next_fire_time(None, _dt.now(KST))
                    nxt = f"{t:%m-%d %H:%M} KST" if t else ""
            except Exception:
                nxt = ""
            await job_failed(job_id, exc, nxt)
            raise
        finally:
            try:
                await record_job_run(redis, job_id, ok, note)
            except Exception as rec_exc:
                logger.warning("[scheduler] 잡 기록 실패 %s: %s", job_id, rec_exc)
            await redis.aclose()

    return wrapper


_JOB_TRIGGERS: dict = {}

# 실사고(2026-08-26): 04:00 프리페치가 `was missed by 0:09:58`로 **건너뛰어졌다**.
# APScheduler 기본 misfire_grace_time은 1초라, 노트북 절전·부하로 조금만 늦어도
# 그날 잡이 통째로 사라진다. 하루 1회짜리 잡에는 치명적이다.
# 6시간이면 새벽 프리페치가 아침까지 늦게라도 돌고, coalesce로 밀린 실행은 1회만 한다.
MISFIRE_GRACE_SEC = 6 * 3600


# (잡 id, 함수, 트리거) — 실행 기록·실패 알림 래퍼를 일괄로 씌운다.
def _job_specs() -> list[tuple]:
    return [
        # [프리페치 2회] 실측 킥오프 분포(KST)에 맞춘다:
        #   유럽 축구 20~04시(22시 최다 19건) · MLB 05~10시(08시 최다 11건)
        #   · 아시아(J1·KBO·K리그1) 18~19시
        # 신선도 게이트가 "캐시 6h 이내 & 킥오프 3h 이상"일 때만 즉답하므로
        # 각 덩어리의 3~7시간 전에 돌아야 캐시가 실제로 쓰인다.
        #
        # 3회 이상으로 늘리면 Perplexity 일 상한 60콜을 넘긴다(실측: 1회 37콜).
        # 아시아 리그는 21:00 시점에 이미 종료돼 다음 회차 대상이 된다.
        ("prefetch_evening", prefetch_job,
         CronTrigger(hour=21, minute=0, timezone=KST)),   # 유럽 축구 (20~04시 킥오프)
        ("prefetch_dawn", prefetch_job,
         CronTrigger(hour=4, minute=30, timezone=KST)),   # MLB (05~10시 킥오프)
        ("odds_snapshot_30m", odds_snapshot_job, IntervalTrigger(minutes=30)),
        ("grade_yesterday", grading_job, CronTrigger(hour=13, minute=0, timezone=KST)),
        ("research_retry_45m", research_retry_job, IntervalTrigger(minutes=45)),
        ("lineup_poll_30m", lineup_poll_job, IntervalTrigger(minutes=30)),
        ("statcast_daily", statcast_refresh_job,
         CronTrigger(hour=3, minute=30, timezone=KST)),
        # 파크팩터는 시즌 누적이라 천천히 변한다 — 주 1회면 충분하고 statsapi 1콜이다
        ("park_weekly", park_refresh_job,
         CronTrigger(day_of_week="mon", hour=3, minute=20, timezone=KST)),
        ("soccerdata_daily", soccer_stats_refresh_job,
         CronTrigger(hour=3, minute=40, timezone=KST)),
        ("elo_refresh_weekly", elo_refresh_job,
         CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=KST)),
    ]


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=KST)
    for job_id, fn, trigger in _job_specs():
        _JOB_TRIGGERS[job_id] = trigger
        scheduler.add_job(_instrument(job_id, fn), trigger, id=job_id,
                          misfire_grace_time=MISFIRE_GRACE_SEC, coalesce=True,
                          max_instances=1)
    # [7-5] 하트비트 — 이게 살아 있어야 /health가 "스케줄러 실행 중"이라고 말한다
    scheduler.add_job(heartbeat_job, IntervalTrigger(minutes=2), id="heartbeat_2m",
                      misfire_grace_time=60, coalesce=True, max_instances=1)
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
