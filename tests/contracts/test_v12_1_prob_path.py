"""🔴🔴 **확률 경로 재구성** — 사용자 지시 2026-10-12(적중률 1번).

> 1. 확률 경로 재구성: ③ **Elo → 바닥 λ/승무패**. ⑪ **축0·축1만**(Elo 대비 잔차).
> **축2·축3·⑩ 전략 판정은 확률 경로 밖**(표시·검증). **C1 개정**, 계약·흐름도 갱신.

🔴 왜 — 444경기 백필(2026-10-12): 축2 개선 **−0.0038** · 축3 **−0.0039**(음수 =
   손실을 만든다). 축0 +0.0007 · 축1 +0.0001 만 남는다. 그리고 봇은 `Elo만` 을
   **이기지 못했다**(−0.0052 · 95% −0.0119~+0.0015 → 0 을 품는다).
🔴 **C1 개정**: 옛 C1 은 *"S3 입력에 Elo 가 없다"* 였다. 이제 **Elo 가 바닥**이고
   상성(축0·축1)은 **그 위의 잔차**다. ⚠️ 동기·일정·감독 발언·맞대결·시장·LLM 은
   그대로 **금지**다(그 금지는 안 걷힌다).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 바닥 = Elo
# ══════════════════════════════════════════════════════════════════

def test_floor_comes_from_elo() -> None:
    """🔴 ③ — Elo 가 **바닥 승무패**를 만든다(입구는 `base.triple_of` 하나)."""
    from app.core import probfloor as pf
    got, why = pf.floor_of(kind="league:J1", dr=120.0)
    assert got is not None and abs(sum(got) - 1.0) < 1e-6, (got, why)
    assert got[0] > got[2], got          # 🔴 등급이 높으면 홈이 유리하다
    assert "Elo" in why


def test_floor_is_none_without_elo() -> None:
    """⚠️ Elo 가 없으면 바닥이 **없다**(지어내지 않는다)."""
    from app.core import probfloor as pf
    got, why = pf.floor_of(kind="league:J1", dr=None)
    assert got is None and ("없다" in why or "🔴" in why)


def test_residual_uses_axis0_and_axis1_only() -> None:
    """🔴 ⑪ — 잔차는 **축0·축1만**이다(축2·축3 은 안 본다)."""
    from app.core import probfloor as pf
    assert tuple(pf.RESIDUAL_AXES) == ("axis0", "axis1")


def test_residual_moves_the_floor() -> None:
    from app.core import probfloor as pf
    flat, _w = pf.floor_of(kind="league:J1", dr=0.0)
    got, why = pf.blend(flat, gaps={"axis0": 1.0, "axis1": 1.0},
                        weights={"axis0": 0.3, "axis1": 0.3}, beta=0.25)
    assert got[0] > flat[0], (flat, got, why)


def test_axis2_axis3_cannot_move_the_probability() -> None:
    """🔴 축2·축3 을 넣어도 **확률이 안 바뀐다**(경로 밖이다)."""
    from app.core import probfloor as pf
    flat, _w = pf.floor_of(kind="league:J1", dr=50.0)
    a, _w1 = pf.blend(flat, gaps={"axis0": 0.5}, weights={"axis0": 0.3},
                      beta=0.25)
    b, _w2 = pf.blend(flat, gaps={"axis0": 0.5, "axis2": 2.0, "axis3": -2.0},
                      weights={"axis0": 0.3, "axis2": 0.2, "axis3": 0.2},
                      beta=0.25)
    assert a == b, (a, b)


def test_strategy_is_out_of_the_probability_path() -> None:
    """🔴 ⑩ 전략 판정이 확률 경로에 **없다**(표시·검증으로만)."""
    # ⚠️ D46 — **독스트링을 뺀 코드만** 본다(문서가 금지어를 설명하는 것과
    #    코드가 그것을 부르는 것은 다르다)
    tree = ast.parse(_src("app/core/probfloor.py"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    said = ast.unparse(tree)
    for bad in ("strategy", "plan", "전략"):
        assert bad not in said, bad


def test_c1_amended_in_the_docs() -> None:
    """🔴 C1 개정이 **문서에 적혀 있다**(Elo 는 바닥 · 나머지 금지는 유지)."""
    said = _src("docs/코드흐름도.md")
    assert "C1 개정" in said
    assert "Elo" in said and "바닥" in said


def test_survival_source_is_only_the_distribution() -> None:
    """🔴🔴 **보드 생존의 출처는 시뮬 분포 하나다**(사용자 지시 2026-10-12).

    > 퇴로는 끊는다 … 생존·등급 **"보류 — 확률 없음(사유)"**.
    🔴 시나리오 무게(`hit / mass`)가 생존·등급에 닿으면 **실패**다.
    """
    said = inspect.getsource(
        __import__("app.core.stages.s7_judge", fromlist=["x"])._one)
    assert "survive.from_dist" in said
    # 🔴 시나리오 무게로 생존을 세는 자리가 **없어야** 한다
    assert "hit / mass" not in said.replace(" ", "")
    assert "hit/mass" not in said.replace(" ", "")
    # 🔴 분포가 없으면 **보류**다
    i = said.index("if not dist:")
    assert '"보류"' in said[i:i + 500]
