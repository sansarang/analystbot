"""SCT-7 → **DS-3** — 현지어 RSS 가 축구 검색의 1순위 통로다.

🔴 실측 2026-09-14: DDG(토르)는 경기당 2질의에도 403 을 줬다. RSS 는 무료·
   pubDate 포함이라 날짜 문을 대신할 증거가 붙어 온다. **그건 그대로다.**

🔴 **2026-09-21: 공급자를 Google News RSS → Bing News RSS 로 갈았다.**
   구글 쪽이 **robots 거부**이기 때문이다 — `*` 에 `Disallow: /` 이고 `/rss/`
   를 여는 Allow 줄이 없으며 `ClaudeBot`·`anthropic-ai` 를 이름으로 지목해
   막는다(원문 직접 수신). 실측: 운영 캐시의 기사 URL **174건 전부**가 그
   도메인이었다. 사용자 결정 "체인은 bing으로".

⚠️ 이 파일의 시험 대상은 **채널이 무엇이냐가 아니라** 그 채널이 지켜야 할
   것들이다 — 현지어 로케일 · **매체 도메인으로 등급** · 값을 손으로 안 적음 ·
   대진 기사는 두 팀의 재료. 그 넷은 그대로 두고 공급자만 바꿨다.
"""
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors import satellite as SAT
from app.collectors import satellite_soccer as SOC
from app.engine import scout_config as SC

NOW = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
KICK = NOW + timedelta(hours=16)

#: 🔴 Bing News RSS 의 실제 모양이다 — apiclick 링크의 `url=` 에 **원문 URL**
#   이 들어 있고, `<News:Source>` 가 매체 이름을 준다(실측 2026-09-21).
FEED = """<rss version="2.0" xmlns:News="https://www.bing.com:443/news/search">
<channel>
<item><title>Torino, formazioni ufficiali - Fantacalcio</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.fantacalcio.it%2fAAA&amp;c=1</link>
<description>Le probabili formazioni</description>
<News:Source>Fantacalcio</News:Source>
<pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate></item>
<item><title>Ricetta tiramisu - Cucina</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.cucina.it%2fBBB&amp;c=2</link>
<description>Dolce</description>
<News:Source>Cucina</News:Source>
<pubDate>Mon, 14 Sep 2026 07:00:00 GMT</pubDate></item>
</channel></rss>"""


def _client(sent):
    """DS-1 런타임 대역. 🔴 **요청이 어디로 나갔는지** 센다."""
    class _RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            sent.append(url)
            return Fetched(url=url, status=200, body=FEED.encode())

    return lambda *a, **k: _RT()


def test_로케일은_검색어표가_정한다():
    """🔴 ceid 는 표에 적지 않는다 — {gl}:{hl 앞 2자} 로 만든다(사본 금지)."""
    assert SC.locale("serie_a") == {"hl": "it", "gl": "IT", "ceid": "IT:it"}
    assert SC.locale("kbo") == {"hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    assert SC.locale("없는리그") is None


@pytest.mark.asyncio
async def test_RSS_는_현지어_로케일로_부르고_매체_도메인을_싣는다(monkeypatch):
    sent: list = []
    monkeypatch.setattr("app.deepsearch.search.Runtime", _client(sent))

    hits = await SAT.rss_hits("Torino formazioni ufficiali", league="serie_a",
                              stage="lineup", now=NOW)

    # 🔴 **거부 경로로 나가지 않는다**
    assert not [u for u in sent if "news.google.com" in u], sent
    # 현지어 로케일은 `scout_config.locale` 이 원본이다 — it/IT
    assert "setmkt=it-IT" in sent[0], sent[0]
    # 🔴 link 는 검색엔진 리다이렉트다. 등급은 **매체 도메인**으로 본다.
    assert hits[0]["source_url"].endswith("fantacalcio.it/AAA"), hits[0]
    assert isinstance(hits[0]["published"], datetime), "screen 이 RSS 를 가르는 근거"


@pytest.mark.asyncio
async def test_등급은_검색엔진_링크가_아니라_매체로_본다(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("app.deepsearch.search.Runtime", _client([]))

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)

    out = await SAT.rss_supplement({"home": "Torino FC", "away": "AS Roma"},
                                   [("Torino", "q")], league="serie_a",
                                   stage="lineup", kickoff=KICK, now=NOW)

    # fantacalcio = tier2 → 열린다. cucina = 미상 + 팀 없음 → 안 열린다.
    # fantacalcio = tier2 → 열린다. cucina = 미상 + 팀 없음 → 안 열린다.
    assert opened == ["https://www.fantacalcio.it/AAA"]
    assert len(out) == 1


def test_축구_수집이_RSS_를_먼저_부르고_토르는_폴백이다():
    src = inspect.getsource(SOC.gather_soccer)
    i_rss, i_tor = src.index("rss_supplement("), src.index("_tor_supplement(")
    assert i_rss < i_tor, "RSS 가 먼저다"
    # 🔴 토르는 RSS 가 0건일 때만 — 그 조건이 코드에 있어야 한다.
    assert "if not _rss:" in src


def test_RSS_기본값을_손으로_적지_않는다():
    """🔴 주소·공급자·신선도 상한을 `rss_hits` 에 박지 않는다.

    공급자와 순서의 원본은 `config/deepsearch.yaml` 의 `search.chain`,
    신선도는 `scout_config.MAX_AGE_H` 다(사본 금지).
    """
    import ast

    src = inspect.getsource(SAT.rss_hits)
    tree = ast.parse(src.lstrip())
    # ⚠️ 주석·docstring 은 세지 않는다 — **코드의 문자열 상수**만 본다.
    body = [n for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    lits = [n.value for n in body if len(n.value) < 200]
    for bad in ("news.google.com", "bing.com", "http"):
        assert not any(bad in x for x in lits), f"주소를 베꼈다: {bad}"
    assert "MAX_AGE_H" in src, "신선도 상한을 원본에서 읽어야 한다"
    assert "chain_search" in src, "공급자 체인을 거쳐야 한다"


# ── SCT-8: 대진 질의 먼저, 팀 질의는 모자랄 때만

@pytest.mark.asyncio
async def test_대진_기사는_양_팀_모두의_재료다(monkeypatch):
    """🔴 "Torino-Roma: le probabili formazioni" 는 두 팀 다 설명한다.
    본문은 한 번만 열고 행만 둘로 만든다 — 추출이 팀으로 기사를 고른다."""
    opened: list[str] = []
    monkeypatch.setattr("app.deepsearch.search.Runtime", _client([]))

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    stats: dict = {}

    out = await SAT.rss_supplement({"home": "Torino FC", "away": "AS Roma"},
                                   [(None, "Torino Roma probabili formazioni")],
                                   league="serie_a", stage="lineup",
                                   kickoff=KICK, now=NOW, stats=stats)

    assert len(opened) == 1, "본문은 한 번만 연다"
    assert sorted(a["team"] for a in out) == ["AS Roma", "Torino FC"]
    assert stats["hits"] == 2, "호출부가 '대진이 충분한가'를 볼 근거"


def test_대진이_충분하면_팀_질의를_생략한다():
    import inspect

    src = inspect.getsource(SOC.gather_soccer)
    assert "_pair_qs" in src and "PAIR_HITS_ENOUGH" in src
    # 🔴 상한을 코드에 적지 않는다 — scout_config 상수를 읽는다.
    assert "< 10" not in src
    assert src.index("_pair_qs") < src.index("PAIR_HITS_ENOUGH")
