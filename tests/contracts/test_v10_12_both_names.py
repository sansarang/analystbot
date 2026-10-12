"""🔴🔴 **상대 이름도 번역한다** — 사용자 지시 2026-10-12.

> 한글를 현지어로 번역해서 보내든가 아니면 찾을수 있게 하면 되잖아

⚠️ 실사고(푸마스 vs 크루스 아술 · Liga MX): fotmob 색인이 한글에 **0건**이라 ②③ 이
   전부 빗나갔고, 3번(LLM 이름 후보)은 **묻는 팀 하나만** 번역했다 — 상대는 끝까지
   한글이어서 경기 페이지 검사가 *"우리 팀이 이 경기에 없다"* 로 전부 떨어졌고
   `openworld_not_found` 로 끝났다.
⚠️ 게다가 LLM 이 빈손이면 `tried` 에 **한 줄도** 안 남아(#3) 3번이 돌았는지조차
   알 수 없었다.
🔴 고침: 두 이름을 **같이** 번역해 색인에서 확인하고, 상대 쪽 이름으로도 한 번 돈다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _fn(name: str):
    tree = ast.parse((ROOT / "app/findgame.py").read_text(encoding="utf-8"))
    return next(x for x in ast.walk(tree)
                if isinstance(x, ast.AsyncFunctionDef) and x.name == name)


def test_상대_이름을_번역해_넘긴다() -> None:
    said = ast.unparse(_fn("_by_llm_names"))
    assert "ask(str(opponent)" in said, "🔴 상대 이름을 번역하지 않는다"
    assert "opponent=said_other" in said, "🔴 번역된 상대를 사다리에 안 넘긴다"


def test_상대_쪽_이름으로도_돈다() -> None:
    """🔴 §2 ② — 한쪽만 색인에 있을 수 있다."""
    said = ast.unparse(_fn("_by_llm_names"))
    assert "team=str(nm), opponent=asked" in said


def test_LLM_이_빈손이어도_사유가_남는다() -> None:
    """🔴 #3 — 조용히 돌아서던 자리다."""
    said = ast.unparse(_fn("_by_llm_names"))
    head = said.split("if plan is None:")[1][:400]
    assert "tried.append" in head and "못 받았다" in head
