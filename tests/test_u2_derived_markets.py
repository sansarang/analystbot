"""U2 — 파생 시장(핸디·U/O) 저장 + manual 북.

🔴 실측 2026-09-15 (ESPN core · esp.1 · Espanyol at Rayo Vallecano):
     spread=-0.5 · overUnder=2.5 · overOdds=-110 · underOdds=-115
     homeTeamOdds.spreadOdds=+120 · awayTeamOdds.spreadOdds=-170
     moneyLine 135/210/240 · open 블록 포함
   값이 다 있는데 parse_soccer_odds 는 h2h 3행만 내고 버렸다.
   → S8 라인 이동·S9 구조 픽이 통째로 불가능했다.
"""
from __future__ import annotations

import inspect

import pytest

from app.collectors import espn_odds as E
from tools import manual_odds as MO

HOME, AWAY = "Rayo Vallecano", "Espanyol"
ITEM = {
    "provider": {"name": "DraftKings"},
    "spread": -0.5, "overUnder": 2.5, "overOdds": -110.0, "underOdds": -115.0,
    "homeTeamOdds": {"moneyLine": 135, "spreadOdds": 120.0,
                     "open": {"pointSpread": {"alternateDisplayValue": "-0.5",
                                              "american": "-105"},
                              "moneyLine": {"american": "+140"}}},
    "awayTeamOdds": {"moneyLine": 210, "spreadOdds": -170.0},
    "drawOdds": {"moneyLine": 240.0},
}


def _rows():
    return E.parse_soccer_odds(ITEM, HOME, AWAY)


def test_spread와_overunder가_행이_된다():
    mk = {r["market"] for r in _rows()}
    assert {"h2h", "spreads", "totals"} <= mk, mk


def test_h2h_행이_줄지_않는다():
    """🔴 반대 위험 — 파생을 더하는 것이지 바꾸는 게 아니다."""
    h = [r for r in _rows() if r["market"] == "h2h" and not r.get("snap_tag")]
    assert len(h) == 3
    assert {r["side"] for r in h} == {HOME, "Draw", AWAY}
    # 미국식 → 소수 (CHN 때 만든 축구 전용 경로 재사용)
    got = {r["side"]: r["odds"] for r in h}
    assert got[HOME] == E.from_american(135)
    assert got[AWAY] == E.from_american(210)
    assert got["Draw"] == E.from_american(240.0)


def test_핸디_부호가_양쪽에_반대로_붙는다():
    """홈 −0.5 면 원정은 +0.5. 둘 다 있어야 디빅이 된다."""
    sp = {r["side"]: r for r in _rows()
          if r["market"] == "spreads" and not r.get("snap_tag")}
    assert sp[HOME]["line"] == -0.5
    assert sp[AWAY]["line"] == 0.5
    assert sp[HOME]["odds"] == E.from_american(120.0)
    assert sp[AWAY]["odds"] == E.from_american(-170.0)


def test_언더오버는_한_라인에_양쪽():
    ou = {r["side"]: r for r in _rows() if r["market"] == "totals"}
    assert set(ou) == {"Over", "Under"}
    assert ou["Over"]["line"] == ou["Under"]["line"] == 2.5
    assert ou["Over"]["odds"] == E.from_american(-110.0)
    assert ou["Under"]["odds"] == E.from_american(-115.0)


# ── 🔴 반대 위험: 거짓 개장가

def test_open은_open_블록에서만_붙는다():
    rows = _rows()
    tagged = [r for r in rows if r.get("snap_tag")]
    assert tagged, "ESPN 이 open 을 주는데 안 쓴다"
    assert all(r["snap_tag"] == "open" for r in tagged)
    # 현재가 행에는 절대 붙지 않는다
    now_rows = [r for r in rows if not r.get("snap_tag")]
    assert all("snap_tag" not in r for r in now_rows)
    # 값도 현재가와 달라야 한다(open +140 vs 현재 +135)
    o = next(r for r in tagged if r["market"] == "h2h")
    assert o["odds"] == E.from_american("+140") != E.from_american(135)


def test_open이_없으면_안_붙인다():
    item = {k: v for k, v in ITEM.items()}
    item["homeTeamOdds"] = {"moneyLine": 135, "spreadOdds": 120.0}
    assert not [r for r in E.parse_soccer_odds(item, HOME, AWAY) if r.get("snap_tag")]


def test_라이브_북은_그대로_버린다():
    item = dict(ITEM, provider={"name": "ESPN BET Live"})
    if E.is_live_book("espn bet live"):
        assert E.parse_soccer_odds(item, HOME, AWAY) == []


def test_only_names가_비면_요청_0():
    """🔴 예산 규칙 — 요청은 게이트 대상 + 빅매치만."""
    src = inspect.getsource(E.fetch_soccer)
    assert "if not code or not only_names" in src
    assert "요청 0" in src


# ── manual 도구

def test_manual_도구가_세_시장을_넣는다():
    rows = MO.rows_for(HOME, AWAY, h2h=[2.15, 3.24, 3.19],
                       ah=MO.parse_pair("-0.5:2.12/1.65"),
                       ou=MO.parse_pair("2.5:1.93/1.77"))
    by = {}
    for r in rows:
        by.setdefault(r["market"], []).append(r)
    assert sorted(by) == ["h2h", "spreads", "totals"]
    assert [r["odds"] for r in by["h2h"]] == [2.15, 3.24, 3.19]
    sp = {r["side"]: r for r in by["spreads"]}
    assert sp[HOME]["line"] == -0.5 and sp[AWAY]["line"] == 0.5
    assert sp[HOME]["odds"] == 2.12 and sp[AWAY]["odds"] == 1.65
    ou = {r["side"]: r for r in by["totals"]}
    assert ou["Over"]["line"] == ou["Under"]["line"] == 2.5


def test_manual은_book이_manual이다():
    """🔴 실소스와 섞이면 '이 값이 어디서 왔나'를 못 가린다."""
    rows = MO.rows_for(HOME, AWAY, h2h=[2.0, 3.0, 4.0])
    assert {r["book"] for r in rows} == {"manual"}
    assert MO.BOOK == "manual" and MO.PROVIDER == "manual"


def test_manual_태그는_표에_있는_값만():
    from app.engine.odds_move import BASELINE_ORDER

    src = inspect.getsource(MO.main)
    assert "BASELINE_ORDER" in src, "태그를 검사하지 않는다"
    assert "open_proxy" in BASELINE_ORDER


@pytest.mark.parametrize("spec,want", [
    ("-0.5:2.12/1.65", (-0.5, 2.12, 1.65)),
    ("2.5:1.93/1.77", (2.5, 1.93, 1.77)),
    ("0:1.90/1.90", (0.0, 1.90, 1.90)),
])
def test_입력_모양_파싱(spec, want):
    assert MO.parse_pair(spec) == want


@pytest.mark.asyncio
async def test_행의_snap_tag가_저장까지_간다():
    """🔴 실측 2026-09-15: ESPN 이 open 을 줬는데 DB 에는 open_proxy 가 붙었다.
    store_rows 가 행의 snap_tag 를 버리고, 뒤늦게 tag_open 이 대용품을 붙였다.
    진짜 개장가를 대용품으로 이름 붙이는 셈이었다."""
    from app.collectors import odds_free as OF

    seen = []

    class _Pool:
        async def execute(self, sql, *a):
            seen.append((sql, a))

        async def fetchrow(self, sql, *a):
            return None          # tag_open 은 아무것도 안 한다

    rows = [{"book": "dk", "market": "h2h", "side": "H", "odds": 2.0,
             "snap_tag": "open"},
            {"book": "dk", "market": "h2h", "side": "A", "odds": 3.0}]
    await OF.store_rows(_Pool(), 1, rows, "espn")
    ins = [a for sql, a in seen if "INSERT INTO odds_snapshots" in sql]
    assert len(ins) == 2
    assert "snap_tag" in [s for s, _ in seen if "INSERT" in s][0]
    assert ins[0][-1] == "open", ins[0]
    assert ins[1][-1] is None, "이름표 없는 행에 값이 붙었다"
