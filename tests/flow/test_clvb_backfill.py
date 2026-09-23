"""[CLV-B] 옛 원장 740행의 **시장 확률을 소급으로 복원**한다.

사용자 2026-09-23: "딥서치해서 찾아서 수정해라"

🔴 실측 2026-09-23 16:40 운영:
```
flow_v14 740행 · p_market_at_decision 0 · price_at_decision 0
  → CLV 대상이 0건이다(CLV-F 가 기준선을 요구한다)
결정 시각 **이전** h2h 스냅샷이 있는 행  740 / 740   ← 전건 복원 가능
중복 제거하면 96행 / 23경기
```
LED-1 에서 키를 고쳤지만 그건 **새 행부터**다. 옛 행은 영원히 빈칸이다.

🔴 **누설이 아니다.** `captured_at <= ts_decided` 만 쓴다 — 결정 시점에 이미
   있던 가격이다. 딥서치(F-20)가 1순위 위협으로 꼽은 look-ahead 를 이 조건이
   막는다. 종가는 건드리지 않는다(그건 `fill_clv` 가 따로 한다).

⚠️ **덮어쓰지 않는다.** 이미 값이 있는 행은 그대로 둔다 — 옛 값을 새 계산으로
   갈아치우면 그때 무엇을 봤는지가 사라진다.
"""
from __future__ import annotations

import pytest

from app.learning import decisions as D


class _Pool:
    def __init__(self, rows, prices=None):
        self.rows = rows
        self.prices = prices if prices is not None else {"home": 1.7, "away": 2.2}
        self.calls = []

    async def fetch(self, sql, *a):
        self.calls.append((sql, a))
        return self.rows

    async def execute(self, sql, *a):
        self.calls.append((sql, a))


def test_함수가_있다():
    assert hasattr(D, "backfill_market")


def test_결정_시각_이전만_본다():
    """🔴 이것이 누설을 막는 조건이다."""
    assert "ts_decided" in D._BF_PENDING_SQL
    assert "p_market_at_decision IS NULL" in D._BF_PENDING_SQL


@pytest.mark.asyncio
async def test_시장_확률과_가격을_채운다(monkeypatch):
    async def _last(conn, *, game_id, market="h2h", at=None, line=None):
        assert at is not None, "기준 시각 없이 가격을 읽었다 — 누설이다"
        return {"home": 1.7, "away": 2.2}

    monkeypatch.setattr("app.learning.prices.last_prices", _last)
    pool = _Pool([{"id": 1, "game_id": 7, "side": "home", "market": "h2h",
                   "line": None, "ts_decided": "2026-09-23T00:00:00+00:00"}])
    got = await D.backfill_market(pool)
    assert got["filled"] == 1, got
    args = [a for sql, a in pool.calls if "UPDATE" in sql.upper()][0]
    # 디빅 후 홈 확률은 0.5~0.6 대, 가격은 1.7
    assert any(abs(float(x) - 1.7) < 1e-9 for x in args
               if isinstance(x, (int, float))), args


@pytest.mark.asyncio
async def test_원정_픽이면_원정_쪽이다(monkeypatch):
    async def _last(conn, **k):
        return {"home": 1.7, "away": 2.2}

    monkeypatch.setattr("app.learning.prices.last_prices", _last)
    pool = _Pool([{"id": 2, "game_id": 7, "side": "away", "market": "h2h",
                   "line": None, "ts_decided": "2026-09-23T00:00:00+00:00"}])
    await D.backfill_market(pool)
    args = [a for sql, a in pool.calls if "UPDATE" in sql.upper()][0]
    assert any(abs(float(x) - 2.2) < 1e-9 for x in args
               if isinstance(x, (int, float))), args


@pytest.mark.asyncio
async def test_가격이_없으면_건너뛴다(monkeypatch):
    async def _last(conn, **k):
        return {}

    monkeypatch.setattr("app.learning.prices.last_prices", _last)
    pool = _Pool([{"id": 3, "game_id": 7, "side": "home", "market": "h2h",
                   "line": None, "ts_decided": "2026-09-23T00:00:00+00:00"}])
    got = await D.backfill_market(pool)
    assert got["filled"] == 0 and got["skipped"] == 1, got


def test_덮어쓰지_않는다():
    """🔴 이미 값이 있는 행은 대상이 아니다 — 그때 무엇을 봤는지가 사라진다."""
    assert "IS NULL" in D._BF_PENDING_SQL


def test_디빅_규약이_한_곳이다():
    """🔴 사본 금지 — `prices.devig` 가 원본이다."""
    import inspect

    src = inspect.getsource(D.backfill_market)
    assert "devig" in src


def test_스케줄러가_부른다():
    import inspect

    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S).splitlines())
    assert "backfill_market" in src
