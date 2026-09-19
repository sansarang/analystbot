"""[ODN-2] MLB 팀토탈·F5 를 실제로 싣는다.

🔴 실측(2026-09-19, odds-api.net 1회 호출 · MLB 신시내티-컵스 3,664행):
     team total  · full time   182행   ← 팀토탈이 **온다**
     total       · 5 innings    40행   ← F5 총점이 **온다**
     moneyline   · 5 innings    16행   ← F5 승패도 온다
     handicap    · 5 innings    47행
   그런데 우리 수집기가 둘 다 버리고 있었다 —
     `LEAGUES` 에 MLB 가 없고, `PERIOD = "full time"` 이 5이닝을 버린다.
🔴 ESPN 쪽은 이것을 **주지 않는다**(실측: odds 항목 키가
   moneyline·spread·overUnder 뿐이고 `teamtotal`·`5 innings` 문자열 0건).
   그래서 "ESPN 으로 이미 된다"는 종전 주석의 전제가 이 두 마켓에는 틀렸다.
🔴 5이닝은 **다른 시장이다.** 정규 라인과 같은 칸에 넣으면 디빅이 통째로
   어긋난다(종전 주석이 옳다) — 그래서 `_f5` 로 **칸을 나눈다.**
"""
from __future__ import annotations


def _row(bet_type, period, line, *, side=None, odds=1.9, book="3et"):
    return {"bet_type": bet_type, "period": period, "line": line,
            "side": side, "odds": odds, "bookmaker": book,
            "is_available": True}


def test_MLB_가_리그_목록에_있다():
    from app.collectors.oddsapinet import LEAGUES

    assert LEAGUES.get("mlb") == "MLB", LEAGUES


def test_정규_팀토탈이_실린다():
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("team total", "full time", "over 4.5", side="away")],
                  home="Reds", away="Cubs")
    assert got == [{"book": "3et", "market": "team_totals",
                    "side": "Cubs Over", "line": 4.5, "odds": 1.9}], got


def test_5이닝은_칸이_다르다():
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("total", "5 innings", "over 4.5"),
                   _row("total", "full time", "over 8.5")],
                  home="Reds", away="Cubs")
    markets = sorted(r["market"] for r in got)
    assert markets == ["totals", "totals_f5"], got


def test_5이닝_승패도_싣는다():
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("moneyline", "5 innings", None, side="home")],
                  home="Reds", away="Cubs")
    assert got == [{"book": "3et", "market": "h2h_f5", "side": "Reds",
                    "line": None, "odds": 1.9}], got


def test_정규_승패는_여전히_안_싣는다():
    """⚠️ oddsportal 이 이미 준다 — 두 소스가 같은 칸을 채우면 디빅이 흔들린다."""
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("moneyline", "full time", None, side="home")],
                  home="Reds", away="Cubs")
    assert got == [], got


def test_1이닝_3이닝_7이닝은_버린다():
    """🔴 실측에 1st·3·7 이닝도 온다. **아는 칸만 싣는다** — 모르는 기간을
       실으면 그게 어느 시장인지 읽는 쪽이 알 수 없다."""
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("total", "1st inning", "over 0.5"),
                   _row("total", "3 innings", "over 1.5"),
                   _row("total", "7 innings", "over 6.5")],
                  home="Reds", away="Cubs")
    assert got == [], got


def test_홀짝은_여전히_버린다():
    from app.collectors.oddsapinet import to_rows

    got = to_rows([_row("team total", "full time", "even", side="away")],
                  home="Reds", away="Cubs")
    assert got == [], got
