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

def test_M130_본문_저장_함수가_하나다():
    from app import cells
    assert hasattr(cells, "store_doc"), "🔴 `cells.store_doc` 가 없다"
    assert hasattr(cells, "doc_date"), "🔴 `cells.doc_date` 가 없다"
    seen = cells.Seen()
    when = dt.datetime(2026, 10, 5, 9, tzinfo=dt.timezone.utc)
    cells.store_doc(seen, "https://a/1", "본문이다", published_at=when,
                    date_source="본문(htmldate)")
    assert cells.doc_date(seen, "https://a/1") == when
    assert seen.bodies.get("https://a/1") == "본문이다"
    # 🔴 **빈 것은 안 들어간다** · 🔴 먼저 넣은 것을 덮지 않는다
    cells.store_doc(seen, "https://a/1", "", published_at=None)
    assert seen.bodies.get("https://a/1") == "본문이다"
    cells.store_doc(seen, "https://a/1", "나중 본문")
    assert seen.bodies.get("https://a/1") == "본문이다"


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

def test_M131_두_하위가_같은_URL_을_써도_날짜가_붙는다():
    """🔴🔴 고정물: 하위 A 가 받고, 하위 B 는 **재사용만** 한다."""
    from app import agentloop, cells
    shared = cells.Seen()
    when = dt.datetime(2026, 10, 4, 10, tzinfo=dt.timezone.utc)
    a = agentloop.Tools(inp=_inp(), seen=shared)
    cells.store_doc(a.store, "https://news/1", "Bradley is unavailable.",
                    published_at=when, date_source="본문")
    b = agentloop.Tools(inp=_inp(), seen=shared)
    assert cells.doc_date(b.store, "https://news/1") == when
    box = {"variables": [{"id": "v1", "type": "def_absence",
                          "team": "team:1", "claim": "x",
                          "quote": "Bradley is unavailable.",
                          "url": "https://news/1"}]}
    got, why = agentloop._vars_from(box, dates=b.dates)
    assert got, why
    assert getattr(got[0], "published_at", None) is not None, (
        "🔴 재사용 본문을 인용한 변수에 **날짜가 없다** — 검증층이 "
        "`date_missing` 으로 버린다")


def test_M131_검증층이_같은_저장소에서_읽는다():
    """🔴 `doc_date` 가 신규·재사용을 **가리지 않는다**."""
    from app import cells
    seen = cells.Seen()
    assert cells.doc_date(seen, "https://없다/1") is None
    cells.store_doc(seen, "https://b/2", "글", published_at="2026-10-05")
    assert cells.doc_date(seen, "https://b/2") == "2026-10-05"


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


@pytest.mark.parametrize("status,want", [
    (None, "LLM_TIMEOUT"), (429, "LLM_429"),
    (500, "LLM_HTTP_5XX"), (503, "LLM_HTTP_5XX"),
])
def test_M136_상태_코드가_사유를_정한다(status, want):
    """🔴🔴 **돌려서** 본다 — 타임아웃을 `budget_cut` 으로 적으면 빨개진다."""
    from app import agentloop, solar
    from app.reasons import Reason
    exc = solar.SolarUnavailable("llm_unavailable: x", status=status)
    assert agentloop._why_of(exc) is getattr(Reason, want), (
        status, agentloop._why_of(exc))
    # 🔴 예산 거부는 **그 넷 어디에도** 안 섞인다
    assert agentloop._why_of(solar.SolarBudgetCut("budget_cut: x")) \
        is Reason.BUDGET_CUT


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


def _inp():
    from app import agentloop
    return agentloop.AgentInput(
        match_key="fotmob:1", home="team:1", away="team:2",
        home_names=("A",), away_names=("B",), competition="L", sport="soccer",
        kickoff_utc=dt.datetime(2026, 10, 5, 18, 45, tzinfo=dt.timezone.utc),
        venue="V", langs=("en",))
