"""[§6] λ 계수 학습 — 임의값을 데이터로 교체한다.

핵심 계약 두 가지:
1. **미래 정보 누수 금지** — 경기 이전 데이터만 피처로 쓴다.
2. **개선되지 않으면 채택하지 않는다** — Brier가 나빠지면 기존 계수를 유지한다.
"""

import json

import pytest

from app.config import Settings
from app.models.calibrate import (
    MIN_GAMES,
    MIN_PRIOR_PA,
    Coefficients,
    build_training_set,
    evaluate,
    fit,
    load_learned,
    predict,
    save,
)

pd = pytest.importorskip("pandas")
S = Settings(_env_file=None)


def _rec(hx=0.330, ax=0.300, hsp=0.330, asp=0.290, win=1):
    return {"home": "H", "away": "A", "home_win": win,
            "home_xwoba": hx, "away_xwoba": ax,
            "home_starter_xwoba": hsp, "away_starter_xwoba": asp}


# ---------------------------------------------------------------- 예측

def test_predict_respects_probability_cap():
    """[§0] 학습 경로도 상한을 지킨다 — 극단 피처가 68%를 넘지 못한다."""
    p = predict(_rec(hx=0.500, ax=0.200, hsp=0.500, asp=0.150), Coefficients.from_settings(S), S)
    assert p <= S.max_win_prob_mlb
    low = predict(_rec(hx=0.200, ax=0.500, hsp=0.150, asp=0.500), Coefficients.from_settings(S), S)
    assert low >= S.min_win_prob_mlb


def test_better_offense_raises_home_probability():
    coef = Coefficients.from_settings(S)
    strong = predict(_rec(hx=0.350), coef, S)
    weak = predict(_rec(hx=0.290), coef, S)
    assert strong > weak


def test_missing_starter_metric_is_tolerated():
    """선발 지표가 없으면 그 보정만 건너뛴다 (예외 없이)."""
    coef = Coefficients.from_settings(S)
    p = predict({**_rec(), "away_starter_xwoba": None, "home_starter_xwoba": None}, coef, S)
    assert 0.3 <= p <= 0.7


# ---------------------------------------------------------------- 평가

def test_evaluate_returns_brier_and_calibration():
    records = [_rec(win=1) for _ in range(6)] + [_rec(win=0) for _ in range(4)]
    out = evaluate(records, Coefficients.from_settings(S), S)
    assert out["n"] == 10
    assert 0 < out["brier"] < 1
    assert 0 <= out["accuracy"] <= 1
    assert isinstance(out["calibration"], list)


# ---------------------------------------------------------------- 학습

def test_fit_refuses_small_sample():
    """[§6] 표본이 얇으면 학습하지 않는다 — 과적합 방지."""
    out = fit([_rec() for _ in range(MIN_GAMES - 1)], S)
    assert out["ok"] is False and "최소" in out["reason"]


def test_fit_improves_brier_on_separable_data():
    """[§6] 신호가 있는 데이터에서는 Brier가 개선돼야 한다."""
    records = ([_rec(hx=0.360, ax=0.280, asp=0.360, hsp=0.280, win=1)] * 150
               + [_rec(hx=0.280, ax=0.360, asp=0.280, hsp=0.360, win=0)] * 150)
    out = fit(records, S)
    assert out["ok"] is True
    assert out["after"]["brier"] <= out["before"]["brier"]
    assert set(out["coefficients_after"]) == {
        "exp_offense", "exp_pitcher", "home_run_edge", "league_runs_per_game"}


def test_save_rejects_unimproved_result(tmp_path):
    """[§6] 개선되지 않으면 계수를 채택하지 않는다."""
    path = tmp_path / "coef.json"
    save({"ok": True, "improved": False, "before": {"brier": 0.25},
          "after": {"brier": 0.26}}, path)
    assert not path.exists()

    save({"ok": True, "improved": True, "before": {"brier": 0.25},
          "after": {"brier": 0.23},
          "coefficients_after": {"exp_offense": 1.5}}, path)
    assert path.exists()
    assert load_learned(path) == {"exp_offense": 1.5}


def test_load_learned_missing_file_is_none(tmp_path):
    assert load_learned(tmp_path / "nope.json") is None


# ---------------------------------------------------------------- 누수 방지

def _pitches(rows):
    return pd.DataFrame(rows)


def _pitch(game_pk, date, home, away, topbot, xwoba, pitcher, score_h, score_a):
    return {"game_pk": game_pk, "game_date": date, "game_type": "R",
            "home_team": home, "away_team": away, "inning_topbot": topbot,
            "estimated_woba_using_speedangle": xwoba, "pitcher": pitcher,
            "post_home_score": score_h, "post_away_score": score_a,
            "inning": 1, "at_bat_number": 1}


def test_training_set_excludes_same_day_data():
    """[§6] 경기 당일 타석을 피처에 넣으면 결과를 미리 아는 셈이다 — 반드시 제외."""
    rows = []
    # 8/01~8/10: 홈팀 .400 / 원정팀 .300으로 사전 표본을 쌓는다
    for day in range(1, 11):
        rows += [_pitch(100 + day, f"2026-08-{day:02d}", "H", "A", "Bot", 0.400, 1, 5, 2)] * 20
        rows += [_pitch(100 + day, f"2026-08-{day:02d}", "H", "A", "Top", 0.300, 2, 5, 2)] * 20
    # 8/20 대상 경기 — 이날 타석은 xwOBA .900(비현실적)이지만 피처에 들어가면 안 된다
    rows += [_pitch(999, "2026-08-20", "H", "A", "Bot", 0.900, 3, 9, 1)] * 20
    rows += [_pitch(999, "2026-08-20", "H", "A", "Top", 0.900, 4, 9, 1)] * 20
    recs = build_training_set(_pitches(rows))
    target = [r for r in recs if r["game_pk"] == 999]
    assert target, "대상 경기가 학습셋에 있어야 한다"
    assert target[0]["home_xwoba"] == pytest.approx(0.400, abs=0.001)  # 당일 0.900이 아니다
    assert target[0]["away_xwoba"] == pytest.approx(0.300, abs=0.001)


def test_training_set_requires_minimum_sample():
    """[§6] 사전 표본이 얇은 경기는 학습에서 제외한다."""
    rows = [_pitch(1, "2026-08-01", "H", "A", "Bot", 0.350, 1, 3, 1)] * 10
    rows += [_pitch(2, "2026-08-05", "H", "A", "Bot", 0.350, 1, 3, 1)] * 10
    recs = build_training_set(_pitches(rows))
    assert recs == []          # 표본 MIN_PRIOR_PA 미만


def test_training_set_drops_ties():
    """무승부(서스펜디드)는 승패 라벨이 없어 제외한다."""
    rows = []
    for day in range(1, 11):
        rows += [_pitch(100 + day, f"2026-08-{day:02d}", "H", "A", "Bot", 0.320, 1, 3, 1)] * 20
        rows += [_pitch(100 + day, f"2026-08-{day:02d}", "H", "A", "Top", 0.320, 2, 3, 1)] * 20
    rows += [_pitch(999, "2026-08-20", "H", "A", "Bot", 0.320, 3, 4, 4)] * 20
    rows += [_pitch(999, "2026-08-20", "H", "A", "Top", 0.320, 4, 4, 4)] * 20
    recs = build_training_set(_pitches(rows))
    assert all(r["game_pk"] != 999 for r in recs)
