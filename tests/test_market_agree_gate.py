"""추천은 시장과 같은 방향일 때만 — v1.4 임시 방어 (2026-09-07 사용자 지시).

근거: 2026-09-06 620행 분석.
  · 추천 게이트 통과분 적중 30.8%(n=13) < 보드만 59.7%(n=77)
  · 우세팀이 갈린 8경기 — 시장 7승, 우리 3승
  · 괴리 4%p 이상 12경기 — 시장 9승, 우리 5승
시장을 거스르는 확신이 데이터상 **안티 신호**였다.

⚠️ 한시 조치다. `MARKET_AGREE_REQUIRED=false` 로 끄면 종전 동작으로 돌아간다.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.pipeline import (
    MARKET_DISAGREE,
    MARKET_MISSING,
    market_disagreement,
    qualifies,
)


def _s(**over):
    base = dict(_env_file=None, market_agree_required=True,
                market_divergence_pp=4.0, min_win_prob=0.58,
                away_prob_penalty=0.05, npb_last3_verified=True)
    base.update(over)
    return Settings(**base)


def _pick(**over):
    p = {"sport": "kbo", "p": 0.62, "p_home": 0.62, "p_market_send": 0.60,
         "pick_state": "final", "lineup_status": "confirmed",
         "form_unavailable": False, "starter_low_sample": []}
    p.update(over)
    return p


def test_production_default_is_on():
    """🔴 `conftest` 가 테스트에서 이 스위치를 끈다 — 그것이 제품 기본값을
    바꾸지 않았음을 여기서 잠근다. 끄는 것은 픽스처 편의이지 정책이 아니다.
    """
    import pathlib

    src = pathlib.Path("app/config.py").read_text(encoding="utf-8")
    assert "market_agree_required: bool = True" in src


# ── 사유 판정 ───────────────────────────────────────────────────
def test_agreement_passes():
    assert market_disagreement(_pick(p_home=0.62, p_market_send=0.60), _s()) is None


def test_missing_market_is_a_reason():
    assert market_disagreement(_pick(p_market_send=None), _s()) == MARKET_MISSING
    assert market_disagreement(_pick(p_home=None), _s()) == MARKET_MISSING


def test_disagreement_at_or_above_threshold():
    """4.0%p 는 **포함**이다 — 카드의 '시장 이견' 판정과 같은 경계여야 한다."""
    assert market_disagreement(_pick(p_home=0.64, p_market_send=0.60),
                               _s()) == MARKET_DISAGREE
    assert market_disagreement(_pick(p_home=0.6399, p_market_send=0.60),
                               _s()) is None


def test_direction_does_not_matter():
    """우리가 높든 낮든 갈린 것은 갈린 것이다."""
    for ours in (0.66, 0.54):
        assert market_disagreement(_pick(p_home=ours, p_market_send=0.60),
                                   _s()) == MARKET_DISAGREE


# ── 임계값이 한 곳에서 온다 (사본 금지) ─────────────────────────
def test_threshold_comes_from_one_setting():
    s2 = _s(market_divergence_pp=10.0)
    assert market_disagreement(_pick(p_home=0.66, p_market_send=0.60), s2) is None
    src = (__import__("pathlib").Path("app/pipeline.py")
           .read_text(encoding="utf-8"))
    seg = src[src.index("def market_disagreement"):]
    seg = seg[:seg.index("\ndef ", 1)]
    assert "market_divergence_pp" in seg
    assert "4.0" not in seg and "0.04" not in seg, "임계값을 손으로 적었다"


# ── 게이트 결합 ─────────────────────────────────────────────────
def test_gate_rejects_when_market_disagrees():
    assert qualifies(_pick(p=0.66, p_home=0.66, p_market_send=0.50), _s()) is False


def test_gate_rejects_when_market_missing():
    assert qualifies(_pick(p_market_send=None), _s()) is False


def test_gate_accepts_when_market_agrees():
    assert qualifies(_pick(p=0.62, p_home=0.62, p_market_send=0.60), _s()) is True


def test_switch_off_restores_previous_behaviour():
    off = _s(market_agree_required=False)
    assert market_disagreement(_pick(p_market_send=None), off) is None
    assert qualifies(_pick(p=0.66, p_home=0.66, p_market_send=0.50), off) is True
    assert qualifies(_pick(p=0.62, p_market_send=None), off) is True


# ── 카드와 게이트가 같은 말을 한다 ──────────────────────────────
def test_card_and_gate_use_the_same_function():
    """게이트가 둘로 갈리면 카드와 요약이 다른 말을 한다(2026-09-05 실사고)."""
    src = (__import__("pathlib").Path("app/engine/form_card.py")
           .read_text(encoding="utf-8"))
    assert "from app.pipeline import market_disagreement" in src
    assert "market_divergence_pp" not in src, "카드가 임계값을 따로 적었다"


@pytest.mark.parametrize("mkt,expect", [
    (0.50, "시장 이견"),
    (None, "시장 미수집"),
])
def test_card_states_the_reason(mkt, expect):
    """정보는 보이되 추천 딱지만 뗀다 — 왜 보드만인지 카드에 적힌다."""
    from app.engine.form_card import _market_why

    why = _market_why({"p_claude": 0.66, "p_market_send": mkt}, _s())
    assert why and expect in why


def test_no_reason_when_agreeing():
    from app.engine.form_card import _market_why

    assert _market_why({"p_claude": 0.62, "p_market_send": 0.60}, _s()) is None
