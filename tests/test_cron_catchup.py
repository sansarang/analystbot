"""[구멍 E] 재기동이 오늘치 cron 발화를 삼킨다.

🔴 실사고 2026-09-03: 14:00 `prefetch_asia` 가 14:03 배포로 사라졌다.
   KBO·NPB 분석 캐시가 없어 저녁에 구제 파이프라인이 대신 돌았고
   (NPB 17:26 · KBO 18:05), KBO 카드가 T-30 을 넘겼다.

   `misfire_grace_time` 은 **살아 있던** 프로세스가 늦게 도는 것을 구제한다.
   죽어 있던 시간은 구제하지 못한다 — in-memory jobstore 는 재기동하면
   잡을 새로 달고, 오늘 발화 시각이 지났으면 다음은 내일이다.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import app.scheduler as S

KST = ZoneInfo("Asia/Seoul")
SRC = Path("app/scheduler.py").read_text(encoding="utf-8")


def test_last_fire_before_finds_todays_firing():
    trig = CronTrigger(hour=14, minute=0, timezone=KST)
    now = datetime(2026, 9, 3, 17, 30, tzinfo=KST)
    prev = S._last_fire_before(trig, now)
    assert prev is not None
    assert prev.astimezone(KST).hour == 14 and prev.astimezone(KST).day == 3


def test_outside_the_grace_window_is_ignored():
    """유예 창 밖이면 따라잡지 않는다 — 창은 `MISFIRE_GRACE_SEC` 이 원본이다."""
    trig = CronTrigger(hour=4, minute=0, timezone=KST)
    now = datetime(2026, 9, 3, 23, 0, tzinfo=KST)     # 19시간 전 발화
    assert S._last_fire_before(trig, now) is None


def test_window_reads_the_existing_constant():
    seg = SRC[SRC.index("def _last_fire_before"):]
    seg = seg[:seg.index("\nasync def ", 10)]
    assert "MISFIRE_GRACE_SEC" in seg, "유예 창 숫자를 새로 적었다(사본 금지)"


class _R:
    def __init__(self, runs):
        self.runs = runs


@pytest.mark.asyncio
async def test_missed_cron_is_fired_once(monkeypatch):
    """🔴 오늘의 사고 그대로 — 14:00 이 지났는데 실행 기록이 없다."""
    called = []

    async def fake_job():
        called.append("prefetch_asia")

    trig = CronTrigger(hour=14, minute=0, timezone=KST)
    monkeypatch.setattr(S, "_JOB_TRIGGERS", {"prefetch_asia": trig})
    monkeypatch.setattr(S, "_job_specs", lambda: [("prefetch_asia", fake_job, trig)])
    monkeypatch.setattr("app.health._job_runs", _no_runs)
    monkeypatch.setattr(S, "datetime", _FixedNow(datetime(2026, 9, 3, 17, 0, tzinfo=KST)))

    fired = await S._catchup_missed_crons(_R({}))
    assert fired == ["prefetch_asia"] and called == ["prefetch_asia"]


@pytest.mark.asyncio
async def test_already_run_today_is_skipped(monkeypatch):
    """실행 기록이 원본이다 — 이미 돌았으면 또 돌지 않는다."""
    called = []

    async def fake_job():
        called.append(1)

    trig = CronTrigger(hour=14, minute=0, timezone=KST)
    ran = datetime(2026, 9, 3, 14, 0, tzinfo=KST).astimezone(UTC).isoformat()

    async def runs(_r):
        return {"prefetch_asia": {"at": ran}}

    monkeypatch.setattr(S, "_JOB_TRIGGERS", {"prefetch_asia": trig})
    monkeypatch.setattr(S, "_job_specs", lambda: [("prefetch_asia", fake_job, trig)])
    monkeypatch.setattr("app.health._job_runs", runs)
    monkeypatch.setattr(S, "datetime", _FixedNow(datetime(2026, 9, 3, 17, 0, tzinfo=KST)))

    assert await S._catchup_missed_crons(_R({})) == [] and called == []


@pytest.mark.asyncio
async def test_interval_jobs_are_not_caught_up(monkeypatch):
    """인터벌 잡은 대상이 아니다 — 스스로 곧 돈다."""
    called = []

    async def fake_job():
        called.append(1)

    trig = IntervalTrigger(minutes=30)
    monkeypatch.setattr(S, "_JOB_TRIGGERS", {"odds_snapshot_30m": trig})
    monkeypatch.setattr(S, "_job_specs", lambda: [("odds_snapshot_30m", fake_job, trig)])
    monkeypatch.setattr("app.health._job_runs", _no_runs)
    assert await S._catchup_missed_crons(_R({})) == [] and called == []


@pytest.mark.asyncio
async def test_job_failure_does_not_stop_the_rest(monkeypatch):
    ok = []

    async def bad():
        raise RuntimeError("boom")

    async def good():
        ok.append(1)

    t = CronTrigger(hour=14, minute=0, timezone=KST)
    monkeypatch.setattr(S, "_JOB_TRIGGERS", {"a": t, "b": t})
    monkeypatch.setattr(S, "_job_specs", lambda: [("a", bad, t), ("b", good, t)])
    monkeypatch.setattr("app.health._job_runs", _no_runs)
    monkeypatch.setattr(S, "datetime", _FixedNow(datetime(2026, 9, 3, 17, 0, tzinfo=KST)))
    assert await S._catchup_missed_crons(_R({})) == ["b"] and ok == [1]


def test_catchup_runs_after_scheduler_start_and_in_background():
    """🔴 기동 경로에서 await 하면 17시대 라인업 폴을 놓친다."""
    start = SRC.index("scheduler.start()")
    call = SRC.index("asyncio.create_task(_catchup())")
    assert start < call, "_JOB_TRIGGERS 가 채워지기 전에 부른다"
    assert "await _catchup_missed_crons(r)" in SRC


async def _no_runs(_r):
    return {}


class _FixedNow:
    def __init__(self, when):
        self._when = when

    def __getattr__(self, k):
        import datetime as _d

        return getattr(_d.datetime, k)

    def now(self, tz=None):
        return self._when
