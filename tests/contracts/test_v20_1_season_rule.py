"""🔴🔴 **§1 판정 규칙 — (a)~(d)**(통합 지시서 2026-10-13 밤 · 실행 **전** 커밋).

> 채택 = 넷 모두
>   (a) 로그 손실 점추정 < 기준 · 짝지은 차이 구간 하한 < 0
>   (b) 방향 적중률이 기준보다 **낮지 않다**(맥니마 기준 우세 p<0.05 면 탈락)
>   (c) 상위 30/20/10% 선택 적중률 평균 ≥ 기준
>   (d) **의미 크기** — 하나 이상: 로그 손실 개선 ≥ 0.002 · 방향 +0.5%p ·
>       상위 20% +1.0%p
> (a)~(c) 통과·(d) 미달 → **"효과 미미 — 기준 유지"**.

⚠️ 이 (d)는 라인업 지시서의 (d)(**움직이는 폭**)와 **다른 것**이다 — 그래서
   규칙 이름을 가른다(`rule="season"`). 🔴 옛 판정은 그대로 남는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))


def _base() -> dict:
    return {0.30: 0.50, 0.20: 0.50, 0.10: 0.50}


def test_season_rule_needs_all_four() -> None:
    import judge_models as jm
    good = {"diff": {"mean": -0.003, "lo": -0.006, "hi": 0.001},
            "dir_rate": 0.460, "base_dir": 0.457, "p_value": 0.7,
            "bands": _base(), "base_bands": _base(), "rule": "season"}
    ok, box, why = jm.passes(**good, size={"ll": 0.003, "dir": 0.003,
                                           "top20": 0.002})
    assert ok and box == {"a": True, "b": True, "c": True, "d": True}, why


def test_small_effect_is_named_not_adopted() -> None:
    """🔴 (a)~(c) 통과인데 (d) 미달이면 **"효과 미미 — 기준 유지"** 다."""
    import judge_models as jm
    ok, box, why = jm.passes(
        diff={"mean": -0.0005, "lo": -0.001, "hi": 0.0001},
        dir_rate=0.458, base_dir=0.457, p_value=0.9, bands=_base(),
        base_bands=_base(), rule="season",
        size={"ll": 0.0005, "dir": 0.001, "top20": 0.001})
    assert not ok and box["d"] is False
    assert "효과 미미" in why, why


def test_any_one_size_passes_d() -> None:
    """🔴 (d)는 **셋 중 하나**면 된다 — 방향만 +0.5%p 여도 통과."""
    import judge_models as jm
    _ok, box, why = jm.passes(
        diff={"mean": -0.001, "lo": -0.002, "hi": 0.0005},
        dir_rate=0.463, base_dir=0.457, p_value=0.9, bands=_base(),
        base_bands=_base(), rule="season",
        size={"ll": 0.001, "dir": 0.006, "top20": 0.000})
    assert box["d"] is True, why


def test_thresholds_are_the_instruction_numbers() -> None:
    """🔴 문턱은 지시서의 수다(손값을 코드에 흘리지 않는다)."""
    import judge_models as jm
    assert jm.SIZE_LL == 0.002
    assert jm.SIZE_DIR == 0.005
    assert jm.SIZE_TOP20 == 0.010
