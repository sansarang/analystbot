"""MLB boxscore 백필 — inningsPitched 표기와 등판 파싱."""

from app.collectors.mlb_boxscore import parse_mlb_ip, parse_pitching, order_text


def test_parse_mlb_ip_outs():
    assert parse_mlb_ip("5.1") == 5 + 1 / 3
    assert parse_mlb_ip("5.2") == 5 + 2 / 3
    assert parse_mlb_ip("6.0") == 6.0
    assert parse_mlb_ip("7") == 7.0
    assert parse_mlb_ip("") is None


def test_parse_pitching_first_is_starter():
    box = {"teams": {"home": {
        "pitchers": ["1", "2"],
        "players": {
            "ID1": {"person": {"fullName": "Starter"},
                    "stats": {"pitching": {"inningsPitched": "5.1",
                                           "earnedRuns": 2, "battersFaced": 22,
                                           "hits": 4, "homeRuns": 1,
                                           "strikeOuts": 6, "baseOnBalls": 1,
                                           "runs": 2}}},
            "ID2": {"person": {"fullName": "Reliever"},
                    "stats": {"pitching": {"inningsPitched": "1.2",
                                           "earnedRuns": 0, "battersFaced": 6,
                                           "hits": 0, "homeRuns": 0,
                                           "strikeOuts": 2, "baseOnBalls": 0,
                                           "runs": 0}}},
        },
    }, "away": {"pitchers": [], "players": {}}}}
    pits = parse_pitching(box)
    assert pits["home"][0]["name"] == "Starter" and pits["home"][0]["is_starter"]
    assert pits["home"][1]["name"] == "Reliever" and not pits["home"][1]["is_starter"]
    assert pits["home"][0]["innings"] == 5 + 1 / 3


def test_order_text_joins_names():
    assert order_text({"batting_order": ["A", "B", "C"]}) == "A-B-C"
