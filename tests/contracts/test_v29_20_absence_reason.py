"""🔴🔴 **결장 사유도 LLM 이 찾는다** — 사용자 지시 2026-10-15.

> fotmob 에 **결장 사유나 알 수 없는 정보**도 역시 **llm 이 서치해서 채워야** 한다

⚠️ 실측 2026-10-15(강원 vs 프놈펜): 결장 **21명의 사유가 전부 `other`** 였다 —
   fotmob 이 사유를 안 준다. 부상·징계·로테이션 중 무엇인지 모르면 그 결장이
   **얼마나 센 변수인지** 알 수 없다.
🔴 그래서 **사유 없는 결장자 이름**을 ⑥ 의 빈 칸으로 올려 LLM 이 찾게 한다.
"""
from __future__ import annotations

import inspect

from app.core.schema import Facts, Missing
from app.core.stages import s4b_gapsearch as gs

KEY, NAME = "team:100001", "Gangwon FC"


def _need(rows: list[Missing]) -> list[str]:
    facts = Facts(missing={KEY: rows}, xi={}, coach={})
    got = gs.need(facts, keys=[KEY], names={KEY: NAME}, sides={KEY: "home"})
    return [x for x in list(got.get(NAME) or got.get(KEY) or [])
            if "결장 사유" in x]


def test_칸이_표에_있다() -> None:
    assert any(one[0].startswith("결장 사유") for one in gs.GAPS), gs.GAPS


def test_사유가_other_면_빈_칸이다() -> None:
    said = _need([Missing(name="Chung-Hyo Park", reason="other")])
    assert said and "Chung-Hyo Park" in said[0], said


def test_사유를_알면_안_묻는다() -> None:
    """🔴 이미 아는 것을 다시 묻지 않는다(예산)."""
    assert _need([Missing(name="Son", reason="injury"),
                  Missing(name="Kim", reason="suspension")]) == []


def test_이름을_적는다() -> None:
    """🔴 열쇠가 아니라 **사람 글자**다 — 그래야 그 선수를 겨눈 질의가 나온다."""
    rows = [Missing(name=f"P{i}", reason="other") for i in range(6)]
    said = _need(rows)
    assert said and "P0" in said[0] and "외 2명" in said[0], said


def test_스키마는_빈_사유를_허용하지_않는다() -> None:
    """⚠️ 실측: `Missing.reason` 은 Literal 이라 **빈 글자가 불가능**하다 —
    모를 때 들어오는 값이 `other` 다. 🔴 `DIM_REASONS` 의 `""` 는 **방어**다."""
    import pydantic
    import pytest
    with pytest.raises(pydantic.ValidationError):
        Missing(name="X", reason="")
    assert Missing(name="X").reason == "other"


def test_아는_사유는_전부_안_묻는다() -> None:
    """🔴 `doubtful`·`international_duty` 도 **아는 것**이다 — 묻지 않는다."""
    for one in ("doubtful", "international_duty"):
        assert _need([Missing(name="Y", reason=one)]) == [], one


def test_프롬프트가_선수_이름으로_찾으라고_한다() -> None:
    src = inspect.getsource(gs.ask) if hasattr(gs, "ask") else ""
    if not src:
        import pathlib
        src = pathlib.Path("app/core/stages/s4b_gapsearch.py").read_text()
    assert "결장 사유 칸이 있으면 그 선수 이름으로 찾는다" in src
    for one in ("injury", "부상", "suspended"):
        assert one in src, one


def test_모르는_사유_글자는_한_곳에_있다() -> None:
    """🔴 사본 금지 — `other`·`unknown` 목록을 여러 곳에 적지 않는다."""
    assert "other" in gs.DIM_REASONS and "" in gs.DIM_REASONS
