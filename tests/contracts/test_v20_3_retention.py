"""🔴🔴 **§2-4 선수단 잔류율**(통합 지시서 2026-10-13 밤).

> 지난 시즌 팀 리그 출전 분 중, `as_of` 시점 **이번 시즌 그 팀 출전 기록**(또는
> 명단)에 있는 선수의 **분 비율** = `retention ∈ [0,1]`.
> 승격팀: 지난 시즌 **하위 리그** 출전 분 기준으로 같은 계산 + **승격 표시**.
> 분 자료: 확보한 `playerStats` `minutes_played`(703/704) · 지난 시즌 자료 없으면 ⬜.
> 계약 **RT1**: **이번 시즌 이후** 경기 정보로 잔류 판정하면 **실패**(L1).
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _m(day: str, *, home: str, away: str, mins: dict) -> dict:
    """🔴 한 경기 — `mins` 는 `{선수: 분}`(홈 쪽만 쓰는 시험용 꼴)."""
    return {"utc": f"{day}T12:00:00Z", "league": "league:KL1",
            "home": home, "away": away,
            "home_minutes": dict(mins), "away_minutes": {}}


def test_retention_is_the_minutes_share() -> None:
    from app.core.ratings import retention as rt
    rows = [_m("2025-05-01", home="A", away="B",
               mins={"p1": 90.0, "p2": 90.0, "p3": 90.0}),
            # 🔴 이번 시즌 — p1·p2 만 뛰었다 → 잔류 분 180/270 = **0.667**
            _m("2026-03-01", home="A", away="B", mins={"p1": 90.0}),
            _m("2026-03-08", home="A", away="B", mins={"p2": 90.0})]
    got, why = rt.of(rows, team="A", as_of=datetime(2026, 3, 20, tzinfo=UTC),
                     league="league:KL1")
    assert got is not None and abs(got - 2 / 3) < 1e-9, (got, why)
    assert "2025" in why and "2026" in why


def test_rt1_future_matches_cannot_decide_retention() -> None:
    """🔴🔴 **RT1** — `as_of` **뒤** 경기로 잔류를 판정하면 수가 달라진다(막는다)."""
    from app.core.ratings import retention as rt
    rows = [_m("2025-05-01", home="A", away="B",
               mins={"p1": 90.0, "p2": 90.0}),
            _m("2026-03-01", home="A", away="B", mins={"p1": 90.0}),
            # ⚠️ 이 경기는 `as_of` **뒤**다 — p2 가 여기서 뛰지만 **세지 않는다**
            _m("2026-09-01", home="A", away="B", mins={"p2": 90.0})]
    got, _why = rt.of(rows, team="A", as_of=datetime(2026, 3, 20, tzinfo=UTC),
                      league="league:KL1")
    assert got is not None and abs(got - 0.5) < 1e-9, got


def test_no_last_season_is_blank_not_zero() -> None:
    """⚠️ 지난 시즌 자료가 없으면 **⬜(None)** 이다 — 0 으로 적지 않는다."""
    from app.core.ratings import retention as rt
    rows = [_m("2026-03-01", home="A", away="B", mins={"p1": 90.0})]
    got, why = rt.of(rows, team="A", as_of=datetime(2026, 3, 20, tzinfo=UTC),
                     league="league:KL1")
    assert got is None and ("⬜" in why or "🔴" in why), why
    assert "승격" in why or "지난 시즌" in why


def test_promoted_is_named() -> None:
    """🔴 이번 시즌에만 있는 팀은 **승격(또는 새 팀)** 이라고 적는다."""
    from app.core.ratings import retention as rt
    rows = [_m("2025-05-01", home="X", away="Y", mins={"q": 90.0}),
            _m("2026-03-01", home="A", away="B", mins={"p1": 90.0})]
    _got, why = rt.of(rows, team="A", as_of=datetime(2026, 3, 20, tzinfo=UTC),
                      league="league:KL1")
    assert "승격" in why, why
