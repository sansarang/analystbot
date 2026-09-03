"""[2026-09-03 승인 수정 3건] 감시·계측이 **정상을 결함으로 세지 않는가.**

🔴 셋 다 같은 병이었다 — 지표가 정상 동작을 이상으로 세면, 진짜 이상이
   그 소음 속에 묻힌다. 실사고: 배당이 88분 멈춘 진짜 고장이 15분마다
   울리는 경보들 사이에서 원인을 못 찾은 채로 있었다.
"""
from datetime import UTC, datetime, timedelta

import pytest


# ═══════════════ ① M-3 — 잠정 상태의 부분 타순은 정상이다 ═══════════════

@pytest.mark.asyncio
async def test_m3_counts_only_confirmed_lineups():
    seen = {}

    class Pool:
        async def fetchrow(self, sql, *a):
            return None

        async def fetchval(self, sql, *a):
            seen["sql"] = sql
            return 0

    from app.engine.daily_summary import monitor_lines

    await monitor_lines(Pool(), None, ("mlb",), "2026-09-03")
    sql = seen.get("sql", "")
    assert "lineups" in sql
    assert "status = 'confirmed'" in sql, \
        "잠정 상태의 부분 타순까지 세면 매일 거짓 '이상 20건'이 찍힌다"


def test_forensics_counts_only_confirmed():
    """🔴 두 테이블이 "확정"을 **다르게** 적는다.

    `lineups.status='confirmed'` vs `lineup_events.is_final`.
    한쪽 이름을 양쪽에 쓰면 조회가 통째로 깨진다 — 실사고 2026-09-03:
    `column l.status does not exist` 로 lineup_events 감시가 죽었다.
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    i = src.index("타순 길이 ≠ 9 인 행")
    seg = src[max(0, i - 1800):i]
    assert "l.status = 'confirmed'" in seg, "lineups 확정 조건이 없다"
    assert "l.is_final" in seg, "lineup_events 는 is_final 이다"
    # 테이블마다 제 조건을 들고 다녀야 한다 — 하드코딩된 공통 WHERE 금지
    assert "AND {final}" in seg, "확정 조건이 테이블별로 갈리지 않는다"


# ═══════════════ ② W-JOB-LATE — 배포 후 미실행 ═══════════════

class _Redis:
    pass


def _patch_runs(monkeypatch, job_id, at):
    import app.health as H

    async def fake(redis):
        return {job_id: {"at": at.isoformat()}}

    monkeypatch.setattr(H, "_job_runs", fake)


def _patch_boot(monkeypatch, when):
    import app.watchdog as W

    monkeypatch.setattr(W, "_boot_time", lambda: when)


@pytest.mark.asyncio
async def test_starved_interval_job_is_named_even_during_boot_grace(monkeypatch):
    """🔴 오늘의 실사고 — 잦은 배포가 30분 잡을 굶겼다.

    기동 유예 중이라도 **이름을 붙여** 알려야 한다. 종전에는 유예에 막혀
    침묵했고, 증상(W-ODDS-STALE)만 15분마다 울었다.
    """
    import app.watchdog as W

    now = datetime(2026, 9, 3, 2, 28, tzinfo=UTC)
    last = now - timedelta(minutes=63)          # 마지막 실행 01:25
    boot = now - timedelta(minutes=5)           # 02:23 재기동 (유예 안)
    _patch_runs(monkeypatch, "odds_snapshot_30m", last)
    _patch_boot(monkeypatch, boot)
    monkeypatch.setattr(W, "_booted_recently", lambda n: True)
    monkeypatch.setattr(W, "datetime", _FixedNow(now))
    monkeypatch.setattr(W, "_next_expected",
                        lambda jid, at: at + timedelta(minutes=30))

    out = await W.check_jobs(_Redis())
    assert out, "배포 후 미실행이 침묵했다"
    code, job, detail = out[0]
    assert code == "W-JOB-LATE" and job == "odds_snapshot_30m"
    assert "배포 후 미실행" in detail
    assert "63분 전" in detail and "주기 30분" in detail


@pytest.mark.asyncio
async def test_normal_restart_delay_stays_silent(monkeypatch):
    """정상 재기동 지연은 여전히 조용하다 — 오탐을 늘리지 않는다."""
    import app.watchdog as W

    now = datetime(2026, 9, 3, 2, 28, tzinfo=UTC)
    last = now - timedelta(minutes=20)          # 주기(30) 의 2배 미만
    boot = now - timedelta(minutes=5)
    _patch_runs(monkeypatch, "odds_snapshot_30m", last)
    _patch_boot(monkeypatch, boot)
    monkeypatch.setattr(W, "_booted_recently", lambda n: True)
    monkeypatch.setattr(W, "datetime", _FixedNow(now))
    monkeypatch.setattr(W, "_next_expected",
                        lambda jid, at: at + timedelta(minutes=30))

    assert await W.check_jobs(_Redis()) == []


@pytest.mark.asyncio
async def test_stale_without_restart_is_not_called_a_deploy_problem(monkeypatch):
    """재기동이 없었으면 '배포 후 미실행'이 아니다 — 원인을 잘못 부르지 않는다."""
    import app.watchdog as W

    now = datetime(2026, 9, 3, 2, 28, tzinfo=UTC)
    last = now - timedelta(minutes=90)
    boot = last - timedelta(hours=3)            # 기동이 마지막 실행보다 이전
    _patch_runs(monkeypatch, "odds_snapshot_30m", last)
    _patch_boot(monkeypatch, boot)
    monkeypatch.setattr(W, "_booted_recently", lambda n: False)
    monkeypatch.setattr(W, "datetime", _FixedNow(now))
    monkeypatch.setattr(W, "_next_expected",
                        lambda jid, at: at + timedelta(minutes=30))

    out = await W.check_jobs(_Redis())
    assert out and "배포 후 미실행" not in out[0][2]
    assert "지났다" in out[0][2]


class _FixedNow:
    """`datetime.now(UTC)` 만 고정한다 — 나머지는 진짜 datetime 그대로."""

    def __init__(self, when):
        self._when = when

    def __getattr__(self, k):
        import datetime as _d

        return getattr(_d.datetime, k)

    def now(self, tz=None):
        return self._when


# ═══════════════ ③ 종료 슬레이트는 배당 실패가 아니다 ═══════════════

def test_finished_slate_is_info_not_warning():
    from pathlib import Path

    src = Path("app/collectors/odds_free.py").read_text(encoding="utf-8")
    i = src.index("무료 소스 전부 실패")
    seg = src[max(0, i - 1400):i]
    assert "starts_at > now()" in seg, "미시작 경기 수를 세지 않는다"
    assert "고장 아님" in seg, "종료 슬레이트를 INFO 로 구분하지 않는다"
    # 모를 때는 종전대로 경고한다 — 조용해지는 쪽으로 기울지 않는다
    assert "upcoming = -1" in seg
