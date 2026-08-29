"""[KBO 1단계] 공식 기록실 파싱 — 종료 점수 적재의 정확성.

진행 중 경기를 종료로 오판하면 점수가 틀린 채로 games에 굳는다.
"""

import pytest

from app.collectors.kbo import (
    KBO_TEAMS,
    STADIUM_HOME,
    parse_matchup,
    parse_rows,
)


# ---------------------------------------------------------------- 매치업 파싱

def test_matchup_is_away_first_home_second():
    """`한화4vs7KT` = 원정 한화 4점, 홈 KT 7점. 구장(수원=KT)이 이 방향을 확인해 준다."""
    g = parse_matchup("한화4vs7KT")
    assert g == {"away": "한화", "away_score": 4, "home": "KT", "home_score": 7}


def test_matchup_two_digit_scores():
    g = parse_matchup("SSG10vs2키움")
    assert g["away"] == "SSG" and g["away_score"] == 10
    assert g["home"] == "키움" and g["home_score"] == 2


def test_matchup_without_scores():
    g = parse_matchup("삼성vs롯데")
    assert g["away"] == "삼성" and g["home"] == "롯데"
    assert g["away_score"] is None and g["home_score"] is None


def test_matchup_garbage_returns_none():
    assert parse_matchup("경기없음") is None
    assert parse_matchup("") is None


# ---------------------------------------------------------------- 상태 판정

DONE = ["08.24(월)", "18:30", "LG2vs1두산", "리뷰", "하이라이트", "TV", "", "잠실", "-"]
LIVE = ["08.25(화)", "18:30", "NC0vs0LG", "", "", "TV", "", "잠실", "-"]
PREVIEW = ["08.26(수)", "18:30", "NCvsLG", "프리뷰", "", "TV", "", "잠실", "-"]
CANCEL = ["08.22(토)", "19:00", "롯데vs두산", "", "", "TV", "", "잠실", "우천취소"]


def test_live_game_is_not_final():
    """★ 진행 중 0-0을 종료로 보면 채점이 오염된다. '리뷰'가 붙어야 종료다."""
    games, failed = parse_rows([LIVE], 2026)
    assert failed == 0
    assert games[0]["status"] == "live"
    assert games[0]["home_score"] == 0, "점수는 읽되 종료로 보지 않는다"


def test_completed_game_is_final():
    games, _ = parse_rows([DONE], 2026)
    assert games[0]["status"] == "final"
    assert games[0]["away_score"] == 2 and games[0]["home_score"] == 1


def test_preview_game_is_scheduled():
    games, _ = parse_rows([PREVIEW], 2026)
    assert games[0]["status"] == "scheduled"


def test_cancelled_game_is_not_final():
    games, _ = parse_rows([CANCEL], 2026)
    assert games[0]["status"] == "cancelled"


# ---------------------------------------------------------------- 날짜 이어쓰기

def test_date_carries_to_following_rows():
    """같은 날 두 번째 경기부터는 날짜 칸이 없다 — 직전 날짜를 이어 쓴다."""
    second = ["19:00", "KT3vs1SSG", "리뷰", "하이라이트", "TV", "", "문학", "-"]
    games, failed = parse_rows([DONE, second], 2026)
    assert failed == 0
    assert [g["date"] for g in games] == ["2026-08-24", "2026-08-24"]
    assert games[1]["time"] == "19:00"


def test_row_before_any_date_is_counted_as_failure():
    """날짜를 모르는 행은 버리고 실패로 센다 — 조용히 넘기지 않는다."""
    orphan = ["19:00", "KT3vs1SSG", "리뷰", "", "TV", "", "문학", "-"]
    games, failed = parse_rows([orphan], 2026)
    assert games == [] and failed == 1


# ---------------------------------------------------------------- 팀 사전

def test_team_dictionary_covers_all_ten_clubs():
    assert len(KBO_TEAMS) == 10
    assert len(set(KBO_TEAMS.values())) == 10, "Odds API 표기가 중복되면 매핑이 깨진다"


def test_parsed_teams_map_to_odds_api_names():
    games, _ = parse_rows([DONE], 2026)
    assert games[0]["home"] == "Doosan Bears"
    assert games[0]["away"] == "LG Twins"
    assert games[0]["home_kr"] == "두산"


def test_every_stadium_home_team_is_in_dictionary():
    for teams in STADIUM_HOME.values():
        for t in teams:
            assert t in KBO_TEAMS, f"{t}가 팀 사전에 없다"


def test_ext_id_is_stable_and_unique():
    games, _ = parse_rows([DONE, PREVIEW], 2026)
    ids = [g["ext_id"] for g in games]
    assert len(set(ids)) == 2
    assert ids[0] == "kbo:2026-08-24:18:30:LG:두산"


def test_doubleheader_ext_ids_differ_by_time():
    """같은 카드 더블헤더는 시각으로 구분한다. game_id(ext_id)가 같으면 한 행으로 뭉개진다."""
    first = ["08.24(월)", "14:00", "LGvs두산", "프리뷰", "", "TV", "", "잠실", "-"]
    second = ["18:30", "LGvs두산", "프리뷰", "", "TV", "", "잠실", "-"]
    games, _ = parse_rows([first, second], 2026)
    assert games[0]["ext_id"] != games[1]["ext_id"]
    assert "14:00" in games[0]["ext_id"] and "18:30" in games[1]["ext_id"]


# ---------------------------------------------------------------- 구조 변경 감지

@pytest.mark.asyncio
async def test_empty_rows_trigger_alert(monkeypatch):
    """구조가 바뀌어 0건이 되면 조용히 넘어가지 않고 알린다."""
    from app.collectors import kbo

    sent = []

    async def fake_stage_failed(stage):
        sent.append(stage)
        return True

    monkeypatch.setattr("app.alerts.stage_failed", fake_stage_failed)

    class FakeClient:
        async def schedule_rows(self, season, month):
            return []

    out = await kbo.fetch_month(2026, 8, FakeClient())
    assert out == []
    assert sent and sent[0].cause == "parse"
    assert "채점" in sent[0].impact
