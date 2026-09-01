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
    trig = str(jobs["asia_pregame_5m"].trigger)
    assert "17" in trig and "18" in trig
    assert "45" in trig
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
