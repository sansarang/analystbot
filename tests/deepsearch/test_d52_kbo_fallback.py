"""[D52] **소스를 끌 때 '대체가 있다'고 적었는데 아무도 안 부르고 있었다.**

🔴 실측 2026-09-22 10:29 KST (오늘 경기 `KT Wiz @ SSG Landers` 18:30):

    gather_kbo → 기사 **0건** (다음 검색 8회 전부 SourceDisabled)
    gather_npb → 기사 9건

   DEC-2 커밋과 `source_gate.REASONS["daum_search"]` 는
   "DS-3 이 기사 검색을 Bing 으로 갈았으므로 **대체가 있다**"고 적었다.
   그 문장이 **틀렸다** — `rss_hits`(Bing) 를 부르는 곳은 축구
   (`satellite_soccer.gather_soccer` → `rss_supplement`) 뿐이고,
   `gather_kbo` 는 `_daum_fetch` 하나만 쓴다. 끈 순간 KBO 기사가 0 이 됐다.

🔴 **어제 계약이 통과한 이유** — '차단'만 시험하고 '대체'를 시험하지 않았다.
   `require("daum_search")` 가 요청을 막는지는 쟀지만, 막힌 자리를 **무엇이
   메우는지**는 아무도 안 쟀다. 그래서 5,519건이 이 회귀를 통과했다.

여기 두 계약은 그 둘을 **따로** 시험한다:
  1. `test_kbo_gather_uses_rss_when_daum_disabled` — 다음이 꺼진 상태에서
     `rss_hits` 가 **실제로 나가고** 기사가 카드 재료로 들어온다.
  2. `test_disabled_source_has_wired_fallback` — 꺼진 소스마다 설정에
     `fallback` 이 적혀 있고, 그 대체가 **소비처에서 호출 그래프로 닿는다.**
     ⚠️ "함수가 존재한다"로는 D52 를 못 잡는다 — `rss_hits` 는 존재했고
        축구에서 불리고 있었다. 막힌 **소비처에서 닿는가**를 본다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

#: 🔴 실제 Bing 응답 모양(`tests/deepsearch/test_ds3_wire.py` 와 같은 출처).
#  ⚠️ 제목에 **한국어 별칭**이 들어 있어야 `_mentions_team` 을 지난다 —
#     우리 DB 표기는 `SSG Landers` 지만 한국 매체 제목은 `SSG 랜더스` 다.
BING_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:News="https://www.bing.com:443/news/search">
<channel><title>SSG 랜더스 - Bing뉴스</title>
<item><title>SSG 랜더스 선발 라인업 발표</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.osen.co.kr%2farticle%2fG1&amp;c=1</link>
<description>SSG 랜더스가 라인업을 발표했다.</description>
<News:Source>OSEN</News:Source>
<pubDate>{PUB}</pubDate></item>
<item><title>KT 위즈 선발 예고</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.osen.co.kr%2farticle%2fG2&amp;c=2</link>
<description>KT 위즈 선발이 예고됐다.</description>
<News:Source>OSEN</News:Source>
<pubDate>{PUB}</pubDate></item>
</channel></rss>"""

ARTICLE_HTML = ("<html><body><p>" + ("기사 본문이다. " * 40) + "</p></body></html>")


class _FakeRss:
    """가짜 RSS 서버. 🔴 **요청 URL 을 전부 기록한다** — 나갔는지가 계약이다."""

    def __init__(self, pub: str):
        self.sent: list[str] = []
        self._pub = pub

    async def fetch(self, url, **kw):
        from app.deepsearch.runtime import Fetched

        self.sent.append(url)
        body = (BING_RSS.replace("{PUB}", self._pub) if "bing.com" in url
                else ARTICLE_HTML)
        return Fetched(url=url, status=200, body=body.encode())


@pytest.mark.asyncio
async def test_kbo_gather_uses_rss_when_daum_disabled(monkeypatch):
    """🔴 다음이 꺼져 있어도 KBO 기사가 **0 이 아니어야 한다.**"""
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    import app.collectors.satellite as SAT

    now = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
    fake = _FakeRss(format_datetime(now - timedelta(hours=2)))
    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: fake)
    # 다음은 **실제로 꺼진 상태**를 쓴다(설정을 흉내내지 않는다).
    from app.collectors import source_gate as SG

    assert not SG.enabled("daum_search"), "이 계약은 다음이 꺼진 상태를 전제한다"

    jg = {"home": "SSG Landers", "away": "KT Wiz",
          "starts_at": now + timedelta(hours=1)}
    out = await SAT.gather_kbo(jg, now=now)

    assert fake.sent, "요청이 아예 안 나갔다 — rss_hits 가 안 불렸다"
    assert [u for u in fake.sent if "bing.com" in u], fake.sent[:3]
    assert not [u for u in fake.sent if "search.daum.net" in u], "꺼진 소스로 나갔다"
    assert out, "다음이 꺼지자 KBO 기사가 0건이다 — D52 회귀"
    # 카드 재료의 모양(`_inject_articles` 가 읽는 키)을 지킨다
    assert set(out[0]) >= {"title", "url", "source", "team", "body"}
    assert out[0]["body"], "본문이 비어 있으면 추출이 no_article_text 로 멈춘다"
    teams = {a["team"] for a in out}
    assert teams <= {"SSG Landers", "KT Wiz"}, teams
    # 🔴 귀속은 **DB 표기**다 — 한국어 별칭으로 붙이면 경기와 못 맞춘다
    assert "랜더스" not in " ".join(teams)


# ── 계약 2 — 꺼진 소스마다 '대체'가 호출 그래프로 닿는가 ──────────────────

_APP = pathlib.Path(__file__).resolve().parents[2] / "app"


def _call_graph() -> dict:
    """`app/` 전체의 함수 → 그 안에서 부르는 이름들.

    🔴 이름 기준이다(완전하지 않다). 그래도 D52 는 잡는다 —
       `gather_kbo` 에서 `rss_hits` 로 가는 길이 **하나도 없었다.**
    """
    graph: dict = {}
    for p in sorted(_APP.rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            called = graph.setdefault(node.name, set())
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                f = sub.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
    return graph


def _reaches(graph: dict, start: str, target: str) -> bool:
    seen, queue = {start}, [start]
    while queue:
        cur = queue.pop()
        for nxt in graph.get(cur, ()):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def test_disabled_source_has_wired_fallback():
    """🔴 끈 소스의 '대체'는 **선언되고 닿아야** 한다.

    ⚠️ 대체가 없는 소스도 있다(KBO 공식 = D33). 그때는 `fallback: none` 과
       사유를 적게 한다 — **모른 채 비는 것과 알고 비는 것**은 다르다.
    """
    from app.engine import rules as R

    graph = _call_graph()
    block = R.get("sources") or {}
    checked = 0
    for name, row in sorted((block or {}).items()):
        if (row or {}).get("enabled", True):
            continue
        checked += 1
        fb = str((row or {}).get("fallback") or "").strip()
        assert fb, (f"sources.{name} 을 껐는데 `fallback` 이 없다 — "
                    "'대체가 있다'는 말은 설정에 적혀야 검증된다(D52)")
        if fb == "none":
            assert str((row or {}).get("fallback_reason") or "").strip(), (
                f"sources.{name}.fallback=none 인데 사유가 없다")
            continue
        func = fb.rsplit(".", 1)[-1]
        assert func in graph, f"sources.{name}.fallback={fb} 가 app/ 에 없다"
        consumers = [str(c) for c in ((row or {}).get("fallback_consumers") or [])]
        assert consumers, (f"sources.{name}.fallback 이 적혀 있는데 "
                           "`fallback_consumers` 가 없다 — 어디가 메우는지 "
                           "적지 않으면 D52 가 또 난다")
        for c in consumers:
            assert c in graph, f"소비처 {c} 가 app/ 에 없다"
            assert _reaches(graph, c, func), (
                f"🔴 {c} 에서 {func} 로 가는 호출 경로가 **없다** — "
                f"sources.{name} 을 끄면 {c} 는 빈손이 된다(D52 와 같은 결함)")
    assert checked, "꺼진 소스가 하나도 없다 — 이 계약이 아무것도 안 봤다"
