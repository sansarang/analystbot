"""저녁 발송 점검 — 계약 문구 + 지금 측정값.

사람은 docs/PREGAME_CHECKLIST.md 와 텔레그램 `/checklist` 로 본다.
추측하지 않는다. Redis·DB·부트 해시에 있는 것만 쓴다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.engine.pregame_push import (
    NPB_FINISH_MIN,
    SEND_OPEN_MIN,
    analysis_open,
    card_sig_key,
    in_send_window,
    today_kst,
)
from app.pipeline import analysis_cache_ready

KST = ZoneInfo("Asia/Seoul")


def contract_lines() -> list[str]:
    return [
        "계약 (코드에 고정)",
        "· 일괄 17:45 덤프 없음. 경기마다 1차/변동",
        "· 빈 카드 없음. 14:00은 텔레그램 없음. MLB·축구 자동 없음",
        "· NPB 크롤·분석은 T-15(18:00→17:45)에 끝. 이후 재판정 없음",
        "· 17:30 1차 완료는 목표가 아니라 강제 종료선이 아님",
        "상세: docs/PREGAME_CHECKLIST.md",
    ]


def _mark(ok: bool | None) -> str:
    if ok is True:
        return "🟢"
    if ok is False:
        return "🔴"
    return "⚪"


def _npb_sample_start(now: datetime) -> datetime:
    """오늘 KST 18:00. 이미 지났으면 그대로(창 닫힘 표시)."""
    local = now.astimezone(KST)
    return local.replace(hour=18, minute=0, second=0, microsecond=0)


async def build_pregame_checklist(pool, redis, now=None) -> str:
    """조회만 한다. Judge·발송을 호출하지 않는다."""
    from app.collectors.crawler_feed import is_alive
    from app.health import HEARTBEAT_KEY, JOB_RUN_KEY, _dur, _kst, _next_runs
    from app.version import boot_info

    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    local = now.astimezone(KST)
    date_s = today_kst()
    info = boot_info()
    L = [
        f"📋 저녁 점검 {local:%Y-%m-%d %H:%M} KST",
        "",
        *contract_lines(),
        "",
        "지금 측정",
        f"{_mark(True)} 코드 {info.short} — {info.subject[:48]}",
    ]

    hb = await redis.get(HEARTBEAT_KEY) if redis else None
    L.append(f"{_mark(hb is not None)} 스케줄러 "
             + (f"하트비트 {_dur(_ago_safe(hb))}" if hb else "미실행"))

    runs = {}
    if redis:
        try:
            raw = await redis.hgetall(JOB_RUN_KEY)
            for k, v in (raw or {}).items():
                try:
                    runs[k] = json.loads(v)
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass
    nxt = await _next_runs()
    ap = runs.get("asia_pregame_5m") or {}
    n_ap = nxt.get("asia_pregame_5m")
    L.append(
        f"{_mark(bool(ap.get('at')))} asia_pregame_5m 마지막 {_kst(ap.get('at'))}"
        + (f" / 다음 {n_ap:%m-%d %H:%M}" if n_ap else "")
    )
    if n_ap is not None:
        nxt_local = n_ap.astimezone(KST) if n_ap.tzinfo else n_ap.replace(tzinfo=KST)
        same_day = nxt_local.date() == local.date() and nxt_local.hour in (17, 18)
        if local.hour < 19 and not same_day:
            L.append("   🔴 다음 실행이 오늘 17·18시가 아님 — 오늘 창을 놓친다")

    if redis:
        try:
            ok, msg = await is_alive(redis)
            L.append(f"{_mark(ok)} {msg}")
        except Exception as exc:
            L.append(f"⚪ 크롤러 확인 실패: {str(exc)[:60]}")

    sample = _npb_sample_start(now)
    L.append(
        f"{_mark(analysis_open('npb', sample, now))} NPB 분석창 "
        f"(18:00 표본) {'열림' if analysis_open('npb', sample, now) else '닫힘'}"
    )
    L.append(
        f"{_mark(in_send_window('npb', sample, now))} NPB 발송창 "
        f"(T-{SEND_OPEN_MIN['npb']}~시작) "
        f"{'열림' if in_send_window('npb', sample, now) else '닫힘'}"
    )
    L.append(f"   NPB 종료선 T-{NPB_FINISH_MIN} (18:00→17:45)")

    for sport, label in (("npb", "NPB"), ("kbo", "KBO")):
        judged = total = None
        if redis:
            raw = await redis.get(f"analysis:{sport}:{date_s}")
            ready = analysis_cache_ready(raw, date_s)
            if raw:
                try:
                    games = json.loads(raw).get("games") or []
                except (TypeError, ValueError):
                    games = []
                sched = [g for g in games if g.get("status") in (None, "scheduled")]
                total = len(sched)
                judged = sum(1 for g in sched
                             if isinstance(g.get("p_claude"), (int, float)))
                L.append(
                    f"{_mark(ready)} {label} 캐시 판정 {judged}/{total}"
                    + ("" if ready else " — 저녁에 슬레이트 파이프라인 안 돌림")
                )
            else:
                L.append(f"⚪ {label} 분석 캐시 없음")
        if pool is not None:
            try:
                rows = await pool.fetch(
                    """
                    SELECT id, sport, starts_at FROM games
                    WHERE sport = $1 AND status = 'scheduled'
                      AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2
                    """,
                    sport,
                    datetime.strptime(date_s, "%Y-%m-%d").date(),
                )
                n_sig = 0
                for r in rows:
                    if redis and await redis.get(card_sig_key(r["id"])):
                        n_sig += 1
                L.append(f"   {label} 발송시그 {n_sig}/{len(rows)}")
            except Exception as exc:
                L.append(f"   {label} 발송시그 조회 실패: {str(exc)[:40]}")

    L.append("")
    L.append("시간대 체크는 docs/PREGAME_CHECKLIST.md")
    return "\n".join(L)


def _ago_safe(iso: str | None):
    from app.health import _ago

    return _ago(iso)
