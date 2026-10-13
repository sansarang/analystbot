"""🔴🔴 **§6-7 검색 품질 측정 · §6-4 신원 감사**(지시서 2026-10-13 밤 셋째).

> 계약 **SQ1**: 정답 판정에 **경기 후 정보**를 쓰는 건 **측정용만** — 카드·확률
> 경로에 닿으면 실패.
> 계약 **ID1**: **잘못 버림 비율 > 10%** 면 판정 기준 재조정 후 재측정.

🔴 **기준선**(2026-10-13 · 카드 49장): 재현율 **16.3%(41/251)** · 정밀도
   **19.1%(41/215)**. 손실 깔때기(버린 문서 10,257건) — ④ 신원 **52%** ·
   ② 질의·날짜 34% · ① 원천 7% · ③ 본문 3.6% · ⑤ 추출 1.7%.
🔴 신원 감사(무작위 100건) — **잘못 버림 1%**(문턱 10% 안) → 신원 **기준은
   건드리지 않는다**. 🔴 그 둘을 함께 읽으면: *"신원이 많이 버리는데 **대체로
   맞게** 버린다"* → 잃는 곳은 **무엇으로 찾나(질의)·어디서 찾나(원천)** 다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def _code(rel: str) -> str:
    """🔴 **D46** — 독스트링을 뺀 코드만 본다."""
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_sq1_measurement_tools_are_not_in_the_app() -> None:
    """🔴🔴 **SQ1** — 측정 도구는 `tools/` 에만 있고 `app/` 이 안 부른다."""
    assert (ROOT / "tools/search_quality.py").exists()
    hits = []
    for path in (ROOT / "app").rglob("*.py"):
        said = _code(str(path.relative_to(ROOT)))
        for bad in ("search_quality", "identity_audit", "search_funnel"):
            if bad in said:
                hits.append((str(path), bad))
    assert not hits, f"🔴 측정 도구가 운영 코드에 닿았다: {hits}"


def test_sq1_truth_uses_the_leak_door_for_the_usual_xi() -> None:
    """🔴 평소 XI 는 **그 경기 앞** 경기로만 센다(L1 · 문은 `before_as_of`)."""
    said = (ROOT / "tools/search_quality.py").read_text(encoding="utf-8")
    assert "before_as_of" in said
    i = said.index("async def truth")
    assert "before_as_of" in said[i:i + 3000]


def test_id1_threshold_is_ten_percent() -> None:
    """🔴🔴 **ID1** — 문턱은 **10%** 다(코드가 그 수를 들고 판정을 적는다)."""
    said = (ROOT / "tools/identity_audit.py").read_text(encoding="utf-8")
    assert "0.10" in said and "ID1" in said


def test_identity_audit_uses_the_one_alias_door() -> None:
    """🔴 별칭은 `discover.aliases_of` 하나다(사본 금지 · 현지어 포함)."""
    said = _code("tools/identity_audit.py")
    assert "aliases_of" in said


def test_new_rule_needs_two_signals() -> None:
    """🔴 새 기준 — 신호 **둘 이상**이어야 통과다(하나로는 안 된다)."""
    import identity_audit as ia
    ok, hits = ia.new_rule("쇼난 벨마레 대 알비렉스 니가타 선발 예상",
                           home="Shonan Bellmare", away="Albirex Niigata")
    assert ok and len(hits) >= 2, hits
    bad, hits2 = ia.new_rule("Transfermarkt — Squad", home="Shonan Bellmare",
                             away="Albirex Niigata")
    assert not bad and len(hits2) < 2, hits2


def test_stage_table_is_one_place() -> None:
    """🔴🔴 §6-7 단계 묶음은 **`reasons.stage_of` 하나**다(사본 금지 · #1).

    ⚠️ 실사고 2026-10-13: 측정 도구가 그 표를 **베껴** 들고 있었다 — 그러면
       카드가 적는 단계와 보고가 적는 단계가 **갈린다**.
    """
    from app import reasons as rs
    assert rs.stage_of("identity_mismatch") == "④ 신원"
    assert rs.stage_of("stale") == "② 질의·날짜"
    assert rs.stage_of("body_missing") == "③ 본문"
    assert "미분류" in rs.stage_of("없는사유")
    said = (ROOT / "tools/search_funnel.py").read_text(encoding="utf-8")
    assert "stage_of" in said
    # 🔴 도구가 자기 표를 다시 들고 있지 않다
    assert "\"identity_mismatch\": \"④" not in said


def test_card_prints_the_search_line() -> None:
    """🔴 **§6-8** — 카드가 질의·결과·문서와 **잃은 단계**를 적는다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "🔎 **검색**" in said and "잃음" in said
    assert "stage_of" in said or "_reason_stage" in said
