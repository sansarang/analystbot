"""PA-27-b 계약 — 확정 XI 가 예상치를 **대체한다. 얹지 않는다.**

🔴 `주전결장`(이력의 주전이 오늘 명단에 없다)과 `라인업결장`(예상 XI 에 있던
   선수가 공식 XI 에 없다)은 기준선이 다르지만 **같은 선수가 양쪽에 걸린다.**
   함께 두면 한 사람을 두 번 센다 —
   실측 재현: `{'주전결장': -1.5, '라인업결장:home': -3.0}` 이 함께 남았다.

🔴 딥서치 근거(2026-09-17):
   "예상 라인업은 구단이 팀을 발표할 때까지만 유효하고, 그 뒤에는 **확정
    11명으로 대체된다**" — Sportmonks Predicted Lineups
   현대 Elo 계열도 확정 라인업을 얹지 않고 갈아끼운다 — PlayerElo · FanPick
   결장 반영은 "그 선수 기여를 빼고 대체자를 더한다" — Footy Forecast
"""
import pytest

from app.engine import rejudge as RJ

PLAYERS = {"A": {"market_value": 100}, "B": {"market_value": 100}}
TT = 1100


def _run(diff, adj, p=0.55):
    return RJ.reweigh(adj=dict(adj), p_code=p, diff=diff, players=PLAYERS,
                      team_total_value=TT, grade="중")


def test_확정_XI가_주전결장을_대체한다():
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"주전결장": -1.5})
    assert "주전결장" not in g["adj_after"], "두 축이 함께 남았다 — 이중 계산"
    assert "라인업결장:home" in g["adj_after"]
    assert g["replaced_axis"] == "주전결장"


def test_대체_사실이_사유에_남는다():
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"주전결장": -1.5})
    assert "대체" in g["why"]


def test_공식_XI가_없으면_유지한다():
    """🔴 반대 위험 — 모르면 안 바꾼다."""
    g = _run(None, {"주전결장": -1.5})
    assert g["adj_after"]["주전결장"] == -1.5
    assert g.get("replaced_axis") is None


def test_복귀만_있으면_대체하지_않는다():
    """🔴 결장이 **확인됐을 때만** 갈아끼운다."""
    g = _run({"home": {"bench_notable": [], "surprise_in": ["A"]}},
             {"주전결장": -1.5})
    assert g["adj_after"]["주전결장"] == -1.5
    assert g.get("replaced_axis") is None


def test_결장과_무관한_축은_안_건드린다():
    """🔴 반대 위험 — 대체 대상은 결장 축 하나뿐이다."""
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"주전결장": -1.5, "이동연전": -1.0, "필승조연투": -2.5})
    assert g["adj_after"].get("이동연전") == -1.0
    assert g["adj_after"].get("필승조연투") == -2.5


def test_주전결장이_없으면_대체_표시도_없다():
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"이동연전": -1.0})
    assert g.get("replaced_axis") is None
    assert g["adj_after"].get("이동연전") == -1.0


def test_대체_뒤_확률이_결장_방향이다():
    """홈 결장이면 홈 확률이 내려간다."""
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"주전결장": -1.5})
    assert g["p_code_after"] < 0.55


def test_원정_결장은_홈에_유리하다():
    g = _run({"away": {"bench_notable": ["A", "B"], "surprise_in": []}},
             {"주전결장": -1.5})
    assert g["p_code_after"] > 0.55


def test_축_이름을_손으로_안_적었다():
    """🔴 사본 금지 — `주전결장` 은 prob.ADJ_RULES 의 키다."""
    from app.engine import prob as P
    assert RJ.KEY_BASE_OUT in P.ADJ_RULES["soccer"]
    assert RJ.KEY_BASE_OUT in P.ADJ_RULES["baseball"]


@pytest.mark.parametrize("sport", ["soccer", "baseball"])
def test_두_종목_모두_같은_축_이름을_쓴다(sport):
    from app.engine import prob as P
    assert P.ADJ_RULES[sport][RJ.KEY_BASE_OUT][0] == "out_starters"
