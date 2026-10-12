"""🔴🔴 **§1 불필요 요소 정리** — 지시서 2026-10-12(셋째) §1.

> 계약 **X1**: 삭제·축소된 단계가 **확률·등급 경로에 남아 있으면 실패**.
> 계약 **X2**: LLM 호출은 **`s4_extract`(사실 추출)·필요 시 라인업 캡처 판독**만.

🔴 처분표(그 지시서 §1)와 **이 계약이 한 짝**이다 — 지운 것이 되살아나면 빨개진다.
⚠️ 이 파일은 **처분이 끝난 뒤** 초록이 된다(먼저 빨갛게 쓴다).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 🔴🔴 **지워질 모듈** — 처분표의 "삭제" 줄
GONE: tuple[str, ...] = (
    "app/core/priority.py",          # ⑨ 우선순위 지수 → absence_loss 가 대체
    "app/core/reweight.py",          # ⑳ 시나리오 재가중 → 생존은 격자에서
    "app/core/stages/s6_hypo.py",    # ⑭⑮ 가설·무너뜨릴 조건(LLM)
    "app/core/stages/s5b_falsify.py",  # ⑱ 반증 딥서치 → 2절 오늘 사실 질의로
)

#: 🔴 LLM 을 불러도 되는 자리 — **사실 추출**과 캡처 판독뿐(X2)
LLM_OK: tuple[str, ...] = (
    "app/core/stages/s4_extract.py",   # ⑥ 기사 → 결장·복귀·라인업 **사실**
    "app/core/ocr.py",                 # 라인업 캡처 판독
    "app/core/llm.py",                 # 통로 자체
    "app/core/rank.py",                # 재정렬(검색 순서 · 사실 추출의 입력)
    "app/core/rerank.py",
)

#: 🔴 LLM 을 부르는 글자(D46 으로 코드만 본다)
LLM_WORDS = ("core.llm", "llm.ask", "llm.json", "_llm.")


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


def test_x1_deleted_modules_are_gone() -> None:
    """🔴🔴 **X1** — 처분표의 "삭제" 모듈은 **파일이 없다**."""
    left = [rel for rel in GONE if (ROOT / rel).is_file()]
    assert not left, f"🔴 아직 남아 있다: {left}"


def test_x1_no_one_imports_them() -> None:
    """🔴 **X1** — `app/` 어디서도 그것을 들여오지 않는다(확률·등급 경로 포함)."""
    bad: list[str] = []
    names = [Path(rel).stem for rel in GONE]
    for p in sorted((ROOT / "app").rglob("*.py")):
        said = _code(p.relative_to(ROOT).as_posix())
        for name in names:
            if f"import {name}" in said or f"{name}." in said:
                bad.append(f"{p.relative_to(ROOT)} → {name}")
    assert not bad, f"🔴 지운 단계를 부른다: {bad}"


def test_x2_llm_is_called_only_for_facts() -> None:
    """🔴🔴 **X2** — LLM 을 부르는 파일은 **사실 추출·캡처 판독**뿐이다."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel in LLM_OK:
            continue
        said = _code(rel)
        if any(w in said for w in LLM_WORDS):
            bad.append(rel)
    assert not bad, f"🔴 LLM 을 부르는 자리가 남았다(X2): {bad}"


def test_card_has_no_llm_prose_blocks() -> None:
    """🔴 ㉔ — 카드 서술은 **코드 템플릿**이다(LLM 문장 블록이 없다)."""
    said = _code("app/core/render.py")
    for bad in ("say", "tactic_long", "verdict_long"):
        assert bad not in said, bad
