"""🔴🔴 **v5 게이트 2 — §3-2 도구를 실제 통로에 꽂는다.**

카드가 스스로 적고 있던 줄:

```
⚠️ §3 에이전트 **도구 미배선** — 스키마·프롬프트·예산은 섰고
   `Tools.search`/`fetch` 가 실제 통로에 아직 안 꽂혔다(§3-2).
```

══════════════════════════════════════════════════════════════════
🔴 **무엇을 꽂나** — 새로 긁지 않는다
══════════════════════════════════════════════════════════════════

⚠️ 세포들이 이미 검색하고 본문을 받는다(깔때기 `queries` 23 · `fetched` 107 ·
   실측 2026-10-04). 🔴 에이전트가 **또 긁으면** 같은 페이지를 두 배로 두드리고
   예산이 두 배가 된다.

🔴 그래서 꽂는 것은 **세포가 이미 받아 둔 것**이다:

    search  →  그 경기에서 **본 검색 결과**(URL·제목·스니펫)
    fetch   →  그 URL 의 **이미 받아 둔 본문**

⚠️ 그래야 §4-4(*"검색 결과에 있던 URL 만"*)가 **자연히** 지켜진다 — 캐시에
   없는 URL 은 애초에 줄 것이 없다.
🔴 그리고 §5-1(인용 대조)이 **그 본문으로** 돈다 — 받아 두지 않은 본문에 대고
   인용을 검증할 수는 없다(그것이 `verifylayer` 의 fail-closed 다).
"""
from __future__ import annotations

import pytest


def test_v5_3_2_세포가_받은_것을_모은다():
    """🔴 깔때기처럼 **한 곳에 모은다** — 세포마다 흩어지면 줄 수가 없다."""
    from app.cells import Seen
    seen = Seen()
    assert seen.urls == [] and seen.bodies == {}
    seen.add_hit("https://a/1", title="제목", snippet="조각", query="q1")
    seen.add_body("https://a/1", "본문이다")
    assert seen.urls == ["https://a/1"]
    assert seen.bodies["https://a/1"] == "본문이다"
    # 🔴 같은 URL 을 두 번 넣어도 **한 건**이다
    seen.add_hit("https://a/1", title="다시", snippet="", query="q2")
    assert seen.urls == ["https://a/1"]
    # ⚠️ 빈 URL·빈 본문은 **안 넣는다**(없는 것을 있는 척하지 않는다)
    seen.add_hit("", title="x", snippet="")
    seen.add_body("https://b/2", "")
    assert seen.urls == ["https://a/1"] and "https://b/2" not in seen.bodies


def test_v5_3_2_search_가_받아_둔_결과를_낸다():
    """🔴 `Tools.search` 가 **빈 목록**이 아니라 그 경기에서 본 것을 낸다."""
    from app import agentloop
    from app.cells import Seen
    seen = Seen()
    seen.add_hit("https://mlb.com/a", title="Brewers rotation",
                 snippet="Henderson will start", query="Brewers rotation")
    tools = agentloop.Tools(inp=_inp(), seen=seen)
    got = tools.search("Milwaukee Brewers San Diego Padres MLB baseball")
    assert got["ok"] is True, got
    assert got["hits"], (
        "🔴 `Tools.search` 가 여전히 **빈 목록**을 낸다 — 도구가 안 꽂혔다")
    first = got["hits"][0]
    assert first["url"] == "https://mlb.com/a"
    assert "Brewers" in first["title"]
    # 🔴 그리고 `seen_urls` 가 **그 URL 로 채워진다**(§4-4 가 그것을 쓴다)
    assert "https://mlb.com/a" in tools.seen_urls


def test_v5_3_2_fetch_가_받아_둔_본문을_낸다():
    """🔴 `Tools.fetch` 가 **이미 받은 본문**을 돌려준다(다시 긁지 않는다)."""
    from app import agentloop
    from app.cells import Seen
    seen = Seen()
    seen.add_hit("https://mlb.com/a", title="t", snippet="s", query="q")
    seen.add_body("https://mlb.com/a", "Henderson will start on Saturday.")
    tools = agentloop.Tools(inp=_inp(), seen=seen)
    tools.search("Milwaukee Brewers San Diego Padres MLB baseball")
    got = tools.fetch("https://mlb.com/a")
    assert got["ok"] is True, got
    assert "Henderson" in got["body"], got


def test_v5_3_2_안_받은_URL_은_거절한다():
    """🔴 §4-4 — *"검색 결과에 있던 URL 만"*. ⚠️ 캐시가 그것을 **자연히** 지킨다."""
    from app import agentloop
    from app.cells import Seen
    tools = agentloop.Tools(inp=_inp(), seen=Seen())
    got = tools.fetch("https://evil.example/x")
    assert got["ok"] is False
    assert "검색 결과에 없던" in got["why"], got


def test_v5_3_2_본문이_없으면_그렇게_말한다():
    """🔴 URL 은 봤는데 **본문을 못 받은** 경우 — 0 으로 때우지 않는다(#3)."""
    from app import agentloop
    from app.cells import Seen
    seen = Seen()
    seen.add_hit("https://mlb.com/a", title="t", snippet="s", query="q")
    tools = agentloop.Tools(inp=_inp(), seen=seen)
    tools.search("Milwaukee Brewers San Diego Padres MLB baseball")
    got = tools.fetch("https://mlb.com/a")
    assert got["ok"] is False
    assert "본문" in got["why"], got


@pytest.mark.asyncio
async def test_v5_3_2_세포가_실제로_모은다():
    """🔴🔴 **실물로 돌린다** — `Cell` 을 돌려 `Seen` 이 차는지 본다(#2).

    ══════════════════════════════════════════════════════════════════
    🔴 **첫 판이 돌연변이 D 를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    `for h in (hits or []):` 를 `for h in []:` 로 바꿔도 **초록이었다** — 내
    계약이 AST 로 *"`add_hit` 를 부르는 줄이 있나"* 만 봤고, 그 줄은 **남아
    있었다**(한 번도 안 돌 뿐이다).
    🔴 §9-5: *"`if False` 로 꺼도 문자열 grep 이 통과하는 돌연변이는 무효"* —
       그 금지가 AST 에도 그대로다. **돌려서 수를 본다.**
    """
    from app.cells import Cell, Question, Seen, Source
    from app.net import Net
    from app.search import Hit

    class _Search:
        #: 🔴 세포가 **이 칸을 본다** — 없으면 *"검색 수단 미정"* 으로 멈춘다
        available = True

        async def query(self, text, *, lang="ko", **kw):
            # 🔴 제목에 **팀 이름 전체**를 둔다 — `_open_hits` 가 그것으로
            #    *"우리 팀 기사인가"* 를 가린다(§17-g-3). ⚠️ 별칭은
            #    `entities.yaml` 에 선언된 팀만 통한다.
            return [Hit(url="https://mlb.com/seen-1",
                        title="Milwaukee Brewers rotation plan",
                        snippet="Logan Henderson will start")]

    class _Net(Net):
        def __init__(self):
            pass

        async def get(self, url, **kw):
            class _R:
                status = 200
                #: ⚠️ `Cell` 이 보는 칸이다 — 없으면 `AttributeError` 다
                dead = False
                reason = ""
                text = ("<html><body><article><p>"
                        + ("Henderson will start on Saturday against the "
                           "Padres. " * 12)
                        + "</p></article></body></html>")
                url = "https://mlb.com/seen-1"
                headers: dict = {}
            return _R()

    from app.blackboard import Blackboard
    seen = Seen()
    q = Question("lineup", "MLB:Brewers:seen", team="Milwaukee Brewers",
                 league="MLB", opponent="San Diego Padres")
    # 🔴 §4-1 — **조각을 선언한다**(세포도 그렇게 한다 · `Source.parts`).
    #    ⚠️ 안 주면 문지기가 글에서 짐작하고 팀 이름은 **보이지 않는다**.
    src = Source("시험", "search",
                 query="Milwaukee Brewers San Diego Padres MLB baseball",
                 parts={"team": "Milwaukee Brewers",
                        "opponent": "San Diego Padres", "competition": "MLB"},
                 # 🔴 **본문을 연다** — 스니펫만 보는 소스는 본문이 없다.
                 #    ⚠️ 그 문은 `parse_body` **또는** `extract_tasks` 를
                 #       요구한다(§19-b-2) — 추출기 쪽을 쓴다(카탈로그 소스가
                 #       그 꼴이다: 규칙 파서 없이 산문을 겨냥한다).
                 open_body=True, extract_tasks=("lineup",))
    cell = Cell(q, [src], seen=seen)
    await cell.run(_Net(), Blackboard(), search=_Search())
    assert seen.urls, (
        "🔴 세포가 `Seen` 에 **안 적었다** — 에이전트는 영원히 빈손이다")
    assert "https://mlb.com/seen-1" in seen.urls
    # 🔴 본문도 모였나 — URL 만 모으면 §5-1 인용 대조를 못 한다
    assert seen.bodies, "🔴 본문이 **안 모였다**(§5-1 이 대조할 글이 없다)"
    assert "Henderson" in next(iter(seen.bodies.values()))


def test_v5_3_2_없는_조각을_선언하지_않는다():
    """🔴🔴 **돌연변이 H 가 통과했다**(2026-10-04).

    `_parts` 의 *"그 글자가 질의에 실제로 있나"* 검사를 끄면 **없는 조각을
    선언한다** — 그러면 §4-1 문지기가 **속는다.** 이름 하나짜리 질의가
    *"세 요소"* 로 통과하고, 쓰레기 86% 가 돌아온다(M33).
    """
    from app import agentloop
    tools = agentloop.Tools(inp=_inp())
    # 🔴 **아무 이름도 없는** 질의 — 선언할 조각이 없다
    assert tools._parts("오늘 경기") == {}
    # ⚠️ 한쪽만 들었으면 **한 조각**이다
    got = tools._parts("Milwaukee Brewers lineup")
    assert set(got) == {"team"}, got
    # 🔴 둘 다·대회까지 들었으면 셋이다
    got3 = tools._parts("Milwaukee Brewers San Diego Padres MLB")
    assert set(got3) == {"team", "opponent", "competition"}, got3
    # 🔴🔴 그리고 **문지기가 실제로 거부한다** — 선언이 거짓이면 통과해 버린다
    bad = tools.search("오늘 경기")
    assert bad["ok"] is False, bad
    assert bad["reason"] == "query_too_bare", bad


def test_v5_3_2_카드가_미배선이라고_적지_않는다():
    """🔴 꽂았으면 **그 줄이 사라져야** 한다 — 아니면 카드가 거짓을 적는다.

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다.
    """
    import pathlib

    from tests._helpers import strip_docs
    body = strip_docs(pathlib.Path("app/analyze.py").read_text())
    assert "도구 미배선" not in body, (
        "🔴 도구를 꽂았는데 카드가 아직 *'도구 미배선'* 을 적는다")


def _inp():
    from datetime import datetime, timedelta, timezone

    from app import agentloop
    return agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers",), away_names=("San Diego Padres",),
        competition="MLB", sport="baseball",
        kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        venue="American Family Field", langs=("en",))
