"""🔴🔴 **§3 날짜 단일 경로 · 전송 사유** — 지시서 2026-10-06 §3 (M130·M131·M136).

> 날짜 — 경로를 **하나로** 만든다. 이번 주에 날짜가 끊긴 경로가 **셋**이었다
> (fetch 신규 · 본문 재사용 · 세포 `_remember_body`). 경로마다 고치는 방식은
> **네 번째를 또 만든다.**
> 본문을 저장하는 함수를 하나로: `store_doc(url, body, published_at, date_source)`.
> 검증층의 날짜 조회도 한 함수: `doc_date(url)`.
> 사유 분리 유지: `llm_timeout`·`llm_http_5xx`·`llm_429`·`budget_cut` 은 서로
> 다른 사유다. 429 가 한 번이라도 나면 동시 호출 4 → 2.
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════
# M130 — 저장은 `store_doc` 하나뿐(AST)
# ══════════════════════════════════════════════════════════════════



def test_M130_app_어디서도_본문을_직접_대입하지_않는다():
    """🔴 AST — `…bodies[x] = y` 가 있으면 그 경로는 날짜를 잃는다."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Assign):
                continue
            for t in n.targets:
                if not (isinstance(t, ast.Subscript)
                        and isinstance(t.value, ast.Attribute)
                        and t.value.attr in ("bodies", "docs", "dates")):
                    continue
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno} "
                           f"{ast.unparse(n)[:70]}")
    assert not bad, (
        "🔴 본문·날짜를 **직접 대입**한다 — `cells.store_doc` 를 써라:\n  "
        + "\n  ".join(bad))


def test_M130_날짜를_버리는_자리가_없다():
    """🔴 `readtext.read|extract` 의 둘째 반환값을 `_` 로 받는 자리(M124 확장)."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Attribute)
                    and n.value.func.attr in ("read", "extract")
                    and getattr(n.value.func.value, "id", "") == "readtext"):
                continue
            tgt = n.targets[0]
            if isinstance(tgt, ast.Tuple) and len(tgt.elts) >= 2 \
                    and isinstance(tgt.elts[1], ast.Name) \
                    and tgt.elts[1].id.startswith("_"):
                bad.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    assert not bad, f"🔴 발행일을 버리는 자리: {bad}"


# ══════════════════════════════════════════════════════════════════
# M131 — 재사용 본문을 인용한 변수도 날짜를 가진다
# ══════════════════════════════════════════════════════════════════





# ══════════════════════════════════════════════════════════════════
# M136 — 전송 사유가 섞이지 않는다
# ══════════════════════════════════════════════════════════════════

def test_M136_사유_넷이_서로_다르다():
    from app.reasons import Reason
    want = ("LLM_TIMEOUT", "LLM_HTTP_5XX", "LLM_429", "BUDGET_CUT")
    vals = []
    for name in want:
        assert hasattr(Reason, name), f"🔴 `Reason.{name}` 이 없다(지시서 §3)"
        vals.append(getattr(Reason, name).value)
    assert len(set(vals)) == 4, vals
    # 🔴 **예산과 망을 섞지 않는다** — 고칠 곳이 다르다
    assert Reason.BUDGET_CUT.fix_where == "예산", Reason.BUDGET_CUT.fix_where
    for name in ("LLM_TIMEOUT", "LLM_HTTP_5XX", "LLM_429"):
        assert getattr(Reason, name).fix_where != "예산", name




def test_M136_429_가_동시_호출을_낮춘다():
    from app import solar
    box = dict(solar.budget_cfg().get("concurrency") or {})
    saw = solar.SAW_429
    try:
        solar.SAW_429 = False
        before = solar.solar_concurrency()
        solar.SAW_429 = True
        assert solar.solar_concurrency() == int(box["solar_after_429"]) < before
    finally:
        solar.SAW_429 = saw




