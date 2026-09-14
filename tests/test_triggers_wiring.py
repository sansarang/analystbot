"""TRG-2 — 시점 트리거 1분 루프 배선.

🔴 실측 결함 2026-09-14: `TRG-1` 이 시점표·SQL 을 만들었는데 **부르는 곳이
   없었다.** `game_triggers` 는 비어 있고 `odds_snapshots.snap_tag` 는 아무도
   쓰지 않았다(grep: 쓰는 곳 0). Part 1-B·Part 4 가 전부 그 이름표를 기준선으로
   쓰므로 여기가 막히면 뒤가 통째로 헛돈다.

⚠️ 이 파일은 **실제 호출**을 단언한다 — 소스 문자열 grep 이 아니다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import triggers as T


class _Pool:
    """fetch/execute 를 받아 적는 가짜 풀. 계획 대상은 없다고 답한다."""

    def __init__(self, due):
        self.due = due
        self.fetched: list[tuple] = []
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        self.fetched.append((sql, args))
        if "FROM game_triggers t JOIN games g" in sql:
            return self.due
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 3"


@pytest.mark.asyncio
async def test_due_트리거가_스냅샷에_이름표를_붙이고_닫힌다(monkeypatch):
    from app import scheduler

    # ⚠️ [FOT-2] `lineup` 시점은 라인업을 다시 받는다 — **계약 테스트가 외부를
    #    치면 안 된다.** 여기서 재는 것은 이름표 부착이다.
    async def _no_recheck(*a, **k):
        return None

    monkeypatch.setattr(scheduler, "_lineup_recheck", _no_recheck)

    now = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
    due = [{"id": 77, "game_id": 7432, "kind": "lineup", "due_at": now,
            "attempts": 0, "sport": "soccer", "league": "세리에A",
            "home": "Como 1907", "away": "Parma Calcio 1913",
            "starts_at": now + timedelta(hours=1)}]
    pool = _Pool(due)

    out = await scheduler._triggers_tick(pool=pool, now=now)

    assert out["발사"] == 1 and out["태그"] == 3 and out["무스냅"] == 0

    tagged = [(s, a) for s, a in pool.executed if "SET snap_tag" in s]
    assert len(tagged) == 1, "이름표 UPDATE 가 한 번 돌아야 한다"
    sql, args = tagged[0]
    assert args[0] == 7432 and args[1] == "lineup"
    # 🔴 나이 상한을 여기에 베끼지 않는다 — 코드의 상수를 그대로 읽는다.
    assert args[2] == now - timedelta(minutes=scheduler.TRIGGER_SNAP_MAX_AGE_MIN)

    marked = [(s, a) for s, a in pool.executed if s is T.MARK_SQL]
    assert marked == [(T.MARK_SQL, (77, now))], "같은 트리거를 다시 쏘지 않게 닫는다"


@pytest.mark.asyncio
async def test_스냅샷이_없으면_이름표_없이_닫는다():
    """🔴 없는 값을 0 으로 채우지 않는다. 그래도 트리거는 닫아야 한다 —
    안 닫으면 1분마다 영원히 재시도한다."""
    from app import scheduler

    now = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
    pool = _Pool([{"id": 9, "game_id": 1, "kind": "open", "due_at": now,
                   "attempts": 0, "sport": "mlb", "league": "MLB",
                   "home": "H", "away": "A", "starts_at": now}])
    pool.execute = _returns(pool, "UPDATE 0")

    out = await scheduler._triggers_tick(pool=pool, now=now)

    assert out["태그"] == 0 and out["무스냅"] == 1 and out["발사"] == 1
    assert any(s is T.MARK_SQL for s, _ in pool.executed)


def _returns(pool, result):
    async def _execute(sql, *args):
        pool.executed.append((sql, args))
        return result
    return _execute


def test_스케줄러가_1분마다_트리거를_돈다():
    from apscheduler.triggers.interval import IntervalTrigger

    from app import scheduler

    spec = [x for x in scheduler._job_specs() if x[0] == "triggers_1m"]
    assert len(spec) == 1, "잡 표에 triggers_1m 이 한 번 등록돼야 한다"
    _, fn, trig = spec[0]
    assert fn is scheduler.triggers_job
    assert isinstance(trig, IntervalTrigger)
    assert trig.interval == timedelta(minutes=1)
