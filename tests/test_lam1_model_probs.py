"""LAM-1 계약 — 우리 총점 확률이 **원장을 거쳐 구조 픽까지** 간다.

🔴 STR-1 이 `ours_totals` 자리를 냈는데 넘기는 쪽이 없어 총점 후보가 0 이었다.
⚠️ **자리표 사고 주의** — PA-23 에서 칸만 늘리고 `$N` 을 안 늘려 원장 저장이
   통째로 터질 뻔했다. 글자를 세지 않고 **실제 호출 인자 수**를 센다.
"""
import inspect
import json
import pathlib
import re

import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL

PROBS = {"totals": {"7.5": {"Over": 0.40, "Under": 0.60}}}
# ⚠️ 엣지가 문턱(structure.EDGE_MIN_PP)을 넘는 예를 쓴다. 처음에 Under 1.75
#    로 잡았더니 디빅 54.6% vs 우리 60% = 5.4%p 라 **걸러진 게 맞았다.**
#    여기서는 Under 2.10 → 디빅 45.4% vs 우리 60% = 14.6%p.
SNAPS = [{"market": "totals", "side": "Over", "line": 7.5, "odds": 1.75},
         {"market": "totals", "side": "Under", "line": 7.5, "odds": 2.10}]


class _Conn:
    def __init__(self, probs=PROBS, snaps=None):
        self.probs = probs
        self.snaps = SNAPS if snaps is None else snaps
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "kbo", "league": "KBO", "home": "NC",
                    "away": "SSG", "starts_at": None,
                    "home_pitcher": None, "away_pitcher": None}
        return {"hypothesis": {}, "p_code": 0.62, "adj_pp": {},
                "p_market": 0.55, "p_prior": 0.58, "odds": 1.75,
                "predicted_side": "home", "confidence": "중",
                "model_probs": json.dumps(self.probs) if self.probs else None}

    async def fetch(self, sql, *a):
        return self.snaps

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


@pytest.fixture
def no_llm(monkeypatch):
    from app.engine import analyze as AN

    async def _skip(*a, **k):
        return {"ledger": None, "skipped": "테스트"}

    monkeypatch.setattr(AN, "run", _skip)


def test_칸이_스키마에_있다():
    sql = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "model_probs" in sql


def test_row에_실린다():
    src = inspect.getsource(PL)
    assert '"model_probs": jg.get("model_probs")' in src


def test_자리표_수가_실제로_맞는다():
    """🔴 글자를 세지 않는다 — INSERT 자리표 최대값과 SQL 을 대조한다."""
    src = inspect.getsource(PL)
    ins = src.split("INSERT INTO pick_ledger", 1)[1][:1600]
    n = max(int(x) for x in re.findall(r"\$(\d+)", ins))
    assert n == 30
    assert "model_probs)" in ins and "$30::jsonb" in ins


@pytest.mark.asyncio
async def test_총점_후보가_나온다(no_llm):
    """우리 Under 60% vs 시장(디빅) — 엣지가 문턱을 넘으면 후보가 남는다."""
    conn = _Conn()
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0}, redis=None)
    hits = [a for s, a in conn.saved if "structure_pick" in s]
    assert hits, "구조 픽이 저장되지 않았다"
    payload = json.loads(hits[-1][1])
    assert payload["market"] == "totals"
    assert payload["side"] in ("Over", "Under")


@pytest.mark.asyncio
async def test_문자열_라인_키를_숫자로_되돌린다(no_llm):
    """🔴 JSON 을 거치면 라인 키가 "7.5" 가 된다 — 그대로 두면 못 찾는다."""
    conn = _Conn(probs={"totals": {"7.5": {"Under": 0.60}}})
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0}, redis=None)
    assert [a for s, a in conn.saved if "structure_pick" in s]


@pytest.mark.asyncio
async def test_우리_확률이_없으면_안_만든다(no_llm):
    """🔴 반대 위험 — λ 가 없는 경기는 종전대로 총점 후보가 없다."""
    conn = _Conn(probs=None)
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0}, redis=None)
    hits = [a for s, a in conn.saved if "structure_pick" in s]
    assert not hits or json.loads(hits[-1][1])["market"] != "totals"


@pytest.mark.asyncio
async def test_파생_배당이_없으면_안_만든다(no_llm):
    conn = _Conn(snaps=[])
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0}, redis=None)
    assert not [a for s, a in conn.saved if "structure_pick" in s]


def test_종목으로_안_가른다():
    src = inspect.getsource(PL.record_confirm_and_analysis)
    blk = src.split("ours_totals", 1)[0][-800:]
    for bad in ("baseball", "BASEBALL_SPORTS"):
        assert bad not in blk, bad


def test_SELECT에_칸이_있다():
    src = inspect.getsource(PL.record_confirm_and_analysis)
    assert "model_probs" in src.split("FROM pick_ledger", 1)[0]
