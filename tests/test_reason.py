"""🔴🔴 **실패한 조건이 사유를 정한다** — 4단계(사용자 설계 2026-10-03).

> 사유 문자열을 **사람이 쓰지 않는다** — 실패한 `if` 문이 enum 을 돌려준다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 거짓 사유가 사용자를 **두 번** 헛돌게 했다
══════════════════════════════════════════════════════════════════

실측 2026-10-03: 봇이 `Croatia` 로 적어 놓고 `크로아티아` 로 되찾아 실패한 뒤
*"질문 창 밖이다 — 날짜를 지정해 다시 물어라"* 라고 적었다. 🔴 **날짜는 맞았고
이름이 달랐다.** 사용자가 날짜를 지정해 다시 물었고 **같은 자리에서 또 막혔다.**

⚠️ 문장을 자리마다 쓰면 *"무엇이 막았나"* 와 *"무엇이 막았다고 내가 생각했나"* 가
   갈린다. 🔴 enum → 문장이 **한 표**이면 그 거짓이 생길 자리가 없다.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from app import matchref
from app.matchref import SAY, Reason

ROOT = Path(__file__).resolve().parents[1]


def test_모든_사유에_사용자_문장이_있다():
    """🔴 빠진 사유가 있으면 그 자리에서 **사용자가 아무 말도 못 듣는다**."""
    missing = [r for r in Reason if r is not Reason.OK and r not in SAY]
    assert not missing, f"사용자 문장이 없는 사유: {missing}"
    for r, text in SAY.items():
        # ⚠️ 표시는 🔴 또는 ⚠️ 다 — **우리 버그가 아닌 사유**(장애·예산)는
        #    ⚠️ 로 적는 것이 맞다(v5-A `deepseek_unavailable` 이 그 꼴이다).
        assert text.strip() and ("🔴" in text or "⚠️" in text), r


def test_다시_물어서_풀리는지를_구조로_가른다():
    """🔴🔴 그 구분이 **거짓말을 막는다**.

    ⚠️ `fixable_by_asking_again` 이 거짓인데 *"다시 물어라"* 라고 적으면 사용자가
       헛돈다 — 실측에서 정확히 그 일이 있었다.
    """
    assert Reason.OUT_OF_WINDOW.fixable_by_asking_again
    assert Reason.AMBIGUOUS.fixable_by_asking_again
    # 🔴 **이름·수집 문제는 다시 물어도 안 풀린다**
    assert not Reason.NAME_UNRESOLVED.fixable_by_asking_again
    assert not Reason.NOT_COLLECTED.fixable_by_asking_again
    assert Reason.NAME_UNRESOLVED.is_our_bug
    assert Reason.NOT_COLLECTED.is_our_bug
    # 🔴 **둘이 겹치면 안 된다** — 겹치면 그 분류가 뜻을 잃는다
    for r in Reason:
        if r is Reason.OK:
            continue
        assert not (r.fixable_by_asking_again and r.is_our_bug), r


def test_문장과_분류가_어긋나지_않는다():
    """🔴🔴 **표 자신이 거짓말하지 않게** 본다.

    ⚠️ *"다시 물어라"* 라고 적어 놓고 `fixable_by_asking_again` 이 거짓이면 그
       표가 바로 그 거짓말이다 — 실측에서 난 사고를 표 안에서 재현한 꼴이다.
    """
    for r, text in SAY.items():
        tells_retry = ("다시 물어라" in text) or ("지목해라" in text) \
            or ("적어 달라" in text)
        if tells_retry:
            assert r.fixable_by_asking_again, f"{r}: 다시 물으라는데 안 풀린다"
        if r.is_our_bug:
            assert "다시 물어도 같다" in text, f"{r}: 안 풀린다고 안 적었다"








def test_사유를_쓰는_곳이_한_모듈이다():
    """🔴 `Reason` 이 여러 파일에 복제되면 그 순간 뜻이 갈린다(사본 금지)."""
    hits = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        if "class Reason(Enum)" in src:
            hits.append(str(p.relative_to(ROOT)))
    # ⚠️ **v5 §8-6 으로 자리가 옮겼다**(2026-10-04) — 사유는 전 구간(검색·읽기·
    #    검증·판정·예산)을 덮으므로 입구 모듈이 들 것이 아니다.
    #    🔴 **여전히 한 파일이다** — 그것이 이 계약의 요점이고 자리만 바뀌었다.
    assert hits == ["app/reasons.py"], hits
    assert matchref.Reason is Reason


