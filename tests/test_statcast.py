"""[2-1] Statcast 수집기 — λ 모델의 1차 입력.

xwOBA는 타구 질에서 계산돼 수비 시프트·구장·시퀀싱 같은 운 요소가 가장 적게 섞인다.
Wharton 논문의 "타선 지표가 예측력이 높다"를 가장 깨끗하게 구현하는 값이다.
"""

import pytest

from app.collectors.statcast import (
    TEAM_CODE_TO_NAME,
    aggregate_pitchers,
    aggregate_team_offense,
    merge_into_research,
)

pd = pytest.importorskip("pandas")


def _pitches(rows):
    return pd.DataFrame(rows)


def _row(**over):
    r = {"inning_topbot": "Bot", "home_team": "CIN", "away_team": "SF",
         "estimated_woba_using_speedangle": 0.320, "launch_speed": 96.0,
         "launch_speed_angle": 6, "events": "single", "p_throws": "R",
         "pitcher": 1, "player_name": "Burns, Chase", "release_speed": 96.5,
         "game_pk": 1, "game_date": "2026-08-20"}
    r.update(over)
    return r


# ---------------------------------------------------------------- 팀 타선

def test_offense_attributes_batting_team_correctly():
    """공격 팀은 이닝 위치로 정한다 — Top이면 원정, Bot이면 홈."""
    df = _pitches([_row(inning_topbot="Bot"), _row(inning_topbot="Top")])
    out = aggregate_team_offense(df)
    assert set(out) == {"Cincinnati Reds", "San Francisco Giants"}


def test_offense_computes_model_inputs():
    """[2-1] xwOBA·배럴률·하드히트율·타구속도·K%/BB%를 계산한다."""
    df = _pitches([
        _row(estimated_woba_using_speedangle=0.400, launch_speed=100.0, launch_speed_angle=6),
        _row(estimated_woba_using_speedangle=0.200, launch_speed=80.0, launch_speed_angle=3),
        _row(events="strikeout", launch_speed=None, launch_speed_angle=None),
        _row(events="walk", launch_speed=None, launch_speed_angle=None),
    ])
    reds = aggregate_team_offense(df)["Cincinnati Reds"]
    assert reds["xwoba_30d"] == pytest.approx(0.31, abs=0.005)
    assert reds["barrel_pct"] == 50.0        # 타구 2개 중 1개가 배럴
    assert reds["hardhit_pct"] == 50.0       # 95mph 이상 1개
    assert reds["k_pct"] == 25.0 and reds["bb_pct"] == 25.0
    assert reds["pa"] == 4


def test_handedness_split_needs_sample():
    """표본이 얇으면 좌우 스플릿을 만들지 않는다 (거짓 정밀도 금지)."""
    thin = aggregate_team_offense(_pitches([_row(p_throws="L")] * 10))
    assert "vs_lhp_woba" not in thin["Cincinnati Reds"]
    thick = aggregate_team_offense(_pitches([_row(p_throws="L")] * 60))
    assert "vs_lhp_woba" in thick["Cincinnati Reds"]


def test_empty_frame_is_safe():
    assert aggregate_team_offense(pd.DataFrame()) == {}
    assert aggregate_pitchers(None) == {}


# ---------------------------------------------------------------- 투수

def test_pitcher_name_normalised_and_metrics():
    """statcast는 'Last, First' 형식 — games 테이블 표기로 바꾼다."""
    df = _pitches([_row(), _row(game_pk=2, release_speed=94.0)])
    out = aggregate_pitchers(df)
    assert "Chase Burns" in out
    p = out["Chase Burns"]
    assert p["throws"] == "R" and p["appearances"] == 2
    assert p["xwoba_allowed"] == pytest.approx(0.320, abs=0.001)
    assert p["velo_window"] == pytest.approx(95.2, abs=0.1)


# ---------------------------------------------------------------- 병합

def test_merge_fills_research_without_overwriting():
    """[2-1] 리서치가 이미 채운 값은 덮지 않는다 — 수집 실패 항목만 메운다."""
    research = {"home_pitcher": {"name": "Chase Burns", "siera": 2.90}}
    jg = {"home": "Cincinnati Reds", "away": "San Francisco Giants"}
    offense = {"Cincinnati Reds": {"xwoba_30d": 0.293, "k_pct": 26.2}}
    pitchers = {"Chase Burns": {"xwoba_allowed": 0.250, "throws": "R"}}

    filled = merge_into_research(research, jg, offense, pitchers)
    assert research["home_offense"]["xwoba_30d"] == 0.293
    assert research["home_pitcher"]["siera"] == 2.90        # 기존 값 보존
    assert research["home_pitcher"]["xwoba_allowed"] == 0.250
    assert any("타선" in f for f in filled)


def test_merge_reports_nothing_when_no_match():
    research = {}
    filled = merge_into_research(research, {"home": "Unknown FC", "away": "Nobody"}, {}, {})
    assert filled == [] and research == {}


def test_team_code_map_covers_30_clubs():
    """팀 약어 매핑이 30개 구단을 덮어야 집계가 새지 않는다."""
    assert len(set(TEAM_CODE_TO_NAME.values())) == 30


# ---------------------------------------------------------------- 모델 연결

def test_allowed_xwoba_takes_priority_in_lambda():
    """[2-1] 허용 xwOBA가 있으면 SIERA/ERA보다 먼저 쓴다 (운 오염이 가장 적다)."""
    from app.config import Settings
    from app.engine.scoring import mlb_lambdas

    s = Settings(_env_file=None)
    jg = {"home": "H", "away": "A"}
    base = {"home_offense": {"woba_30d": 0.320}, "away_offense": {"woba_30d": 0.320},
            "home_pitcher": {"era_season": 4.20}}
    with_xw = mlb_lambdas(jg, {**base, "away_pitcher": {
        "xwoba_allowed": 0.270, "siera": 5.00, "era_season": 6.00}}, s)
    assert "허용 xwOBA 0.270" in " ".join(with_xw.trace)

    without = mlb_lambdas(jg, {**base, "away_pitcher": {"siera": 5.00}}, s)
    assert with_xw.home < without.home      # 좋은 투수(xwOBA .270)면 상대 득점이 낮다
