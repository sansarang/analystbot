"""엔진 수식 단위 테스트 + 목 judge 왕복 검증."""

import pytest

from app.engine.consensus import consensus_scores, expert_weight
from app.engine.judge import Judge
from app.engine.parlay import best_parlays
from app.engine.value import devig, ensemble, ev, heuristic_model_prob, implied_prob, kelly


def test_ev_known_value():
    # 스펙 검증값: p=0.687, odds=1.61 → EV +0.106
    assert round(ev(0.687, 1.61), 3) == 0.106


def test_implied_prob_and_devig():
    assert implied_prob(2.0) == 0.5
    devigged = devig([implied_prob(1.9), implied_prob(2.0)])
    assert abs(sum(devigged) - 1.0) < 1e-12
    assert devigged[0] > devigged[1]


def test_kelly_half_and_cap():
    # p=0.6, odds=2.0 → full kelly 0.2, half 0.1 → 5% 상한에 걸림
    assert kelly(0.6, 2.0) == 0.05
    # 상한 미만 케이스: p=0.55, odds=2.0 → full 0.1, half 0.05 → cap 경계
    assert kelly(0.55, 2.0) == pytest.approx(0.05)
    assert kelly(0.52, 2.0) == pytest.approx(0.02)
    # 엣지 없으면 0
    assert kelly(0.4, 2.0) == 0.0
    assert kelly(0.9, 1.0) == 0.0


def test_ensemble_weights():
    assert ensemble(1.0, 0.0, 0.0) == 0.45
    assert ensemble(0.0, 1.0, 0.0) == 0.30
    assert ensemble(0.0, 0.0, 1.0) == 0.25
    assert ensemble(0.6, 0.5, 0.55) == pytest.approx(0.45 * 0.6 + 0.30 * 0.5 + 0.25 * 0.55)


def test_heuristic_model_prob_bounds():
    assert 0.05 <= heuristic_model_prob(0.3, 0.7, 6.0, 2.0) <= 0.95
    strong_home = heuristic_model_prob(0.65, 0.45, 2.8, 4.5)
    weak_home = heuristic_model_prob(0.45, 0.65, 4.5, 2.8)
    assert strong_home > 0.5 > weak_home


def test_expert_weight_clamp():
    assert expert_weight(None) == 1.0
    assert expert_weight(0.25) == 1.25
    assert expert_weight(3.0) == 2.0    # 상한
    assert expert_weight(-1.5) == 0.2   # 하한


def test_consensus_scores_weighted():
    weights = {"sharp": 2.0, "square": 0.5}
    scores = consensus_scores(
        [("sharp", "h2h:A"), ("square", "h2h:B"), ("square", "h2h:B")], weights
    )
    assert scores["h2h:A"] == pytest.approx(2.0 / 3.0)
    assert scores["h2h:B"] == pytest.approx(1.0 / 3.0)
    assert consensus_scores([], weights) == {}


def test_parlay_search():
    legs = [
        {"game_id": 1, "pick": "h2h:A", "p": 0.6, "odds": 1.9, "ev": 0.14},
        {"game_id": 2, "pick": "h2h:B", "p": 0.55, "odds": 2.0, "ev": 0.10},
        {"game_id": 3, "pick": "h2h:C", "p": 0.5, "odds": 2.2, "ev": 0.10},
        {"game_id": 1, "pick": "totals:Over:8.5", "p": 0.55, "odds": 1.95, "ev": 0.07},
        {"game_id": 4, "pick": "h2h:D", "p": 0.5, "odds": 1.8, "ev": -0.10},  # 음수 EV 제외
    ]
    parlays = best_parlays(legs)
    assert len(parlays) == 3
    # EV 내림차순
    assert parlays[0]["ev"] >= parlays[1]["ev"] >= parlays[2]["ev"]
    for p in parlays:
        game_ids = [leg["game_id"] for leg in p["legs"]]
        assert len(game_ids) == len(set(game_ids))          # 동일 경기 중복 금지
        assert 2 <= len(game_ids) <= 4
        assert all(leg["pick"] != "h2h:D" for leg in p["legs"])  # 음수 EV 레그 배제
    # 최상위 조합 EV 수치 검증: 3폴더 1+2+3 → p=0.165, odds=8.36 → ev≈0.379
    top = parlays[0]
    assert top["ev"] == pytest.approx(0.6 * 0.55 * 0.5 * 1.9 * 2.0 * 2.2 - 1, rel=1e-9)


async def test_mock_judge_roundtrip():
    payload = {
        "date": "2026-08-22",
        "games": [
            {"game_id": 1, "home": "A", "away": "B", "p_model": 0.62, "p_market": 0.58,
             "stats": {"home_era": 3.1, "away_era": 4.2}},
            {"game_id": 2, "home": "C", "away": "D", "p_model": 0.48, "p_market": 0.52,
             "stats": {}},
        ],
        "expert_picks": [], "breaking_news": "",
    }
    verdict = await Judge(mock=True).judge(payload)
    assert {g["game_id"] for g in verdict["games"]} == {1, 2}
    for g in verdict["games"]:
        assert 0.0 <= g["p_claude"] <= 1.0
        assert isinstance(g["verdict"], str) and isinstance(g["excluded_picks"], list)
    assert verdict["games"][0]["p_claude"] == pytest.approx(0.60)
