"""[운영 안정화 2] 워치독 — **고장을 시스템이 먼저 알린다.**

사람이 먼저 발견하는 고장은 0건이어야 한다. 5분마다 다섯 가지를 보고,
하나라도 걸리면 관리자 채널로 코드가 붙은 1줄 경보를 보낸다.

  W-SEND-PENDING   발송 창인데 안 나간 경기
  W-ODDS-STALE     배당 스냅샷 나이 > 60분
  W-ODDS-BLOCKED   배당 API가 차단 상태 (TTL이 없어 스스로 안 풀린다)
  W-LLM-FAIL       LLM 호출 연속 실패
  W-STORE-DOWN     DB·Redis 오류
  W-JOB-LATE       잡의 마지막 실행이 주기의 2배를 넘김

🔴 왜 필요한가 (이번 주 실사고):
   · 배당이 **차단 상태로 며칠간 조용히 멈춰 있었다** — 매 실행 로그는
     `odds snapshot skipped — 차단 중`뿐이고 아무도 알림을 못 받았다.
     `api_guard` 차단은 TTL이 없어 시간으로 풀리지 않는다.
   · 크레딧이 소진돼 판정이 멈췄는데 카드도 경보도 없었다.
   · 판정 캐시 구제가 1회 실패로 20시간 잠겨 그 종목이 통째로 침묵했다.

⚠️ 이 모듈은 **읽기만 한다.** 고치지 않고, 차단을 임의로 풀지도 않는다 —
   자동 해제는 크레딧을 다시 태울 수 있어 사람이 결정할 일이다.
⚠️ 점검 하나가 실패해도 나머지는 계속한다. 워치독이 죽으면 눈이 없어진다.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

#: 배당 스냅샷이 이보다 오래되면 경보. 잡 주기가 30분이라 60분이면 2회 연속 실패다.
ODDS_STALE_MIN = 60
#: LLM 연속 실패 몇 번부터 경보인가. 크레딧 소진은 보통 즉시 연속으로 난다.
LLM_FAIL_STREAK = 3
#: 잡이 주기의 몇 배를 넘기면 늦은 것으로 보는가.
JOB_LATE_FACTOR = 2

LLM_FAIL_KEY = "watchdog:llm_fail"
ODDS_SNAP_KEY = "oddsnap:{}"

#: 주기가 있는 잡만 본다 — 하루 1회 잡은 여기서 판단하지 않는다(오탐 원천).
WATCHED_JOBS = {
    "heartbeat_2m": 2, "mlb_pregame_5m": 5, "asia_pregame_5m": 5,
    "odds_snapshot_30m": 30, "lineup_poll_30m": 30, "research_retry_45m": 45,
}


async def note_llm_failure(redis, detail: str = "") -> int:
    """LLM 호출 실패 1건. 반환은 현재 연속 실패 수."""
    if redis is None:
        return 0
    try:
        n = await redis.incr(LLM_FAIL_KEY)
        await redis.expire(LLM_FAIL_KEY, 3 * 3600)
        if detail:
            await redis.set(f"{LLM_FAIL_KEY}:last", detail[:300], ex=3 * 3600)
        return int(n)
    except Exception as exc:
        logger.debug("[watchdog] LLM 실패 기록 실패: %s", exc)
        return 0


async def clear_llm_failures(redis) -> None:
    """성공하면 연속 실패를 끊는다 — 이걸 빼면 경보가 영원히 남는다."""
    if redis is None:
        return
    try:
        await redis.delete(LLM_FAIL_KEY)
    except Exception as exc:
        logger.debug("[watchdog] LLM 실패 초기화 실패: %s", exc)


# ─────────────────────────── 점검 ───────────────────────────

async def check_odds(redis) -> list[tuple[str, str, str]]:
    """(a) 배당 차단 · (b) 스냅샷 나이. 반환 [(코드, 대상, 상세)]."""
    out = []
    try:
        from app.api_guard import block_info

        info = await block_info("odds")
        if info:
            at = str(info.get("at") or "?")[:19]
            out.append(("W-ODDS-BLOCKED", "odds",
                        f"{at} 부터 차단({info.get('reason')}) — TTL이 없어 "
                        f"스스로 풀리지 않는다. 키 교체 또는 수동 해제 필요"))
            return out          # 차단 중이면 stale 은 당연한 결과다. 중복 경보 금지.
    except Exception as exc:
        logger.debug("[watchdog] 배당 차단 조회 실패: %s", exc)
    try:
        from app.collectors.odds import SPORT_KEYS

        keys = {k for v in SPORT_KEYS.values() for k in (v or [])}
        now = datetime.now(UTC).timestamp()
        oldest, oldest_key = None, None
        for k in keys:
            raw = await redis.get(ODDS_SNAP_KEY.format(k))
            if raw is None:
                continue
            age = (now - float(raw)) / 60
            if oldest is None or age > oldest:
                oldest, oldest_key = age, k
        if oldest is not None and oldest > ODDS_STALE_MIN:
            out.append(("W-ODDS-STALE", oldest_key or "odds",
                        f"마지막 스냅샷 {oldest:.0f}분 전 (상한 {ODDS_STALE_MIN}분)"))
    except Exception as exc:
        logger.debug("[watchdog] 배당 나이 조회 실패: %s", exc)
    return out


async def check_llm(redis) -> list[tuple[str, str, str]]:
    """(c) LLM 연속 실패."""
    try:
        n = int(await redis.get(LLM_FAIL_KEY) or 0)
    except Exception:
        return []
    if n < LLM_FAIL_STREAK:
        return []
    try:
        last = await redis.get(f"{LLM_FAIL_KEY}:last") or ""
    except Exception:
        last = ""
    return [("W-LLM-FAIL", "judge",
             f"연속 {n}회 실패 — 판정이 멈춰 있다" + (f" ({last})" if last else ""))]


async def check_store(pool, redis) -> list[tuple[str, str, str]]:
    """(d) DB·Redis 실제 왕복. 연결 객체가 있는 것과 도는 것은 다르다."""
    out = []
    try:
        await redis.ping()
    except Exception as exc:
        out.append(("W-STORE-DOWN", "redis", f"{type(exc).__name__}: {exc}"[:200]))
    if pool is not None:
        try:
            await pool.fetchval("SELECT 1")
        except Exception as exc:
            out.append(("W-STORE-DOWN", "postgres",
                        f"{type(exc).__name__}: {exc}"[:200]))
    return out


async def check_jobs(redis) -> list[tuple[str, str, str]]:
    """(e) 잡별 마지막 실행이 주기의 2배를 넘겼는가."""
    from app.health import _job_runs

    try:
        runs = await _job_runs(redis)
    except Exception as exc:
        logger.debug("[watchdog] 잡 실행 조회 실패: %s", exc)
        return []
    now = datetime.now(UTC)
    out = []
    for job_id, period in WATCHED_JOBS.items():
        row = runs.get(job_id)
        if not row:
            continue          # 한 번도 안 돈 잡은 판단하지 않는다 (기동 직후 오탐)
        try:
            at = datetime.fromisoformat(row["at"])
        except (KeyError, ValueError):
            continue
        late = now - at
        if late > timedelta(minutes=period * JOB_LATE_FACTOR):
            out.append(("W-JOB-LATE", job_id,
                        f"마지막 실행 {late.total_seconds() / 60:.0f}분 전 "
                        f"(주기 {period}분)"))
    return out


async def check_pending_sends(pool, redis) -> list[tuple[str, str, str]]:
    """(f) 발송 창 안인데 아직 안 나간 경기.

    ⚠️ **판정이 있는데 안 나간 것만** 센다. 판정 자체가 없는 것은
       구제·크레딧 경보가 따로 잡는다 — 같은 고장을 두 번 울리지 않는다.
    """
    if pool is None:
        return []
    from app.engine.pregame_push import (
        SPORTS, card_sig_key, in_send_window, still_upcoming,
    )
    from app.pipeline import mlb_slate_date, today_kst

    now = datetime.now(UTC)
    try:
        rows = await pool.fetch(
            """SELECT id, sport, home, away, starts_at FROM games
                WHERE sport = ANY($1::text[]) AND status = 'scheduled'
                  AND starts_at > now()
                ORDER BY starts_at""", list(SPORTS))
    except Exception as exc:
        logger.debug("[watchdog] 미발송 조회 실패: %s", exc)
        return []
    pending = []
    for r in rows:
        sport = r["sport"]
        if not still_upcoming(r["starts_at"], now) or \
                not in_send_window(sport, r["starts_at"], now):
            continue
        try:
            if await redis.get(card_sig_key(r["id"])):
                continue                      # 이미 카드가 나갔다
            date_s = mlb_slate_date() if sport == "mlb" else today_kst()
            if not await redis.get(f"analysis:{sport}:{date_s}"):
                continue                      # 판정 캐시 자체가 없다 — 다른 경보 소관
        except Exception:
            continue
        pending.append(f"{r['away']}@{r['home']}")
    if not pending:
        return []
    return [("W-SEND-PENDING", f"{len(pending)}경기",
             "발송 창인데 카드가 없다: " + ", ".join(pending[:5])
             + (" 외" if len(pending) > 5 else ""))]


async def run_checks(pool, redis) -> list[tuple[str, str, str]]:
    """전 점검. 하나가 죽어도 나머지는 돈다 — 워치독이 눈을 감으면 안 된다."""
    found: list[tuple[str, str, str]] = []
    for name, coro in (
        ("store", check_store(pool, redis)),
        ("odds", check_odds(redis)),
        ("llm", check_llm(redis)),
        ("jobs", check_jobs(redis)),
        ("sends", check_pending_sends(pool, redis)),
    ):
        try:
            found += await coro
        except Exception as exc:
            logger.warning("[watchdog] 점검 %s 실패: %s", name, exc)
    return found


async def run(pool, redis) -> int:
    """점검 후 경보. 반환은 걸린 건수."""
    from app.alerts import watchdog as alert

    found = await run_checks(pool, redis)
    for code, target, detail in found:
        logger.warning("[watchdog] %s %s — %s", code, target, detail)
        try:
            await alert(code, detail, target=target)
        except Exception as exc:
            logger.warning("[watchdog] 경보 실패 %s: %s", code, exc)
    if not found:
        logger.info("[watchdog] 이상 없음")
    return len(found)
