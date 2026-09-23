"""[STR-2] `starter_recent3` 가 **교체 메모**만 보고 있었다.

🔴 변수 이름은 "선발 최근 3등판"인데 ⑤는 `starter_change_notes` 만 읽는다.
   선발이 안 바뀐 경기는 언제나 `unknown` 이다 — 그게 대부분이다.
🔴 자료는 DB 에 있다(실측 2026-09-20):
     Hayden Wesneski 선발 등판 7행 · Michael McGreevy 6행 · Brandon Pfaadt 6행
   내보내기는 이미 그 값을 쓴다(`_STARTER_SQL`, STR-1 의 `recent6`).
🔴 **상대 선발**을 본다. 우리 픽이 원정이면 홈 선발이 우리를 막는 쪽이다 —
   그쪽 최근 등판이 우리 득점 전망을 바꾼다.
⚠️ 교체 메모도 계속 본다 — 둘은 다른 사실이고 둘 다 증거다.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.flow.ctx import Ctx
from app.flow.state import State


def _st(pick="away"):
    s = State(run_id="r", game_id="1", sport="baseball", league="MLB",
              home="HOME", away="AWAY", kickoff_utc="2026-09-20T01:00:00Z")
    s.hyp_side = s.pick_side = pick   # [SIDE-2] ⑤는 조사 방향을 본다
    s.n04_hyp = [{"id": "H", "vars": [{"var": "starter_recent3", "is_core": True}]}]
    return s


class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.seen = []

    async def fetch(self, sql, *a):
        self.seen.append((sql, a))
        return self.rows if "pitcher_appearances" in sql else []


def test_상대_선발_이름을_고른다():
    """🔴 픽이 원정이면 **홈 선발**이 상대다."""
    from app.flow.nodes.n05_evidence import opp_starter_of

    assert opp_starter_of(_st("away"), {"home": "A", "away": "B"}) == "A"
    assert opp_starter_of(_st("home"), {"home": "A", "away": "B"}) == "B"
    assert opp_starter_of(_st("away"), {"home": None}) is None


@pytest.mark.asyncio
async def test_교체가_없어도_최근등판을_증거로_낸다():
    from app.flow.nodes import n05_evidence as N

    rows = [{"d": datetime(2026, 9, 14, tzinfo=UTC).date(), "innings": 6.0,
             "er": 1, "k": 7, "bb": 1, "opponent": "X"},
            {"d": datetime(2026, 9, 9, tzinfo=UTC).date(), "innings": 5.0,
             "er": 4, "k": 3, "bb": 3, "opponent": "Y"}]
    st = _st("away")
    ctx = Ctx(pool=_Pool(rows), inject={"starter_notes": [],
                                        "absences": [], "extract": {},
                                        "starters": {"home": "Ace", "away": "Joe"}})
    out = await N.run(st, ctx)
    got = [e for e in out.n05_evidence if e["var"] == "starter_recent3"]
    assert got, "교체가 없다고 증거가 0이면 안 된다"
    assert "6.0이닝" in got[0]["raw_excerpt"], got[0]


@pytest.mark.asyncio
async def test_등판_기록이_없으면_지어내지_않는다():
    from app.flow.nodes import n05_evidence as N

    st = _st("away")
    ctx = Ctx(pool=_Pool([]), inject={"starter_notes": [], "absences": [],
                                      "extract": {},
                                      "starters": {"home": "Ace", "away": "Joe"}})
    out = await N.run(st, ctx)
    assert [e for e in out.n05_evidence if e["var"] == "starter_recent3"] == []
