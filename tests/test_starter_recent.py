"""오늘 선발 최근 등판. 시즌 ERA는 넣지 않는다."""
from datetime import UTC, datetime

from app.engine.starter_recent import pitcher_name, slim_start


def test_slim_start_omits_era():
    row = {
        "opponent": "KIA", "innings": 6.0, "r": 2, "hits": 5,
        "k": 7, "bb": 1, "er": 2, "era": 3.00,
        "starts_at": datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
    }
    got = slim_start(row)
    assert got["opponent"] == "KIA"
    assert got["innings"] == 6.0
    assert got["r"] == 2
    assert got["date"] == "2026-08-20"
    assert "era" not in got
    assert "er" not in got


def test_pitcher_name_falls_back_to_game_column_when_research_empty():
    jg = {"home_pitcher": "Carlos Rodón", "away_pitcher": "Blake Snell",
          "research": {}}
    assert pitcher_name(jg, "home") == "Carlos Rodón"
    assert pitcher_name(jg, "away") == "Blake Snell"


def test_pitcher_name_prefers_research_dict():
    jg = {
        "home_pitcher": "wrong",
        "research": {"home_pitcher": {"name": "페덱"}},
    }
    assert pitcher_name(jg, "home") == "페덱"
