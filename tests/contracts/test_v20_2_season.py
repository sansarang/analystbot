"""🔴🔴 **§2-1 시즌 표기**(통합 지시서 2026-10-13 밤).

> 모든 경기에 `season_id`(리그 달력 기준: J1 2026/27 **추춘제 전환** · K리그
> **단일 연도** 등 리그별 규칙 표) 부여. 팀별 **"이번 시즌 리그 경기 수"** 를
> `as_of` 기준으로 셀 수 있게.
> 계약 **SE1**: `season_id` 없는 경기가 폼·Elo 계산에 들어가면 **실패**.

🔴 규칙은 **설정 파일 하나**(`config/season_rules.yaml`)다 — 코드에 달력을 박지
   않는다(리그가 달력을 바꾸면 그 파일만 고친다 · J1 이 2026-07 에 바꿨다).
⚠️ 표에 없는 리그는 **빈 글자 + 사유**다(연도를 지어내지 않는다).
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _at(said: str) -> datetime:
    return datetime.fromisoformat(said).replace(tzinfo=UTC)


def test_calendar_league_is_the_year() -> None:
    from app.core import season as se
    got, why = se.id_of(league="league:KL1", when=_at("2026-03-08"))
    assert got == "2026", (got, why)
    assert "단일 연도" in why or "calendar" in why


def test_j1_transition_is_measured_by_the_rule_table() -> None:
    """🔴🔴 J1 — **2026-07 전**은 단일 연도, **그 뒤**는 추춘제다(실측 경계)."""
    from app.core import season as se
    spring, _w1 = se.id_of(league="league:J1", when=_at("2026-02-06"))
    autumn, _w2 = se.id_of(league="league:J1", when=_at("2026-08-07"))
    spring27, _w3 = se.id_of(league="league:J1", when=_at("2027-05-22"))
    assert spring == "2026", spring
    assert autumn == "2026/27", autumn
    assert spring27 == "2026/27", spring27


def test_unknown_league_is_blank_with_a_reason() -> None:
    from app.core import season as se
    got, why = se.id_of(league="league:노리그", when=_at("2026-03-08"))
    assert got == "" and "🔴" in why


def test_se1_guard_names_the_rows() -> None:
    """🔴🔴 **SE1** — `season_id` 없는 줄을 **이름으로** 막는다(조용히 넘기지 않는다)."""
    from app.core import season as se
    rows = [{"utc": "2026-03-08T12:00:00Z", "league": "league:KL1"},
            {"utc": "2026-03-15T12:00:00Z", "league": "league:노리그"}]
    said = se.tag(rows)
    assert said[0]["season_id"] == "2026" and said[1]["season_id"] == ""
    why = se.require(said)
    assert why and "🔴" in why and "1" in why, why
    assert not se.require([said[0]])        # 🔴 전부 있으면 **빈 글자**다


def test_this_season_games_are_counted_before_as_of() -> None:
    """🔴 팀별 **이번 시즌 경기 수** — `as_of` **이전**만(L1)."""
    from app.core import season as se
    rows = [{"utc": "2026-03-01T12:00:00Z", "league": "league:KL1",
             "home": "A", "away": "B"},
            {"utc": "2026-03-08T12:00:00Z", "league": "league:KL1",
             "home": "B", "away": "A"},
            {"utc": "2026-03-15T12:00:00Z", "league": "league:KL1",
             "home": "A", "away": "C"},
            {"utc": "2025-11-01T12:00:00Z", "league": "league:KL1",
             "home": "A", "away": "C"}]
    got, why = se.games_of(rows, team="A", as_of=_at("2026-03-10"),
                           league="league:KL1")
    assert got == 2, (got, why)             # 🔴 03-15 는 뒤 · 2025 는 다른 시즌
    assert "2026" in why
