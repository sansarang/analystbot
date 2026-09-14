"""D1-5 — ESPN 축구 배당(core API) · 게이트 대상만 (사용자 지시).

🔴 주소는 실측으로 갈렸다(2026-09-14):
     site.api.espn.com  → 403 Access Denied (ita.1·esp.1·eng.1 전부)
     sports.core.api.espn.com → 200 · DraftKings home -500 · away 1100 · draw 500
🔴 **축구는 미국식 배당만 온다.** 야구(decimal)와 경로를 섞지 않는다.
"""
import pytest

from app.collectors import espn_odds as E

ITEM = {"provider": {"name": "DraftKings", "id": "100"},
        "homeTeamOdds": {"moneyLine": -500},
        "awayTeamOdds": {"moneyLine": 1100},
        "drawOdds": {"moneyLine": 500.0}}


def test_미국식을_소수배당으로_환산한다():
    """항등식이라 추측이 아니다 — −a → 1+100/a · +b → 1+b/100."""
    assert E.from_american(-500) == 1.2
    assert E.from_american(1100) == 12.0
    assert E.from_american(500) == 6.0
    assert E.from_american(0) is None and E.from_american(None) is None


def test_홈_무_원정_세_칸을_읽는다():
    rows = E.parse_soccer_odds(ITEM, "Como", "Parma")

    assert {r["side"]: r["odds"] for r in rows} == {"Como": 1.2, "Parma": 12.0,
                                                    "Draw": 6.0}
    assert {r["book"] for r in rows} == {"draftkings"}


def test_라이브_북은_버린다():
    """🔴 실사고: 7:0 앞선 경기의 라이브 배당이 섞여 괴리가 거짓이 됐다."""
    live = dict(ITEM, provider={"name": "DraftKings - Live Odds"})

    assert E.parse_soccer_odds(live, "Como", "Parma") == []


def test_없는_칸은_만들지_않는다():
    """0 으로 채우지 않는다."""
    partial = {"provider": {"name": "Bet 365"}, "homeTeamOdds": {"moneyLine": -200},
               "awayTeamOdds": {}, "drawOdds": {"summary": "5/1"}}

    rows = E.parse_soccer_odds(partial, "Como", "Parma")

    assert [r["side"] for r in rows] == ["Como"]
    assert rows[0]["book"] == "bet365", "공백을 지운 이름"


@pytest.mark.asyncio
async def test_게이트_대상이_없으면_요청을_하지_않는다(monkeypatch):
    """🔴 예산 규칙이 여기서 지켜진다 — 게이트 밖 경기는 안 친다."""
    called = []

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **k):
            called.append(url)
            raise AssertionError("요청하면 안 된다")

    monkeypatch.setattr("httpx.AsyncClient", _C)

    assert await E.fetch_soccer("serie_a", "20260914", only_names=set()) == {}
    assert await E.fetch_soccer("serie_a", "20260914") == {}
    assert not called


def test_리그_코드는_사용자가_준_여덟이다():
    assert E.SOCCER_LEAGUES["serie_a"] == "ita.1"
    assert set(E.SOCCER_LEAGUES.values()) == {"eng.1", "esp.1", "ita.1", "ger.1",
                                              "fra.1", "ned.1", "kor.1", "jpn.1"}
    assert E.SOCCER_MAX_REQ_PER_GAME == 10
