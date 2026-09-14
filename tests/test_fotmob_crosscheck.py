"""FOT-3 — 결장 교차검증: FotMob 정본 · Transfermarkt 2순위 (사용자 지시).

🔴 API-Football 은 사슬에서 뺐다. 무료 플랜이 현 시즌을 막는다(실측 원문:
   "Free plans do not have access to this season, try from 2022 to 2024").
"""
import ast
import inspect

from app import pipeline
from app.collectors import satellite_soccer as SOC


def _jg(home_un=None, away_un=None, missing=None):
    def side(un):
        d = {"starters": [], "unavailable": un}
        return d

    return {"home": "Torino FC", "away": "AS Roma",
            "fotmob": {"home": side(home_un), "away": side(away_un),
                       "missing": list(missing or [])}}


def _idx(**teams):
    return {SOC.tm_key(k): v for k, v in teams.items()}


def test_FotMob_에_있으면_그것이_정본이다():
    jg = _jg(home_un=[{"name": "Ché Adams"}])
    idx = _idx(**{"Torino FC": [{"선수": "Ché Adams", "부상": "근육", "복귀": ""}]})

    rep = SOC.cross_check_unavailable(jg, idx)

    assert jg["fotmob"]["home"]["unavailable"] == [{"name": "Ché Adams"}]
    assert jg["fotmob"]["home"].get("unavailable_src") == "fotmob"
    assert not jg["fotmob"]["home"].get("conflict")
    assert "fotmob 1명" in rep["home"]


def test_명단이_갈리면_충돌로_표시한다():
    jg = _jg(home_un=[{"name": "Ché Adams"}])
    idx = _idx(**{"Torino FC": [{"선수": "Cesare Casadei", "부상": "근육", "복귀": ""}]})

    SOC.cross_check_unavailable(jg, idx)

    assert jg["fotmob"]["home"]["conflict"] is True
    # 🔴 그래도 정본은 FotMob 이다 — 덮어쓰지 않는다.
    assert jg["fotmob"]["home"]["unavailable"] == [{"name": "Ché Adams"}]


def test_FotMob_이_None_이면_TM_으로_메운다():
    jg = _jg(away_un=None, missing=["away 결장 명단 미제공"])
    idx = _idx(**{"AS Roma": [{"선수": "Paulo Dybala", "부상": "햄스트링",
                               "복귀": "2026-10-01"}]})

    rep = SOC.cross_check_unavailable(jg, idx)

    got = jg["fotmob"]["away"]["unavailable"]
    assert [x["name"] for x in got] == ["Paulo Dybala"]
    assert jg["fotmob"]["away"]["unavailable_src"] == "transfermarkt"
    assert jg["fotmob"]["missing"] == [], "메웠으면 missing 에서 빠진다"
    assert "transfermarkt 1명" in rep["away"]


def test_둘_다_없으면_모른다로_남긴다():
    """🔴 0 으로 쓰지 않는다."""
    jg = _jg(away_un=None, missing=["away 결장 명단 미제공"])

    rep = SOC.cross_check_unavailable(jg, {})

    assert jg["fotmob"]["away"]["unavailable"] is None
    assert jg["fotmob"]["missing"] == ["away 결장 명단 미제공"]
    assert rep["away"] == "모름(유지)"


def test_API_Football_실호출은_0이다():
    """키는 두되 **실호출 0** — 무료 플랜이 현 시즌을 막는다(실측).

    ⚠️ 목 모드 경로는 남긴다. 네트워크를 타지 않고, 테스트·개발의 일정
       소스가 그것이다(이 줄을 지우자 축구 파이프라인 테스트가 5경기 → 1경기).
    """
    src = inspect.getsource(pipeline.build_analysis)
    tree = ast.parse(src.lstrip())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "APIFootballClient")
    # 그 호출을 감싸는 if 가 **목 모드 조건**이어야 한다.
    guards = [n for n in ast.walk(tree)
              if isinstance(n, ast.If)
              and "mock_football" in ast.dump(n.test)
              and node in list(ast.walk(n))]
    assert guards, "API-Football 호출이 목 모드 밖에서 돈다"
