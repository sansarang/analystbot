"""🔴🔴 **1. 가치 없는 선수 — 0 합산 금지** (사용자 지시 2026-10-12).

> 1. 가치 없는 선수: **가치 0 합산 금지**. 대체값 = **같은 리그·같은 포지션 선발
> 선수 가치 중앙값**, 카드에 **"대체값 — 누구" 🔴**.
> 계약: 선발 11명 중 가치 0이 축0 합산에 들어가면 실패.

🔴 왜 — 실측 2026-10-12(가와사키–나고야 ⓓ 감사): 가와사키 선발 11명 중
   `Pedro Romano` 가 **가치 없음**이었고 그대로 **0 으로 합산**됐다. 영입 직후
   선수·하위 리그 출신은 **늘 0** 이 된다(그 팀 축0 이 조용히 깎인다).
"""
from __future__ import annotations


def _p(name: str, pos: str, value: float | None) -> dict:
    return {"name": name, "pos": pos, "value": value}


def test_median_by_position_fills_the_gap() -> None:
    from app.core import playervalue as pv
    rows = [_p("A", "DF", 100.0), _p("B", "DF", 300.0), _p("C", "DF", None),
            _p("D", "FW", 900.0)]
    got, said = pv.fill(rows)
    by = {x["name"]: x for x in got}
    assert by["C"]["value"] == 200.0, by["C"]
    assert by["C"]["filled"] is True
    assert "C" in said and "대체값" in said


def test_zero_is_treated_as_missing() -> None:
    """🔴 `0` 도 **없음**이다 — 0 을 그대로 더하면 그 팀이 깎인다."""
    from app.core import playervalue as pv
    rows = [_p("A", "MF", 100.0), _p("B", "MF", 500.0), _p("C", "MF", 0.0)]
    got, _said = pv.fill(rows)
    assert {x["name"]: x["value"] for x in got}["C"] == 300.0


def test_no_same_position_falls_back_to_all_starters() -> None:
    """⚠️ 같은 포지션이 없으면 **선발 전체 중앙값**으로 간다(사유에 적는다)."""
    from app.core import playervalue as pv
    rows = [_p("A", "DF", 100.0), _p("B", "FW", 300.0), _p("C", "GK", None)]
    got, said = pv.fill(rows)
    assert {x["name"]: x["value"] for x in got}["C"] == 200.0
    assert "포지션" in said


def test_nothing_to_borrow_keeps_none() -> None:
    """🔴 빌릴 값이 아예 없으면 **채우지 않는다**(지어내지 않는다 · #4)."""
    from app.core import playervalue as pv
    rows = [_p("A", "DF", None), _p("B", "FW", None)]
    got, said = pv.fill(rows)
    assert all(x["value"] is None for x in got)
    assert "못 채웠다" in said


def test_axis0_never_sums_a_zero_value() -> None:
    """🔴 계약 — 축0 합산에 **0 이 들어가면 실패**다(코드로 센다)."""
    import ast
    import inspect

    from app.core import backfill, matchup
    for fn in (matchup.axis0, backfill.features):
        said = ast.unparse(ast.parse(inspect.getsource(fn).lstrip()))
        # 🔴 `r["value"]` 를 그대로 더하는 자리가 있으면 0 이 섞인다 →
        #    `playervalue.fill` 을 지나야 한다.
        if "value" in said:
            assert "playervalue" in said or "value_sum" in said, fn.__name__


def test_card_says_who_got_a_filled_value() -> None:
    from app.core import playervalue as pv
    rows = [_p("A", "DF", 100.0), _p("B", "DF", 300.0), _p("C", "DF", None)]
    _got, said = pv.fill(rows)
    assert said.startswith("🔴") and "대체값" in said and "C" in said
