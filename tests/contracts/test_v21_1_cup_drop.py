"""🔴🔴 **§1 폼 입력 컵 제외**(지시서 2026-10-13 밤 셋째 · K0 불변).

> 축1 폼 창을 **리그 경기만**으로(부족하면 이번 시즌 리그 → 지난 시즌 리그 순
> 보충, **컵 제외**). 보충 경기 표시.
> ⚠️ 이 규칙은 **"국내 리그 경기의 폼"** 에만 적용한다(대륙 대회는 §5-3 규칙).

🔴 **왜** — 실측 2026-10-13: 운영이 받는 팀 일정에는 **이번 시즌만** 있어 지난
   시즌은 구조적으로 못 섞이고, 대신 **컵이 섞인다**(창 5경기 중 J1 **0.84** ·
   K1 0.21 · 울산 34경기 중 3 · 가시마 12경기 중 3).
🔴 컵을 가리는 자리는 `level.is_cup` 하나다(사본 금지).
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _row(day: str, comp: str) -> dict:
    return {"utc": f"{day}T12:00:00Z", "league": "league:KL1",
            "league_name": comp, "comp": comp, "gf": 1, "ga": 0}


def test_cup_rows_are_dropped() -> None:
    from app.core.legacy import form_input as fi
    rows = [_row("2026-03-01", "K League 1"),
            _row("2026-03-05", "Korean FA Cup"),
            _row("2026-03-08", "K League 1"),
            _row("2026-03-12", "AFC Champions League"),
            _row("2026-03-15", "K League 1")]
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:KL1", k_min=3, drop_cup=True)
    # 🔴 **컵과 대륙 대회를 둘 다** 뺀다(§1 은 *"리그 경기만"* 이라고 했다)
    assert len(got) == 3, got
    assert all("League 1" in str(r.get("league_name")) for r in got), got
    assert "리그 밖" in why and "2" in why


def test_cup_drop_is_off_by_default() -> None:
    """🔴 기본값은 **끈 상태**다 — 판정이 끝나기 전에는 운영이 안 바뀐다."""
    import inspect

    from app.core.legacy import form_input as fi
    said = inspect.signature(fi.pick).parameters["drop_cup"]
    assert said.default is False


def test_cup_rows_cannot_fill_the_shortfall() -> None:
    """🔴 보충도 **리그 경기로만** 한다(컵으로 채우지 않는다)."""
    from app.core.legacy import form_input as fi
    rows = [_row("2025-10-01", "K League 1"),
            _row("2025-10-08", "Korean FA Cup"),
            _row("2026-03-01", "K League 1")]
    got, why = fi.pick(rows, as_of=datetime(2026, 3, 20, tzinfo=UTC),
                       league="league:KL1", k_min=3, drop_cup=True)
    assert len(got) == 2, got            # 🔴 리그 둘(이번 1 + 지난 1)
    assert all("Cup" not in str(r.get("league_name")) for r in got), got
    assert "채웠다" in why


def test_the_cup_gate_is_one_function() -> None:
    """🔴 가리는 문은 **`competition.key_of` + `level.is_cup`** 이다(글자 비교 금지).

    ⚠️ 실측 2026-10-13: `is_cup` 만으로는 **`AFC Champions League` 를 못 잡는다**
       (컵이 아니라 대륙 대회다) → 대회 표기를 **리그 열쇠로 바꿔** 비교한다.
    """
    import ast
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/core/legacy/form_input.py").read_text(encoding="utf-8")
    tree = ast.parse(said)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "is_cup" in code and "key_of" in code
    for bad in ('"cup"', "'cup'", '"Cup"'):
        assert bad not in code, bad
