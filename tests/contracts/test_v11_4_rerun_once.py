"""🔴🔴 **3c 반증 되돌림 — 최대 1회** — 수정 지시서 2026-10-12.

> [3c] 되돌림: ⑫b에서 **새로 확인된 무너짐이 라인업·결장 사실(K1·K6)이면** 그
> 사실을 VariableSet에 넣고 **④부터 재실행**(F1 경로).
> 루프 상한 **1회** — 두 번째는 표시만. 카드 머리에
> "🔁 반증으로 재계산 — 바뀐 것: 상성·확률·등급(전→후)".

🔴 B4 — 재실행 최대 1회. 🔴 B3 — 그 경로를 **제외하면** 반증 전후 확률이 같다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _cond(kind: str, state: str, strength: str = "soft"):
    """🔴 반증이 찾은 조건 — **출처·시각을 들고 있다**(질의가 찾은 기사)."""
    from app.core.schema import BreakCondition
    return BreakCondition(id=f"BRK:{kind}:1", kind=kind, state=state,
                          strength=strength, said="x", player_name="Y",
                          source="https://news.test/a",
                          found_at="2026-10-12T00:00:00Z")


# ══════════════════════════════════════════════════════════════════
# 어떤 무너짐이 되돌림인가 — K1·K6 만
# ══════════════════════════════════════════════════════════════════

def test_only_lineup_facts_trigger_the_rerun() -> None:
    from app.core.stages import s5b_falsify as fx
    broke = [_cond("K1", fx.BROKEN)]
    assert fx.rerun_rows(broke), "🔴 K1(결장)은 되돌림이다"
    assert fx.rerun_rows([_cond("K6", fx.BROKEN)])
    # 🔴 라인업·결장이 **아닌** 종류는 등급만 바꾼다(C2)
    for kind in ("K2", "K3", "K4", "K5"):
        assert not fx.rerun_rows([_cond(kind, fx.BROKEN)]), kind


def test_intact_or_unknown_never_reruns() -> None:
    from app.core.stages import s5b_falsify as fx
    assert not fx.rerun_rows([_cond("K1", fx.INTACT)])
    assert not fx.rerun_rows([_cond("K1", fx.UNKNOWN)])


def test_rerun_rows_makes_variable_facts() -> None:
    """🔴 그 사실을 **VariableSet 에 넣는다** — 꼴이 변수 재료다."""
    from app.core.stages import s5b_falsify as fx
    got = fx.rerun_facts([_cond("K1", fx.BROKEN)])
    assert got and isinstance(got, list)
    one = dict(got[0])
    assert one.get("type") in ("absence", "returning")
    assert one.get("claim")
    # 🔴 **출처·시각이 그대로 간다** — 지어낸 사실이 아니라는 증거다
    assert one.get("source") == "https://news.test/a"
    assert one.get("found_at") == "2026-10-12T00:00:00Z"
    assert one.get("from_break") == "BRK:K1:1"


# ══════════════════════════════════════════════════════════════════
# B4 — 한 번만
# ══════════════════════════════════════════════════════════════════

def test_b4_guarded_by_a_flag() -> None:
    """🔴 재실행 호출이 **깃발 검사 안**에 있다(두 번째는 표시만)."""
    tree = ast.parse(_src("app/core/pipeline.py"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        said = ast.unparse(node)
        if "analyze(" in said and "break_facts" in said:
            found.append(said)
    assert found, "🔴 되돌림 호출이 없다"
    for said in found:
        assert "rerun" in said, said[:200]


def test_analyze_takes_the_flag() -> None:
    import inspect

    from app.core import pipeline
    sig = inspect.signature(pipeline.analyze)
    assert "break_facts" in sig.parameters
    assert "break_rerun" in sig.parameters


def test_head_line_when_rerun() -> None:
    """🔴 카드 머리 — "🔁 반증으로 재계산"."""
    said = _src("app/core/render.py")
    # ⚠️ 굵게 표시(`**`)가 사이에 들어간다 — 글자 둘을 따로 센다
    assert "🔁" in said and "반증으로 재계산" in said


def test_card_carries_the_rerun_mark() -> None:
    from app.core.schema import Card
    assert "break_rerun" in Card.model_fields


def test_b3_probability_same_without_the_rerun_path() -> None:
    """🔴 B3 — ⑫b 는 확률을 **다시 세지 않는다**(되돌림 경로만 예외다).

    ⚠️ 글자로 센다: ⑫b 호출과 ⑬ 사이에 확률 모듈 호출이 있으면 실패.
    """
    said = _src("app/core/pipeline.py")
    i_fx = said.index("s5b_falsify.run(")
    i_scen = said.index("s6_hypo.scenarios(")
    middle = said[i_fx:i_scen]
    for bad in ("_pm.run(", "probmodel.run("):
        assert bad not in middle, middle[:200]
