"""[PIPE-8 2026-09-25] 원장이 **종목과 마켓을 갈라 적는다.**

사용자 감사 2026-09-25 모순 8:
```
decision_ledger  flow_v14 923행 전부 sport='baseball' · market='h2h'
→ 리그별 채점·CLV 비교 불가 · 구조 픽 0건
```
원인은 둘이었다:
  `state.sport` 가 `baseball|soccer` 규약(`bridge._sport_of`)인데 그대로 적었다.
  `_INSERT` SQL 에 `'h2h'`·`NULL` 이 **박혀** 있었다.

⚠️ 과거 923행 소급 갱신은 **하지 않았다** — 되돌리기 어려운 UPDATE 라
   승인 전에는 돌리지 않는다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow import record as R
from app.flow.labels import PICK_STRUCT, sport_code


class _Pool:
    def __init__(self):
        self.calls = []

    async def fetchrow(self, sql, *a):
        self.calls.append(("SELECT", a))
        return None

    async def execute(self, sql, *a):
        self.calls.append((sql, a))


class _Ctx:
    def __init__(self, pool):
        self.pool = pool


class _S:
    run_id = "r1"
    game_id = "7"
    sport = "baseball"            # 🔴 흐름 규약 — 리그가 아니다
    league = "NPB"
    stop_reason = None
    pick_side = "home"
    n02_market = {"p": {"home": 0.64, "draw": None, "away": 0.36},
                  "odds": {"home": 1.7, "away": 2.3}}
    n03_gate = {"gate": "동의"}
    n07_adjust = [{"pp": -1.2}]
    n08_pcode = {"p_code_pick": 0.6522}
    n09_conf = {"grade": "B"}
    n11_value = None


def _inserts(pool):
    return [c for c in pool.calls if isinstance(c[0], str)
            and "INSERT" in c[0]]


@pytest.mark.asyncio
async def test_pipe8_종목이_리그코드로_적힌다():
    pool = _Pool()
    assert await R.record(_S(), _Ctx(pool)) is True
    args = _inserts(pool)[0][1]
    assert args[2] == "npb", args
    assert args[2] != "baseball", "흐름 규약을 그대로 적었다"
    # 🔴 사본 금지 — 원본 함수와 같은 값이어야 한다
    assert args[2] == sport_code(_S())


@pytest.mark.asyncio
async def test_pipe8_축구는_종목_그대로다():
    class _Soc(_S):
        sport = "soccer"
        league = "EPL"

    pool = _Pool()
    await R.record(_Soc(), _Ctx(pool))
    assert _inserts(pool)[0][1][2] == "soccer", _inserts(pool)[0][1]


@pytest.mark.asyncio
async def test_pipe8_구조픽이_자기_마켓으로_남는다():
    class _St(_S):
        n11_value = {"pick_type": PICK_STRUCT,
                     "structure": {"market": "total_over", "line": 7.0,
                                   "odds": 1.9, "edge_pp": 3.1}}
        n08_pcode = {"p_code_pick": 0.6522,
                     "ours_markets": {"total_over": {7.0: 0.58}}}

    pool = _Pool()
    assert await R.record(_St(), _Ctx(pool)) is True
    rows = [c[1] for c in _inserts(pool)]
    assert len(rows) == 2, rows
    markets = {r[4] for r in rows}
    assert markets == {"h2h", "total_over"}, markets
    struct = next(r for r in rows if r[4] == "total_over")
    assert struct[5] == 7.0, struct           # line
    assert struct[6] == "over", struct        # side
    assert struct[7] == 1.9, struct           # price
    assert struct[8] == 0.58, struct          # p_model


@pytest.mark.asyncio
async def test_pipe8_모델_확률이_없으면_구조행을_만들지_않는다():
    """🔴 지어내지 않는다 — `ours_markets` 에 없으면 남기지 않는다."""
    class _St(_S):
        n11_value = {"pick_type": PICK_STRUCT,
                     "structure": {"market": "total_over", "line": 7.0,
                                   "odds": 1.9}}
        n08_pcode = {"p_code_pick": 0.6522, "ours_markets": {}}

    pool = _Pool()
    await R.record(_St(), _Ctx(pool))
    assert {c[1][4] for c in _inserts(pool)} == {"h2h"}


def test_pipe8_SQL에_마켓을_박지_않았다():
    assert "'h2h'" not in R._INSERT, "마켓이 SQL 에 박혀 있다"
    assert "market = $" in R._SAME_SQL, "중복 검사가 h2h 로 고정돼 있다"


def test_pipe8_소급_마이그레이션은_코드에_없다():
    """⚠️ 되돌리기 어려운 UPDATE 는 승인 전에는 돌리지 않는다."""
    src = inspect.getsource(R)
    assert "UPDATE decision_ledger" not in src
