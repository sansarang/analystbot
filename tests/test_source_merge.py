"""[§8-30] 소스 병합의 **조건 도달**을 직접 확인한다.

실사고(2026-08-27): 네이버 병합이 `if weather:` 안에 있었고 `elif sport == "npb"`가
그 날씨 if에 붙어 있었다. 결과는 **조용한 데이터 손실**이었다 —
NPB는 돔경기가 하나만 있어도 Yahoo(유일한 숫자 소스)가 병합되지 않았고,
KBO는 날씨 조회가 실패하면 선발 ERA·WHIP·폼이 함께 사라졌다.
로그에도 상태값에도 흔적이 없어 아무도 알 수 없었다.

이 테스트는 **소스 병합이 날씨와 독립임**을 못 박는다. 두 관심사를 다시 엮으면
아래 중 하나가 반드시 깨진다.
"""

import pytest

from app.pipeline import merge_source_data

NPB_JG = {"home": "Yomiuri Giants", "away": "Hanshin Tigers"}
KBO_JG = {"home": "Kia Tigers", "away": "Lotte Giants"}
NPB_KEY = "Hanshin Tigers@Yomiuri Giants"
KBO_KEY = "Lotte Giants@Kia Tigers"

YAHOO = {NPB_KEY: {"home_pitcher": {"name": "戸郷翔征", "era_season": 2.80},
                   "away_pitcher": {"name": "村上頌樹", "era_season": 3.10}}}
NAVER = {KBO_KEY: {"home_pitcher": {"name": "황동하", "era_season": 4.82,
                                    "whip": 1.49, "ip_avg_recent": 3.82, "throws": "R"},
                   "home_form": "WLLWW", "stadium": "광주"}}
# 돔구장은 조회를 건너뛰고도 **참 값**을 돌려준다 — 이게 사고의 방아쇠였다.
DOME_WEATHER = {1: {"text": None, "dome": True, "temp_c": None, "wind_ms": None}}
REAL_WEATHER = {1: {"text": "기온 31도, 풍속 2.6m/s", "dome": False,
                    "temp_c": 31.0, "wind_ms": 2.6}}


def test_npb_yahoo_merges_even_when_weather_present():
    """🔴 회귀 핵심 — 돔경기가 있어 날씨가 채워져도 Yahoo는 병합돼야 한다.

    옛 구조에서는 `elif`가 날씨 if에 붙어 있어 이 경우 Yahoo가 **통째로 누락**됐다.
    NPB 12팀 중 5팀이 돔이므로 사실상 상시 발생했다.
    """
    research: dict = {}
    done = merge_source_data(research, NPB_JG, "npb",
                             {"yahoo": YAHOO, "weather": DOME_WEATHER})
    assert "yahoo" in done, "돔경기(날씨 있음)에서 Yahoo 병합이 건너뛰어졌다"
    assert "npb_stats" in done
    assert research["home_pitcher"]["era_season"] == 2.80


def test_npb_official_obp_merges_independent_of_weather():
    """팀 OBP는 날씨·Yahoo와 독립이다 — 돔이라고 타선 숫자가 빠지면 안 된다."""
    teams = {"Yomiuri Giants": {"obp": 0.297, "ops": 0.651, "slg": 0.354},
             "Hanshin Tigers": {"obp": 0.317, "ops": 0.688, "slg": 0.371}}
    for weather in ({}, DOME_WEATHER):
        research: dict = {}
        done = merge_source_data(research, NPB_JG, "npb",
                                 {"yahoo": YAHOO, "npb_teams": teams,
                                  "weather": weather})
        assert "npb_stats" in done and "yahoo" in done
        assert research["home_offense"]["obp_30d"] == 0.297
        assert research["away_offense"]["obp_30d"] == 0.317
        assert research["home_pitcher"]["era_season"] == 2.80


def test_npb_yahoo_merges_when_weather_absent():
    research: dict = {}
    done = merge_source_data(research, NPB_JG, "npb", {"yahoo": YAHOO, "weather": {}})
    assert "yahoo" in done
    assert research["away_pitcher"]["era_season"] == 3.10


def test_npb_form_merges_independent_of_weather():
    form = {"Yomiuri Giants": {"results_l3": "WLW", "score_games": 3}}
    research: dict = {}
    done = merge_source_data(research, NPB_JG, "npb",
                             {"yahoo": YAHOO, "npb_form": form, "weather": DOME_WEATHER})
    assert "npb_form" in done
    assert research["home_usage"]["results_l3"] == "WLW"


def test_kbo_naver_merges_when_weather_fails():
    """🔴 회귀 핵심 — 날씨 조회가 실패해도 네이버 선발 지표는 살아야 한다.

    옛 구조에서는 날씨가 빈 dict면 네이버 병합 자체가 실행되지 않아
    선발 ERA·WHIP·평균이닝·손잡이·최근폼이 전부 사라졌다.
    """
    research: dict = {}
    done = merge_source_data(research, KBO_JG, "kbo",
                             {"naver": NAVER, "weather": {}, "kbo_teams": {},
                              "kbo_pitchers": {}, "parks": {}})
    assert "naver" in done, "날씨 실패가 네이버 병합을 함께 죽였다"
    assert research["home_pitcher"]["era_season"] == 4.82
    assert research["home_pitcher"]["ip_avg_recent"] == 3.82
    assert research["home_recent_form"]["form"] == "WLLWW"


def test_kbo_naver_merges_with_weather():
    research: dict = {}
    done = merge_source_data(research, KBO_JG, "kbo",
                             {"naver": NAVER, "weather": REAL_WEATHER, "kbo_teams": {},
                              "kbo_pitchers": {}, "parks": {}})
    assert {"naver", "weather"} <= set(done)


@pytest.mark.parametrize("sport,payload,expect", [
    ("npb", {"yahoo": YAHOO}, "yahoo"),
    ("kbo", {"naver": NAVER, "kbo_teams": {}, "kbo_pitchers": {}, "parks": {}}, "naver"),
])
def test_source_merge_needs_no_weather_key_at_all(sport, payload, expect):
    """날씨 키가 아예 없어도 종목 소스는 병합된다 — 두 관심사는 독립이다."""
    jg = NPB_JG if sport == "npb" else KBO_JG
    assert expect in merge_source_data({}, jg, sport, payload)


def test_weather_merges_independently_of_sport_source():
    """반대 방향 — 종목 소스가 비어도 날씨는 들어가야 한다."""
    research: dict = {}
    jg = dict(KBO_JG, game_id=1)
    done = merge_source_data(research, jg, "kbo",
                             {"weather": REAL_WEATHER, "kbo_teams": {},
                              "kbo_pitchers": {}, "parks": {}})
    assert "weather" in done
    assert research.get("weather") == "기온 31도, 풍속 2.6m/s"


def test_kbo_usage_merges_independently_of_weather():
    """[§8-33] 카드 ①칸 재료도 날씨와 독립이다 — 같은 사고를 반복하지 않는다."""
    usage = {"Kia Tigers": {"relief_ip_l3": 6.33, "relief_batters_l3": 37,
                            "back_to_back_count": 3},
             "Lotte Giants": {"relief_ip_l3": 4.33, "relief_batters_l3": 25,
                              "back_to_back_count": 0}}
    for weather in ({}, REAL_WEATHER):
        research: dict = {}
        done = merge_source_data(research, KBO_JG, "kbo",
                                 {"kbo_usage": usage, "weather": weather,
                                  "kbo_teams": {}, "kbo_pitchers": {}, "parks": {}})
        assert "kbo_usage" in done, f"날씨={bool(weather)}일 때 소모 병합이 건너뛰어졌다"
        assert research["home_usage"]["relief_batters_l3"] == 37
        assert research["away_usage"]["back_to_back_count"] == 0


def test_standings_merge_reaches_regardless_of_weather():
    """[§8-34] 카드 ④칸 재료도 날씨와 독립이다."""
    # 게임차는 1위가 표에 있어야 나온다 — 실제로도 그날 프리뷰가 10팀을 다 준다
    naver = {KBO_KEY: {"home_team": {"rank": 4, "w": 62, "l": 50, "d": 2},
                       "away_team": {"rank": 6, "w": 50, "l": 60, "d": 2}},
             "Samsung Lions@KT Wiz": {"home_team": {"rank": 1, "w": 65, "l": 42, "d": 3},
                                      "away_team": {"rank": 2, "w": 66, "l": 44, "d": 3}}}
    for weather in ({}, REAL_WEATHER):
        research: dict = {}
        done = merge_source_data(research, KBO_JG, "kbo",
                                 {"naver": naver, "weather": weather,
                                  "kbo_teams": {}, "kbo_pitchers": {}, "parks": {}})
        assert "standings" in done, f"날씨={bool(weather)}일 때 순위 병합이 건너뛰어졌다"
        assert research["home_standing"]["games_behind"] == 5.5
        assert research["away_standing"]["rank"] == 6


def test_no_statcast_data_is_safe():
    """수집이 통째로 없어도 죽지 않는다.

    반환값은 **도달한 병합**을 뜻한다(무엇을 채웠는지가 아니다) — 버그가
    '실행 자체가 안 됐다'는 성격이었으므로 도달 여부를 기록한다.
    빈 입력에서도 kbo 계열 병합은 도달하되 아무것도 채우지 않는다.
    """
    assert merge_source_data({}, KBO_JG, "kbo", None) == []
    research: dict = {}
    assert merge_source_data(research, KBO_JG, "kbo", {}) == ["kbo_stats", "kbo_park"]
    assert research == {}, "빈 입력인데 값이 생겼다"
    assert merge_source_data({}, NPB_JG, "npb", {}) == ["npb_stats"]
    assert merge_source_data({}, {"home": "A", "away": "B"}, "mlb", {}) == []


# ---------------------------------------------------------------- [§8-35] 변화 이력

def test_lineup_timeline_records_when_not_just_what():
    """**언제 바뀌었는지가 정보다.** 스냅샷 하나만 보면 영원히 못 본다."""
    from app.collectors.crawler_feed import lineup_timeline

    changes = [
        {"game": KBO_KEY, "field": "lineup_home", "kind": "added",
         "at": "2026-08-26T17:43:00+09:00", "from": "", "to": "가-나-다"},
        {"game": KBO_KEY, "field": "lineup_away", "kind": "added",
         "at": "2026-08-26T17:51:00+09:00", "from": "", "to": "라-마-바"},
        {"game": KBO_KEY, "field": "lineup_home", "kind": "changed",
         "at": "2026-08-26T18:05:00+09:00", "from": "가-나-다", "to": "가-다-나"},
        {"game": KBO_KEY, "field": "home_pitcher", "kind": "changed",
         "at": "2026-08-26T18:10:00+09:00", "from": "황동하", "to": "김태형"},
        {"game": "다른@경기", "field": "lineup_home", "kind": "added",
         "at": "2026-08-26T17:00:00+09:00", "from": "", "to": "x"},
    ]
    t = lineup_timeline(changes, KBO_JG)
    assert t["lineup_announced_at"] == "17:43", "가장 이른 발표 시각이어야 한다"
    assert t["lineup_changes"] == ["18:05 홈 라인업 변경"]
    assert t["starter_changes"] == ["18:10 홈 선발 황동하 → 김태형"]


def test_lineup_timeline_ignores_other_games():
    from app.collectors.crawler_feed import lineup_timeline

    other = [{"game": "X@Y", "field": "lineup_home", "kind": "added",
              "at": "2026-08-26T17:00:00+09:00"}]
    assert lineup_timeline(other, KBO_JG) == {}


def test_crawler_merge_labels_lineup_sides():
    """🔴 종전에는 `홈|원정` 합본이라 어느 쪽이 어느 팀인지 알 수 없었다."""
    from app.collectors.crawler_feed import merge_into_research

    research: dict = {}
    snap = {KBO_KEY: {"lineup_home": "가-나-다", "lineup_away": "라-마-바",
                      "home_pitcher": "황동하"}}
    merge_into_research(research, KBO_JG, snap)
    assert research["home_lineup"]["order"] == "가-나-다"
    assert research["away_lineup"]["order"] == "라-마-바"
    assert "lineup" not in research, "레이블 없는 합본이 남아 있다"


def test_notable_rows_keeps_game_alignment():
    """🔴 변화 감지가 재판정을 트리거한다 — 경기가 어긋나면 조용한 오판이 된다.

    `notable_changes()`는 걸러낸 문장만 돌려주므로 원본 목록과 zip하면
    다른 경기의 변화가 엉뚱한 경기에 붙는다.
    """
    from app.collectors.crawler_feed import notable_changes, notable_rows

    changes = [
        {"game": "A@B", "field": "weather", "kind": "changed", "at": "2026-08-26T17:00:00+09:00"},
        {"game": "C@D", "field": "home_pitcher", "kind": "changed",
         "at": "2026-08-26T18:10:00+09:00", "from": "황동하", "to": "김태형"},
        {"game": "E@F", "field": "stadium", "kind": "changed", "at": "2026-08-26T18:20:00+09:00"},
        {"game": "G@H", "field": "lineup_home", "kind": "changed",
         "at": "2026-08-26T18:30:00+09:00", "from": "가-나", "to": "나-가"},
    ]
    rows = notable_rows(changes)
    assert [r["game"] for r in rows] == ["C@D", "G@H"], "경기 키가 어긋났다"
    assert "황동하 → 김태형" in rows[0]["change"]
    # 문장 버전과 건수가 같아야 한다 — 한쪽만 필터가 달라지면 정렬이 깨진다
    assert len(rows) == len(notable_changes(changes))


def test_notable_rows_empty_is_empty():
    from app.collectors.crawler_feed import notable_rows

    assert notable_rows([]) == [] and notable_rows(None) == []


def test_crawler_name_then_official_era_fills():
    """크롤러가 선발 이름을 바꾼 뒤 공식 ERA가 그 투수 것으로 채워져야 한다.

    예전에는 크롤러가 마지막이라 직전에 채운 ERA가 지워진 채 남았다.
    """
    research = {"home_pitcher": {"name": "옛투수", "era_season": 2.00}}
    snap = {KBO_KEY: {"home_pitcher": "양현종", "away_pitcher": "",
                      "lineup_home": "김도영(3루수)-최형우(지명타자)",
                      "lineup_away": ""}}
    done = merge_source_data(research, KBO_JG, "kbo", {
        "crawler": snap,
        "kbo_teams": {},
        "kbo_pitchers": {"양현종": {"era_season": 3.50, "whip": 1.20}},
        "parks": {},
    })
    assert "crawler" in done and "kbo_stats" in done
    assert research["home_pitcher"]["name"] == "양현종"
    assert research["home_pitcher"]["era_season"] == 3.50
    assert "김도영" in research["home_lineup"]["order"]


MLB_JG = {"home": "Los Angeles Dodgers", "away": "San Diego Padres",
          "home_pitcher": "Yoshinobu Yamamoto", "away_pitcher": "Dylan Cease",
          "game_id": 1,
          "stats": {"home_pitcher_era": 2.50, "away_pitcher_era": 3.80}}


def test_mlb_statsapi_merges_independent_of_weather():
    """KBO 네이버와 같다 — 날씨가 없어도 선발 이름·ERA가 카드에 올라야 한다."""
    for weather in ({}, DOME_WEATHER, REAL_WEATHER):
        research: dict = {}
        done = merge_source_data(research, MLB_JG, "mlb", {
            "offense": {"Los Angeles Dodgers": {"xwoba_30d": 0.340}},
            "pitchers": {"Yoshinobu Yamamoto": {"xwoba_allowed": 0.280, "throws": "R"}},
            "bullpen": {"Los Angeles Dodgers": {"bp_pitches_3d": 210}},
            "standings": {"Los Angeles Dodgers": {"rank": 1, "w": 80, "l": 50, "d": 0,
                                                  "win_pct": 0.615}},
            "weather": weather,
        })
        assert "mlb_statsapi" in done
        assert research["home_pitcher"]["name"] == "Yoshinobu Yamamoto"
        assert research["home_pitcher"]["era_season"] == 2.50
        assert research["home_offense"]["xwoba_30d"] == 0.340
        assert research["home_usage"]["bp_pitches_3d"] == 210
        assert research["home_standing"]["rank"] == 1


def test_mlb_form_and_confirmed_lineup_merge():
    research: dict = {}
    jg = {**MLB_JG, "lineup_status": "none"}
    done = merge_source_data(research, jg, "mlb", {
        "form": {"Los Angeles Dodgers": {
            "score_games": 3, "results_l3": "WWL", "runs_l3": 15,
            "runs_allowed_l3": 9, "runs_per_game_l3": 5.0,
        }},
        "absences": {1: {"lineup": {
            "confirmed": True,
            "home": {"batting_order": [f"H{i}" for i in range(9)]},
            "away": {"batting_order": [f"A{i}" for i in range(9)]},
        }, "injured": {}}},
        "weather": {},
    })
    assert "mlb_usage" in done
    assert research["home_usage"]["results_l3"] == "WWL"
    assert research["home_lineup"]["order"].startswith("H0-")
    assert jg["lineup_status"] == "confirmed"


def test_mlb_pipeline_has_no_heuristic_and_no_odds_key():
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "heuristic_model_prob" not in src
    assert 'active_keys = ["baseball_mlb"]' not in src
    assert "elif sport == \"mlb\"" in src  # merge_source_data 분기
