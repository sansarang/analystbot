"""[v1.1 4단계] 시장 괴리 3분류 + 엣지 후보.

가장 중요한 테스트는 **배당의 판정 유입 금지**다 — 섞이면 "우리 판정"이
사실은 시장을 베낀 것이 되고, 그 순간 괴리 측정 자체가 무의미해진다.
"""

import ast
from pathlib import Path

import pytest

from app.engine.market_edge import (
    CLS_EDGE, CLS_MARKET_AHEAD, CLS_NEUTRAL, DIVERGENCE_PP,
    EDGE_CANDIDATE, EDGE_NONE, apply, classify, demote_confidence,
    implied_probs,
)


# ---------------------------------------------------------------- 격리 (최우선)

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
    return mods


@pytest.mark.parametrize("mod", [
    "app/engine/team_form.py", "app/engine/matchup.py", "app/engine/prompts.py",
    "app/engine/narrator.py",
])
def test_judgement_modules_never_import_market_edge(mod):
    """🔴 판정·폼·서술이 배당 모듈을 import 하면 안 된다."""
    assert "app.engine.market_edge" not in _imports(Path(mod)), \
        f"{mod}가 배당 후처리를 import 한다 — 판정에 배당이 흘러든다"


def test_prompts_carry_no_odds_fields():
    """프롬프트 문구에 배당이 등장하지 않는다."""
    from app.engine.prompts import MATCHUP, TEAM_FORM

    for p in (MATCHUP, TEAM_FORM):
        assert "배당" not in p or "배당, 팀 명성" in p or "배당을" in p
    # 매치업은 "배당을 쓰지 않는다"는 금지 문구만 있어야 한다
    assert "배당, 팀 명성, 시즌 승률, 사전 지식은 쓰지 않는다" in MATCHUP


def test_market_edge_does_not_import_judgement_modules():
    """반대 방향 — 후처리가 판정 모듈을 끌어오면 순환·결합이 생긴다."""
    mods = _imports(Path("app/engine/market_edge.py"))
    assert not (mods & {"app.engine.team_form", "app.engine.matchup",
                        "app.engine.prompts"})


# ---------------------------------------------------------------- 마진 제거

def test_implied_probs_removes_bookmaker_margin():
    """1/배당 그대로 쓰면 합이 1을 넘어 시장을 5~8%p 과대평가한다."""
    imp = implied_probs({"home": 1.81, "away": 2.05})
    assert abs(sum(imp.values()) - 1.0) < 1e-6
    assert imp["home"] > imp["away"]


def test_implied_probs_handles_three_way():
    imp = implied_probs({"home": 2.10, "draw": 3.40, "away": 3.60})
    assert abs(sum(imp.values()) - 1.0) < 1e-6
    assert set(imp) == {"home", "draw", "away"}


def test_implied_probs_rejects_garbage():
    assert implied_probs({}) is None
    assert implied_probs({"home": 0.5, "away": 2.0}) is None   # 배당 ≤1 은 불가
    assert implied_probs({"home": "x", "away": "y"}) is None


# ---------------------------------------------------------------- 3분류

def test_no_odds_means_no_classification():
    """배당 미수집이면 아무것도 하지 않는다 — 확률 게이트만으로 간다."""
    r = classify(0.66, "home", None)
    assert r["classification"] is None
    assert r["edge_status"] == EDGE_NONE
    assert r["market_prob"] is None and r["divergence_pp"] is None


def test_nc_type_is_an_edge_candidate():
    """NC형: 판정 68% vs 시장 52% → 엣지 후보. 실측 적중 사례."""
    r = classify(0.68, "home", {"home": 1.81, "away": 2.05})
    assert r["classification"] == CLS_EDGE
    assert r["edge_status"] == EDGE_CANDIDATE
    assert r["divergence_pp"] >= DIVERGENCE_PP
    assert "검증대기" in r["note"], "6단계 전에 승격하면 SF형에 걸린다"


def test_phi_type_is_neutral():
    """PHI형: 66% vs 65% → 맞아도 남는 게 없는 '다 아는 픽'."""
    r = classify(0.66, "home", {"home": 1.50, "away": 2.60})
    assert r["classification"] == CLS_NEUTRAL
    assert r["edge_status"] == EDGE_NONE
    assert r["note"] is None


def test_sf_type_flags_market_ahead():
    """SF형: 우리 55%인데 시장은 반대 방향 → 시장이 옳았다, 패스가 정답."""
    r = classify(0.55, "home", {"home": 3.20, "away": 1.35})
    assert r["classification"] == CLS_MARKET_AHEAD
    assert "시장이 더 확신" in r["note"] and "방향 반대" in r["note"]


def test_market_ahead_by_margin_without_direction_flip():
    r = classify(0.52, "home", {"home": 1.35, "away": 3.20})
    assert r["classification"] == CLS_MARKET_AHEAD


# ---------------------------------------------------------------- 적용

def test_apply_demotes_confidence_but_never_touches_probability():
    """확률은 건드리지 않는다 — 이 단계는 분류·표기다."""
    jg = {"p_claude": 0.55, "judge_confidence": "high",
          "matchup": {"우세": "home"}, "game_id": 1}
    apply(jg, {"home": 3.20, "away": 1.35})
    assert jg["p_claude"] == 0.55, "판정 확률이 배당에 좌우됐다"
    assert jg["judge_confidence"] == "medium", "확신도 1단계 강등이 안 됐다"
    assert jg["market_divergence"] is True


def test_apply_is_noop_without_odds():
    jg = {"p_claude": 0.62, "judge_confidence": "high",
          "matchup": {"우세": "home"}}
    apply(jg, None)
    assert jg["judge_confidence"] == "high"
    assert jg["edge_status"] == EDGE_NONE
    assert jg.get("market_divergence") is None


def test_away_pick_uses_away_probability():
    """원정 픽은 1-p_home 으로 비교해야 한다 — 안 하면 부호가 뒤집힌다."""
    jg = {"p_claude": 0.30, "judge_confidence": "high",
          "matchup": {"우세": "away"}}
    apply(jg, {"home": 3.60, "away": 1.30})
    # 우리 원정 70% vs 시장 원정 ~72% → 중립
    assert jg["edge_status"] == EDGE_NONE
    assert abs(jg["divergence_pp"]) < DIVERGENCE_PP


def test_demote_stops_at_low():
    assert demote_confidence("high") == "medium"
    assert demote_confidence("medium") == "low"
    assert demote_confidence("low") == "low"
