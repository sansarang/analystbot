"""🔴🔴 **(가) 라인업은 확률에 넣지 않고 카드 표시·검증만**(사용자 결정 2026-10-13 밤).

> 둘 다 실패 → (가): 라인업은 확률에 넣지 않고 **카드 표시·검증만**.
> **L9 값**과 **"평소 대비 공격 기여 −X%"** 를 카드에 적는다.

🔴 왜 (가)로 끝났나 — 세 판 모두 판정을 못 넘었다:
| 재료 | 판 | 왜 떨어졌나 |
|---|---|---|
| 구간 ±(`player_pm`) | `B+L1` | (a)(b)(c)는 통과했지만 폭 **0.12%p · ≥3%p 0건**((d) 전 판정) |
| 박스 기록 L6(오늘 합) | `B+L6` | 폭 2.42%p 인데 **선택 적중 ↓**(55.0→52.9) · 넓은 구간 방향 45.5<46.0 |
| 박스 기록 L9(오늘−평소) | `B+L9` | 폭 1.49%p · 축0 상관 **0.000**(깨끗하다) · 🔴 그런데 로그 손실 **+0.0010** 이고 ≥3%p 66경기 방향 **37.9% ≪ 45.5%** |

🔴 **그래서 λ 에 안 건다.** 표시는 하되 **확률 경로와 닿는 곳이 0** 이어야 한다 —
   이 계약이 그 자리를 센다(X1·X2 와 같은 종류의 잠금).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _code(rel: str) -> str:
    """🔴 **D46** — 독스트링을 뺀 코드만 본다(문서가 설명하는 것과 부르는 것은 다르다)."""
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_view_is_computed_and_named() -> None:
    """🔴 `lineupfix.view_of` — **L9 와 평소 대비 %** 를 낸다(표시용)."""
    from app.core import lineupfix as lf
    box = {"value": {"a": 1.0, "b": 0.4, "x": 0.5, "y": 0.5},
           "kind": {k: "공격" for k in ("a", "b", "x", "y")}}
    got, why = lf.view_of(home={"xi": ["b"], "usual": ["a", "b"], "bench": []},
                          away={"xi": ["x", "y"], "usual": ["x", "y"],
                                "bench": []}, box=box)
    # 🔴 홈은 평소 1.4 중 0.4 만 나왔다 → **−71%**
    assert round(got["home_pct"]) == -71, got
    assert round(got["away_pct"]) == 0, got
    assert abs(got["L9"] - (0.4 - 1.4)) < 1e-9, got
    assert "평소 대비" in why


def test_view_says_when_it_cannot() -> None:
    """⚠️ 판·평소 XI 가 없으면 **미산출 + 사유**다(0 으로 메우지 않는다 · #3)."""
    from app.core import lineupfix as lf
    got, why = lf.view_of(home={"xi": ["a"], "usual": [], "bench": []},
                          away={"xi": ["b"], "usual": [], "bench": []},
                          box={})
    assert got == {} and "🔴" in why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **잠금 — 표시가 확률에 닿지 않는다**
# ══════════════════════════════════════════════════════════════════

def test_probability_path_never_reads_the_view() -> None:
    """🔴 ⑯·λ·격자·시뮬 어디에도 `lineup_view`·`view_of`·`lineupfix` 가 **없다**."""
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/sim.py"):
        said = _code(rel)
        for bad in ("lineup_view", "view_of", "lineupfix"):
            assert bad not in said, (rel, bad)


def test_pipeline_carries_the_view_only_as_display() -> None:
    """🔴🔴 파이프라인은 그 수를 **카드 칸에만** 싣는다.

    ⚠️ 운반은 필요하다(카드가 받아야 한다) — 그래서 **어디에 싣는지**를 센다:
       `lineup_view` 는 **`model_copy` 로 ② 칸을 고치는 자리**에서만 나오고,
       ⑯(`probmodel.run`)의 인자에는 **없다**.
    """
    tree = ast.parse(_code("app/core/pipeline.py"))
    ok = bad = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        said = ast.unparse(node)
        if "lineup_view" not in said:
            continue
        if "model_copy" in ast.unparse(node.func) + said[:40]:
            ok += 1
        else:
            bad += 1
    assert ok >= 1, "🔴 표시 칸에 싣는 자리가 없다"
    # 🔴 ⑯ 의 인자에 그 수가 **없다**
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and ast.unparse(node.func).endswith((".run", "probmodel.run"))
                and "floor=" in ast.unparse(node)):
            assert "lineup_view" not in ast.unparse(node), ast.unparse(node)


def test_correction_is_not_wired() -> None:
    """🔴 `lineupfix.apply`(λ 보정)를 **운영 코드가 부르지 않는다**(판정 탈락)."""
    hits = []
    for path in (ROOT / "app").rglob("*.py"):
        said = _code(str(path.relative_to(ROOT)))
        if "lineupfix.apply" in said or ".apply(lam" in said:
            hits.append(str(path))
    assert not hits, f"🔴 보정이 운영에 이어졌다: {hits}"


def test_card_prints_the_lineup_line() -> None:
    """🔴 카드가 그 줄을 적는다 — 못 쟀으면 **미산출**이라고 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "평소 대비 공격 기여" in said
    assert "라인업 표시 미산출" in said
