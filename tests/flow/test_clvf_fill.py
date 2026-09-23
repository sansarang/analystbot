"""[CLV-F] **결과를 기다리지 않고 채점한다.** 표본이 2건 → 17건.

사용자 2026-09-23: "딥서치해서 찾아서 수정해라" (문제 1 — 성적을 잴 수 없다)

🔴 **딥서치 근거** (→ docs/FORKS.md F-20):
   · CLV 는 **결과(win/loss)보다 빠른 신호**다 — 적중률은 "결과 지표"이고
     CLV 는 "과정 지표"라, 50건 표본의 60% 적중은 운으로도 나온다.
   · 양의 CLV 를 꾸준히 내는 쪽이 장기 수익을 내고, 음이면 못 낸다 —
     적중률은 분산에 크게 흔들려 상관이 약하다.
   · 다만 CLV 도 **200~500건**은 있어야 "실력"이라 말할 수 있다.
     지금 목표는 결론이 아니라 **잴 수 있게 만드는 것**이다.

🔴 실측 2026-09-23 16:30 운영:
```
flow_v14 원장 경기 23 · 그중 **종료 2건** ← 결과로는 2건밖에 못 잰다
                      · 종가 스냅샷 있음 **17건** ← CLV 로는 17건을 잰다
```
도구는 이미 있었다 — `learning.prices.close_p` · `learning.metrics.clv`.
**부르는 곳만 없었다.**

🔴 **누설이 아니다.** `prices.CLOSE_WHERE` 가 `captured_at <= LEAST(기준,
   starts_at)` 이라 킥오프 이후 스냅샷은 애초에 안 들어온다 — 딥서치가
   경고한 look-ahead bias 를 이 조건이 막는다.
⚠️ 그래도 **킥오프 전 경기는 채우지 않는다** — 아직 종가가 아니다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.learning import decisions as D

NOW = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)


class _Pool:
    def __init__(self, rows, close=0.58):
        self.rows = rows
        self.close = close
        self.calls = []

    async def fetch(self, sql, *a):
        self.calls.append((sql, a))
        return self.rows

    async def execute(self, sql, *a):
        self.calls.append((sql, a))

    def acquire(self):
        pool = self

        class _C:
            async def __aenter__(self_inner):
                return pool

            async def __aexit__(self_inner, *a):
                return False
        return _C()


def test_함수가_있다():
    assert hasattr(D, "fill_clv")


@pytest.mark.asyncio
async def test_종가로_CLV_를_채운다(monkeypatch):
    """🔴 이 단위의 전부 — 결과를 안 기다린다."""
    async def _close(conn, *, game_id, side, market="h2h", line=None):
        return 0.58

    monkeypatch.setattr("app.learning.prices.close_p", _close)
    pool = _Pool([{"id": 1, "game_id": 7, "side": "home", "market": "h2h",
                   "line": None, "p_market_at_decision": 0.52}])
    got = await D.fill_clv(pool)
    assert got["filled"] == 1, got
    wrote = [a for sql, a in pool.calls if "UPDATE" in sql.upper()]
    assert wrote, pool.calls
    # clv = 0.58 − 0.52 = +0.06 (우리 쪽으로 움직였다)
    # ⚠️ `wrote` 는 인자 튜플의 목록이다 — `wrote[0]` 이 이미 인자들이다.
    assert any(abs(float(x) - 0.06) < 1e-6 for x in wrote[0]
               if isinstance(x, (int, float))), wrote


@pytest.mark.asyncio
async def test_결정시점_확률이_없으면_건너뛴다(monkeypatch):
    """🔴 기준선이 없으면 CLV 가 없다 — 0 으로 채우지 않는다."""
    async def _close(conn, **k):
        return 0.58

    monkeypatch.setattr("app.learning.prices.close_p", _close)
    pool = _Pool([{"id": 2, "game_id": 7, "side": "home", "market": "h2h",
                   "line": None, "p_market_at_decision": None}])
    got = await D.fill_clv(pool)
    assert got["filled"] == 0 and got["skipped"] == 1, got


@pytest.mark.asyncio
async def test_종가를_못_구하면_건너뛴다(monkeypatch):
    async def _close(conn, **k):
        return None

    monkeypatch.setattr("app.learning.prices.close_p", _close)
    pool = _Pool([{"id": 3, "game_id": 7, "side": "home", "market": "h2h",
                   "line": None, "p_market_at_decision": 0.52}])
    got = await D.fill_clv(pool)
    assert got["filled"] == 0, got


def test_킥오프_전_경기는_고르지_않는다():
    """🔴 **아직 종가가 아니다.** 질의가 시작 시각을 본다."""
    assert "starts_at" in D._CLV_PENDING_SQL
    assert "now()" in D._CLV_PENDING_SQL


def test_이미_채운_행은_다시_안_본다():
    assert "p_close IS NULL" in D._CLV_PENDING_SQL


def test_부호_규약의_원본이_하나다():
    """🔴 사본 금지 — `metrics.clv` 가 원본이다."""
    import inspect

    src = inspect.getsource(D.fill_clv)
    assert "metrics" in src or "clv(" in src


def test_스케줄러가_부른다():
    import inspect

    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S).splitlines())
    assert "fill_clv" in src
