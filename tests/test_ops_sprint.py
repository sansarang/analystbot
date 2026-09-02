"""[운영 안정화 스프린트] 가동률 지표 · 워치독 · 사고 3건 재발 차단.

원칙: 판정 입력·프롬프트·게이트·임계값은 이 스프린트에서 한 글자도 안 바꾼다.
여기 있는 것은 전부 **"안 돌던 것을 돌게, 죽으면 알리게"** 다.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest


class FakeRedis:
    """해시·문자열·TTL만 흉내낸다. 실제 동작을 검증할 만큼만."""

    def __init__(self):
        self.h: dict = {}
        self.s: dict = {}
        self.fail = False

    async def hincrby(self, key, field, n=1):
        if self.fail:
            raise RuntimeError("redis down")
        self.h.setdefault(key, {})[field] = self.h.get(key, {}).get(field, 0) + n

    async def hgetall(self, key):
        return {k: str(v) for k, v in self.h.get(key, {}).items()}

    async def expire(self, *a, **k):
        return True

    async def get(self, key):
        return self.s.get(key)

    async def set(self, key, val, ex=None, nx=False):
        if nx and key in self.s:
            return False
        self.s[key] = str(val)
        return True

    async def incr(self, key):
        self.s[key] = str(int(self.s.get(key, 0)) + 1)
        return int(self.s[key])

    async def delete(self, *keys):
        for k in keys:
            self.s.pop(k, None)

    async def ping(self):
        if self.fail:
            raise RuntimeError("redis down")
        return True


# ─────────────────── 1. 가동률 지표 ───────────────────

def test_delivered_counts_unchanged_as_sent():
    """이미 보낸 카드에 변경이 없는 것은 **도달**이다 — 미발송이 아니다.

    이걸 실패로 세면 발송률이 영원히 100%가 안 되고, 목표가 무의미해진다.
    """
    from app.engine.dispatch_stats import record, summary

    r = FakeRedis()

    async def go():
        for outcome in ("sent", "sent", "revised", "unchanged"):
            await record(r, "kbo", "2026-09-02", outcome)
        return await summary(r, "kbo", "2026-09-02")

    st = asyncio.run(go())
    assert st["target"] == 4 and st["misses"] == {}
    from app.engine.dispatch_stats import delivered, rate

    assert delivered(st) == 4 and rate(st) == 1.0


def test_misses_carry_a_reason_for_every_one():
    """🔴 "조용한 0"은 결함이다 — 미발송은 전건에 사유가 붙는다."""
    from app.engine.dispatch_stats import record, summary

    r = FakeRedis()

    async def go():
        await record(r, "npb", "2026-09-02", "sent")
        await record(r, "npb", "2026-09-02", "cache_missing")
        await record(r, "npb", "2026-09-02", "unjudged")
        await record(r, "npb", "2026-09-02", "send_failed")
        return await summary(r, "npb", "2026-09-02")

    st = asyncio.run(go())
    assert st["target"] == 4
    assert st["misses"] == {"판정 캐시 없음": 1, "판정 없음": 1,
                            "텔레그램 발송 실패": 1}
    assert sum(st["misses"].values()) == st["target"] - 1, "전건에 사유"


def test_not_target_outcomes_leave_the_denominator():
    """창 전·이미 시작·취소는 대상이 아니다 — 분모에서 뺀다."""
    from app.engine.dispatch_stats import rate, record, summary

    r = FakeRedis()

    async def go():
        for o in ("window_not_open", "already_started", "void", "not_supported"):
            await record(r, "mlb", "2026-09-01", o)
        await record(r, "mlb", "2026-09-01", "sent")
        return await summary(r, "mlb", "2026-09-01")

    st = asyncio.run(go())
    assert st["target"] == 1 and rate(st) == 1.0


def test_rate_is_none_when_nothing_was_due():
    """대상이 0이면 발송률은 **없음**이다. 0%로 쓰면 없는 실패를 만든다."""
    from app.engine.dispatch_stats import rate, render

    assert rate({"target": 0}) is None
    assert render({"target": 0}, "KBO") == []


def test_record_failure_does_not_raise():
    """지표 기록이 발송을 막으면 안 된다."""
    from app.engine.dispatch_stats import record

    r = FakeRedis()
    r.fail = True
    asyncio.run(record(r, "kbo", "2026-09-02", "sent"))    # 예외 없이 지나가야 한다


# ─────────────────── 2. 워치독 ───────────────────

def test_llm_streak_alerts_only_at_threshold():
    """연속 3회부터 경보 — 일시적 1회 실패로 울리지 않는다."""
    from app.watchdog import LLM_FAIL_STREAK, check_llm, note_llm_failure

    r = FakeRedis()

    async def go(n):
        for _ in range(n):
            await note_llm_failure(r, "크레딧 소진")
        return await check_llm(r)

    assert asyncio.run(go(LLM_FAIL_STREAK - 1)) == []
    r2 = FakeRedis()

    async def go2():
        for _ in range(LLM_FAIL_STREAK):
            await note_llm_failure(r2, "크레딧 소진")
        return await check_llm(r2)

    found = asyncio.run(go2())
    assert found and found[0][0] == "W-LLM-FAIL"
    assert "크레딧 소진" in found[0][2]


def test_success_clears_the_streak():
    """성공하면 끊는다 — 안 끊으면 경보가 영원히 남는다."""
    from app.watchdog import check_llm, clear_llm_failures, note_llm_failure

    r = FakeRedis()

    async def go():
        for _ in range(5):
            await note_llm_failure(r, "x")
        await clear_llm_failures(r)
        return await check_llm(r)

    assert asyncio.run(go()) == []


def test_blocked_odds_suppresses_the_stale_alert(monkeypatch):
    """차단 중이면 stale 은 당연한 결과다 — 같은 고장을 두 번 울리지 않는다.

    ⚠️ 유료 경로가 켜져 있을 때만 차단을 본다. 무과금 전환 후 기본값에서는
       `theodds` 차단이 경보 대상이 아니다 — 끈 것을 고장이라 울리면 오탐이다.
    """
    from app import watchdog as wd
    from app.config import Settings

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, odds_provider="theodds"))

    async def fake_block(name):
        return {"at": "2026-08-30T01:00:00+00:00", "reason": "credit"}

    async def go():
        import app.api_guard as ag

        orig = ag.block_info
        ag.block_info = fake_block
        try:
            return await wd.check_odds(None, FakeRedis())
        finally:
            ag.block_info = orig

    found = asyncio.run(go())
    codes = [c for c, _, _ in found]
    assert codes == ["W-ODDS-BLOCKED"], "stale 은 함께 울리지 않는다"
    assert "TTL이 없어" in found[0][2]


def test_free_mode_does_not_alert_on_the_disabled_paid_key():
    """끈 것을 고장이라고 울리는 것이 오탐의 가장 흔한 원인이다."""
    from app import watchdog as wd

    async def fake_block(name):
        return {"at": "2026-08-27T22:46:28+00:00", "reason": "credit"}

    async def go():
        import app.api_guard as ag

        orig = ag.block_info
        ag.block_info = fake_block
        try:
            return await wd.check_odds(None, FakeRedis())   # 기본 = free
        finally:
            ag.block_info = orig

    assert asyncio.run(go()) == []


def test_stale_is_judged_per_provider():
    """ESPN 이 죽어도 배트맨이 살아 있으면 KBO 는 멀쩡하다 — 소스마다 따로 본다."""
    from app import watchdog as wd

    class FakePool:
        async def fetch(self, *a, **k):
            return [{"provider": "espn", "age": 999.0}]    # ESPN 이 낡았다

    found = asyncio.run(wd.check_odds(FakePool(), FakeRedis()))
    assert [(c, t) for c, t, _ in found] == [("W-ODDS-STALE", "espn")]


def test_store_down_is_detected_by_a_real_roundtrip():
    """연결 객체가 있는 것과 도는 것은 다르다 — 실제로 왕복시킨다."""
    from app.watchdog import check_store

    r = FakeRedis()
    r.fail = True
    found = asyncio.run(check_store(None, r))
    assert found and found[0][0] == "W-STORE-DOWN" and found[0][1] == "redis"


def test_job_late_uses_the_real_trigger(monkeypatch):
    """유예 안이면 조용하고, 넘기면 울린다 — 판단 기준은 **실제 트리거**다."""
    import json

    from apscheduler.triggers.interval import IntervalTrigger

    from app import watchdog as wd
    from app.health import JOB_RUN_KEY

    monkeypatch.setattr(wd, "_booted_recently", lambda now: False)
    monkeypatch.setattr("app.scheduler._JOB_TRIGGERS",
                        {"heartbeat_2m": IntervalTrigger(minutes=2)},
                        raising=False)
    r = FakeRedis()

    async def go(minutes_ago):
        at = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
        r.h[JOB_RUN_KEY] = {"heartbeat_2m": json.dumps({"at": at, "ok": True})}
        return await wd.check_jobs(r)

    assert asyncio.run(go(3)) == [], "유예 4분 안이면 정상"
    found = asyncio.run(go(60))
    assert found and found[0][:2] == ("W-JOB-LATE", "heartbeat_2m")


def test_never_run_job_is_not_late():
    """한 번도 안 돈 잡은 판단하지 않는다 — 기동 직후 오탐의 원천이다."""
    from app.watchdog import check_jobs

    assert asyncio.run(check_jobs(FakeRedis())) == []


def test_one_broken_check_does_not_blind_the_rest():
    """점검 하나가 죽어도 나머지는 돈다 — 워치독이 눈을 감으면 안 된다."""
    from app import watchdog as wd

    async def boom(*a, **k):
        raise RuntimeError("점검 폭발")

    r = FakeRedis()
    r.fail = True                      # store 점검은 실패를 '찾아낸다'
    orig = wd.check_jobs
    wd.check_jobs = boom
    try:
        found = asyncio.run(wd.run_checks(None, r))
    finally:
        wd.check_jobs = orig
    assert any(c == "W-STORE-DOWN" for c, _, _ in found)


def test_every_code_has_a_label():
    """경보 코드는 사람이 읽을 이름을 갖는다 — grep 도, 오탐 차단도 코드 단위다."""
    from app.alerts import WATCHDOG_CODES
    from app.watchdog import LLM_FAIL_KEY  # noqa: F401

    used = {"W-SEND-PENDING", "W-ODDS-STALE", "W-ODDS-BLOCKED", "W-LLM-FAIL",
            "W-STORE-DOWN", "W-JOB-LATE", "W-RESCUE-DEAD"}
    assert used <= set(WATCHDOG_CODES)


# ─────────────────── 3b. 구제 재시도 ───────────────────

def test_rescue_failure_retries_instead_of_locking_the_day():
    """🔴 실패가 20시간 잠그던 결함 — 이 함수가 막으려던 사고를 이 가드가 만들었다."""
    import app.pipeline as P

    r = FakeRedis()
    calls = {"n": 0}

    async def failing_pipeline(*a, **k):
        calls["n"] += 1
        raise RuntimeError("판정 실패")

    orig = P.run_pipeline
    P.run_pipeline = failing_pipeline
    try:
        for _ in range(3):
            r.s.pop("analysis:rescue:fail:kbo:2026-09-02:lock", None)  # 5분 경과 흉내
            asyncio.run(P.ensure_analysis_cache(None, r, "kbo", "2026-09-02"))
    finally:
        P.run_pipeline = orig
    assert calls["n"] == 3, f"3회까지 재시도해야 한다 (실제 {calls['n']})"
    # 4회째는 포기한다 — 무한 재시도로 크레딧을 태우지 않는다
    r.s.pop("analysis:rescue:fail:kbo:2026-09-02:lock", None)
    P.run_pipeline = failing_pipeline
    try:
        asyncio.run(P.ensure_analysis_cache(None, r, "kbo", "2026-09-02"))
    finally:
        P.run_pipeline = orig
    assert calls["n"] == 3, "상한을 넘으면 더 돌지 않는다"


def test_rescue_lock_holds_within_five_minutes():
    """5분 안에는 다시 돌지 않는다 — 5분 폴링마다 슬레이트를 재판정하면 안 된다."""
    import app.pipeline as P

    r = FakeRedis()
    calls = {"n": 0}

    async def failing(*a, **k):
        calls["n"] += 1
        raise RuntimeError("x")

    orig = P.run_pipeline
    P.run_pipeline = failing
    try:
        for _ in range(4):            # 잠금을 지우지 않는다 = 5분이 안 지났다
            asyncio.run(P.ensure_analysis_cache(None, r, "npb", "2026-09-02"))
    finally:
        P.run_pipeline = orig
    assert calls["n"] == 1


# ─────────────────── 3a. 침묵 금지 ───────────────────

def test_unavailable_card_says_why_and_is_not_a_pick():
    """판정을 못 냈으면 그 사실이라도 보낸다. **추천이 아니다.**"""
    from app.engine.pregame_push import compose_unavailable_card

    row = {"id": 1, "away": "NYY", "home": "LAA"}
    text = compose_unavailable_card(row, "mlb", "크레딧 소진", "09/03 11:38")
    assert "판정 불가" in text and "크레딧 소진" in text
    assert "분석 미완" in text
    for banned in ("%", "추천합니다", "★"):
        assert banned not in text, f"판정 불가 카드에 {banned} 가 있으면 안 된다"


def test_unavailable_card_is_sent_once_per_game():
    """같은 경기에 두 번 보내지 않는다 — 5분 폴링에서 도배가 된다."""
    from app.engine import pregame_push as pp

    r = FakeRedis()
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    orig = pp._send_card
    pp._send_card = fake_send
    try:
        row = {"id": 7, "away": "A", "home": "B",
               "starts_at": datetime.now(UTC) + timedelta(hours=1)}
        for _ in range(3):
            asyncio.run(pp.send_unavailable(r, row, "kbo", "크레딧 소진"))
    finally:
        pp._send_card = orig
    assert len(sent) == 1


def test_unavailable_reason_prefers_measured_cause():
    """사유는 아는 만큼만. 모르면 모른다고 쓴다 — 지어내지 않는다."""
    from app.engine.pregame_push import _unavailable_reason
    from app.watchdog import LLM_FAIL_KEY

    r = FakeRedis()
    assert "조사 중" in asyncio.run(_unavailable_reason(r))
    r.s[LLM_FAIL_KEY] = "4"
    r.s[f"{LLM_FAIL_KEY}:last"] = "matchup: 크레딧 소진"
    got = asyncio.run(_unavailable_reason(r))
    assert "연속 4회" in got and "크레딧 소진" in got


# ─────────────────── 스프린트 경계 ───────────────────

def test_judgement_design_was_not_touched():
    """🔴 이 스프린트는 **가동만** 고친다. 판정 설계는 동결이다."""
    from app.engine.matchup import clip_p_home
    from app.engine.prompts import MATCHUP

    assert "p_home은 0.32~0.68 범위를 벗어나지 않는다" in MATCHUP
    assert "확률을 최대 ±3%p까지만 조정" in MATCHUP
    assert "{{BOXSCORE_JSON}}" in MATCHUP and "{{LINEUP_SEASON_JSON}}" in MATCHUP
    assert clip_p_home(0.99) == pytest.approx(0.68)
    assert clip_p_home(0.01) == pytest.approx(0.32)


def test_watchdog_only_reads_never_unblocks():
    """차단 자동 해제 금지 — 잔액 없는 키로 계속 호출하면 요금만 태운다."""
    from pathlib import Path

    src = Path("app/watchdog.py").read_text(encoding="utf-8")
    assert "clear_block" not in src, "워치독은 차단을 풀지 않는다"
    assert "trip_credit" not in src, "워치독은 차단을 걸지도 않는다"


# ─────────────────── 0. 잔여 결함 ───────────────────

def test_mlb_cache_ready_uses_eastern_slate_date():
    """🔴 MLB 슬레이트 날짜는 미 동부 기준이다. KST 문자열과 대조하면 언제나 False.

    실측 2026-09-02: 15경기 전부 `p_claude` 가 있는데
      analysis_cache_ready(raw, "2026-09-01")        → False   ← ET 슬레이트
      analysis_cache_ready(raw, "2026-09-02")        → True    ← KST 날짜
    그래서 MLB 는 폴링마다 "캐시 없음"으로 읽혀 헛구제를 돌리고 하루치
    구제 토큰을 태웠다.
    """
    import json

    from app.pipeline import analysis_cache_ready

    raw = json.dumps({"games": [
        {"status": "scheduled", "starts_at": "2026-09-02T11:40:00+00:00",
         "starts_at_kst": "09/02 20:40", "p_claude": 0.55}]})
    # ET 로 2026-09-02 07:40 → 슬레이트 날짜는 09-02
    assert analysis_cache_ready(raw, "2026-09-02", "mlb") is True
    assert analysis_cache_ready(raw, "2026-09-01", "mlb") is False
    # 종전 경로(종목 미지정)는 KST 문자열을 본다 — 아시아 종목은 그대로다
    assert analysis_cache_ready(raw, "2026-09-02") is True


def test_mlb_late_night_game_belongs_to_previous_et_date():
    """KST 아침 경기는 **전날** ET 슬레이트다 — 이 구분이 버그의 핵심이었다."""
    import json

    from app.pipeline import analysis_cache_ready

    # 2026-09-02 02:40Z = ET 2026-09-01 22:40 = KST 09/02 11:40
    raw = json.dumps({"games": [
        {"status": "scheduled", "starts_at": "2026-09-02T02:40:00+00:00",
         "starts_at_kst": "09/02 11:40", "p_claude": 0.6}]})
    assert analysis_cache_ready(raw, "2026-09-01", "mlb") is True
    assert analysis_cache_ready(raw, "2026-09-02", "mlb") is False


def test_et_date_never_invents_a_value():
    """시각을 못 읽으면 빈 문자열 — 지어내지 않는다."""
    from app.pipeline import _et_date_of

    assert _et_date_of({}) == ""
    assert _et_date_of({"starts_at": "쓰레기"}) == ""


def test_lineup_repair_only_fixes_exact_nine():
    """9명이 정확히 될 때만 교정한다. 억지로 만들지 않는다."""
    from tools.repair_lineups import repair_order

    known = {"Ha-Seong Kim", "Pete Crow-Armstrong"}
    broken = ["Drake Baldwin", "Ozzie Albies", "Matt Olson", "Ronald Acuña Jr.",
              "Michael Harris II", "Mauricio Dubón", "Mike Yastrzemski",
              "Sean Murphy", "Ha", "Seong Kim"]
    fixed = repair_order(broken, known)
    assert fixed is not None and len(fixed) == 9 and fixed[-1] == "Ha-Seong Kim"
    # 빈 배열·부분 라인업은 복원 불가 → None (호출부가 contaminated 로 표시한다)
    assert repair_order([], known) is None
    assert repair_order(["김도영(3루수)", "박찬호(유격수)"], known) is None
    # 이미 9명이면 손대지 않는다
    assert repair_order(["a"] * 9, known) is None


def test_contaminated_rows_are_excluded_from_judgement_paths():
    """오염 행이 라인업 의도·T5 로 흘러가면 안 된다 — 쿼리가 막는다."""
    from pathlib import Path

    for path in ("app/collectors/lineup_history.py", "app/engine/lineup_record.py",
                 "app/engine/pitcher_matchup.py"):
        src = Path(path).read_text(encoding="utf-8")
        assert "contaminated" in src, f"{path} 가 오염 행을 거르지 않는다"


def test_npb_rejudge_window_is_wider_than_full_analysis():
    """[0c] npb-window 병합 확인 — 풀 분석 T-15, 경량 재판정 T-10."""
    from app.engine.pregame_push import (
        NPB_FINISH_MIN, NPB_REJUDGE_FINISH_MIN, analysis_open, rejudge_open,
    )

    assert NPB_REJUDGE_FINISH_MIN < NPB_FINISH_MIN
    now = datetime.now(UTC)
    at_t12 = now + timedelta(minutes=12)          # T-12: 풀 닫힘, 경량 열림
    assert analysis_open("npb", at_t12, now) is False
    assert rejudge_open("npb", at_t12, now) is True
    at_t8 = now + timedelta(minutes=8)            # T-8: 둘 다 닫힘
    assert rejudge_open("npb", at_t8, now) is False
    # KBO 는 이원화 대상이 아니다
    assert rejudge_open("kbo", at_t8, now) is True


def test_npb_two_minute_job_shares_the_same_window_gate():
    """[0c] NPB 2분 잡은 창 게이트를 공유한다 — 시각을 코드에 다시 박지 않는다."""
    from apscheduler.triggers.interval import IntervalTrigger

    import app.scheduler as sc

    specs = {x[0]: x for x in sc._job_specs()}
    assert "npb_pregame_2m" in specs and "asia_pregame_5m" in specs
    assert isinstance(specs["npb_pregame_2m"][2], IntervalTrigger)
    assert isinstance(specs["asia_pregame_5m"][2], IntervalTrigger)


# ─────────────────── 오탐 정리 (2026-09-02 실경보) ───────────────────

def test_cron_windowed_job_is_not_late_outside_its_window(monkeypatch):
    """🔴 실사고 2026-09-02 12:40: `mlb_pregame_5m` 은 `CronTrigger(hour="5-11")`
    이다. 12:40 KST 에 "마지막 실행 46분 전"은 **정상**인데 5분 인터벌로
    가정해 울렸다. 주기를 손으로 적으면 트리거와 어긋난다.
    """
    import json

    from apscheduler.triggers.cron import CronTrigger

    from app import watchdog as wd
    from app.health import JOB_RUN_KEY

    monkeypatch.setattr(wd, "_booted_recently", lambda now: False)
    monkeypatch.setattr(
        "app.scheduler._JOB_TRIGGERS",
        {"mlb_pregame_5m": CronTrigger(hour="5-11", minute="*/5", timezone=wd.KST)},
        raising=False)
    r = FakeRedis()
    # 마지막 실행 11:55 KST, 지금 12:40 KST → 다음 예정은 **내일 05:00** 이다
    last = datetime(2026, 9, 2, 2, 55, tzinfo=UTC)      # 11:55 KST
    r.h[JOB_RUN_KEY] = {"mlb_pregame_5m": json.dumps({"at": last.isoformat(),
                                                      "ok": True})}
    assert asyncio.run(wd.check_jobs(r)) == [], "창 밖인데 울리면 오탐이다"


def test_interval_job_still_alerts_when_genuinely_stuck(monkeypatch):
    """오탐을 없애느라 진짜 고장을 놓치면 안 된다."""
    import json

    from apscheduler.triggers.interval import IntervalTrigger

    from app import watchdog as wd
    from app.health import JOB_RUN_KEY

    monkeypatch.setattr(wd, "_booted_recently", lambda now: False)
    monkeypatch.setattr("app.scheduler._JOB_TRIGGERS",
                        {"heartbeat_2m": IntervalTrigger(minutes=2)},
                        raising=False)
    r = FakeRedis()
    stale = datetime.now(UTC) - timedelta(hours=3)
    r.h[JOB_RUN_KEY] = {"heartbeat_2m": json.dumps({"at": stale.isoformat(),
                                                    "ok": True})}
    found = asyncio.run(wd.check_jobs(r))
    assert found and found[0][:2] == ("W-JOB-LATE", "heartbeat_2m")


def test_restart_grace_suppresses_the_first_hour(monkeypatch):
    """🔴 실사고 2026-09-02 13:05: 재기동 직후 `research_retry_45m` 이 울렸다.

    APScheduler 인메모리 잡스토어는 기동 시 초기화돼 첫 실행이 한 주기 뒤다.
    Redis 의 재기동 전 기록과 비교하면 언제나 "늦음"으로 보인다.
    """
    from app import watchdog as wd

    monkeypatch.setattr(wd, "_booted_recently", lambda now: True)
    assert asyncio.run(wd.check_jobs(FakeRedis())) == []


def test_unimplemented_source_is_not_watched():
    """🔴 실사고 2026-09-02 13:38: 배트맨은 수집기가 아직 없는데 감시 목록에
    있어 15분마다 영원히 울렸다. 사실이지만 **고장이 아니다.**"""
    from app.watchdog import ACTIVE_PROVIDERS

    assert "betman" not in ACTIVE_PROVIDERS
    assert "sharp" not in ACTIVE_PROVIDERS, "키 없으면 비활성 — 감시 대상 아님"
    assert "espn" in ACTIVE_PROVIDERS
