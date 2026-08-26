"""[2-1] Statcast 수집기 — λ 모델의 1차 입력.

xwOBA는 타구 질에서 계산돼 수비 시프트·구장·시퀀싱 같은 운 요소가 가장 적게 섞인다.
Wharton 논문의 "타선 지표가 예측력이 높다"를 가장 깨끗하게 구현하는 값이다.
"""

import json
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
    # woba_value/woba_denom은 정식 xwOBA 계산의 분자·분모다 (삼진·볼넷 포함)
    r = {"inning_topbot": "Bot", "home_team": "CIN", "away_team": "SF",
         "estimated_woba_using_speedangle": 0.320, "launch_speed": 96.0,
         "launch_speed_angle": 6, "events": "single", "p_throws": "R",
         "pitcher": 1, "player_name": "Burns, Chase", "release_speed": 96.5,
         "game_pk": 1, "game_date": "2026-08-20",
         "woba_value": 0.9, "woba_denom": 1}
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
        # 삼진·볼넷은 타구 추정치가 없다 → 실제 woba_value를 쓴다
        _row(events="strikeout", launch_speed=None, launch_speed_angle=None,
             estimated_woba_using_speedangle=None, woba_value=0.0),
        _row(events="walk", launch_speed=None, launch_speed_angle=None,
             estimated_woba_using_speedangle=None, woba_value=0.69),
    ])
    reds = aggregate_team_offense(df)["Cincinnati Reds"]
    # (0.400 + 0.200 + 0.0 + 0.69) / 4 = 0.3225 — 삼진이 분모에 들어간다
    assert reds["xwoba_30d"] == pytest.approx(0.3225, abs=0.001)
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


# --- 당일 키 부재 시 3일 폴백 (2026-08-25 실사고: λ 0/15) ---

@pytest.mark.asyncio
async def test_load_falls_back_to_recent_day():
    """당일 키가 없으면 최근 3일 안의 키를 쓴다."""
    from app.collectors.statcast import load

    store = {"statcast:offense:2026-08-24": json.dumps({"Reds": {"xwoba_30d": 0.33}}),
             "statcast:pitchers:2026-08-24": json.dumps({"Greene": {"xwoba_allowed": 0.29}})}

    class R:
        async def get(self, k):
            return store.get(k)

    off, pit, bp, bat, lg = await load(R(), "2026-08-25")
    assert off["Reds"]["xwoba_30d"] == 0.33
    assert pit["Greene"]["xwoba_allowed"] == 0.29
    assert bp == {} and bat == {} and lg == {}   # 없는 캐시는 빈 dict


@pytest.mark.asyncio
async def test_load_prefers_same_day_over_fallback():
    """당일 키가 있으면 그것을 쓴다 — 폴백이 최신 데이터를 덮으면 안 된다."""
    from app.collectors.statcast import load

    store = {"statcast:offense:2026-08-25": json.dumps({"Reds": {"xwoba_30d": 0.35}}),
             "statcast:offense:2026-08-24": json.dumps({"Reds": {"xwoba_30d": 0.33}})}

    class R:
        async def get(self, k):
            return store.get(k)

    off, _pit, _bp, _bat, _lg = await load(R(), "2026-08-25")
    assert off["Reds"]["xwoba_30d"] == 0.35


@pytest.mark.asyncio
async def test_load_gives_up_beyond_window():
    """4일 이상 지난 캐시는 쓰지 않는다 — 최근 폼을 놓치기 때문."""
    from app.collectors.statcast import load

    store = {"statcast:offense:2026-08-20": json.dumps({"Reds": {"xwoba_30d": 0.33}})}

    class R:
        async def get(self, k):
            return store.get(k)

    off, pit, bp, bat, lg = await load(R(), "2026-08-25")
    assert off == {} and pit == {} and bp == {} and bat == {}


def test_merge_uses_game_starter_name():
    """선발 투수명이 jg에 있으면 Statcast 투수 지표가 붙어야 한다.

    실사고(2026-08-25): judge_games에 home_pitcher/away_pitcher를 싣지 않아
    투수 캐시 556명이 있는데도 λ의 '상대 선발 억제력'이 14/14경기 누락됐다.
    """
    from app.collectors.statcast import merge_into_research

    jg = {"home": "Detroit Tigers", "away": "Tampa Bay Rays",
          "home_pitcher": "Jackson Jobe", "away_pitcher": "Ian Seymour"}
    pitchers = {"Jackson Jobe": {"xwoba_allowed": 0.291, "velo": 96.2},
                "Ian Seymour": {"xwoba_allowed": 0.318}}
    research: dict = {}
    filled = merge_into_research(research, jg, {}, pitchers)
    assert research["home_pitcher"]["xwoba_allowed"] == 0.291
    assert research["away_pitcher"]["xwoba_allowed"] == 0.318
    assert any("선발" in f for f in filled)


def test_merge_without_starter_name_skips_pitcher():
    """선발 미정이면 조용히 건너뛴다 — 없는 데이터를 지어내지 않는다."""
    from app.collectors.statcast import merge_into_research

    jg = {"home": "Detroit Tigers", "away": "Tampa Bay Rays"}
    research: dict = {}
    filled = merge_into_research(research, jg, {}, {"Jackson Jobe": {"xwoba_allowed": 0.29}})
    assert "home_pitcher" not in research
    assert not any("선발" in f for f in filled)


# --- 삼진 제외 버그 회귀 방지 (2026-08-25: 부호가 뒤집혔다) ---

def test_strikeouts_lower_allowed_xwoba():
    """삼진이 많은 투수가 **좋게** 나와야 한다.

    실사고: estimated_woba_using_speedangle만 평균 내면 삼진이 분모에서 빠져
    탈삼진형 투수가 오히려 나쁘게 계산됐다(Paul Skenes 0.368 > 리그 중앙 0.310).
    """
    contact = _pitches([_row(pitcher=1, player_name="Contact, Guy", game_pk=g,
                             estimated_woba_using_speedangle=0.350, woba_value=0.9)
                        for g in range(1, 6)] * 12)
    strikeout = _pitches(
        [_row(pitcher=2, player_name="Whiff, King", game_pk=g,
              estimated_woba_using_speedangle=0.350, woba_value=0.9)
         for g in range(1, 6)] * 6
        + [_row(pitcher=2, player_name="Whiff, King", game_pk=g, events="strikeout",
                estimated_woba_using_speedangle=None, woba_value=0.0,
                launch_speed=None, launch_speed_angle=None)
           for g in range(1, 6)] * 6)
    c = aggregate_pitchers(contact)["Guy Contact"]["xwoba_allowed"]
    k = aggregate_pitchers(strikeout)["King Whiff"]["xwoba_allowed"]
    assert k < c, "삼진을 잡을수록 허용 xwOBA가 낮아야 한다 — 아니면 부호가 뒤집힌 것"
    assert k == pytest.approx(0.175, abs=0.01)


def test_strikeouts_raise_offense_xwoba_cost():
    """삼진을 많이 당하는 타선은 **나쁘게** 나와야 한다."""
    good = _pitches([_row(estimated_woba_using_speedangle=0.350, woba_value=0.9)] * 20)
    whiffy = _pitches(
        [_row(estimated_woba_using_speedangle=0.350, woba_value=0.9)] * 10
        + [_row(events="strikeout", estimated_woba_using_speedangle=None, woba_value=0.0,
                launch_speed=None, launch_speed_angle=None)] * 10)
    g = aggregate_team_offense(good)["Cincinnati Reds"]["xwoba_30d"]
    w = aggregate_team_offense(whiffy)["Cincinnati Reds"]["xwoba_30d"]
    assert w < g, "삼진이 많은 타선의 xwOBA가 더 낮아야 한다"


# --- 표본 가드 (2026-08-25: 0.012~1.010 잡음) ---

def test_thin_sample_pitcher_gets_league_average():
    """50투구·3등판 미만이면 리그 평균으로 대체하고 사유를 남긴다."""
    rows = [_row(pitcher=1, player_name="Bulk, Guy", game_pk=g,
                 estimated_woba_using_speedangle=0.300, woba_value=0.9)
            for g in range(1, 11)] * 10
    rows += [_row(pitcher=99, player_name="Tiny, Sample", game_pk=500,
                  estimated_woba_using_speedangle=1.500, woba_value=2.0)]
    out = aggregate_pitchers(_pitches(rows))
    tiny = out["Sample Tiny"]
    assert tiny["low_sample"] is True
    assert tiny["sample_note"] == "표본 부족 — 리그 평균 적용"
    assert tiny["xwoba_allowed"] != pytest.approx(1.500, abs=0.01), "잡음이 그대로 새면 안 된다"
    assert "low_sample" not in out["Guy Bulk"]


def test_enough_by_appearances_alone():
    """3등판이면 투구 수가 적어도 채택한다 (기준은 OR)."""
    rows = [_row(pitcher=7, player_name="Short, Start", game_pk=g,
                 estimated_woba_using_speedangle=0.280, woba_value=0.9)
            for g in (1, 2, 3)]
    p = aggregate_pitchers(_pitches(rows))["Start Short"]
    assert "low_sample" not in p
    assert p["appearances"] == 3


# --- 불펜·선발이닝·파크팩터를 Statcast/statsapi로 자체 산출 (Perplexity 대체) ---

def _pitch(pid, name, gp, inning, top="Top", **over):
    r = _row(pitcher=pid, player_name=name, game_pk=gp, inning=inning,
             inning_topbot=top, at_bat_number=inning * 3)
    r.update(over)
    return r


def test_bullpen_overuse_from_statcast():
    """리그 중앙값의 1.3배 이상 던진 불펜만 '과소모'로 본다."""
    from app.collectors.statcast import aggregate_bullpen

    rows = []
    for gp in (1, 2, 3):
        # CIN 불펜을 많이 굴린다 (선발 1명 + 구원 다수)
        rows.append(_pitch(1, "Starter, Cin", gp, 1))
        rows += [_pitch(9, "Relief, Cin", gp, i) for i in range(2, 10)] * 4
        # SF 불펜은 적게
        rows.append(_pitch(2, "Starter, Sf", gp, 1, top="Bot"))
        rows.append(_pitch(8, "Relief, Sf", gp, 8, top="Bot"))
    out = aggregate_bullpen(_pitches(rows))
    assert out["Cincinnati Reds"]["bp_overused"] is True
    assert out["San Francisco Giants"]["bp_overused"] is False
    assert out["Cincinnati Reds"]["bp_pitches_3d"] > out["San Francisco Giants"]["bp_pitches_3d"]


def test_starter_innings_average():
    """등판당 서로 다른 이닝 수의 평균 = 평균 이닝 근사."""
    from app.collectors.statcast import starter_innings

    rows = []
    for gp, last in ((1, 6), (2, 4)):     # 6이닝, 4이닝 → 평균 5.0
        rows += [_pitch(1, "Burns, Chase", gp, i) for i in range(1, last + 1)]
    assert starter_innings(_pitches(rows))["Chase Burns"] == pytest.approx(5.0)


def test_merge_attaches_bullpen_and_park():
    """불펜 과소모·파크팩터가 리서치에 실려 λ가 읽을 수 있어야 한다."""
    from app.collectors.statcast import merge_into_research

    jg = {"home": "Colorado Rockies", "away": "Seattle Mariners"}
    bullpen = {"Seattle Mariners": {"bp_pitches_3d": 260, "bp_overused": True},
               "Colorado Rockies": {"bp_pitches_3d": 120, "bp_overused": False}}
    parks = {"Colorado Rockies": 1.264}
    research: dict = {}
    filled = merge_into_research(research, jg, {}, {}, bullpen, parks)
    assert research["bullpen_overused"] == "원정"
    assert research["park_factor"] == 1.264
    assert any("파크팩터" in f for f in filled)


def test_merge_skips_bullpen_when_both_overused():
    """양쪽 다 과소모면 상대적 이점이 없다 — 표기하지 않는다."""
    from app.collectors.statcast import merge_into_research

    jg = {"home": "A", "away": "B"}
    bullpen = {"A": {"bp_pitches_3d": 260, "bp_overused": True},
               "B": {"bp_pitches_3d": 255, "bp_overused": True}}
    research: dict = {}
    merge_into_research(research, jg, {}, {}, bullpen, None)
    assert "bullpen_overused" not in research


def test_merge_does_not_override_research_park():
    """리서치가 이미 파크팩터를 채웠으면 덮지 않는다."""
    from app.collectors.statcast import merge_into_research

    research = {"park_factor": 1.11}
    merge_into_research(research, {"home": "Colorado Rockies", "away": "X"},
                        {}, {}, None, {"Colorado Rockies": 1.264})
    assert research["park_factor"] == 1.11


# --- [1][2] 결장·날씨를 정식 API로 (Perplexity 대체) ---

def test_absences_from_injured_marks_top_hitters():
    """타석 상위 2명은 '주포'(-4%p), 3~9위는 '주전 타자'(-2%p)로 문장이 갈린다."""
    from app.collectors.absences import from_injured

    batters = [{"id": i, "pa": 100 - i} for i in range(1, 12)]
    injured = [{"id": 1, "name": "Star Man", "position": "CF", "status": "10일 IL"},
               {"id": 5, "name": "Regular Guy", "position": "2B", "status": "10일 IL"},
               {"id": 99, "name": "Bench Guy", "position": "LF", "status": "10일 IL"}]
    out = from_injured("Reds", batters, injured)
    assert "주포" in out[0] and "Star Man" in out[0]
    assert "주전 타자" in out[1]
    assert "(선수)" in out[2], "랭킹 밖 선수는 주전으로 보지 않는다"


def test_absences_prefers_lineup_when_confirmed():
    """라인업이 확정되면 IL이 아니라 타순 기준으로 판정하고 근거를 밝힌다."""
    from app.collectors.absences import collect

    jg = {"home": "Reds", "away": "Giants"}
    batters = {"Reds": [{"id": i, "pa": 100 - i} for i in range(1, 10)]}
    lineup = {"confirmed": True,
              "home": {"batting_order_ids": [2, 3, 4, 5, 6, 7, 8, 9, 20]},
              "away": {"batting_order_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9]}}
    sentences, basis = collect(jg, batters, lineup, {})
    assert basis == "라인업 확정"
    assert any("라인업 제외" in x for x in sentences)


def test_absences_falls_back_to_il_when_not_confirmed():
    from app.collectors.absences import collect

    jg = {"home": "Reds", "away": "Giants"}
    batters = {"Reds": [{"id": 1, "pa": 90}]}
    injured = {"home": [{"id": 1, "name": "Star", "position": "CF", "status": "60일 IL"}]}
    sentences, basis = collect(jg, batters, {"confirmed": False}, injured)
    assert basis == "IL 명단" and sentences


def test_weather_skips_domed_parks():
    """돔구장은 날씨 보정을 걸지 않는다 — 없는 근거로 λ가 움직이면 안 된다."""
    from app.collectors.weather import merge_into_research

    research: dict = {}
    note = merge_into_research(research, {"game_id": 1, "home": "Toronto Blue Jays"},
                               {1: {"dome": True, "text": None}})
    assert "돔구장" in note
    assert "weather" not in research


def test_weather_text_is_parseable_by_scoring():
    """생성 문장이 scoring._weather_factor의 정규식에 걸려야 한다."""
    from app.collectors.weather import describe
    from app.config import get_settings
    from app.engine.scoring import _weather_factor

    text = describe(29.0, 3.2)
    assert _weather_factor({"weather": text}, get_settings()) is not None


def test_weather_omits_wind_direction():
    """풍향은 검증 불가라 문장에 넣지 않는다 (부호 뒤집힘 위험)."""
    from app.collectors.weather import describe

    text = describe(25.0, 5.0)
    assert "맞바람" not in text and "뒷바람" not in text


# ---------------------------------------------------------------- [§8-6] 관측 창

def _game(day: str, pk: int, **over):
    return _row(game_date=day, game_pk=pk, **over)


def test_offense_window_keeps_only_recent_games():
    """창을 경기 수로 자른다 — 일수가 아니다.

    팀마다 휴식일이 달라 '최근 30일'은 팀별로 다른 경기 수를 뜻했다.
    실측(1496경기)에서 15경기 창이 30일 창보다 승패 +1.34%p 나았다.
    """
    rows = [_game(f"2026-08-{d:02d}", d) for d in range(1, 11)]
    full = aggregate_team_offense(_pitches(rows))["Cincinnati Reds"]
    win3 = aggregate_team_offense(_pitches(rows), window_games=3)["Cincinnati Reds"]
    assert full["games"] == 10
    assert win3["games"] == 3


def test_offense_window_zero_means_no_trim():
    """0이면 자르지 않는다 — 종전 동작으로 복귀할 수 있어야 한다."""
    rows = [_game(f"2026-08-{d:02d}", d) for d in range(1, 8)]
    assert aggregate_team_offense(_pitches(rows), window_games=0)[
        "Cincinnati Reds"]["games"] == 7


def test_offense_window_larger_than_history_is_safe():
    """보유 경기보다 큰 창을 요구해도 있는 만큼만 쓴다 — 크래시 금지."""
    rows = [_game("2026-08-01", 1), _game("2026-08-02", 2)]
    assert aggregate_team_offense(_pitches(rows), window_games=15)[
        "Cincinnati Reds"]["games"] == 2


def test_offense_window_actually_changes_the_metric():
    """자른 구간이 지표를 바꿔야 한다 — 자르는 시늉만 하면 안 된다."""
    old = [_game(f"2026-08-{d:02d}", d, estimated_woba_using_speedangle=0.250,
                 woba_value=0.0) for d in range(1, 6)]
    new = [_game(f"2026-08-{d:02d}", d, estimated_woba_using_speedangle=0.450,
                 woba_value=2.0) for d in range(6, 11)]
    df = _pitches(old + new)
    recent = aggregate_team_offense(df, window_games=5)["Cincinnati Reds"]
    whole = aggregate_team_offense(df)["Cincinnati Reds"]
    assert recent["xwoba_30d"] > whole["xwoba_30d"], (
        "최근 5경기가 좋았는데 창을 잘라도 지표가 오르지 않았다")


def test_pitcher_window_trims_to_recent_starts():
    """선발도 등판 수로 자른다."""
    rows = [_game(f"2026-08-{d:02d}", d) for d in range(1, 11)]
    full = aggregate_pitchers(_pitches(rows))["Chase Burns"]
    win3 = aggregate_pitchers(_pitches(rows), window_starts=3)["Chase Burns"]
    assert full["appearances"] == 10
    assert win3["appearances"] == 3


def test_window_key_name_unchanged():
    """⚠️ 창이 30일이 아니어도 출력 키는 `xwoba_30d`를 유지한다.

    scoring._offense와 merge_into_research가 이 키로 읽는다. 이름을 바꾸면
    조용히 λ에서 타선이 통째로 빠진다 — 2026-08-26 선발 뒤집힘과 같은 유형의 사고다.
    """
    out = aggregate_team_offense(_pitches([_row()]), window_games=15)
    assert "xwoba_30d" in out["Cincinnati Reds"]
