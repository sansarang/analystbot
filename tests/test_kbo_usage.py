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


# ---------------------------------------------------------------- 카드 ③ 스코어보드

from app.collectors.kbo_usage import classify_game, parse_scoreboard  # noqa: E402

# 실제(2026-08-26 광주): 롯데 11 - 16 KIA. 홈은 9회말을 치지 않아 배열이 8칸이다.
REAL_SB = {"scoreBoard": {
    "rheb": {"away": {"r": 11, "h": 20, "e": 0, "b": 3},
             "home": {"r": 16, "h": 13, "e": 0, "b": 10}},
    "inn": {"away": [1, 0, 2, 0, 0, 2, 0, 6, 0], "home": [3, 0, 2, 3, 3, 0, 5, 0]}}}


def test_scoreboard_handles_uneven_innings():
    """홈팀은 이기고 있으면 9회말을 치지 않는다 — 배열 길이가 다르다."""
    home = parse_scoreboard(REAL_SB, "home")
    away = parse_scoreboard(REAL_SB, "away")
    assert home["runs"] == 16 and home["opp_runs"] == 11
    assert away["runs"] == 11 and away["opp_runs"] == 16
    assert len(home["runs_by_inning"]) == 8 and len(away["runs_by_inning"]) == 9
    assert home["result"] == "W" and away["result"] == "L"


def test_comeback_needs_inning_by_inning_not_final_score():
    """🔴 최종 스코어만으로는 '9회에 뒤집혔다'와 '처음부터 앞섰다'가 구분되지 않는다."""
    # 8/26 KIA는 1회부터 앞서 끝까지 리드 — 역전승이 아니다
    assert classify_game([3, 0, 2, 3, 3, 0, 5, 0], [1, 0, 2, 0, 0, 2, 0, 6, 0]) == {
        "result": "W", "margin": 5, "comeback_win": False, "blown_lead": False,
        "shutout_loss": False, "shutout_win": False, "one_run": False}
    # 같은 5-4라도 뒤졌다가 이기면 역전승
    assert classify_game([0, 0, 0, 0, 0, 0, 0, 0, 5], [4, 0, 0, 0, 0, 0, 0, 0, 0]
                         )["comeback_win"] is True
    # 앞서다 졌으면 역전패 (불펜 붕괴 신호)
    assert classify_game([4, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 5]
                         )["blown_lead"] is True


def test_shutout_and_one_run_are_distinguished():
    """같은 1패라도 완봉패와 1점차 패는 정반대 상태다."""
    sh = classify_game([0] * 9, [0, 0, 3, 0, 0, 0, 0, 0, 0])
    assert sh["shutout_loss"] is True and sh["one_run"] is False
    close = classify_game([0, 0, 2, 0, 0, 0, 0, 0, 0], [0, 3, 0, 0, 0, 0, 0, 0, 0])
    assert close["shutout_loss"] is False and close["one_run"] is True


def test_scoreboard_missing_returns_none_not_zeros():
    """수집 실패를 0득점으로 내보내면 '타선 침묵 ▼'으로 오독된다."""
    assert parse_scoreboard({}, "home") is None
    assert parse_scoreboard({"scoreBoard": {"inn": {}}}, "home") is None


def test_summarize_includes_card3_facts():
    games = [{"date": "2026-08-26", "pitchers": parse_pitchers(REAL_RECORD, "away"),
              "score": parse_scoreboard(REAL_SB, "away")}]
    s = summarize(games)
    assert s["results_l3"] == "L"
    assert s["runs_l3"] == 11 and s["runs_allowed_l3"] == 16
    assert s["score_games"] == 1


# ---------------------------------------------------------------- 카드 ④ 순위표

def test_standings_computes_games_behind_without_extra_http():
    """[§8-34] 순위 전용 엔드포인트는 403이다(실측). 프리뷰에서 조립한다."""
    from app.collectors.naver_kbo import KBO_SEASON_GAMES, build_standings

    table = {
        "Samsung Lions@KT Wiz": {
            "home_team": {"rank": 1, "w": 65, "l": 42, "d": 3},
            "away_team": {"rank": 2, "w": 66, "l": 44, "d": 3}},
        "Lotte Giants@Kia Tigers": {
            "home_team": {"rank": 4, "w": 62, "l": 50, "d": 2},
            "away_team": {"rank": 6, "w": 50, "l": 60, "d": 2}},
    }
    st = build_standings(table)
    assert st["KT Wiz"]["games_behind"] == 0.0
    # ((65-66) + (44-42)) / 2 = 0.5
    assert st["Samsung Lions"]["games_behind"] == 0.5
    assert st["Kia Tigers"]["games_behind"] == 5.5
    assert st["Kia Tigers"]["remaining"] == KBO_SEASON_GAMES - 114


def test_standings_keeps_official_rank_not_recomputed():
    """순위를 승률로 다시 매기면 무승부 처리 차이로 공식 순위와 어긋난다."""
    from app.collectors.naver_kbo import build_standings

    table = {"A@B": {"home_team": {"rank": 3, "w": 10, "l": 5, "d": 9},
                     "away_team": {"rank": 1, "w": 11, "l": 5, "d": 0}}}
    assert build_standings(table)["B"]["rank"] == 3


def test_standings_empty_input_is_empty():
    from app.collectors.naver_kbo import build_standings

    assert build_standings({}) == {}
    assert build_standings({"A@B": {}}) == {}


def test_standings_omits_games_behind_without_the_leader():
    """🔴 부분 표에서 가짜 선두를 세우면 게임차가 조용히 틀린다.

    못 구하는 값은 만들지 않는다 — 빈칸이 틀린 값보다 낫다.
    """
    from app.collectors.naver_kbo import build_standings

    partial = {"A@B": {"home_team": {"rank": 4, "w": 62, "l": 50, "d": 2},
                       "away_team": {"rank": 6, "w": 50, "l": 60, "d": 2}}}
    st = build_standings(partial)
    assert "games_behind" not in st["B"], "1위가 없는데 게임차를 만들어냈다"
    assert st["B"]["remaining"] == 30, "잔여 경기는 그 팀만으로 계산되므로 남아야 한다"
