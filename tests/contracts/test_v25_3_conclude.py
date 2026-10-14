"""🔴🔴 **보드 없음 결론 규칙 (가)** — 사용자 결정 2026-10-13(갈림길 답).

> 갈림길 답 = (가). 카드 결론 줄에 박는다(`⏸ 보류 — 보드가 없다` 삭제).
> 등급 상한(조건부)은 그대로 적용. 이 규칙을 v6 §7 에 기록 · 계약 테스트 추가.

🔴 **CL1** 구간 밖 → **접는다** · **CL2** 구간 안 + 상한 조건부 → **조건부** ·
   **CL3** 구간 안 + 상한 없음 → **간다** · **CL4** 확률 없으면 결론 없음(⬜) ·
   **CL5** 옛 글자(`보류 — 보드가 없다`)가 **코드에 없다** · **CL6** v6 §7 문서에
   기록돼 있다 · **CL7** 이 규칙에 **시장·배당이 닿지 않는다**.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


#: 🔴🔴 **백필이 아직 안 끝난 대회**(CL2 의 예시 자리).
#:
#:  ⚠️ 전에는 `league:ACLE` 이 이 자리였다 — 2026-10-14 에 그 대회를 **310경기로
#:     적합해서** 상한이 풀렸고(`간다`) 이 계약이 빨개졌다. 🔴 규칙은 그대로다 —
#:     **예시가 낡았다**. 그래서 아직 적합이 없는 대회로 바꾼다.
#:  🔴 이 대회도 적합되면 또 빨개진다 — 그때 **적합 없는 대회로 다시 바꾼다**
#:    (`app.rules.base_model(키)` 가 비는 대회를 고른다). 그것이 이 계약이 사는 법이다.
NO_FIT = "league:ACL2"


def test_예시_대회가_정말_적합이_없다() -> None:
    """🔴 아래 두 계약이 쓰는 예시가 **여전히 적합 없는 대회**인가."""
    from app import rules
    assert not rules.base_model(NO_FIT), (
        f"`{NO_FIT}` 가 적합됐다 — `NO_FIT` 을 적합 없는 대회로 바꿔라")


def test_cl1_outside_the_band_folds() -> None:
    from app.core import conclude
    pick, why = conclude.of(0.422, kind=NO_FIT)
    assert pick == "접는다" and "구간 밖" in why, why


def test_cl2_inside_with_cap_is_conditional() -> None:
    from app.core import conclude
    pick, why = conclude.of(0.523, kind=NO_FIT)
    assert pick == "조건부" and "백필 미완" in why, why


def test_cl3_inside_without_cap_goes() -> None:
    from app.core import conclude
    pick, why = conclude.of(0.60, kind="league:KL1")
    assert pick == "간다", (pick, why)


def test_cl4_no_probability_no_pick() -> None:
    from app.core import conclude
    pick, why = conclude.of(None, kind="league:ACL2")
    assert pick == "" and "확률이 없다" in why


def test_cl5_old_line_is_gone() -> None:
    """🔴 **CL5** — 옛 결론 글자가 **코드에서** 사라졌다.

    ⚠️ **D46** — 독스트링·주석을 뺀 **코드만** 본다(그 글자가 *"걷혔다"* 고
       설명하는 독스트링은 금지어가 아니다).
    """
    import ast
    tree = ast.parse((ROOT / "app/core/stages/s7_judge.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    said = ast.unparse(tree)
    assert "보류 — 보드가 없다" not in said
    assert "conclude" in said


def test_cl6_recorded_in_v6_section7() -> None:
    said = (ROOT / "docs/fable/inbox/2026-10-06_v6_soccer_4layer.md").read_text(
        encoding="utf-8")
    assert "보드 없음 결론 규칙 (가)" in said
    assert "접는다" in said and "조건부" in said and "간다" in said


def test_cl7_no_market_in_the_rule() -> None:
    """🔴 **CL7** — 규칙이 시장·배당을 읽지 않는다(D46: 코드만 본다)."""
    import ast
    import inspect
    from app.core import conclude
    tree = ast.parse(inspect.getsource(conclude))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    said = ast.unparse(tree)
    for bad in ("market", "odds", "배당", "시장"):
        assert bad not in said, bad


def test_cl8_cap_opens_when_the_backfill_lands() -> None:
    """🔴 백필이 끝난 대륙 대회는 상한이 **풀린다**(규칙이 영구 상한이 아니다)."""
    import inspect
    from app.core import conclude
    said = inspect.getsource(conclude.cap_of)
    assert "base_model" in said and "상한 없음" in said


def test_cl9_started_match_has_no_grade() -> None:
    """🔴🔴 **CL9** — 이미 시작한 경기는 **등급 없음**이 (가)보다 위다.

    🔴 그래도 (가)가 낸 글자를 **함께** 적는다(*"킥오프 전 기준이면"*) — 사후
       설명을 예측으로 읽히지 않게 머리에 그 사실을 박는다.
    """
    from app.core.stages.s7_judge import _conclusion
    got = _conclusion([], started=True, enough=True, thin_why="",
                      source="none", top=0.60, kind="league:KL1")
    assert "이미 시작한 경기" in got and "킥오프 전 기준이면" in got, got
    assert "간다" in got, got
