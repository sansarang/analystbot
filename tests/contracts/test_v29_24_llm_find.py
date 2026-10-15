"""🔴🔴 **solar 경기 찾기 퇴로** — 사용자 지시 2026-10-15
*"봇에 경기 검색 solar api 를 추가해라"*.

⚠️ 실사고 2026-10-15(남아공 `Hope FC` 22:30): 퇴로 셋이 전부 못 찾았다 —
   철자(이름표가 모른다) · ⑥단 findgame(**fotmob 색인에 없다**) · 대회 일정
   (**남아공 리그가 대회 표에 없다**). `openworld_not_found` 로 ①에서 멈췄고,
   벽은 **상대 팀 이름을 모르는 것**이었다.

지키는 것:
  LF1 `_by_llm` 이 **퇴로 맨 앞**에 배선돼 있다(사용자 지시 2026-10-15:
      *"solar 로 그냥 넣어라 맨 처음으로"* — 앞 셋을 다 기다리는 시간이 아깝다)
  LF2 공급자는 **`llm.ask_first`**(solar → deepseek) 하나로 고른다
  LF3 🔴🔴 **문서 접지** — 모델이 낸 이름·인용이 본문에 없으면 **버린다**
  LF4 출력 칸에 **수가 없다**(이름 둘과 인용뿐)
  LF5 물어본 팀이 그 경기 한쪽이어야 한다(`verify.same_team`)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s1_resolve.py"


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


def _fn(name: str) -> str:
    code = _code(MOD)
    i = code.index(f"async def {name}(")
    j = code.find("\nasync def ", i + 10)
    return code[i:j if j > i else len(code)]


def test_lf1_wired_first() -> None:
    """LF1 🔴 `run` 이 `_by_llm` 을 **맨 처음** 부른다(사용자 지시 2026-10-15).

    ⚠️ 실측 2026-10-15(`Hope FC`): 앞 셋이 전부 못 찾는 경기에서 ⑥단
       findgame 을 기다리는 데만 시간이 갔다. 🔴 순서가 바뀌어도 확정 기준은
       그대로다 — 본문 대조 → 기존 길(⑥단 → 입구 → `same_team`).
    """
    said = _fn("run")
    for one in ("_respell(", "_openworld(", "_by_schedule(", "_by_llm("):
        assert one in said, f"LF1 🔴 `run` 이 `{one}` 를 안 부른다"
    first = said.index("_by_llm(")
    for one in ("_respell(", "_by_schedule("):
        assert first < said.index(one), (
            f"LF1 🔴 solar 퇴로가 `{one}` 보다 **뒤에** 있다 — 맨 처음이어야 한다")


def test_lf2_provider_order_is_shared() -> None:
    """LF2 🔴 공급자 순서를 **직접 적지 않는다** — `ask_first` 가 든다."""
    said = _fn("_by_llm")
    assert "ask_first(" in said, "LF2 🔴 `llm.ask_first` 를 안 쓴다"
    assert 'provider="solar"' not in said and "ORDER" not in said, (
        "LF2 🔴 공급자를 이 함수가 정한다 — 순서의 원본은 `llm.ORDER` 하나다")


def test_lf3_grounded_in_docs() -> None:
    """LF3 🔴🔴 **본문 대조**가 있어야 한다(모델 기억 금지 · 절대규칙 5)."""
    said = _fn("_by_llm")
    assert "_grounded" in said, "LF3 🔴 본문 대조 함수가 없다"
    # 🔴 세 글자(홈·원정·인용) 전부를 대조한다
    assert "_grounded(quote" in said and "_grounded(x)" in said, said[-600:]
    assert "body_of(" in said, "LF3 🔴 본문을 받지 않는다 — 스니펫만으로는 안 된다"


def test_lf4_output_has_no_numbers() -> None:
    """LF4 🔴 출력 칸은 **이름 둘 + 인용**뿐이다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s1_resolve import _find_schema

    got = set(_find_schema().model_fields)
    assert got == {"home", "away", "quote"}, (
        f"LF4 🔴 출력 칸이 {sorted(got)} 다 — 수·시각을 모델이 내면 창 검사가 "
        "모델 글자에 기대게 된다")


def test_lf5_asked_team_must_be_in_match() -> None:
    """LF5 🔴 물어본 팀이 그 경기 한쪽이어야 한다(이름 맞추기는 하나다)."""
    said = _fn("_by_llm")
    assert "verify.same_team" in said, "LF5 🔴 `same_team` 문을 안 지난다"
    # 🔴 그리고 **기존 길로 되돌아간다**(확정 기준을 새로 만들지 않는다)
    assert "_openworld(" in said and "_try(" in said, said[-500:]
