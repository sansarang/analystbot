"""[8번 2026-09-04] 재배포가 만드는 눈먼 구간을 없앤다.

🔴 실측 2026-09-04 (증거):
   · 15:21 스케줄러 기동 → `odds_snapshot_30m` 첫 실행은 15:51.
   · 그 사이 워치독이 `W-ODDS-STALE oddsportal` 을 66·71·76분으로 3회 발신.
   · 같은 시각 oddsportal 을 직접 호출: KBO 200/995KB(15경기) ·
     NPB 200/790KB(12경기) — **소스는 멀쩡했다.**
   · 15:51 실행 직후 `배당 스냅샷 최신 ... (0.3시간 전)` 로 나이가 되돌아왔다.
   → 원인은 소스도 파서도 아니고 **IntervalTrigger 의 첫 실행이 주기만큼
     뒤라는 것**이다. 배포가 잦은 날에는 이 잡이 한 번도 못 돈다.

같은 사고가 ENGINEERING.md §4 에 `[근거 134d37b]` (88분 굶음)로 이미 있다.
두 번 났으므로 리듬 규율만으로는 못 막는다 — 코드로 막는다.
"""
import pytest


def test_odds_snapshot_runs_at_boot():
    from app.scheduler import RUN_AT_BOOT

    assert "odds_snapshot_30m" in RUN_AT_BOOT


def test_boot_run_list_stays_cheap():
    """무거운 잡이 여기 들어오면 기동이 느려지고 17시대 폴링을 놓친다.

    프리페치·리허설·백필처럼 분 단위 작업은 넣지 않는다.
    """
    from app.scheduler import RUN_AT_BOOT

    for job_id in RUN_AT_BOOT:
        assert not any(bad in job_id for bad in
                       ("prefetch", "rehearsal", "backfill", "daily", "weekly",
                        "history", "finals", "statcast", "audition")), job_id
    assert len(RUN_AT_BOOT) <= 3, "기동 시 실행 잡이 늘어나면 기동이 느려진다"


def test_boot_run_jobs_are_real_registered_jobs():
    """🔴 사본 금지 — 여기 적은 이름이 실제 잡 id 와 어긋나면 조용히 무효가 된다."""
    from app.scheduler import RUN_AT_BOOT, _job_specs

    ids = {job_id for job_id, _, _ in _job_specs()}
    for job_id in RUN_AT_BOOT:
        assert job_id in ids, f"{job_id} 는 등록된 잡이 아니다"


def test_scheduler_schedules_boot_run_earlier_than_the_interval():
    """등록 결과로 확인한다 — 상수만 보면 실제로 앞당겨졌는지 알 수 없다.

    ⚠️ 아직 start() 하지 않은 스케줄러의 잡은 `next_run_time` 이 **없다**
       (APScheduler 가 start 시점에 계산한다). 명시적으로 넘긴 것만 값을
       갖는다 — 그래서 이 속성의 유무 자체가 "앞당겼는가"의 증거다.
    """
    from datetime import datetime, timedelta

    from app.scheduler import KST, RUN_AT_BOOT, build_scheduler

    sched = build_scheduler()
    now = datetime.now(KST)
    for job_id in RUN_AT_BOOT:
        job = sched.get_job(job_id)
        assert job is not None, job_id
        nrt = getattr(job, "next_run_time", None)
        assert nrt is not None, f"{job_id} 첫 실행이 지정되지 않았다"
        assert nrt < now + timedelta(minutes=5), (
            f"{job_id} 첫 실행이 {nrt} — 주기(30분)만큼 밀려 있다")


@pytest.mark.parametrize("job_id", ["watchdog_5m", "lineup_poll_30m",
                                    "research_retry_45m"])
def test_other_interval_jobs_keep_their_normal_first_run(job_id):
    """일괄 적용이 아니다 — 목록에 있는 잡만 앞당긴다."""
    from app.scheduler import build_scheduler

    sched = build_scheduler()
    job = sched.get_job(job_id)
    assert job is not None, job_id
    assert getattr(job, "next_run_time", None) is None, (
        f"{job_id} 가 기동 실행 대상이 아닌데 첫 실행이 지정됐다")
