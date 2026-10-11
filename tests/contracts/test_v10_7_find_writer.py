"""🔴🔴 **경기 찾기 — LLM 이 이름 후보만 댄다** — 사용자 지시 2026-10-11(3번).

> 라인업 확인하는것도 llm 한번 호출로 찾게하는것도 검토해라..(경기 찾는것도)
>   → 3번: `findwriter` — LLM 은 **글자(팀 이름·슬러그·매체)** 만 내고,
>      우리가 **팀 색인에서 확인한 것만** 쓴다.

⚠️ 오늘 네 번 실패했다: `openworld_not_found`(미토+이와키 · 쇼난+니가타) ·
   `match_not_found`(미토) · 한글 `위트레흐트` 안 풀림. 넷 다 **이름 문제**다.

🔴🔴 **잠금 넷**(②③ 과 같다)
  ① LLM 출력은 **글자뿐**이다 — 수·판정 칸이 없다.
  ② **색인에서 확인된 글자만** 쓴다(지어낸 슬러그는 자동으로 버려진다 · #4).
  ③ 색인 사다리가 **먼저** 돈다 — LLM 은 그것이 **실패한 뒤에만** 부른다(비용).
  ④ 카드·기록이 **후보 N개 중 확인 M개**를 적는다(#3).
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


def test_output_is_strings_only() -> None:
    """🔴🔴 ① — 칸 셋 다 **글자 목록**이다(수·판정 없음)."""
    from app.core.findwriter import TeamGuess
    assert set(TeamGuess.model_fields) == {"teams", "slugs", "sites"}


def test_slug_shape_is_guarded() -> None:
    """🔴 슬러그 꼴이 아니면 버린다(모델이 주소·대문자·문장을 준다)."""
    from app.core import findwriter as fw
    got, bad = fw.keep_slugs(["fc-utrecht", "FC Utrecht",
                              "https://www.fotmob.com/teams/9908/fc-utrecht",
                              "shonan-bellmare", "a", "일본 팀"])
    assert got == ["fc-utrecht", "shonan-bellmare"], got
    assert len(bad) == 4, bad


def test_team_names_are_cleaned() -> None:
    """🔴 이름은 다듬고 수를 자른다(주소·빈 글자는 버린다)."""
    from app.core import findwriter as fw
    got, bad = fw.keep_teams(["  FC Utrecht ", "FC Utrecht", "",
                              "http://x.y", "ユトレヒト"])
    assert got == ["FC Utrecht", "ユトレヒト"], got
    assert any("http" in x for x in bad), bad
    assert len(got) <= fw.MAX_TEAMS


def test_confirm_uses_the_index() -> None:
    """🔴🔴 ② — **색인에서 확인된 것만** 돌려준다(지어낸 글자는 버려진다)."""
    from app.core import findwriter as fw
    idx = {"9908": "fc-utrecht", "6180": "shonan-bellmare"}
    got, said = fw.confirm(idx, names=["FC Utrecht", "없는 팀 이름"],
                           slugs=["fc-utrecht", "zzz-made-up"])
    assert got, (got, said)
    assert all(isinstance(x, tuple) and len(x) == 2 for x in got), got
    assert any("fc-utrecht" in str(x) for x in got), got
    assert any("버렸다" in said or "확인" in said for _ in [0]), said


def test_llm_runs_only_after_the_index_fails() -> None:
    """🔴🔴 ③ — 색인 사다리가 **먼저**다(LLM 은 그 뒤에만 부른다)."""
    from app import findgame
    src = _src(findgame.find)
    i = src.find("_by_index")
    j = src.find("_by_llm_names")
    assert i >= 0 and j >= 0, (i, j)
    assert i < j, "LLM 을 색인보다 먼저 부른다(비용)"
    #: 🔴 그 함수가 `findwriter` 를 부른다(확인은 색인이 한다)
    made = _src(findgame._by_llm_names)
    assert "findwriter" in made and "confirm" in made


def test_skipped_in_replay() -> None:
    """⚠️ 재생에서는 안 부른다 — 녹음이 그 질문을 모른다."""
    from app.core import findwriter as fw
    src = inspect.getsource(fw)
    assert "재생" in src or "replay" in src


def test_records_candidates_and_confirmed() -> None:
    """🔴 #3 — **후보 N개 중 확인 M개**를 적는다."""
    from app.core import findwriter as fw
    said = fw.said_of(teams=["a"], slugs=["b"], ok=[("1", "b")], bad=["c"])
    assert "후보" in said and "확인" in said
