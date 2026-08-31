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
                         "daily_summary_overseas"}
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
    seen: list[str] = []

    async def fake_ingest(pool, date, sport):
        seen.append(sport)

    import app.scheduler as sched

    monkeypatch.setattr(sched, "ingest_finals", fake_ingest)
    monkeypatch.setattr(sched, "get_pool", _fake_pool)
    await sched.finals_job()
    assert seen == ["mlb", "soccer", "kbo", "npb"]


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
    assert seen == ["mlb", "soccer", "kbo", "npb"]
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
