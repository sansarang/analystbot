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
        "계약",
        "· 일괄 17:45 덤프 없음. 경기마다 1차/변동. 빈 카드 없음",
        "· NPB 크롤·분석 T-15(18:00→17:45) 끝. 이후 재판정 없음",
        "· 17:30 1차 완료는 강제 아님",
    ]


def incident_lines() -> list[str]:
    """8/28 실측과 미실측을 숨기지 않는다. 상세는 docs/PREGAME_CHECKLIST.md."""
    return [
        "8/28 안 됨",
        "❌ 빈 카드(캐시 없어) — parlay odds=None → math.prod. 저녁 캐시 유실. 실카드 0",
        "❌ 17:45 일괄 덤프 + NX 키 — 변동 재발송 불가",
        "❌ 발송창 T-30에야 열림 — 1차를 T-30까지 못 끝냄",
        "❌ 6경기 직렬 Judge ~12분 (17:45→17:57)",
        "❌ 저녁 ensure_analysis_cache가 슬레이트 파이프라인 재실행",
        "❌ predicted→confirmed만으로 같은 타순 재판정",
        "❌ 세이부(gid523) 결장 건수로 라쿠텐 56% — 실경기는 세이부. 승패 미추천, Over 4.5",
        "❌ 배포 20:18 — asia_pregame 오늘 17·18시 창 놓침",
        "❌ /health prefetch_daily는 잡 이름 불일치(항상 기록 없음처럼 보임)",
        "❌ 의도 파싱 400 (빈 모델명). Groq/Gemini disabled. 리서치 0/15",
        "8/28 됨",
        "✅ KBO 전경기 취소 — 카드 안 냄",
        "✅ 14:00 prefetch_asia 텔레그램 없음",
        "✅ /health 커밋=배포 해시. 스케줄러·크롤러 기동. MLB 판정은 됨(자동발송 아님)",
        "코드 고침 · 저녁 창은 8/29 첫 실측",
        "🧪 parlay None은 조합만 포기 · p_claude 없는 캐시 미발송 · 취소 DB 반영",
        "🧪 경기 단위 1차/변동 · 카드시그 · 선발+타순만 시그 · NPB 먼저 병렬",
        "🧪 저녁 슬레이트 파이프라인 제거 · today_nine · NPBStopBefore=15 · 발송창 T-40",
        "보장 안 함",
        "⚠️ 17:30 1차 완료는 강제 아님. 강제선은 NPB 17:45",
        "⚠️ 17:45 이후 NPB 타순 변경은 버림. 캐시는 사용자 담당(저녁에 안 메움)",
        "⚠️ 타순이 17:43에 뜨면 Judge가 17:45를 넘길 수 있음",
        "⚠️ KBO 19시 이후는 5분 잡 밖(30분 폴링). pytest 2건 HEAD부터 실패(발송 무관)",
        "상세: docs/PREGAME_CHECKLIST.md",
    ]


def research_lines() -> list[str]:
    """돈·관중·승패 관련. 연구만. 코드 없음."""
    return [
        "연구 (미구현 · 딥서치 전제)",
        "📚 동기는 게임차가 아님. 상품은 관중(입장). 승패는 그 돈을 열거나 닫음",
        "📚 세 겹 섞지 말 것: 구단 장부 / 가을 흥행(KBO 5위 PS, NPB CS 홈) / 선수 자산",
        "📚 게이트: 매진팀(한화)은 오늘 패가 이번 주 표를 안 바꿈. 져도 차는 팀(롯데). 5위=추가 홈",
        "📚 관련 유무는 채점 원장만. λ·연봉 API 금지. 200~300픽 전 결론 금지",
        "⚠️ PPLX·Grok 꺼짐. KBO·NPB 딥서치 꺼짐. 켜진 뒤에만 코딩",
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
        *incident_lines(),
        "",
        *research_lines(),
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
