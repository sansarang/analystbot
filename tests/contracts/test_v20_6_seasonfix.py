"""🔴🔴 **§4-2 S2-M1 — 시즌 초 수축**(통합 지시서 2026-10-13 밤).

> 시즌 초 N경기(이번 시즌 리그 경기 수 < 8) 동안 M1 의 팀 간 차이를 리그 평균
> 쪽으로 수축:
>   `log(λ홈/λ원정)_new = s · log(λ홈/λ원정)_M1` ,
>   `s = 1 − k·(1 − mean_retention)·(1 − games/8)`
> 총골 기대 보존(정규화 ±2%) → 격자 재계산. `k` 시즌 교차 적합 · **상한 s ≥ 0.5**.
> 계약 **SF1**: 시즌 **9번째 경기부터 s=1** · **SF2**: 판 없이 적용하면 **실패**.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def test_sf1_after_eight_games_there_is_no_shrink() -> None:
    from app.core import seasonfix as sf
    got, why = sf.s_of(games=8, mean_retention=0.2, k=1.0)
    assert got == 1.0, (got, why)
    said, _w = sf.s_of(games=12, mean_retention=0.0, k=1.0)
    assert said == 1.0
    assert "9번째" in why or "8경기" in why


def test_shrink_is_strongest_at_the_start_and_capped() -> None:
    """🔴 경기 수 0 · 잔류율 0 이면 가장 세게 수축한다 — 그래도 **s ≥ 0.5**."""
    from app.core import seasonfix as sf
    got, _w = sf.s_of(games=0, mean_retention=0.0, k=1.0)
    assert got == 0.5, got                      # 🔴 상한에 눌린다
    mid, _w2 = sf.s_of(games=4, mean_retention=0.5, k=1.0)
    assert 0.5 < mid < 1.0, mid
    high, _w3 = sf.s_of(games=4, mean_retention=1.0, k=1.0)
    assert high == 1.0, high                    # 🔴 전원 잔류면 수축 없다


def test_apply_shrinks_the_ratio_and_keeps_the_total() -> None:
    from app.core import seasonfix as sf
    lam = {"home": 1.8, "away": 1.0}
    got, why = sf.apply(lam, s=0.5)
    import math
    was = math.log(lam["home"] / lam["away"])
    now = math.log(got["home"] / got["away"])
    assert abs(now - 0.5 * was) < 1e-9, (was, now, why)
    assert abs(sum(got.values()) / sum(lam.values()) - 1.0) <= 0.02 + 1e-9
    assert "s 0.500" in why or "s **0.500**" in why


def test_sf2_no_plate_no_shrink() -> None:
    """🔴🔴 **SF2** — `k` 판이 없으면 **수축하지 않는다**(손값 금지)."""
    from app.core import seasonfix as sf
    got, why = sf.plate_of(league="league:J1",
                           as_of=datetime(2000, 1, 1, tzinfo=UTC))
    assert got == {} and "🔴" in why
    lam = {"home": 1.5, "away": 1.2}
    said, why2 = sf.bend(lam, games=2, mean_retention=0.3, plate={})
    assert said == lam and "🔴" in why2 and "판" in why2


def test_bend_uses_the_plate_k() -> None:
    from app.core import seasonfix as sf
    lam = {"home": 1.5, "away": 1.2}
    got, why = sf.bend(lam, games=2, mean_retention=0.0,
                       plate={"k": 0.4})
    assert got != lam and "k 0.4" in why
