"""U6 — 표적 수집. need 가 정한 것만 쓰고, 8칸을 다 저장한다.

🔴 실측 2026-09-15(FotMob matchDetails 6049978):
     starters[].marketValue = 1173408 · totalStarterMarketValue 가시마 6,352,468
     matchFacts.teamForm → home ['W','W','L','L','L'] · away ['D','W','D','D','L']
   원자료에 다 있는데 parse_lineup 이 버리고 있었다.
   추출 8칸 중 doubt·last3·midweek·notes 가 저장되지 않아 U7 이 맞출 대상이 없었다.
"""
from __future__ import annotations

import inspect

import pytest

from app.collectors import fotmob as FM
from app.collectors import parsers as PR
from app.collectors import satellite as SAT
from app.engine import hypothesis as H
from app.engine import scout_config as SC

DETAILS = {"content": {"lineup": {
    "lineupType": "standard", "source": "opta", "matchId": 1,
    "homeTeam": {"id": 1, "name": "H", "formation": "4-4-2",
                 "totalStarterMarketValue": 6352468, "averageStarterAge": 28.8,
                 "starters": [{"id": 9, "name": "P", "marketValue": 1173408,
                               "positionId": 11, "shirtNumber": "1"}],
                 "subs": [{"id": 8, "name": "S"}], "unavailable": []},
    "awayTeam": {"id": 2, "name": "A", "formation": "4-3-3",
                 "totalStarterMarketValue": 4098733,
                 "starters": [{"id": 7, "name": "Q", "marketValue": 221933}],
                 "subs": []}},
    "matchFacts": {"teamForm": [
        [{"resultString": "W", "date": {"utcTime": "2026-09-01T00:00Z"}}],
        [{"resultString": "D", "date": {"utcTime": "2026-09-02T00:00Z"}}]]}}}


# ── FotMob

def test_시장가치가_선수별로_저장된다():
    lu = FM.parse_lineup(DETAILS)
    p = lu["home"]["starters"][0]
    assert p["market_value"] == 1173408
    assert p["position_id"] == 11 and p["shirt"] == "1"


def test_팀_총가치가_저장된다():
    lu = FM.parse_lineup(DETAILS)
    assert lu["home"]["total_market_value"] == 6352468
    assert lu["away"]["total_market_value"] == 4098733
    assert lu["home"]["avg_age"] == 28.8


def test_기존_starters_키가_그대로다():
    """🔴 반대 위험 — 읽는 곳이 넷이다. 더하기만 한다."""
    p = FM.parse_lineup(DETAILS)["home"]["starters"][0]
    assert p["id"] == 9 and p["name"] == "P"


def test_최근5가_양팀_저장된다():
    lu = FM.parse_lineup(DETAILS)
    assert [x["result"] for x in lu["last5"]["home"]] == ["W"]
    assert [x["result"] for x in lu["last5"]["away"]] == ["D"]


def test_teamForm이_없으면_빈목록():
    """⚠️ 0승으로 읽지 않는다."""
    assert FM.parse_form({}) == {"home": [], "away": []}
    assert FM.parse_form({"content": {"matchFacts": {}}}) == {"home": [], "away": []}


# ── 추출 8칸

def test_추출_8칸이_전부_저장된다():
    box = SAT.fill_schema({"out": ["A"]})
    assert set(H.FIELDS) <= set(box)
    assert box["out"] == ["A"]
    for f in ("doubt", "last3", "midweek", "notes"):
        assert f in box and box[f] is None


def test_없는_칸은_None이지_빈값이_아니다():
    """🔴 'out=[]' 는 결장 0명이고 'out=None' 은 안 봤다는 뜻이다."""
    box = SAT.fill_schema({})
    assert box["out"] is None and box["out"] != []


# ── need 한정

def test_need를_받으면_그것만_남는다():
    box = SAT.fill_schema({"out": ["A"], "midweek": "UCL", "notes": "x",
                           "last3": "WWL"})
    got = SAT.apply_need(box, "home", ["home.out", "home.midweek"])
    assert got["out"] == ["A"] and got["midweek"] == "UCL"
    assert got["notes"] is None and got["last3"] is None
    assert sorted(got["collected_extra"]) == ["last3", "notes"]


def test_need를_못_받으면_종전대로_전부():
    """🔴 반대 위험 — 굶기지 않는다. need=None(미배선)과 []( 보드)는 다르다."""
    box = SAT.fill_schema({"out": ["A"], "notes": "x"})
    got = SAT.apply_need(box, "home", None)
    assert got["out"] == ["A"] and got["notes"] == "x"
    assert "collected_extra" not in got


def test_need가_빈목록이면_전부_뺀다():
    box = SAT.fill_schema({"out": ["A"], "notes": "x"})
    got = SAT.apply_need(box, "home", [])
    assert got["out"] is None and got["notes"] is None
    assert sorted(got["collected_extra"]) == ["notes", "out"]


def test_상대편_need는_내_칸에_안_쓴다():
    box = SAT.fill_schema({"out": ["A"]})
    got = SAT.apply_need(box, "home", ["away.out"])
    assert got["out"] is None, "원정 need 로 홈 칸을 남겼다"


def test_extract가_need를_받는다():
    sig = inspect.signature(SAT.extract_game_facts)
    assert "need" in sig.parameters
    assert sig.parameters["need"].default is None


# ── tier0

def test_tier0이_tier1보다_앞선다():
    assert SC.RANK_PRIMARY == 0
    assert SC.RANK_PRIMARY < 1 < 2 < 3 < SC.RANK_UNLISTED < SC.RANK_UNKNOWN


def test_등급_순서가_뒤집히지_않는다():
    """🔴 반대 위험 — 순서가 깨지면 fetch 우선순위가 뒤집힌다."""
    import yaml
    import pathlib

    doc = yaml.safe_load(pathlib.Path("config/sources.yaml")
                         .read_text(encoding="utf-8"))
    assert "tier0_primary" in doc
    assert isinstance(doc["tier0_primary"], dict)
    # 값은 사용자가 채운다 — 지금은 비어 있는 것이 정상이다
    assert all(isinstance(v, list) for v in doc["tier0_primary"].values())


# ── 파서

@pytest.mark.parametrize("url,want", [
    ("https://www.fantacalcio.it/x", "parse_fantacalcio"),
    ("https://ligainsider.de/y", "parse_ligainsider"),
    ("https://www.sportsmole.co.uk/z", "parse_sportsmole"),
    ("https://gazzetta.it/q", None),
])
def test_도메인별_파서가_고른다(url, want):
    fn = PR.for_domain(url)
    assert (fn.__name__ if fn else None) == want


def test_파서가_실패하면_None이다():
    """🔴 반대 위험 — 실패를 '없음'으로 치면 LLM 경로가 막힌다."""
    assert PR.try_parse("https://www.fantacalcio.it/x", "") is None
    assert PR.try_parse("https://gazzetta.it/q", "<b>x</b>") is None


def test_파서가_채우면_out이_나온다():
    html = ('<div>Indisponibili <ul><li title="Mario Rossi"></li>'
            '<li title="Luca Bianchi"></li></ul></div>')
    got = PR.try_parse("https://www.fantacalcio.it/x", html)
    assert got and got["source_parser"] == "fantacalcio"
    assert "Mario Rossi" in got["out"] and "Luca Bianchi" in got["out"]


def test_파서는_순수함수다():
    src = inspect.getsource(PR)
    for bad in ("httpx", "asyncpg", "get_pool", "await "):
        assert bad not in src, bad


# ── snippet_level

@pytest.mark.parametrize("tier,box,want", [
    (0, {}, False), (1, {}, False), (2, {}, False),
    (3, {}, True), (4, {}, True), (9, {}, True),
    (3, {"out": ["A"]}, False),
    (4, {"last3": "WWL"}, False),
    (None, {}, False),
])
def test_snippet_level은_tier3이상_수치없음(tier, box, want):
    assert SAT.snippet_level(tier, SAT.fill_schema(box)) is want
