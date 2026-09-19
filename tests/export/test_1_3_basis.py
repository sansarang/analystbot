"""[ABS-1] 결장 근거(basis)를 **필드로** 남긴다.

🔴 지금은 근거가 **문장 안에만** 있다. 문장을 읽는 쪽은 정규식을 쓰게 되고,
   그 정규식은 문장을 바꾸는 날 조용히 틀린다. 근거는 만든 쪽이 적어야 한다.
🔴 문장 자체는 **한 글자도 바꾸지 않는다** — 그 문구가 곧 λ 계수다
   (`absences._describe` 머리말 · `scoring._absence_factors`). 판정 로직 변경 금지.
"""
from __future__ import annotations

import pytest


# ── ① 근거 값의 원본이 한 곳에 있다

def test_basis_값_집합이_있다():
    from app.collectors import absences as A

    assert set(A.BASES) == {"IL", "lineup_excluded",
                            "transfermarkt", "fotmob_unavailable"}, A.BASES


# ── ② 두 생산자의 문장을 각각 제 근거로 분류한다

@pytest.mark.parametrize("sentence,want", [
    ("New York Yankees의 Jazz Chisholm Jr.(주전 타자) Injured 10-Day로 결장", "IL"),
    ("New York Yankees의 Kervin Castro(선발) Injured 60-Day로 결장", "IL"),
    ("Pittsburgh Pirates의 Rafael Flores Jr.(주전 타자) 라인업 제외로 결장",
     "lineup_excluded"),
    ("New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐",
     "lineup_excluded"),
    ("New York Yankees의 José Caballero 주전 결장 — 오늘 라인업에서 빠짐",
     "lineup_excluded"),
])
def test_문장을_근거로_분류한다(sentence, want):
    from app.collectors import absences as A

    assert A.classify(sentence) == want, sentence


def test_모르는_문장은_None_이다():
    from app.collectors import absences as A

    assert A.classify("무슨 팀의 누구 결장") is None


# ── ③ 생산자가 그 표지를 **상수에서** 가져온다 (손으로 두 번 적지 않는다)

def test_생산자가_상수를_쓴다():
    import inspect

    from app.collectors import absences as A
    from app.engine import lineup_diff as D

    src = inspect.getsource(D.merge_absences_from_diff)
    assert "오늘 라인업에서 빠짐" not in src, "표지를 손으로 적었다 — 사본이다"
    assert A.MARK_TODAY_OUT in D.merge_absences_from_diff.__globals__.values() \
        or "MARK_TODAY_OUT" in src, "상수를 쓰지 않는다"


def test_문장은_한_글자도_바뀌지_않았다():
    """🔴 문구가 곧 계수다 — 기존 출력과 **완전히 같아야** 한다."""
    from app.engine.lineup_diff import merge_absences_from_diff

    r: dict = {}
    got = merge_absences_from_diff(
        r, "New York Yankees",
        [{"type": "regular_out", "who": "Aaron Judge"},
         {"type": "regular_out", "who": "José Caballero"}],
        {"slots": {"AaronJudge": 3}})
    assert got == [
        "New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐",
        "New York Yankees의 José Caballero 주전 결장 — 오늘 라인업에서 빠짐",
    ], got


# ── ④ 내보내기가 근거를 필드로 낸다

def test_export_out_항목에_basis_필드가_있다():
    from app.export.for_fable import _lineup_block

    block = _lineup_block([], "away", [
        "New York Yankees의 Jazz Chisholm Jr.(주전 타자) Injured 10-Day로 결장",
        "New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐",
    ])
    outs = block["out"]
    assert all(isinstance(o, dict) for o in outs), outs
    assert [o["basis"] for o in outs] == ["IL", "lineup_excluded"], outs
    assert all(o.get("text") for o in outs), outs


def test_regulars_missing_count가_근거별로_나뉜다():
    from app.export.for_fable import _lineup_block

    block = _lineup_block([], "away", [
        "New York Yankees의 Jazz Chisholm Jr.(주전 타자) Injured 10-Day로 결장",
        "New York Yankees의 Kervin Castro(선발) Injured 60-Day로 결장",
        "New York Yankees의 Aaron Judge 중심 타선 결장 — 평소 3번, 오늘 라인업에서 빠짐",
    ])
    assert block["regulars_missing_count"] == {"IL": 2, "lineup_excluded": 1}, \
        block["regulars_missing_count"]
