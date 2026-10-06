"""🔴🔴 **v5 §3-3·§3-4 — 프롬프트와 카탈로그.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]










# ══════════════════════════════════════════════════════════════════
# §3-4 변수 카탈로그
# ══════════════════════════════════════════════════════════════════


def test_v5_3_4_카탈로그가_선언에서_온다():
    """🔴 *"유형마다 search 템플릿 2~3개와 작동 방향 규칙이 … 에 있다."*

    ⚠️ 지시문은 `config/catalog.yaml` 이라 적었다 — 우리 선언은
       `config/variable_types.yaml` 이다(v4 §4 유형표). 🔴 **한 곳**이면 된다.
    """
    from app import rules
    types = rules.variable_types()
    assert len(types) >= 15, len(types)
    # 🔴 검색 템플릿이 있는 유형은 **2개 이상**을 든다(§3-4)
    few = {k: len(v.get("search") or [])
           for k, v in types.items()
           if v.get("search") and len(v.get("search") or []) < 2}
    assert not few, f"🔴 템플릿이 하나뿐인 유형: {few}"




# ══════════════════════════════════════════════════════════════════
# §4-4 받기 전에 거른다 · §4-5 크기·시간 상한 · §4-6 깊이 소스 예산
# ══════════════════════════════════════════════════════════════════


# ── 대역 ──────────────────────────────────────────────────────────




def _draft(sid: str, strength: float):
    from app import scenarios
    return scenarios.Draft(id=sid, scores=["2-1"], strength=strength,
                           template_id="t", why="w", variables=["V1"],
                           added_by="template")




