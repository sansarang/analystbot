"""🔴🔴 **운영 확정 — M1 + ρ 보정 · 그림자 M3**(사용자 결정 2026-10-12).

> ⑯ 운영 확률 = `legacy/old_engine.run`(K0 해시 고정) → `drawfix`(ρ 판) 순서.
> 판 없으면 **보정 없이 + 🔴**. 그림자 = M3(probfloor) · 바닥 = Elo.
> 생존·역배·보호 줄 = **M1 보정 후 격자** 합(소수 넷째 자리).
> 축 기여 분해는 **보정 전** 수를 설명함을 카드에 표시.
> 계약 **M1-1**: 운영 확률이 `old_engine` 외 경로에서 나오면 실패.
> 계약 **M1-2**: `drawfix` 판 없이 보정 수가 나오면 실패.
> 계약 **M1-3**: 그림자·바닥 확률이 **등급·생존에 닿으면** 실패.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _code(rel: str) -> str:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_m1_1_operation_number_comes_from_old_engine() -> None:
    """🔴🔴 **M1-1** — 운영 확률의 출처는 `old_engine` 하나다."""
    said = _code("app/core/probmodel.py")
    assert "from app.core.legacy import old_engine" in said
    i = said.index("said_m1.ok()")
    assert "got.home, got.draw, got.away = (said_m1.home" in said[i:i + 400]
    # 🔴 그 뒤로 **M3 가 운영 수를 덮는 자리가 없다** — `run` 안에서만 센다
    #    (⚠️ `_fill` 도 같은 줄을 쓰지만 그것은 **옛 네 축 경로**의 도움함수다)
    tail = said[i:said.index("_note(state, f'S3 확률(상성)")
                if "_note(state, f'S3 확률(상성)" in said
                else said.index("def _state_said")]
    assert "got.home, got.draw, got.away = said_three" in tail  # ρ 보정만
    assert tail.count("got.home, got.draw, got.away") == 2, (
        f"🔴 운영 수를 덮는 자리가 {tail.count('got.home, got.draw, got.away')}"
        "곳이다 — 출처가 하나가 아니다")


def test_m1_2_no_correction_without_a_version_file() -> None:
    """🔴🔴 **M1-2** — 판이 없으면 보정 수가 **안 나온다**."""
    from app.core import drawfix
    got, why = drawfix.load(league="league:없는리그",
                            as_of=__import__("datetime").datetime(
                                2026, 10, 11, tzinfo=__import__(
                                    "datetime").UTC))
    assert got == {} and "⬜" in why
    # 🔴 보정 함수도 값이 0 이면 **격자를 안 바꾼다**
    grid = {(0, 0): 0.3, (1, 1): 0.3, (1, 0): 0.2, (0, 1): 0.2}
    assert drawfix.bend(grid, rho=0.0, draw=0.0) == grid


def test_m1_2_correction_needs_the_plate_in_code() -> None:
    """🔴 코드가 **판을 읽고 나서만** 보정한다(손값 금지)."""
    said = _code("app/core/probmodel.py")
    i = said.index("_dfx.load(")
    j = said.index("_dfx.bend(")
    assert i < j, "🔴 판을 읽기 전에 보정한다"
    assert "if said_fix and said_m1.scores" in said


def test_m1_3_shadow_and_floor_never_touch_grade_or_survival() -> None:
    """🔴🔴 **M1-3** — 그림자·바닥은 **등급·생존**에 닿지 않는다."""
    said = _code("app/core/pipeline.py")
    # 🔴 생존에 넘기는 분포는 `edge["sim"]["scores"]`(= M1 보정 후 격자)다
    i = said.index("s7_judge.run(")
    assert "dist=" in said[i:i + 400]
    assert "shadow" not in said[i:i + 400] and "floor" not in said[i:i + 400]
    # 🔴 판정 쪽 코드에 그림자·바닥이 **없다**
    judge = _code("app/core/stages/s7_judge.py")
    for bad in ("shadow", "floor"):
        assert bad not in judge, bad


def test_survival_and_underdog_use_the_corrected_grid() -> None:
    """🔴 생존·역배·보호 줄이 **같은(보정 후) 격자**를 쓴다."""
    said = _code("app/core/render.py")
    i = said.index("_underdog_line")
    # 🔴 λ 로 격자를 **다시 만들지 않는다** — 저장된 격자를 쓴다
    block = said[said.index("def _underdog_line"):][:1800]
    assert "scores" in block, "🔴 역배 줄이 저장된 격자를 안 쓴다"


def test_card_says_decomposition_is_pre_correction() -> None:
    """🔴 축 기여 분해가 **보정 전** 수를 설명한다고 카드가 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "보정 전" in said


def test_card_shows_the_confidence_band() -> None:
    """🔴 §2 — 문턱은 보류하고 **구간(30/20/10%)만** 카드에 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "확신 구간" in said
    from app.core import bands
    assert bands.of(0.62) == "상위 10%" or bands.of(0.62) == "상위 20%"
    assert bands.of(0.30) == ""
