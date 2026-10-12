"""🔴🔴 **§13 정보 품질 InfoQ** · **§14 판정 행동** — 지시서 2026-10-12(둘째).

> §13 — 0~5점: +1 확정 XI(양 팀 id) · +1 결장 사다리 한 칸 이상 성공(양 팀) ·
> +1 새 사실 72시간 ≥1 · +1 ContextRow 완전 · +1 벤치 id 확정.
> 재현·백필에선 계산 불가 칸(기사)은 ⬜ — 운영 카드에서만 계산·저장.
> 계약 **C13-1**: InfoQ 가 **확률에 닿으면** 실패.
> §14 — InfoQ ≤ 2 → 등급 **한 단계↓** · "조건부" 이상 불가 · 빠진 칸을 방아쇠로.
> 계약 **C14-1**: InfoQ ≤ 2 인데 "간다" 면 실패.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _strip(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_five_boxes_and_the_score() -> None:
    from app.core import infoquality as iq
    assert len(iq.BOXES) == 5
    got = iq.score_of({"xi_ids": True, "ladder": True, "fresh": True,
                       "context": True, "bench_ids": True})
    assert got.score == 5 and got.unknown == []


def test_missing_boxes_are_named() -> None:
    """🔴 못 센 칸은 **이름으로** 남는다(조용한 0 금지 · #3)."""
    from app.core import infoquality as iq
    got = iq.score_of({"xi_ids": True, "ladder": False, "fresh": None,
                       "context": True, "bench_ids": False})
    assert got.score == 2
    assert "결장 사다리" in got.why and "벤치" in got.why
    # 🔴 `None` = **계산 불가**(⬜) — 0 점과 다르다
    assert any("새 사실" in u for u in got.unknown), got.unknown


def test_low_infoq_drops_a_grade() -> None:
    """🔴 §14 — InfoQ ≤ 2 → 등급 **한 단계↓**(사다리는 `s7_judge.BREAK_LADDER`)."""
    from app.core import infoquality as iq
    got, why = iq.step_of(score=2)
    assert got == 1 and "InfoQ" in why
    # 🔴 넉넉하면 **안 건드린다**
    assert iq.step_of(score=3)[0] == 0


def test_c14_1_no_go_when_info_is_thin() -> None:
    """🔴🔴 **C14-1** — InfoQ ≤ 2 면 `간다` 가 **남지 못한다**('조건부' 상한)."""
    from app.core import infoquality as iq
    for said in ("간다", "조건 없음"):
        assert iq.cap_stance(said, score=1) == "조건부", said
    # ⚠️ 이미 더 나쁜 판정은 **그대로 둔다**(올리는 길이 없다)
    assert iq.cap_stance("접는다", score=1) == "접는다"
    assert iq.cap_stance("간다", score=5) == "간다"


def test_ladder_is_not_a_copy() -> None:
    """🔴 등급 사다리를 **베끼지 않는다** — `s7_judge.BREAK_LADDER` 를 쓴다."""
    said = _strip("app/core/infoquality.py")
    assert "BREAK_LADDER" in said
    assert '"낸다"' not in said and "'낸다'" not in said


def test_c13_1_infoq_never_touches_the_probability() -> None:
    """🔴🔴 **C13-1** — 확률 경로가 `infoquality` 를 **안 부른다**."""
    for rel in ("app/core/probmodel.py", "app/core/probfloor.py",
                "app/core/sim.py", "app/core/matchup.py"):
        said = _strip(rel)
        assert "infoquality" not in said, rel
        assert "infoq" not in said.lower(), rel


def test_pipeline_applies_it_after_the_grade() -> None:
    """🔴 ㉑·㉒ **뒤에** 적용된다(확률·생존은 그대로다).

    ⚠️ 적용 자리는 `s7_judge` 안이 아니라 **`pipeline`** 이다 — 반증 판정
       (`by_breaks`)도 같은 자리에서 등급 위에 얹힌다. 🔴 그 순서를 센다.
    """
    said = _strip("app/core/pipeline.py")
    assert "_iq.apply" in said
    i = said.index("by_breaks")
    assert "_iq.apply" in said[i:], "🔴 반증 판정 **앞에서** 적용됐다"
