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

KINDS = {"domestic_league", "domestic_cup", "club_continental",
         "national_friendly"}


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


def test_the_league_cup_is_registered() -> None:
    """🔴 운영이 **실제로 분석한 대회**가 표에 있다(실측 2026-10-13 · `League Cup`).

    ⚠️ 그 경기는 `league:fotmob224` 로 **자동 등록**됐고 카드 머리가 `League Cup`
       이라고 적었다 — 유형이 없으면 CP1 이 막는다.
    """
    from app.core import competition as cp
    one = dict(cp.rows().get("league:JLC") or {})
    assert one.get("kind") == "domestic_cup", one
    assert list((one.get("sources") or {}).get("fotmob_ids") or []) == [224]
    # 🔴 운영은 **fotmob 리그 id** 를 들고 온다 → 그 길로 손 표가 먼저 잡힌다
    got, _why = cp.key_of(league_id=224)
    assert got == "league:JLC", got
    # ⚠️ **이름만**(`League Cup`)으로는 손 표가 안 잡는다 — 나라마다 같은 이름이
    #    있어 그 매칭은 **일부러 좁다**(자동 등록 기록으로 떨어진다 · 실측).
    said, why2 = cp.key_of(competition="League Cup")
    assert said in ("league:JLC", "league:fotmob224"), (said, why2)
    # 🔴 고유한 이름은 잡는다
    assert cp.key_of(competition="YBC Levain")[0] == "league:JLC"


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
