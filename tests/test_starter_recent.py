"""오늘 선발 최근 등판. 시즌 ERA는 넣지 않는다."""
from datetime import UTC, datetime

from app.engine.starter_recent import slim_start


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
