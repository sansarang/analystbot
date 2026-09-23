"""APScheduler 잡 — 04:00 KST 프리페치, 30분마다 배당 스냅샷, 13:00 KST 전날 채점.

실행: python -m app.scheduler
"""

import asyncio
import json
import logging
import os
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
        # [휴식일] 대상 리그가 **전부** 경기 없음이면 한 장으로 알린다.
        #   종전에는 이 날 7건이 🔴로 나가고 "전량 실패 — 신뢰도 낮음"으로 끝나서,
        #   사용자가 장애인지 휴식일인지 알 수 없었다(실측 2026-08-31 14:01).
        try:
            await _notify_rest_day(all_stages, sports)
        except Exception as exc:
            logger.warning("[scheduler] 휴식일 안내 실패 — 프리페치는 계속: %s", exc)
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


async def _notify_rest_day(all_stages, sports) -> bool:
    """대상 리그가 전부 휴식일이면 텔레그램 1장. 아니면 아무것도 하지 않는다.

    ⚠️ **일부만 휴식일이면 보내지 않는다.** 경기가 있는 리그의 리포트가 따로
       나가는데 "경기 없습니다"를 같이 보내면 서로 모순으로 읽힌다.
    ⚠️ 실패가 하나라도 섞였으면 보내지 않는다 — 휴식일이라고 단정할 근거가 없다.
    """
    from app.alerts import _no_game_leagues
    from app.notify import send_telegram
    from app.pipeline import next_slate_hint

    rest = _no_game_leagues(all_stages)
    want = [_SPORT_KR.get(s, s) for s in sports]
    if not rest or set(rest) != set(want):
        return False
    if any(st.failed for st in all_stages):
        return False
    nxt = await next_slate_hint(await get_pool(), sports)
    text = (f"\U0001f5d3\ufe0f 오늘은 {'·'.join(want)} 경기가 없습니다.\n"
            f"다음 슬레이트: {nxt}")
    logger.info("[scheduler] 휴식일 안내 발송 — %s", ", ".join(want))
    return await send_telegram(text)


async def soccer_trial_job() -> None:
    """[축구 시범 운영] T-3h 판정 · confirmed 재판정 → 카드 발송.

    ⚠️ **야구 경로와 완전히 분리돼 있다.** 이 잡이 실패해도 야구 발송·판정에
       영향이 없다 — 전 구간 예외 격리이며, soccer_trial 모듈은 야구 코드를
       수정하지 않는다(import 경계 테스트로 잠금).
    ⚠️ 시범 운영 등급이다. 카드에 "⚽️ 축구 · 시범 운영" 라벨이 붙고,
       레저에는 trial=true 로 기록돼 캘리브레이션에서 분리 집계된다.
    """
    import redis.asyncio as aioredis

    from app.notify import send_telegram

    s = get_settings()
    # 🔴 [2026-09-06 사용자 지시] Anthropic 은 최종 판정에서만 쓴다.
    #    soccer_trial 은 `judge_route.chain` 을 타지 않고 Anthropic 을 직접
    #    부르므로, 스위치가 꺼져 있으면 **수집도 하지 않고** 돌아간다.
    if not s.soccer_trial_enabled:
        logger.info("[soccer-trial] 꺼짐(SOCCER_TRIAL_ENABLED=false) — "
                    "Anthropic 직접 호출 경로라 돌리지 않는다")
        return
    from app.engine.soccer_trial import run_once

    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        out = await run_once(pool, redis, send=send_telegram)
        if out["judged"] or out["resent"]:
            logger.info("[soccer-trial] 판정 %d · 재판정 %d · 생략 %d · 상한 %d",
                        out["judged"], out["resent"], out["skipped"], out["capped"])
    except Exception as exc:
        logger.exception("[soccer-trial] 실패 — 야구 경로에는 영향 없음: %s", exc)
    finally:
        await redis.aclose()


async def daily_summary_asia_job() -> None:
    """[일일 요약] 17:35 KST — 당일 KBO·NPB 판정 요약 1장."""
    await _send_daily_summary(("kbo", "npb"), "🇰🇷🇯🇵 오늘 아시아 픽 요약")


async def daily_summary_overseas_job() -> None:
    """[일일 요약] 05:30 KST — MLB 아침 슬레이트 요약 1장.

    04:30 prefetch_dawn 이 판정을 만든 **뒤**여야 한다 — 종전 21:00은
    판정보다 앞서서 매일 "픽 없음"만 나갔다(실측 2026-08-31).
    """
    await _send_daily_summary(("mlb",), "🌏 오늘 MLB 픽 요약")


async def daily_summary_soccer_job() -> None:
    """[일일 요약] 01:45 KST — 그날 밤 유럽 축구 요약 1장.

    T-3h 판정이 22:30부터 돌아 01:30이면 대부분 끝나 있다. 가장 이른
    킥오프(01:30)를 이미 지난 경기는 조회에서 빠진다 — 걸 수 없는 것을
    목록에 올리지 않는다.
    """
    await _send_daily_summary(("soccer",), "⚽️ 오늘 밤 유럽 픽 요약")


async def _send_daily_summary(sports, title: str) -> None:
    """요약 카드 발송. 추천 0건인 날도 보낸다 — "픽 없음"도 정보다.

    ⚠️ 요약 실패가 경기별 카드 발송을 막지 않는다 (별개 잡).
    """
    from app.engine.daily_summary import build
    from app.notify import send_telegram
    from app.pipeline import today_kst

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        text = await build(await get_pool(), tuple(sports), title, today_kst(),
                           redis=redis)
    except Exception as exc:
        logger.exception("[daily-summary] 집계 실패: %s", exc)
        return
    finally:
        try:
            await redis.aclose()
        except Exception as exc:      # 닫기 실패가 요약을 막지 않는다
            logger.debug("[daily-summary] redis 닫기 실패: %s", exc)
    if not text:
        logger.warning("[daily-summary] 빈 카드 — 발송 생략")
        return
    await send_telegram(text)
    logger.info("[daily-summary] 발송 — %s", title)


async def prefetch_asia_job() -> None:
    """KBO·NPB 당일 슬레이트 — 18:30 킥오프의 3~7시간 전(14:00 KST).

    라인업 폴링의 재판정은 `analysis:{sport}:{date}` 가 없으면 바로 끝난다.
    기존 21:00 프리페치 시점에는 아시아 경기가 이미 종료라 이 캐시가 안 생긴다.

    🔴 [SP-3 2026-09-23] **캐시를 만든 뒤 선발을 `games` 로 옮긴다.** 흐름 ⑤는
       `games.home_pitcher` 를 읽는데 그 칸에 쓰는 코드가 `naver_kbo`(KBO 전용)
       하나뿐이라 NPB 는 늘 비어 있었고, 실측에서 NPB 6경기가 전부 ⑥
       "모름과반"으로 멈췄다(같은 시각 캐시에는 이름이 있었다).
    ⚠️ 옮기기가 실패해도 프리페치 결과를 버리지 않는다.
    """
    sports = ("kbo", "npb")
    await prefetch_job(sports=sports)
    try:
        from app.collectors.lineups import upsert_probables_from_analysis

        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            day = datetime.now(KST).date().isoformat()
            pool = await get_pool()
            for sp in sports:
                got = await upsert_probables_from_analysis(pool, redis, sp, day)
                logger.info("[scheduler] %s 예고선발 → games: %s", sp, got)
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.warning("[scheduler] 예고선발 적재 실패: %s", exc)


async def park_refresh_job() -> None:
    """[§2] 파크팩터 주 1회 갱신 — statsapi 날짜범위 1콜. 구장 득점환경은 천천히 변한다."""
    from app.collectors.park import refresh

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        result = await refresh(redis)
        logger.info("[scheduler] 파크팩터 갱신(MLB): %s", result)
        # 🔴 [VEN-1 2026-09-23] **KBO 도 같은 잡에서 돌린다.** 모듈은 멀쩡했고
        #    (실측: stadiums 9 · games 782), 종전 0 은 `koreabaseball` 게이트
        #    때문이었다(2026-09-23 KBO-ON 으로 켰다). 부르는 곳이 없어서
        #    `park_factor` 가 야구 전 리그에서 언제나 미상이었다.
        #    ⚠️ 새 잡을 만들지 않는다 — 주기가 두 벌이 되면 한쪽만 도는 날이
        #       생긴다. 실패해도 MLB 결과를 버리지 않는다.
        try:
            from app.collectors.kbo_park import refresh as kbo_refresh

            kbo = await kbo_refresh(redis)
            logger.info("[scheduler] 파크팩터 갱신(KBO): %s", kbo)
            result = {"mlb": result, "kbo": kbo}
        except Exception as exc:
            logger.warning("[scheduler] KBO 파크팩터 갱신 실패: %s", exc)
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


async def flow_shadow_job() -> None:
    """[v1.4 STEP 13] 새 파이프라인 섀도 실행 — **관측 전용.**

    🔴 `PIPELINE_V14` 가 꺼져 있으면 즉시 반환한다(배포해도 무해).
       발송은 `PIPELINE_V14_SEND` 가 따로 가른다.
    🔴 **창에 매이지 않는다.** 실사고 2026-09-19: 폴링 창 안에 넣었더니 창이
       닫힌 시간대에 한 번도 돌지 않았다. 관측은 창과 무관해야 한다.
    ⚠️ 기존 경로를 건드리지 않는다 — 실패해도 로그 한 줄이다.
    """
    s = get_settings()
    if not getattr(s, "pipeline_v14", False):
        return
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    try:
        from app.flow.bridge import run_today

        out = await run_today(await get_pool(), redis)
        logger.info("[scheduler] v1.4 섀도 %s", out)
    except Exception as exc:
        logger.warning("[scheduler] v1.4 섀도 실패: %s", exc)
    finally:
        await redis.aclose()


# ══════════════════════════════════════════════════════════════════
# [EXP-2] T-3h · T-60 자동 내보내기
#
# 🔴 **읽기 전용이다.** 발송 경로를 타지 않는다 — `n13_send` 도 `_send_card` 도
#    부르지 않는다. 규율 9(발송 중단 유지)를 깨지 않는다.
# 🔴 리그 목록을 **손으로 적지 않는다** — `for_fable.LEAGUE_SPORT` 가 원본이다.
# ⚠️ 창(window)이 아니라 **문턱**으로 쏜다. 창으로 하면 한 틱만 밀려도 그날
#    산출물이 통째로 없어진다(실사고 2026-09-19 `run_slate`).
# ══════════════════════════════════════════════════════════════════

#: 단계별 문턱 — 첫 경기 킥오프까지 남은 시간이 이보다 작아지면 쏜다.
EXPORT_LEAD: dict = {"t3h": timedelta(hours=3), "lineup": timedelta(minutes=60)}

#: 하루 1회 표시. 🔴 `SET NX` 로 잡는다 — 잡이 겹쳐 돌아도 두 번 쓰지 않는다.
EXPORT_MARK_TTL = 20 * 3600

#: 오늘 KST 슬레이트에서 리그별 **가장 이른 미시작 경기**.
#  🔴 내보내기 전용이 아니다 — ODN-3 도 같은 판단(첫 경기까지 남은 시간)을
#     쓰므로 이름에서 `EXPORT` 를 뺐다. 같은 사실은 한 곳에서 읽는다.
_SLATE_FIRST_SQL = """
    SELECT sport, league, min(starts_at) AS first_kickoff
      FROM games
     WHERE status = 'scheduled' AND starts_at > now()
       AND (starts_at AT TIME ZONE 'Asia/Seoul')::date
           = (now() AT TIME ZONE 'Asia/Seoul')::date
     GROUP BY sport, league
"""


def _export_league_code(sport: str, league: str) -> str | None:
    """`games` 한 행 → 내보내기 `--league` 코드. 모르면 None(건너뛴다)."""
    from app.export.for_fable import LEAGUE_SPORT, SOCCER_LABEL

    sp = (sport or "").lower()
    if sp in LEAGUE_SPORT and LEAGUE_SPORT[sp] == sp:
        return sp                                  # mlb · kbo · npb
    for code, label in SOCCER_LABEL.items():       # uel · ucl · kleague
        if str(league or "").strip() == label:
            return code
    return None


async def _export_stage(stage: str) -> dict:
    """한 단계를 쏜다. 반환은 `{리그: 경로}` — **조용한 0 을 막는 기록**이다."""
    from app.export.for_fable import collect, write

    s = get_settings()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    out: dict = {}
    try:
        pool = await get_pool()
        rows = [dict(r) for r in await pool.fetch(_SLATE_FIRST_SQL)]
        now = datetime.now(UTC)
        lead = EXPORT_LEAD[stage]
        for r in rows:
            code = _export_league_code(r["sport"], r["league"])
            if code is None:
                continue
            first = r["first_kickoff"]
            if first.tzinfo is None:
                first = first.replace(tzinfo=UTC)
            if first - now > lead:
                continue                            # 아직 이르다
            date_kst = datetime.now(KST).date().isoformat()
            mark = f"export:{code}:{date_kst}:{stage}"
            if not await redis.set(mark, "1", ex=EXPORT_MARK_TTL, nx=True):
                continue                            # 오늘 이미 썼다
            try:
                doc = await collect(code, date_kst)
                doc["export_meta"]["stage"] = stage
                p, md = write(doc, stage=stage)
                out[code] = str(p)
                logger.info("[export] %s %s — %d경기 · %s (%d바이트)",
                            stage, code, len(doc["games"]), p, p.stat().st_size)
            except Exception as exc:
                await redis.delete(mark)            # 실패는 표시를 남기지 않는다
                logger.warning("[export] %s %s 실패: %s", stage, code, exc)
    finally:
        await redis.aclose()
    return out


#: [ODN-3] 한 번에 긁는 MLB 경기 수. 🔴 **예산에서 나온 숫자다.**
#   실측 2026-09-19: 109/1000 · 1.7일 → 하루 ~64콜. KBO·NPB 정기 잡만으로
#   월 720콜이라 MLB 여유는 하루 5콜 안쪽이다(경기 1건 = 스냅샷 1콜).
#   창 안 MLB 는 27경기 — 전수면 월 1,620콜이고 소스가 통째로 죽는다.
MLB_DERIV_CAP = 4

#: 게이트 대상을 고를 때 쓰는 스냅샷. 🔴 `analysis_runs` 가 원본이다 —
#  라벨 목록을 손으로 적지 않고 `stop` 을 읽는다.
_GATE_SQL = """
    SELECT DISTINCT ON (a.game_id)
           a.game_id,
           a.snapshot_json->'n03_gate'->>'gate'   AS gate,
           a.snapshot_json->'n03_gate'->>'stop'   AS stop,
           a.snapshot_json->'n03_gate'->>'gap_pp' AS gap_pp
      FROM analysis_runs a
      JOIN games g ON g.id::text = a.game_id::text
     WHERE a.node = 'n03_gate'
       AND g.sport = 'mlb' AND g.status = 'scheduled'
       AND g.starts_at > now()
     ORDER BY a.game_id, a.created_at_utc DESC
"""


def pick_deriv_targets(rows: list[dict], *, cap: int) -> tuple[list, dict]:
    """게이트 대상만, `|gap|` 큰 순으로 `cap` 개. 반환 `(고른 것, 버린 사유별 수)`.

    🔴 **버린 수를 센다.** 조용히 자르면 "전부 훑었다"로 읽히고, 그 오해가
       다음 사람의 판단을 바꾼다.
    ⚠️ 괴리를 모르는 경기는 **뒤로** 보낸다 — 앞에 두면 상한이 그쪽에 다 쓰인다.
    """
    dropped: dict = {}
    live = []
    for r in rows or []:
        stop = r.get("stop")
        if stop is True or str(stop).lower() == "true":
            k = str(r.get("gate") or "보드고정")
            dropped[k] = dropped.get(k, 0) + 1
            continue
        live.append(r)

    def _gap(r):
        try:
            return abs(float(r.get("gap_pp")))
        except (TypeError, ValueError):
            return None

    live.sort(key=lambda r: (_gap(r) is None, -(_gap(r) or 0.0)))
    if len(live) > cap:
        dropped["상한초과"] = len(live) - cap
        live = live[:cap]
    return live, dropped


async def odds_mlb_deriv_job() -> None:
    """[ODN-3] MLB 팀토탈·F5 — **게이트 대상만, 하루 1회.**

    🔴 정기 잡(`oddsapinet_2x`)에 얹지 않는다. 그쪽은 15:30·17:30 이라 MLB
       슬레이트(KST 05~12)가 이미 끝나 있다.
    🔴 예산 가드가 두 겹이다: `budget_ok()`(80% 문턱) + `MLB_DERIV_CAP`(건수).
       앞의 것만 있으면 한 번에 27경기를 긁어 하루에 80% 를 넘길 수 있다.
    ⚠️ 대상이 0이어도 **로그를 남긴다** — "긁을 게 없었다"와 "잡이 안 돌았다"는
       다르다.
    """
    from app.collectors import oddsapinet as ON
    from app.collectors.odds_free import store_rows

    if not ON._key():
        return
    s = get_settings()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        rows = [dict(r) for r in await pool.fetch(_SLATE_FIRST_SQL)]
        mlb = [r for r in rows if (r.get("sport") or "") == "mlb"]
        if not mlb:
            return
        first = mlb[0]["first_kickoff"]
        if first.tzinfo is None:
            first = first.replace(tzinfo=UTC)
        if first - datetime.now(UTC) > EXPORT_LEAD["t3h"]:
            return                                   # 아직 이르다
        date_kst = datetime.now(KST).date().isoformat()
        if not await redis.set(f"odds_mlb_deriv:{date_kst}", "1",
                               ex=EXPORT_MARK_TTL, nx=True):
            return                                   # 오늘 이미 긁었다
        if not await ON.budget_ok():
            logger.info("[odds-mlb] 예산 문턱 — 건너뜀")
            return

        gates = [dict(r) for r in await pool.fetch(_GATE_SQL)]
        targets, dropped = pick_deriv_targets(gates, cap=MLB_DERIV_CAP)
        logger.info("[odds-mlb] 게이트 %d경기 중 %d경기 대상 · 버림 %s",
                    len(gates), len(targets), dropped or "없음")
        if not targets:
            return

        by_id = {str(r["id"]): r for r in await pool.fetch(
            "SELECT id, home, away FROM games WHERE sport='mlb'"
            " AND status='scheduled' AND starts_at > now()")}
        evs = await ON.fetch_events("mlb")
        total = 0
        for t in targets:
            g = by_id.get(str(t["game_id"]))
            if not g:
                continue
            ev = _match_event(evs, g["home"], g["away"])
            if ev is None:
                logger.info("[odds-mlb] game=%s 소스에서 못 찾음 (%s @ %s)",
                            t["game_id"], g["away"], g["home"])
                continue
            items = await ON.fetch_odds(ev.get("event_id") or ev.get("id"))
            out = ON.to_rows(items, home=g["home"], away=g["away"])
            if out:
                await store_rows(pool, int(g["id"]), out, provider=ON.PROVIDER)
                total += len(out)
        logger.info("[odds-mlb] %d경기 · %d행 적재", len(targets), total)
    except Exception as exc:
        logger.warning("[odds-mlb] 실패: %s", exc)
    finally:
        await redis.aclose()


def _match_event(evs: list, home: str, away: str):
    """소스 이벤트 목록에서 우리 경기를 찾는다. 못 찾으면 None(지어내지 않는다)."""
    def norm(x):
        return "".join(ch for ch in str(x or "").lower() if ch.isalnum())

    h, a = norm(home), norm(away)
    for ev in evs or []:
        eh, ea = norm(ev.get("home_team")), norm(ev.get("away_team"))
        if (h and eh and (h in eh or eh in h)) and (a and ea and (a in ea or ea in a)):
            return ev
    return None


async def export_t3h_job() -> None:
    """킥오프 3시간 전 내보내기. 🔴 리그별 **첫 경기** 기준이다."""
    got = await _export_stage("t3h")
    if got:
        logger.info("[scheduler] export t3h %s", got)


async def export_lineup_job() -> None:
    """라인업 확정 시점(T-60) 재내보내기. 파일명에 `_lineup` 이 붙는다."""
    got = await _export_stage("lineup")
    if got:
        logger.info("[scheduler] export lineup %s", got)


async def satellite_job() -> None:
    """[SAT] 위성 수집 — DB에 없는 경기 정보를 미리 긁어 캐시에 쌓는다.

    ⚠️ **기본 꺼짐.** `satellite_enabled` 가 아니면 즉시 반환한다 — 배포해도
       무해하다. 딥서치가 이 캐시를 읽는 것은 별개 배선(증분2)이라, 이 잡만으로는
       판정 경로가 바뀌지 않는다.
    """
    from app.collectors import satellite

    s = get_settings()
    if not s.satellite_enabled:
        return
    sports = [x.strip() for x in (s.satellite_sports or "").split(",") if x.strip()]
    if not sports:
        return
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        out = await satellite.run_satellite(
            pool, redis, sports=sports,
            cutoff_min=s.satellite_cutoff_min,
            lookahead_h=s.satellite_lookahead_h)
        logger.info("[scheduler] 위성 수집: %s", out)
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


def pregame_clock(start):
    """[SND-1] 잡 시작 시각 + 그 뒤 실제로 흐른 시간. 원본은 `pregame_push.Clock`.

    ⚠️ 여기 시각 계산을 적지 않는다 — 사본이 되면 한쪽만 고쳐진다.
    """
    from app.engine.pregame_push import Clock

    return Clock(start)


async def mlb_pregame_poll() -> None:
    """MLB 아침 창 — statsapi 라인업 + 캐시 발송. Go 크롤러 없음.

    KBO `crawler_lineup_poll`과 대칭. 사이트만 statsapi.mlb.com.
    """
    import time as _time

    from app.alerts import cycle_errors, cycle_report
    from app.collectors.lineups import STATUS_CONFIRMED, MLBLineupClient, refresh_mlb_lineup
    from app.engine.pregame_push import send_game_prediction, still_upcoming
    from app.pipeline import (analysis_cache_ready, ensure_analysis_cache,
                              rejudge_after_lineup)

    s = get_settings()
    pool = await get_pool()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    date = mlb_slate_date()
    now = datetime.now(UTC)
    # 🔴 [SND-1] MLB 창은 T-180 이라 이 결함의 **발현은 없었다**(실측 위반 0건).
    #    그래도 같은 구조이므로 같이 고친다 — 증상이 안 났다고 결함이 없는 것은
    #    아니다. 프리페치가 길어지면 MLB 도 같은 자리에 선다.
    clock = pregame_clock(now)
    # 🔴 [2026-09-07] 시각을 크론에 박는 대신 **오늘 실제 경기 시각**으로 연다.
    #    `asia_poll_window` 와 같은 규약 — 경기가 없으면 창이 자연히 닫힌다.
    open_, why = await mlb_poll_window(pool, now)
    if not open_:
        logger.debug("[mlb-pregame] 창 닫힘 — %s", why)
        await redis.aclose()
        return
    t0 = _time.monotonic()
    rep: list[str] = []
    errs: list[dict] = []
    tally = {"rejudged": 0, "sent": 0, "revised": 0, "failed": 0}
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
        # [정찰 C3] MLB 도 정찰한다. **레지스트리에 등록해 놓고 호출처가
        #   KBO·NPB 폴링뿐이면 MLB 는 등록만 되고 한 번도 안 돈다** —
        #   섀도 패널이 아시아 사이클에만 있어 MLB 가 조용히 감시 밖에 있던
        #   것과 같은 결함이다(2026-09-03). 정찰이 실패해도 폴링은 계속한다.
        try:
            from app.engine.scout import observe_slate

            await observe_slate(
                pool, redis,
                [{"sport": "mlb", "game_id": r["id"],
                  "starts_at": r["starts_at"]} for r in rows],
                date, now=now)
        except Exception as exc:
            logger.warning("[scout] mlb 정찰 실패 — 폴링은 계속한다: %s", exc)
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
        if updated:
            # 🔴 MLB 도 같은 구멍이었다. `rejudge_after_lineup` 이 캐시가 없으면
            #    `return False` 로 조용히 끝난다 — 04:30 프리페치가 한 번
            #    실패하면 그날 MLB 카드가 0장이다. 오늘은 프리페치가 성공해
            #    드러나지 않았을 뿐이다(실측 2026-09-01).
            raw = await redis.get(f"analysis:mlb:{date}")
            if not analysis_cache_ready(raw, date, "mlb"):
                if await ensure_analysis_cache(pool, redis, "mlb", date):
                    logger.info("[scheduler] mlb 캐시 구제 성공 — 재판정 계속")
                else:
                    errs.append({"what": "mlb 판정 캐시 없음",
                                 "detail": "슬레이트 파이프라인 구제 실패/이미 시도"})
        for game, res in updated:
            try:
                ok = await rejudge_after_lineup(game, res)
                if ok:
                    tally["rejudged"] += 1
                    sent = await send_game_prediction(redis, game, date,
                                                      now=clock.utc())
                    if sent in ("sent", "revised"):
                        tally[sent] += 1
                        logger.info("[scheduler] mlb 예측 카드 %s game=%s",
                                    sent, game["id"])
                else:
                    tally["failed"] += 1
                    errs.append({"what": f"mlb 재판정 무효 game={game['id']}",
                                 "detail": f"{game['away']}@{game['home']}"})
                if res["status"] == STATUS_CONFIRMED:
                    logger.info("[scheduler] MLB 라인업 확정 — 최종 픽 game=%s ok=%s",
                                game["id"], ok)
            except Exception as exc:
                tally["failed"] += 1
                errs.append({"what": f"mlb 재판정 실패 game={game['id']}",
                             "detail": str(exc)[:150], "exc": exc})
                logger.warning("[scheduler] MLB 라인업 재판정 실패 game=%s: %s",
                               game["id"], exc)
        for r in rows:
            if r["id"] in rejudged or not still_upcoming(r["starts_at"], now):
                continue
            try:
                sent = await send_game_prediction(redis, dict(r), date,
                                                  now=clock.utc())
                if sent in ("sent", "revised"):
                    logger.info("[scheduler] mlb 예측 카드 %s game=%s",
                                sent, r["id"])
            except Exception as exc:
                errs.append({"what": f"mlb 발송 실패 game={r['id']}",
                             "detail": str(exc)[:150], "exc": exc})
                logger.warning("[scheduler] mlb 발송 실패 game=%s: %s",
                               r["id"], exc)
        if updated:
            rep.append(f"  MLB 대상 {len(rows)}경기 · 라인업 변동 {len(updated)}")
        # [T-30 보장] 아시아와 **대칭**이다. 보장선은 종목을 가리지 않는다.
        await guarantee_first_cards(pool, redis, "mlb", date, rows, clock.utc(),
                                    tally, errs)
        # [감시 L2·L3] 아시아 사이클과 **대칭**이다. 여기가 비어 있어 MLB 만
        #   그림자 패널을 못 받고 있었다 (실측 2026-09-03).
        await _run_shadow_panel(redis, ("mlb",), date)
        await report_cycle(redis, "MLB 판정", rep, errs, tally,
                           _time.monotonic() - t0,
                           cycle_report, cycle_errors, next_run="5분 뒤")
    finally:
        await redis.aclose()


async def asia_poll_window(pool, now) -> tuple[bool, str]:
    """지금이 아시아 폴링 창인가. 반환 (열림, 사유).

    창 = [가장 이른 경기 − (KBO 발송창 + 20분), 가장 늦은 경기 시작]

    ⚠️ **새 상수를 만들지 않는다.** `SEND_OPEN_MIN["kbo"]`(70) + 20분 여유로
       잡는다 — 발송 창이 열리기 전에 크롤이 먼저 돌아야 카드가 나간다.
    ⚠️ 요일 분기를 넣지 않는다. 월요일(KBO 휴식일)이든 우천 순연이든
       **오늘 예정 경기가 없으면** 창이 자연히 닫힌다.
    ⚠️ 조회 실패도 닫힘이다 — 모르는 것을 폴링의 근거로 쓰지 않는다.
    """
    from app.engine.pregame_push import SEND_OPEN_MIN

    if pool is None:
        return False, "pool 없음"
    try:
        row = await pool.fetchrow(
            """SELECT min(starts_at) AS lo, max(starts_at) AS hi
                 FROM games
                WHERE sport = ANY($1::text[]) AND status = 'scheduled'
                  AND (starts_at AT TIME ZONE 'Asia/Seoul')::date
                      = (now() AT TIME ZONE 'Asia/Seoul')::date""",
            ["kbo", "npb"])
    except Exception as exc:
        logger.warning("[scheduler] 아시아 폴링 창 조회 실패 — 닫힘: %s", exc)
        return False, "조회 실패"
    if not row or row["lo"] is None:
        return False, "오늘 예정 경기 없음"
    lead = timedelta(minutes=SEND_OPEN_MIN["kbo"] + 20)
    if now < row["lo"] - lead:
        return False, f"창 이전 (첫 경기 {row['lo']:%H:%M}Z)"
    if now > row["hi"]:
        return False, f"창 이후 (막 경기 {row['hi']:%H:%M}Z)"
    return True, ""


async def mlb_poll_window(pool, now) -> tuple[bool, str]:
    """지금이 MLB 폴링 창인가. 반환 (열림, 사유).

    🔴 [2026-09-07] **종전에는 `CronTrigger(hour="5-11", …)` 였다.**
       KBO·NPB 가 `hour="17,18"` 로 시각을 박아 낮경기·순연을 통째로 놓쳤던
       것과 **같은 결함**이 MLB 에만 남아 있었다. 실측(최근 30일 337경기):
       01시 7 · 02시 40 · 03시 25 · 04시 9 = **81경기(24%)가 창 밖**이라
       발송 창이 열려도(T-180) 폴링이 자고 있어 카드가 나가지 못했다.
       `CLAUDE.md` 발송 규율의 "첫 카드 보장선 T-30"이 그 24%에는
       적용된 적이 없다.

    창 = [가장 이른 경기 − (MLB 발송창 + 20분), 가장 늦은 경기 시작]

    ⚠️ **새 상수를 만들지 않는다.** `SEND_OPEN_MIN["mlb"]`(180) + 20분 여유다
       — `asia_poll_window` 와 같은 규약이다.
    ⚠️ 날짜 기준은 **미국 동부**다(`CLAUDE.md` 규칙 5). KST 날짜로 자르면
       01~04시 KST 경기가 전날 슬레이트로 밀려 또 빠진다.
       `mlb_slate_date()` 가 원본이므로 규칙을 여기 다시 쓰지 않는다.
    ⚠️ 조회 실패도 닫힘이다 — 모르는 것을 폴링의 근거로 쓰지 않는다.
    """
    from datetime import date as _date

    from app.engine.pregame_push import SEND_OPEN_MIN

    if pool is None:
        return False, "pool 없음"
    try:
        row = await pool.fetchrow(
            """SELECT min(starts_at) AS lo, max(starts_at) AS hi
                 FROM games
                WHERE sport = 'mlb' AND status = 'scheduled'
                  AND (starts_at AT TIME ZONE 'America/New_York')::date = $1""",
            _date.fromisoformat(mlb_slate_date()))
    except Exception as exc:
        logger.warning("[scheduler] MLB 폴링 창 조회 실패 — 닫힘: %s", exc)
        return False, "조회 실패"
    if not row or row["lo"] is None:
        return False, "오늘 슬레이트 예정 경기 없음"
    lead = timedelta(minutes=SEND_OPEN_MIN["mlb"] + 20)
    if now < row["lo"] - lead:
        return False, f"창 이전 (첫 경기 {row['lo']:%H:%M}Z)"
    if now > row["hi"]:
        return False, f"창 이후 (막 경기 {row['hi']:%H:%M}Z)"
    return True, ""


async def report_cycle(redis, where: str, rep: list[str], errs: list[dict],
                       tally: dict, elapsed: float, cycle_report, cycle_errors,
                       *, next_run: str = "") -> None:
    """[1·2단계 2026-09-01] 한 사이클의 결과 리포트 + 이상 묶음.

    🔴 **일이 있었을 때만 보낸다.** 5분 폴링에 매번 보내면 하루 100건이 넘고,
       2026-08-27 의 "알림 7~8건 폭주로 정작 카드가 안 보인" 사고가 재발한다.
       판정·발송·오류가 하나도 없는 틱은 조용히 지나간다.

    ⚠️ 리포트 실패가 폴링을 죽이지 않는다 — 알림은 보조다.
    """
    moved = tally["rejudged"] + tally["sent"] + tally["revised"]
    if not moved and not errs:
        return
    lines = list(rep)
    lines.append(f"  ✅ 재판정 {tally['rejudged']}경기 · 발송 {tally['sent']} · "
                 f"수정 {tally['revised']}")
    if tally["failed"]:
        lines.append(f"  ⚠️ 실패 {tally['failed']}경기")
    try:
        lines += await _slate_extra_lines(redis)
    except Exception as exc:
        logger.debug("[scheduler] 리포트 부가 줄 실패: %s", exc)
    verdict = (f"발송 {tally['sent'] + tally['revised']}건"
               + (f" · 이상 {len(errs)}건" if errs else " · 이상 없음"))
    try:
        await cycle_report(where, lines, verdict, elapsed_sec=elapsed)
    except Exception as exc:
        logger.warning("[scheduler] 사이클 리포트 실패: %s", exc)
    if errs:
        try:
            await cycle_errors(where, errs, next_run=next_run)
        except Exception as exc:
            logger.warning("[scheduler] 이상 묶음 실패: %s", exc)


async def _slate_extra_lines(redis) -> list[str]:
    """오늘 판정 캐시에서 딥서치·표본부족 줄을 읽는다.

    새 기능들이 로그에만 남고 알림에는 한 줄도 없었다 (2026-09-01):
    딥서치 발동·표본 부족·배당 오염 차단·라인업 의도. 사용자가 코드를 열지
    않고도 무슨 일이 있었는지 알 수 있어야 한다.
    """
    import json as _json

    from app.pipeline import today_kst

    out: list[str] = []
    date = today_kst()
    for sport in ("kbo", "npb", "mlb"):
        key_date = mlb_slate_date() if sport == "mlb" else date
        raw = await redis.get(f"analysis:{sport}:{key_date}")
        if not raw:
            continue
        try:
            games = (_json.loads(raw) or {}).get("games") or []
        except (TypeError, ValueError):
            continue
        low = [g for g in games if g.get("starter_low_sample")]
        deep = [g for g in games if g.get("deepsearch_trigger")]
        done = [g for g in deep
                if (g.get("deepsearch_trigger") or {}).get("deepsearch")
                == "investigated"]
        if low:
            out.append(f"  ⚠️ {sport.upper()} 선발 표본 부족 {len(low)}경기 "
                       f"— 추천 자격 없음")
        if deep:
            searched = sum(int((g.get("deepsearch_trigger") or {}).get("searches") or 0)
                           for g in deep)
            out.append(f"  🔍 {sport.upper()} 딥서치 트리거 {len(deep)} · "
                       f"조사 {len(done)} · 검색 {searched}회")
    return out


async def crawler_lineup_poll(sports: tuple[str, ...] = ("npb", "kbo")) -> None:
    """[배선] KBO·NPB 라인업을 크롤러 스냅샷에서 확인하고, 새로 뜨면 재판정한다.

    NPB는 **창이 둘로 갈린다** (npb-window, 2026-09-01):
      `analysis_open` 풀 분석(크롤·리서치 재실행)   T-15 ← 불변
      `rejudge_open`  경량(캐시 폼 + 매치업만)       T-10 ← 신설
    공시가 T-30이라 T-15로 함께 닫으면 창이 15분뿐이고, 놓친 경기는 잠정으로
    남아 추천 게이트(`qualifies`)에서 통째로 탈락한다. 비용이 다른 두 경로를
    같은 선으로 닫을 이유가 없다.

    NPB는 시작 15분 전(18:00 → 17:45)까지 크롤·분석을 끝낸다. 그 시각 이후
    풀 분석은 하지 않는다. 타순이 바뀐 경기는 종목 안에서 병렬로 돌리고, 끝나는
    즉시 보낸다. 슬레이트 파이프라인은 평소 저녁에 돌리지 않지만, **판정 캐시가
    아예 없으면 하루 1회 구제 실행**한다(2026-09-01 — 프리페치 실패가 그날 종목
    전체의 침묵으로 이어지던 것을 막는다).
    ⚠️ MLB 경로(`refresh_mlb_lineup`)는 statsapi 전용이라 이 두 종목에 쓸 수 없다.
    ⚠️ 한 경기 실패가 나머지를 막지 않는다.
    """
    import time as _time

    import redis.asyncio as aioredis

    from app.alerts import cycle_errors, cycle_report
    from app.collectors import crawler_feed
    from app.engine.pregame_push import (
        NPB_REJUDGE_FINISH_MIN, lineup_confirmed, lineup_pending_card,
        minutes_until_start, rejudge_open, roster_signature,
        send_game_prediction, still_upcoming, void_analysis_games,
    )
    from app.pipeline import (
        analysis_cache_ready, ensure_analysis_cache, is_final_window,
        rejudge_after_lineup, today_kst,
    )

    s = get_settings()
    pool = await get_pool()
    now = datetime.now(UTC)
    # 🔴 [SND-1 2026-09-11] 이 잡은 재판정(LLM)을 품고 있어 **38분까지 걸린다**
    #    (실측 2026-09-10). 발송 검사는 잡 머리의 시각이 아니라 **호출 시점**을
    #    봐야 한다 — 그렇지 않으면 이미 시작한 경기에 카드가 나간다.
    clock = pregame_clock(now)
    # 🔴 5분마다 돌되 경기 시각으로 창을 연다. 빈 틱은 **로그 없이** 끝난다 —
    #    하루 288틱 중 대부분이 창 밖이라 로그를 남기면 그것이 소음이 된다.
    open_, why = await asia_poll_window(pool, now)
    if not open_:
        logger.debug("[scheduler] 아시아 폴링 창 밖 — %s", why)
        return
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    t0 = _time.monotonic()
    # [1·2단계 2026-09-01] 사이클 리포트 재료.
    #   🔴 저녁 판정 사이클에는 리포트가 아예 없었다 — `prefetch_report` 는
    #      프리페치 잡에서만 불린다. 그래서 KBO·NPB 저녁 슬레이트가 어떻게
    #      됐는지 알려면 Railway 로그를 직접 열어야 했다.
    #   ⚠️ **빈 틱에서는 보내지 않는다.** 5분 폴링에 매번 보내면 하루 100건이
    #      넘고, 2026-08-27 의 알림 폭주가 재발한다.
    rep: list[str] = []
    errs: list[dict] = []
    tally = {"rejudged": 0, "sent": 0, "revised": 0, "failed": 0}
    try:
        # NPB를 먼저 — 종료선을 KBO 슬레이트에 밀리지 않게.
        for sport in sports:
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
            # [정찰 C3] 이 틱의 슬레이트를 정찰한다. **새 잡을 만들지 않는다** —
            #   이미 도는 폴링에 얹는다. 읽기만 하고 판정·발송을 건드리지 않으며,
            #   실패해도 폴링을 막지 않는다(정찰이 발송을 멈추면 본말전도다).
            try:
                from app.engine.scout import observe_slate

                await observe_slate(
                    pool, redis,
                    [{"sport": sport, "game_id": r["id"],
                      "starts_at": r["starts_at"]} for r in rows],
                    date, now=now)
            except Exception as exc:
                logger.warning("[scout] %s 정찰 실패 — 폴링은 계속한다: %s",
                               sport, exc)
            jobs: list[tuple] = []
            catchup: list = []
            for r in rows:
                game = crawler_feed.snapshot_for_game(snap, dict(r))
                have = any((game.get(f"lineup_{sd}") or "").strip()
                           for sd in ("home", "away"))
                if not have:
                    # 🔴 **판정이 있으면 타순 전이라도 1차 카드를 보낸다.**
                    #    종전에는 여기서 `continue` 라 재판정도 발송도 없었다.
                    #    실측 2026-09-01 17:25: KBO 5경기 판정이 14:00 에 끝나
                    #    레저에 있는데도 카드가 한 장도 안 나갔다. 사용자는
                    #    "봇이 죽었나"와 "라인업이 안 떴다"를 구분할 수 없었다.
                    #
                    #    MLB 폴링(`mlb_pregame_poll`)은 이미 라인업과 무관하게
                    #    전 경기 발송을 시도한다 — KBO·NPB 만 예외였다.
                    #
                    #    ⚠️ 추천으로 오해될 위험은 없다: `pick_state` 가
                    #       "🕐 잠정 — 라인업 확정 전"으로 붙고, `qualifies()` 가
                    #       확정 라인업을 하드 요건으로 요구해 보드만으로 나간다.
                    #    ⚠️ 중복 발송도 없다: `send_game_prediction` 이 해시로
                    #       거르고, 타순이 뜨면 lineup_hash 가 바뀌어 수정 카드가
                    #       자동으로 나간다(2026-09-01 재발송 규칙).
                    catchup.append(dict(r))
                    continue
                # 🔴 [v1.3 A-1] **확정은 타순 9명 유무로 정한다.**
                #    종전 `is_final_window`(경기 N분 전인가)는 "언제 왔는가"를
                #    확정 여부로 읽었다. NPB 창 T-30인데 타순이 T-44에 오면
                #    `predicted` 로 굳고, 안 바뀌면 영영 확정이 못 된다 —
                #    2026-09-02 NPB 4경기가 그렇게 "미확정" 카드를 받았다.
                #    시각 규칙은 발송 창·종료선 용도로만 남는다.
                status = ("confirmed"
                          if lineup_confirmed(game.get("lineup_home"),
                                              game.get("lineup_away"))
                          else "predicted")
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
                    # [M-1 계측] 폴러의 전이. 카드가 (잠정)을 달면 이 로그와
                    #   대조해 DB·캐시·카드 셋 중 어디가 어긋났는지 본다.
                    logger.info("[lineup-status] game=%s %s→%s at=poller "
                                "9명=%s", r["id"], r["lineup_status"], status,
                                status == "confirmed")
                    if r["lineup_status"] == "confirmed" and status != "confirmed":
                        # 🔴 **역행**이다 — 확정이라고 해놓고 되돌아갔다.
                        from app.engine.monitor_metrics import (
                            note_lineup_regress,
                        )

                        await note_lineup_regress(redis, sport, date)
                    await pool.execute(
                        "UPDATE games SET lineup_status = $2, "
                        "home_pitcher = COALESCE($3, home_pitcher), "
                        "away_pitcher = COALESCE($4, away_pitcher), "
                        "updated_at = now() WHERE id = $1",
                        r["id"], status,
                        game.get("home_pitcher") or None,
                        game.get("away_pitcher") or None)
                if roster_changed and rejudge_open(sport, r["starts_at"], now):
                    jobs.append((dict(r), status, notes, roster, sig_key, game))
                else:
                    if roster_changed:
                        await redis.set(sig_key, roster, ex=86400)
                        from app.engine.pregame_push import REJUDGE_FINISH_MIN

                        cut = REJUDGE_FINISH_MIN.get(sport)
                        if cut is not None and still_upcoming(r["starts_at"], now):
                            logger.warning(
                                "[scheduler] %s T-%d 이후 라인업 변동 — 재판정 안 함 "
                                "game=%s", sport.upper(), cut, r["id"])
                    catchup.append(dict(r))

            async def _rejudge_and_send(item, *, _sport=sport, _date=date):
                row, status, notes, roster, sig_key, game = item
                raw = await redis.get(f"analysis:{_sport}:{_date}")
                if not analysis_cache_ready(raw, _date, _sport):
                    # 🔴 종전에는 여기서 그냥 `return` 이었다. 그래서 프리페치가
                    #    한 번 실패하면 그날 그 종목은 통째로 침묵했다.
                    #    실측 2026-09-01: "npb 캐시 없음 — 생략" × 6경기 → 카드 0장.
                    #    판정은 만들 수 있는 상태였는데 아무도 만들지 않았다.
                    #    ⚠️ 구제는 하루 1회다(ensure_analysis_cache 가 nx 가드).
                    made = await ensure_analysis_cache(pool, redis, _sport, _date)
                    if not made:
                        errs.append({
                            "what": f"{_sport} 판정 캐시 없음 game={row['id']}",
                            "detail": f"{row['away']}@{row['home']} — "
                                      f"슬레이트 파이프라인 구제 실패/이미 시도"})
                        logger.warning(
                            "[scheduler] %s 캐시 없음·구제 실패 — 생략 game=%s",
                            _sport, row["id"])
                        return
                    logger.info("[scheduler] %s 캐시 구제 성공 — 재판정 계속 game=%s",
                                _sport, row["id"])
                try:
                    ok = await rejudge_after_lineup(
                        row, {"status": status, "notes": notes,
                              "starters": {"home": game.get("home_pitcher") or None,
                                           "away": game.get("away_pitcher") or None},
                              "injuries": {}})
                    if ok:
                        tally["rejudged"] += 1
                        await redis.set(sig_key, roster, ex=86400)
                        sent = await send_game_prediction(redis, row, _date,
                                                          now=clock.utc())
                        if sent in ("sent", "revised"):
                            tally[sent] += 1
                            logger.info("[scheduler] %s 예측 카드 %s game=%s",
                                        _sport, sent, row["id"])
                    else:
                        tally["failed"] += 1
                        errs.append({
                            "what": f"{_sport} 재판정 무효 game={row['id']}",
                            "detail": f"{row['away']}@{row['home']} — 캐시 미판정/무효"})
                    logger.info("[scheduler] %s 라인업 %s — 재판정 game=%s ok=%s",
                                _sport, status, row["id"], ok)
                except Exception as exc:
                    tally["failed"] += 1
                    errs.append({"what": f"{_sport} 재판정 실패 game={row['id']}",
                                 "detail": str(exc)[:150], "exc": exc})
                    logger.warning("[scheduler] %s 재판정 실패 game=%s: %s",
                                   _sport, row["id"], exc)

            if jobs:
                await asyncio.gather(
                    *[_rejudge_and_send(item) for item in jobs],
                    return_exceptions=True)
            for row in catchup:
                try:
                    sent = await send_game_prediction(redis, row, date,
                                                      now=clock.utc())
                    if sent in ("sent", "revised"):
                        tally[sent] += 1
                        logger.info("[scheduler] %s 예측 카드 %s game=%s",
                                    sport, sent, row["id"])
                except Exception as exc:
                    errs.append({"what": f"{sport} 발송 실패 game={row['id']}",
                                 "detail": str(exc)[:150], "exc": exc})
                    logger.warning("[scheduler] %s 발송 실패 game=%s: %s",
                                   sport, row["id"], exc)
            # [T-30 보장] 창은 이미 열려 있다(KBO T-70 · NPB T-40). 그래도
            #   판정이 없어 못 나간 경기가 남을 수 있다 — 보장선에서 강제한다.
            await guarantee_first_cards(pool, redis, sport, date, rows,
                                        clock.utc(), tally, errs)
            # [npb-window] T-10에도 확정이 안 온 NPB 경기는 조용히 두지 않는다.
            if sport == "npb":
                await _npb_pending_notice(redis, rows, now)
            if rows:
                # 🔴 `if jobs:` 였다. 타순변동이 없으면 줄이 통째로 빠져,
                #    17:35 리포트가 "NPB 대상 6경기"만 적고 발송 5건(KBO)을
                #    그 아래 붙였다 — 종목이 뒤바뀌어 읽힌다(실측 2026-09-01).
                rep.append(f"  {sport.upper()} 대상 {len(rows)}경기 · "
                           f"타순변동 {len(jobs)} · 미변동 {len(catchup)}")
        # [감시 L2·L3] **발송이 끝난 뒤** 그림자 패널을 돌린다.
        #   T-차감 시간에 LLM 왕복을 넣지 않는다. 실패해도 이 사이클과 무관하다.
        await _run_shadow_panel(redis, sports, date)
        await report_cycle(redis, "아시아 판정", rep, errs, tally,
                           _time.monotonic() - t0,
                           cycle_report, cycle_errors, next_run="5분 뒤")
    finally:
        await redis.aclose()


async def guarantee_first_cards(pool, redis, sport: str, date: str, rows,
                               now, tally=None, errs=None) -> int:
    """🔴 [2026-09-03] **T-30 첫 카드 보장.**

    그 시점에 카드가 한 장도 안 나간 경기는, 라인업이 미공시여도 지금 있는
    재료로 판정해 내보낸다. 사용자 결정: "라인업을 기다리다 카드가 아예
    안 나가는" 것이 가장 나쁘다.

    ⚠️ **이미 발송된 경기는 건드리지 않는다** — 발송 이력 키로 먼저 거른다.
    ⚠️ 판정 설계·게이트·트리거를 바꾸지 않는다. 바뀌는 것은 **언제 보내는가**
       뿐이다. 잠정 기반이면 카드가 종전 규칙대로 `(잠정)` 을 단다 —
       새 표기를 발명하지 않는다.
    ⚠️ 확정 공시가 오면 종전 재판정 경로가 수정 카드를 보낸다. 이 함수는
       그 경로를 대체하지 않는다.
    """
    from app.engine.pregame_push import (
        Clock, already_sent, guarantee_due, send_game_prediction, still_upcoming,
    )
    from app.pipeline import (analysis_cache_ready, ensure_analysis_cache,
                              rejudge_after_lineup)

    # 🔴 [SND-1 2026-09-11] **인자로 받은 `now` 를 발송까지 들고 가지 않는다.**
    #    아래 `rejudge_after_lineup` 은 LLM 호출이라 분 단위로 걸린다 —
    #    실사고 2026-09-10: 38분 뒤 발송에 그 시각을 그대로 써서, 이미
    #    시작한 경기(18:30)에 19:06 에 1차 카드가 나갔다.
    #    ⚠️ 시그니처는 그대로다. 시각이 고정된 기존 테스트는 경과가 0 이라
    #       종전과 똑같이 동작한다.
    clock = Clock(now)
    n = 0
    for r in rows:
        row = dict(r)
        gid = row["id"]
        now = clock.utc()
        if not still_upcoming(row["starts_at"], now):
            continue
        if not guarantee_due(row["starts_at"], now):
            continue
        if await already_sent(redis, gid):
            continue
        try:
            sent = await send_game_prediction(redis, row, date, now=clock.utc())
            if sent in ("sent", "revised"):
                n += 1
                if tally is not None:
                    tally[sent] = tally.get(sent, 0) + 1
                logger.info("[guarantee] %s T-30 첫 카드 %s game=%s (기존 판정)",
                            sport, sent, gid)
                continue
            # 판정이 없어서 못 나간 경우에만 만들어 본다.
            logger.info("[guarantee] %s T-30 미발송 game=%s — 판정 강제 시도",
                        sport, gid)
            raw = await redis.get(f"analysis:{sport}:{date}")
            if not analysis_cache_ready(raw, date, sport):
                await ensure_analysis_cache(pool, redis, sport, date)
            await rejudge_after_lineup(
                row, {"status": row.get("lineup_status") or "none", "notes": [],
                      "starters": {"home": row.get("home_pitcher") or None,
                                   "away": row.get("away_pitcher") or None},
                      "injuries": {}})
            # 🔴 [SND-1] 강제 판정은 **몇 분이 걸린다.** 그 사이 경기가 시작했을
            #    수 있다 — 다시 묻는다. 실사고 2026-09-10 이 정확히 여기다.
            if not still_upcoming(row["starts_at"], clock.utc()):
                logger.warning("[guarantee] %s 강제 판정 중 경기가 시작했다 — "
                               "발송하지 않는다 game=%s", sport, gid)
                continue
            sent = await send_game_prediction(redis, row, date, now=clock.utc())
            if sent in ("sent", "revised"):
                n += 1
                if tally is not None:
                    tally[sent] = tally.get(sent, 0) + 1
                logger.info("[guarantee] %s T-30 첫 카드 %s game=%s (강제 판정)",
                            sport, sent, gid)
            else:
                logger.warning("[guarantee] 🔴 %s T-30 보장 실패 game=%s 결과=%s",
                               sport, gid, sent)
                if errs is not None:
                    errs.append({"what": f"{sport} T-30 첫 카드 보장 실패 game={gid}",
                                 "detail": f"{row['away']}@{row['home']} — {sent}"})
                # 🔴 [PGP-2 2026-09-08] **침묵 대신 사실을 보낸다.**
                #    여기가 "보내야 하는데 못 보냈다"가 확정되는 자리다 —
                #    그 앞은 아직 기다릴 수 있는 시간이다. 판정 불가 카드는
                #    2026-09-02 에 만들어졌지만 호출부가 죽은 함수 안에만 있어
                #    6일간 0장이었다(감사 PGP-2·SCH-1). 사용자는 "봇이 죽었나"와
                #    "오늘 픽이 없나"를 구분할 수 없었다.
                from app.engine.pregame_push import explain_missing

                if await explain_missing(redis, row, sport, now):
                    logger.warning("[guarantee] %s game=%s 판정 불가 카드 발송",
                                   sport, gid)
                    if tally is not None:
                        tally["unavailable"] = tally.get("unavailable", 0) + 1
        except Exception as exc:
            logger.warning("[guarantee] %s 보장 실패 game=%s: %s", sport, gid, exc)
            if errs is not None:
                errs.append({"what": f"{sport} T-30 보장 예외 game={gid}",
                             "detail": str(exc)[:150], "exc": exc})
    if n:
        logger.info("[guarantee] %s T-30 보장 발송 %d건", sport, n)
    return n


async def _run_shadow_panel(redis, sports, date) -> None:
    """[감시 L2·L3] 발송 후 그림자 패널. **예외를 밖으로 내보내지 않는다.**"""
    try:
        import json as _json

        from app.engine.shadow_panel import run_panel

        pool = await get_pool()
        for sport in sports:
            raw = await redis.get(f"analysis:{sport}:{date}")
            if not raw:
                continue
            games = (_json.loads(raw) or {}).get("games") or []
            res = await run_panel(pool, redis, games)
            if res.get("targets"):
                logger.info("[shadow] %s 대상 %d · 검사역 %d · 독립 %d · skip %d",
                            sport.upper(), res["targets"], res["reviewed"],
                            res["shadowed"], res["skipped"])
    except Exception as exc:
        logger.warning("[shadow] 패널 실행 생략 — 발송과 무관: %s", exc)


async def _npb_pending_notice(redis, rows, now) -> None:
    """T-10에도 확정이 안 온 NPB 경기 — **조용히 잠정으로 두지 않는다.**

    사용자 입장에서 "카드가 안 온 것"과 "라인업이 안 나온 것"은 다르다.
    말하지 않으면 봇이 죽은 줄 안다. 경기당 1회만 보낸다.
    """
    from app.engine.pregame_push import (
        NPB_REJUDGE_FINISH_MIN, lineup_pending_card, minutes_until_start,
        still_upcoming,
    )
    from app.notify import send_telegram

    for r in rows:
        if (r["lineup_status"] or "") == "confirmed":
            continue
        if not still_upcoming(r["starts_at"], now):
            continue
        left = minutes_until_start(r["starts_at"], now)
        if left is None or left > NPB_REJUDGE_FINISH_MIN:
            continue
        key = f"npb_pending_notice:{r['id']}"
        try:
            if await redis.get(key):
                continue
            await redis.set(key, "1", ex=6 * 3600)
        except Exception as exc:
            logger.warning("[scheduler] 관망 알림 중복키 실패 game=%s: %s",
                           r["id"], exc)
        try:
            await send_telegram(
                lineup_pending_card("npb", r["home"], r["away"], left))
            logger.info("[scheduler] NPB 라인업 미확정 관망 카드 game=%s left=%.0f분",
                        r["id"], left)
        except Exception as exc:
            logger.warning("[scheduler] 관망 카드 발송 실패 game=%s: %s",
                           r["id"], exc)


async def asia_pregame_kbo() -> None:
    """KBO 전용 5분 폴링."""
    await crawler_lineup_poll(("kbo",))


async def npb_pregame_2m() -> None:
    """NPB 전용 2분 폴링 — 공시(T-30)와 종료선(T-10) 사이가 좁다.

    5분 간격이면 T-30~T-10 20분 창에 최대 4회뿐이고, 공시 직후 한 틱을
    놓치면 그 경기는 잠정으로 끝난다.
    """
    await crawler_lineup_poll(("npb",))


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
    일정 upsert 창은 백필과 같은 APPEARANCE_DAYS — 3일만 넣으면 나머지
    경기는 no_game. 14일이면 오늘 선발 등판이 1회로 끊긴다.
    ⚠️ NPB는 6인 로테이션이라 28일이다(2026-09-01). 일정 upsert 창이
       백필 창보다 짧으면 그 앞 경기가 전부 no_game 이 된다 — 함께 늘어난다.
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


async def _free_odds_snapshot() -> None:
    """무료 3원 배당 수집. **유료 키를 한 번도 부르지 않는다.**

    MLB  ESPN → (실패 시) SharpAPI
    KBO·NPB  배트맨 스냅샷(Go 크롤러 적재)을 DB 로 옮긴다
    ⚠️ 한 리그 실패가 나머지를 막지 않는다.
    """
    from app.collectors.odds_free import (collect_asia, collect_mlb,
                                          collect_soccer, coverage)
    from app.pipeline import mlb_slate_date, today_kst

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    summary = []
    dates: list[str] = []
    try:
        try:
            # 🔴 날짜를 계산하지 않는다. **DB에 있는 다가올 경기**에서 읽는다 —
            #    계산한 슬레이트가 아직 적재 전이면 매칭이 0이 되고, 그것이
            #    소스 고장으로 오독된다 (실사고 2026-09-02 14:42).
            from app.collectors.odds_free import upcoming_mlb_dates

            dates = await upcoming_mlb_dates(pool)
            if not dates:
                summary.append("mlb=대상경기없음")
                logger.info("[odds] MLB — 36시간 내 예정 경기가 DB에 없다")
            for d in dates:
                r = await collect_mlb(pool, d)
                summary.append(
                    f"mlb[{d}]=" + ("대상없음" if r.get("no_games")
                                    else f"{r['rows']}행/{r['matched']}경기"
                                         f"({r['provider'] or '실패'})"))
        except Exception as exc:
            logger.warning("[odds] MLB 무료 수집 실패: %s", exc)
            summary.append("mlb=실패")
        for sport in ("kbo", "npb"):
            try:
                r = await collect_asia(pool, redis, sport, today_kst())
                summary.append(f"{sport}={r['rows']}행/{r['matched']}경기")
            except Exception as exc:
                logger.warning("[odds] %s 배트맨 수집 실패: %s", sport, exc)
                summary.append(f"{sport}=실패")
        # 🔴 [ODP-1 2026-09-13] 축구 1X2. 종전에는 축구 배당이 **0건**이었다
        #    (최근 14일 69경기) — oddsportal 리그 표에 축구가 없어서였다.
        #    ⚠️ 실패해도 야구 수집을 막지 않는다.
        try:
            r = await collect_soccer(pool, redis, today_kst())
            summary.append(f"soccer={r['rows']}행/{r['matched']}경기")
        except Exception as exc:
            logger.warning("[odds] 축구 수집 실패: %s", exc)
            summary.append("soccer=실패")
        # 🔴 [D1-6 사용자 지시] ESPN 축구(DraftKings)는 **게이트 대상만** 친다.
        #    대상이 없으면 요청 0이다. 실패해도 다른 수집을 막지 않는다.
        try:
            n_dk = await _espn_soccer_snapshot(pool, redis)
            if n_dk:
                summary.append(f"dk={n_dk}행")
        except Exception as exc:
            logger.warning("[odds] ESPN 축구 실패: %s", exc)
        # [검증 3] 리그별 커버리지를 매 스냅샷마다 남긴다 — 3일 집계의 재료다.
        # 커버리지도 **실제 대상 날짜**로 잰다. 대상이 없으면 재지 않는다 —
        # 분모가 0인 비율을 만들면 그게 곧 오탐이다.
        targets = [("mlb", d) for d in dates]
        targets += [("kbo", today_kst()), ("npb", today_kst())]
        for sport, d in targets:
            try:
                c = await coverage(pool, sport, d)
                if c["total"]:
                    logger.info("[odds-coverage] %s %s — 배당 확보 %d/%d (%.0f%%)",
                                sport.upper(), d, c["with_odds"], c["total"],
                                (c["rate"] or 0) * 100)
                    await redis.set(f"odds_coverage:{sport}:{d}",
                                    json.dumps(c), ex=48 * 3600)
            except Exception as exc:
                logger.debug("[odds-coverage] %s 실패: %s", sport, exc)
        logger.info("[odds] 무료 수집 완료 — %s", " · ".join(summary))
    finally:
        await redis.aclose()


#: [D1-6] 게이트 대상으로 보는 라벨. 🔴 문자열을 베끼지 않는다 — gate 상수다.
def _gate_target_labels() -> tuple[str, ...]:
    from app.engine.gate import DOUBT, OVER

    return (OVER, DOUBT)


async def _espn_soccer_snapshot(pool, redis) -> int:
    """[D1-6] 게이트 대상 축구 경기만 ESPN(DraftKings) 배당을 받는다.

    🔴 대상 선정은 **원장(gate_reason)과 더비표**에서 읽는다 — 새 기준을
       만들지 않는다. 대상이 없으면 요청 0.
    ⚠️ 예산: 경기당 최대 10요청(`espn_odds.SOCCER_MAX_REQ_PER_GAME`).
    """
    from datetime import UTC, datetime

    from app.collectors import espn_odds as E
    from app.collectors.odds_free import store_rows
    from app.engine.bigmatch import is_big_match
    from app.leagues import league_labels

    rows = await pool.fetch(
        """SELECT g.id, g.league, g.home, g.away, l.gate_reason
             FROM games g
             LEFT JOIN pick_ledger l ON l.game_id = g.id AND l.is_final
            WHERE g.sport = 'soccer' AND g.status = 'scheduled'
              AND g.starts_at BETWEEN now() - interval '1 hour'
                                  AND now() + interval '30 hours'""")
    labels = _gate_target_labels()
    keys = league_labels()
    want: dict[str, set] = {}
    gid_by: dict[str, list] = {}
    for r in rows:
        lk = keys.get(r["league"] or "")
        if not lk or lk not in E.SOCCER_LEAGUES:
            continue
        reason = r["gate_reason"] or ""
        big = is_big_match(league=lk, home=r["home"] or "", away=r["away"] or "")
        if not (any(reason.startswith(x) for x in labels) or big.big):
            continue
        want.setdefault(lk, set()).add(r["home"] or "")
        gid_by.setdefault(lk, []).append(r)
    if not want:
        logger.info("[espn_odds] 축구 — 게이트 대상 0(요청 0)")
        return 0
    date = datetime.now(UTC).strftime("%Y%m%d")
    total = 0
    for lk, names in want.items():
        got = await E.fetch_soccer(lk, date, only_names=names, redis=redis)
        for name, odd_rows in got.items():
            g = next((x for x in gid_by[lk]
                      if E._hit(name, x["home"] or "")), None)
            if g is None:
                continue
            total += await store_rows(pool, g["id"], odd_rows, "espn")
    logger.info("[espn_odds] 축구 — 대상 %d경기 · 적재 %d행",
                sum(len(v) for v in want.values()), total)
    return total


async def oddsapinet_job() -> None:
    """[ODN-1 2026-09-17] KBO·NPB **총점·핸디·팀토탈** — 하루 2회.

    🔴 **기존 `odds_snapshot_30m` 을 건드리지 않는다.** 그쪽은 ESPN·oddsportal
       무료·무제한이고 거기서 CLV(판정시각·마감)와 라인 이동 스냅샷이 나온다.
       늦추면 그게 깨진다. 이 잡만 따로 돈다.
    🔴 **예산이 먼저다.** 월 1,000 크레딧(sandbox)이라 80% 를 넘으면 멈춘다.
       기존 30분 주기로 붙였으면 월 11,520콜이 필요해 이틀이면 끝났다.
    ⚠️ 키가 없으면 조용히 비활성이다(절대 규칙 3).
    """
    from app.collectors import oddsapinet as ON
    from app.collectors.odds_free import store_rows

    if not ON._key():
        logger.info("[oddsapinet] 키 없음 — 비활성")
        return
    if not await ON.budget_ok():
        return
    pool = await get_pool()
    total = games = 0
    # 🔴 [ODN-2] `LEAGUES` 가 아니라 `JOB_LEAGUES` 다. 파서가 읽을 수 있는
    #    리그와 **정기로 긁는 리그**는 다르다 — 섞으면 MLB 를 파서에 추가하는
    #    순간 월 크레딧이 터진다(실측: MLB 27경기 × 2회 = 월 1,620콜).
    for sport in ON.JOB_LEAGUES:
        evs = await ON.fetch_events(sport)
        if not evs:
            logger.info("[oddsapinet] %s 대상 경기 0", sport)
            continue
        ids = await _match_oddsapinet(pool, sport, evs)
        for ev, gid in ids:
            rows = ON.to_rows(await ON.fetch_odds(ev["event_id"]),
                              home=ev.get("home_team") or "",
                              away=ev.get("away_team") or "")
            if rows:
                total += await store_rows(pool, gid, rows, ON.PROVIDER)
                games += 1
    logger.info("[oddsapinet] KBO·NPB — 경기 %d · 적재 %d행", games, total)


async def _match_oddsapinet(pool, sport: str, evs: list) -> list:
    """API 경기 → 우리 game_id. 🔴 못 맞추면 **버린다**(억지로 붙이지 않는다).

    🔴 [ODN-M 2026-09-23] **팀 이름을 실제로 본다.** 종전 질의에는 팀 조건이
       없었고 `fetchrow` 가 창 안의 **아무 행이나** 돌려줬다. KBO 5경기가 전부
       18:30 시작이라 실측에서 셋이 전부 한 id 로 갔다:
```
kbo: 이벤트 3 → 매칭 3
  NC Dinos@KT Wiz · Kia Tigers@Doosan Bears · Lotte Giants@Hanwha Eagles
  → 전부 game_id=1774      (kbo 1경기에 7,720행이 겹쳐 쌓였다)
npb: 4경기 → 16962 · 2경기 → 16963
```
       다른 경기의 총점·핸디가 한 행에 섞이면 ⑪이 **남의 가격**으로 픽을 낸다.
       바로 위 독스트링은 이미 "시작 시각(±3시간) + 팀 이름 부분일치"라고
       적고 있었다 — 문서가 맞고 구현이 없었다.

    🔴 **대조표를 새로 만들지 않는다.** `football.match_team_name`(토큰 교집합
       최대 · 동점이면 None)이 원본이다.
    ⚠️ `similar_team` 단독은 쓰지 않는다 — `similar_team("Kia Tigers",
       "Hanshin Tigers")` 가 **True** 다(둘 다 Tigers). 홈·원정이 **같은 행에서
       둘 다** 맞을 때만 인정한다.
    ⚠️ 한 `game_id` 는 한 번만 쓴다 — 두 이벤트가 같은 경기에 붙으면 그것이
       바로 위 오염이다.
    """
    from datetime import datetime, timezone

    from app.collectors.football import match_team_name

    out: list = []
    used: set = set()
    cache: dict = {}
    for ev in evs:
        ts = ev.get("start_time")
        if not ts:
            continue
        when = datetime.fromtimestamp(int(ts), timezone.utc)
        key = int(ts)
        if key not in cache:
            # ⚠️ `$2` 에 **명시 캐스트**를 준다. 없으면 asyncpg 가 타입을
            #    추론하지 못해 `operator does not exist: timestamptz >= interval`
            #    로 터진다(⑨ 첫 사이클이 잡았다).
            cache[key] = [dict(r) for r in await pool.fetch(
                """SELECT id, home, away FROM games
                    WHERE sport = $1
                      AND starts_at BETWEEN $2::timestamptz - interval '3 hours'
                                        AND $2::timestamptz + interval '3 hours'""",
                sport, when)]
        rows = [r for r in cache[key] if r["id"] not in used]
        e_home = str(ev.get("home_team") or "")
        e_away = str(ev.get("away_team") or "")
        hit = None
        for r in rows:
            h = match_team_name(e_home, [str(r["home"])])
            a = match_team_name(e_away, [str(r["away"])])
            if h and a:
                hit = r
                break
        if hit is None:
            logger.info("[oddsapinet] 못 맞춤 %s @ %s (%s) — 창 안 %d경기",
                        e_away, e_home, when, len(rows))
            continue
        used.add(hit["id"])
        out.append((ev, hit["id"]))
    return out


async def odds_snapshot_job() -> None:
    """배당 스냅샷 — 크레딧 예산 관리:

    경기가 있는 리그만 조회. 킥오프 3시간 전부터는 30분 간격(매 실행),
    그 외 시간대는 리그당 3시간 간격. 사용량·잔여량은 snapshot 시 로그·Redis 기록.
    """
    import redis.asyncio as aioredis

    from app.api_guard import is_blocked, is_disabled
    from app.collectors.odds import SPORT_KEYS
    from app.leagues import LEAGUES

    # [무과금 전환 2026-09-02] 기본은 무료 3원 체계다. The Odds API 경로는
    #   **지우지 않았다** — `ODDS_PROVIDER=theodds` 로 되돌아간다.
    if (get_settings().odds_provider or "free").lower() != "theodds":
        return await _free_odds_snapshot()
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
        # 🔴 [ACL-1] odds_key 가 None 인 리그(acl)는 이 경로를 타지 않는다 —
        #    배당은 오즈포털에서 온다.
        label_to_key = {c["label"]: c["odds_key"] for c in LEAGUES.values()
                        if c.get("odds_key")}
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


async def ingest_fotmob_finals(pool=None, *, upsert=None, now=None) -> dict:
    """[W3-1] FotMob 이 주 소스인 리그의 **끝난 경기**를 적재한다.

    🔴 `upsert_slate` 은 FMR-1 이후 점수·상태를 함께 쓴다. 없던 것은
       **끝난 뒤 부르는 사람**이다 — 종전에는 일정 프리페치에서만 불렸고
       (`pipeline.py:1457`) 그때는 경기가 안 끝나 점수가 없었다.
       실측 2026-09-21: J1 0/11 · K리그1 0/14 · ACL 0/10 · 덴마크 0/8.

    🔴 **날짜는 UTC 다.** FotMob 은 경기를 UTC 날짜로 색인한다(W2 실측:
       US Lecce@AC Milan 이 UTC 09-20 · KST 09-21 이고 20260920 에만 있다).
       KST 로 받으면 유럽·심야 경기가 통째로 빠진다.

    ⚠️ **어제와 오늘 두 날**을 받는다(지시문 W3-3). 오늘만 받으면 자정을
       넘겨 끝난 경기가 영영 안 들어온다.
    ⚠️ 한 리그가 터져도 나머지는 돈다 — 실패는 **조용히 삼키지 않고**
       반환값 `failed` 와 로그에 남긴다.
    """
    from datetime import timedelta, timezone

    from app.leagues import LEAGUES

    if upsert is None:
        from app.collectors.fotmob import upsert_slate as upsert

    now = now or datetime.now(timezone.utc)
    days = [(now - timedelta(days=1)).strftime("%Y%m%d"), now.strftime("%Y%m%d")]
    keys = [k for k, cfg in LEAGUES.items() if cfg.get("result_source") == "fotmob"]
    out: dict = {"days": days, "leagues": keys, "saved": 0, "matched": 0,
                 "failed": [], "conflict": [], "needs_90": []}
    for key in keys:
        for day in days:
            try:
                r = await upsert(pool, day, league_key=key) or {}
            except Exception as exc:
                out["failed"].append({"league": key, "day": day,
                                      "error": f"{type(exc).__name__}: {exc}"[:200]})
                logger.warning("[finals] FotMob 적재 실패 %s %s: %s", key, day, exc)
                continue
            out["saved"] += int(r.get("saved") or 0)
            out["matched"] += int(r.get("matched") or 0)
            out["conflict"] += list(r.get("conflict") or [])
            out["needs_90"] += list(r.get("needs_90") or [])
    logger.info("[finals] FotMob 결과 적재 — 리그 %d · 날짜 %s · 매칭 %d · 저장 %d"
                " · 실패 %d · 충돌 %d · 90분확인 %d",
                len(keys), days, out["matched"], out["saved"],
                len(out["failed"]), len(out["conflict"]), len(out["needs_90"]))
    return out


async def ingest_kbo_finals(pool=None, *, upsert=None, now=None) -> dict:
    """[RES-1] 어제·오늘 KBO 결과를 네이버 일정 API 에서 적재한다.

    🔴 **어제와 오늘 둘 다** 본다 — 경기는 KST 저녁에 끝나고 이 잡은 새벽에
       도는데, 늦게 끝난 경기나 서스펜디드가 다음 날 확정되기도 한다.
    ⚠️ 날짜는 KST 기준이다(절대 규칙 5: KBO 표기는 KST).
    """
    from app.collectors.naver_kbo import upsert_probables, upsert_results

    fn = upsert or upsert_results
    pool = pool or await get_pool()
    base = (now or datetime.now(KST)).date()
    out = {"days": 0, "applied": 0, "seen": 0, "failed": 0}
    # 🔴 [SP-1 2026-09-23] **예고선발·구장도 여기서 옮긴다.** 네이버 preview 가
    #    이미 주는데(실측: 잭로그·박준영·로건) `games.home_pitcher` 가 예정
    #    26경기 전건 비어 있었고, ⑤의 `starter_recent3` 가 그 칸을 읽는다.
    #    ⚠️ 새 잡을 만들지 않는다 — 같은 네이버 소스를 두 잡이 치면 주기가
    #       두 벌이 되고 한쪽만 도는 날이 생긴다.
    #    ⚠️ **오늘·내일**을 본다(결과는 어제·오늘). 예고선발은 앞을 본다.
    #    ⚠️ 실패해도 결과 적재를 막지 않는다.
    redis_p = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        from app.collectors.naver_kbo import refresh as _nk_refresh

        for ahead in (0, 1):
            d = (base + timedelta(days=ahead)).strftime("%Y-%m-%d")
            try:
                await _nk_refresh(redis_p, d)
                got = await upsert_probables(pool, d, redis=redis_p)
                logger.info("[scheduler] KBO 예고선발 %s: %s", d, got)
            except Exception as exc:
                logger.warning("[scheduler] KBO 예고선발 %s 실패: %s", d, exc)
    finally:
        try:
            await redis_p.aclose()
        except Exception:
            pass
    for delta in (1, 0):
        d = (base - timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            r = await fn(pool, d)
        except Exception as exc:
            out["failed"] += 1
            logger.warning("[scheduler] KBO 결과 %s 실패 — 다음 날짜 계속: %s",
                           d, exc)
            continue
        out["days"] += 1
        out["applied"] += int(r.get("applied") or 0)
        out["seen"] += int(r.get("seen") or 0)
    logger.info("[scheduler] KBO 결과 적재: %s", out)
    return out


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
            # 🔴 축구는 **오늘 KST 날짜도** 훑는다. 유럽 킥오프는 KST 새벽이라
            #    오늘 01:30~05:00에 끝난 경기가 "어제"에 잡히지 않는다.
            #    실측 2026-08-31: KST 09/01 새벽 7경기가 yesterday(8/31)
            #    조회에서 통째로 빠졌다.
            if sport == "soccer":
                done["soccer_today"] = await ingest_finals(pool, today_kst(), sport)
        except (ApiQuotaError, ApiAuthError) as exc:
            logger.error("[scheduler] finals %s halted (%s): %s",
                         sport, type(exc).__name__, exc)
            await notify_api_error(exc)
        except Exception as exc:
            logger.exception("[scheduler] finals %s 실패 — 다음 종목 계속: %s", sport, exc)
    # 🔴 [W3-1 2026-09-21] **FotMob 이 주 소스인 리그.** football-data 무료로는
    #    J·K·ACL·덴마크 결과를 받을 수 없다(실측: 전건 ApiAuthError).
    #    ⚠️ 채점보다 **먼저** 돈다 — 결과가 들어와야 그 아래 `grade_pending`
    #       이 닫을 것이 생긴다.
    try:
        done["fotmob"] = await ingest_fotmob_finals(pool)
    except Exception as exc:
        logger.exception("[scheduler] FotMob 결과 적재 실패 — 채점은 계속: %s", exc)

    # 🔴 [RES-1 2026-09-21] **KBO 결과의 새 소스.** 종전 소스
    #    (`koreabaseball.com` 일정 페이지)는 robots 거부로 꺼졌다(D33) —
    #    그대로 두면 오늘 이후 KBO 결과가 안 들어오고 채점이 멈춘다.
    #    ⚠️ `grade_pending` **앞**에 둔다: 결과가 들어와야 채점할 것이 생긴다.
    try:
        done["kbo_naver"] = await ingest_kbo_finals(pool)
    except Exception as exc:
        logger.exception("[scheduler] KBO 결과 적재 실패 — 채점은 계속: %s", exc)

    # [v1.1 0단계] 결과가 들어왔으니 미채점 픽을 채점한다.
    #   ⚠️ 채점은 **측정 전용**이다 — 판정 경로는 이 표를 읽지 않는다.
    #   적재 실패와 무관하게 돌린다: 어제 못 채점한 행이 남아 있을 수 있다.
    try:
        from app.engine.pick_ledger import grade_pending

        graded = await grade_pending(pool)
        logger.info("[scheduler] 픽 레저 채점 %d건 · void %d건",
                    graded["graded"], graded["void"])
    except Exception as exc:
        logger.exception("[scheduler] 픽 레저 채점 실패 — 적재는 성공: %s", exc)
    # 🔴 [LED-1 2026-09-23] **결정 원장도 채점한다.** 실측: decision_ledger
    #    1,118행 중 `flow_v14` 740행이 채점 0 이었다 — 흐름 판정이 맞았는지
    #    셀 방법이 없었고, 그러면 ⑦ 조정도 ⑨ 확신도 고칠 근거가 없다.
    #    ⚠️ 새 잡을 만들지 않는다 — 결과가 들어온 **바로 이 자리**가 맞다.
    #    ⚠️ 구경로 채점(`pick_ledger`)을 대체하지 않는다. 둘은 다른 표다.
    try:
        from app.learning.decisions import grade_pending as _grade_dl

        _dl = await _grade_dl(pool)
        logger.info("[scheduler] 결정 원장 채점: %s", _dl)
        # 🔴 [CLV-F 2026-09-23] **결과를 기다리지 않는 채점.** 실측: 원장
        #    23경기 중 종료는 2건인데 종가 스냅샷은 17건이다. CLV 는 결과보다
        #    빠른 신호다(딥서치 → FORKS F-20).
        from app.learning.decisions import fill_clv as _fill_clv

        logger.info("[scheduler] 결정 원장 CLV: %s", await _fill_clv(pool))
    except Exception as exc:
        logger.exception("[scheduler] 결정 원장 채점 실패: %s", exc)
    logger.info("[scheduler] 종료 점수 적재: %s", sorted(done))
    return done


async def calibration_report_job() -> None:
    """[v1.1 0단계] 주간 캘리브레이션 요약을 관리자에게 보낸다.

    일요일 밤(경기 종료 후). 표본이 얇으면 표본 부족이라고 말하고 끝낸다 —
    얇은 표본으로 임계값을 흔드는 것이 이 프로젝트에서 가장 비싼 실수다.
    """
    from app.engine.calibration import summarize, render_report

    pool = await get_pool()
    try:
        rows = await summarize(pool, days=7)
        text = render_report(rows, days=7)
    except Exception as exc:
        logger.exception("[scheduler] 캘리브레이션 집계 실패: %s", exc)
        return
    from app.notify import send_telegram

    await send_telegram(text)
    logger.info("[scheduler] 주간 캘리브레이션 리포트 발송")


# ⚠️ 아래는 **1회성 코드다.** Redis에 남아 있던 판정을 레저로 옮겨 담기 위한
#    것이고, 백필 완료를 로그로 확인한 뒤에는 다음 배포에서 이 함수와
#    main()의 create_task 호출을 통째로 지워도 된다.
#    남겨 두어도 해롭지 않다 — 처리한 키는 건너뛰고, 건너뛰지 못해도
#    record_analysis가 같은 판정에 이력 행을 만들지 않는다.
BACKFILL_SINCE = "2026-08-29"


async def startup_backfill_job() -> None:
    """기동 직후 1회, 백그라운드로 레저 소급 백필 + 즉시 채점.

    레저가 0건으로 시작하면 캘리브레이션이 한 주를 통째로 기다린다.
    Redis에 남아 있는 판정은 이미 사실이므로 옮겨 담는다.

    ⚠️ 실패해도 스케줄러는 계속 돈다 — 백필은 편의지 운영 요건이 아니다.
    """
    import redis.asyncio as aioredis

    from app.engine.pick_ledger import backfill_from_redis, grade_pending

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        stats = await backfill_from_redis(pool, redis, BACKFILL_SINCE)
        graded = await grade_pending(pool)
        logger.info(
            "[scheduler] 레저 백필(%s 이후) — 슬레이트 %d · 신규 %d · 재판정 %d "
            "· 변화없음 %d · 기처리 %d · 건너뜀 %d / 즉시 채점 %d · void %d",
            BACKFILL_SINCE, stats["slates"], stats["inserted"], stats["rejudged"],
            stats["unchanged"], stats["seen"], stats["skipped"],
            graded["graded"], graded["void"])
        # [1회성 관측] 운영 DB를 직접 조회할 수 없어, 현재 레저 내용을 로그로
        #   한 번 드러낸다. 오늘 채점된 행이 무엇인지 눈으로 확인하기 위한 것이고,
        #   확인이 끝나면 다음 배포에서 이 블록을 지운다.
        try:
            rows = await pool.fetch(
                "SELECT game_id, sport, date, p_home, favored, confidence,"
                "       gate_result, is_final, merged_from, winner, final_score,"
                "       hit, void, graded_at"
                "  FROM pick_ledger ORDER BY id DESC LIMIT 20")
            logger.info("[ledger-snapshot] 총 %d행(최근 20)", len(rows))
            for r in rows:
                logger.info("[ledger-snapshot] %s", json.dumps(
                    {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                     for k, v in dict(r).items()}, ensure_ascii=False))
        except Exception as exc:
            logger.warning("[ledger-snapshot] 조회 실패: %s", exc)
        # [1회성 관측] v1.1 1단계 묶음 — NPB pitcher_appearances 운영 실적 확인.
        #   로컬에는 801행(선발 192)이 있으나 운영은 조회 경로가 없어 미확인이었다.
        #   05:25 npb_lineup_history 잡 로그로도 확인되지만, 그 잡이 도는 것을
        #   기다리지 않고 지금 사실을 드러낸다. 확인 후 이 블록도 함께 지운다.
        try:
            rows = await pool.fetch(
                "SELECT sport, count(*) AS rows,"
                "       count(*) FILTER (WHERE is_starter) AS starters,"
                "       max((SELECT max(g.starts_at) FROM games g"
                "            WHERE g.id = a.game_id)) AS latest"
                "  FROM pitcher_appearances a GROUP BY sport ORDER BY sport")
            for r in rows:
                logger.info("[appearances] %s 총 %s행 · 선발 %s · 최신 %s",
                            r["sport"], r["rows"], r["starters"], r["latest"])
            if not rows:
                logger.warning("[appearances] 🔴 pitcher_appearances 가 비어 있다")
        except Exception as exc:
            logger.warning("[appearances] 조회 실패: %s", exc)
        # [운영 안정화 3c·4] 기동 시 1회 소급 진단 — 운영 Redis·DB 는 밖에서
        #   못 읽는다. "며칠째 배당이 죽어 있었나", "타순이 몇 건 오염됐나"는
        #   서버가 스스로 말해야 한다.
        await _repair_impossible_live(pool)
        # [리허설 · MLB] `REHEARSAL_MLB=1` 일 때 기동 시 1회. 격리·읽기 전용.
        # [리허설 · KBO] 저녁 슬레이트 **사전 예측**. `REHEARSAL_KBO=1` 일 때만.
        #   ⚠️ 17:00 이후에는 스스로 멈춘다 — 실슬레이트가 정본이다.
        # [수동 프리페치] `RUN_PREFETCH_ASIA=1` 일 때 기동 후 1회.
        #   ⚠️ 14:00 cron 은 **이미 실행됐다**(크레딧 부족으로 실패). 실행
        #      기록이 있으니 `_catchup_missed_crons` 가 다시 돌리지 않는다 —
        #      "돌았지만 실패한 것"과 "안 돈 것"은 다르고, 따라잡기는 후자만
        #      본다. 그래서 명시적 훅이 필요하다.
        #   ⚠️ 백그라운드로 띄운다 — 몇 분 걸리는 작업이 기동을 막으면
        #      17시대 폴링을 놓친다.
        if os.getenv("RUN_PREFETCH_ASIA") == "1":
            async def _manual_prefetch() -> None:
                try:
                    logger.warning("[manual] 🔁 아시아 프리페치 수동 실행 시작")
                    await prefetch_asia_job()
                    logger.warning("[manual] ✅ 아시아 프리페치 수동 실행 완료")
                except Exception as exc:
                    logger.error("[manual] 프리페치 실패: %r", exc)

            asyncio.create_task(_manual_prefetch())
        # [오디션] 무료 LLM 판정 후보 실측. `LLM_AUDITION=1` 일 때만.
        #   ⚠️ Anthropic 0콜 — 프롬프트는 순수 함수로 렌더한다.
        if os.getenv("LLM_AUDITION") == "1":
            try:
                from tools.llm_audition import run as _audition

                await _audition(pool, redis)
            except Exception as exc:
                logger.error("[audition] 실행 실패: %r", exc)
        if os.getenv("REHEARSAL_KBO") == "1":
            try:
                from tools.rehearsal_kbo import run as _reh_kbo

                await _reh_kbo(pool, redis)
            except Exception as exc:
                logger.error("[reh-kbo] 실행 실패: %r", exc)
        if os.getenv("REHEARSAL_MLB") == "1":
            try:
                from tools.rehearsal_mlb import run as _reh_mlb

                await _reh_mlb(pool, redis)
            except Exception as exc:
                logger.error("[reh-mlb] 실행 실패: %r", exc)

        await _startup_forensics(pool, redis)
        # [리허설] `REHEARSAL=1` 일 때 기동 시 1회. 격리 키·발송 차단.
        if os.getenv("REHEARSAL") == "1":
            try:
                from tools.rehearsal import run as _rehearse

                await _rehearse(pool, redis)
            except Exception as exc:
                logger.error("[rehearsal] 실행 실패: %r", exc)
        # [전 리그 프로브] `PROBE_LEAGUE=1` 일 때 기동 시 1회.
        #   ⚠️ 읽기 전용이다 — 카드·판정·캐시·ledger 를 건드리지 않는다.
        if os.getenv("PROBE_LEAGUE") == "1":
            try:
                from tools.probe_league import run as _probe_league

                await _probe_league(redis)
            except Exception as exc:
                logger.error("[probe] 전 리그 프로브 실패: %r", exc)
        # [0a] 오염 타순 소급 교정. **서버가 한다** — 운영 DB 는 내부
        #   호스트명이라 `railway run` 으로도 밖에서 못 닿는다.
        #   멱등하다: 고쳐진 행은 길이 9가 되어 다음부터 선택되지 않는다.
        await _repair_lineups_once(pool, redis)
    except Exception as exc:
        logger.exception("[scheduler] 레저 백필 실패 — 운영은 계속: %s", exc)
    finally:
        await redis.aclose()


#: 오염 교정 1회 실행 표시. 배포마다 다시 돌 필요는 없다.
_REPAIR_KEY = "lineups:repaired:v1"


async def _repair_lineups_once(pool, redis) -> None:
    """하이픈으로 갈린 타순을 재파싱해 교정하고, 안 되면 오염으로 표시한다.

    ⚠️ **명단 사전이 비면 하지 않는다.** 사전 없이 재결합하면 추측이 된다.
    ⚠️ 읽기 실패·조회 실패는 조용히 넘긴다 — 기동을 막지 않는다.
    """
    try:
        if await redis.get(_REPAIR_KEY):
            return
    except Exception as exc:
        logger.debug("[repair] 실행 표시 조회 실패(계속): %s", exc)
    try:
        from app.collectors.starter_season import _roster
        from app.engine.lineup_diff import NAME_REGISTRY
        from tools.repair_lineups import TABLES, _as_list, repair_order

        await _roster(datetime.now(UTC).year, redis)
        if not NAME_REGISTRY:
            logger.warning("[repair] 실명 사전이 비었다 — 교정 보류(추측 금지)")
            return
        fixed = marked = 0
        for table, _ts in TABLES:
            rows = await pool.fetch(
                f"""SELECT id, batting_order FROM {table}
                     WHERE batting_order IS NOT NULL
                       AND jsonb_typeof(batting_order) = 'array'
                       AND jsonb_array_length(batting_order) <> 9""")
            for r in rows:
                new = repair_order(_as_list(r["batting_order"]), NAME_REGISTRY)
                if new is not None:
                    await pool.execute(
                        f"UPDATE {table} SET batting_order = $1::jsonb,"
                        f"       contaminated = FALSE WHERE id = $2",
                        json.dumps(new, ensure_ascii=False), r["id"])
                    fixed += 1
                else:
                    await pool.execute(
                        f"UPDATE {table} SET contaminated = TRUE WHERE id = $1",
                        r["id"])
                    marked += 1
        logger.error("[repair] 🔧 오염 타순 정리 — 교정 %d건 · 오염표시 %d건 "
                     "(표시된 행은 라인업 의도·T5 에서 제외된다)", fixed, marked)
        await redis.set(_REPAIR_KEY, f"{fixed}/{marked}", ex=90 * 86400)
    except Exception as exc:
        logger.warning("[repair] 오염 교정 실패 — 운영은 계속: %s", exc)


async def _catchup_missed_crons(redis) -> list[str]:
    """🔴 [2026-09-04] **재기동이 오늘치 cron 발화를 삼킨다.**

    APScheduler 는 in-memory jobstore 라 재기동하면 잡을 새로 단다. cron 잡의
    오늘 발화 시각이 이미 지났으면 **그 하루는 통째로 건너뛴다** — 다음 발화는
    내일이다. `misfire_grace_time` 은 살아 있던 프로세스가 늦게 도는 것을
    구제할 뿐, 죽어 있던 시간은 구제하지 못한다.

      실사고 2026-09-03: 14:00 `prefetch_asia` 가 14:03 배포로 사라졌다.
      그래서 KBO·NPB 분석 캐시가 없었고, 저녁에 구제 파이프라인이 대신
      돌아야 했다(NPB 17:26, KBO 18:05). KBO 는 그 과정에서 카드가
      T-30 을 넘겼다.

    기동 시 **놓친 cron 을 한 번씩 따라잡는다.**
    ⚠️ 창은 `MISFIRE_GRACE_SEC` 하나다 — "얼마나 늦어도 돌 가치가 있는가"를
       이미 정해 둔 값이고, 여기 새 숫자를 적지 않는다(사본 금지).
    ⚠️ 이미 오늘 돈 잡은 건너뛴다. 실행 기록이 원본이다.
    """
    from apscheduler.triggers.cron import CronTrigger

    from app.health import _job_runs

    now = datetime.now(KST)
    try:
        runs = await _job_runs(redis)
    except Exception as exc:
        logger.warning("[catchup] 실행 기록 조회 실패 — 따라잡기 생략: %s", exc)
        return []
    fns = {jid: fn for jid, fn, _ in _job_specs()}
    fired: list[str] = []
    for job_id, trig in _JOB_TRIGGERS.items():
        if not isinstance(trig, CronTrigger) or job_id not in fns:
            continue
        prev = _last_fire_before(trig, now)
        if prev is None:
            continue
        row = runs.get(job_id) or {}
        last = None
        try:
            last = datetime.fromisoformat(row["at"]) if row.get("at") else None
        except (KeyError, ValueError):
            last = None
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if last >= prev:
                continue                      # 이미 돌았다
        logger.error("[catchup] 🔴 %s 오늘 발화(%s KST)를 재기동이 삼켰다 — "
                     "지금 한 번 따라잡는다", job_id, prev.astimezone(KST).strftime("%H:%M"))
        try:
            await fns[job_id]()
            fired.append(job_id)
        except Exception as exc:
            logger.warning("[catchup] %s 따라잡기 실패: %s", job_id, exc)
    if not fired:
        logger.info("[catchup] 놓친 cron 잡 없음")
    return fired


def _last_fire_before(trig, now):
    """그 트리거의 **직전 발화 시각**. 유예 창 밖이면 None.

    ⚠️ APScheduler 는 "다음 발화"만 준다. 유예 창 시작점부터 앞으로 걸어
       `now` 직전 것을 찾는다 — 발화 시각을 손으로 계산하지 않는다.
    """
    window = datetime.fromtimestamp(now.timestamp() - MISFIRE_GRACE_SEC,
                                     tz=KST)
    prev, cur = None, None
    for _ in range(64):                        # 무한 루프 방지
        cur = trig.get_next_fire_time(cur, window if cur is None else cur)
        if cur is None or cur >= now:
            break
        prev = cur
    return prev


async def _repair_impossible_live(pool) -> list[dict]:
    """🔴 [P0 2026-09-03] **시작 전 경기는 `live` 일 수 없다.** 불변식 복구.

    실사고: KBO 공식 페이지의 경기 전 `0-0` 플레이스홀더를 파서가 점수로 읽어
    4경기를 `live` 로 적재했다. 아시아 폴링은 `status='scheduled'` 만 조회하므로
    **행이 0건이 되어 조용히 아무것도 하지 않았다** — 카드도, 구제도, 경보도
    없었다. 파서를 고쳐도 이미 DB 에 들어간 행은 스스로 낫지 않는다.
    그 행을 고칠 유일한 경로(`upsert_schedule`)가 그 행을 못 찾기 때문이다.

    ⚠️ 이건 종목을 가리지 않는 **불변식**이다: 시작 시각이 미래인데 진행 중인
       경기는 없다. 멱등하고, 고칠 게 없으면 아무 일도 하지 않는다.
    """
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """UPDATE games SET status = 'scheduled', updated_at = now()
                WHERE status = 'live' AND starts_at > now()
             RETURNING id, sport, away, home, starts_at""")
    except Exception as exc:
        logger.warning("[repair] 불가능한 live 복구 실패: %s", exc)
        return []
    if not rows:
        logger.info("[repair] 시작 전 live 경기 0건 — 정상")
        return []
    for r in rows:
        logger.error("[repair] 🔴 시작 전인데 live 였다 → scheduled 복구 "
                     "game=%s %s %s@%s start=%s", r["id"], r["sport"],
                     r["away"], r["home"], r["starts_at"])
    logger.error("[repair] 🔴 %d경기 복구 — 이 행들은 폴링 조회에서 통째로 "
                 "빠져 있었다(카드·구제·경보 전부 침묵)", len(rows))
    return [dict(r) for r in rows]


async def _startup_forensics(pool, redis) -> None:
    """기동 시 1회 소급 진단. **읽기만 한다** — 아무것도 고치지 않는다.

    ① API 차단 상태와 그 시작 시각 (배당이 며칠째 멈춰 있었는가)
    ② 배당 스냅샷 최신 시각 · 가치 게이트가 무력화된 기간
    ③ 하이픈 이름으로 오염됐던 타순 이력 건수
    """
    from datetime import datetime as _dt

    # ① 차단 상태
    try:
        from app.api_guard import block_info

        for name in ("odds", "anthropic", "perplexity", "grok"):
            info = await block_info(name)
            if not info:
                continue
            at = info.get("at") or ""
            days = ""
            try:
                days = f" · {(_dt.now(UTC) - _dt.fromisoformat(at)).days}일째"
            except Exception:
                days = ""
            logger.error("[forensics] 🔴 %s 차단 중 — %s 부터%s (사유=%s) "
                         "TTL 없음: 키 교체 또는 clear_block 전까지 안 풀린다",
                         name, at[:19], days, info.get("reason"))
    except Exception as exc:
        logger.warning("[forensics] 차단 조회 실패: %s", exc)

    # ② 배당 적재가 언제 멈췄나 — 가치 게이트 무력화 기간의 근거
    try:
        row = await pool.fetchrow(
            "SELECT max(captured_at) AS last, count(*) AS n FROM odds_snapshots")
        if row and row["last"]:
            age = (_dt.now(UTC) - row["last"]).total_seconds() / 3600
            level = logger.error if age > 6 else logger.info
            level("[forensics] 배당 스냅샷 최신 %s (%.1f시간 전) · 총 %s행 — "
                  "이 기간 가치 게이트는 배당 없이 확률만으로 동작했다",
                  row["last"], age, row["n"])
        else:
            logger.error("[forensics] 🔴 odds_snapshots 가 비어 있다")
    except Exception as exc:
        logger.warning("[forensics] 배당 적재 조회 실패: %s", exc)

    # ③ 하이픈 이름 오염 — 저장된 타순 배열이 9명이 아닌 행이 몇 건인가.
    #    `Pete Crow-Armstrong` 이 두 조각으로 갈려 들어가면 길이가 10이 된다.
    #    그 라인업은 슬롯이 통째로 밀려 가짜 '타순 이동'을 만들었다.
    #    ⚠️ **확정본만 센다** — 공시 전 부분 타순은 정상이다. 두 테이블이
    #       "확정"을 다르게 적는다: `lineups.status='confirmed'` vs
    #       `lineup_events.is_final`. 한쪽 이름을 양쪽에 쓰면 조회가 깨진다
    #       (실사고 2026-09-03: `column l.status does not exist`).
    for table, ts, final in (("lineup_events", "observed_at", "l.is_final"),
                             ("lineups", "captured_at", "l.status = 'confirmed'")):
        try:
            rows = await pool.fetch(
                f"""SELECT g.sport,
                           count(*) AS bad,
                           min(l.{ts}) AS first_seen,
                           max(l.{ts}) AS last_seen
                      FROM {table} l JOIN games g ON g.id = l.game_id
                     WHERE l.batting_order IS NOT NULL
                       AND jsonb_typeof(l.batting_order) = 'array'
                       AND jsonb_array_length(l.batting_order) <> 9
                       AND {final}
                     GROUP BY g.sport ORDER BY g.sport""")
            if rows:
                for r in rows:
                    logger.error("[forensics] 🔴 %s %s — 타순 길이 ≠ 9 인 행 %s건 "
                                 "(%s ~ %s). 이 라인업은 슬롯이 밀려 가짜 "
                                 "'타순 이동'이 라인업 의도·T5 로 흘렀다",
                                 table, r["sport"], r["bad"],
                                 str(r["first_seen"])[:16], str(r["last_seen"])[:16])
            else:
                logger.info("[forensics] %s 확정 타순 길이 이상 0건 "
                            "(잠정 상태의 부분 타순은 정상이라 세지 않는다)",
                            table)
        except Exception as exc:
            logger.warning("[forensics] %s 조회 실패: %s", table, exc)


# ⚠️ 아래도 **1회성 코드다.** 축구 라인업 리드타임·레이트리밋을 하룻밤 재기 위한
#    프로브이고, 관측이 끝나 로그를 회수한 뒤에는 다음 배포에서 이 함수와
#    main()의 create_task 호출을 통째로 지운다.
#    (docs/SOCCER_FORM.md 부록 B 승인 조건 2·3의 측정 도구)
#
# 원칙: **"내 컴퓨터가 켜져 있어야 도는 것"은 이 시스템에 하나도 없어야 한다.**
#   로컬 nohup으로 띄우면 맥이 잠들 때 조용히 죽고, 죽었다는 사실조차
#   서버 로그에 남지 않아 "데이터 없음"과 "수집 실패"를 구분할 수 없다.
SOCCER_PROBE_ENABLED = True


async def soccer_lineup_probe_job() -> None:
    """축구 라인업 리드타임 프로브 — 읽기 전용, 결과는 **구조화 로그**로.

    ⚠️ 프로덕션 Redis/DB를 건드리지 않는다. 프로브 모듈은 httpx와 표준
       라이브러리만 import 한다(계약 테스트로 잠금).
    ⚠️ 결과를 파일이 아니라 로그로 남긴다 — 컨테이너 파일시스템은 재배포에
       사라지고, railway 로그는 남아 회수·재조립할 수 있다.
    ⚠️ 프로브 실패가 스케줄러 본연의 잡을 죽이면 안 된다 — 전 구간 예외 격리.
    """
    if not SOCCER_PROBE_ENABLED:
        return
    try:
        from tools.probe_soccer_lineup import run as probe_run
    except Exception as exc:
        logger.warning("[soccer-probe] 로드 실패 — 건너뜀: %s", exc)
        return

    def emit(rec: dict) -> None:
        # 한 줄 = JSON 1건. 내일 아침 `grep '\[soccer-probe\] {'` 로 jsonl 재조립.
        try:
            logger.info("[soccer-probe] %s", json.dumps(rec, ensure_ascii=False))
        except Exception:
            pass

    def plog(msg: str) -> None:
        logger.info("[soccer-probe] %s", msg)

    try:
        out = await probe_run(hours=30, lead_start=150, interval=600,
                              emit=emit, log=plog)
        logger.info("[soccer-probe] 종료 — 관측 %d건 / 대상 %d건",
                    len(out.get("observed") or []), out.get("targets", 0))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("[soccer-probe] 실패 — 스케줄러는 계속: %s", exc)


async def watch_job() -> None:
    """[DS-2 / deepsearch_addendum DS-2a] 변화 감지 — **조회만 한다.**

    🔴 09-21 에 늦게 안 셋이 전부 타이밍 실패였다: 08:30 중지 · 11:06 등록
       공시 · 12:40경 우천 중지. 페이지는 그 자리에 있었고 그 순간에 안 봤다.
    ⚠️ 워치독·자가점검과 같은 규약 — **예외를 밖으로 던지지 않는다.**
       감시가 스케줄러를 죽이면 감시가 아니라 고장이다.
    ⚠️ 판정·발송에 닿지 않는다. 결과는 `watch_events` 와 로그뿐이다.
    """
    from app.deepsearch.watch import run_watch

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        await run_watch(pool, redis)
    except Exception as exc:
        logger.warning("[watch] 잡 실패 — 무시하고 계속: %s", exc)
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


async def selfcheck_job() -> None:
    """[W1 / wiring_first §W1] 자가 점검 — **조회만 한다.**

    🔴 결과는 Redis 한 칸과 /health 한 줄로만 간다. 판정·발송에 닿지 않는다.
    ⚠️ 워치독과 같은 규약이다 — 예외를 밖으로 던지지 않는다. 점검이 스케줄러를
       죽이면 점검이 아니라 고장이다.
    """
    from app.ops.selfcheck import run as run_selfcheck

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        pool = await get_pool()
        await run_selfcheck(pool, redis)
    except Exception as exc:
        logger.warning("[selfcheck] 잡 실패 — 무시하고 계속: %s", exc)
    finally:
        await redis.aclose()


async def watchdog_job() -> None:
    """[운영 안정화 2] 5분마다 고장 점검 — 사람이 먼저 발견하는 고장 0건이 목표.

    ⚠️ 워치독 실패는 **경보를 못 보내게 만든다.** 예외를 밖으로 던지지 않고
       로그만 남긴다 — 잡 실패 알림 회로 자체가 이 잡에 의존하지 않는다.
    """
    from app.watchdog import run

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        pool = None
        try:
            pool = await get_pool()
        except Exception as exc:
            logger.warning("[watchdog] DB 연결 실패(나머지 점검은 계속): %s", exc)
        return await run(pool, redis)
    except Exception as exc:
        logger.exception("[watchdog] 점검 자체가 실패: %s", exc)
        return None
    finally:
        await redis.aclose()


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


# ── [TRG-2 2026-09-14] 시점 트리거 1분 루프 — Part A 배선 ───────────────
#: 이름표를 붙일 배당 스냅샷의 최대 나이(분). 배당 수집 주기의 두 배 + 여유다.
#  더 오래된 값에 `open` 을 붙이면 괴리 기준선이 거짓이 된다.
TRIGGER_SNAP_MAX_AGE_MIN = 70
#: 한 tick 에서 집어 오는 due 상한. 우선순위로 고른 뒤 동시 상한만큼 쏜다.
TRIGGER_DUE_LIMIT = 60

#: 계획 대상 — 트리거가 아직 없거나, 킥오프가 옮겨져 `close` 가 어긋난 경기.
#: 🔴 [U1 2026-09-15] 종전에는 `kind='close'` **하나를 보초**로 썼다. 그게
#   있으면 경기를 통째로 건너뛰므로 **종류가 늘어도 기존 경기엔 안 붙었다**
#   (실측: ACTIONS 8종을 넣었는데 game=8205 는 그대로 5행).
#   → 트리거 **개수**를 함께 본다($3 = len(triggers.ALL_KINDS)).
#   ⚠️ 개수만 보면 안 된다 — 킥오프가 바뀐 경우도 종전대로 다시 계획한다.
_TRIGGER_PLAN_SQL = """
    SELECT g.id, g.starts_at
      FROM games g
      LEFT JOIN (
            SELECT game_id,
                   count(*)                                             AS n,
                   max(due_at)   FILTER (WHERE kind = 'close')          AS close_due,
                   bool_or(fired_at IS NOT NULL)
                       FILTER (WHERE kind = 'close')                    AS close_fired
              FROM game_triggers GROUP BY game_id
      ) t ON t.game_id = g.id
     WHERE g.starts_at IS NOT NULL
       AND g.starts_at BETWEEN $1 AND $2
       AND (t.game_id IS NULL
            OR COALESCE(t.n, 0) < $3
            OR (COALESCE(t.close_fired, FALSE) = FALSE
                AND t.close_due IS DISTINCT FROM g.starts_at))
"""

#: 그 경기의 **가장 최근** 배당에만 이름표를 붙인다(소스·시장·쪽·라인별 1행).
_TRIGGER_TAG_SQL = """
    WITH latest AS (
        SELECT DISTINCT ON (provider, market, side, line) id
          FROM odds_snapshots
         WHERE game_id = $1 AND snap_tag IS NULL AND captured_at >= $3
         ORDER BY provider, market, side, line, captured_at DESC
    )
    UPDATE odds_snapshots SET snap_tag = $2
     WHERE id IN (SELECT id FROM latest)
"""


async def _triggers_tick(pool=None, now=None) -> dict:
    """[TRG-2] 시점이 된 트리거를 쏜다. 반환 `{계획, 발사, 태그, 무스냅}`.

    🔴 **여기서 배당을 새로 긁지 않는다.** 이미 수집된 스냅샷에 이름표를 붙일
       뿐이다(`record_clv` 와 같은 원칙 — "새 소스를 부르지 않는다"). 트리거가
       수집을 부르기 시작하면 1분마다 외부 호출이 늘고 예산이 무너진다.
    ⚠️ 스냅샷이 없어도 트리거는 fired 로 닫는다 — 안 닫으면 1분마다 영원히
       재시도한다. 대신 사유를 로그에 남긴다(조용한 0 금지).
    ⚠️ 시점표·동시 상한·SQL 은 `app.engine.triggers` 가 원본이다. 여기에
       베끼지 않는다.
    """
    from app.engine import triggers as T

    pool = pool or await get_pool()
    now = now or datetime.now(UTC)
    out = {"계획": 0, "발사": 0, "태그": 0, "무스냅": 0}

    # ① 계획 — 킥오프가 있는 예정 경기에 5시점을 등록/갱신한다.
    try:
        # 🔴 [U1 2026-09-15] 창을 **전후 30시간**으로. 종전 −6h 는 늦게 적재된
        #    경기(ACL 은 킥오프 당일에 처음 들어왔다)의 지난 시점을 놓쳤다.
        # 🔴 [U1] 종류 수는 `triggers.ALL_KINDS` 가 원본이다 — 숫자를 여기
        #    적지 않는다(사본 금지).
        rows = await pool.fetch(_TRIGGER_PLAN_SQL,
                                now - timedelta(hours=30), now + timedelta(hours=30),
                                len(T.ALL_KINDS))
    except Exception as exc:
        logger.warning("[triggers] 계획 대상 조회 실패: %s", exc)
        rows = []
    for r in rows:
        for p in T.plan(r["starts_at"]):
            try:
                await pool.execute(T.UPSERT_SQL, r["id"], p["kind"], p["due_at"])
                out["계획"] += 1
            except Exception as exc:
                logger.warning("[triggers] 계획 실패 game=%s %s: %s",
                               r["id"], p["kind"], exc)

    # ② 발사 — 시각이 된 것을 우선순위대로. 동시 상한은 원본을 쓴다.
    try:
        due = [dict(r) for r in await pool.fetch(T.DUE_SQL, now, TRIGGER_DUE_LIMIT)]
    except Exception as exc:
        logger.warning("[triggers] due 조회 실패: %s", exc)
        due = []
    due = T.prioritize(due)
    sem = asyncio.Semaphore(T.MAX_CONCURRENT)
    since = now - timedelta(minutes=TRIGGER_SNAP_MAX_AGE_MIN)

    async def _one(row: dict) -> None:
        async with sem:
            # 🔴 [U1 2026-09-15] **스냅샷 종류만 이름표를 붙인다.** 행동 트리거
            #    (model·rejudge·card…)의 kind 가 `snap_tag` 로 새면
            #    `odds_move.BASELINE_ORDER` 에 없는 값이 되어 `record_move` 의
            #    `order.index()` 가 ValueError 로 터진다 — 이동 분석이 죽는다.
            #    판정의 원본은 `triggers.is_snapshot` 이다(목록을 여기 적지 않는다).
            n = 0
            if T.is_snapshot(row.get("kind")):
                try:
                    res = await pool.execute(_TRIGGER_TAG_SQL, row["game_id"],
                                             row["kind"], since)
                    n = int(str(res or "").split()[-1] or 0)
                except Exception as exc:
                    logger.warning("[triggers] 이름표 실패 game=%s %s: %s",
                                   row["game_id"], row["kind"], exc)
                    n = 0
                if n:
                    out["태그"] += n
                else:
                    out["무스냅"] += 1
                    logger.info("[triggers] game=%s %s — 최근 %d분 안에 잡힌 배당이 "
                                "없다. 이름표 없이 닫는다",
                                row["game_id"], row["kind"], TRIGGER_SNAP_MAX_AGE_MIN)
            else:
                # ⚠️ 자리만 있는 트리거다(U5~U11 이 붙인다). 조용히 닫지 않는다.
                out.setdefault("행동", 0)
                out["행동"] += 1
            # 🔴 [FOT-2 사용자 지시] **T-60 에 라인업을 다시 받는다.**
            #    시점 이름(`lineup`)은 `triggers.KINDS` 가 원본이다 — 여기에
            #    분(分)을 적지 않는다. 실패는 결측이고 이름표 작업을 막지 않는다.
            if row.get("kind") == "lineup" and (row.get("sport") or "") == "soccer":
                try:
                    await _lineup_recheck(pool, row, now)
                except Exception as exc:
                    logger.warning("[triggers] 라인업 재확인 실패 game=%s: %s",
                                   row.get("game_id"), exc)
            try:
                await pool.execute(T.MARK_SQL, row["id"], now)
                out["발사"] += 1
            except Exception as exc:
                logger.warning("[triggers] fired 기록 실패 id=%s: %s",
                               row["id"], exc)

    if due:
        await asyncio.gather(*(_one(r) for r in due))
    if out["계획"] or out["발사"]:
        # ⚠️ 우선순위는 |gap| 순인데 gap 을 넣어 주는 배선(GATE-1)이 아직 없다.
        #    그래서 지금은 사실상 due 순이다 — 그 사실을 로그가 말한다.
        logger.info("[triggers] 계획 %d · 발사 %d · 이름표 %d행 · 무스냅 %d "
                    "(우선순위 gap 미배선 → due 순)",
                    out["계획"], out["발사"], out["태그"], out["무스냅"])
    return out


async def _lineup_recheck(pool, row: dict, now) -> None:
    """[FOT-2] T-60 재호출 — `confirmed` 로 바뀌면 예상 XI 와 대조한다.

    🔴 **두 시점 값을 모두 원장에 남긴다**(사용자 지시). "안 바뀌었다"와
       "못 받았다"를 나중에 갈라야 한다.
    ⚠️ diff 는 `fotmob.diff_xi` 가 **id 기준**으로 센다 — 이름 매칭 금지.
    """
    from app.collectors import fotmob
    from app.engine import game_trace as GT

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        jg = {"game_id": row["game_id"], "sport": row.get("sport"),
              "home": row.get("home"), "away": row.get("away"),
              "starts_at": row.get("starts_at")}
        got = await fotmob.attach(jg, redis=redis)
        date = (row.get("starts_at") or now).astimezone(KST).strftime("%Y-%m-%d")
        if not got:
            await GT.note(pool, game_id=row["game_id"], sport="soccer", date=date,
                          stage=GT.COLLECT, summary="T-60 라인업 재확인 — 받지 못했다",
                          ref={"event": "fotmob_lineup", "lineup_type": None})
            return
        await GT.note(
            pool, game_id=row["game_id"], sport="soccer", date=date,
            stage=GT.COLLECT,
            summary=(f"T-60 라인업 {got.get('lineup_type')} · "
                     f"홈 {len((got.get('home') or {}).get('starters') or [])}명 · "
                     f"원정 {len((got.get('away') or {}).get('starters') or [])}명"
                     + (f" · diff {got.get('diff')}" if got.get("diff") else "")),
            ref={"event": "fotmob_lineup", "lineup_type": got.get("lineup_type"),
                 "diff": got.get("diff"), "missing": got.get("missing"),
                 "home_xi": [p.get("name")
                             for p in (got.get("home") or {}).get("starters") or []],
                 "away_xi": [p.get("name")
                             for p in (got.get("away") or {}).get("starters") or []]})
        logger.info("[triggers] game=%s T-60 라인업 %s%s", row["game_id"],
                    got.get("lineup_type"),
                    f" · diff {got.get('diff')}" if got.get("diff") else "")
        # 🔴 [FOT-3 2026-09-17] **diff 를 다시 계산에 넣는다.** 종전에는
        #    game_trace 에 적고 끝나서, 확정 라인업이 예상과 달라도 p_code 도
        #    등급도 그대로였다 — T-60 재판정이 이름뿐이었다(PART A 표 S10).
        # 🔴 출처는 **공식 XI** 다. docs/FORKS.md F-2 의 권한표에서 `주전결장`
        #    을 **대체할 수 있는 유일한 출처**이고, 정작 그쪽이 안 이어져
        #    있었다(딥서치 경로만 PA-27 로 이어졌다).
        # 🔴 **저장 전용이다.** p_code·confidence·adj_pp 를 안 덮고 *_after 에만
        #    남긴다. 실패해도 트리거를 막지 않는다(CLV·이동과 같은 규약).
        try:
            await _rejudge_from_xi(pool, row["game_id"], got)
        except Exception as exc:
            logger.warning("[triggers] game=%s T-60 재판정 실패: %s",
                           row["game_id"], exc)
    finally:
        await redis.aclose()


def _xi_players(got: dict) -> tuple[dict, float | None]:
    """공식·예상 XI 선수 → `({이름: 선수}, 기준 총가치)`.

    🔴 **팀별 총가치로 중요도를 맞춘다.** `adjust.importance` 의 분모는 그
       선수 **자기 팀**의 선발 총가치인데 `rejudge.reweigh` 는
       `team_total_value` 를 하나만 받는다. 그래서 여기서 원정 선수 가치를
       `홈총액/원정총액` 으로 **환산해** 넣는다 — 계산이 같아지고 reweigh
       시그니처를 안 바꾼다.
    ⚠️ 갈림길이 아니다 — 분모가 자기 팀이라는 것은 `importance` 문서가 이미
       정해 놓았다.
    🔴 총가치가 없으면 **환산하지 않는다.** 없는 값을 지어내지 않는다.
    """
    tot = {side: (got.get(side) or {}).get("total_market_value")
           for side in ("home", "away")}
    ref = tot.get("home") or tot.get("away")
    box: dict = {}
    for side in ("home", "away"):
        scale = 1.0
        if ref and tot.get(side):
            scale = float(ref) / float(tot[side])
        for pl in ((got.get(side) or {}).get("starters") or []):
            name = pl.get("name")
            if not name:
                continue
            mv = pl.get("market_value")
            box[str(name)] = {**pl,
                              "market_value": (float(mv) * scale if mv
                                               else mv)}
    return box, (float(ref) if ref else None)


async def _rejudge_from_xi(pool, game_id: int, got: dict) -> bool:
    """[FOT-3] 공식 XI diff → 재가감 → 원장 `*_after`. **저장 전용.**

    🔴 `diff` 가 없으면 아무것도 안 한다 — `fotmob.attach` 는 `confirmed` 일
       때만 diff 를 채운다. 예상 XI 단계에서 재판정하지 않는다.
    🔴 원장 행이 없으면 안 쓴다 — 판정 전이면 되짚을 `p_code` 가 없다.
    """
    from app.engine import pick_ledger as PL
    from app.engine import rejudge as RJ

    diff = got.get("diff")
    if not diff:
        return False
    row = await pool.fetchrow(
        "SELECT p_code, adj_pp, confidence FROM pick_ledger "
        "WHERE game_id = $1 AND is_final", game_id)
    if row is None or row["p_code"] is None:
        logger.info("[rejudge] game=%s 원장 판정이 없다 — T-60 재판정 안 함",
                    game_id)
        return False
    raw = row["adj_pp"]
    adj = json.loads(raw) if isinstance(raw, str) else (raw or {})
    players, total = _xi_players(got)
    rj = RJ.reweigh(adj=adj, p_code=row["p_code"], diff=diff, players=players,
                    team_total_value=total, grade=row["confidence"],
                    sport="soccer", source=RJ.SRC_OFFICIAL)
    wrote = await PL.record_rejudge(pool, game_id=game_id, rj=rj,
                                    by=RJ.SRC_OFFICIAL)
    logger.info("[rejudge] game=%s 공식 XI → p_code %s → %s · 등급 %s → %s · "
                "%s · 저장 %s", game_id, row["p_code"], rj.get("p_code_after"),
                row["confidence"], rj.get("grade_after"), rj.get("why"), wrote)
    return wrote


async def triggers_job() -> None:
    """[TRG-2] 1분 트리거 루프. 수집·판정은 하지 않는다 — 시각만 관리한다."""
    await _triggers_tick()


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
        # [TRG-2] 시점 트리거 — 1분. 배당을 긁지 않고 이름표만 붙인다.
        ("triggers_1m", triggers_job, IntervalTrigger(minutes=1)),
        ("watchdog_5m", watchdog_job, IntervalTrigger(minutes=5)),
        # 🔴 [W1 / wiring_first 2026-09-21] 자가 점검. **조회 전용**이고
        #    외부 API 를 부르지 않는다(DB SELECT 3개 + Redis 스캔).
        #    ⚠️ 워치독보다 성기게 둔다 — 같은 자료를 5분마다 다시 셀 이유가 없다.
        ("selfcheck_30m", selfcheck_job, IntervalTrigger(minutes=30)),
        # 🔴 [DS-2 2026-09-21] 변화 감지. **비용 0** — 해시가 바뀐 때만 파서를
        #    돌린다. 주기의 원본은 `config/deepsearch.yaml` 의 `watch.intervals`
        #    이고, 여기서는 **가장 촘촘한 주기**로 돈다(공지 10분).
        #    ⚠️ 잡 자체는 조회 전용이다. 판정·발송에 닿지 않는다.
        ("watch_10m", watch_job, IntervalTrigger(minutes=10)),
        ("odds_snapshot_30m", odds_snapshot_job, IntervalTrigger(minutes=30)),
        # 🔴 [ODN-1] KBO·NPB 총점 — **하루 2회**. 월 1,000 크레딧이라
        #    30분 주기로는 이틀이면 끝난다(11,520콜 필요).
        #    15:00 = 아시아 야구 T-3h · 17:30 = T-1h(라인업 뒤).
        #    ⚠️ 위 30분 잡은 **안 건드린다** — 무료 소스이고 CLV 가 거기서 난다.
        ("oddsapinet_2x", oddsapinet_job,
         CronTrigger(hour="15,17", minute=30, timezone=KST)),
        # [SAT] 위성 수집 — 기본 꺼짐(satellite_enabled). 켜면 15분마다 DB에 없는
        #   경기 정보를 미리 긁어 캐시에 쌓는다. 판정 경로는 아직 안 읽는다(증분2 전).
        ("satellite_15m", satellite_job, IntervalTrigger(minutes=15)),
        # [v1.4 STEP 13] 섀도 관측. `PIPELINE_V14` 가 꺼져 있으면 즉시 반환한다.
        ("flow_shadow_15m", flow_shadow_job, IntervalTrigger(minutes=15)),
        # [EXP-2] 자동 내보내기. 🔴 읽기 전용 — 발송 경로를 타지 않는다.
        #   문턱 방식이라 주기는 "얼마나 정확히 T-3h 를 맞추나"만 정한다.
        ("export_t3h_10m", export_t3h_job, IntervalTrigger(minutes=10)),
        ("export_lineup_5m", export_lineup_job, IntervalTrigger(minutes=5)),
        # [ODN-3] MLB 팀토탈·F5 — 게이트 대상만 하루 1회. 예산이 먼저다.
        ("odds_mlb_deriv_10m", odds_mlb_deriv_job, IntervalTrigger(minutes=10)),
        ("ingest_finals_13h", finals_job, CronTrigger(hour=13, minute=0, timezone=KST)),
        # [축구 시범 운영] 10분마다 — T-3h 판정 · confirmed 재판정.
        #   유럽 경기는 KST 심야~새벽이라 창을 넓게 둔다.
        ("soccer_trial_10m", soccer_trial_job,
         CronTrigger(hour="0-6,18-23", minute="*/10", timezone=KST)),
        # [일일 요약] 아시아판 17:35 (T-30 잠정 강제 직후) · 해외판 21:00
        ("daily_summary_asia", daily_summary_asia_job,
         CronTrigger(hour=17, minute=35, timezone=KST)),
        # 🔴 해외판은 **판정 이후**여야 한다. 21:00은 MLB 프리페치(04:30)와
        #   축구 T-3h 판정(22:30~)보다 앞서서, 매일 "픽 없음"만 나갔다
        #   (실측 2026-08-31 21:00). MLB 판정이 끝나는 05:30으로 옮긴다.
        ("daily_summary_overseas", daily_summary_overseas_job,
         CronTrigger(hour=5, minute=30, timezone=KST)),
        # 축구는 KST 심야에 판정되므로 그 뒤에 한 장 더 — 밤 픽을 걸 시각에 맞춘다.
        ("daily_summary_soccer", daily_summary_soccer_job,
         CronTrigger(hour=1, minute=45, timezone=KST)),
        # [v1.1 0단계] 주간 캘리브레이션 — 일요일 밤, 그날 경기가 끝난 뒤.
        #   측정 리포트일 뿐 판정에 개입하지 않는다.
        ("calibration_weekly", calibration_report_job,
         CronTrigger(day_of_week="sun", hour=23, minute=30, timezone=KST)),
        ("research_retry_45m", research_retry_job, IntervalTrigger(minutes=45)),
        # 🔴 [SCH-2 2026-09-08] `lineup_poll_30m` 을 **뺐다 — 고유 커버리지가 0이었다.**
        #      lineup_poll_30m → mlb_pregame_poll() + crawler_lineup_poll(("npb","kbo"))
        #      mlb_pregame_5m  → mlb_pregame_poll()              ← 같은 함수
        #      asia_pregame_5m → crawler_lineup_poll(("kbo",))   ← 같은 함수
        #      npb_pregame_2m  → crawler_lineup_poll(("npb",))   ← 같은 함수
        #    창 게이트(`mlb_poll_window`·`asia_poll_window`)도 같은 것을 쓴다.
        #    30분마다 이미 하는 일을 한 번 더 했고, 5분/2분 잡과 **동시에 발화하면
        #    경합**했다. 크레딧을 두 번 태우고 원장에 두 번 찍힌다.
        #    ⚠️ 이 잡만이 원장 폭주의 원인은 아니다 — 주 원인은 재판정 방아쇠
        #       (`changed = status != prev or bool(notes)`)다. 여기서 줄이는 몫은
        #       KBO 기준 시간당 12회 대비 2회, **약 14%** 다. 과장하지 않는다.
        #    ⚠️ `lineup_poll_job` 함수는 **지우지 않았다** — 등록만 뺐다.
        #       수동 호출·테스트가 그것을 쓸 수 있고, 지우는 것은 별건이다.
        # NPB 18:00 → 17:45까지 크롤·분석 종료. KBO는 시작 직전까지 5분마다.
        # 🔴 종전에는 CronTrigger(hour="17,18") 였다 — **시각을 코드에 박아**
        #    17~18시 슬레이트만 다뤘다. 주말 낮경기(14:00·17:00)·더블헤더·
        #    우천 순연 편성은 폴링 자체가 돌지 않는다.
        #    이제 5분마다 돌되 잡 서두에서 **오늘 실제 경기 시각**으로 창을
        #    연다(asia_poll_window). 요일 분기는 넣지 않는다 — 경기가 없으면
        #    게이트가 자연히 닫힌다.
        ("asia_pregame_5m", asia_pregame_kbo, IntervalTrigger(minutes=5)),
        # [npb-window] NPB는 공시(T-30)와 경량 재판정 종료선(T-10) 사이가
        #   20분뿐이다. 5분 간격이면 4틱, 공시 직후 한 틱을 놓치면 그 경기는
        #   끝이다. NPB만 2분으로 따로 돈다 — 창 게이트는 같은 것을 쓴다.
        ("npb_pregame_2m", npb_pregame_2m, IntervalTrigger(minutes=2)),
        # MLB 폴링. 사이트는 statsapi. 캐시만 보낸다.
        # 🔴 [2026-09-07] 종전에는 `CronTrigger(hour="5-11", …)` 로 **시각을
        #    박아** 01~04시 KST 경기 81건(최근 30일 337경기의 24%)에서 아예
        #    돌지 않았다. 발송 창이 T-180 에 열려도 폴링이 자고 있으니
        #    "첫 카드 보장선 T-30"이 그 24%에는 적용된 적이 없다.
        #    KBO·NPB 가 `hour="17,18"` 로 겪었던 것과 같은 결함이다.
        #    이제 5분마다 돌되 `mlb_poll_window` 가 실제 경기 시각으로 연다.
        ("mlb_pregame_5m", mlb_pregame_poll, IntervalTrigger(minutes=5)),
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


#: 기동 직후 **한 번 바로** 돌려야 하는 잡. IntervalTrigger 는 첫 실행이
#  주기만큼 뒤라, 재배포마다 그 길이만큼 눈먼 구간이 생긴다.
#  🔴 실측 2026-09-04: `odds_snapshot_30m` 이 그래서 굶었다. 15:21 기동 →
#     첫 실행 15:51. 그 사이 워치독이 `W-ODDS-STALE oddsportal` 을 66·71·76분
#     으로 세 번 울렸다. oddsportal 은 멀쩡했다(같은 시각 직접 호출 200,
#     KBO 15경기·NPB 12경기 파싱). 소스가 아니라 **우리 배포 리듬**이 원인이다.
#     같은 사고가 ENGINEERING.md §4 `[근거 134d37b]` 로 이미 한 번 적혀 있다.
#  ⚠️ 무거운 잡은 넣지 마라 — 여기 있는 것은 요청 1~2건짜리다.
RUN_AT_BOOT = ("odds_snapshot_30m",)


def build_scheduler() -> AsyncIOScheduler:
    from datetime import datetime as _dt

    scheduler = AsyncIOScheduler(timezone=KST)
    for job_id, fn, trigger in _job_specs():
        _JOB_TRIGGERS[job_id] = trigger
        if job_id in ("asia_pregame_5m", "mlb_pregame_5m"):
            grace = 4 * 60
        else:
            grace = MISFIRE_GRACE_SEC
        kw = {}
        if job_id in RUN_AT_BOOT:
            # 기동 시각 그대로 두면 스키마 적용·DB 연결과 겹친다. 30초 뒤로.
            kw["next_run_time"] = _dt.now(KST) + timedelta(seconds=30)
        scheduler.add_job(_instrument(job_id, fn), trigger, id=job_id,
                          misfire_grace_time=grace, coalesce=True,
                          max_instances=1, **kw)
    # [7-5] 하트비트 — 이게 살아 있어야 /health가 "스케줄러 실행 중"이라고 말한다
    scheduler.add_job(heartbeat_job, IntervalTrigger(minutes=2), id="heartbeat_2m",
                      misfire_grace_time=60, coalesce=True, max_instances=1)
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # 🔴 [SEC-1] 키가 로그에 평문으로 찍히지 않게 한다. basicConfig **뒤**라야
    #    루트 핸들러가 이미 있어 거기에도 필터가 걸린다 (전파된 레코드는 상위
    #    로거 필터를 다시 타지 않는다 — 핸들러 필터만이 본다).
    from app.secrets_mask import install_log_filter

    install_log_filter()
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
    # [감시 C2] L2·L3 의 가동 여부를 **기동 시점에** 말한다. 발송이 한 번
    #   돌아야 알 수 있으면, 저녁 내내 휴면인 줄 모르고 지나간다.
    try:
        from app.llm.gemini import is_available as _gemini_ok

        logger.info("[shadow] gemini %s — L2·L3 %s",
                    "설정됨" if _gemini_ok() else "미설정",
                    "가동" if _gemini_ok() else "휴면")
    except Exception as exc:
        logger.debug("[shadow] 가용성 확인 실패: %s", exc)
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("scheduler started: %s", [j.id for j in scheduler.get_jobs()])
    # [v1.1 0단계 · 1회성] 레저 소급 백필을 **기동 뒤 백그라운드로** 돌린다.
    #   기동 경로에서 await 하면 Redis 스캔이 스케줄러 시작을 지연시킨다 —
    #   17시대 라인업 폴을 놓치면 그날 발송이 통째로 밀린다.
    asyncio.create_task(startup_backfill_job())
    # [따라잡기] 재기동이 삼킨 오늘치 cron 을 한 번씩 돌린다.
    #   ⚠️ 스케줄러가 **뜬 뒤**에 부른다 — `_JOB_TRIGGERS` 가 그때 채워진다.
    #   ⚠️ 백그라운드로 띄운다. 프리페치는 몇 분 걸리는데, 기동 경로에서
    #      await 하면 17시대 라인업 폴을 놓친다.
    async def _catchup() -> None:
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await _catchup_missed_crons(r)
        except Exception as exc:
            logger.warning("[catchup] 따라잡기 실패: %s", exc)
        finally:
            await r.aclose()

    asyncio.create_task(_catchup())
    # [1회성] 축구 라인업 프로브 — 서버가 주체다. 로컬 맥에 의존하지 않는다.
    asyncio.create_task(soccer_lineup_probe_job())
    await asyncio.Event().wait()  # 종료 시그널까지 대기


if __name__ == "__main__":
    asyncio.run(main())
