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


def test_side_form_facts_no_season_era():
    from app.collectors.mlb_boxscore import apply_boxscores, side_form_facts

    box = {"teams": {"home": {
        "pitchers": ["1", "2"],
        "teamStats": {
            "batting": {"hits": 9, "homeRuns": 2, "baseOnBalls": 4,
                        "strikeOuts": 8},
            "fielding": {"errors": 1},
        },
        "players": {
            "ID1": {"person": {"fullName": "Starter"},
                    "stats": {"pitching": {"inningsPitched": "5.1",
                                           "runs": 2, "numberOfPitches": 88,
                                           "earnedRuns": 2}}},
            "ID2": {"person": {"fullName": "Reliever"},
                    "stats": {"pitching": {"inningsPitched": "1.2",
                                           "runs": 0}}},
        },
    }, "away": {"pitchers": [], "players": {}, "teamStats": {}}}}
    facts = side_form_facts(box, "home")
    assert facts["starter_ip"] == 5 + 1 / 3
    assert facts["starter_r"] == 2
    assert facts["starter_pitches"] == 88
    assert facts["bullpen_count"] == 1
    assert facts["hits"] == 9 and facts["hr"] == 2
    assert facts["bb"] == 4 and facts["k"] == 8
    assert facts["errors"] == 1
    assert "era" not in facts
    form = {"CLE": {"games": [{"game_id": "1", "home": True, "runs": 5}]}}
    apply_boxscores(form, {"1": box})
    assert form["CLE"]["games"][0]["starter_name"] == "Starter"
