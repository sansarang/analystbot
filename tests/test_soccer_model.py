"""축구 3-way 디비그 · 팀명 퍼지 매칭 · Elo 모델 단위 테스트."""

from datetime import UTC, datetime

import pytest

from app.collectors.football import match_team_name, similar_team, team_tokens
from app.engine.value import devig, implied_prob
from app.models.soccer_elo import SoccerElo, probs_from_diff, replay
from app.pipeline import _market_probs


def test_devig_two_way_mlb():
    ph, pa = devig([implied_prob(1.9), implied_prob(2.0)])
    assert ph + pa == pytest.approx(1.0)
    assert ph == pytest.approx((1 / 1.9) / (1 / 1.9 + 1 / 2.0))


def test_devig_three_way_soccer():
    # 홈 1.5 / 무 4.2 / 원정 6.0 — 무승부를 포함해 정규화해야 한다
    probs = devig([implied_prob(1.5), implied_prob(4.2), implied_prob(6.0)])
    assert sum(probs) == pytest.approx(1.0)
    over = 1 / 1.5 + 1 / 4.2 + 1 / 6.0
    assert probs[0] == pytest.approx((1 / 1.5) / over)
    # 2-way로 잘못 디비그하면 홈 확률이 부풀어야 함 (버그 재현 검증)
    wrong_two_way = devig([implied_prob(1.5), implied_prob(6.0)])[0]
    assert wrong_two_way > probs[0] + 0.05


async def test_market_probs_three_way_in_db(db_pool):
    game_id = await db_pool.fetchval(
        "INSERT INTO games (sport, league, ext_id, starts_at, home, away) "
        "VALUES ('soccer', 'EPL', 's3w', $1, 'HomeFC', 'AwayFC') RETURNING id",
        datetime(2026, 8, 23, 12, 0, tzinfo=UTC),
    )
    for side, odds in (("HomeFC", 1.5), ("Draw", 4.2), ("AwayFC", 6.0)):
        await db_pool.execute(
            "INSERT INTO odds_snapshots (game_id, book, market, side, odds) "
            "VALUES ($1, 'dk', 'h2h', $2, $3)", game_id, side, odds,
        )
    probs, best = await _market_probs(db_pool, game_id, "HomeFC", "AwayFC")
    assert set(probs) == {"HomeFC", "Draw", "AwayFC"}
    assert sum(probs.values()) == pytest.approx(1.0)
    over = 1 / 1.5 + 1 / 4.2 + 1 / 6.0
    assert probs["HomeFC"] == pytest.approx((1 / 1.5) / over)
    assert best["AwayFC"] == 6.0


def test_team_fuzzy_matching():
    assert similar_team("Manchester City FC", "Manchester City")
    assert similar_team("OB Odense BK", "Odense")
    assert similar_team("AGF Aarhus", "Aarhus")
    assert not similar_team("Liverpool", "Everton")
    assert match_team_name("Manchester City", ["Man City", "Norwich City", "Man United"]) == "Man City"
    assert match_team_name("FC Machida Zelvia", ["Machida", "Urawa Reds", "FC Tokyo"]) == "Machida"
    # 모호(동점)하면 None
    assert match_team_name("City", ["Man City", "Norwich City"]) is None
    assert team_tokens("FC Nordsjaelland") == {"nordsjaelland"}


def test_probs_from_diff_properties():
    ph, pd_, pa = probs_from_diff(0.0, -0.6, 0.6)
    assert ph + pd_ + pa == pytest.approx(1.0)
    assert ph == pytest.approx(pa)  # 동일 전력 + HA 0 → 대칭
    stronger = probs_from_diff(200.0, -0.6, 0.6)
    assert stronger[0] > ph and stronger[2] < pa


def test_replay_updates_ratings_walk_forward():
    matches = [
        {"date": datetime(2026, 1, i + 1), "home": "A", "away": "B",
         "res": "H", "season": "s1", "market": None}
        for i in range(5)
    ]
    ratings, records = replay(matches, home_adv=60.0)
    assert ratings["A"] > 1500 > ratings["B"]
    # 첫 경기 예측은 갱신 전 레이팅(동률) 기준이어야 walk-forward
    assert records[0][0] == pytest.approx(60.0)
    assert records[-1][0] > records[0][0]


def test_soccer_elo_probs_inference():
    elo = SoccerElo(
        ratings={"DNK": {"Aarhus": 1560.0, "Odense": 1480.0}},
        params={"DNK": {"home_adv": 60.0, "c1": -0.6, "c2": 0.6}},
    )
    p = elo.probs("AGF Aarhus", "OB Odense BK", "덴마크 수페르리가")
    assert p is not None and sum(p) == pytest.approx(1.0, abs=1e-3)
    assert p[0] > p[2]  # 홈+레이팅 우위
    assert elo.probs("Unknown FC", "OB Odense BK", "덴마크 수페르리가") is None
    assert elo.probs("AGF Aarhus", "OB Odense BK", "K리그") is None  # 미지원 리그
