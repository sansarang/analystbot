"""[1단계 2026-09-05] 이미 가진 기사가 판정에 도달하게 한다.

🔴 감사 결론: 자료2 가 "없음"인 이유는 기사가 없어서가 아니었다.
   · RSS 로 팀당 99~100건을 72시간 창으로 받고 있었다(실측 2026-09-04:
     `q=KIA 타이거즈` 99건 · `q=KT 위즈` 100건).
   · 그런데 팀 폼이 읽는 `research[f"{side}_news"]` 를 **아무도 채우지
     않았다** — 전수 grep 0건. RSS 결과는 `deepsearch._free_articles`
     전용이고, KBO·NPB 는 딥서치가 꺼져 있어 통째로 버려졌다.
   · 그래서 팀 폼은 늘 뉴스 없이 돌았고 `뉴스태그` 가 비었으며,
     자료2(= `news_payload` 가 꺼내는 그 태그)가 "없음"이 됐다.

⚠️ 지시서가 지목한 `team_briefs`·`news_articles` 테이블은 **존재하지
   않는다**(스키마에 뉴스 테이블 0개, 두 이름 코드 0건). 증상은 같다 —
   "읽는 쪽이 채워지지 않는다". 실제 구조에 맞춰 고쳤다.

⚠️ AI 요약을 넣지 않는다. 제목·URL·시각 원문만 넘기고, 태그는 팀 폼이 만든다.
"""
import ast
from pathlib import Path

import pytest


def code_only(src: str) -> str:
    """독스트링·주석을 뺀 **실행되는 줄**만.

    ⚠️ 주석에는 왜 그렇게 했는지가 적혀 있고 거기엔 금지어가 자연히 나온다
       ("요약하면 안 된다", "72시간 창"). 주석까지 금지하면 사고 기록을
       지우게 된다 — 오늘 세 번 같은 자리에서 걸렸다.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0].value.value = ""
    return ast.unparse(tree)


# ─────────────────── 배선 ───────────────────

def test_team_form_news_key_is_now_written():
    """🔴 이것이 결함의 핵심이었다 — 읽는 키를 쓰는 곳이 0건이었다."""
    src = Path("app/collectors/news_rss.py").read_text(encoding="utf-8")
    assert 'research[f"{side}_news"] = rows' in src


def test_injection_happens_before_team_form():
    """팀 폼이 돈 뒤에 넣으면 그 슬레이트는 여전히 뉴스가 없다."""
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    inject = src.index("_news_by_side(_g, r)")
    form = src.index("forms = await analyze_games(")
    assert inject < form, "주입이 팀 폼 호출보다 뒤에 있다"


def test_no_summarisation_in_the_path():
    """🔴 AI 요약을 판정 재료로 넣지 않는다 — 원문만 넘긴다."""
    src = code_only(Path("app/collectors/news_rss.py").read_text(encoding="utf-8"))
    for banned in ("complete(", "anthropic", "judge_route", "openai_compat",
                   "gemini", "요약"):
        assert banned not in src, banned


def test_by_side_does_not_refetch():
    """`for_game` 캐시를 타야 한다 — 같은 슬레이트에서 두 번 긁지 않는다."""
    import inspect

    from app.collectors.news_rss import by_side

    src = inspect.getsource(by_side)
    assert "for_game(" in src
    assert "fetch_team(" not in src, "캐시를 우회해 직접 긁는다"


# ─────────────────── 팀 매칭 ───────────────────

@pytest.mark.asyncio
async def test_articles_are_split_by_the_query_team(monkeypatch):
    """🔴 팀 매칭은 쿼리 팀명으로만 한다 — 본문에서 추정하지 않는다."""
    import app.collectors.news_rss as nr

    async def _fake(jg, redis=None, *, limit=12):
        return [{"title": "KIA 기사", "url": "u1", "team": "Kia Tigers"},
                {"title": "KT 기사", "url": "u2", "team": "KT Wiz"},
                {"title": "KIA 기사2", "url": "u3", "team": "Kia Tigers"}]

    monkeypatch.setattr(nr, "for_game", _fake)
    out = await nr.by_side({"sport": "kbo", "home": "Kia Tigers",
                            "away": "KT Wiz"}, None)
    assert [x["title"] for x in out["home"]] == ["KIA 기사", "KIA 기사2"]
    assert [x["title"] for x in out["away"]] == ["KT 기사"]
    assert "team" not in out["home"][0], "내부 표식은 research 에 남기지 않는다"


@pytest.mark.asyncio
async def test_side_with_no_articles_is_omitted_not_empty(monkeypatch):
    """빈 배열을 넣으면 '수집했는데 0건'과 '안 넣었다'가 섞인다."""
    import app.collectors.news_rss as nr

    async def _fake(jg, redis=None, *, limit=12):
        return [{"title": "a", "url": "u", "team": "Kia Tigers"}]

    monkeypatch.setattr(nr, "for_game", _fake)
    out = await nr.by_side({"sport": "kbo", "home": "Kia Tigers",
                            "away": "KT Wiz"}, None)
    assert "away" not in out


def test_merge_fills_only_present_sides():
    from app.collectors.news_rss import merge_into_research

    r = {}
    filled = merge_into_research(r, {"home": "A", "away": "B"},
                                 {"home": [{"title": "t", "url": "u"}]})
    assert filled == ["home_news"]
    assert r["home_news"][0]["title"] == "t"
    assert "away_news" not in r


# ─────────────────── 창 ───────────────────

def test_window_is_enforced_in_one_place_only():
    """72시간 창을 두 곳에서 자르면 어느 쪽이 실제 창인지 알 수 없다."""
    import inspect

    from app.collectors.news_rss import MAX_AGE_HOURS, by_side

    assert MAX_AGE_HOURS == 72
    src = code_only("import x\n" + inspect.getsource(by_side).lstrip())
    assert "MAX_AGE_HOURS" not in src and "72" not in src


# ─────────────────── 자료2 도달 ───────────────────

def test_material2_reads_the_tag_the_form_produces():
    """자료2 는 기사가 아니라 팀 폼이 만든 태그다 — 경로를 고정한다."""
    import inspect

    from app.engine.matchup import news_payload

    src = inspect.getsource(news_payload)
    assert '"뉴스태그"' in src


def test_form_prompt_receives_the_headlines():
    """팀 폼이 실제로 그 키를 읽는다(주입 대상이 맞는지 확인)."""
    src = Path("app/engine/team_form.py").read_text(encoding="utf-8")
    assert 'research.get(f"{side}_news")' in src
