"""🔴🔴 **예상 XI 결장 반영 규칙** — 사용자 지시 2026-10-13 밤 다섯째 2번.

> 2. 예상 XI 결장 반영 규칙 변경(즉시 · 확률 엔진 불변) — fotmob 결장(B) 단독 →
>    예상 XI 에서 빼지 않는다. "결장 의심(B 단독)" 표시만.
>    — 빼는 조건: S등급(공식 징계·구단 발표) 하나 또는 B + A/C 원천 교차 확인.

🔴 왜 — `adapt.xi_of` 가 **결장 명단에 이름이 있으면 그냥 뺐다**. 그 명단의
   원천은 fotmob 경기 페이지 하나(**B**)이고, 그 칸은 *"부상 의심"* 수준의 이름도
   싣는다. 예상 11명에서 사람을 빼면 **그 자리를 우리가 지어내야** 하므로(또는
   10명으로 남으므로) 틀린 XI 가 된다.
🔴 **확률 엔진은 안 바뀐다** — 라인업은 확률 경로에서 영구 제외다(통합 지시서
   머리 §0). 이 규칙은 **예상 XI 명단과 카드 표시**만 바꾼다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _miss(name: str, *, source: str, url: str = ""):
    from app.core.schema import Missing
    return Missing(name=name, source=source, source_url=url)  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════
# 🔴 XA1 — 규칙은 **한 함수**가 정한다(사본 금지)
# ══════════════════════════════════════════════════════════════════

def test_b_alone_does_not_remove() -> None:
    """🔴🔴 **B 단독은 못 뺀다**(fotmob 경기 페이지 하나)."""
    from app.core import absence
    ok, why = absence.removable([_miss("A", source="page")], league="league:J1")
    assert ok is False, why
    assert "B 단독" in why


def test_s_alone_removes() -> None:
    """🔴 S 하나면 뺀다 — 연맹 징계 공시."""
    from app.core import absence
    ok, why = absence.removable([_miss("A", source="discipline")],
                                league="league:J1")
    assert ok is True, why
    assert "S" in why


def test_b_plus_article_removes() -> None:
    """🔴 B + A/C 원천 **교차 확인**이면 뺀다."""
    from app.core import absence
    ok, why = absence.removable(
        [_miss("A", source="page"),
         _miss("A", source="article", url="https://www.nikkansports.com/x")],
        league="league:J1")
    assert ok is True, why


def test_roster_gap_still_removes() -> None:
    """⚠️ **오늘 출전 명단에 없다**(명단 대조)는 그대로 뺀다 — 선발이 불가능하다.

    🔴 지시가 바꾼 것은 **fotmob `unavailable` 칸(B)** 하나다. 명단 대조는
       *"오늘 선발+벤치에 그 이름이 없다"* 는 **구조 사실**이다.
    """
    from app.core import absence
    ok, why = absence.removable([_miss("A", source="roster")],
                                league="league:J1")
    assert ok is True, why


# ══════════════════════════════════════════════════════════════════
# 🔴 XA2 — 어댑터가 **그 함수만** 본다
# ══════════════════════════════════════════════════════════════════

def test_adapter_asks_the_rule() -> None:
    """🔴 `adapt.xi_of` 가 `absence.removable` 을 부른다(사본 금지)."""
    tree = ast.parse(_src("app/core/adapt.py"))
    said = ast.unparse(tree)
    assert "removable" in said


def test_predicted_xi_keeps_the_b_only_name() -> None:
    """🔴🔴 예상 XI 에 **11명이 그대로 남고** 의심 사유가 붙는다."""
    from app.core import adapt
    raw = {"players": [f"P{i}" for i in range(1, 12)],
           "lineup_state": "predicted"}
    got = adapt.xi_of("team:000001", raw, missing=[_miss("P3", source="page")])
    assert len(got.players) == 11, got.players
    assert "P3" in got.players
    assert any("결장 의심" in c for c in got.conflicts), got.conflicts


def test_cross_confirmed_name_is_removed() -> None:
    from app.core import adapt
    raw = {"players": [f"P{i}" for i in range(1, 12)],
           "lineup_state": "predicted"}
    got = adapt.xi_of("team:000001", raw,
                      missing=[_miss("P3", source="page"),
                               _miss("P3", source="discipline")])
    assert len(got.players) == 10 and "P3" not in got.players
    assert any("제외" in c for c in got.conflicts), got.conflicts


def test_confirmed_xi_is_untouched() -> None:
    """⚠️ 확정 XI 는 **손대지 않는다**(그 11명이 실제로 나왔다)."""
    from app.core import adapt
    raw = {"players": [f"P{i}" for i in range(1, 12)],
           "lineup_state": "confirmed"}
    got = adapt.xi_of("team:000001", raw, missing=[_miss("P3", source="discipline")])
    assert len(got.players) == 11 and not got.conflicts


# ══════════════════════════════════════════════════════════════════
# 🔴 XA3 — **확률 엔진 불변**
# ══════════════════════════════════════════════════════════════════

def test_probability_engine_does_not_read_the_rule() -> None:
    """🔴 `removable` 이 확률 경로에서 **안 불린다**(표시·명단만 바꾼다)."""
    for rel in ("app/core/probfloor.py", "app/core/probmodel.py",
                "app/core/lineupfix.py", "app/core/legacy/old_engine.py"):
        assert "removable" not in _src(rel), rel
