"""PA-22-b 계약 — 위생 검사를 실제로 건다.

🔴 PA-22 가 `margin_ok`·`devig_ok`·`placeholder_suspect` 를 만들었는데
   호출부가 0건이었다 — 오늘만 여덟 번 본 그 병이다.
🔴 재현 실측: 마진 0(합 100.0%)짜리 배당이 게이트까지 가서
   `시장 과대 · gap -22.46` 을 만들었다. **만들어진 값으로 괴리를 쟀다.**
"""
import pathlib

import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL
from app.engine import prior as P

HOME, AWAY = "AC Milan", "AS Roma"


def _snaps(h_odds, a_odds):
    """⚠️ `_snap_probs` 는 `side` 를 **팀 이름**과 대조한다."""
    return [{"provider": "x", "book": "b", "snap_tag": "open", "market": "h2h",
             "side": s, "odds": o, "home": HOME, "away": AWAY,
             "captured_at": None}
            for s, o in ((HOME, h_odds), (AWAY, a_odds))]


class _Conn:
    def __init__(self, snaps, peers=None):
        self.snaps = snaps
        self.peers = peers or []
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "WHERE id = $1" in sql:
            return {"sport": "soccer", "league": "세리에A",
                    "home": HOME, "away": AWAY}
        return {"w": 2, "d": 1, "l": 1}

    async def fetch(self, sql, *a):
        if "p_market" in sql:
            return self.peers
        return self.snaps

    async def fetchval(self, sql, *a):
        return None

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


@pytest.fixture(autouse=True)
def tiers(monkeypatch):
    monkeypatch.setattr(P, "load_tiers", lambda key: {HOME: 2, AWAY: 3})


@pytest.mark.asyncio
async def test_마진_0이면_시장_없음이다():
    """🔴 실제 북에는 없는 값이다 — 그것으로 괴리를 재면 게이트가 거짓이다."""
    out = await PL.record_prior(_Conn(_snaps(2.0, 2.0)), game_id=1)
    assert out["label"] == G.BOARD
    assert out["gap_pp"] is None


@pytest.mark.asyncio
async def test_정상_마진은_통과한다():
    """🔴 반대 위험 — 정상 배당을 막으면 전 경기가 보드 고정이 된다."""
    out = await PL.record_prior(_Conn(_snaps(1.81, 2.05)), game_id=1)
    assert out["label"] != G.BOARD
    assert out["gap_pp"] is not None


@pytest.mark.asyncio
async def test_마진_과대도_막는다():
    out = await PL.record_prior(_Conn(_snaps(1.5, 1.7)), game_id=1)
    assert out["label"] == G.BOARD


@pytest.mark.asyncio
async def test_자리표_의심을_표시한다():
    """같은 슬레이트의 다른 경기와 소수점까지 같으면 표시한다."""
    from app.engine.market_edge import implied_probs

    mp = implied_probs({"home": 1.81, "away": 2.05})
    conn = _Conn(_snaps(1.81, 2.05), peers=[{"p_market": mp["home"]}])
    await PL.record_prior(conn, game_id=1)
    assert any("placeholder_suspect" in s for s, _ in conn.saved)


@pytest.mark.asyncio
async def test_자리표는_폐기가_아니다():
    """🔴 반대 위험 — 표시만 하고 게이트는 그대로 돈다."""
    from app.engine.market_edge import implied_probs

    mp = implied_probs({"home": 1.81, "away": 2.05})
    conn = _Conn(_snaps(1.81, 2.05), peers=[{"p_market": mp["home"]}])
    out = await PL.record_prior(conn, game_id=1)
    assert out["gap_pp"] is not None, "표시했다고 시장을 버리면 안 된다"


@pytest.mark.asyncio
async def test_다른_경기와_다르면_표시_안_한다():
    conn = _Conn(_snaps(1.81, 2.05), peers=[{"p_market": 0.4000}])
    await PL.record_prior(conn, game_id=1)
    assert not any("placeholder_suspect" in s for s, _ in conn.saved)


@pytest.mark.asyncio
async def test_자리표_검사가_터져도_게이트는_돈다():
    """저장 전용 규약 — 측정 장치가 판정을 죽이면 안 된다."""
    class _Boom(_Conn):
        async def fetch(self, sql, *a):
            if "p_market" in sql:
                raise RuntimeError("DB 없음")
            return self.snaps

    out = await PL.record_prior(_Boom(_snaps(1.81, 2.05)), game_id=1)
    assert out["gap_pp"] is not None


def test_문턱을_손으로_안_적었다():
    """🔴 사본 금지 — 100.5·115·0.005 는 market_edge 가 원본이다."""
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    blk = src.split("PA-22-b")[1][:1200]
    for lit in ("100.5", "115.0", "0.005"):
        assert lit not in blk, f"문턱을 손으로 적었다: {lit}"
    assert "margin_ok(" in blk and "devig_ok(" in blk


def test_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "placeholder_suspect" in src
