"""🔴🔴 **§6 — 날짜 3층 마감 + 골격 배선**(지시서 2026-10-05 딥서치 재구축).

> 이미 실측·일부 구현된 것을 이 재구축 안에서 **끝까지 배선한다.**
>  1. ①층 — `time_range=week` 기본. **결과가 2건 이하면** 그 질의 한정으로
>     `time_range` 없이 **1회 재시도**(fetch 전 ②③층이 거르니 안전).
>  2. ②층 — `app/datehint.py` 를 **하위 에이전트의 검색 결과 경로에 배선** —
>     `self.snippets` 가 실제로 채워지는지 **배선 계약으로** 확인한다.
>  3. ③층 — `htmldate` 가 `published_at` 의 **원본**.
>  4. GDELT `seendate` · Bing RSS `pubDate` 유지. Google News 는 **dead**.

🔴 그리고 §1~§5 의 골격을 **실제 경로**(`analyze._run_agent`)에 잇는다 —
   안 이은 코드는 없는 코드보다 나쁘다(규율 #2).
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# ①층 — **2건 이하면** 창 없이 1회 재시도
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전엔 **0건**일 때만 벗겼다. 🔴 지시서가 수를 바꿨다: *"결과가 2건
#     이하면 그 질의 한정으로 `time_range` 없이 1회 재시도."*
def test_r6_두건_이하면_창을_벗기고_다시():
    import asyncio

    from app import search
    assert hasattr(search, "SEARX_THIN_AT"), (
        "🔴 `search.SEARX_THIN_AT` 가 없다 — 몇 건을 '얄팍하다'로 보나")
    assert search.SEARX_THIN_AT == 2, search.SEARX_THIN_AT
    seen: list = []

    class Fake(search.SearxSearch):
        async def _one(self, text, *, lang="ko", engines=None, time_range=""):
            seen.append(time_range)
            # 🔴 창을 걸면 **2건**(얄팍하다) · 벗기면 다섯
            return ([search.Hit(title="t", url=f"https://a{i}.com/x")
                     for i in range(2 if time_range else 5)])

    got = asyncio.run(Fake().query("아무 질의"))
    assert seen == ["week", ""], (
        f"🔴 2건인데 다시 안 던졌다(던진 창: {seen})")
    assert len(got) == 5, f"🔴 벗긴 결과를 안 썼다: {len(got)}"


def test_r6_세건이면_다시_안_던진다():
    """🔴 상한을 넘으면 **그대로 쓴다** — 쓸데없는 호출을 늘리지 않는다."""
    import asyncio

    from app import search
    seen: list = []

    class Fake(search.SearxSearch):
        async def _one(self, text, *, lang="ko", engines=None, time_range=""):
            seen.append(time_range)
            return [search.Hit(title="t", url=f"https://a{i}.com/x")
                    for i in range(3)]

    asyncio.run(Fake().query("아무 질의"))
    assert seen == ["week"], f"🔴 3건인데 또 던졌다: {seen}"


# ══════════════════════════════════════════════════════════════════
# ②층 — 하위 에이전트의 **검색 결과 경로**에 배선
# ══════════════════════════════════════════════════════════════════
def test_r6_스니펫이_실제로_채워진다():
    """🔴 *"`self.snippets` 가 실제로 채워지는지 배선 계약으로 확인한다"*.

    ⚠️ 지시서가 그 까닭을 적었다: *"채우는 곳이 없으면 **조용히 꺼진다** —
       12→0 과 같은 병."*
    """
    from app import agentloop
    inp = _inp()
    tools = agentloop.Tools(inp)

    class Chain:
        async def query(self, text, *, lang="ko", **kw):
            from app.search import Hit
            return [Hit(title="Ronaldo out", url="https://a.com/1",
                        snippet="Published October 4, 2026 — he is out")]

    tools.chain = Chain()
    # ⚠️ `_book_search` 는 **장부용**이고 검색을 안 한다(재서 고쳤다) —
    #    스니펫을 채우는 자리는 `_hunt` 다.
    got, _why = tools._hunt("France Belgium injury news", "en")
    assert got, "🔴 검색이 아무것도 안 돌려줬다"
    said = tools.snippets.get("https://a.com/1") or ""
    assert "October 4, 2026" in said, (
        f"🔴 스니펫이 **안 채워졌다** — ②층이 조용히 꺼진다: {said!r}")


def test_r6_오래된_문서는_안_받는다():
    """🔴 7일 밖이 **확실하면** 받지 않는다. ⚠️ 힌트가 없으면 받는다."""
    from app import agentloop, datehint
    inp = _inp()
    tools = agentloop.Tools(inp)
    tools.snippets["https://a.com/old"] = "Published August 1, 2026"
    skip, why = datehint.too_old("https://a.com/old",
                                 tools.snippets["https://a.com/old"])
    assert skip and "밖" in why, why
    # 🔴 `_open` 이 그것을 **부른다**(배선)
    import textwrap
    tree = ast.parse(textwrap.dedent(
        inspect.getsource(agentloop.Tools._open)))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "too_old" in called, (
        f"🔴 `_open` 이 `datehint.too_old` 를 안 부른다{sorted(called)}")


def _inp():
    import datetime as dt

    from app import agentloop
    return agentloop.AgentInput(
        match_key="fotmob:1", home="team:000081", away="team:000021",
        kickoff_utc=dt.datetime(2026, 10, 5, 18, 45, tzinfo=dt.timezone.utc),
        home_names=("France",), away_names=("Belgium",),
        competition="UEFA Nations League A Grp. 1", sport="soccer",
        venue="Stade de France")


# ══════════════════════════════════════════════════════════════════
# 골격 배선 — 실제 경로가 §2~§5 를 **쓴다**
# ══════════════════════════════════════════════════════════════════
def test_r6_실제_경로가_분할을_쓴다():
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for want in ("split", "run_all", "merge", "write_book", "funnel_lines"):
        assert want in called, (
            f"🔴 `analyze` 가 `{want}` 를 **안 부른다** — 골격이 안 이어졌다")


def test_r6_하위가_재정렬을_쓴다():
    from app import agentloop
    tree = ast.parse(inspect.getsource(agentloop))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "order" in called or "paragraphs" in called, (
        "🔴 하위 경로가 재정렬을 **안 쓴다** — §5 가 안 이어졌다")


def test_r6_하위_프롬프트가_붙는다():
    from app import agentloop
    src = inspect.getsource(agentloop)
    assert "prompt_tail" in src, (
        "🔴 하위 프롬프트 꼬리(`prompt_tail`)가 안 붙는다 — 담당 유형을 모른다")


def test_r6_동시성_가드가_검색과_fetch_에_걸린다():
    from app import agentloop
    src = inspect.getsource(agentloop)
    assert "gate(" in src, (
        "🔴 `lead.gate` 가 검색·fetch 에 안 걸렸다(M66) — 병렬 8개가 상한 없이 "
        "SearXNG 를 때린다")


# ══════════════════════════════════════════════════════════════════
# 남은 배선 셋 — **2차 보충 · 1단 재정렬 · 좁히기**
# ══════════════════════════════════════════════════════════════════
def test_r6_2차_보충이_실제로_돈다():
    """🔴 §3-3 — `empty`·`not_tried` 칸을 **한 번** 다시 돌린다(M64)."""
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for want in ("second_round", "second_budget"):
        assert want in called, (
            f"🔴 `analyze` 가 `{want}` 를 **안 부른다** — 빈 칸이 그대로 남는다")


def test_r6_1단_재정렬이_검색_결과에_걸린다():
    """🔴 §5 1단 — 받기 **전에** 순서를 바꾸고 `take(cap)` 로 자른다."""
    from app import agentloop
    tree = ast.parse(inspect.getsource(agentloop))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "order" in called, (
        "🔴 1단 재정렬(`rerank.order`)이 **안 걸렸다** — 검색 결과 순서가 "
        "그대로다")
    assert "take" in called, (
        "🔴 `rerank.take` 가 **안 걸렸다** — fetch 상한이 순서와 무관해진다")


def test_r6_좁히기와_1차_언어가_걸린다():
    """🔴 §4 — 씨앗 → 좁히기(결과의 구체 낱말) · 1차 언어."""
    from app import agentloop
    src = inspect.getsource(agentloop)
    for want in ("narrow_words", "narrow_query", "first_lang"):
        assert want in src, (
            f"🔴 `{want}` 가 하위 경로에 **안 걸렸다** — 2차가 지어내게 된다")
