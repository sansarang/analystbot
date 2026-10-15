"""🔴🔴 **fotmob 열쇠 접두 · 버린 문서 드러내기** — 사용자 지시 2026-10-15.

⚠️ 실사고 2026-10-15(BG Pathum vs Adelaide): 일정 퇴로가 `ext_id` 를 **날숫자**
   `6054753` 로 적었다. fotmob 어댑터는 **접두를 요구**하므로(`sources_context`)
   ② 가 받을 주소가 **0건**이 되어 `XI 0/2 · 감독 0/2` 가 났고, `fotmob:6054753`
   행이 따로 있어 **같은 경기가 두 행**이 됐다(실측).

지키는 것:
  RS6 일정 퇴로는 `matchkey.make("fotmob", …)` 로 열쇠를 만든다
  RS7 ② 장부가 **열쇠 없음**과 **라인업 미발표**를 가른다
  RS8 ③ 장부가 **버린 문서 수·사유**를 적는다(#3 조용한 0 금지)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def test_rs6_schedule_fallback_uses_prefix() -> None:
    """RS6 🔴🔴 — 퇴로가 **접두 붙인 열쇠**를 적는다."""
    said = _code("app/core/stages/s1_resolve.py")
    i = said.index("async def _by_schedule")
    j = said.find("\nasync def ", i + 10)
    one = said[i:j if j > i else len(said)]
    assert 'matchkey.make("fotmob"' in one, (
        "RS6 🔴🔴 퇴로가 `matchkey.make` 를 안 쓴다 — 날숫자를 적으면 fotmob "
        "어댑터가 그 경기를 **못 집는다**(XI 0/2 의 뿌리)")
    assert "_UPSERT_GAME, \"soccer\", lg, ext," in one, one[-400:]


def test_rs7_xi_reason_is_split() -> None:
    """RS7 🔴 ② 가 **열쇠 없음**과 **미발표**를 가른다."""
    said = _code("tools/run_collect.py")
    assert "context_of(ref.competition, ref.id)" in said, (
        "RS7 🔴 어댑터 유무를 **원본 라우팅**으로 확인하지 않는다")
    assert "열쇠에 어댑터가 없다" in said and "아직 안 올라왔다" in said


def test_rs8_dropped_docs_are_named() -> None:
    """RS8 🔴 ③ 장부가 버린 문서를 **수와 사유로** 적는다."""
    said = _code("tools/run_collect.py")
    assert 'getattr(st, "drops", None)' in said, (
        "RS8 🔴 버린 문서를 안 읽는다 — `문서 5건` 만 찍으면 열기 실패 6건이 "
        "안 보인다(실측 2026-10-15)")
    assert "버린 문서" in said and "🔴 버림" in said
