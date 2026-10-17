"""🔴🔴 **§0 옛 경로 고정** — 비교 시험 지시서 2026-10-12 §0.

> `app/core/legacy/old_engine.py` — 마지막 옛 구조 커밋의 축0~3 합산·β·λ·시뮬
> 로직을 **그대로** 옮긴다(수정 금지, 태그 `legacy-4axis`).
> 계약 **K0**: 옛 경로 코드 해시가 태그와 다르면 **실패**.

🔴 왜 해시인가 — 비교 시험의 **기준**이 조용히 움직이면 그 시험은 아무것도 말하지
   않는다. ⚠️ 고쳐야 할 이유가 생기면 그것은 *"옛 경로를 바꾼다"* 는 뜻이고, 그
   결정은 **사용자**가 한다(그때 이 해시를 함께 고친다).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "app/core/legacy/old_engine.py"

#: 🔴🔴 **태그 `legacy-4axis`** — 얼린 그 파일의 sha256
#
#  ⚠️ **2026-10-15 에 한 번 바뀠다** — 사용자 결정으로 **상성을 삭제**했다
#     (축 종합·쪽값이 λ 를 안 움직인다 · 이동 0 고정). K0(얼림)을 그 지시가
#     풀었고, 그 밖의 줄은 **하나도 안 건드렸다**.
#  🔴 옛 해시(2026-10-12 측정): 71def33640d1a7d41b7731700960fef8509fc7c41ac85741c80c9317ec6ee53f
TAG_SHA = "5ec097aadabcb32f39524edef6695702162d7dfc6fa5b322be8a09e9beae9140"


def test_k0_legacy_hash_matches_the_tag() -> None:
    """🔴🔴 **K0** — 한 글자만 바뀌어도 빨개진다."""
    got = hashlib.sha256(LEGACY.read_bytes()).hexdigest()
    assert got == TAG_SHA, (
        f"🔴 **K0 위반** — 옛 경로가 바뀌었다\n  지금 {got}\n  태그 {TAG_SHA}\n"
        "  ⚠️ 비교 시험의 기준이 움직이면 그 시험은 아무것도 말하지 않는다.")


def test_legacy_has_no_floor_path() -> None:
    """🔴 옛 경로에는 **Elo 바닥이 없다**(그것이 새 구조의 것이다)."""
    said = LEGACY.read_text(encoding="utf-8")
    for bad in ("probfloor", "floor=", "shadow"):
        assert bad not in said, bad


def test_legacy_keeps_all_four_axes() -> None:
    """🔴 옛 경로는 **축0~3 네 개**를 합산한다(새 구조는 둘만 쓴다)."""
    from app.core.legacy import old_engine as oe
    # ⚠️ 한 줄 꼴은 `{"축": {"att": {home, away}, "dfn": {…}}}` 다(그 커밋의 F3 식)
    one = {"att": {"home": 1.0, "away": 0.0}, "dfn": {"home": 1.0, "away": 0.0}}
    said = oe.sides_move({"axis0": one, "axis2": one, "axis3": one},
                         {"axis0": 0.3, "axis2": 0.2, "axis3": 0.2},
                         beta=0.25, cap=0.35)
    # 🔴 축2·축3 이 **움직인다** — 새 구조에서는 안 움직인다(v12 계약이 그것을 센다)
    only0 = oe.sides_move({"axis0": one}, {"axis0": 0.3}, beta=0.25, cap=0.35)
    assert said["home"] > only0["home"], (said, only0)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§6 운영 그림자 기간** — 카드마다 M1·M3 를 **둘 다** 기록
# ══════════════════════════════════════════════════════════════════
#
#  > 판정과 무관하게 지금부터 운영 카드마다 **M1·M3 확률을 둘 다** 기록
#  > (최종 확률은 현 운영판). 결과 30경기마다 같은 지표로 자동 채점·보고.


def test_operation_uses_the_frozen_engine() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_operation_uses_the_frozen_engine)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_card_records_both_numbers() -> None:
    """🔴 카드가 **최종(M3)·그림자(M1)·바닥** 셋을 적는다(채점이 그것을 읽는다)."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "그림자 확률" in said and "바닥(Elo)" in said
    got = (ROOT / "tools/score_cards.py").read_text(encoding="utf-8")
    for want in ("SHADOW", "FLOOR", "REPORT_EVERY"):
        assert want in got, want
