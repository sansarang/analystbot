"""NPB 최근 3경기 — Yahoo 일정 점수 + /stats 선발 이닝. 시즌 ERA는 넣지 않는다."""
from app.collectors.npb_form import (
    apply_boxscores,
    fetch_recent_form,
    merge_into_research,
    parse_recent_form,
    summarize_pitching,
)


def _g(gid, day, home, away, hs, aws):
    return {
        "game_id": gid, "date": day, "home": home, "away": away,
        "home_score": hs, "away_score": aws,
    }


YAK = "Tokyo Yakult Swallows"
GIANTS = "Yomiuri Giants"
TIGERS = "Hanshin Tigers"
DRAGONS = "Chunichi Dragons"


def test_parse_recent_form_last_three_excludes_today():
    finals = [
        _g("1", "2026-08-28", YAK, GIANTS, 6, 8),
        _g("2", "2026-08-27", YAK, TIGERS, 3, 2),
        _g("3", "2026-08-26", DRAGONS, YAK, 1, 4),
        _g("4", "2026-08-25", YAK, GIANTS, 0, 1),   # 4번째 — 창 밖
        _g("today", "2026-08-29", YAK, TIGERS, 9, 0),  # 당일 누출 금지
    ]
    form = parse_recent_form(finals, before="2026-08-29")
    yak = form[YAK]
    assert yak["score_games"] == 3
    assert yak["results_l3"] == "LWW"          # 28패, 27승, 26승 (최신순)
    assert yak["runs_l3"] == 6 + 3 + 4
    assert "today" not in {g["game_id"] for g in yak["games"]}
    assert yak["games"][0]["opponent"] == GIANTS


def test_opponent_rank_win_pct_only_context():
    """허용: 상대 순위·승률 1줄. 금지: ERA를 폼 패킷에 넣는 것."""
    finals = [_g("1", "2026-08-28", YAK, GIANTS, 6, 8)]
    standings = {GIANTS: {"rank": 2, "win_pct": 0.580}}
    form = parse_recent_form(finals, before="2026-08-29", standings=standings)
    row = form[YAK]["games"][0]
    assert row["opponent_rank"] == 2
    assert row["opponent_win_pct"] == 0.580
    blob = str(form)
    assert "era" not in blob.lower()
    assert "xwoba" not in blob.lower()


def test_summarize_pitching_drops_season_era():
    pitchers = [
        {"name": "井上", "is_starter": True, "innings": 6.667, "r": 2, "er": 2},
        {"name": "清水", "is_starter": False, "innings": 1.0, "r": 0},
    ]
    got = summarize_pitching(pitchers)
    assert got["starter_name"] == "井上"
    assert got["starter_ip"] == 6.667
    assert got["starter_r"] == 2
    assert got["bullpen_count"] == 1
    assert "era" not in got


def test_apply_boxscores_home_away_sides():
    form = parse_recent_form(
        [_g("2021039325", "2026-08-28", YAK, GIANTS, 6, 8)],
        before="2026-08-29")
    by_gid = {
        "2021039325": {
            "home": [{"name": "山野", "is_starter": True, "innings": 6.0, "r": 8}],
            "away": [{"name": "井上", "is_starter": True, "innings": 7.0, "r": 6},
                     {"name": "清水", "is_starter": False, "innings": 1.0, "r": 0}],
        }
    }
    apply_boxscores(form, by_gid)
    yak = form[YAK]["games"][0]
    giants = form[GIANTS]["games"][0]
    assert yak["starter_name"] == "山野" and yak["starter_r"] == 8
    assert giants["bullpen_count"] == 1
    assert yak["bullpen_count"] == 0


def _stats_html():
    def tbl(rows):
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                       for r in rows)
        return f"<table>{body}</table>"

    head = ["", "選手名", "防御率", "投球回", "投球数", "打者", "被安打",
            "被本塁打", "奪三振", "与四球", "与死球", "ボーク", "失点", "自責点"]
    away = tbl([head, ["", "井上 温大", "3.38", "6.2", "98", "27",
                       "6", "1", "5", "2", "0", "0", "2", "2"]])
    home = tbl([head, ["", "石川 達也", "162.00", "6.0", "90", "24",
                       "5", "1", "4", "1", "0", "0", "3", "3"]])
    return away + home


class _Client:
    async def schedule(self, day):
        if day == "2026-08-28":
            return '''<div id="gm_card">
<a href="/npb/game/2021039325/index">神宮 ヤクルト 巨人 6 - 8 試合終了</a>
</div>'''
        return '<div id="gm_card"></div>'

    async def stats(self, gid):
        assert gid == "2021039325"
        return _stats_html()


async def test_fetch_recent_form_skips_today_and_attaches_box():
    form = await fetch_recent_form("2026-08-29", client=_Client(), days=2)
    yak = form[YAK]
    assert yak["score_games"] == 1
    assert yak["games"][0]["starter_ip"] == 6.0
    assert yak["games"][0]["starter_r"] == 3
    # 시즌 防御率 162.00 / 3.38 을 경기 ERA로 넣으면 안 된다
    assert "era" not in yak["games"][0]


def test_merge_does_not_copy_banned_season_keys():
    research = {}
    table = {YAK: {"results_l3": "WLW", "era_season": 3.21, "xwoba": 0.320}}
    filled = merge_into_research(research, {"home": YAK, "away": GIANTS}, table)
    assert "home_usage.results_l3" in filled
    assert "era_season" not in (research.get("home_usage") or {})
    assert "xwoba" not in (research.get("home_usage") or {})
