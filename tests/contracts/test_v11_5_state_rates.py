"""🔴🔴 **2번 경기 흐름 스크립트 = 상태별 득점률** — 수정 지시서 2026-10-12.

> [2c] 위치: ⑪ 분 단위 시뮬 루프 안. 매 분 현재 스코어로 각 팀 상태를 정하고
> λ분당 × 그 상태 배율. 기존 축3 시간대 배율과 **한 표로 합친다** — 같은 효과를
> 두 번 곱하면 계약 실패. 주변분포 보정: 상태 배율 적용 뒤에도 팀 기대 득점
> 평균이 λ에서 **±2% 안**(정규화).
> [2b] TeamRead에 `state_mult {lead:{for,against}, level:{…}, trail:{…}}`.
> [2a] 팀별 상태 배율을 facts에 싣는다(없으면 리그값·🔴).

🔴 S1 — 상태 배율과 축3 배율이 같은 효과를 **이중으로 곱하면 실패**.
🔴 S2 — 상태 배율 적용 후 팀 평균 득점이 λ ±2%.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 실측 꼴 — 팀별·상태별 `for`(득점률)·`against`(실점률) 배율
TABLE = {
    "home": {"lead": {"for": 0.80, "against": 1.10},
             "level": {"for": 1.00, "against": 1.00},
             "trail": {"for": 1.25, "against": 0.95}},
    "away": {"lead": {"for": 0.90, "against": 1.05},
             "level": {"for": 1.00, "against": 1.00},
             "trail": {"for": 1.15, "against": 1.00}},
}


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# S2 — 주변분포 보정 ±2%
# ══════════════════════════════════════════════════════════════════

def test_s2_expected_goals_stay_within_two_percent() -> None:
    from app.core import sim
    lam_h, lam_a = 1.60, 1.10
    out = sim.run(lam_h, lam_a, state_mult=TABLE)
    got = dict(out.xg)
    assert abs(got["home"] - lam_h) / lam_h <= 0.02, got
    assert abs(got["away"] - lam_a) / lam_a <= 0.02, got


def test_s2_also_holds_with_late_multipliers() -> None:
    """⚠️ 시간대 배율과 **함께** 걸어도 ±2% 안이다."""
    from app.core import sim
    lam_h, lam_a = 1.40, 1.30
    out = sim.run(lam_h, lam_a, late_home=0.15, late_away=-0.10,
                  state_mult=TABLE)
    got = dict(out.xg)
    assert abs(got["home"] - lam_h) / lam_h <= 0.02, got
    assert abs(got["away"] - lam_a) / lam_a <= 0.02, got


# ══════════════════════════════════════════════════════════════════
# 상태 배율이 **실제로** 분포를 바꾼다(장식이 아니다)
# ══════════════════════════════════════════════════════════════════

def test_state_table_changes_the_distribution() -> None:
    from app.core import sim
    flat = sim.run(1.5, 1.2)
    said = sim.run(1.5, 1.2, state_mult=TABLE)
    # 🔴 앞선 팀이 느려지고 뒤진 팀이 빨라지면 **무승부가 늘어난다**
    assert said.draw > flat.draw, (said.draw, flat.draw)


def test_per_team_tables_differ() -> None:
    """🔴 팀별 표다 — 한 쌍을 양 팀에 함께 쓰지 않는다."""
    from app.core import sim
    only_home = {"home": TABLE["home"],
                 "away": {k: {"for": 1.0, "against": 1.0}
                          for k in ("lead", "level", "trail")}}
    a = sim.run(1.4, 1.4, state_mult=only_home)
    b = sim.run(1.4, 1.4, state_mult=TABLE)
    assert abs(a.home - b.home) > 1e-6, (a.home, b.home)


# ══════════════════════════════════════════════════════════════════
# S1 — 한 표다(두 번 곱하지 않는다)
# ══════════════════════════════════════════════════════════════════

def test_s1_one_table_not_two() -> None:
    """🔴 실측 표가 오면 **T11 임시 배율(`lead_mul`)과 곱하지 않는다**."""
    from app.core import sim
    both = sim.run(1.5, 1.2, state_mult=TABLE,
                   lead_mul={"leading": 0.5, "trailing": 2.0})
    only = sim.run(1.5, 1.2, state_mult=TABLE)
    assert abs(both.draw - only.draw) < 1e-9, (both.draw, only.draw)


def test_s1_fallback_to_t11_when_no_table() -> None:
    """⚠️ 실측 표가 없으면 **T11 배율이 그대로 돈다**(퇴로를 끊지 않는다)."""
    from app.core import sim
    flat = sim.run(1.5, 1.2)
    said = sim.run(1.5, 1.2, lead_mul={"leading": 0.8, "trailing": 1.2})
    assert abs(said.draw - flat.draw) > 1e-6


def test_s1_code_says_why() -> None:
    said = _src("app/core/sim.py")
    assert "한 표" in said and "두 번" in said


# ══════════════════════════════════════════════════════════════════
# 2a·2b 배선
# ══════════════════════════════════════════════════════════════════

def test_2b_team_read_has_state_mult() -> None:
    from app.core.strategy import TeamRead
    got = TeamRead(team="team:000001")
    assert hasattr(got, "state_mult")
    assert dict(got.state_mult) == {}


def test_2a_facts_carry_state_rates() -> None:
    from app.core.schema import Facts
    assert "state_rates" in Facts.model_fields


def test_2c_wired_into_the_probability_call() -> None:
    """🔴 ⑪ 이 그 표를 시뮬에 넘긴다."""
    said = _src("app/core/probmodel.py")
    assert "state_mult" in said


def test_table_loader_falls_back_to_league() -> None:
    """🔴 표본 부족 팀 = **리그 배율 + 🔴**(지어내지 않는다)."""
    from app.core import staterates as sr
    got, why = sr.for_team(league="league:PD", team="team:999999",
                           table={"league": {"lead": {"for": 0.9,
                                                      "against": 1.1}}})
    assert dict(got.get("lead") or {}).get("for") == 0.9
    assert "🔴" in why


def test_missing_table_is_named_not_zero() -> None:
    from app.core import staterates as sr
    got, why = sr.for_team(league="league:XX", team="team:1", table={})
    assert got == {}
    assert "없다" in why or "🔴" in why


def test_no_invented_numbers() -> None:
    """🔴 #4 — 기본 배율을 **코드에 박아 두지 않는다**(1.0 말고는)."""
    tree = ast.parse(_src("app/core/staterates.py"))
    bad = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, float)
           and n.value not in (0.0, 1.0, 2.0)]
    assert not bad, bad
