"""🔴🔴 **2. 홈 이점 이중 계산 감사**(사용자 지시 2026-10-12).

> (a) ⓑ 수축이 홈팀=홈 경기 폼으로 당길 때 그 폼에 **홈 이점이 이미 들어 있는가**
>     → λ 홈 배율과 겹치는지 수식으로 보고. 겹치면 쪽 폼에서 **리그 홈/원정 평균
>     차를 빼고(중심화)** 수축한다.
> (b) λ 기준: "한 팀 평균"이 **한 값**인지, **원정 λ 에 원정 배율**이 들어가는지.

🔴 감사 결과(실측 2026-10-12):
  · `lam_h = per_team × (home_share/per_team) = home_share` ✅
  · `lam_a = per_team` ❌ — **원정 배율이 없다**. 라리가 per_team 1.3444 ·
    home_share 1.5296 → away_share 1.1592 인데 1.3444 를 써서 **+16% 과대**.
  · 쪽 폼(홈팀=홈 경기)에는 홈 이점 Δ = home_share − away_share 가 **이미** 들어
    있다 → exp(β×종합)과 λ 홈 배율이 **겹친다**(이중 계산).
"""
from __future__ import annotations


def test_away_lambda_uses_the_away_share() -> None:
    """🔴 (b) — 원정 λ 는 **원정 몫**이다(한 팀 평균이 아니다)."""
    from app.core import probmodel as pm
    got, why = pm.away_mul(home_share=1.5296, per_team=1.3444)
    # 🔴 away_share = 2×per_team − home_share = 1.1592 → 배율 0.8623
    assert abs(got - (1.1592 / 1.3444)) < 1e-6, (got, why)
    assert "원정 몫" in why


def test_away_mul_is_one_when_no_measurement() -> None:
    """⚠️ 실측이 없으면 **1.0**(다른 대회에서 빌리지 않는다)."""
    from app.core import probmodel as pm
    got, why = pm.away_mul(home_share=None, per_team=1.3)
    assert got == 1.0 and ("없다" in why or "⬜" in why)


def test_lambda_code_applies_both_multipliers() -> None:
    """🔴 λ 식에 **홈·원정 배율이 둘 다** 들어간다."""
    import inspect

    from app.core import probmodel as pm
    said = inspect.getsource(pm.run)
    assert "lam_a = mean * mul_a" in said.replace("  ", " "), said[:1]


def test_side_form_is_centered() -> None:
    """🔴 (a) — 쪽 폼에서 **리그 홈/원정 평균 차를 뺀다**(중심화)."""
    from app.core import form
    rows = [{"gf": 2, "ga": 1, "opp": "X"}] * 5
    games = [{"side": "home", "gf": 2, "ga": 1, "opp": f"X{i}"}
             for i in range(5)]
    plain = form.form_of("t", rows, elo={}, games=games, side_at="home")
    mid = form.form_of("t", rows, elo={}, games=games, side_at="home",
                       side_center=0.37)
    assert plain.side_index is not None and mid.side_index is not None
    # 🔴 홈 쪽은 Δ 만큼 **내려간다**(그 이점은 λ 홈 배율이 이미 센다)
    assert abs(plain.side_index - mid.side_index - 0.37) < 1e-6, (
        plain.side_index, mid.side_index)


def test_away_side_is_centered_the_other_way() -> None:
    from app.core import form
    rows = [{"gf": 1, "ga": 1, "opp": "X"}] * 5
    games = [{"side": "away", "gf": 1, "ga": 1, "opp": f"X{i}"}
             for i in range(5)]
    mid = form.form_of("t", rows, elo={}, games=games, side_at="away",
                       side_center=0.37)
    plain = form.form_of("t", rows, elo={}, games=games, side_at="away")
    # 🔴 원정 쪽은 Δ 만큼 **올라간다**
    assert abs(mid.side_index - plain.side_index - 0.37) < 1e-6


def test_center_is_reported() -> None:
    from app.core import form
    rows = [{"gf": 2, "ga": 1, "opp": "X"}] * 5
    games = [{"side": "home", "gf": 2, "ga": 1, "opp": f"X{i}"}
             for i in range(5)]
    got = form.form_of("t", rows, elo={}, games=games, side_at="home",
                       side_center=0.37)
    assert "중심화" in got.why


def test_center_comes_from_the_measured_baseline() -> None:
    """🔴 Δ 는 **실측**에서 온다(감으로 적지 않는다)."""
    from app.core import probmodel as pm
    got, why = pm.side_center(home_share=1.5296, per_team=1.3444)
    assert abs(got - (1.5296 - 1.1592)) < 1e-6, (got, why)
    assert pm.side_center(home_share=None, per_team=1.3)[0] == 0.0
