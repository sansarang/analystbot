"""🔴🔴 **§10 이변 경고** · §14 판정 행동 — 지시서 2026-10-12(둘째) §10·§14.

> 대상: §9 **미채택** 신호 + 확률로 넣을 수 없는 신호
>   F6 약한 강팀(강팀 승 < 50%) · F8 정보 공백(InfoQ ≤ 2) · F9 고분산(λ합 상위
>   q 분위) · §9 미채택 항
> 등급: 🟡 S ≥ 상위 30% 분위 · 🔴 S ≥ 상위 10% 분위.
> 🔴 의 실제 강팀 승률이 예측보다 **구간상 낮을 때만** 운영 🔴 켬.
> 계약 **U3**: 경고가 확률·λ·생존에 닿으면 실패. **U5**: 검증표 미통과 등급이
> 운영 경고로 켜지면 실패. **S2**: 같은 신호가 λ 식과 경고 점수에 **동시에**
> 들어가면 실패. **U4**: 🔴 인데 강팀 승·핸디 줄에 등급이 붙으면 실패.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _strip(rel: str) -> str:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


MODEL = {"coef": {"weak_fav": 0.8, "thin_info": 0.5},
         "q30": 0.4, "q10": 0.9,
         "checked": {"red": True, "yellow": True}}


def test_signals_are_named() -> None:
    from app.core import upset as up
    assert set(up.SIGNALS) >= {"weak_fav", "thin_info", "high_var"}


def test_score_uses_only_adopted_coefficients() -> None:
    """🔴 S = Σ **채택 계수** × 신호값 — 계수 없는 신호는 **안 센다**."""
    from app.core import upset as up
    got = up.score_of({"weak_fav": 1.0, "thin_info": 1.0, "high_var": 1.0},
                      model=MODEL)
    assert abs(got.score - (0.8 + 0.5)) < 1e-9, got
    assert "high_var" in got.skipped


def test_grade_by_quantiles() -> None:
    from app.core import upset as up
    assert up.score_of({"weak_fav": 1.0}, model=MODEL).grade == "🟡"
    assert up.score_of({"weak_fav": 1.0, "thin_info": 1.0},
                       model=MODEL).grade == "🔴"
    assert up.score_of({}, model=MODEL).grade == ""


def test_u5_unchecked_grade_never_goes_live() -> None:
    """🔴🔴 **U5** — 검증표를 통과하지 않은 등급은 **운영에서 안 켜진다**."""
    from app.core import upset as up
    said = dict(MODEL, checked={"red": False, "yellow": True})
    got = up.score_of({"weak_fav": 1.0, "thin_info": 1.0}, model=said)
    assert got.grade == "🟡", got          # 🔴 → 참고(🟡)로 내려간다
    assert "검증 안 됨" in got.why


def test_s2_no_signal_in_both_places() -> None:
    """🔴🔴 **S2** — λ 식에 **채택된 항**은 경고 점수에서 **빠진다**."""
    from app.core import upset as up
    got = up.score_of({"weak_fav": 1.0, "rest_d": 2.0},
                      model=dict(MODEL, coef={**MODEL["coef"], "rest_d": 0.3}),
                      adopted={"rest_d"})
    assert "rest_d" in got.skipped and abs(got.score - 0.8) < 1e-9, got
    assert "확률이 이미" in got.why


def test_u3_warning_never_touches_probability() -> None:
    """🔴🔴 **U3** — 확률 경로가 `upset` 을 **안 부른다**."""
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/sim.py", "app/core/matchup.py"):
        said = _strip(rel)
        assert "upset" not in said, rel


def test_u4_red_folds_the_favourite_lines() -> None:
    """🔴🔴 **U4** — 🔴 면 **강팀 승·강팀 핸디 줄**에 등급이 안 붙는다."""
    from app.core import upset as up
    # ⚠️ 강팀이 **원정**(울산)이므로 강팀 줄은 `win away` 다 — 처음 쓴 계약이
    #    `win home` 을 강팀 줄로 적었다(내 실수였다 · 보장은 그대로다).
    for name in ("win away", "handicap Ulsan HD FC -1.5"):
        assert up.folds(name, grade="🔴", fav_name="Ulsan HD FC",
                        fav_side="away", home="Gwangju FC",
                        away="Ulsan HD FC"), name
    # 🔴 약팀 보호 줄은 **판정 대상으로 남는다**
    for name in ("win home", "handicap Gwangju FC 1.5", "unbeaten home",
                 "draw"):
        assert not up.folds(name, grade="🔴", fav_name="Ulsan HD FC",
                            fav_side="away", home="Gwangju FC",
                            away="Ulsan HD FC"), name


def test_yellow_only_drops_one_step() -> None:
    from app.core import upset as up
    assert up.step_of("🟡") == 1 and up.step_of("🔴") == 0
    assert up.step_of("") == 0
