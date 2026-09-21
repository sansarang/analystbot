"""[DS-3a] 검색 경로를 **갈아 끼울 수 있게** 한다.

🔴 **왜 갈아야 했나.** 기사 검색의 기본 경로 `news.google.com/rss/search` 가
   **robots 거부**다(실측 2026-09-21: `*` 블록이 `Disallow: /` 이고 `/rss/` 를
   여는 Allow 줄이 없다. 게다가 `ClaudeBot`·`anthropic-ai` 를 **이름으로
   지목해** 막는다). 사용자가 대안을 정했다 — "체인은 bing으로".

🔴 **질의를 말없이 바꾸지 않는다.** 처음엔 "짧을수록 좋다"는 규칙을 넣으려
   했는데 실측이 뒤집었다:
     川崎フロンターレ        11항목/8최근 → 최신 「감독 교체책 반성」(쓸모없음)
     川崎フロンターレ スタメン  5항목/2최근 → 최신 「スタメン発表」(찾던 것)
   좁히면 **수는 줄고 정확도는 오른다.** "회수 수"가 잘못된 지표라는 뜻이다.
   → 규칙은 **오디션(DS-3a 3)** 이 정한다. 질의의 원본은 `search_terms.yaml`.

⚠️ 요청은 전부 DS-1 런타임을 지난다(robots·간격·상한·서킷).
⚠️ 검증 규칙을 새로 만들지 않는다 — `situation.is_recap`(경기 후 기사)과
   `situation.published_before`(시점)가 **원본**이다.
⚠️ 공급자 이름·순서는 `config/deepsearch.yaml` 의 `search.chain` 하나에서 온다.
   이 파일에는 등록표만 있고 **순서가 없다.**
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime

from app.deepsearch.runtime import Runtime, load_config

logger = logging.getLogger(__name__)


def _s(key, default=None):
    return ((load_config().get("search") or {}).get(key, default))


def _p(name, key, default=None):
    return ((_s("providers") or {}).get(name) or {}).get(key, default)


@dataclass
class Hit:
    url: str
    title: str = ""
    snippet: str = ""
    published_at: datetime | None = None
    content: str | None = None
    provider: str = ""
    raw: dict = field(default_factory=dict)


class BingNewsRSS:
    """robots 가 `/news/…` 를 막지 않는다(실측 2026-09-21 14:18).

    ⚠️ 링크가 `bing.com/news/apiclick.aspx` 리다이렉트다 — 원문 URL 이
       필요하면 **1회 추가 요청**이 든다. 여기서는 받은 그대로 싣고 원문
       해석은 부르는 쪽이 필요할 때 한다(비용을 숨기지 않는다).
    """

    name = "bing_news_rss"

    def __init__(self, *, runtime=None):
        self._rt = runtime or Runtime()

    @property
    def daily_query_cap(self):
        return _p(self.name, "daily_query_cap")

    async def search(self, *, query: str, market: str = "ko-KR",
                     since_hours: int | None = None,
                     max_results: int | None = None) -> list[Hit]:
        base = _p(self.name, "base") or "https://www.bing.com/news/search"
        url = (f"{base}?q={urllib.parse.quote(query)}"
               f"&format=RSS&setmkt={urllib.parse.quote(market)}")
        got = await self._rt.fetch(url)
        return parse_rss((got.body or b"").decode("utf-8", "replace"),
                         provider=self.name, limit=max_results)


class MediaRss:
    """매체 자체 RSS. 🔴 **검색이 아니다** — 최신 목록이라 "이 경기·이 선수"로
    물을 수 없다. 코드가 걸러야 하고 그만큼 회수가 낮다. 보조다."""

    name = "media_rss"

    def __init__(self, *, runtime=None, feeds=None):
        self._rt = runtime or Runtime()
        self._feeds = feeds if feeds is not None else (_p(self.name, "feeds") or [])

    @property
    def daily_query_cap(self):
        return _p(self.name, "daily_query_cap")

    async def search(self, *, query: str, market: str = "ko-KR",
                     since_hours: int | None = None,
                     max_results: int | None = None) -> list[Hit]:
        out: list[Hit] = []
        for feed in self._feeds:
            try:
                got = await self._rt.fetch(feed)
            except Exception as exc:
                logger.debug("[ds3a] 피드 실패 %s: %s", feed, exc)
                continue
            out.extend(parse_rss((got.body or b"").decode("utf-8", "replace"),
                                 provider=self.name))
        return out[:max_results] if max_results else out


#: 이름 → 구현. 🔴 **순서는 여기 없다** — config 가 정한다.
REGISTRY: dict = {}
for _cls in (BingNewsRSS, MediaRss):
    REGISTRY[_cls.name] = _cls

#: 유료 공급자가 살아나려면 이 환경변수가 있어야 한다(지시문 DS-3a 1).
KEY_ENV: dict = {"brave": "BRAVE_API_KEY", "firecrawl": "FIRECRAWL_API_KEY",
                 "parallel": "PARALLEL_API_KEY", "tavily": "TAVILY_API_KEY"}


def chain_names() -> list[str]:
    return list(_s("chain") or [])


def budget_usd(name: str) -> float:
    return float(_p(name, "monthly_budget_usd") or 0)


def is_free(name: str) -> bool:
    """과금 가능한가. 🔴 키를 요구하는 공급자는 **키가 곧 과금 통로**다."""
    return name not in KEY_ENV and budget_usd(name) == 0


def active_names() -> list[str]:
    """체인 중 **지금 실제로 쓸 수 있는** 것.

    ⚠️ 키 없는 유료 공급자는 빠진다 — 있는 척하면 상한 계산이 어긋난다.
    """
    out = []
    for n in chain_names():
        env = KEY_ENV.get(n)
        if env and not os.environ.get(env):
            continue
        if n not in REGISTRY and not env:
            continue
        out.append(n)
    return out


def build(name: str, *, runtime=None):
    cls = REGISTRY.get(name)
    return None if cls is None else cls(runtime=runtime)


_USED: dict = {}


async def chain_search(query: str, *, market: str = "ko-KR",
                       since_hours: int | None = None,
                       max_results: int | None = None,
                       providers=None) -> list[Hit]:
    """앞에서부터 쓰고, **상한에 닿으면 다음으로 넘어간다.**

    🔴 전부 막혀도 **예외가 아니라 빈손**이다 — 검색 실패가 슬레이트를 죽이면
       안 된다. 대신 사유는 로그에 남긴다(조용한 0 이 아니다).
    """
    own = providers is None
    chain = ([p for p in (build(n) for n in active_names()) if p is not None]
             if own else list(providers))
    for p in chain:
        cap = getattr(p, "daily_query_cap", None)
        used = _USED.get(p.name, 0) if own else getattr(p, "used", 0)
        if cap is not None and used >= int(cap):
            logger.info("[ds3a] %s 상한 도달(%s/%s) — 다음 공급자",
                        p.name, used, cap)
            continue
        try:
            hits = await p.search(query=query, market=market,
                                  since_hours=since_hours,
                                  max_results=max_results)
        except Exception as exc:
            logger.warning("[ds3a] %s 실패 — 다음 공급자: %s", p.name, exc)
            continue
        if own:
            _USED[p.name] = used + 1
        if hits:
            return hits
        logger.info("[ds3a] %s 빈손 — 다음 공급자", p.name)
    logger.warning("[ds3a] 모든 공급자가 빈손이다: %r", query[:60])
    return []


_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_TAG = {k: re.compile(rf"<{k}>(.*?)</{k}>", re.S)
        for k in ("title", "link", "description", "pubDate")}


def _unescape(s: str) -> str:
    import html

    return html.unescape((s or "").strip())


def parse_rss(text: str, *, provider: str = "", limit=None) -> list[Hit]:
    from email.utils import parsedate_to_datetime

    out: list[Hit] = []
    for block in _ITEM.findall(text or ""):
        def g(k, _b=None):
            m = _TAG[k].search(_b if _b is not None else block)
            return _unescape(m.group(1)) if m else ""

        try:
            pub = parsedate_to_datetime(g("pubDate")) if g("pubDate") else None
        except Exception:
            pub = None
        out.append(Hit(url=g("link"), title=g("title"), snippet=g("description"),
                       published_at=pub, provider=provider))
        if limit and len(out) >= limit:
            break
    return out


def verify(hits, *, sport: str, starts_at) -> tuple:
    """공급자가 준 것에도 **같은 검증**을 건다. 반환 `(통과, 버린 것)`.

    🔴 규칙을 여기서 만들지 않는다 — `situation.is_recap`(경기 후 기사)과
       `situation.published_before`(시점·창)가 원본이다(사본 금지).
    ⚠️ 버린 것을 **사유와 함께** 돌려준다. 몇 건을 왜 버렸는지 모르면
       회수율이 좋아 보이는 쪽을 고르게 된다 — 그게 오늘 실측이 경고한 것이다.
    """
    from email.utils import format_datetime

    from app.engine.situation import is_recap, published_before

    ok, dropped = [], []
    for h in hits:
        if is_recap(h.title or "", sport):
            dropped.append({"url": h.url, "reason": "post_match",
                            "title": h.title})
            continue
        # 🔴 **RFC 2822 문자열로 넘긴다.** `published_before` 는 그 형식만
        #    파싱하고, 못 파싱하면 "모르면 통과" 규칙에 따라 **True 를
        #    돌려준다**. datetime 이나 ISO 문자열을 주면 10일 전 기사도
        #    조용히 통과한다(실측 2026-09-21: datetime 10일 전 → True).
        #    ⚠️ 운영 캐시는 지금 RFC 2822 라 살아 있는 결함은 아니다
        #       (실측: analysis:* 의 published 159건 전부 파싱됨). 잠재 함정이다 → D37.
        raw = (format_datetime(h.published_at)
               if isinstance(h.published_at, datetime) else h.published_at)
        if not published_before({"published": raw}, starts_at, sport):
            dropped.append({"url": h.url, "reason": "out_of_window",
                            "title": h.title})
            continue
        ok.append(h)
    return ok, dropped
