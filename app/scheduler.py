"""APScheduler 잡 — 04:00 KST 프리페치, 30분마다 배당 스냅샷, 13:00 KST 전날 채점.

실행: python -m app.scheduler
"""

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.collectors.base import (
    ApiAuthError, ApiQuotaError, ApiRateLimitError,
    ProviderBlockedError, ProviderDisabledError,
)
from app.collectors.odds import snapshot_odds
from app.config import get_settings
from app.collectors.finals import ingest_finals, reconcile_stale_games
from app.db import get_pool
from app.notify import notify_api_error
from app.pipeline import mlb_slate_date, run_pipeline, today_kst

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

_SPORT_KR = {"mlb": "MLB", "soccer": "축구", "kbo": "KBO", "npb": "NPB"}


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


def yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


async def prefetch_job(sports: tuple[str, ...] = ("mlb", "soccer")) -> None:
    """[1] 프리페치 = 심층 리서치 파이프라인.

    전 경기 심층 리서치(경기당 Perplexity 1콜) + 2단 판정(잠정 결론 → 반박 검증)까지
    실행해 캐시. 실패 경기는 '리서치 미완' 마킹 — 첫 요청 시 신선도 게이트가 온디맨드 보완.

    레이트리밋 방어(실사고: MLB 10경기 + 축구 17경기 동시 리서치 → 429 폭주):
    종목(리그) 단위로 순차 실행하고, 종목 안에서도 경기 단위 순차 처리한다.
    마지막에 429로 실패해 큐에 쌓인 경기를 한 번 더 순차 재시도한다.

    sports: 기본 MLB·축구(21:00·04:30). KBO·NPB는 `prefetch_asia_job`(14:00).
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
        for sport in sports:
            sport_kr = _SPORT_KR.get(sport, sport)
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
            all_stages += [replace(st, name=f"[{sport_kr}] {st.name}")
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


async def prefetch_asia_job() -> None:
    """KBO·NPB 당일 슬레이트 — 18:30 킥오프의 3~7시간 전(14:00 KST).

    라인업 폴링의 재판정은 `analysis:{sport}:{date}` 가 없으면 바로 끝난다.
    기존 21:00 프리페치 시점에는 아시아 경기가 이미 종료라 이 캐시가 안 생긴다.
    """
    await prefetch_job(sports=("kbo", "npb"))


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
    """[6] 레이트리밋으로 밀린 리서치·2단 판정을 다음 사이클에 순차 재시도."""
    from app.engine.cell_grade import drain_retry_queue as drain_cells
    from app.research.deep import drain_retry_queue

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        recovered = await drain_retry_queue(redis)
        if recovered:
            logger.info("[scheduler] research retry: %d경기 복구", recovered)
        # [#73] 전 provider 전멸로 판정 0건이던 경기 — 캐시를 무효화해
        #   다음 요청이 2단을 다시 태우게 한다. **여기서 직접 LLM을 부르지
        #   않는다** — 요청 경로와 프리페치 경로가 이미 2단을 돌린다. 같은 일을
        #   세 곳에서 하면 어느 것이 쓰였는지 알 수 없게 된다.
        pending = await drain_cells(redis)
        if pending:
            for item in pending:
                key = f"analysis:{item.get('sport')}:{item.get('date')}"
                try:
                    await redis.delete(key, key.replace("analysis:", "card:"))
                except Exception:
                    pass
            logger.info("[scheduler] 2단 재시도: %d경기 캐시 무효화", len(pending))
    finally:
        await redis.aclose()


async def lineup_poll_job() -> None:
    """[2-2] 확정 라인업 폴링 — MLB statsapi + KBO·NPB 크롤러.

    확정을 수신하면 그 경기만 재판정해 예비 픽을 최종 픽으로 갱신한다.
    """
    await mlb_pregame_poll()
    await crawler_lineup_poll()


async def mlb_pregame_poll() -> None:
    """MLB 아침 창 — statsapi 라인업 + 캐시 발송. Go 크롤러 없음.

    KBO `crawler_lineup_poll`과 대칭. 사이트만 statsapi.mlb.com.
    """
    from app.collectors.lineups import STATUS_CONFIRMED, MLBLineupClient, refresh_mlb_lineup
    from app.engine.pregame_push import send_game_prediction, still_upcoming
    from app.pipeline import rejudge_after_lineup

    s = get_settings()
    pool = await get_pool()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    date = mlb_slate_date()
    now = datetime.now(UTC)
    try:
        rows = await pool.fetch(
            """
            SELECT id, ext_id, sport, home, away, home_pitcher, away_pitcher,
                   lineup_status, starts_at, league
            FROM games
            WHERE sport = 'mlb' AND status = 'scheduled'
              AND starts_at > now()
              AND starts_at < now() + interval '4 hours'
            ORDER BY starts_at
            """
        )
        pending = [r for r in rows
                   if (r["lineup_status"] or "") != "confirmed"]
        client = MLBLineupClient()
        updated = []
        for r in pending:
            res = await refresh_mlb_lineup(
                pool, dict(r), client, redis=redis, date=date)
            if res["changed"]:
                updated.append((dict(r), res))
        if pending:
            logger.info("[scheduler] MLB 라인업 폴링 %d경기 확인 · 변경 %d건",
                        len(pending), len(updated))
        rejudged = {g["id"] for g, _ in updated}
        for game, res in updated:
            try:
                ok = await rejudge_after_lineup(game, res)
                if ok:
                    sent = await send_game_prediction(redis, game, date, now=now)
                    if sent in ("sent", "revised"):
                        logger.info("[scheduler] mlb 예측 카드 %s game=%s",
                                    sent, game["id"])
                if res["status"] == STATUS_CONFIRMED:
                    logger.info("[scheduler] MLB 라인업 확정 — 최종 픽 game=%s ok=%s",
                                game["id"], ok)
            except Exception as exc:
                logger.warning("[scheduler] MLB 라인업 재판정 실패 game=%s: %s",
                               game["id"], exc)
        for r in rows:
            if r["id"] in rejudged or not still_upcoming(r["starts_at"], now):
                continue
            try:
                sent = await send_game_prediction(redis, dict(r), date, now=now)
                if sent in ("sent", "revised"):
                    logger.info("[scheduler] mlb 예측 카드 %s game=%s",
                                sent, r["id"])
            except Exception as exc:
                logger.warning("[scheduler] mlb 발송 실패 game=%s: %s",
                               r["id"], exc)
    finally:
        await redis.aclose()


async def crawler_lineup_poll() -> None:
    """[배선] KBO·NPB 라인업을 크롤러 스냅샷에서 확인하고, 새로 뜨면 재판정한다.

    NPB는 시작 15분 전(18:00 → 17:45)까지 크롤·분석을 끝낸다. 그 시각 이후
    재판정하지 않는다. 타순이 바뀐 경기는 종목 안에서 병렬로 돌리고, 끝나는
    즉시 보낸다. 슬레이트 파이프라인(`ensure_analysis_cache`)은 저녁에 돌리지 않는다.
    ⚠️ MLB 경로(`refresh_mlb_lineup`)는 statsapi 전용이라 이 두 종목에 쓸 수 없다.
    ⚠️ 한 경기 실패가 나머지를 막지 않는다.
    """
    import redis.asyncio as aioredis

    from app.collectors import crawler_feed
    from app.engine.pregame_push import (
        analysis_open, roster_signature, send_game_prediction, still_upcoming,
        void_analysis_games,
    )
    from app.pipeline import (
        analysis_cache_ready, is_final_window,
        rejudge_after_lineup, today_kst,
    )

    s = get_settings()
    pool = await get_pool()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    now = datetime.now(UTC)
    try:
        # NPB를 먼저 — 17:45 종료선을 KBO 슬레이트에 밀리지 않게.
        for sport in ("npb", "kbo"):
            date = today_kst()
            snap = await crawler_feed.load_snapshot(redis, sport, date)
            if not snap:
                continue
            rows = await pool.fetch(
                """SELECT id, ext_id, sport, home, away, starts_at, lineup_status,
                          home_pitcher, away_pitcher
                   FROM games WHERE sport = $1 AND status = 'scheduled'
                     AND starts_at BETWEEN now() - interval '30 minutes'
                                       AND now() + interval '4 hours'""", sport)
            cancelled = await crawler_feed.mark_cancelled_games(pool, rows, snap)
            if cancelled:
                await void_analysis_games(redis, sport, date, cancelled)
                rows = [r for r in rows if r["id"] not in set(cancelled)]
            jobs: list[tuple] = []
            catchup: list = []
            for r in rows:
                game = crawler_feed.snapshot_for_game(snap, dict(r))
                have = any((game.get(f"lineup_{sd}") or "").strip()
                           for sd in ("home", "away"))
                if not have:
                    continue
                final = is_final_window(r["starts_at"], now, sport=sport)
                status = "confirmed" if final else "predicted"
                roster = roster_signature(
                    game.get("home_pitcher"), game.get("away_pitcher"),
                    game.get("lineup_home"), game.get("lineup_away"))
                sig_key = f"lineup_sig:{r['id']}"
                roster_changed = await redis.get(sig_key) != roster
                notes = []
                if (r["home_pitcher"] and game.get("home_pitcher")
                        and r["home_pitcher"] != game["home_pitcher"]):
                    notes.append(
                        f"홈 선발 변경: {r['home_pitcher']} → {game['home_pitcher']}")
                if (r["away_pitcher"] and game.get("away_pitcher")
                        and r["away_pitcher"] != game["away_pitcher"]):
                    notes.append(
                        f"원정 선발 변경: {r['away_pitcher']} → {game['away_pitcher']}")
                if roster_changed:
                    await pool.execute(
                        "UPDATE games SET lineup_status = $2, "
                        "home_pitcher = COALESCE($3, home_pitcher), "
                        "away_pitcher = COALESCE($4, away_pitcher), "
                        "updated_at = now() WHERE id = $1",
                        r["id"], status,
                        game.get("home_pitcher") or None,
                        game.get("away_pitcher") or None)
                if roster_changed and analysis_open(sport, r["starts_at"], now):
                    jobs.append((dict(r), status, notes, roster, sig_key, game))
                else:
                    if roster_changed:
                        await redis.set(sig_key, roster, ex=86400)
                        if sport == "npb" and still_upcoming(r["starts_at"], now):
                            logger.warning(
                                "[scheduler] NPB T-15 이후 라인업 변동 — 재판정 안 함 game=%s",
                                r["id"])
                    catchup.append(dict(r))

            async def _rejudge_and_send(item, *, _sport=sport, _date=date):
                row, status, notes, roster, sig_key, game = item
                raw = await redis.get(f"analysis:{_sport}:{_date}")
                if not analysis_cache_ready(raw, _date):
                    logger.warning(
                        "[scheduler] %s 캐시 없음 — 슬레이트 파이프라인 생략 game=%s",
                        _sport, row["id"])
                    return
                try:
                    ok = await rejudge_after_lineup(
                        row, {"status": status, "notes": notes,
                              "starters": {"home": game.get("home_pitcher") or None,
                                           "away": game.get("away_pitcher") or None},
                              "injuries": {}})
                    if ok:
                        await redis.set(sig_key, roster, ex=86400)
                        sent = await send_game_prediction(redis, row, _date, now=now)
                        if sent in ("sent", "revised"):
                            logger.info("[scheduler] %s 예측 카드 %s game=%s",
                                        _sport, sent, row["id"])
                    logger.info("[scheduler] %s 라인업 %s — 재판정 game=%s ok=%s",
                                _sport, status, row["id"], ok)
                except Exception as exc:
                    logger.warning("[scheduler] %s 재판정 실패 game=%s: %s",
                                   _sport, row["id"], exc)

            if jobs:
                await asyncio.gather(
                    *[_rejudge_and_send(item) for item in jobs],
                    return_exceptions=True)
            for row in catchup:
                try:
                    sent = await send_game_prediction(redis, row, date, now=now)
                    if sent in ("sent", "revised"):
                        logger.info("[scheduler] %s 예측 카드 %s game=%s",
                                    sport, sent, row["id"])
                except Exception as exc:
                    logger.warning("[scheduler] %s 발송 실패 game=%s: %s",
                                   sport, row["id"], exc)
    finally:
        await redis.aclose()


async def kbo_lineup_history_job() -> None:
    """KBO 평소 라인업 이력 — 공식 박스스코어 선발 9명을 lineup_events에 적재.

    평소 비교에 최소 5경기가 필요하다. 네이버 preview는 과거 타순을 보관하지
    않는다. `source='boxscore'`로 남겨 발표 라인업(crawler)과 구분한다.
    """
    from app.collectors.kbo import fetch_month, upsert_games
    from app.collectors.kbo_boxscore import backfill

    now = datetime.now(KST)
    months = [now.month]
    if now.month > 1:
        months.insert(0, now.month - 1)
    pool = await get_pool()
    games: list[dict] = []
    for mo in months:
        try:
            games.extend(await fetch_month(now.year, mo))
        except Exception as exc:
            logger.warning("[scheduler] KBO 일정 %d-%02d 조회 실패: %s",
                           now.year, mo, exc)
    try:
        n = await upsert_games(pool, games) if games else 0
    except Exception as exc:
        logger.warning("[scheduler] KBO 일정 적재 실패: %s", exc)
        n = 0
    try:
        stats = await backfill(pool, now.year, tuple(months), limit_per_team=10)
    except Exception as exc:
        logger.warning("[scheduler] KBO 라인업 백필 실패: %s", exc)
        stats = {}
    logger.info("[scheduler] KBO 라인업 이력 upsert %d · 백필 %s", n, stats)


async def npb_lineup_history_job() -> None:
    """NPB 평소 라인업 이력 — Yahoo 종료 경기 打順 9명을 lineup_events에 적재.

    타순은 경기 시작 약 30분 전에야 뜨므로(スポナビ 도움말) 당일 오전 백필은
    어제 이전 종료 분만 쌓인다. `source='boxscore'`로 발표 라인업과 구분한다.
    일정 upsert 창은 백필과 같은 APPEARANCE_DAYS(21) — 3일만 넣으면 나머지
    경기는 no_game. 14일이면 오늘 선발 등판이 1회로 끊긴다.
    """
    from app.collectors.npb_boxscore import APPEARANCE_DAYS, backfill
    from app.collectors.yahoo_npb import upsert_schedule

    now = datetime.now(KST)
    pool = await get_pool()
    n = 0
    days = APPEARANCE_DAYS
    for back in range(days):
        day = (now.date() - timedelta(days=back)).isoformat()
        try:
            counts = await upsert_schedule(pool, day)
            n += counts.get("total") or 0
        except Exception as exc:
            logger.warning("[scheduler] NPB 일정 %s 적재 실패: %s", day, exc)
    try:
        stats = await backfill(pool, as_of=now.date(), days=days, limit_per_team=10)
    except Exception as exc:
        logger.warning("[scheduler] NPB 라인업 백필 실패: %s", exc)
        stats = {}
    logger.info("[scheduler] NPB 라인업 이력 upsert %d · 백필 %s", n, stats)


async def mlb_lineup_history_job() -> None:
    """MLB 평소 라인업 이력 — statsapi 종료 경기 타순 9명을 lineup_events에 적재.

    KBO·NPB 백필과 같다. 사이트만 statsapi. `source='boxscore'`.
    """
    from app.collectors.mlb_boxscore import APPEARANCE_DAYS, ET, backfill

    now = datetime.now(ET)
    pool = await get_pool()
    try:
        stats = await backfill(pool, as_of=now.date(), days=APPEARANCE_DAYS,
                               limit_per_team=10)
    except Exception as exc:
        logger.warning("[scheduler] MLB 라인업 백필 실패: %s", exc)
        stats = {}
    logger.info("[scheduler] MLB 라인업 이력 백필 %s", stats)


async def odds_snapshot_job() -> None:
    """배당 스냅샷 — 크레딧 예산 관리:

    경기가 있는 리그만 조회. 킥오프 3시간 전부터는 30분 간격(매 실행),
    그 외 시간대는 리그당 3시간 간격. 사용량·잔여량은 snapshot 시 로그·Redis 기록.
    """
    import redis.asyncio as aioredis

    from app.api_guard import is_blocked, is_disabled
    from app.collectors.odds import SPORT_KEYS
    from app.leagues import LEAGUES

    if is_disabled("odds") or await is_blocked("odds"):
        logger.info("[scheduler] odds snapshot skipped — %s",
                    "disabled" if is_disabled("odds") else "차단 중 (호출 없음)")
        return

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        rows = await pool.fetch(
            "SELECT sport, league, min(starts_at) AS next_kick FROM games "
            "WHERE status = 'scheduled' AND starts_at > now() - interval '1 hour' "
            "GROUP BY sport, league"
        )
        label_to_key = {c["label"]: c["odds_key"] for c in LEAGUES.values()}
        due: dict[str, list[str]] = {}
        now = datetime.now(KST)
        for r in rows:
            if r["sport"] in ("mlb", "kbo", "npb"):
                # 야구는 totals 라인만. 승부 배당 키는 넣지 않는다.
                keys_for = SPORT_KEYS.get(r["sport"]) or []
                key = keys_for[0] if keys_for else None
            else:
                key = label_to_key.get(r["league"])
            if key is None:
                continue
            within_3h = (r["next_kick"].astimezone(KST) - now) <= timedelta(hours=3)
            last = await redis.get(f"oddsnap:{key}")
            stale = last is None or (now.timestamp() - float(last)) >= 3 * 3600
            if within_3h or stale:
                due.setdefault(r["sport"], []).append(key)
        total = 0
        for sport, keys in due.items():
            if not keys:
                continue
            total += await snapshot_odds(pool, sport, only_keys=sorted(set(keys)))
            for key in keys:
                await redis.set(f"oddsnap:{key}", str(now.timestamp()), ex=86400)
        logger.info("[scheduler] odds snapshot: %d rows (keys=%s)",
                    total, {s: sorted(set(k)) for s, k in due.items() if k})
    except (ProviderDisabledError, ProviderBlockedError):
        logger.info("[scheduler] odds snapshot skipped — disabled/blocked")
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


async def finals_job() -> None:
    """전날 종료 점수 적재. **픽 채점은 하지 않는다** (2026-08-29 사용자 지시).

    목표는 이 경기 적중이다 (DISCIPLINE 4). 남는 일은 games에 결과를 채우는
    것뿐이고, 그것은 다음 날 폼 패킷(지난 3경기)의 재료가 된다.

    **야구·축구 넷 다 적재한다.** 한 종목이 실패해도 나머지는 계속한다.
    """
    pool = await get_pool()
    # 상태가 밀린 경기를 먼저 정합한다 — 적재는 그 날짜를 다시 받아오는 일이라
    # 이걸 건너뛰면 밀린 날짜가 영원히 scheduled로 남는다.
    try:
        await reconcile_stale_games(pool)
    except Exception as exc:
        logger.warning("[scheduler] stale 정합 실패 — 적재는 계속: %s", exc)
    # [§8-37] 중복 경기 행 자가 복구. **한 번 고쳐두면 끝나는 문제가 아니다** —
    #   소스가 늘어날 때마다 같은 경기가 다른 ext_id로 다시 갈라질 수 있고,
    #   그러면 예측이 붙은 행과 점수가 들어온 행이 또 남남이 된다
    #   (실측 2026-08-27: KBO 5 · MLB 10 · NPB 6 중복).
    #   ⚠️ **반드시 적재보다 먼저** 합친다 — 뒤에 하면 그날도 중복 상태로 돈다.
    try:
        from app.collectors.game_match import merge_duplicate_games

        merged = await merge_duplicate_games(pool)
        if merged.get("merged"):
            logger.warning("[scheduler] 중복 경기 %d행 재발 — 병합함 (예측 %d건 이관)",
                           merged["merged"], merged.get("moved_predictions", 0))
    except Exception as exc:
        logger.warning("[scheduler] 중복 병합 실패 — 적재는 계속: %s", exc)
    done: dict[str, object] = {}
    for sport in ("mlb", "soccer", "kbo", "npb"):
        try:
            done[sport] = await ingest_finals(pool, yesterday_kst(), sport)
        except (ApiQuotaError, ApiAuthError) as exc:
            logger.error("[scheduler] finals %s halted (%s): %s",
                         sport, type(exc).__name__, exc)
            await notify_api_error(exc)
        except Exception as exc:
            logger.exception("[scheduler] finals %s 실패 — 다음 종목 계속: %s", sport, exc)
    logger.info("[scheduler] 종료 점수 적재: %s", sorted(done))
    return done


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
        # 아시아 야구 18:30 — 라인업 폴링이 쓰는 analysis 캐시를 여기서 만든다.
        # 21:00 슬롯에 넣으면 당일 경기는 이미 끝나 있다.
        ("prefetch_asia", prefetch_asia_job,
         CronTrigger(hour=14, minute=0, timezone=KST)),
        ("odds_snapshot_30m", odds_snapshot_job, IntervalTrigger(minutes=30)),
        ("ingest_finals_13h", finals_job, CronTrigger(hour=13, minute=0, timezone=KST)),
        ("research_retry_45m", research_retry_job, IntervalTrigger(minutes=45)),
        ("lineup_poll_30m", lineup_poll_job, IntervalTrigger(minutes=30)),
        # NPB 18:00 → 17:45까지 크롤·분석 종료. KBO는 시작 직전까지 5분마다.
        ("asia_pregame_5m", crawler_lineup_poll,
         CronTrigger(hour="17,18", minute="0,5,10,15,20,25,30,35,40,45,50,55",
                     timezone=KST)),
        # MLB 아침 슬레이트 (05~11 KST). 사이트는 statsapi. 캐시만 보낸다.
        ("mlb_pregame_5m", mlb_pregame_poll,
         CronTrigger(hour="5-11", minute="0,5,10,15,20,25,30,35,40,45,50,55",
                     timezone=KST)),
        ("statcast_daily", statcast_refresh_job,
         CronTrigger(hour=3, minute=30, timezone=KST)),
        # 파크팩터는 시즌 누적이라 천천히 변한다 — 주 1회면 충분하고 statsapi 1콜이다
        ("park_weekly", park_refresh_job,
         CronTrigger(day_of_week="mon", hour=3, minute=20, timezone=KST)),
        ("soccerdata_daily", soccer_stats_refresh_job,
         CronTrigger(hour=3, minute=40, timezone=KST)),
        ("elo_refresh_weekly", elo_refresh_job,
         CronTrigger(day_of_week="mon", hour=5, minute=0, timezone=KST)),
        # 평소 라인업 비교에 최소 5경기가 필요한데, 네이버는 과거 타순을 안 남긴다.
        # 박스스코어 선발 9명을 하루 1회 적재한다 (30분 폴링에 넣으면 HTTP가 폭주한다).
        ("kbo_lineup_history", kbo_lineup_history_job,
         CronTrigger(hour=5, minute=20, timezone=KST)),
        # NPB는 Yahoo `/top` 종료 경기 打順. 오전엔 오늘 타순이 없다(시작 ~30분 전).
        ("npb_lineup_history", npb_lineup_history_job,
         CronTrigger(hour=5, minute=25, timezone=KST)),
        ("mlb_lineup_history", mlb_lineup_history_job,
         CronTrigger(hour=5, minute=15, timezone=KST)),
    ]


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=KST)
    for job_id, fn, trigger in _job_specs():
        _JOB_TRIGGERS[job_id] = trigger
        if job_id in ("asia_pregame_5m", "mlb_pregame_5m"):
            grace = 4 * 60
        else:
            grace = MISFIRE_GRACE_SEC
        scheduler.add_job(_instrument(job_id, fn), trigger, id=job_id,
                          misfire_grace_time=grace, coalesce=True,
                          max_instances=1)
    # [7-5] 하트비트 — 이게 살아 있어야 /health가 "스케줄러 실행 중"이라고 말한다
    scheduler.add_job(heartbeat_job, IntervalTrigger(minutes=2), id="heartbeat_2m",
                      misfire_grace_time=60, coalesce=True, max_instances=1)
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.version import boot_line

    logger.info(boot_line("scheduler"))
    get_settings().log_mock_status()
    # [§8-39] **기동 시 스키마를 적용한다.**
    #   실사고(2026-08-27): `apply_schema`는 있었지만 수동(`python -m app.db init`)
    #   전용이라 아무도 부르지 않았다. 그 결과 로컬에만 컬럼이 생기고 서버에는
    #   없어서, 새 코드를 배포하면 `lam_total` INSERT가 곧바로 터지는 상태였다.
    #   schema.sql은 전부 IF NOT EXISTS·DROP NOT NULL이라 **멱등**이다
    #   (2회 연속 적용 실증). 스케줄러는 단일 인스턴스라 여기가 적용 지점이다.
    #   ⚠️ 실패해도 기동은 계속한다 — 마이그레이션 실패로 봇 전체가 죽으면
    #      더 나쁘다. 대신 크게 로그를 남긴다.
    try:
        from app.db import apply_schema, get_pool

        await apply_schema(await get_pool())
        logger.info("[scheduler] 스키마 적용 완료")
    except Exception as exc:
        logger.error("[scheduler] 🔴 스키마 적용 실패 — 새 컬럼이 없으면 "
                     "예측 기록이 터진다: %s", exc)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler started: %s", [j.id for j in scheduler.get_jobs()])
    await asyncio.Event().wait()  # 종료 시그널까지 대기


if __name__ == "__main__":
    asyncio.run(main())
