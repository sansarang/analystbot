"""🔴🔴 **§1 평가 지표** — 지시서 2026-10-12(엔진 교체) §1.

> 주지표: **로그 손실**. 병기: RPS · 방향 적중률 · 상위 30/20/10% 선택 적중률
> (같은 경기 수) · 브라이어(참고). 비교는 전부 **짝지은 차이 + 부트스트랩 95%**.
> 평가 표본: 적합은 시즌 A, 평가는 시즌 B — **그리고 반대**(교차).
> **같은 데이터로 적합·평가한 수는 보고 금지.**
> 판정 규칙(고정): 후보가 기준보다 로그 손실 **구간상** 낫다 → 채택. 구간이 0을
> 품는다 → **단순한 쪽 유지**. 나쁘다 → 폐기.
> 계약 **E1**: 적합 기간과 평가 기간이 겹치면 **실패**.
"""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════
# 지표 자체
# ══════════════════════════════════════════════════════════════════

def test_rps_is_ordered() -> None:
    """🔴 RPS — **순서를 아는** 점수다(무를 틀린 것보다 홈/원정을 틀린 것이 나쁘다)."""
    from app.core import metrics as m
    near = m.rps([0.2, 0.5, 0.3], 1)        # 무가 났는데 무를 높게 봤다
    far = m.rps([0.8, 0.1, 0.1], 2)         # 원정이 났는데 홈을 높게 봤다
    assert near < far, (near, far)
    assert abs(m.rps([1.0, 0.0, 0.0], 0)) < 1e-9


def test_logloss_and_brier() -> None:
    from app.core import metrics as m
    assert abs(m.logloss([0.5, 0.25, 0.25], 0) - math.log(2)) < 1e-9
    assert abs(m.brier([1.0, 0.0, 0.0], 0)) < 1e-9


def test_paired_diff_gives_a_bootstrap_interval() -> None:
    """🔴 비교는 **짝지은 차이**다 — 같은 경기에서 둘의 손실을 뺀다."""
    from app.core import metrics as m
    got = m.paired([0.6] * 40, [0.7] * 40)
    assert got["mean"] < 0 and got["lo"] <= got["mean"] <= got["hi"]
    assert got["n"] == 40


def test_verdict_rule_is_fixed() -> None:
    """🔴🔴 판정 규칙(고정) — 구간이 0을 품으면 **단순한 쪽**이다."""
    from app.core import metrics as m
    assert m.verdict_of({"mean": -0.01, "lo": -0.02, "hi": -0.004}) == "채택"
    assert m.verdict_of({"mean": -0.01, "lo": -0.03, "hi": +0.01}) == "유지"
    assert m.verdict_of({"mean": +0.02, "lo": +0.01, "hi": +0.03}) == "폐기"


def test_bands_use_the_same_count() -> None:
    """🔴 선택 적중률은 **같은 경기 수**로 견준다."""
    from app.core import metrics as m
    rows = [{"a": [0.9, 0.05, 0.05], "b": [0.4, 0.3, 0.3], "hit": 0}
            for _ in range(10)]
    got = m.bands(rows, keys=("a", "b"))
    for frac, box in got.items():
        assert box["a"]["n"] == box["b"]["n"], (frac, box)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **E1** — 적합 기간과 평가 기간이 겹치면 실패
# ══════════════════════════════════════════════════════════════════

def test_e1_overlap_is_refused() -> None:
    from app.core import metrics as m
    import pytest
    with pytest.raises(ValueError):
        m.check_split(fit={"2025", "2026"}, eval={"2026"})
    assert m.check_split(fit={"2025"}, eval={"2026"}) == ""


def test_e1_is_enforced_in_the_judge_tool() -> None:
    """🔴 도구가 **그 문**을 지난다(글자로 센다 · 사본 금지)."""
    said = (ROOT / "tools/judge_models.py").read_text(encoding="utf-8")
    assert "check_split" in said, said[:200]


def test_subgroup_calibration_table() -> None:
    """🔴 §1 — 하위 그룹 보정표(그룹별 **평균 예측 − 실제**, 구간)."""
    from app.core import metrics as m
    rows = [{"p": [0.5, 0.25, 0.25], "hit": 0, "g": "x"} for _ in range(20)]
    rows += [{"p": [0.5, 0.25, 0.25], "hit": 2, "g": "x"} for _ in range(20)]
    got = m.calib(rows, group="g", side=0)
    assert got["x"]["n"] == 40
    # 🔴 예측 50% · 실제 50% → 편향 0
    assert abs(got["x"]["bias"]) < 1e-9
    assert got["x"]["lo"] <= got["x"]["bias"] <= got["x"]["hi"]
