"""SCT-2 — 딥서치 설정: 현지어 검색어 · 소스 화이트리스트 · 추출 스키마.

지시문 Phase 4. **세 가지만, 현지어로, 화이트리스트에서.**

🔴 위성(층1)의 `_SOCCER_TERMS = ""` 는 **건드리지 않는다.** 그건 다음
   뉴스검색 채널이고, 검색어를 붙였더니 맥도날드·프로야구 기사가 왔다는
   실측(2026-09-12)이 있다. 여기 만드는 검색어는 **딥서치(층2)** 채널의 것이다.
"""
import pytest

from app.engine import scout_config as SC


# ── 검색어 표

def test_우리_리그가_전부_있다():
    """🔴 목록을 손으로 적지 않는다 — `leagues.LEAGUES` + 야구 3종목."""
    from app.leagues import LEAGUES

    want = set(LEAGUES) | {"mlb", "kbo", "npb"}
    assert want <= set(SC.SEARCH_TERMS), want - set(SC.SEARCH_TERMS)


def test_리그마다_두_개다():
    for lg, terms in SC.SEARCH_TERMS.items():
        assert len(terms) == 2, (lg, terms)


def test_팀_자리표시자가_있다():
    for lg, terms in SC.SEARCH_TERMS.items():
        for t in terms:
            assert "{team}" in t, (lg, t)


def test_지시문_현지어_그대로다():
    assert SC.SEARCH_TERMS["la_liga"] == [
        "{team} alineación oficial", "{team} bajas lesionados"]
    assert SC.SEARCH_TERMS["serie_a"] == [
        "{team} probabili formazioni", "{team} infortunati"]
    assert SC.SEARCH_TERMS["bundesliga"] == [
        "{team} Aufstellung", "{team} Ausfälle"]
    assert SC.SEARCH_TERMS["j1"] == ["{team} スタメン", "{team} 負傷 欠場"]
    assert SC.SEARCH_TERMS["npb"] == ["{team} スタメン", "{team} 予告先発"]
    assert SC.SEARCH_TERMS["kbo"] == ["{team} 선발 라인업", "{team} 엔트리 말소"]


def test_질의를_만들면_팀이_들어간다():
    q = SC.queries("la_liga", "Celta Vigo")
    assert q == ["Celta Vigo alineación oficial", "Celta Vigo bajas lesionados"]


def test_경기당_상한은_팀당_하나씩_둘이다():
    """지시문: 경기당 검색 2회 상한(팀당 1). 양 팀 모두 검색."""
    assert SC.PER_TEAM_QUERIES == 1
    assert SC.PER_GAME_FETCH == 3


# ── 토르 경로의 한계 (한국어는 못 나간다)

def test_한국어_검색어는_토르로_못_나간다는_것을_표가_안다():
    """🔴 `tor_search.is_tor_safe_query` 가 한국어를 거부한다. 그 리그는
       다른 통로(그라운딩·다음)로 가야 한다 — 표가 그 사실을 들고 있어야
       호출부가 조용히 0건을 받지 않는다."""
    from app.collectors.tor_search import is_tor_safe_query

    for lg in ("kbo", "kleague1"):
        assert SC.tor_safe(lg) is False
        assert not is_tor_safe_query(SC.queries(lg, "X")[0])
    for lg in ("la_liga", "epl", "serie_a"):
        assert SC.tor_safe(lg) is True


# ── 소스 화이트리스트

def test_등급이_넷이다():
    assert set(SC.SOURCES) == {"tier1_official", "tier2_local",
                               "tier3_aggregator", "blocked"}


def test_공식_도메인은_비어_있고_그게_기록돼_있다():
    """🔴 구단 공식 도메인 100여 개를 추측해 채우지 않는다(티어 표와 같다)."""
    assert SC.SOURCES["tier1_official"] == []
    txt = open("config/sources.yaml", encoding="utf-8").read()
    assert "사용자가 채운다" in txt


def test_지시문이_준_예시가_들어_있다():
    local = SC.SOURCES["tier2_local"]
    agg = SC.SOURCES["tier3_aggregator"]
    for d in ("grootheerenveen.nl", "calciolecce.it", "losclive.com"):
        assert d in local, d
    for d in ("sportsmole.co.uk", "whoscored.com", "fotmob.com"):
        assert d in agg, d


@pytest.mark.parametrize("url,want", [
    ("https://grootheerenveen.nl/a/b", 2),
    ("https://www.sportsmole.co.uk/x", 3),
    ("https://news.example.com/x", 9),
])
def test_등급_판정은_도메인으로_한다(url, want):
    assert SC.rank(url) == want


def test_차단_도메인은_0이다():
    SC.SOURCES["blocked"].append("spam-affiliate.example")
    try:
        assert SC.rank("https://spam-affiliate.example/x") == 0
    finally:
        SC.SOURCES["blocked"].remove("spam-affiliate.example")


def test_상위_세_개만_고른다():
    urls = ["https://news.example.com/1",          # 9
            "https://whoscored.com/2",             # 3
            "https://grootheerenveen.nl/3",        # 2
            "https://calciolecce.it/4",            # 2
            "https://fotmob.com/5"]                # 3
    got = SC.pick_sources(urls)
    assert len(got) == SC.PER_GAME_FETCH
    assert got[0].startswith("https://grootheerenveen.nl")
    assert "news.example.com" not in " ".join(got)


# ── 추출 스키마

def test_스키마_칸이_지시문_그대로다():
    assert set(SC.EXTRACT_SCHEMA) == {
        "team", "out", "doubt", "predicted_xi", "last3", "notes",
        "source", "fetched_at"}


def test_스키마_밖의_것은_버린다():
    raw = {"team": "Heerenveen", "out": ["A"], "doubt": [],
           "predicted_xi": [], "last3": ["L 2-3"], "notes": "x",
           "source": "a.nl", "fetched_at": "t",
           "전적": "5승", "감독코멘트": "이길 것", "팬반응": "분노"}
    got = SC.validate(raw)
    assert set(got) == set(SC.EXTRACT_SCHEMA)
    assert "전적" not in got


def test_notes는_한_줄이다():
    got = SC.validate({"team": "X", "notes": "a\nb\nc"})
    assert "\n" not in got["notes"]


def test_명단은_문자열_목록이다():
    got = SC.validate({"team": "X", "out": ["A", 3, None, "  B  "]})
    assert got["out"] == ["A", "3", "B"]


def test_팀이_없으면_버린다():
    """🔴 어느 팀 것인지 모르는 추출은 쓸 수 없다."""
    assert SC.validate({"out": ["A"]}) is None


def test_빈_추출도_유효하다():
    """⚠️ 결장자가 없는 것과 못 찾은 것은 다르다 — 빈 목록은 사실이다."""
    got = SC.validate({"team": "X"})
    assert got["out"] == [] and got["predicted_xi"] == []
