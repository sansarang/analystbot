"""🔴🔴 **LLM 이 질의를 쓴다(②) · 매체를 고른다(③)** — 사용자 지시 2026-10-11.

> llm 호출로 서치하는 방법은? … **2,3 해라**
>   ② LLM 이 **질의를 쓴다**(현지어 포함) — 던지는 것은 **우리 검색 사슬**이다
>   ③ LLM 이 **어디를 열지 고른다** — 받은 도메인은 **확인 뒤에만** 쓴다

🔴🔴 **잠금 넷**(규율)
  ① LLM 출력은 **글자(질의·도메인)뿐**이다 — 사실·숫자·판정에 닿지 않는다.
  ② 던지는 통로는 **기존 사슬**이다(새 엔진·새 fetch 경로 없음).
  ③ 도메인은 **robots 를 받아 확인한 뒤에만** 쓴다(지어낸 주소 금지 · #4).
  ④ 카드가 **무엇을 던졌는지** 적는다(#3).
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="m", sport="soccer", competition="J. League 2",
                    competition_short="J2", home="team:000001",
                    away="team:000002", home_name="Shonan Bellmare",
                    away_name="Albirex Niigata",
                    kickoff_utc="2026-10-11T09:00:00Z")


# ══════════════════════════════════════════════════════════════════
# ② 질의 — 글자만, 그리고 **그 경기 것인지** 검사한다
# ══════════════════════════════════════════════════════════════════

def test_queries_must_name_a_team() -> None:
    """🔴🔴 ② — 팀 이름이 **한 글자도 없는 질의는 버린다**(딴 데로 못 간다)."""
    from app.core import querywriter as qw
    got, bad = qw.keep(["湘南ベルマーレ スタメン", "오늘 축구 경기 일정",
                        "Albirex Niigata injury"],
                       aliases=["Shonan Bellmare", "湘南ベルマーレ",
                                "Albirex Niigata"])
    assert "湘南ベルマーレ スタメン" in got and "Albirex Niigata injury" in got
    assert any("오늘 축구" in x for x in bad), bad


def test_queries_are_capped_and_cleaned() -> None:
    """🔴 ② — 수를 자르고(예산) 공백·중복·금지 문자를 지운다."""
    from app.core import querywriter as qw
    rows = [f"Shonan Bellmare 질의{i}" for i in range(20)]
    got, _bad = qw.keep([*rows, "Shonan Bellmare  질의0 ", "Shonan 'x' 질의"],
                        aliases=["Shonan Bellmare", "Shonan"])
    assert len(got) <= qw.MAX_QUERIES, len(got)
    assert len(got) == len(set(got)), got
    assert not any("'" in x for x in got), got


def test_llm_output_is_strings_only() -> None:
    """🔴🔴 ① — 스키마에 **글자 목록 둘**뿐이다(수·판정 칸이 없다)."""
    from app.core.querywriter import QueryPlan
    assert set(QueryPlan.model_fields) == {"queries", "sites"}


# ══════════════════════════════════════════════════════════════════
# ③ 매체 — 확인 뒤에만 쓴다
# ══════════════════════════════════════════════════════════════════

def test_sites_need_a_hostname() -> None:
    """🔴 ③ — 호스트 꼴이 아니면 버린다(모델이 문장을 줄 수 있다)."""
    from app.core import querywriter as qw
    got, bad = qw.hosts(["gekisaka.jp", "https://www.soccer-king.jp/news",
                         "일본 축구 매체를 보세요", "localhost", "a.b"])
    assert "gekisaka.jp" in got and "www.soccer-king.jp" in got, got
    assert any("매체를" in x for x in bad), bad
    assert "localhost" not in got, got


def test_sites_are_used_as_site_queries() -> None:
    """🔴🔴 ③ — 확인된 도메인은 **`site:` 질의**로 기존 사슬에 던진다.

    🔴 새 fetch 경로를 만들지 않는다 — 통로는 그대로다.
    """
    from app.core import querywriter as qw
    got = qw.site_queries(["gekisaka.jp"], ["湘南ベルマーレ スタメン"])
    assert got == ["site:gekisaka.jp 湘南ベルマーレ スタメン"], got


def test_verify_before_use() -> None:
    """🔴🔴 ③ — robots 를 **받아 확인**한 도메인만 쓴다(지어낸 주소 금지)."""
    from app.core import querywriter as qw
    src = _src(qw.check_hosts)
    assert "robots" in src and "net" in src
    assert "200" in src or "ok" in src


# ══════════════════════════════════════════════════════════════════
# 배선·기록
# ══════════════════════════════════════════════════════════════════

def test_wired_into_deep_search() -> None:
    """🔴 배선 — 딥서치가 그 질의를 **기존 사슬로** 던진다."""
    from app.core.stages import s3_docs
    src = inspect.getsource(s3_docs)
    assert "querywriter" in src, "딥서치가 안 부른다"


def test_card_prints_what_was_thrown() -> None:
    """🔴 #3 — **무엇을 던졌는지** 카드가 적는다."""
    from app.core import querywriter as qw
    assert "said_of" in dir(qw)
    said = qw.said_of(queries=["a"], sites=["b.jp"], bad=["c"], why="x")
    assert "질의" in said and "매체" in said and "버린" in said
