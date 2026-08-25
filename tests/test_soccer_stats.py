"""[§2-3] soccerdata 축구 데이터 — Perplexity 산문 파싱을 정식 소스로 대체.

정식 데이터 소스가 있는데 산문에서 xG를 긁을 이유가 없다.
다만 커버리지가 Big 5로 한정되므로, 미지원 리그는 기존 방식을 유지해야 한다.
"""

import pytest

from app.collectors.soccer_stats import (
    MIN_XG_MATCHES,
    SD_LEAGUES,
    UNSUPPORTED,
    _season_code,
    elo_ratings,
    merge_xg_into_research,
    supported,
    team_xg_windows,
)

pd = pytest.importorskip("pandas")


# ---------------------------------------------------------------- 커버리지

def test_big5_supported_others_fall_back():
    """[§2-3] 실조회 확인: soccerdata 기본 지원은 Big 5뿐이다.

    우리 화이트리스트 7개 중 4개만 커버되고 나머지는 Perplexity 수집을 유지한다.
    """
    for label in ("EPL", "라리가", "세리에A", "분데스리가"):
        assert supported(label), label
    for label in UNSUPPORTED:
        assert not supported(label), f"{label}은 미지원이어야 한다"
    assert set(UNSUPPORTED) == {"J1 리그", "덴마크 수페르리가", "K리그1"}


def test_league_ids_match_soccerdata_names():
    assert SD_LEAGUES["EPL"] == "ENG-Premier League"
    assert SD_LEAGUES["분데스리가"] == "GER-Bundesliga"


def test_season_code_and_backfill():
    """시즌 초 표본 부족을 메우기 위해 직전 시즌 코드를 만들 수 있어야 한다."""
    cur, prev = _season_code(), _season_code(None, 1)
    assert len(cur) == 4 and len(prev) == 4
    assert int(prev[:2]) == int(cur[:2]) - 1


# ---------------------------------------------------------------- xG 창

def _matches(rows):
    return pd.DataFrame(rows)


def _m(home, away, hxg, axg, date):
    return {"home_team": home, "away_team": away,
            "home_xg": hxg, "away_xg": axg, "date": date}


def test_xg_window_and_home_away_split():
    """[§2-3] 최근 6경기 xG/xGA + 홈/원정 스플릿."""
    rows = []
    for i in range(6):
        rows.append(_m("Arsenal", "Foe", 2.0, 0.5, f"2026-08-{10+i:02d}"))
    for i in range(6):
        rows.append(_m("Foe", "Arsenal", 1.0, 1.2, f"2026-07-{10+i:02d}"))
    w = team_xg_windows(_matches(rows))
    ars = w["Arsenal"]
    assert ars["matches"] == 6
    assert ars["xg6_home"] == pytest.approx(2.0)
    assert ars["xga6_home"] == pytest.approx(0.5)
    assert ars["xg6_away"] == pytest.approx(1.2)


def test_thin_split_is_omitted():
    """표본 3경기 미만이면 스플릿을 만들지 않는다 (거짓 정밀도 금지)."""
    rows = [_m("Arsenal", "Foe", 2.0, 0.5, "2026-08-10"),
            _m("Foe", "Arsenal", 1.0, 1.2, "2026-08-12")]
    ars = team_xg_windows(_matches(rows))["Arsenal"]
    assert "xg6_home" not in ars and "xg6_away" not in ars


def test_empty_frame_is_safe():
    assert team_xg_windows(pd.DataFrame()) == {}
    assert team_xg_windows(None) == {}
    assert elo_ratings(None) == {}


# ---------------------------------------------------------------- 병합

def test_merge_uses_venue_split():
    """[§2-3] 홈팀은 홈 스플릿, 원정팀은 원정 스플릿이 더 정확하다."""
    research = {}
    jg = {"home": "Arsenal", "away": "Brighton"}
    windows = {
        "Arsenal": {"xg6": 1.9, "xga6": 1.0, "matches": 6,
                    "xg6_home": 2.3, "xga6_home": 0.8},
        "Brighton": {"xg6": 1.5, "xga6": 1.3, "matches": 6,
                     "xg6_away": 1.1, "xga6_away": 1.7},
    }
    filled = merge_xg_into_research(research, jg, windows)
    assert research["home_recent_form"]["xg6"] == 2.3      # 홈 스플릿
    assert research["away_recent_form"]["xg6"] == 1.1      # 원정 스플릿
    assert len(filled) == 2


def test_merge_skips_thin_samples():
    """[§2-3] 표본이 얇으면 쓰지 않는다 — 모델이 보정을 건너뛴다."""
    research = {}
    windows = {"Arsenal": {"xg6": 3.0, "xga6": 0.1, "matches": MIN_XG_MATCHES - 1}}
    filled = merge_xg_into_research(research, {"home": "Arsenal", "away": "X"}, windows)
    assert filled == [] and research == {}


def test_merge_does_not_overwrite_existing():
    research = {"home_recent_form": {"xg6": 1.11, "form": "WWWWW"}}
    windows = {"Arsenal": {"xg6": 2.5, "xga6": 0.9, "matches": 6}}
    merge_xg_into_research(research, {"home": "Arsenal", "away": "X"}, windows)
    assert research["home_recent_form"]["xg6"] == 1.11     # 기존 값 보존


# ---------------------------------------------------------------- 모델 연결

def test_xg_feeds_soccer_lambda():
    """[§2-3] Understat xG가 λ 계산의 1차 입력이 된다."""
    from app.config import Settings
    from app.engine.scoring import soccer_lambdas

    s = Settings(_env_file=None)
    research = {}
    merge_xg_into_research(research, {"home": "Arsenal", "away": "Brighton"}, {
        "Arsenal": {"xg6": 2.2, "xga6": 0.8, "matches": 6},
        "Brighton": {"xg6": 1.0, "xga6": 1.8, "matches": 6},
    })
    r = soccer_lambdas({"home": "Arsenal", "away": "Brighton"}, research, s)
    assert r.usable and r.home > r.away


def test_perplexity_no_longer_asks_for_xg():
    """[§2-3] 정식 소스가 생겼으므로 산문 파싱 요청을 제거했다."""
    from app.research import deep

    assert "xg6" not in deep._SCHEMA_SOCCER
    assert "xG and xGA per match" not in deep.TARGETS["soccer"]
