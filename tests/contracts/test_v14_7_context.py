"""🔴🔴 **§7 경기 직전 상태** — 지시서 2026-10-12(둘째) §7.

> `ContextRow{team_id, as_of — 전부 before_as_of, 리그+컵+대표팀 차출 기간 포함
>   rest_days(직전 공식 경기 → 킥오프) · load_14d · cup_4d · break_days ·
>   league_n_since_break · travel_km(없으면 ⬜) · form3 · streak_len·kind}`
> Covariates: `restΔ = clip(rest,0,10) 차` · `loadΔ` · `cupΔ` · `pb_home` ·
> `form3Δ`.
> 계약 **C7-1**: 킥오프 이후 경기 포함 시 실패. **C7-2**: 컵 경기를 빼고 rest 를
> 세면 실패.
"""
from __future__ import annotations

from datetime import UTC, datetime

KICK = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)


def _rows() -> list[dict]:
    """🔴 그 팀의 지난 경기 — `{utc, comp_kind, gf, ga}`(어댑터 꼴 하나)."""
    return [
        # 🔴 3일 전 **컵** 경기(여기서 rest 를 세야 한다 — C7-2)
        {"utc": "2026-10-08T10:00:00Z", "comp": "cup", "gf": 1, "ga": 0},
        # 리그 경기들
        {"utc": "2026-10-04T05:00:00Z", "comp": "league", "gf": 2, "ga": 2},
        {"utc": "2026-09-27T05:00:00Z", "comp": "league", "gf": 0, "ga": 1},
        {"utc": "2026-09-20T05:00:00Z", "comp": "league", "gf": 3, "ga": 0},
        # 🔴 **킥오프 뒤** 경기 — C7-1 이 막는다
        {"utc": "2026-10-12T05:00:00Z", "comp": "league", "gf": 9, "ga": 0},
    ]


def test_rest_counts_the_cup_game() -> None:
    """🔴🔴 **C7-2** — 직전 **공식** 경기부터 센다(컵을 빼지 않는다)."""
    from app.core import context as ctx
    got = ctx.row_of("T", _rows(), as_of=KICK)
    assert got.rest_days == 3, got            # 10-08 → 10-11
    assert got.cup_4d is True, got            # 4일 안에 컵이 있었다
    # ⚠️ 리그만 봤다면 10-04 → 7일이 된다 — 그 수가 나오면 틀린 것이다
    assert got.rest_days != 7


def test_c7_1_future_games_never_enter() -> None:
    """🔴🔴 **C7-1** — 킥오프 이후 경기는 **하나도** 안 들어간다."""
    from app.core import context as ctx
    got = ctx.row_of("T", _rows(), as_of=KICK)
    assert got.n_used == 4, got.n_used
    assert got.load_14d == 3, got             # 09-27 은 14일 밖이다


def test_naive_as_of_is_refused() -> None:
    import pytest

    from app.core import context as ctx
    with pytest.raises(ValueError):
        ctx.row_of("T", _rows(), as_of=datetime(2026, 10, 11, 5, 0))


def test_break_days_and_since_break() -> None:
    """🔴 `break_days` 는 **직전 리그** 경기부터다(휴식기 감지)."""
    from app.core import context as ctx
    rows = [{"utc": "2026-09-20T05:00:00Z", "comp": "league",
             "gf": 1, "ga": 1}]
    got = ctx.row_of("T", rows, as_of=KICK)
    assert got.break_days == 21 and got.league_n_since_break == 0


def test_form3_is_three_league_games() -> None:
    """🔴 `form3` — 최근 리그 **3경기 승점**(수축)."""
    from app.core import context as ctx
    got = ctx.row_of("T", _rows(), as_of=KICK)
    # 🔴 리그 3경기: 2-2(무 1) · 0-1(패 0) · 3-0(승 3) = 4점 / 9
    assert abs(got.form3 - 4.0 / 9.0) < 1e-9, got.form3


def test_covariates_are_home_minus_away() -> None:
    """🔴 Δ 는 **홈 − 원정**이고 rest 는 0~10 으로 자른다."""
    from app.core import context as ctx
    home = ctx.row_of("H", [{"utc": "2026-09-01T05:00:00Z", "comp": "league",
                             "gf": 1, "ga": 0}], as_of=KICK)
    away = ctx.row_of("A", _rows(), as_of=KICK)
    cov = ctx.covariates(home, away)
    # 🔴 홈은 40일 쉬었지만 **10 으로 자른다** → 10 − 3 = 7
    assert cov["rest_d"] == 7, cov
    assert cov["load_d"] == 0 - 3, cov
    assert cov["cup_d"] == 0 - 1, cov
    # 🔴 `pb_home` — 홈이 휴식기 뒤 첫 리그 경기다
    assert cov["pb_home"] == 1, cov


def test_streak_is_verification_only() -> None:
    """🔴 `streak_len` 은 **검증 전용**이다 — 공변량에 없다(계약 C12-1 의 짝)."""
    from app.core import context as ctx
    home = ctx.row_of("H", _rows(), as_of=KICK)
    cov = ctx.covariates(home, home)
    assert "streak" not in " ".join(cov)
    assert home.streak_kind in ("승", "무", "패", "")


def test_travel_is_unknown_without_a_table() -> None:
    """⚠️ 구장 좌표 표가 없으면 `travel_km` 은 **⬜**(지어내지 않는다)."""
    from app.core import context as ctx
    got = ctx.row_of("T", _rows(), as_of=KICK)
    assert got.travel_km is None and "⬜" in got.why
