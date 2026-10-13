"""🔴🔴 **§5-0 대회 유형 표 · §5-1 준비 점검**(지시서 2026-10-13 밤 셋째).

> 대회마다 `kind` 를 고정: `domestic_league` · `club_continental` ·
> `national_friendly`. 필드: 이름·fotmob id·kind·대륙·단판/홈앤어웨이·중립 규칙·
> 포함 시즌. 계약 **CP1**: `kind` 없는 대회는 **분석하지 않는다**
> (🔴 "대회 유형 미등록").

🔴 fotmob id 는 **받아서 확인했다**(2026-10-13): 42 `Champions League` ·
   525 `AFC Champions League Elite` · 9469 `AFC Champions League Two`.
⚠️ 친선은 **대회 id 로 가리지 않는다** — `comp_kind(national=, friendly=)` 다.
"""
from __future__ import annotations

KINDS = {"domestic_league", "club_continental", "national_friendly"}


def test_every_row_has_a_kind() -> None:
    from app.core import competition as cp
    bad = [k for k, v in cp.rows().items()
           if str(dict(v).get("kind") or "") not in KINDS]
    assert not bad, f"🔴 `kind` 가 없거나 모르는 대회: {bad}"


def test_the_five_new_competitions_are_registered() -> None:
    from app.core import competition as cp
    rows = cp.rows()
    for key, kind, ids in (("league:ELC", "domestic_league", [48]),
                           ("league:UCL", "club_continental", [42]),
                           ("league:ACLE", "club_continental", [525]),
                           ("league:ACL2", "club_continental", [9469]),
                           ("national_friendly", "national_friendly", [])):
        one = dict(rows.get(key) or {})
        assert one, f"🔴 `{key}` 가 표에 없다"
        assert one.get("kind") == kind, (key, one.get("kind"))
        assert list((one.get("sources") or {}).get("fotmob_ids") or []) == ids


def test_cp1_unknown_competition_is_refused() -> None:
    """🔴🔴 **CP1** — `kind` 를 모르는 대회는 **분석하지 않는다**."""
    from app.core import competition as cp
    got, why = cp.kind_require("league:J1")
    assert got == "domestic_league" and "🔴" not in why
    bad, why2 = cp.kind_require("league:없는리그")
    assert bad == "" and "대회 유형 미등록" in why2


def test_continental_rows_carry_format_and_seasons() -> None:
    """🔴 단판·홈앤어웨이·중립 규칙과 포함 시즌이 **표에** 있다(코드에 없다)."""
    from app.core import competition as cp
    for key in ("league:UCL", "league:ACLE", "league:ACL2"):
        one = dict(cp.rows().get(key) or {})
        box = dict(one.get("format") or {})
        assert box.get("stage_single") and box.get("why"), key
        assert "two_legs" in box and "neutral" in box, key
        assert len(list(one.get("seasons") or [])) >= 2, key
        assert one.get("confederation") in ("UEFA", "AFC"), key


def test_neutral_rule_is_readable_from_the_table() -> None:
    """🔴 **CC3 의 재료** — 중립 경기 규칙을 표에서 읽는다(손값 금지)."""
    from app.core import competition as cp
    got, why = cp.neutral_of("league:UCL", stage="Final")
    assert got is True, why
    said, why2 = cp.neutral_of("league:UCL", stage="League phase")
    assert said is False, why2
    none, why3 = cp.neutral_of("league:없는리그", stage="Final")
    assert none is None and "🔴" in why3
