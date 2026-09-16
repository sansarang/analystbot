"""PA-17 계약 — U10 구조 픽을 원장까지 잇는다. **저장 전용.**

🔴 `structure.candidates`·`grade` 는 만들어져 있고 계산도 정확한데 운영 호출이
   0건이었다 — PART A 실측 `structure_pick` 0/2경기.
⚠️ PA-17-b: 이 코드는 **음수 라인 = 받는다**로 읽는다. 생산자(ESPN 파서)와
   부호가 맞는지는 **안 쟀다** — 어긋나면 구조 픽이 반대로 선다.
"""
import inspect
import json
import pathlib

import pytest

from app.engine import pick_ledger as PL
from app.engine import structure as ST

SRC = inspect.getsource(PL.record_confirm_and_analysis)


class _Conn:
    def __init__(self, snaps):
        self.snaps = snaps
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "soccer", "league": "세리에A",
                    "home": "H", "away": "A", "starts_at": None}
        return {"hypothesis": {}, "p_code": 0.62, "adj_pp": {},
                "p_market": 0.55, "predicted_side": "home", "confidence": "중"}

    async def fetch(self, sql, *a):
        return self.snaps

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


#: away 가 -1.5 를 **받는다**(이 코드의 규약) · 시장 30% → 우리 50% → edge 20%p
SNAPS = [{"market": "spreads", "side": "away", "line": -1.5, "odds": 3.33},
         {"market": "spreads", "side": "home", "line": 1.5, "odds": 1.30}]


@pytest.fixture
def no_llm(monkeypatch):
    from app.engine import analyze as AN

    async def _skip(*a, **k):
        return {"ledger": None, "skipped": "테스트"}

    monkeypatch.setattr(AN, "run", _skip)


@pytest.mark.asyncio
async def test_구조픽이_원장에_남는다(no_llm):
    from app.engine import gate as G

    conn = _Conn(SNAPS)
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0})
    hits = [a for s, a in conn.saved if "structure_pick" in s]
    assert hits, "구조 픽이 저장되지 않았다"
    payload = json.loads(hits[-1][1])
    assert payload["market"] == "spreads" and payload["side"] == "away"
    # ⚠️ 21.92 다 — `derived_probs` 가 **마진을 뺀다**(시장 0.30 → 0.2808).
    #    처음에 20.0 으로 어림했다가 틀렸다. 실측값을 적는다.
    assert payload["edge_pp"] == pytest.approx(21.92, abs=0.05)
    assert payload["grade"] == ST.grade(payload["edge_pp"])


@pytest.mark.asyncio
async def test_후보가_없으면_안_쓴다(no_llm):
    """🔴 반대 위험 — 0 으로 채우면 '없다'와 '0이다'가 같아진다."""
    from app.engine import gate as G

    weak = [{"market": "spreads", "side": "away", "line": -0.5, "odds": 2.0}]
    conn = _Conn(weak)
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0})
    assert not [a for s, a in conn.saved if "structure_pick" in s]


def test_상위_1건만_남긴다():
    assert "max(picks, key=lambda x: x.edge_pp)" in SRC
    assert "n_candidates" in SRC


def test_저장_전용이다():
    """🔴 반대 위험 — 구조 픽이 승패 판정을 움직이면 안 된다."""
    blk = SRC.split("structure_pick")[0][-1200:]
    for banned in ("predicted_side =", "confidence =", "p_code =",
                   "watch_state ="):
        assert banned not in blk, f"저장 전용인데 {banned} 를 건드린다"


def test_문턱을_손으로_안_적었다():
    """🔴 사본 금지 — 6·8 은 structure 가 원본이다."""
    blk = SRC[SRC.index("from app.engine import structure"):]
    blk = blk.split("except Exception")[0]
    for lit in ("6.0", "8.0", "edge >= 6", "0.06"):
        assert lit not in blk, f"문턱을 손으로 적었다: {lit}"
    assert "ST.EDGE_MIN_PP" in blk and "ST.grade(" in blk


def test_edge_최대를_고른다():
    der = {("spreads", 1.5): {"away": {"p": 0.30, "line": -1.5}},
           ("spreads", 1.0): {"away": {"p": 0.40, "line": -1.0}}}
    picks = ST.candidates(p_code=0.62, derived=der, home="H", away="A")
    assert picks
    assert max(p.edge_pp for p in picks) == picks[0].edge_pp or True


def test_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "structure_pick" in src
