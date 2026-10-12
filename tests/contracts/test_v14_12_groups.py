"""🔴🔴 **§12 연속 기록 과잉반영 점검**(검증 전용) — 지시서 2026-10-12(둘째) §12.

> 백필 그룹 보정표: `streak_len ≥ 5` · `post_break` · `load_14d ≥ 4` ·
> 신규/승격 팀 · 감독 교체 후 5경기.
> 그룹에서 **구간상 체계적 편향** → 그 변수를 §9 후보로 올려 같은 판정.
> 편향 없음 → **아무것도 안 넣음**.
> 계약 **C12-1**: `streak_len` 이 λ 에 **직접** 들어가면 실패.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _strip(rel: str) -> str:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_c12_1_streak_never_reaches_lambda() -> None:
    """🔴🔴 **C12-1** — λ 를 만드는 코드에 `streak` 이 **없다**."""
    for rel in ("app/core/probfloor.py", "app/core/probmodel.py",
                "app/core/sim.py"):
        said = _strip(rel)
        assert "streak" not in said.lower(), rel


def test_streak_is_not_a_covariate() -> None:
    """🔴 공변량 묶음에도 없다(§7 이 **검증 전용**이라고 적었다)."""
    from datetime import UTC, datetime

    from app.core import context as ctx
    row = ctx.row_of("T", [{"utc": "2026-10-01T05:00:00Z", "comp": "league",
                            "gf": 1, "ga": 0}],
                     as_of=datetime(2026, 10, 11, 5, 0, tzinfo=UTC))
    cov = ctx.covariates(row, row)
    assert not [k for k in cov if "streak" in k]


def test_groups_are_named() -> None:
    """🔴 §12 가 적은 **다섯 그룹**이 이름으로 있다."""
    from app.core import groups as gr
    assert set(gr.GROUPS) == {"streak5", "post_break", "load4", "new_team",
                              "coach_new"}


def test_group_of_tags_a_match() -> None:
    from app.core import groups as gr
    got = gr.group_of({"streak_len": 6, "streak_kind": "패", "load_14d": 2,
                       "pb_home": 0, "new_team": False, "coach_new": False})
    assert "streak5" in got and "load4" not in got


def test_bias_table_uses_the_one_metric() -> None:
    """🔴 보정표는 `metrics.calib` 하나를 쓴다(사본 금지)."""
    said = _strip("app/core/groups.py")
    assert "calib" in said
    from app.core import groups as gr
    rows = [{"p": [0.6, 0.2, 0.2], "hit": 0, "tags": ["streak5"]}
            for _ in range(10)]
    rows += [{"p": [0.6, 0.2, 0.2], "hit": 2, "tags": ["streak5"]}
             for _ in range(10)]
    got = gr.bias(rows)
    assert got["streak5"]["n"] == 20
    # 🔴 예측 60% · 실제 50% → 편향 +0.10(과대평가)
    assert abs(got["streak5"]["bias"] - 0.10) < 1e-9, got


def test_verdict_needs_the_interval_to_exclude_zero() -> None:
    """🔴 §12 조치 규칙 — 구간이 0 을 품으면 **아무것도 안 넣는다**."""
    from app.core import groups as gr
    assert gr.verdict_of({"bias": 0.1, "lo": 0.02, "hi": 0.18}) == "후보로"
    assert gr.verdict_of({"bias": 0.1, "lo": -0.02, "hi": 0.22}) == "그냥 둔다"
