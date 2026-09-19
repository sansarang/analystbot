"""[ELO-1] ①사전값이 슬레이트마다 서야 한다.

🔴 원인 사슬 (전부 실측, 2026-09-19):
   ① `team_elo` 캐시를 쓰는 곳은 **옛 파이프라인의 게으른 폴백 하나뿐**이다
      (`app/pipeline.py:2915`). 전용 갱신 잡이 없다 —
      `elo_refresh_weekly` 는 축구 `soccer_elo`(CSV 재피팅)로 다른 물건이다.
   ② `PIPELINE_V14=True` 가 그 옛 경로를 지나친다.
   ③ `n01_prior` 는 **읽기만** 한다(`TE.load`). 없으면 `p_home=None`.
   ④ 캐시 키가 **킥오프 UTC 날짜**다 → 오늘 슬레이트의 키가 없다.
   → 운영 Redis 에 `elo:*` 가 `2026-09-18` 세 개뿐이었고, 최근 사이클
     36경기가 전건 `보드고정(사전값이 없다)` 이었다.

🔴 고치는 자리는 **슬레이트 단위**다. 경기마다 다시 계산하면 36배가 된다.
⚠️ `n01_prior` 는 여전히 elo 와 HFA 만 읽는다 — 원장·배당·②노드에 손대지 않는다.
"""
from __future__ import annotations

import inspect

import pytest


def test_n01은_원장도_배당도_읽지_않는다():
    """🔴 [2-2 통과 조건] 사전값은 시장을 보기 전에 선다."""
    from app.flow.nodes import n01_prior as N

    src = inspect.getsource(N)
    for forbidden in ("pick_ledger", "odds", "n02", "market", "devig"):
        assert forbidden not in src, f"n01 이 {forbidden} 를 읽는다"
    assert "team_elo" in src


def test_사전값에_asof_가_남는다():
    """🔴 어느 날짜 레이팅을 썼는지 모르면 "오래된 값으로 판정했다"를 못 잡는다."""
    from app.flow.nodes import n01_prior as N

    src = inspect.getsource(N)
    assert "asof" in src, "어느 날짜 레이팅인지 스냅샷에 남기지 않는다"


@pytest.mark.asyncio
async def test_오늘_키가_없으면_어제를_쓴다():
    """⚠️ 갱신을 한 번 놓쳤다고 슬레이트 전체가 보드고정이 되면 안 된다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n01_prior as N
    from app.flow.state import State

    class _R:
        def __init__(self, store):
            self.store = store

        async def get(self, k):
            return self.store.get(k)

    import json
    store = {"elo:mlb:2026-09-18": json.dumps({"A": 1600.0, "B": 1500.0})}
    st = State(run_id="r1", game_id="1", sport="baseball", league="MLB",
               home="A", away="B", kickoff_utc="2026-09-19T01:40:00Z")
    out = await N.run(st, Ctx(redis=_R(store)))
    assert out.n01_prior["p_home"] is not None, out.n01_prior
    assert out.n01_prior["asof"] == "2026-09-18", out.n01_prior


@pytest.mark.asyncio
async def test_아무_날짜도_없으면_지어내지_않는다():
    from app.flow.ctx import Ctx
    from app.flow.nodes import n01_prior as N
    from app.flow.state import State

    class _R:
        async def get(self, k):
            return None

    st = State(run_id="r1", game_id="1", sport="baseball", league="MLB",
               home="A", away="B", kickoff_utc="2026-09-19T01:40:00Z")
    out = await N.run(st, Ctx(redis=_R()))
    assert out.n01_prior["p_home"] is None
    assert out.n01_prior["asof"] is None


def test_bridge_가_슬레이트마다_elo_를_보장한다():
    """🔴 경기마다 다시 계산하면 36배다 — 슬레이트 단위로 한 번."""
    from app.flow import bridge as B

    src = inspect.getsource(B)
    assert "ensure_elo" in src, "슬레이트 앞에서 elo 를 보장하지 않는다"


@pytest.mark.asyncio
async def test_ensure_elo_는_있으면_다시_계산하지_않는다():
    from app.flow.bridge import ensure_elo

    calls = []

    class _R:
        async def get(self, k):
            return '{"A": 1500.0}'

    async def _refresh(*a, **k):
        calls.append(a)
        return {}

    got = await ensure_elo(None, _R(), "mlb", "2026-09-19", refresh=_refresh)
    assert got is True
    assert calls == [], "이미 있는데 다시 계산했다"


@pytest.mark.asyncio
async def test_ensure_elo_는_없으면_계산한다():
    from app.flow.bridge import ensure_elo

    calls = []

    class _R:
        async def get(self, k):
            return None

    async def _refresh(pool, redis, sport, date, **k):
        calls.append((sport, date))
        return {"A": 1500.0}

    # ⚠️ 풀이 없으면 재계산하지 않는다(그게 맞다) — 있는 상황을 만든다.
    got = await ensure_elo(object(), _R(), "mlb", "2026-09-19", refresh=_refresh)
    assert got is True
    assert calls == [("mlb", "2026-09-19")], calls


@pytest.mark.asyncio
async def test_풀이_없으면_재계산하지_않는다():
    """🔴 드라이런·테스트에는 DB 가 없다 — 거기서 재계산을 시도하면 터진다."""
    from app.flow.bridge import ensure_elo

    class _R:
        async def get(self, k):
            return None

    assert await ensure_elo(None, _R(), "mlb", "2026-09-19") is False
