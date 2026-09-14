"""SCT-7 — Google News RSS 가 축구 검색의 **1순위 통로**다.

🔴 실측 2026-09-14: DDG(토르)는 경기당 2질의에도 403 을 줬다. RSS 는 무료·
   pubDate 포함이라 날짜 문을 대신할 증거가 붙어 온다.

⚠️ BASE·UA·파서를 새로 만들지 않는다 — `news_rss` 가 원본이다.
"""
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors import satellite as SAT
from app.collectors import satellite_soccer as SOC
from app.engine import scout_config as SC

NOW = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
KICK = NOW + timedelta(hours=16)

FEED = """<rss><channel>
<item><title>Torino, formazioni ufficiali - Fantacalcio</title>
<link>https://news.google.com/rss/articles/AAA</link>
<pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate>
<source url="https://www.fantacalcio.it">Fantacalcio</source></item>
<item><title>Ricetta tiramisu - Cucina</title>
<link>https://news.google.com/rss/articles/BBB</link>
<pubDate>Mon, 14 Sep 2026 07:00:00 GMT</pubDate>
<source url="https://www.cucina.it">Cucina</source></item>
</channel></rss>"""


class _Resp:
    status_code = 200
    text = FEED

    def raise_for_status(self):
        pass


def _client(sent):
    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **k):
            sent.append((url, params))
            return _Resp()

    return _C


def test_로케일은_검색어표가_정한다():
    """🔴 ceid 는 표에 적지 않는다 — {gl}:{hl 앞 2자} 로 만든다(사본 금지)."""
    assert SC.locale("serie_a") == {"hl": "it", "gl": "IT", "ceid": "IT:it"}
    assert SC.locale("kbo") == {"hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    assert SC.locale("없는리그") is None


@pytest.mark.asyncio
async def test_RSS_는_현지어_로케일로_부르고_매체_도메인을_싣는다(monkeypatch):
    sent: list = []
    monkeypatch.setattr("httpx.AsyncClient", _client(sent))

    hits = await SAT.rss_hits("Torino formazioni ufficiali", league="serie_a",
                              stage="lineup", now=NOW)

    url, params = sent[0]
    assert url.startswith("https://news.google.com/rss/search")
    assert params["hl"] == "it" and params["gl"] == "IT" and params["ceid"] == "IT:it"
    # 🔴 link 는 news.google.com 리다이렉트다. 등급은 매체 도메인으로 본다.
    assert hits[0]["source_url"].endswith("fantacalcio.it")
    assert isinstance(hits[0]["published"], datetime), "screen 이 RSS 를 가르는 근거"


@pytest.mark.asyncio
async def test_등급은_구글_링크가_아니라_매체로_본다(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr("httpx.AsyncClient", _client([]))

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)

    out = await SAT.rss_supplement({"home": "Torino FC", "away": "AS Roma"},
                                   [("Torino", "q")], league="serie_a",
                                   stage="lineup", kickoff=KICK, now=NOW)

    # fantacalcio = tier2 → 열린다. cucina = 미상 + 팀 없음 → 안 열린다.
    assert opened == ["https://news.google.com/rss/articles/AAA"]
    assert len(out) == 1


def test_축구_수집이_RSS_를_먼저_부르고_토르는_폴백이다():
    src = inspect.getsource(SOC.gather_soccer)
    i_rss, i_tor = src.index("rss_supplement("), src.index("_tor_supplement(")
    assert i_rss < i_tor, "RSS 가 먼저다"
    # 🔴 토르는 RSS 가 0건일 때만 — 그 조건이 코드에 있어야 한다.
    assert "if not _rss:" in src


def test_RSS_기본값을_손으로_적지_않는다():
    """BASE·UA·파서는 news_rss 가 원본이다(사본 금지)."""
    import ast

    src = inspect.getsource(SAT.rss_hits)
    tree = ast.parse(src.lstrip())
    # ⚠️ 주석은 세지 않는다 — **문자열 상수**에 URL 이 박혔는지만 본다.
    lits = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("news.google.com/rss" in x for x in lits), "BASE 를 베끼지 않는다"
    imported = {a.name for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module == "app.collectors.news_rss"
                for a in n.names}
    assert {"BASE", "UA", "parse_feed"} <= imported


# ── SCT-8: 대진 질의 먼저, 팀 질의는 모자랄 때만

@pytest.mark.asyncio
async def test_대진_기사는_양_팀_모두의_재료다(monkeypatch):
    """🔴 "Torino-Roma: le probabili formazioni" 는 두 팀 다 설명한다.
    본문은 한 번만 열고 행만 둘로 만든다 — 추출이 팀으로 기사를 고른다."""
    opened: list[str] = []
    monkeypatch.setattr("httpx.AsyncClient", _client([]))

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
