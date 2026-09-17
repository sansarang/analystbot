"""PA-24 계약 — 조정 전 기본 확률(`p_base`)을 원장에 남긴다 (지시문 8단계).

🔴 종전에는 `record_prior` 가 `soccer_prior(...)` 로 3-way 를 만들어 놓고
   `p_home = pri[0]` 로 홈만 남겼다 — 무·원정이 그 줄에서 사라졌다.
   그래서 "조정이 얼마나 움직였나"를 원장만 보고 답할 수 없었고,
   10단계 변수별 채점의 전제가 없었다.
"""
import json
import pathlib

import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL
from app.engine import prior as P


class _Conn:
    def __init__(self):
        self.saved = []

    async def fetchrow(self, sql, *a):
        # ⚠️ `_FORM_SQL` 에도 "FROM games" 가 있다 — 그걸로 가르면 두 질의가
        #    같은 분기로 간다(처음에 그렇게 썼다가 KeyError 가 났다).
        #    경기 행은 `WHERE id = $1` 로 가른다.
        if "WHERE id = $1" in sql:
            return {"sport": "soccer", "league": "세리에A",
                    "home": "AC Milan", "away": "AS Roma"}
        return {"w": 2, "d": 1, "l": 1}

    async def fetch(self, sql, *a):
        return []

    async def fetchval(self, sql, *a):
        return None

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


@pytest.fixture
def tiers(monkeypatch):
    monkeypatch.setattr(P, "load_tiers",
                        lambda key: {"AC Milan": 2, "AS Roma": 3})


@pytest.mark.asyncio
async def test_축구는_3way를_남긴다(tiers):
    conn = _Conn()
    out = await PL.record_prior(conn, game_id=1)
    assert out is not None
    base = out["p_base"]
    assert set(base) == {"h", "d", "a"}
    assert base["h"] == pytest.approx(out["p_prior"], abs=1e-6)
    assert sum(base.values()) == pytest.approx(1.0, abs=1e-3)


@pytest.mark.asyncio
async def test_원장_저장에_p_base가_실린다(tiers):
    conn = _Conn()
    await PL.record_prior(conn, game_id=1)
    hits = [a for s, a in conn.saved if "p_base" in s]
    assert hits, "p_base 가 저장되지 않았다"
    payload = json.loads(hits[-1][7])
    assert set(payload) == {"h", "d", "a"}


@pytest.mark.asyncio
async def test_야구는_홈만이다(monkeypatch):
    """⚠️ 야구는 2-way 다 — 없는 칸(무)을 만들지 않는다."""
    monkeypatch.setattr(P, "load_tiers", lambda key: {"A": 2, "B": 3})

    class _BB(_Conn):
        async def fetchrow(self, sql, *a):
            if "WHERE id = $1" in sql:
                return {"sport": "mlb", "league": "MLB", "home": "A", "away": "B"}
            return {"w": 10, "d": 0, "l": 8}

    out = await PL.record_prior(_BB(), game_id=1)
    assert set(out["p_base"]) == {"h"}


@pytest.mark.asyncio
async def test_티어_미기입이면_p_base도_없다(monkeypatch):
    """🔴 반대 위험 — 사전값이 없는데 기본 확률을 지어내면 안 된다(U3)."""
    monkeypatch.setattr(P, "load_tiers", lambda key: {"다른 팀": 3})
    out = await PL.record_prior(_Conn(), game_id=1)
    assert out["label"] == G.BOARD
    assert out["p_prior"] is None
    hits = [a for s, a in _Conn().saved if "p_base" in s]
    assert not hits or all(a[7] is None for a in hits)


def test_p_prior를_안_건드린다():
    """🔴 반대 위험 — 읽는 곳이 여럿이다. p_base 는 **추가**다."""
    led = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "p_prior = $2::double precision" in led


def test_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "p_base JSONB" in src


def test_p_base는_조정_전_값이다():
    """🔴 `p_code`(조정 후)와 다른 값이어야 의미가 있다."""
    led = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    blk = led.split("p_base = {")[1][:200]
    for banned in ("adj", "p_code", "shrink"):
        assert banned not in blk, f"조정 값이 섞였다: {banned}"
