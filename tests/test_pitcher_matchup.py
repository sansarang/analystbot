"""투수 맞대결 사실층 — 컷오프·표본·시즌 ERA 오표기를 막는다.

0단계 실측(2026-08-28): 타석 단위는 없고 등판 단위(IP/TBF/ER)만 있다.
λ 계수는 만들지 않는다.
"""
import json
from datetime import UTC, datetime, timedelta

from app.collectors.kbo_boxscore import parse_official_ip, parse_official_pitchers
from app.collectors.yahoo_npb import parse_npb_ip, parse_pitching_stats
from app.engine.performance import FIELD_TO_COEFFICIENT, UNMAPPED_FIELDS, WinProbAdjuster
from app.engine.pitcher_matchup import (
    MIN_RATE_APPS,
    SEASON_VS_TEAM_LABEL,
    era_from_apps,
    format_pitcher,
    format_season_vs_team,
    from_rows,
    season_vs_team_of,
    today_pitchers,
)
from app.config import Settings
from app.research.validate import sanitize_research

NINE = ["김도영(3루수)", "박찬호(유격수)", "최형우(지명타자)", "나성범(우익수)",
        "소크라테스(중견수)", "변우혁(1루수)", "김선빈(2루수)",
        "한준수(포수)", "이우성(좌익수)"]
OTHER = ["A(1루수)", "B(2루수)", "C(3루수)", "D(유격수)", "E(좌익수)",
         "F(중견수)", "G(우익수)", "H(포수)", "I(지명타자)"]

T0 = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)


def _app(gid, *, ip, er, start=None, pitcher="양현종", opponent="LG Twins"):
    return {
        "game_id": gid, "pitcher": pitcher, "opponent": opponent,
        "is_starter": True, "innings": ip, "er": er, "batters": 24,
        "hits": 5, "hr": 0, "k": 6, "bb": 2, "r": er,
        "starts_at": start if start is not None else T0 - timedelta(days=gid),
    }


def test_official_ip_rejects_entry_inning():
    """등판 '7.9'는 7회 2사 투입이다. 이닝으로 읽으면 안 된다."""
    assert parse_official_ip("1 2/3") == 1.667
    assert parse_official_ip("2 1/3") == 2.333
    assert parse_official_ip("6") == 6.0
    assert parse_official_ip("7.9") is None
    assert parse_official_ip("") is None


def test_official_pitchers_use_game_line_not_season_era():
    """실측 헤더 17열. 마지막 열 평균자책점은 시즌값 — 저장하지 않는다."""
    header = ["선수명", "등판", "결과", "승", "패", "세", "이닝", "타자",
              "투구수", "타수", "피안타", "홈런", "4사구", "삼진", "실점",
              "자책", "평균자책점"]
    rows = [
        {"row": [{"Text": c} for c in header]},
        {"row": [{"Text": c} for c in [
            "양현종", "선발", "&nbsp;", "1", "0", "0", "6", "24",
            "95", "22", "5", "0", "2", "7", "1", "1", "3.45"]]},
        {"row": [{"Text": c} for c in [
            "정해영", "7.9", "세", "0", "0", "1", "1 1/3", "5",
            "18", "4", "0", "0", "1", "2", "0", "0", "2.10"]]},
    ]
    got = parse_official_pitchers({"rows": rows})
    assert len(got) == 2
    assert got[0]["name"] == "양현종" and got[0]["is_starter"] is True
    assert got[0]["innings"] == 6.0 and got[0]["er"] == 1 and got[0]["batters"] == 24
    assert "era" not in got[0] and "era_season" not in got[0]
    assert got[1]["is_starter"] is False
    assert got[1]["innings"] == 1.333


def test_official_pitchers_read_headers_not_first_data_row():
    """실측 2026-08-28: 헤더는 headers, rows[0]은 선수(토다). table 키."""
    from app.collectors.kbo_boxscore import parse_box

    header = ["선수명", "등판", "결과", "승", "패", "세", "이닝", "타자",
              "투구수", "타수", "피안타", "홈런", "4사구", "삼진", "실점",
              "자책", "평균자책점"]
    data = ["토다", "선발", "승", "7", "8", "0", "6", "26",
            "108", "25", "8", "0", "1", "3", "3", "3", "5.04"]
    blob = {
        "headers": [{"row": [{"Text": c} for c in header]}],
        "rows": [{"row": [{"Text": c} for c in data]}],
    }
    got = parse_official_pitchers(blob)
    assert len(got) == 1
    assert got[0]["name"] == "토다" and got[0]["is_starter"] is True
    assert got[0]["innings"] == 6.0 and got[0]["er"] == 3 and got[0]["batters"] == 26
    assert "era" not in got[0]

    nine = [{"row": [{"Text": str(i)}, {"Text": "중"}, {"Text": f"타자{i}"}]}
            for i in range(1, 10)]
    hitter = json.dumps({"rows": nine})
    box = parse_box({
        "arrHitter": [{"table1": hitter}, {"table1": hitter}],
        "arrPitcher": [{"table": blob}, {"table": blob}],
    }, "2026-08-27", "x")
    assert len(box["away_pitchers"]) == 1 and box["away_pitchers"][0]["name"] == "토다"
    assert len(box["home"]) == 9


def test_npb_ip_is_outs_not_decimal():
    """Yahoo `6.2` = 6⅔. float(6.2)으로 읽으면 틀리다."""
    assert parse_npb_ip("6.2") == 6.667
    assert parse_npb_ip("6.1") == 6.333
    assert parse_npb_ip("7") == 7.0
    assert parse_npb_ip("0.1") == 0.333
    assert parse_npb_ip("6.5") is None


def test_npb_stats_first_table_is_away():
    """실측: /stats 투수표는 원정 먼저. /top 打順(홈 먼저)과 반대."""
    def tbl(rows):
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                       for r in rows)
        return f"<table>{body}</table>"
    head = ["", "選手名", "防御率", "投球回", "投球数", "打者", "被安打",
            "被本塁打", "奪三振", "与四球", "与死球", "ボーク", "失点", "自責点"]
    away = tbl([head, ["", "井上 温大", "3.38", "6.2", "98", "27",
                       "6", "1", "5", "2", "0", "0", "2", "2"]])
    home = tbl([head, ["", "石川 達也", "162.00", "0.1", "8", "3",
                       "2", "1", "0", "0", "0", "0", "3", "3"],
                ["", "清水 昇", "1.99", "1.0", "15", "4",
                 "0", "0", "2", "1", "0", "0", "0", "0"]])
    got = parse_pitching_stats(away + home)
    assert got["away"][0]["name"] == "井上 温大"
    assert got["away"][0]["is_starter"] is True
    assert got["away"][0]["innings"] == 6.667
    assert got["away"][0]["er"] == 2
    assert got["home"][0]["name"] == "石川 達也"
    assert got["home"][0]["innings"] == 0.333
    assert "era" not in got["home"][0], "시즌 防御率 162.00을 경기 ERA로 넣었다"


def test_cutoff_excludes_today_and_future():
    nine = [n.split("(")[0] for n in NINE]
    rows = [
        _app(99, ip=6, er=1, start=T0),
        _app(98, ip=7, er=0, start=T0 + timedelta(hours=1)),
        _app(1, ip=6, er=2, start=T0 - timedelta(days=2)),
    ]
    rec = from_rows("양현종", "starter", nine, rows, {}, T0)
    assert rec["n"] == 1 and rec["appearances"][0]["game_id"] == 1
    assert rec["era_window"] is None  # 1등판


def test_thin_sample_has_no_era():
    nine = [n.split("(")[0] for n in NINE]
    rows = [_app(i, ip=6, er=1) for i in range(1, MIN_RATE_APPS)]
    rec = from_rows("양현종", "starter", nine, rows, {}, T0)
    assert rec["n"] == MIN_RATE_APPS - 1
    assert rec["era_window"] is None
    assert rec["era_vs_similar_nine"] is None
    line = format_pitcher(rec)
    assert "미산출" in line
    assert "ERA 1" not in line and "창 ERA" not in line


def test_three_apps_get_window_era_not_labeled_as_this_nine():
    nine = [n.split("(")[0] for n in NINE]
    rows = [
        _app(1, ip=6, er=2),
        _app(2, ip=6, er=1),
        _app(3, ip=6, er=3),
    ]
    rec = from_rows("양현종", "starter", nine, rows, {}, T0)
    assert rec["era_window"] == 3.0  # 6 ER / 18 IP * 9
    assert rec["era_vs_similar_nine"] is None  # 겹치는 타순 없음
    line = format_pitcher(rec)
    assert "상대 타선은 그때그때 다름" in line
    assert "오늘 9명과 유사한" not in line


def test_similar_nine_era_needs_three_overlaps():
    nine = [n.split("(")[0] for n in NINE]
    lu = {i: NINE for i in range(1, 4)}
    rows = [_app(i, ip=6, er=i) for i in range(1, 4)]
    rec = from_rows("양현종", "starter", nine, rows, lu, T0)
    assert rec["n_similar"] == 3
    assert rec["era_vs_similar_nine"] == 3.0  # 6 ER / 18 IP
    lu2 = {1: NINE, 2: OTHER, 3: OTHER}
    rec2 = from_rows("양현종", "starter", nine, rows, lu2, T0)
    assert rec2["n_similar"] == 1
    assert rec2["era_vs_similar_nine"] is None


def test_season_vs_team_is_never_last5():
    line = format_season_vs_team({"era": 1.69})
    assert SEASON_VS_TEAM_LABEL in line
    assert "오늘 9명 아님" in line
    assert "최근" not in line and "last" not in line.lower()
    blk = season_vs_team_of(
        {"home_pitcher": {"era_vs_opponent": 1.69}}, "home")
    assert blk["scope"] == "season_vs_team"
    assert blk["label"] == SEASON_VS_TEAM_LABEL


def test_sanitize_drops_thin_matchup_era_and_fixes_season_label():
    dirty = {
        "pitcher_matchup": {
            "home": {
                "pitchers": [{
                    "name": "양현종", "role": "starter", "n": 2,
                    "era_window": 1.11, "era_vs_similar_nine": 0.00,
                    "n_similar": 1, "appearances": [{"innings": 6, "er": 1}],
                }],
                "season_vs_team": {
                    "era": 1.69,
                    "label": "최근 5경기 vs 오늘 타선",
                },
            }
        }
    }
    out, dropped = sanitize_research(dirty, "kbo")
    p = out["pitcher_matchup"]["home"]["pitchers"][0]
    assert "era_window" not in p
    assert "era_vs_similar_nine" not in p
    assert out["pitcher_matchup"]["home"]["season_vs_team"]["label"] == SEASON_VS_TEAM_LABEL
    assert dropped == [] or "pitcher_matchup" not in dropped


def test_era_vs_opponent_survives_sanitize_with_scope():
    out, _ = sanitize_research({
        "home_pitcher": {"name": "山野 太一", "era_season": 2.15,
                         "era_vs_opponent": 1.69,
                         "era_vs_opponent_scope": "season_vs_team"},
    }, "npb")
    assert out["home_pitcher"]["era_vs_opponent"] == 1.69
    assert out["home_pitcher"]["era_vs_opponent_scope"] == "season_vs_team"


def test_pitcher_matchup_is_unmapped_not_a_coefficient():
    assert "pitcher_matchup" in UNMAPPED_FIELDS
    assert "pitcher_matchup" not in FIELD_TO_COEFFICIENT
    out = WinProbAdjuster(Settings(_env_file=None)).adjust(
        0.5, {"home": "H", "away": "A"},
        {"pitcher_matchup": {"home": {"pitchers": [{"n": 5}]}}},
        "kbo")
    assert "투수 최근 등판 vs 상대 타선" in out["unused"]
    assert out["p"] == 0.5


def test_today_pitchers_starter_then_relievers():
    res = {
        "home_pitcher": {"name": "양현종"},
        "home_usage": {"key_relievers": ["정해영", "양현종"]},
        "home_bullpen_staff": ["정해영", "김대유"],
    }
    names = today_pitchers(res, "home")
    assert names[0] == ("양현종", "starter")
    roles = {n: r for n, r in names}
    assert roles["정해영"] == "reliever" and roles["김대유"] == "reliever"
    assert len(names) == 3


def test_lookback_keeps_newest_five_not_oldest():
    """창은 최근 5등판. 입력 순서가 오래된 것부터여도 같다."""
    nine = [n.split("(")[0] for n in NINE]
    rows = [_app(i, ip=6, er=9 if i >= 6 else 0) for i in range(1, 9)]
    rec = from_rows("양현종", "starter", nine, rows, {}, T0)
    assert rec["n"] == 5
    assert {a["game_id"] for a in rec["appearances"]} == {1, 2, 3, 4, 5}
    assert rec["era_window"] == 0.0  # 최근 5경기 ER 0. 6~8은 창 밖.


def test_zero_inning_does_not_invent_era():
    assert era_from_apps([{"innings": 0, "er": 3}]) is None
    assert era_from_apps([{"innings": 0.333, "er": 3}]) is None  # IP < 1
    assert era_from_apps([{"innings": 6, "er": 2}]) == 3.0


def test_names_with_dots_still_match():
    nine = [n.split("(")[0] for n in NINE]
    rows = [_app(1, ip=6, er=1, pitcher="양현종.")]
    rec = from_rows("양현종", "starter", nine, rows, {1: NINE}, T0)
    assert rec["n"] == 1
