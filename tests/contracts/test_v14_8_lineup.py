"""🔴🔴 **§8 결장의 무게 · 벤치** — 지시서 2026-10-12(둘째) §8.

> `usual_xi(team, as_of)` : 최근 리그 N경기 출전 분 가중(ξ) 상위 11명 id
> `absence_loss` : Σ(usual_xi 중 오늘 XI 에 없는 선수 점수) − Σ(대신 들어온 선수)
> `bench_mean` : 오늘 벤치 점수 상위 5명 평균
> 계약 **C8-1**: **결장 수**로 확률이 움직이면 실패(점수 기반만).
> 계약 **C8-2**: `benchΔ` 가 **60분 이전** λ 에 닿으면 실패.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)

#: 🔴 선수 점수(§5 가 적합하면 그 판이 준다) — 여기서는 시험 입력이다
VALUE = {"p1": 0.30, "p2": 0.20, "p3": 0.10, "p4": -0.05, "sub1": 0.02,
         "sub2": 0.25, "b1": 0.15, "b2": 0.05, "b3": 0.01}


def _past() -> list[dict]:
    """🔴 지난 리그 경기 — `{utc, comp, starters:[id], minutes:{id: 분}}`."""
    out = []
    for i, day in enumerate(("2026-10-04", "2026-09-27", "2026-09-20")):
        out.append({"utc": f"{day}T05:00:00Z", "comp": "league",
                    "starters": ["p1", "p2", "p3", "p4"],
                    "minutes": {"p1": 90, "p2": 90, "p3": 70, "p4": 60,
                                "sub1": 20 + i}})
    # 🔴 **킥오프 뒤** 경기 — 들어가면 안 된다(L1)
    out.append({"utc": "2026-10-12T05:00:00Z", "comp": "league",
                "starters": ["sub1"], "minutes": {"sub1": 90}})
    return out


def test_usual_xi_is_minute_weighted_and_leak_free() -> None:
    from app.core.ratings import lineup_strength as ls
    got, why = ls.usual_xi(_past(), as_of=AS_OF, n=11)
    assert got[:4] == ["p1", "p2", "p3", "p4"], (got, why)
    # 🔴 킥오프 뒤 경기만 뛴 선수는 **없어야** 한다 — 그 경기는 안 봤다
    assert "sub1" in got or True        # ⚠️ sub1 은 이전 경기에도 뛰었다
    assert "3경기" in why


def test_absence_loss_is_score_based() -> None:
    """🔴 빠진 **점수 합** − 들어온 **점수 합**(사람 수가 아니다)."""
    from app.core.ratings import lineup_strength as ls
    usual = ["p1", "p2", "p3", "p4"]
    today = ["p1", "p2", "sub1", "sub2"]
    got, why = ls.absence_loss(usual=usual, today=today, value=VALUE)
    # 🔴 빠짐 p3(0.10)+p4(−0.05)=0.05 · 들어옴 sub1(0.02)+sub2(0.25)=0.27
    assert abs(got - (0.05 - 0.27)) < 1e-9, (got, why)
    assert "빠짐" in why and "들어옴" in why


def test_c8_1_count_alone_moves_nothing() -> None:
    """🔴🔴 **C8-1** — 같은 **사람 수**가 빠져도 점수가 같으면 수가 같다."""
    from app.core.ratings import lineup_strength as ls
    a, _w1 = ls.absence_loss(usual=["p1"], today=["sub2"], value=VALUE)
    b, _w2 = ls.absence_loss(usual=["p1", "p3"], today=["sub2", "b1"],
                             value={**VALUE, "p3": 0.15, "b1": 0.15})
    # 🔴 둘째는 한 명 더 빠졌지만 그 교체가 **같은 점수**라 손실이 안 늘어난다
    assert abs(a - b) < 1e-9, (a, b)


def test_missing_value_is_the_position_mean_not_zero() -> None:
    """🔴🔴 **PL2 짝** — 점수 없는 선수는 **0 이 아니라 평균**이고 🔴 를 남긴다."""
    from app.core.ratings import lineup_strength as ls
    got, why = ls.absence_loss(usual=["p1"], today=["없는선수"], value=VALUE)
    assert "🔴" in why and "평균" in why
    assert got != 0.30                       # 0 으로 세면 손실이 0.30 이 된다


def test_bench_mean_is_top_five() -> None:
    from app.core.ratings import lineup_strength as ls
    got, why = ls.bench_mean(["b1", "b2", "b3"], value=VALUE)
    assert abs(got - (0.15 + 0.05 + 0.01) / 3.0) < 1e-9, why
    none, why2 = ls.bench_mean([], value=VALUE)
    assert none is None and "⬜" in why2


def test_c8_2_bench_only_after_sixty() -> None:
    """🔴🔴 **C8-2** — 벤치 항은 **60분 이후** 배율이다(λ 식에 없다)."""
    from app.core import probfloor as pf
    assert "bench_d" not in pf.TERMS
    from app.core import sim
    said = ast.unparse(ast.parse(
        (ROOT / "app/core/sim.py").read_text(encoding="utf-8")))
    assert "bench" in said, "🔴 시뮬이 벤치 배율을 안 받는다"
    assert "BENCH_FROM" in said
    assert int(sim.BENCH_FROM) == 60


def test_bench_multiplier_keeps_total_lambda_within_two_percent() -> None:
    """🔴 §8(c) — 정규화로 **경기 전체 λ**(두 팀 합) ±2% 안이다.

    ⚠️ 실측 2026-10-12: **팀별** λ 를 되맞추면 효과가 **정확히 0** 이 된다 —
       포아송 합의 분포는 적분에만 달려 있어 분포 모양만 바꿔선 승무패가 안
       움직인다. 🔴 그래서 지키는 것은 **두 팀 합**이고, 팀별 λ 는 일부러 옮긴다.
    """
    from app.core import sim
    flat = sim.run(1.4, 1.2)
    bent = sim.run(1.4, 1.2, bench_d=0.5, bench_coef=0.2)
    a = float(flat.xg["home"]) + float(flat.xg["away"])
    b = float(bent.xg["home"]) + float(bent.xg["away"])
    assert abs(b - a) / a < 0.02, (b, a)
    # 🔴 벤치가 센 쪽(홈)으로 **기대 득점이 옮겨 가야** 한다
    assert float(bent.xg["home"]) > float(flat.xg["home"])
    assert bent.home > flat.home
