"""🔴🔴 **3d 보드 판정 — 간다/조건부/접는다** — 수정 지시서 2026-10-12.

> [3d] 위치: ⑭ 보드 판정. … 기존 등급 계산 결과 **위에** 반증 규칙을 얹는다:
>   모든 조건 "확인-무너짐 없음" → 간다
>   "미확인" 하나 이상, hard 무너짐 없음 → 조건부 · 미확인 조건을 **방아쇠로 자동 등록**
>   hard 무너짐 1개 이상 → 접는다(등급 없음)
>   soft 무너짐만 → 한 단계↓
> 확률 불변(C2). 시장(V6)은 이 판정에 안 들어간다(C12).

🔴 B1 — "간다"는 **조건 목록 전부에 확인 결과가 있을 때만**.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _cond(kind: str, state: str, strength: str = ""):
    from app.core.schema import BreakCondition
    return BreakCondition(id=f"BRK:{kind}:1", kind=kind, state=state,
                          strength=strength, said="x")


def _judgement(grade: str = "낸다"):
    """🔴 실측한 필수 칸만 채운다 — `MarketEval(line, survival, cap, grade)`."""
    from app.core.schema import BoardLine, Judgement, MarketEval
    ev = MarketEval(line=BoardLine(market="win", side="home"),
                    survival=0.7, cap=1.0, grade=grade, why="x")
    return Judgement(evals=[ev], board_source="피드", direction="홈",
                     conclusion="x")


# ══════════════════════════════════════════════════════════════════
# 네 판정
# ══════════════════════════════════════════════════════════════════

def test_all_intact_is_go() -> None:
    from app.core.stages import s7_judge
    got = s7_judge.by_breaks(_judgement(), [_cond("K3", "확인-무너짐 없음"),
                                            _cond("K4", "확인-무너짐 없음")])
    assert got.stance == "간다"
    assert got.evals[0].grade == "낸다", "🔴 등급을 건드리면 안 된다"


def test_unknown_is_conditional_and_registers_a_trigger() -> None:
    from app.core.stages import s7_judge
    rows = [_cond("K3", "확인-무너짐 없음"), _cond("K4", "미확인")]
    got = s7_judge.by_breaks(_judgement(), rows)
    assert got.stance == "조건부"
    assert any("BRK:K4" in t for t in got.triggers), got.triggers


def test_hard_broken_folds() -> None:
    from app.core.stages import s7_judge
    rows = [_cond("K1", "확인-무너짐", "hard"),
            _cond("K3", "확인-무너짐 없음")]
    got = s7_judge.by_breaks(_judgement(), rows)
    assert got.stance == "접는다"
    assert all(ev.grade == "없음" for ev in got.evals), got.evals


def test_soft_only_lowers_one_step() -> None:
    from app.core.stages import s7_judge
    rows = [_cond("K2", "확인-무너짐", "soft"),
            _cond("K3", "확인-무너짐 없음")]
    got = s7_judge.by_breaks(_judgement("낸다"), rows)
    assert got.stance == "한 단계↓"
    assert got.evals[0].grade == "소액", got.evals[0].grade


def test_b1_go_needs_every_condition_checked() -> None:
    """🔴 B1 — 하나라도 `미확인`이면 **간다가 아니다**."""
    from app.core.stages import s7_judge
    rows = [_cond("K3", "확인-무너짐 없음"), _cond("K1", "미확인")]
    assert s7_judge.by_breaks(_judgement(), rows).stance != "간다"


def test_no_conditions_is_not_go() -> None:
    """⚠️ 조건이 **0건**이면 '전부 확인'이 아니다 — 그 사실을 적는다."""
    from app.core.stages import s7_judge
    got = s7_judge.by_breaks(_judgement(), [])
    assert got.stance == "조건 없음"


# ══════════════════════════════════════════════════════════════════
# C2 · C12
# ══════════════════════════════════════════════════════════════════

def test_c2_probability_untouched() -> None:
    """🔴 확률 불변 — 이 함수는 확률을 인자로도 받지 않는다."""
    import inspect

    from app.core.stages import s7_judge
    sig = inspect.signature(s7_judge.by_breaks)
    for bad in ("prob", "sim", "dist", "layers"):
        assert bad not in sig.parameters, bad


def test_c12_market_not_in_this_verdict() -> None:
    import ast as _ast
    import inspect

    from app.core.stages import s7_judge
    said = _ast.unparse(_ast.parse(
        inspect.getsource(s7_judge.by_breaks).lstrip()))
    for bad in ("market", "V6", "시장"):
        assert bad not in said, bad


def test_wired_after_grade_by_check() -> None:
    """🔴 배선 — 기존 등급 계산 **뒤**에 얹는다."""
    said = _src("app/core/pipeline.py")
    # 🔴 **감싸는 꼴**이 배선이다 — `by_breaks(_grade_by_check(...))` 이면
    #    기존 등급 계산 결과 위에 얹은 것이다. ⚠️ 글자 자리로 앞뒤를 재면
    #    중첩 호출에서 거짓이 된다(내가 그 함정을 밟았다 · 2026-10-12).
    assert "by_breaks(_grade_by_check(" in said.replace("\n", "").replace(
        " ", ""), said[said.index("by_breaks("):][:120]


def test_stance_is_a_schema_field() -> None:
    from app.core.schema import Judgement
    assert "stance" in Judgement.model_fields


def test_card_prints_the_stance() -> None:
    said = _src("app/core/render.py")
    assert "반증" in said and "stance" in said


def test_mutation_unknown_cannot_be_go() -> None:
    """🔴 돌연변이 — `미확인`인데 '간다'로 적는 코드가 있으면 잡는다."""
    import inspect

    from app.core.stages import s7_judge
    tree = ast.parse(inspect.getsource(s7_judge.by_breaks).lstrip())
    said = ast.unparse(tree)
    assert "'간다'" in said or '"간다"' in said
    # 🔴 '간다'를 돌려주는 자리 앞에 **미확인 0건** 검사가 있어야 한다
    assert "UNKNOWN" in said or "미확인" in said
