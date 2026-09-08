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


def test_other_interval_jobs_keep_their_normal_first_run():
    """일괄 적용이 아니다 — 목록에 있는 잡만 앞당긴다.

    🔴 [SCH-2 2026-09-08] 종전에는 대표 잡 셋을 **손으로 적어** parametrize 했고
       (`watchdog_5m`·`lineup_poll_30m`·`research_retry_45m`), 잡 하나를 빼자
       그 사본이 깨졌다. 이 저장소의 반복 결함(사본이 원본을 못 따라간다)이
       테스트 쪽에서 난 것이다. 이제 **등록표에서 읽는다** — 잡이 늘거나 줄어도
       따라간다.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    from app.scheduler import RUN_AT_BOOT, _job_specs, build_scheduler

    sched = build_scheduler()
    targets = [j for j, _fn, trig in _job_specs()
               if isinstance(trig, IntervalTrigger) and j not in RUN_AT_BOOT]
    assert targets, "간격 잡이 하나도 없다 — 등록표를 잘못 읽었다"
    for job_id in targets:
        job = sched.get_job(job_id)
        assert job is not None, job_id
        assert getattr(job, "next_run_time", None) is None, (
            f"{job_id} 가 기동 실행 대상이 아닌데 첫 실행이 지정됐다")


# ═══════════════ [SCH-2 2026-09-08] 같은 일을 두 번 하는 잡이 있었다
#
# 🔴 `lineup_poll_30m` 은 **고유 커버리지가 0** 이었다:
#      lineup_poll_30m  → mlb_pregame_poll() + crawler_lineup_poll(("npb","kbo"))
#      mlb_pregame_5m   → mlb_pregame_poll()                 ← 같은 함수
#      asia_pregame_5m  → crawler_lineup_poll(("kbo",))      ← 같은 함수
#      npb_pregame_2m   → crawler_lineup_poll(("npb",))      ← 같은 함수
#    창 게이트도 같은 것(`mlb_poll_window`·`asia_poll_window`)을 쓴다. 즉 30분마다
#    이미 하는 일을 한 번 더 하고, 5분/2분 잡과 **동시에 발화하면 경합**한다.
#    실측 2026-09-08 pick_ledger 경기당 판정 횟수:
#      09-04 kbo 5.40 · 09-05 6.60 · **09-06 13.40(최대 17)** · npb 09-06 10.33
#    ⚠️ 이 잡만이 원인은 아니다 — 주 원인은 재판정 방아쇠(`changed`)다(FINDINGS
#       SCH-2). 여기서 줄이는 몫은 KBO 기준 시간당 12회 대비 2회, **약 14%** 다.
#       과장하지 않는다.


def test_같은_함수를_두_잡이_돌리지_않는다():
    """🔴 중복 잡은 크레딧을 두 번 태우고 원장에 두 번 찍는다."""
    import inspect

    from app.scheduler import _job_specs

    specs = _job_specs()
    ids = {job_id for job_id, _, _ in specs}
    assert "lineup_poll_30m" not in ids, (
        "lineup_poll_30m 은 mlb_pregame_poll·crawler_lineup_poll 을 다시 부른다 — "
        "그 둘은 mlb_pregame_5m·asia_pregame_5m·npb_pregame_2m 이 이미 돌린다.")
    # 남은 잡들이 세 경로를 **여전히 전부** 덮는지 확인한다(반대 위험).
    src = {job_id: inspect.getsource(fn) for job_id, fn, _ in specs}
    assert "mlb_pregame_poll" in str(src.get("mlb_pregame_5m", "")) \
        or "mlb_pregame_5m" in ids, "MLB 폴링이 사라졌다"
    assert "kbo" in src.get("asia_pregame_5m", ""), "KBO 폴링이 사라졌다"
    assert "npb" in src.get("npb_pregame_2m", ""), "NPB 폴링이 사라졌다"


def test_세_폴링_잡이_모두_남아_있다():
    """⚠️ 반대 위험 — 중복을 없앤다며 유일한 경로까지 빼면 카드가 0장이 된다."""
    from app.scheduler import _job_specs

    ids = {job_id for job_id, _, _ in _job_specs()}
    for need in ("mlb_pregame_5m", "asia_pregame_5m", "npb_pregame_2m"):
        assert need in ids, f"{need} 이 없다 — 그 리그는 라인업을 못 받는다"
