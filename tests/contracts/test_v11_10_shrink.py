"""🔴🔴 **ⓑ 수축 — 같은 판 재료로** (사용자 지시 2026-10-12).

> ⓑ 수축: 수축 표적(`side_index`)을 **같은 판 재료**로 만든다 — 득실판은 보정된
> 득실, xG판은 xG. **생득실 금지.**
> `SIDE_FULL=5` → 가중 **상한 0.5 이하**로(🔴 임시, 백필 적합 전). 수축 전후 값을
> 축1 사유에 적는다.
> 계약: xG판과 득실판의 축1이 소수 셋째 자리까지 같으면 **경고**(한 판만 xG면
> xG판 무효). 레반테–세비야 원정 +0.600 재확인.

🔴 왜 — 실사고 2026-10-12(가와사키–나고야): `side_index` 가 **생득실**로만 만들어져
   `n>=5` 면 가중 100% 로 전체 폼(보정·운 할인·xG)을 **통째로 덮었다**. 그래서
   xG판이 득실판과 소수점까지 같아졌고(레반테–세비야 원정 +0.600), 가와사키 축1 이
   컵 포함 홈 생득실 **1.6** 으로 섰다.
"""
from __future__ import annotations


def _games(n_home: int = 5, *, gf: float, ga: float, xgf: float, xga: float
           ) -> list[dict]:
    """🔴 홈 경기 n 개 — 득실과 xG 가 **서로 다른 말**을 하게 만든다."""
    return [{"side": "home", "gf": gf, "ga": ga, "xgf": xgf, "xga": xga,
             "xg_n": 1, "opp": f"X{i}"} for i in range(n_home)]


def test_cap_is_half_or_less() -> None:
    """🔴 가중 **상한 0.5 이하**(🔴 임시값 · 백필 적합 전)."""
    from app.core import form
    assert form.SIDE_CAP <= 0.5, form.SIDE_CAP


def test_weight_never_exceeds_the_cap() -> None:
    from app.core import form
    got = form.shrink(whole=0.0, side=1.0, n=99)
    assert abs(got - form.SIDE_CAP) < 1e-9, got


def test_goal_board_shrinks_toward_adjusted_goals() -> None:
    """🔴 득실판의 수축 표적은 **보정된 득실**이다(생득실이 아니다)."""
    import inspect

    from app.core import form
    said = inspect.getsource(form.form_of)
    assert "side_adj" in said or "보정된 득실" in said, said[:200]


def test_xg_board_shrinks_toward_xg() -> None:
    """🔴 xG판의 수축 표적은 **xG** 다 — 생득실로 덮이지 않는다."""
    from app.core import form
    rows = [{"gf": 3, "ga": 0, "opp": "X"}] * 5
    games = _games(gf=3, ga=0, xgf=0.8, xga=1.4)
    a = form.form_of("득실", rows, elo={}, games=games, side_at="home")
    b = form.form_of("xG", rows, elo={}, games=games, side_at="home",
                     xg_only=True)
    assert a.index() is not None and b.index() is not None
    # 🔴 득실은 +(3-0), xG 는 −(0.8-1.4) — 수축 뒤에도 **방향이 갈려야** 한다
    assert a.index() > 0 > b.index(), (a.index(), b.index())


def test_two_boards_must_not_be_identical() -> None:
    """🔴 계약 — 소수 셋째 자리까지 같으면 **경고**다(xG판 무효 표시)."""
    from app.core import form
    rows = [{"gf": 3, "ga": 0, "opp": "X"}] * 5
    games = _games(gf=3, ga=0, xgf=0.8, xga=1.4)
    a = form.form_of("득실", rows, elo={}, games=games, side_at="home")
    b = form.form_of("xG", rows, elo={}, games=games, side_at="home",
                     xg_only=True)
    assert round(float(a.index()), 3) != round(float(b.index()), 3)


def test_same_value_raises_the_warning_flag() -> None:
    """🔴 두 판이 같으면 그 사실을 **글자로** 낸다(사람이 보게)."""
    from app.core import form
    said = form.boards_warn(goal=1.234, xg=1.2341)
    assert said and "같다" in said
    assert not form.boards_warn(goal=1.234, xg=0.900)


def test_reason_says_before_and_after() -> None:
    """🔴 *"수축 전후 값을 축1 사유에 적는다"*."""
    from app.core import form
    rows = [{"gf": 2, "ga": 0, "opp": "X"}] * 5
    got = form.form_of("t", rows, elo={}, games=_games(gf=2, ga=0, xgf=1.0,
                                                       xga=1.0),
                       side_at="home")
    assert "수축 전" in got.why and "수축 뒤" in got.why, got.why
