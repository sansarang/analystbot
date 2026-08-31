"""[축구 시범 운영] 게이트·카드·격리.

가장 중요한 테스트는 **야구 경로 무영향**이다 — 시범 등급 코드가 검증된
파이프라인을 건드리면, 축구 실패가 야구 발송을 죽인다.
"""

import ast
from pathlib import Path

import pytest

from app.engine.soccer_trial import (
    CLIP_DRAW, CLIP_WIN, GATE_AWAY, GATE_DC, GATE_HOME,
    gate, lineup_state, normalize, render_card, stars,
)


# ---------------------------------------------------------------- 격리 (최우선)

def _imported_modules(path: Path) -> set[str]:
    """함수 안 지역 import 까지 포함해 실제 import 대상만 모은다.

    문자열 검색은 쓰지 않는다 — `settings.matchup_model` 같은 **설정 이름**이
    걸려 거짓 양성이 난다(실측: 첫 판이 그렇게 실패했다).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_soccer_trial_does_not_import_baseball_judgement_modules():
    """🔴 시범 코드가 야구 판정 모듈에 의존하지 않는다.

    의존하면 축구 실패가 야구 발송을 죽일 수 있고, 시범 등급 변경이
    검증된 파이프라인에 새어 든다.
    """
    mods = _imported_modules(Path("app/engine/soccer_trial.py"))
    banned = {"app.engine.team_form", "app.engine.matchup", "app.engine.markets",
              "app.engine.pregame_push", "app.engine.scoring"}
    leaked = mods & banned
    assert not leaked, f"축구 시범이 야구 판정 모듈을 import 한다: {sorted(leaked)}"


def test_soccer_trial_job_is_exception_isolated():
    """축구 판정이 실패해도 야구에 영향이 없어야 한다."""
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def soccer_trial_job"):]
    body = body[:body.index("\nasync def ")]
    assert "except Exception" in body
    assert "야구" in body, "격리 의도가 주석에 남아 있어야 한다"


def test_shares_gate_numbers_with_manual_protocol():
    """수동 프로토콜과 수치가 같아야 나중에 표본을 합칠 수 있다."""
    assert (GATE_HOME, GATE_AWAY, GATE_DC) == (0.55, 0.60, 0.75)
    assert CLIP_WIN == (0.20, 0.65) and CLIP_DRAW == (0.18, 0.33)


# ---------------------------------------------------------------- 클리핑·게이트

def test_normalize_clips_then_sums_to_one():
    """합은 **정확히** 1.0이어야 한다 — 더블찬스가 이 위에 얹히기 때문이다."""
    ph, pd, pa = normalize({"p_home": 0.95, "p_draw": 0.02, "p_away": 0.03})
    assert ph + pd + pa == 1.0
    # 클리핑 상한(0.65)에 무승부 하한(0.18)·패 하한(0.20)이 더해져 재정규화되므로
    # 홈 확률은 0.65/1.03 ≈ 0.631 을 넘을 수 없다. 압도적 전력차도 여기서 멈춘다.
    assert ph <= 0.632, f"클리핑이 뚫렸다: {ph}"
    assert pd >= 0.17


def test_draw_is_never_squeezed_out():
    """무승부를 0으로 만들지 않는다 — 축구 판정의 핵심 규율."""
    _, pd, _ = normalize({"p_home": 0.9, "p_draw": 0.0, "p_away": 0.1})
    assert pd > 0.15


def test_gate_thresholds():
    lines, passed = gate(0.56, 0.25, 0.19)
    assert ("홈 승", 0.56) in passed
    lines, passed = gate(0.30, 0.28, 0.42)
    assert not passed, "원정 42%는 60% 미달인데 통과했다"
    lines, passed = gate(0.50, 0.30, 0.20)
    assert any(n.startswith("1X") for n, _ in passed), "1X 80%가 통과해야 한다"


def test_stars_ladder():
    assert stars(0.61) == "★★★★★" and stars(0.56) == "★★★★"
    assert stars(0.51) == "★★★" and stars(0.46) == "★★" and stars(0.40) == "★"


# ---------------------------------------------------------------- 라인업 상태

def _md(kind, n=11):
    return {"content": {"lineup": {
        "lineupType": kind, "source": "enetpulse",
        "homeTeam": {"starters": [{}] * n, "unavailable": [], "formation": "4-3-3"},
        "awayTeam": {"starters": [{}] * n, "unavailable": [{"name": "X"}],
                     "formation": "4-4-2"}}}}


def test_predicted_lineup_is_not_confirmed():
    """예상 라인업을 확정으로 읽으면 잠정 카드가 확정판으로 나간다."""
    assert lineup_state(_md("predicted"))["confirmed"] is False
    assert lineup_state(_md("standard"))["confirmed"] is True
    assert lineup_state(_md(None))["confirmed"] is False
    assert lineup_state(_md("standard", n=9))["confirmed"] is False


# ---------------------------------------------------------------- 카드

def _game(lineup_type="predicted", ph=0.55, pd=0.25, pa=0.20):
    return {"league": "라리가", "home": "Barcelona", "away": "Rayo",
            "kickoff_kst": "09/01 04:30", "lineup_type": lineup_type,
            "p_home": ph, "p_draw": pd, "p_away": pa,
            "home_lineup": {"formation": "4-3-3", "결장": ["A", "B"]},
            "away_lineup": {"formation": "4-4-2", "결장": ["C"]},
            "verdict": {"lambda_home": 1.9, "lambda_away": 0.9, "확신도": "중",
                        "근거": ["근거1", "근거2", "근거3"], "변수": ["변수1"]}}


def test_card_marks_trial_grade():
    """카드에 시범 운영 라벨이 반드시 붙는다 — 신뢰 등급이 야구와 다르다."""
    card = render_card(_game())
    assert card.startswith("⚽️ 축구 · 시범 운영")


def test_provisional_card_is_not_a_recommendation():
    card = render_card(_game("predicted"))
    assert "🕐 잠정" in card
    assert "확정 픽 아님" in card
    assert "✅ 추천(시범)" not in card


def test_confirmed_card_can_recommend():
    card = render_card(_game("standard"))
    assert "✅ 확정판" in card
    assert "✅ 추천(시범)" in card


def test_card_shows_required_odds_not_value_verdict():
    """배당 미수집 단계에서는 필요배당까지만 — 가치 판정을 지어내지 않는다."""
    card = render_card(_game("standard"))
    assert "필요배당" in card
    assert "배당 미수집" in card
