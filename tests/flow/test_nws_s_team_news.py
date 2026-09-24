"""[NWS-S] 팀별 RSS 를 ⑤에 잇는다 — **이미 있던 것을 안 부르고 있었다.**

사용자 2026-09-24: "기존에 rss로 모으는거 있지 않았니?"

🔴 있었다. `news_rss` 가 팀별 구글 뉴스를 긁고 **구경로만** 쓰고 있었다.
   흐름은 크롤러의 **리그 Bing 검색**만 봤고 그쪽은 기사가 오래됐다:
```
크롤러 Bing 리그 검색   기사 6~9일 전 → ②news_dir 8/8 = 0 · ⑤ news_injury 미상
news_rss 팀별 질의      **0.3h ~ 5.6h** (실측 2026-09-24 KBO 3경기 68건)
   [away] 4.9h  최원태, … 하필 지금 부상 이탈→어차피 10월 복귀니까
```
   같은 "RSS" 라도 **질의가 팀별이면 신선하다** — F-24 를 이 실측이 정정한다.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow import attribution as A


# ── 낱말 판정을 꺼낸 것이 사본을 만들지 않았나 ──────────────────────

def test_낱말_판정이_한_곳이다():
    """🔴 `direction_of` 가 `tone_of` 를 쓴다 — 두 벌이 되면 한쪽만 고쳐진다."""
    src = inspect.getsource(A.direction_of)
    assert "tone_of(" in src
    assert "LEXICON_DIR" not in src, "낱말 표를 두 곳에서 읽는다"


def test_악재_호재가_같이_있으면_모른다():
    assert A.tone_of("부상 딛고 복귀") is None
    assert A.tone_of("라팍 53번째 만원 관중") is None
    assert A.tone_of("최원태, 하필 지금 부상 이탈") == {"dir": -1, "word": "부상"}
    assert (A.tone_of("주전 포수 1군 등록") or {}).get("dir") == +1


# ── 쪽이 정해진 기사표 ─────────────────────────────────────────────

def test_쪽은_질의가_정한다():
    """🔴 제목에서 팀을 다시 찾지 않는다 — 한국어 기사 제목에는 영문
    팀명이 없다. `by_side` 가 질의 팀명으로 이미 갈라 놨다."""
    got = A.news_dir_sided({
        "home": [{"title": "최원태, 하필 지금 부상 이탈", "age_h": 4.9}],
        "away": [{"title": "라팍 53번째 만원 관중", "age_h": 5.6}]})
    assert got == {"home": -1, "away": 0,
                   "basis": "부상 — 최원태, 하필 지금 부상 이탈"}


def test_한_팀에_둘_다_오면_상쇄다():
    """⚠️ `news_dir` 과 같은 규약 — 억지로 하나를 고르지 않는다."""
    got = A.news_dir_sided({"home": [{"title": "에이스 부상 이탈", "age_h": 1},
                                     {"title": "4번 타자 1군 등록", "age_h": 2}]})
    assert got["home"] == 0
    assert got["basis"], "무엇을 봤는지는 남긴다"


def test_기사가_없으면_None():
    assert A.news_dir_sided({}) is None
    assert A.news_dir_sided({"home": [], "away": []}) is None
    assert A.news_dir_sided({"home": [{"title": "관중 기록", "age_h": 1}]}) is None


def test_창을_두_벌_만들지_않았다():
    """⚠️ F-19 가 지적한 자리 — 기본은 자르지 않는다(72h 는 `parse_feed`)."""
    arts = {"home": [{"title": "에이스 부상 이탈", "age_h": 50}]}
    assert A.news_dir_sided(arts)["home"] == -1
    assert A.news_dir_sided(arts, max_age_h=24) is None


# ── 배선의 끝 ──────────────────────────────────────────────────────

def _code_only(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def test_다섯번_노드가_실제로_부른다():
    from app.flow.nodes import n05_evidence as E

    code = _code_only(E.run)
    assert "_news_rss_dir" in code, "만들어 놓고 안 부른다"
    helper = _code_only(E._news_rss_dir)
    assert "news_rss" in helper and "by_side" in helper
    assert "news_dir_sided" in helper
    # 🔴 종목 목록을 손으로 적지 않는다 — LOCALE 이 원본이다
    assert "LOCALE" in helper
    assert '"kbo"' not in helper and "'kbo'" not in helper


@pytest.mark.asyncio
async def test_시장_경로를_치우지_않았다(monkeypatch):
    """🔴 ②가 방향을 냈으면 그것을 쓴다 — 배당 이동과 **시각을 맞춘** 것은
    ②뿐이다. 팀 뉴스는 그것이 비었을 때의 보조다."""
    from app.flow.nodes import n05_evidence as E

    called = []

    async def spy(state, ctx):
        called.append(1)
        return {"home": -1, "away": 0, "basis": "보조"}

    monkeypatch.setattr(E, "_news_rss_dir", spy)
    src = _code_only(E.run)
    i_mkt = src.index('news_dir')
    i_rss = src.index("_news_rss_dir")
    assert i_mkt < i_rss, "②보다 먼저 팀 뉴스를 본다"


@pytest.mark.asyncio
async def test_종목이_없으면_긁지_않는다(monkeypatch):
    """⚠️ 축구는 `news_rss.LOCALE` 에 없다 — 헛질의를 보내지 않는다."""
    from app.flow.nodes import n05_evidence as E

    hit = []

    async def boom(*a, **k):
        hit.append(1)
        raise AssertionError("긁으면 안 된다")

    monkeypatch.setattr("app.collectors.news_rss.by_side", boom)

    class _S:
        game_id = "1"
        sport = "soccer"
        league = "EPL"
        home = "Arsenal FC"
        away = "Chelsea FC"

    class _C:
        redis = None

    assert await E._news_rss_dir(_S(), _C()) is None
    assert hit == []


@pytest.mark.asyncio
async def test_조회_실패가_흐름을_죽이지_않는다(monkeypatch):
    from app.flow.nodes import n05_evidence as E

    async def boom(*a, **k):
        raise RuntimeError("망")

    monkeypatch.setattr("app.collectors.news_rss.by_side", boom)

    class _S:
        game_id = "1"
        sport = "baseball"
        league = "KBO"
        home = "KT Wiz"
        away = "NC Dinos"

    class _C:
        redis = None

    assert await E._news_rss_dir(_S(), _C()) is None
