"""🔴🔴 **§6-5 사실 추출 — EX1·EX2 와 상태·등급·충돌**.

> 스키마: {종류, 대상, **상태**(결장/의심/복귀/선발 예상), 사유, 기간, 출처 URL,
> **원천 등급**, 문서 시각, 근거 문장}. 같은 사실 여러 원천 → 하나로 합치고
> **원천 등급 최고값·원천 수 기록**. 서로 다르면 **충돌 표시**(카드에 둘 다).
> 계약 **EX1**: 근거 문장·출처 없는 사실은 버린다.
> **EX2**: 근거 문장에 **경기 결과**가 있으면 버린다(premature_result).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 🔴 EX1
# ══════════════════════════════════════════════════════════════════

def test_ex1_needs_a_quote() -> None:
    from app.core.search import facts as fx
    ok, why = fx.keep(quote="", urls=["https://a.test/x"])
    assert ok is False and "EX1" in why


def test_ex1_needs_a_source() -> None:
    from app.core.search import facts as fx
    ok, why = fx.keep(quote="그 선수는 결장한다", urls=[])
    assert ok is False and "EX1" in why


def test_ex1_passes_with_both() -> None:
    from app.core.search import facts as fx
    ok, why = fx.keep(quote="그 선수는 결장한다", urls=["https://a.test/x"])
    assert ok is True, why


# ══════════════════════════════════════════════════════════════════
# 🔴 EX2 — 근거 문장에 경기 결과가 있으면 버린다
# ══════════════════════════════════════════════════════════════════

def test_ex2_drops_a_result_sentence() -> None:
    from app.core.search import facts as fx
    ok, why = fx.keep(quote="홈 팀이 2-1 로 이겼다", urls=["https://a.test/x"])
    assert ok is False and "EX2" in why


def test_ex2_keeps_a_score_without_a_result_word() -> None:
    """⚠️ 스코어 꼴만 있는 문장은 **버리지 않는다**(거짓 탈락을 막는다)."""
    from app.core.search import facts as fx
    ok, why = fx.keep(quote="3-5-2 로 나설 전망이다", urls=["https://a.test/x"])
    assert ok is True, why


# ══════════════════════════════════════════════════════════════════
# 🔴 상태 · 등급 · 충돌
# ══════════════════════════════════════════════════════════════════

def test_states_are_the_four() -> None:
    from app.core.search import facts as fx
    assert fx.STATES == ("결장", "의심", "복귀", "선발 예상")


def test_doubt_beats_absence() -> None:
    """🔴 *"doubtful to miss"* 는 **의심**이다(결장이 아니다)."""
    from app.core.search import facts as fx
    got, why = fx.state_of("He is doubtful and could miss the game")
    assert got == "의심", (got, why)


def test_state_is_empty_when_unknown() -> None:
    from app.core.search import facts as fx
    got, why = fx.state_of("그 팀은 원정에 나선다")
    assert got == "" and "🔴" in why


def test_grade_is_the_best_of_the_sources() -> None:
    """🔴 원천 **등급 최고값**과 원천 수를 센다(표가 등급을 정한다)."""
    from app.core.search import facts as fx
    best, n, why = fx.grades_of(["https://www.bbc.com/sport/a",
                                 "https://unknown.test/b"],
                                league="league:PL")
    assert n == 2 and best == "A", (best, why)


def test_conflict_is_flagged() -> None:
    from app.core.search import facts as fx
    bad, why, rows = fx.conflict_of(["그 선수는 결장한다",
                                     "그 선수가 복귀한다"])
    assert bad is True and set(rows) == {"결장", "복귀"} and "충돌" in why


# ══════════════════════════════════════════════════════════════════
# 🔴 배선
# ══════════════════════════════════════════════════════════════════

def test_variable_carries_the_schema() -> None:
    from app.core.schema import Variable
    for name in ("state", "grade", "n_sources", "conflict"):
        assert name in Variable.model_fields, name


def test_s5_uses_the_module() -> None:
    said = _src("app/core/stages/s5_verify.py")
    assert "search import facts" in said
    assert "grades_of(" in said and "conflict_of(" in said


def test_card_prints_state_and_grade() -> None:
    said = _src("app/core/render.py")
    assert "상태 **" in said and "원천 {v.grade}등급" in said
