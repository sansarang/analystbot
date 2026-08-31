"""[v1.1 5단계] 가치 게이트 — 추천의 2차 문.

실측 사례로 3분류가 정확히 갈리는지 잠근다:
  PHI    0.66 × 1.39 = 0.92  확률 통과인데 헛통과 → 가치주의
  BAL    0.63 × 1.70 = 1.07  경계 확률인데 헛탈락 → 추천
  닛폰햄  0.61 × 1.43 = 0.87  같은 유형 → 가치주의
"""

import pytest

from app.engine.value_gate import (
    CLS_BOARD_ONLY, CLS_EDGE, CLS_RECOMMENDED, CLS_VALUE_WARN, VALUE_MIN,
    classify, label, passes_value, required_odds, stars, value,
)


# ---------------------------------------------------------------- 실측 3형

def test_phi_type_high_prob_no_value():
    assert value(0.66, 1.39) == pytest.approx(0.92, abs=0.005)
    assert passes_value(0.66, 1.39) is False
    assert classify(probability_ok=True, vetoed=False,
                    p=0.66, odds=1.39) == CLS_VALUE_WARN


def test_bal_type_edge_prob_with_value():
    assert value(0.63, 1.70) == pytest.approx(1.07, abs=0.005)
    assert passes_value(0.63, 1.70) is True
    assert classify(probability_ok=True, vetoed=False,
                    p=0.63, odds=1.70) == CLS_RECOMMENDED


def test_nippon_ham_type():
    assert passes_value(0.61, 1.43) is False
    assert classify(probability_ok=True, vetoed=False,
                    p=0.61, odds=1.43) == CLS_VALUE_WARN


# ---------------------------------------------------------------- 폴백

def test_missing_odds_is_unknown_not_failure():
    """🔴 None을 False로 취급하면 배당 수집 실패가 추천을 막는다."""
    assert value(0.62, None) is None
    assert passes_value(0.62, None) is None
    assert classify(probability_ok=True, vetoed=False,
                    p=0.62, odds=None) == CLS_RECOMMENDED


def test_required_odds_for_uncollected_cards():
    assert required_odds(0.62) == pytest.approx(VALUE_MIN / 0.62, abs=0.01)
    assert required_odds(None) is None


# ---------------------------------------------------------------- 순서 규율

def test_veto_beats_probability_and_value():
    """확신도 '하'는 확률·가치가 아무리 좋아도 탈락이다 (기존 규율)."""
    assert classify(probability_ok=True, vetoed=True,
                    p=0.70, odds=2.00) == CLS_BOARD_ONLY


def test_probability_failure_is_board_only():
    assert classify(probability_ok=False, vetoed=False,
                    p=0.55, odds=2.50) == CLS_BOARD_ONLY


def test_edge_requires_confirmed_status():
    """엣지는 6단계 딥서치를 통과한 것만 — candidate 로는 승격하지 않는다."""
    assert classify(probability_ok=True, vetoed=False, p=0.68, odds=1.81,
                    edge_status="candidate") == CLS_RECOMMENDED
    assert classify(probability_ok=True, vetoed=False, p=0.68, odds=1.81,
                    edge_status="confirmed") == CLS_EDGE


def test_edge_does_not_replace_recommendation():
    """엣지는 추천을 대체하지 않고 그 위에 붙는 라벨이다."""
    assert "🎯엣지" in label(CLS_EDGE, divergence_pp=16.0)
    assert "+16.0%p" in label(CLS_EDGE, divergence_pp=16.0)
    assert label(CLS_RECOMMENDED) == "[✅추천]"
    assert label(CLS_VALUE_WARN) == "[⚠️가치주의]"
    assert label(CLS_BOARD_ONLY) == ""


# ---------------------------------------------------------------- 별표

def test_star_ladder():
    assert stars(0.68) == "★★★★★" and stars(0.67) == "★★★★"
    assert stars(0.63) == "★★★★" and stars(0.62) == "★★★"
    assert stars(0.58) == "★★★" and stars(0.57) == "★★"
    assert stars(0.53) == "★★" and stars(0.52) == "★"
    assert stars(None) == ""


def test_provisional_stars_are_marked():
    assert stars(0.64, provisional=True) == "★★★★ (잠정)"


# ---------------------------------------------------------------- 카드 배선

def test_card_shows_stars_and_value():
    from app.engine.form_card import render_form_card

    jg = {"home": "Doosan Bears", "away": "Kiwoom Heroes", "sport": "kbo",
          "league": "KBO", "lineup_status": "confirmed", "p_claude": 0.64,
          "matchup": {"p_home": 0.64, "우세": "home", "근거": ["a"], "변수": []}}
    card = render_form_card(jg, "kbo")
    assert "★★★★" in card
    assert "필요배당" in card, "배당 미수집이면 필요배당을 알려야 한다"


def test_card_shows_market_note_when_present():
    from app.engine.form_card import render_form_card

    jg = {"home": "A", "away": "B", "sport": "kbo", "league": "KBO",
          "lineup_status": "confirmed", "p_claude": 0.64,
          "market_note": "🎯 엣지후보 · 검증대기 (우리 64% vs 시장 52%, +12.0%p)",
          "matchup": {"p_home": 0.64, "우세": "home", "근거": [], "변수": []}}
    assert "엣지후보" in render_form_card(jg, "kbo")
