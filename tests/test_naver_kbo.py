"""[§8-19] 네이버 스포츠 KBO 크롤러 — LLM 0회로 경기력 재료를 모은다.

실사고(2026-08-26): KBO 5경기 딥서치에서 **3경기가 "재료 없음"으로 실패**했다.
Perplexity를 한 번 부르고 같은 프롬프트로 한 번 더 부르고 포기하는 구조였다 —
그건 딥서치가 아니라 API 호출이다. 네이버 preview 하나가 선발·구종·최근폼·순위·
상대전적을 한 번에 준다. 이 수집기 도입 후 **5경기 전부 λ가 섰다.**
"""

import pytest

from app.collectors.naver_kbo import (
    REQUIRED_PREVIEW,
    TEAM_TO_ODDS,
    _num,
    form_from_previous,
    merge_into_research,
    parse_preview,
)


def _pv(**over):
    pv = {
        "gameInfo": {"stadium": "잠실", "hCode": "LG", "aCode": "NC"},
        "homeStarter": {
            "playerInfo": {"name": "임찬규", "hitType": "우투우타"},
            "currentSeasonStats": {"era": "4.14", "whip": "1.39",
                                   "inn": "121.2", "gameCount": 22},
            "currentPitKindStats": [{"type": "FAST", "speed": 139}],
        },
        "awayStarter": {
            "playerInfo": {"name": "구창모", "hitType": "좌투좌타"},
            "currentSeasonStats": {"era": "3.89", "whip": "1.27",
                                   "inn": "120.1", "gameCount": 21},
            "currentPitKindStats": [{"type": "SLID", "speed": 130}],
        },
        "homeStandings": {"hra": "0.269", "era": "4.91", "rank": 3, "w": 62, "l": 50},
        "awayStandings": {"hra": "0.272", "era": "4.79", "rank": 8, "w": 48, "l": 57},
        "homeTeamPreviousGames": [
            {"hCode": "LG", "aCode": "NC", "hScore": 5, "aScore": 4},
            {"hCode": "HH", "aCode": "LG", "hScore": 3, "aScore": 12},
        ],
        "awayTeamPreviousGames": [
            {"hCode": "LG", "aCode": "NC", "hScore": 5, "aScore": 4},
        ],
        "seasonVsResult": {"hw": 6, "hl": 5, "hd": 0},
    }
    pv.update(over)
    return pv


# ---------------------------------------------------------------- 파싱

def test_innings_notation_is_thirds_not_decimal():
    """⚠️ 야구 이닝 '120.1'은 120.1이 아니라 **120⅓**이다.

    그냥 float()하면 선발 담당 이닝(ip_avg_recent)이 미세하게 틀리고,
    그 값이 λ의 선발 억제 비중에 그대로 들어간다.
    """
    assert _num("120.1") == pytest.approx(120 + 1 / 3, abs=0.01)
    assert _num("120.2") == pytest.approx(120 + 2 / 3, abs=0.01)
    assert _num("4.14") == pytest.approx(4.14)      # 이닝이 아닌 값은 그대로
    assert _num("") is None and _num(None) is None


def test_form_is_from_our_teams_perspective():
    """⚠️ `result` 필드는 경기 결과 표기지 **그 팀 기준 승패가 아니다.**

    홈/원정을 보고 뒤집지 않으면 최근 폼이 통째로 반대로 들어간다.
    """
    games = [
        {"hCode": "LG", "aCode": "NC", "hScore": 5, "aScore": 4},   # LG 승 / NC 패
        {"hCode": "HH", "aCode": "LG", "hScore": 3, "aScore": 12},  # LG 승(원정)
    ]
    assert form_from_previous(games, "LG") == "WW"
    assert form_from_previous(games, "NC") == "L"      # NC는 첫 경기만 있다


def test_form_marks_draws():
    games = [{"hCode": "LG", "aCode": "NC", "hScore": 3, "aScore": 3}]
    assert form_from_previous(games, "LG") == "D"


def test_parse_preview_extracts_starters_and_form():
    d = parse_preview(_pv())
    assert d["home_pitcher"]["name"] == "임찬규"
    assert d["home_pitcher"]["throws"] == "R"
    assert d["away_pitcher"]["throws"] == "L"
    assert d["home_pitcher"]["era_season"] == 4.14
    assert d["away_pitcher"]["whip"] == 1.27
    # 선발 담당 이닝 — λ의 입력
    assert d["home_pitcher"]["ip_avg_recent"] == pytest.approx(5.52, abs=0.05)
    assert d["home_form"] == "WW"
    assert d["home_team"]["rank"] == 3
    assert d["stadium"] == "잠실"
    assert d["h2h"]["home_w"] == 6


def test_parse_preview_rejects_changed_structure():
    """⚠️ 비공개 API다 — 구조가 바뀌면 **조용히 0건**이 된다. 검증 후 거부한다."""
    broken = _pv()
    del broken["homeStarter"]
    assert parse_preview(broken) is None
    assert parse_preview({}) is None
    for k in REQUIRED_PREVIEW:
        assert k in _pv()


def test_pitch_mix_is_collected():
    """구종·구속은 딥서치가 절대 못 주는 정보다 — 판정이 매치업을 읽는 재료."""
    d = parse_preview(_pv())
    assert "FAST" in d["home_pitcher"]["pitch_mix"]
    assert "139km" in d["home_pitcher"]["pitch_mix"]


# ---------------------------------------------------------------- 병합

def test_crawl_overrides_deep_search():
    """[§8-19] 크롤링이 딥서치를 **덮어쓴다** — 구단 발표가 LLM 산문보다 정확하다."""
    research = {"home_pitcher": {"name": "임찬규", "era_season": 9.99},
                "home_recent_form": {"form": "LLLLL"}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    filled = merge_into_research(research, jg, parse_preview(_pv()))
    assert research["home_pitcher"]["era_season"] == 4.14
    assert research["home_recent_form"]["form"] == "WW"
    assert any("era_season" in f for f in filled)


def test_merge_is_safe_on_empty():
    """수집 실패해도 크래시하지 않는다 — 빈 결과는 그냥 아무것도 안 채운다."""
    research = {}
    assert merge_into_research(research, {"home": "LG Twins", "away": "NC Dinos"}, {}) == []
    assert research == {}


def test_team_mapping_covers_all_ten():
    """축약 표기 → Odds 팀명. 하나라도 빠지면 그 경기가 통째로 매칭되지 않는다."""
    assert len(TEAM_TO_ODDS) == 10
    assert TEAM_TO_ODDS["키움"] == "Kiwoom Heroes"
