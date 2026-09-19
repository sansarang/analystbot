"""[DT-1] ⑤의 DB 조회가 **문자열 킥오프**를 넘겨 전부 죽고 있었다.

🔴 실측 2026-09-20 (운영, g10932 직접 호출):
     asyncpg.exceptions.DataError: invalid input for query argument $2:
       '2026-09-19T23:10:00Z' (expected a datetime.date or datetime.datetime
        instance, got 'str')
   `::timestamptz` 캐스트가 SQL 안에 있어도 asyncpg 는 **바인딩 단계에서**
   타입을 본다. 그래서 캐스트가 구해 주지 않는다.
🔴 그런데 `_bullpen3d`·`_last3` 는 `except Exception: return []` 로 **조용히
   삼켰다.** 그래서 `bullpen_3d`·`form_recent5` 가 영원히 `unknown` 이었고,
   ⑥이 늘 `모름과반`으로 끝났다.
   데이터는 있었다 — HOU 불펜 3일 10행 · STL 2행(실측).
⚠️ 이 저장소는 같은 함정을 이미 겪었다("'str' object has no attribute
   'toordinal'"). 두 번째다.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest


def test_킥오프를_datetime_으로_바꾼다():
    from app.flow.nodes.n05_evidence import _kickoff_dt

    got = _kickoff_dt("2026-09-19T23:10:00Z")
    assert isinstance(got, datetime)
    assert got.tzinfo is not None
    assert got == datetime(2026, 9, 19, 23, 10, tzinfo=UTC)


def test_모르는_모양은_None_이다():
    """🔴 못 읽으면 None — 조회가 '전체 기간'이 되지 창이 0이 되면 안 된다."""
    from app.flow.nodes.n05_evidence import _kickoff_dt

    assert _kickoff_dt("") is None
    assert _kickoff_dt(None) is None
    assert _kickoff_dt("어제") is None


def test_이미_datetime_이면_그대로():
    from app.flow.nodes.n05_evidence import _kickoff_dt

    d = datetime(2026, 9, 19, 23, 10, tzinfo=UTC)
    assert _kickoff_dt(d) is d


@pytest.mark.asyncio
async def test_조회가_문자열을_넘기지_않는다():
    """🔴 결함 자체를 겨눈다 — 풀에 무엇이 들어가는지 잡는다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N
    from app.flow.state import State

    seen = []

    class _Pool:
        async def fetch(self, sql, *a):
            seen.append(a)
            return []

    st = State(run_id="r", game_id="1", sport="baseball", league="MLB",
               home="H", away="A", kickoff_utc="2026-09-19T23:10:00Z")
    ctx = Ctx(pool=_Pool())
    await N._bullpen3d(st, ctx, "home")
    await N._last3(st, ctx, "home")
    assert seen, "조회가 아예 안 됐다"
    for args in seen:
        for v in args:
            assert not (isinstance(v, str) and v.startswith("2026-")), \
                f"문자열 시각을 넘겼다: {v!r}"
