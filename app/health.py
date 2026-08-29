"""[7-5] /health — 지금 시스템이 실제로 어떤 상태인지 한 화면.

실사고(2026-08-25): 봇은 26커밋 뒤처져 있었고 스케줄러는 꺼져 있었으며
프리페치는 전 단계 실패했는데, 사용자가 그 사실을 알 방법이 전혀 없었다.
이 명령은 "지금 믿어도 되는 상태인가"를 한 번에 답한다.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.engine.scoring import lambda_persisted
from app.version import boot_info, commits_behind, uptime_text

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

# 스케줄러 잡의 기대 주기 — 마지막 실행이 이보다 오래되면 '밀림'으로 본다
JOB_PERIODS = {
    "prefetch_daily": timedelta(days=1),
    "odds_snapshot_30m": timedelta(minutes=30),
    "grade_yesterday": timedelta(days=1),
    "research_retry_45m": timedelta(minutes=45),
    "lineup_poll_30m": timedelta(minutes=30),
    "asia_pregame_5m": timedelta(minutes=5),
    "mlb_pregame_5m": timedelta(minutes=5),
    "statcast_daily": timedelta(days=1),
    "soccerdata_daily": timedelta(days=1),
    "elo_refresh_weekly": timedelta(days=7),
}

HEARTBEAT_KEY = "scheduler:heartbeat"
HEARTBEAT_TTL = 300           # 스케줄러가 살아있으면 2분마다 갱신 → 5분 TTL
JOB_RUN_KEY = "scheduler:job_last_run"


async def touch_heartbeat(redis) -> None:
    """스케줄러가 살아있음을 알린다 (2분 주기 잡에서 호출)."""
    await redis.set(HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL)


async def record_job_run(redis, job_id: str, ok: bool, note: str = "") -> None:
    """잡 1회 실행 결과를 기록 — /health의 '마지막 실행'이 여기서 나온다."""
    payload = json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                          "ok": ok, "note": note[:200]})
    await redis.hset(JOB_RUN_KEY, job_id, payload)


async def _job_runs(redis) -> dict:
    try:
        raw = await redis.hgetall(JOB_RUN_KEY)
    except Exception:
        return {}
    out = {}
    for k, v in (raw or {}).items():
        try:
            out[k] = json.loads(v)
        except (ValueError, TypeError):
            continue
    return out


def _kst(iso: str | None) -> str:
    if not iso:
        return "기록 없음"
    try:
        return datetime.fromisoformat(iso).astimezone(KST).strftime("%m-%d %H:%M")
    except ValueError:
        return "기록 없음"


def _ago(iso: str | None) -> timedelta | None:
    if not iso:
        return None
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(iso)
    except ValueError:
        return None


def _dur(td: timedelta | None) -> str:
    if td is None:
        return "?"
    mins = int(td.total_seconds() // 60)
    if mins < 60:
        return f"{mins}분 전"
    hours, mins = divmod(mins, 60)
    if hours < 24:
        return f"{hours}시간 {mins}분 전"
    return f"{hours // 24}일 {hours % 24}시간 전"


async def _next_runs() -> dict:
    """트리거에서 다음 실행 시각을 계산 (스케줄러 프로세스와 무관하게)."""
    try:
        from app.scheduler import build_scheduler

        now = datetime.now(KST)
        return {j.id: j.trigger.get_next_fire_time(None, now)
                for j in build_scheduler().get_jobs()}
    except Exception as exc:
        logger.warning("[health] 다음 실행 시각 계산 실패: %s", exc)
        return {}


async def build_health(pool, redis) -> str:
    """/health 본문. 조회만 한다 — 어떤 상태도 바꾸지 않는다."""
    s = get_settings()
    now = datetime.now(KST)
    L: list[str] = [f"🩺 상태 점검 {now:%Y-%m-%d %H:%M} KST"]

    # ---- 1) 코드 버전 -------------------------------------------------
    info = boot_info()
    behind = commits_behind()
    icon = "🔴" if behind else "🟢"
    L.append("")
    L.append(f"{icon} 코드 {info.short} · 가동 {uptime_text()}")
    L.append(f"   {info.subject[:58]}")
    if behind:
        L.append(f"   ⚠️ 최신보다 {behind}커밋 뒤처짐 — 재시작 필요")
    if info.dirty:
        L.append("   ⚠️ 미커밋 변경이 있는 상태로 기동됨")

    # ---- 2) 스케줄러 --------------------------------------------------
    hb = await redis.get(HEARTBEAT_KEY) if redis else None
    alive = hb is not None
    L.append("")
    L.append(f"{'🟢' if alive else '🔴'} 스케줄러 "
             + (f"실행 중 (하트비트 {_dur(_ago(hb))})" if alive
                else "**미실행** — 프리페치·채점·스냅샷이 전부 멈춰 있습니다"))
    runs = await _job_runs(redis) if redis else {}
    nxt = await _next_runs()
    for job_id, period in JOB_PERIODS.items():
        r = runs.get(job_id) or {}
        ago = _ago(r.get("at"))
        late = ago is not None and ago > period * 2
        mark = "🔴" if (r and not r.get("ok")) else ("🟡" if late or ago is None else "🟢")
        n = nxt.get(job_id)
        L.append(f"   {mark} {job_id:<20} 마지막 {_kst(r.get('at'))} "
                 f"/ 다음 {n:%m-%d %H:%M}" if n else
                 f"   {mark} {job_id:<20} 마지막 {_kst(r.get('at'))}")

    # ---- 3) API 쿼터 --------------------------------------------------
    L.append("")
    L.append("📡 API 쿼터")
    if redis:
        today = now.strftime("%Y-%m-%d")
        odds_left = await redis.get("odds_quota_remaining")
        calls = await redis.get(f"research_calls:{today}")
        used = int(calls or 0)
        from app.research.deep import DAILY_RESEARCH_CAP

        L.append(f"   Odds API 잔여 {odds_left or '?'}콜")
        L.append(f"   Perplexity {used}/{DAILY_RESEARCH_CAP}콜"
                 + ("  ⚠️ 상한 초과 — 캐시 기준 동작" if used >= DAILY_RESEARCH_CAP else ""))
    L.append(f"   judge 모델 {s.judge_model}")

    # ---- 4) 마지막 프리페치 -------------------------------------------
    L.append("")
    pf = runs.get("prefetch_daily") or {}
    if pf:
        L.append(f"{'🟢' if pf.get('ok') else '🔴'} 마지막 프리페치 {_kst(pf.get('at'))} "
                 f"({_dur(_ago(pf.get('at')))})")
        if pf.get("note"):
            for line in str(pf["note"]).splitlines()[:8]:
                L.append(f"   {line}")
    else:
        L.append("⚪ 마지막 프리페치 기록 없음")

    # ---- 5) 오늘 지표 -------------------------------------------------
    L.append("")
    L.append("📊 오늘 지표")
    if redis:
        today = now.strftime("%Y-%m-%d")
        for sport, label in (("mlb", "MLB"), ("soccer", "축구")):
            raw = await redis.get(f"analysis:{sport}:{_slate_date(sport)}")
            if not raw:
                L.append(f"   {label} 분석 캐시 없음")
                continue
            data = json.loads(raw)
            games = [g for g in data.get("games", []) if g.get("status") == "scheduled"]
            lam = sum(1 for g in games if lambda_persisted(g))
            judged = sum(1 for g in games if g.get("p_claude") is not None)
            res_ok = sum(1 for g in games
                         if (g.get("research_status") in ("refreshed", "cached")))
            n = len(games) or 1
            L.append(f"   {label} λ {lam}/{len(games)} ({lam / n:.0%}) · "
                     f"판정 {judged}/{len(games)} ({judged / n:.0%}) · "
                     f"리서치 {res_ok}/{len(games)} ({res_ok / n:.0%})")
        fill = await redis.hgetall(f"research_fill:{today}")
        if fill:
            tot = int(fill.get("games_total", 0) or 0)
            inv = int(fill.get("games_invalid", 0) or 0)
            if tot:
                L.append(f"   리서치 무효율 {inv / tot:.0%} ({inv}/{tot})"
                         + ("  ⚠️ 30% 초과 — 키워드 과잉 의심" if inv / tot > 0.30 else ""))

    # ---- 6) DB 규모 ---------------------------------------------------
    if pool is not None:
        try:
            row = await pool.fetchrow(
                "SELECT (SELECT count(*) FROM games) g, "
                "(SELECT count(*) FROM predictions) p, "
                "(SELECT count(*) FROM predictions WHERE result IS NOT NULL) pg, "
                "(SELECT count(*) FROM games WHERE status <> 'final' "
                "  AND starts_at < now() - interval '6 hours') stale"
            )
            L.append("")
            L.append(f"🗄 경기 {row['g']} · 픽 {row['p']}(채점 {row['pg']})"
                     + (f" · ⚠️ 상태 밀림 {row['stale']}건" if row["stale"] else ""))
        except Exception as exc:
            L.append(f"\n🗄 DB 조회 실패: {exc}")

    # ---- 크롤러 생사 [§8-23] ------------------------------------------
    #  조용한 정지가 가장 위험하다 — 데이터가 어제 값으로 굳어도 아무도 모른다.
    try:
        from app.collectors.crawler_feed import is_alive

        ok, msg = await is_alive(redis)
        L.append(f"{'🟢' if ok else '🔴'} {msg}")
    except Exception as exc:      # 관측 장치가 본체를 죽이면 안 된다
        L.append(f"⚪ 크롤러 상태 확인 실패: {str(exc)[:60]}")

    # ---- LLM provider 사용량·장애 [#73] --------------------------------
    #  ⚠️ **잔여 크레딧은 쓰지 않는다.** 벤더가 알려주지 않는 값을 추정해 보여주면
    #     그 추정이 근거로 쓰인다. 아는 것(호출 수·장애 시각)만 쓴다.
    try:
        from app.llm.ledger import format_summary, summary

        L.append("")
        L.extend(format_summary(await summary(redis)))
    except Exception as exc:
        L.append(f"⚪ LLM 상태 확인 실패: {str(exc)[:60]}")

    # ---- 라인업 리드타임 관측 [관행값 → 실측 교체용] --------------------
    #  ⚠️ 지금 쓰는 기준(KBO 1시간·MLB 3시간)은 **관행**이다. 여기 쌓이는
    #     분포가 실측이고, 20건이 넘으면 config 교체를 검토한다.
    try:
        from app.engine.lineup_timing import observed, summarize

        for _sp in ("kbo", "mlb"):
            _leads = await observed(redis, _sp)
            if _leads:
                L.append(f"📋 {_sp.upper()} {summarize(_leads, _sp)}")
    except Exception as exc:
        L.append(f"⚪ 라인업 관측 확인 실패: {str(exc)[:60]}")

    return "\n".join(L)


def _slate_date(sport: str) -> str:
    from app.pipeline import mlb_slate_date, today_kst

    return mlb_slate_date() if sport == "mlb" else today_kst()
