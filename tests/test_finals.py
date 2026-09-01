"""종료 점수 적재 잡 + 스케줄러 등록.

픽 채점기(grade_yesterday)는 없다 — 성적표를 판정에 되먹이는 회로였고 삭제됐다.
v1.1 0단계의 픽 레저·캘리브레이션은 그것과 다르다: 기록·집계만 하고 판정 경로가
읽지 않는다. 그 비개입은 tests/test_pick_ledger.py가 코드로 잠근다.
"""

import pytest

from app.scheduler import build_scheduler


def test_scheduler_jobs_registered():
    scheduler = build_scheduler()
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {"prefetch_evening", "prefetch_dawn", "prefetch_asia",
                         "odds_snapshot_30m", "ingest_finals_13h",
                         "elo_refresh_weekly", "research_retry_45m", "lineup_poll_30m",
                         "statcast_daily", "soccerdata_daily", "park_weekly",
                         "kbo_lineup_history", "npb_lineup_history",
                         "mlb_lineup_history",
                         "asia_pregame_5m", "mlb_pregame_5m",
                         "heartbeat_2m",
                         # [v1.1 0단계] 주간 캘리브레이션 리포트. **측정 전용**이다 —
                         #   삭제된 픽 채점기(grade_yesterday)의 부활이 아니다.
                         #   그쪽은 성적표를 판정에 되먹였고, 이쪽은 판정 경로가
                         #   읽지 않는다 (test_pick_ledger가 코드로 잠근다).
                         "calibration_weekly",
                         # [축구 시범 운영 + 일일 요약] 2026-08-31 조기 도입
                         "soccer_trial_10m", "daily_summary_asia",
                         "daily_summary_overseas", "daily_summary_soccer"}
    assert "grade_yesterday" not in jobs
    assert str(jobs["calibration_weekly"].trigger) == \
        "cron[day_of_week='sun', hour='23', minute='30']"
    # [계약 갱신 2026-09-01] 시각 고정 Cron → 5분 Interval + 경기 시각 창 게이트.
    #   종전 hour="17,18" 은 주말 낮경기(14:00·17:00)·더블헤더·우천 순연을
    #   통째로 놓쳤다. 창은 이제 `asia_poll_window` 가 DB 경기 시각으로 연다.
    trig = str(jobs["asia_pregame_5m"].trigger)
    assert "interval" in trig and "0:05:00" in trig
    mlb_trig = str(jobs["mlb_pregame_5m"].trigger)
    assert "5" in mlb_trig and "11" in mlb_trig
    assert "0:02:00" in str(jobs["heartbeat_2m"].trigger)
    assert "day_of_week='mon'" in str(jobs["elo_refresh_weekly"].trigger)
    assert str(jobs["prefetch_evening"].trigger) == "cron[hour='21', minute='0']"
    assert str(jobs["prefetch_dawn"].trigger) == "cron[hour='4', minute='30']"
    assert str(jobs["prefetch_asia"].trigger) == "cron[hour='14', minute='0']"
    assert str(jobs["ingest_finals_13h"].trigger) == "cron[hour='13', minute='0']"
    assert "0:30:00" in str(jobs["odds_snapshot_30m"].trigger)


async def _fake_pool():
    return None


@pytest.mark.asyncio
async def test_finals_job_covers_all_sports(monkeypatch):
    """4종목 전부 적재하되, **축구는 어제·오늘 두 날짜를 훑는다.**

    유럽 킥오프는 KST 새벽이라 오늘 01:30~05:00에 끝난 경기가 "어제"에
    잡히지 않는다(실측 2026-08-31: KST 09/01 새벽 7경기가 통째로 빠졌다).
    """
    seen: list[tuple[str, str]] = []

    async def fake_ingest(pool, date, sport):
        seen.append((sport, date))

    import app.scheduler as sched

    monkeypatch.setattr(sched, "ingest_finals", fake_ingest)
    monkeypatch.setattr(sched, "get_pool", _fake_pool)
    await sched.finals_job()
    assert [s for s, _ in seen] == ["mlb", "soccer", "soccer", "kbo", "npb"]
    soccer_dates = [d for s, d in seen if s == "soccer"]
    assert len(set(soccer_dates)) == 2, \
        f"축구가 같은 날짜를 두 번 훑었다: {soccer_dates}"


@pytest.mark.asyncio
async def test_finals_job_continues_after_one_sport_fails(monkeypatch):
    seen: list[str] = []

    async def fake_ingest(pool, date, sport):
        seen.append(sport)
        if sport == "mlb":
            raise RuntimeError("statsapi 다운")

    import app.scheduler as sched

    monkeypatch.setattr(sched, "ingest_finals", fake_ingest)
    monkeypatch.setattr(sched, "get_pool", _fake_pool)
    out = await sched.finals_job()
    assert seen == ["mlb", "soccer", "soccer", "kbo", "npb"]
    assert "soccer" in out and "kbo" in out and "mlb" not in out


def test_jobs_survive_missed_run_window():
    scheduler = build_scheduler()
    for job in scheduler.get_jobs():
        assert job.misfire_grace_time and job.misfire_grace_time >= 60, job.id
        assert job.coalesce is True, f"{job.id}: 밀린 실행이 쌓이면 안 된다"
        assert job.max_instances == 1, f"{job.id}: 동시 실행 금지"
    pf = {j.id: j for j in scheduler.get_jobs()}["prefetch_dawn"]
    assert pf.misfire_grace_time >= 3600, "일 1회 잡은 넉넉한 유예가 필요하다"


def test_grader_module_is_gone():
    import importlib.util

    assert importlib.util.find_spec("app.grader") is None


async def test_performance_button_does_not_grade():
    from app.bot.main import render_performance

    out = await render_performance(None)
    assert "적중" in out
    assert "채점" in out


def test_npb_backfill_does_not_lose_appearances_when_lineup_fails():
    """🔴 타순(`/top`)과 등판(`/stats`)은 서로 다른 페이지인데, 종전에는
    타순 파싱이 실패하면 `continue` 로 빠져나가 **등판까지 함께 버렸다.**

    실측 2026-09-01: NPB 등판 858행(선발 204)으로 KBO 1,860행(선발 371)의
    절반. 최근 7일 선발의 32.6%가 "표본 ≤1"로 추천 자격을 잃었다
    (KBO 0% · MLB 14.4%).
    """
    from pathlib import Path

    src = Path("app/collectors/npb_boxscore.py").read_text(encoding="utf-8")
    body = src[src.index("async def backfill"):]
    i_app = body.index("record_appearances(")
    i_guard = body.index("if not lu:")
    assert i_app < i_guard, "타순 실패 가드보다 등판 적재가 뒤에 있다 — 또 버린다"
    assert "rescued_app" in body, "회수 건수를 세지 않으면 효과를 알 수 없다"


def test_cycle_report_only_fires_when_something_happened():
    """🔴 5분 폴링에 매번 보내면 하루 100건이 넘는다 — 2026-08-27 폭주 재발.
    판정·발송·오류가 없는 빈 틱은 조용히 지나가야 한다."""
    import asyncio
    from pathlib import Path

    from app.scheduler import report_cycle

    calls = []

    async def rep(*a, **k):
        calls.append(("report", a))
        return True

    async def errs(*a, **k):
        calls.append(("errors", a))
        return True

    empty = {"rejudged": 0, "sent": 0, "revised": 0, "failed": 0}
    asyncio.run(report_cycle(None, "테스트", [], [], empty, 1.0, rep, errs))
    assert calls == [], "빈 틱에서 알림이 나갔다"

    moved = {"rejudged": 2, "sent": 2, "revised": 0, "failed": 0}
    asyncio.run(report_cycle(None, "테스트", [], [], moved, 1.0, rep, errs))
    assert [c[0] for c in calls] == ["report"], "판정이 있었는데 리포트가 없다"

    calls.clear()
    asyncio.run(report_cycle(None, "테스트", [], [{"what": "x"}], empty, 1.0,
                             rep, errs))
    assert [c[0] for c in calls] == ["report", "errors"], "오류만 있을 때도 알려야 한다"

    src = Path("app/alerts.py").read_text(encoding="utf-8")
    assert "async def cycle_errors" in src
    assert "our_frames(exc, limit=2)" in src, "파일:라인이 없으면 전달해도 못 찾는다"


def test_asia_poll_sends_provisional_card_before_lineup():
    """🔴 실측 2026-09-01 17:25: KBO 5경기 판정이 14:00에 끝나 레저에 있는데도
    카드가 한 장도 안 나갔다. `crawler_lineup_poll` 이 타순 없는 경기를
    `continue` 로 버려 재판정도 발송도 없었기 때문이다.

    MLB 폴링은 이미 라인업과 무관하게 전 경기 발송을 시도한다 —
    KBO·NPB 만 예외였다. 일치시킨다.

    ⚠️ 추천으로 새지 않는다: qualifies() 가 확정 라인업을 하드 요건으로
       요구하므로 잠정 카드는 보드만으로 나간다.
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def crawler_lineup_poll"):]
    guard = body.index("if not have:")
    tail = body[guard:guard + 900]
    assert "catchup.append(dict(r))" in tail, \
        "타순 없는 경기가 여전히 발송 경로에서 빠진다"
    # 확정 요건은 그대로여야 한다 — 잠정이 추천으로 새면 안 된다
    from app.pipeline import qualifies

    assert qualifies({"sport": "kbo", "p": 0.70, "pick_state": "preliminary"}) is False
    assert qualifies({"sport": "kbo", "p": 0.70, "pick_state": "final"}) is True


def test_ensure_analysis_cache_is_actually_called():
    """🔴 실측 2026-09-01: `ensure_analysis_cache` 는 만들어져 있었지만
    **부르는 곳이 하나도 없었다**(호출처 3곳이 전부 주석·docstring).
    그래서 그 함수의 docstring 이 예언한 그대로 NPB 6경기가 죽었다:
      "npb 캐시 없음 — 슬레이트 파이프라인 생략" × 6 → 카드 0장
    MLB 도 같은 구멍이었다(rejudge_after_lineup 이 캐시 없으면 return False).
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    # 주석이 아닌 실제 호출이 KBO·NPB 경로와 MLB 경로 양쪽에 있어야 한다
    calls = [ln for ln in src.splitlines()
             if "await ensure_analysis_cache(" in ln and not ln.strip().startswith("#")]
    assert len(calls) >= 2, f"실제 호출 {len(calls)}곳 — 두 폴링 경로 모두 필요"


def test_rescue_runs_at_most_once_per_day():
    """⚠️ 5분 폴링마다 슬레이트를 다시 돌면 Sonnet 6~15콜 × 하루 100틱이다."""
    from pathlib import Path

    from app.pipeline import _RESCUE_KEY, _RESCUE_TTL

    assert "{sport}" in _RESCUE_KEY and "{date}" in _RESCUE_KEY
    assert _RESCUE_TTL >= 12 * 3600
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    body = src[src.index("async def ensure_analysis_cache"):]
    assert "nx=True" in body[:2000], "중복 구제를 막는 nx 가드가 없다"


def test_cycle_report_lists_every_sport_it_polled():
    """🔴 실측 2026-09-01 17:35 리포트: "NPB 대상 6경기"만 적고 발송 5건(KBO)을
    그 아래 붙여, 종목이 뒤바뀌어 읽혔다. `if jobs:` 라 타순변동이 없는 종목은
    줄이 통째로 빠졌다."""
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def crawler_lineup_poll"):]
    i = body.index('rep.append(f"  {sport.upper()} 대상')
    assert "if rows:" in body[max(0, i - 400):i], "종목 줄이 여전히 jobs 조건에 묶여 있다"


def _asia_window(lo_h, hi_h, now_h, now_m=0):
    """창 게이트 헬퍼 — KST 시각(시)로 lo/hi/now 를 만들어 판정."""
    import asyncio
    from datetime import UTC, datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.scheduler import asia_poll_window

    KST = ZoneInfo("Asia/Seoul")
    day = datetime(2026, 9, 1, tzinfo=KST)

    class _Pool:
        async def fetchrow(self, *_a, **_k):
            if lo_h is None:
                return {"lo": None, "hi": None}
            return {"lo": day.replace(hour=lo_h).astimezone(UTC),
                    "hi": day.replace(hour=hi_h).astimezone(UTC)}

    now = day.replace(hour=now_h, minute=now_m).astimezone(UTC)
    return asyncio.run(asia_poll_window(_Pool(), now))


def test_asia_window_opens_for_weekend_afternoon_games():
    """🔴 종전 CronTrigger(hour="17,18") 는 시각을 코드에 박아 주말 낮경기
    (14:00·17:00)·더블헤더·우천 순연을 통째로 놓쳤다. 이제 경기 시각으로 연다.

    창 = [첫 경기 − (SEND_OPEN_MIN["kbo"]=70 + 20)분, 막 경기 시작]
    14:00 첫 경기면 12:30 부터 열린다.
    """
    assert _asia_window(14, 17, 13)[0] is True, "주말 14:00 경기인데 13시가 닫혔다"
    assert _asia_window(14, 17, 12, 40)[0] is True          # 12:40 = 창 안
    assert _asia_window(14, 17, 12, 0)[0] is False          # 12:00 = T-120, 아직
    assert _asia_window(14, 17, 18)[0] is False             # 막 경기 시작 뒤


def test_asia_window_still_covers_weekday_evening():
    """회귀 — 평일 KBO 18:30 · NPB 18:00 은 종전과 같이 열려 있어야 한다."""
    assert _asia_window(18, 18, 17)[0] is True              # 17:00
    assert _asia_window(18, 18, 18)[0] is True              # 18:00 (막 경기 시작)
    assert _asia_window(18, 18, 16, 50)[0] is True          # 16:50 = 첫경기-70-20
    assert _asia_window(18, 18, 16, 0)[0] is False          # 16:00 = 아직 이르다


def test_asia_window_closes_on_no_games_without_weekday_branch():
    """월요일(KBO 휴식일)·우천 전면 취소는 **요일 분기 없이** 닫힌다."""
    open_, why = _asia_window(None, None, 17)
    assert open_ is False and "경기 없음" in why
    from pathlib import Path
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def asia_poll_window"):]
    body = body[:body.index("async def report_cycle")]
    # 요일로 분기하는 코드가 없어야 한다 (주석의 "요일 분기를 넣지 않는다"는 제외)
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.strip().startswith("#") and '"""' not in ln)
    assert "weekday" not in code and "isoweekday" not in code


def test_asia_job_is_interval_not_cron():
    from apscheduler.triggers.interval import IntervalTrigger

    from app.scheduler import _job_specs

    trig = {j: tr for j, _f, tr in _job_specs()}["asia_pregame_5m"]
    assert isinstance(trig, IntervalTrigger), "여전히 시각 고정 Cron 이다"


def test_matchup_failure_reverts_lineup_for_retry():
    """🔴 실사고 2026-09-02 06:40: Anthropic 잔액 소진으로 game 1855·1856·1857
    의 매치업이 전부 실패했는데 `rejudge_after_lineup` 은 ok=True 를 돌려줬다.

    `refresh_mlb_lineup` 이 판정 성패와 무관하게 games 를 먼저 confirmed 로
    UPDATE 하고, 다음 폴링은 `lineup_status != "confirmed"` 로 거른다.
    그래서 판정만 실패한 경기는 **다시는 조회되지 않는다** — 06:55 폴링이
    "3경기 확인 · 변경 0건" 으로 지나갔고, 충전·재시작 뒤에도 스스로
    돌아오지 못했다. 라인업은 반영됐는데 승률은 실패 직전 값으로 굳는다.
    """
    import asyncio
    from pathlib import Path

    from app.pipeline import _revert_lineup_for_retry

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    body = src[src.index("async def rejudge_after_lineup"):]
    i_fail = body.index("라인업 매치업 실패")
    assert "_revert_lineup_for_retry" in body[i_fail:i_fail + 1200], \
        "매치업 실패 후 재시도 자격을 복원하지 않는다"

    # 되돌리기가 실패해도 흐름을 막지 않는다
    jg = {"game_id": None}
    asyncio.run(_revert_lineup_for_retry(jg, Exception("x")))   # game_id 없음 → 조용히 종료

    calls = []

    class _Pool:
        async def execute(self, sql, *a):
            calls.append((sql, a))

    async def _run():
        import app.db as db
        orig = db.get_pool

        async def fake_pool():
            return _Pool()

        db.get_pool = fake_pool
        try:
            jg2 = {"game_id": 1855, "lineup_status": "confirmed"}
            await _revert_lineup_for_retry(jg2, Exception("잔액 소진"))
            return jg2
        finally:
            db.get_pool = orig

    jg2 = asyncio.run(_run())
    assert jg2["lineup_status"] == "predicted"
    assert calls and "lineup_status = 'predicted'" in calls[0][0]
    assert "lineup_status = 'confirmed'" in calls[0][0], \
        "이미 confirmed 인 행만 되돌려야 한다"
    assert calls[0][1] == (1855,)
