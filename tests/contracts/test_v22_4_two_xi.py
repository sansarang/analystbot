"""🔴🔴 **4번 라인업 전후 가치**(지시 2026-10-13 밤 넷째).

> 운영 카드마다 **"예상 XI 판" 확률**과 **"확정 XI 판" 확률**을 둘 다 저장
> (이미 재분석 경로 있음). `score_cards` **30경기마다** 두 판의 방향·로그 손실·
> 상위 20% 비교 — 차이가 작으면 *"판정은 확정 XI 후에만"* 을 **등급 규칙 후보**로 보고.

🔴 **확률은 안 바뀐다** — 저장·채점용이다(등급·생존에 닿으면 실패).
🔴 XI 상태를 읽는 문은 `layer1.xi_state` 하나다(사본 금지).
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


def test_card_has_the_two_fields() -> None:
    from app.core.schema import Card
    for name in ("prob_expected", "prob_expected_why"):
        assert name in Card.model_fields, name


def test_pipeline_carries_the_previous_run() -> None:
    """🔴 지난 실행(예상 XI 판)의 확률을 **그 카드에서** 가져온다."""
    said = _code("app/core/pipeline.py")
    assert "prob_expected" in said and "_LAST" in said
    # 🔴 XI 상태는 `layer1.xi_state` 하나로 읽는다
    assert "xi_state" in said


def test_card_prints_both_plates() -> None:
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "예상 XI 판" in said and "확정 XI 판" in said


def test_score_cards_compares_the_two_plates() -> None:
    said = (ROOT / "tools/score_cards.py").read_text(encoding="utf-8")
    assert "XI_PLATE" in said and "예상 XI 판" in said
    assert "REPORT_EVERY" in said


def test_the_two_plates_never_touch_grade_or_survival() -> None:
    """🔴🔴 확률 불변 — 판정·생존 코드에 그 이름이 **없다**."""
    for rel in ("app/core/stages/s7_judge.py", "app/core/bands.py",
                "app/core/probmodel.py"):
        path = ROOT / rel
        if not path.exists():
            continue
        code = _code(rel)
        for bad in ("prob_expected", "확정 XI 판"):
            assert bad not in code, (rel, bad)
