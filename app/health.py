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
    "ingest_finals_13h": timedelta(days=1),
    "research_retry_45m": timedelta(minutes=45),
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
                else "**미실행** — 프리페치·점수 적재·스냅샷이 전부 멈춰 있습니다"))
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
                "(SELECT count(*) FROM games WHERE status <> 'final' "
                "  AND starts_at < now() - interval '6 hours') stale"
            )
            L.append("")
            L.append(f"🗄 경기 {row['g']} · 픽 기록 {row['p']}"
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

    # 🔴 [W1 / wiring_first 2026-09-21] 자가 점검 **요약 한 줄.**
    #    상세는 export 의 coverage 블록이다 — /health 를 길게 만들지 않는다.
    #    ⚠️ 사용자 결정 2026-09-20: 지시문의 `/status` 는 전부 여기로 읽는다.
    #       STEP 2 에서 `/status` 를 만들 때 이 줄들을 그리로 옮긴다.
    L.append("")
    L.append(await selfcheck_line(redis))

    # 🔴 [HYC-6 2026-09-23] **잴 방법이 없는 칸**을 한 줄로 알린다.
    #    HYC-3 로 `미실행`(볼 방법이 없다)이 생겼는데 운영에서 볼 데가 없었다 —
    #    "왜 이 변수는 영원히 비어 있나"를 사람이 DB 를 파야 알았다.
    #    ⚠️ 한 줄이다. 상세는 export 의 `coverage` 블록이다(계획서 규율).
    #    ⚠️ 관측이 본체를 죽이면 안 된다 — 실패는 한 줄로 삼킨다.
    try:
        import json as _json

        from app.flow.coverage import line as _cov_line

        _rows = await pool.fetch(
            # 🔴 [HYC6c 2026-09-23] **최신부터 자른다.** 종전에는 정렬 없이
            #    `LIMIT 500` 을 집어 미실행 행이 표본에 안 들어왔고,
            #    `/health` 가 통째로 침묵했다(실측: 같은 창에서 500행 →
            #    빈 목록 · 1,730행 → 잡힘).
            """SELECT snapshot_json FROM analysis_runs
                WHERE node = 'n06_verdict'
                  AND created_at_utc > now() - interval '2 days'
                ORDER BY id DESC
                LIMIT 3000""") if pool is not None else []
        _vs = []
        for _r in _rows:
            _sn = _r["snapshot_json"]
            if isinstance(_sn, str):
                _sn = _json.loads(_sn)
            _v = (_sn or {}).get("n06_verdict")
            if _v:
                _vs.append(_v)
        _cl = _cov_line(_vs)
        if _cl:
            L.append("")
            L.append(_cl)
    except Exception as exc:
        L.append(f"⚪ 변수 적용범위 확인 실패: {str(exc)[:60]}")

    # 🔴 [SRCV-1 / [2]b 2026-09-21 사용자 지시] 꺼진 소스를 **사유와 함께** 찍는다.
    #    "미상으로 멈춤"이 고장이 아니라 **의도한 동작**임을 여기서 말한다 —
    #    말하지 않으면 다음 사람이 고장으로 읽고 그냥 켠다.
    #    ⚠️ 문구의 원본은 `source_gate.restriction_lines()` 하나다(사본 금지).
    try:
        from app.collectors.source_gate import restriction_lines

        _r = restriction_lines()
        if _r:
            L.append("")
            L.extend(_r)
    except Exception as exc:      # 관측 장치가 본체를 죽이면 안 된다
        L.append(f"⚪ 소스 제한 확인 실패: {str(exc)[:60]}")

    return "\n".join(L)


async def selfcheck_line(redis) -> str:
    """자가 점검 한 줄. 🔴 **문구는 `selfcheck.summarize` 가 원본**이다 —
    여기서 다시 만들지 않는다(사본 금지).

    ⚠️ 읽기에 실패해도 /health 를 죽이지 않는다. 못 읽었으면 못 읽었다고 쓴다
       — "위반 없음"으로 적으면 조용한 0 이 된다.
    """
    try:
        import json

        from app.ops.selfcheck import key_of, summarize

        today = datetime.now(KST).strftime("%Y-%m-%d")
        raw = await redis.get(key_of(today)) if redis else None
        if raw is None:
            return "⚪ 자가 점검 — 오늘 기록 없음(아직 안 돌았다)"
        return summarize(json.loads(raw) or [])
    except Exception as exc:
        return f"⚪ 자가 점검 확인 실패: {str(exc)[:60]}"


def _slate_date(sport: str) -> str:
    from app.pipeline import mlb_slate_date, today_kst

    return mlb_slate_date() if sport == "mlb" else today_kst()
