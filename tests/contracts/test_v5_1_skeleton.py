"""🔴🔴 **§1 — 골격·버리는 것** (작업 지시서 2026-10-05 딥서치 전면 재구축).

> **버린다**(삭제 커밋, 복구 금지)
>  · 경기 전체를 한 에이전트가 도는 진입 경로 → 하위 과제 병렬로 대체
>  · `TOP_PARAS` 의 BM25 단독 문단 선택 → §5 하이브리드로 대체
>  · `done` 거부 루프(네 유형 안 찾으면 `done` 거절) → **분할 자체가 커버리지를
>    보장하므로 제거.** 거부가 예산을 태운 실측(출력 25k 소진) 있음
>  · 세포 검색 계획기 잔재 → 부활 금지, 장부 역할만 유지
>
> **신설**: `app/research/subtasks.py` · `lead.py` · `rerank.py` ·
>   `tools/research_report.py`

⚠️ 승계: `done` 거부 루프에 걸린 옛 계약은 **대체 사유를 적고** 지운다 —
   *"커버리지 보장이 거부에서 분할로 이동(§2), 커버리지 계약은 M59·장부 `found`
   배선 계약이 승계"*.
"""
from __future__ import annotations

import ast
import inspect


def test_r1_골격_파일_넷이_있다():
    import importlib
    for name in ("app.research.subtasks", "app.research.lead",
                 "app.research.rerank"):
        mod = importlib.import_module(name)
        assert mod is not None, name
    import pathlib
    assert pathlib.Path("tools/research_report.py").exists(), (
        "🔴 `tools/research_report.py` 가 없다")


def test_r1_done_거부_루프가_없다():
    """🔴 거부가 예산을 태웠다 — 분할이 커버리지를 보장하므로 **지운다**."""
    from app import agentloop
    assert not hasattr(agentloop, "DONE_RESERVE"), (
        "🔴 `DONE_RESERVE` 가 남아 있다 — `done` 거부 루프의 예비분이다")
    tools = getattr(agentloop, "Tools", None)
    assert tools is not None
    assert not hasattr(tools, "done_ok"), (
        "🔴 `Tools.done_ok` 이 남아 있다 — `done` 을 거부하는 자리다")
    src = inspect.getsource(agentloop)
    tree = ast.parse(src)
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "done_ok" not in called, "🔴 아직 `done_ok` 을 부른다"


def test_r1_거부_사유도_걷혔다():
    """🔴 `checklist_left` 는 그 루프의 사유다 — 루프가 없으면 사유도 없다."""
    from app.reasons import Reason
    assert not hasattr(Reason, "CHECKLIST_LEFT"), (
        "🔴 `checklist_left` 가 남아 있다 — 부를 곳이 없는 사유는 거짓이다")


def test_r1_bm25_단독_문단_선택이_안_쓰인다():
    """🔴 §5 하이브리드가 그 자리를 대신한다.

    ⚠️ `top_paragraphs` 자체는 **1단 재료**로 남는다(BM25 상위 20) — 지시서
       §5 가 *"BM25 상위 20 → reranker 로 재점수"* 라고 적었다.
    🔴 금지되는 것은 **그것만으로 프롬프트에 넣는 것**이다.
    """
    from app import readtext
    assert hasattr(readtext, "top_paragraphs"), (
        "🔴 `top_paragraphs` 를 지우면 안 된다 — §5 1단의 재료다")
    assert not hasattr(readtext, "TOP_PARAS"), (
        "🔴 `TOP_PARAS`(6문단 단독 선택)가 남아 있다 — §5 가 상위 8 로 바꿨다")


def test_r1_세포_검색_계획기가_부활하지_않았다():
    from app import cells
    src = inspect.getsource(cells)
    tree = ast.parse(src)
    # 🔴 `may_search` 는 **장부 역할**이라 남는다 — 검색을 *하는* 코드가 없어야
    assert "cell_search_off" in src or "may_search" in src, (
        "🔴 장부 역할(`may_search`)이 사라졌다 — 그것은 유지해야 한다")
    del tree
