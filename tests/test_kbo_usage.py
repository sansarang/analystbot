"""[§8-33] 투수 소모 수집 — 카드 ①칸의 재료.

이 칸이 다섯 칸 중 가장 중요하다. "어제 불펜 5명이 26타자를 상대했다"는
시즌 ERA보다 오늘 승패를 잘 설명하는데, 기존 λ는 시즌 누적만 봐서 통째로 놓쳤다.
"""

import pytest

from app.collectors.kbo_usage import (
    RECENT_GAMES,
    fetch_recent_usage,
    merge_into_research,
    parse_innings,
    parse_pitchers,
    summarize,
)

# 실제 응답(2026-08-26 광주, 롯데 11 - 16 KIA). 경기값·시즌값이 한 행에 섞여 있다.
REAL_RECORD = {"pitchersBoxscore": {
    "away": [
        {"name": "로드리게스", "inn": "3 ⅔", "pa": 22, "bf": 84, "era": "4.23", "gameCount": 23},
        {"name": "이영재", "inn": "0 ⅓", "pa": 2, "bf": 6, "era": "2.25", "gameCount": 8},
        {"name": "김한결", "inn": "0 ⅔", "pa": 4, "bf": 15, "era": "8.22", "gameCount": 5},
        {"name": "정현수", "inn": "0", "pa": 1, "bf": 8, "era": "5.40", "gameCount": 12},
        {"name": "이민석", "inn": "1 ⅔", "pa": 11, "bf": 44, "era": "6.19", "gameCount": 21},
        {"name": "이진하", "inn": "1 ⅔", "pa": 7, "bf": 23, "era": "4.50", "gameCount": 11},
    ],
    "home": [{"name": "황동하", "inn": "2 ⅔", "pa": 13, "bf": 43}],
}}


def test_parse_innings_handles_naver_fractions():
    assert parse_innings("3 ⅔") == 3.667
    assert parse_innings("0 ⅓") == 0.333
    assert parse_innings("1") == 1.0
    assert parse_innings("0") == 0.0


def test_parse_innings_distinguishes_zero_from_unknown():
    """0과 '모름'을 섞으면 '안 던졌다'와 '파싱 실패'가 구분되지 않는다."""
    assert parse_innings("0") == 0.0
    assert parse_innings("") is None
    assert parse_innings(None) is None
    assert parse_innings("정보없음") is None


def test_parse_pitchers_uses_game_values_not_season():
    """🔴 회귀 핵심 — `bf`는 시즌값이다. 경기값으로 오인하면 타자 수가 4배가 된다.

    실측(2026-08-27): 선수 `pa` 합 47 = 팀 `pa` 합 47. `bf` 합은 180이었다.
    """
    rows = parse_pitchers(REAL_RECORD, "away")
    assert len(rows) == 6
    assert sum(r["batters"] for r in rows) == 47, "팀 합계(47)와 어긋난다 — bf를 쓴 것"
    assert rows[0]["name"] == "로드리게스" and rows[0]["is_starter"] is True
    assert all(r["is_starter"] is False for r in rows[1:])


def test_summarize_splits_starter_and_relief():
    games = [{"date": "2026-08-26", "pitchers": parse_pitchers(REAL_RECORD, "away")}]
    s = summarize(games)
    assert s["pitchers_used_last"] == 6
    assert s["starter_ip_l3"] == 3.67           # 선발만 (합계는 소수 2자리)
    assert round(s["relief_ip_l3"], 2) == 4.33  # 나머지 5명
    assert s["relief_batters_last"] == 25       # 47 - 22


def test_back_to_back_is_observed_not_inferred():
    """연투는 **관측**이다 — '마무리'라는 역할 추정 없이 나온다.

    응답에 역할 라벨이 없으므로 '마무리 연투'는 추정이고, 추정을 사실 칸에
    넣으면 카드가 오염된다.
    """
    mk = lambda names: [{"name": n, "innings": 1.0, "batters": 3, "is_starter": i == 0}
                        for i, n in enumerate(names)]
    games = [
        {"date": "2026-08-26", "pitchers": mk(["선발A", "정해영", "김범수"])},
        {"date": "2026-08-25", "pitchers": mk(["선발B", "정해영", "곽도규"])},
        {"date": "2026-08-24", "pitchers": mk(["선발C", "최지민"])},
    ]
    s = summarize(games)
    assert s["back_to_back"] == ["정해영"], "최근 2경기 모두 등판한 투수만"
    assert s["back_to_back_count"] == 1
    assert s["window_games"] == RECENT_GAMES


def test_summarize_empty_is_empty_not_zero():
    """수집 실패를 '소모 0'으로 내보내면 '충분함 ▲'으로 오독된다."""
    assert summarize([]) == {}


def test_merge_into_research_does_not_interpret():
    research: dict = {}
    jg = {"home": "Kia Tigers", "away": "Lotte Giants"}
    table = {"Kia Tigers": {"relief_ip_l3": 6.33, "back_to_back_count": 3}}
    filled = merge_into_research(research, jg, table)
    assert "home_usage.relief_ip_l3" in filled
    assert research["home_usage"]["relief_ip_l3"] == 6.33
    assert "away_usage" not in research          # 없는 팀은 만들지 않는다
    # 해석 문구가 섞이면 안 된다 — ▲▼는 2단 해석봇이 정한다
    assert all(not isinstance(v, str) or "얇" not in v
               for v in research["home_usage"].values())


class _FakeClient:
    """당일 경기를 응답에 섞어 넣어 누출 방지가 실제로 동작하는지 본다."""

    def __init__(self):
        self.asked: list[str] = []

    async def games(self, date):
        self.asked.append(date)
        return [{"gameId": f"G{date}", "homeTeamName": "KIA", "awayTeamName": "롯데"}]

    async def record(self, gid):
        return {"pitchersBoxscore": {
            "home": [{"name": "선발", "inn": "5", "pa": 20}],
            "away": [{"name": "선발2", "inn": "5", "pa": 20}]}}


@pytest.mark.asyncio
async def test_usage_never_reads_the_target_date():
    """🔴 누출 방지 — 예측 대상일의 경기는 그 시점에 알 수 없다."""
    c = _FakeClient()
    out = await fetch_recent_usage("2026-08-27", client=c)
    assert "2026-08-27" not in c.asked, "예측 대상일을 조회했다 — 누출"
    assert c.asked[0] == "2026-08-26"
    assert out["Kia Tigers"]["window_games"] == RECENT_GAMES
