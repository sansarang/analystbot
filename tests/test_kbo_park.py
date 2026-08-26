"""[§8-25] KBO 파크팩터 — 스탯 사이트를 못 믿을 때 **직접 잰다.**

실사고(2026-08-26): KBO λ가 매번 `파크팩터 미확보`였다. 잠실이 투수친화라는 건
상식인데 λ가 반영하지 못했다. 스탯티즈는 접속 불가, KBO 공식 구장별 페이지는 비어 있다.
→ 공식 일정에 구장·점수가 다 있으니 543경기로 직접 측정했다.
"""

import pytest

from app.collectors.kbo_park import (
    MIN_GAMES_PER_SIDE,
    STADIUM_OF_TEAM,
    TEAM_HOME_STADIUM,
    compute,
    merge_into_research,
)


def _g(home, away, hs, as_, stadium, status="final"):
    return {"home_kr": home, "away_kr": away, "home_score": hs, "away_score": as_,
            "stadium": stadium, "status": status}


def _season(team, opp, home_total, away_total, n=25):
    """그 팀의 홈 n경기(총득점 home_total)·원정 n경기(away_total)를 만든다."""
    out = []
    for _ in range(n):
        out.append(_g(team, opp, home_total // 2, home_total - home_total // 2,
                      TEAM_HOME_STADIUM[team]))
        out.append(_g(opp, team, away_total // 2, away_total - away_total // 2,
                      TEAM_HOME_STADIUM[opp]))
    return out


def test_park_factor_cancels_team_strength():
    """[§8-25] ⚠️ 단순 '구장별 평균 득점'은 **팀 편향**이 섞인다.

    한화 홈(대전)이 높은 것이 구장 탓인지 한화 타선 탓인지 구분되지 않는다.
    → PF = 그 팀 홈 총득점 / 그 팀 원정 총득점. 같은 팀이 양쪽에 있어 전력이 상쇄된다.
    """
    # 롯데: 홈에서 12점, 원정에서 8점 → 사직이 타자친화
    games = _season("롯데", "LG", home_total=12, away_total=8)
    table = compute(games)
    assert table["사직"]["pf"] == pytest.approx(1.5, abs=0.01)
    # 상대(LG)는 정확히 반대로 잡힌다 — 잠실은 투수친화
    assert table["잠실"]["pf"] == pytest.approx(8 / 12, abs=0.01)


def test_thin_sample_is_excluded_not_defaulted():
    """⚠️ 표본 미달을 1.0으로 채우면 '측정했는데 중립'과 '못 쟀다'가 구분되지 않는다."""
    few = _season("롯데", "LG", 12, 8, n=MIN_GAMES_PER_SIDE // 2 - 1)
    assert compute(few) == {}


def test_unfinished_and_scoreless_games_ignored():
    games = _season("롯데", "LG", 12, 8)
    games.append(_g("롯데", "LG", None, None, "사직"))          # 우천 취소
    games.append(_g("롯데", "LG", 5, 5, "사직", status="live"))  # 진행 중
    table = compute(games)
    assert table["사직"]["games"] == MIN_GAMES_PER_SIDE + 5      # n=25


def test_jamsil_averages_two_home_teams():
    """[§8-25] 잠실은 LG·두산 공용이다 — 경기 수 가중 평균이어야 한다."""
    games = _season("LG", "롯데", home_total=8, away_total=10)
    games += _season("두산", "KIA", home_total=10, away_total=10)
    table = compute(games)
    assert table["잠실"]["teams"] == 2
    # LG 0.8 · 두산 1.0 → 가중 평균 0.9 근방
    assert 0.85 < table["잠실"]["pf"] < 0.95


def test_all_ten_teams_mapped():
    """매핑이 빠지면 그 구장이 통째로 사라진다."""
    assert len(TEAM_HOME_STADIUM) == 10
    assert len(set(TEAM_HOME_STADIUM.values())) == 9   # 잠실 공용
    assert len(STADIUM_OF_TEAM) == 10


# ---------------------------------------------------------------- 병합

def test_merge_uses_home_team_stadium():
    research = {}
    filled = merge_into_research(research, {"home": "Lotte Giants", "away": "Kia Tigers"},
                                 {"사직": {"pf": 1.208, "games": 54, "teams": 1}})
    assert research["park_factor"] == 1.208
    assert "사직" in research["park"] and "54경기" in research["park"]
    assert filled == ["park_factor"]


def test_merge_skips_when_unmeasured():
    """⚠️ 못 잰 구장을 1.0으로 채우지 않는다 — 없는 것을 있는 척하지 않는다."""
    research = {}
    assert merge_into_research(research, {"home": "Lotte Giants"}, {}) == []
    assert "park_factor" not in research
    assert merge_into_research(research, {"home": "알 수 없는 팀"},
                               {"사직": {"pf": 1.2}}) == []


def test_park_factor_actually_moves_lambda():
    """파크팩터가 λ를 실제로 움직여야 한다 — 넣기만 하고 안 쓰이면 의미가 없다."""
    from app.config import Settings
    from app.engine.scoring import mlb_lambdas

    s = Settings(_env_file=None)
    base = {"home_offense": {"obp_30d": 0.347}, "away_offense": {"obp_30d": 0.331},
            "home_pitcher": {"era_season": 4.0}, "away_pitcher": {"era_season": 4.0}}
    jg = {"home": "Lotte Giants", "away": "Kia Tigers"}
    neutral = mlb_lambdas(jg, dict(base), s, sport="kbo")
    hitter = mlb_lambdas(jg, {**base, "park_factor": 1.208}, s, sport="kbo")
    pitcher = mlb_lambdas(jg, {**base, "park_factor": 0.888}, s, sport="kbo")
    assert hitter.home > neutral.home > pitcher.home
    assert any("파크팩터" in t for t in hitter.trace)


# ---------------------------------------------------------------- [§8-26] 날씨

def test_kbo_npb_stadiums_have_coords_or_dome():
    """[§8-26] 모든 KBO·NPB 홈팀이 좌표를 갖거나 돔으로 분류돼야 한다.

    빠지면 그 경기만 조용히 날씨 없이 λ를 낸다 — 어느 경기가 빠졌는지도 모른다.
    """
    from app.collectors.kbo_park import STADIUM_OF_TEAM
    from app.collectors.weather import DOMED, PARK_COORDS

    for team in STADIUM_OF_TEAM:                      # KBO 10팀
        assert team in PARK_COORDS or team in DOMED, f"{team} 좌표·돔 분류 없음"

    from app.collectors.yahoo_npb import TEAM_TO_ODDS

    for team in TEAM_TO_ODDS.values():                # NPB 12팀
        assert team in PARK_COORDS or team in DOMED, f"{team} 좌표·돔 분류 없음"


def test_dome_teams_have_no_coords():
    """돔은 조회하지 않는다 — 좌표를 넣어두면 불필요한 호출이 나간다."""
    from app.collectors.weather import DOMED, PARK_COORDS

    for team in ("Kiwoom Heroes", "Yomiuri Giants", "Chunichi Dragons"):
        assert team in DOMED
        assert team not in PARK_COORDS


def test_jamsil_shared_by_two_teams_same_coords():
    """잠실은 LG·두산 공용 — 좌표가 같아야 한다."""
    from app.collectors.weather import PARK_COORDS

    assert PARK_COORDS["LG Twins"] == PARK_COORDS["Doosan Bears"]


def test_coords_are_in_plausible_range():
    """⚠️ 위경도가 뒤바뀌면 엉뚱한 지역 날씨가 들어온다 — 조용한 오염이다."""
    from app.collectors.weather import KBO_COORDS, NPB_COORDS

    for name, (lat, lon) in {**KBO_COORDS, **NPB_COORDS}.items():
        assert 30 < lat < 46, f"{name} 위도 이상: {lat}"      # 한국·일본 위도대
        assert 124 < lon < 146, f"{name} 경도 이상: {lon}"
