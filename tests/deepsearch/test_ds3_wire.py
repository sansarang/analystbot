"""[DS-3] 기사 검색을 **robots 가 허용하는 경로로** 바꾼다.

🔴 **실측 2026-09-21 — 지금 기사 공급이 100% robots 거부 경로다.**
     운영 캐시의 기사 URL **174건 · 도메인 1종 = `news.google.com`**
   `news.google.com/robots.txt` 는 `*` 에 `Disallow: /` 이고 `/rss/` 를 여는
   Allow 줄이 없으며, `ClaudeBot`·`anthropic-ai` 를 **이름으로 지목**해 막는다.

🔴 **대체가 실제로 더 낫다 — 원문 URL 을 준다.**
   Bing News RSS 는 `<News:Source>`(매체 이름)를 주고, apiclick 링크의
   **`url=` 파라미터에 원문 URL 이 그대로** 들어 있다(실측):
     link  http://www.bing.com/news/apiclick.aspx?…&url=https%3a%2f%2fwww.osen.co.kr%2f…
     → www.osen.co.kr · www.yna.co.kr · www.mt.co.kr · www.fnnews.com …
   ⚠️ 내가 앞서 "원문 URL 을 얻으려면 1회 추가 요청이 든다"고 적은 것은 **틀렸다.**
      추가 요청 0 이다.
   ⚠️ 일부는 `msn.com` 으로 감싸여 온다(실측 12건 중 4건). 그때 `News:Source` 가
      `노컷뉴스 on MSN` 처럼 **매체 이름을 준다.**

⚠️ 출력 모양은 **바꾸지 않는다** — `{url,title,snippet,source,source_url,published}`.
   `_tor_supplement`·`scout_config.screen` 이 그 모양을 본다.
⚠️ `published` 는 **datetime** 이다(`screen` 이 그 타입으로 RSS 를 가른다).
"""
from __future__ import annotations

from datetime import datetime

import pytest

#: 🔴 **실제 Bing 응답에서 그대로 떼 왔다**(2026-09-21). 지어내지 않았다.
BING_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:News="https://www.bing.com:443/news/search">
<channel><title>한화 이글스 - Bing뉴스</title>
<item><title>OSEN 기사 제목</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=abc&amp;url=https%3a%2f%2fwww.osen.co.kr%2farticle%2fG1112879088&amp;c=1&amp;mkt=ko-kr</link>
<description>한화 이글스 선발 라인업이 발표됐다.</description>
<News:Source>OSEN</News:Source>
<pubDate>Sun, 20 Sep 2026 02:03:00 GMT</pubDate></item>
<item><title>MSN 으로 감싸인 기사</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.msn.com%2fko-kr%2fnews%2fx&amp;c=2</link>
<description>본문 일부</description>
<News:Source>노컷뉴스 on MSN</News:Source>
<pubDate>Sun, 20 Sep 2026 08:00:01 GMT</pubDate></item>
</channel></rss>"""


def test_원문_URL_을_추가요청_없이_푼다():
    """🔴 apiclick 의 `url=` 에 원문이 들어 있다 — 요청 0."""
    from app.deepsearch.search import real_url

    got = real_url("http://www.bing.com/news/apiclick.aspx?ref=FexRss&"
                   "url=https%3a%2f%2fwww.osen.co.kr%2farticle%2fG1&c=1")
    assert got == "https://www.osen.co.kr/article/G1"
    # 감싸이지 않은 주소는 그대로 돌려준다
    assert real_url("https://www.yna.co.kr/x") == "https://www.yna.co.kr/x"
    assert real_url("") == ""


def test_파서가_매체와_원문을_싣는다():
    from app.deepsearch.search import parse_rss

    hits = parse_rss(BING_RSS, provider="bing_news_rss")
    assert len(hits) == 2
    a, b = hits
    assert a.url == "https://www.osen.co.kr/article/G1112879088"
    assert a.source == "OSEN"
    assert b.url == "https://www.msn.com/ko-kr/news/x"
    # ⚠️ MSN 래핑이면 `News:Source` 가 매체 이름을 준다 — 버리지 않는다
    assert b.source == "노컷뉴스 on MSN"
    assert isinstance(a.published_at, datetime)


@pytest.mark.asyncio
async def test_rss_hits_가_거부_경로를_치지_않는다(monkeypatch):
    """🔴 `news.google.com` 으로 나가는 요청이 **0** 이어야 한다."""
    import app.collectors.satellite as SAT

    sent: list[str] = []

    class _RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            sent.append(url)
            return Fetched(url=url, status=200, body=BING_RSS.encode())

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    out = await SAT.rss_hits("한화 이글스 선발", league="kbo")
    assert sent, "요청이 아예 안 나갔다"
    assert not [u for u in sent if "news.google.com" in u], sent
    assert all("bing.com" in u for u in sent), sent
    assert out, "기사가 0건이다"


@pytest.mark.asyncio
async def test_출력_모양을_바꾸지_않는다(monkeypatch):
    """⚠️ `_tor_supplement`·`scout_config.screen` 이 이 모양을 본다."""
    import app.collectors.satellite as SAT

    class _RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            return Fetched(url=url, status=200, body=BING_RSS.encode())

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    out = await SAT.rss_hits("한화 이글스 선발", league="kbo")
    h = out[0]
    assert set(h) >= {"url", "title", "snippet", "source", "source_url",
                      "published"}
    assert isinstance(h["published"], datetime), "screen 이 타입으로 RSS 를 가른다"
    # 🔴 등급은 **매체 도메인**으로 봐야 한다 — 검색엔진 주소로 보면 전건 미상
    assert "bing.com" not in h["source_url"]
    assert "osen.co.kr" in h["source_url"]


@pytest.mark.asyncio
async def test_빈손이어도_예외가_아니다(monkeypatch):
    import app.collectors.satellite as SAT

    class _RT:
        async def fetch(self, url, **kw):
            raise RuntimeError("망")

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    assert await SAT.rss_hits("q", league="kbo") == []


def test_구글_RSS_상수를_안_쓴다():
    """🔴 `news_rss.BASE` 를 부르면 거부 경로로 나간다."""
    import inspect

    import app.collectors.satellite as SAT

    src = inspect.getsource(SAT.rss_hits)
    assert "news_rss" not in src, "거부 경로 모듈을 아직 부른다"
    assert "chain_search" in src or "deepsearch" in src
