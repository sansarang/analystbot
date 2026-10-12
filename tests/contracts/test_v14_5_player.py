"""🔴🔴 **§5 선수 점수(플러스마이너스 · 릿지)** — 지시서 2026-10-12(둘째) §5.

> 구간 분할(교체·골 시점) → 응답 = 구간 **(득점−실점)/90분**, 설명 = 구간 출전
> 선수 **±1** → 릿지 회귀. 출전 분 < 300 → 리그·포지션 평균 쪽 수축
> (가중 = 분/(분+K)). 시간 감쇠 가중(§6 ξ).
> 계약 **PL1**: 오늘 경기·이후 경기 정보가 들어가면 실패.
> 계약 **PL2**: 신원 미확정 선수가 **0 으로** 들어가면 실패.
"""
from __future__ import annotations

from datetime import UTC, datetime

AS_OF = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)


def _match(day: str, *, home_ids, away_ids, goals, subs=None) -> dict:
    """🔴 한 경기 — `{utc, home_ids, away_ids, goals:[{min, home}], subs:[…]}`."""
    return {"utc": f"{day}T05:00:00Z", "comp": "league",
            "home_ids": list(home_ids), "away_ids": list(away_ids),
            "goals": list(goals), "subs": list(subs or [])}


def _games() -> list[dict]:
    out = []
    for day in ("2026-08-01", "2026-08-08", "2026-08-15", "2026-08-22",
                "2026-08-29", "2026-09-05"):
        out.append(_match(day, home_ids=["h1", "h2", "h3"],
                          away_ids=["a1", "a2", "a3"],
                          goals=[{"min": 20, "home": True},
                                 {"min": 70, "home": True}]))
    # 🔴 **킥오프 뒤** 경기 — PL1 이 막는다(여기서 a 쪽이 크게 이긴다)
    out.append(_match("2026-10-12", home_ids=["h1"], away_ids=["a1"],
                      goals=[{"min": 10, "home": False},
                             {"min": 20, "home": False},
                             {"min": 30, "home": False}]))
    return out


def test_segments_split_on_goals_and_subs() -> None:
    """🔴 구간은 **교체·골 시점**으로 갈린다."""
    from app.core.ratings import player_pm as pm
    rows = pm.segments(_match("2026-08-01", home_ids=["h1"], away_ids=["a1"],
                              goals=[{"min": 20, "home": True}],
                              subs=[{"min": 60, "out": "h1", "in": "h9",
                                     "home": True}]))
    # 🔴 0~20 · 20~60 · 60~90 → 세 구간
    assert [r["minutes"] for r in rows] == [20, 40, 30], rows
    # 🔴 교체 뒤 구간에는 **들어온 선수**가 있다
    assert "h9" in rows[-1]["home_on"] and "h1" not in rows[-1]["home_on"]


def test_response_is_goal_diff_per_ninety() -> None:
    from app.core.ratings import player_pm as pm
    rows = pm.segments(_match("2026-08-01", home_ids=["h1"], away_ids=["a1"],
                              goals=[{"min": 45, "home": True}]))
    # 🔴 첫 구간(0~45)에서 홈이 한 골 → (1−0)/45분 × 90 = +2.0
    assert abs(rows[0]["y"] - 2.0) < 1e-9, rows[0]


def test_pl1_future_games_never_enter() -> None:
    """🔴🔴 **PL1** — `as_of` 이후 경기는 적합에 **안 들어간다**."""
    from app.core.ratings import player_pm as pm
    got = pm.fit(_games(), as_of=AS_OF, lam=1.0)
    assert got.n_matches == 6, got.n_matches
    # 🔴 뒤 경기에서만 뛴 선수는 **표에 없다**(h9 는 아예 없다)
    assert "h9" not in got.value


def test_naive_as_of_is_refused() -> None:
    import pytest

    from app.core.ratings import player_pm as pm
    with pytest.raises(ValueError):
        pm.fit(_games(), as_of=datetime(2026, 10, 11, 5, 0), lam=1.0)


def test_winning_side_gets_the_higher_score() -> None:
    from app.core.ratings import player_pm as pm
    got = pm.fit(_games(), as_of=AS_OF, lam=1.0)
    assert got.value["h1"] > got.value["a1"], got.value


def test_shrink_for_small_minutes() -> None:
    """🔴 출전 분 < 300 → 평균 쪽으로 **수축**(가중 = 분/(분+K))."""
    from app.core.ratings import player_pm as pm
    got = pm.fit(_games(), as_of=AS_OF, lam=1.0)
    assert got.minutes["h1"] >= 300 or got.shrunk, got.minutes
    raw = got.raw["h1"]
    assert abs(got.value["h1"]) <= abs(raw) + 1e-9


def test_pl2_unknown_player_is_not_zero() -> None:
    """🔴🔴 **PL2** — 모르는 선수는 **0 이 아니라 평균**이고 🔴 가 붙는다."""
    from app.core.ratings import player_pm as pm
    got = pm.fit(_games(), as_of=AS_OF, lam=1.0)
    said, why = pm.value_of("처음보는선수", got)
    assert "🔴" in why
    assert said == got.mean


def test_table_says_its_provenance() -> None:
    from app.core.ratings import player_pm as pm
    got = pm.fit(_games(), as_of=AS_OF, lam=1.0)
    assert got.as_of == AS_OF and "릿지" in got.why
