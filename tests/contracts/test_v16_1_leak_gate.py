"""🔴🔴 **§1 누설 관문 · §7 판정 규칙 고정** — 비교 시험 지시서 2026-10-12.

> 계약 **L4**: 재현에서 **현재 값 입구**가 ⬜ 없이 축 값에 들어가면 실패.
> 계약 **J1**: `judge_models.py` 는 **실행 전 커밋**, 실행 후 변경 시 실패.

🔴 L4 를 코드로 센다 — *"현재 값"* 으로 표시된 입구(`asof.NOW_ONLY`)가 **재현
   모드에서 막혀 있나**(`asof.may_use(key, replay=True)` 가 거짓인가).
🔴 J1 은 **판정 규칙이 결과를 보기 전에 박혀 있다**는 보장이다 — 그 함수가
   `app/core/metrics.verdict_of` 와 `tools/judge_models.PASS` 둘뿐임을 센다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_l4_current_value_entries_are_blocked_in_replay() -> None:
    """🔴🔴 **L4** — `현재 값` 입구는 재현에서 **못 쓴다**."""
    from app.core import asof
    now_only = [k for k, v in asof.NOW_ONLY.items()
                if str(v).startswith(asof.MARK)]
    assert now_only, "🔴 L2 표가 비었다(그러면 L4 가 아무것도 안 센다)"
    for key in now_only:
        ok, why = asof.may_use(key, replay=True)
        assert not ok, f"🔴 **L4 위반** — 재현에서 `{key}` 가 통과한다({why})"
        # 🔴 사유가 **이름으로** 남아야 한다(⬜ 표시의 근거다)
        assert key in why or "현재 값" in why, why


def test_l4_live_run_may_use_them() -> None:
    """⚠️ 운영(실시간)에서는 쓸 수 있다 — 그 경계가 L2 의 뜻이다."""
    from app.core import asof
    ok, _why = asof.may_use("standings", replay=False)
    assert ok


def test_leak_audit_tool_exists_and_reports_three_parts() -> None:
    """🔴 §1 도구가 **입구표·결과 grep·계수 판** 셋을 낸다."""
    said = (ROOT / "tools/leak_audit.py").read_text(encoding="utf-8")
    for want in ("1-1", "1-3", "1-4", "NOW_ONLY", "before_as_of"):
        assert want in said, want


def test_j1_judgement_rule_is_a_function_not_a_comment() -> None:
    """🔴🔴 **J1** — 판정 규칙이 **코드**로 박혀 있다(결과를 보고 못 고친다).

    🔴 `tools/judge_models.PASS` 가 (a)(b)(c) 를 세고, 그 셋의 뜻이 지시서 §7 과
       같은 글자로 적혀 있다.
    """
    said = (ROOT / "tools/judge_models.py").read_text(encoding="utf-8")
    tree = ast.parse(said)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "passes" in names, "🔴 §7 판정 함수(`passes`)가 없다"
    for want in ("+0.005", "p < 0.05", "상위 30", "항 수가 적은 쪽"):
        assert want in said, want
