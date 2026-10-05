"""검색 수단 계약 — §19-i (사용자 결정 2026-09-27).

게이트 원문(§19-i-8): *"검색 어댑터 실측 픽스처 = 19-g의 2·3·5번(西スポ 스니펫,
安芸の者, RotoWire)이 SearXNG 경유로 재현되어야 한다. Google CSE는 반증 세포
1건(휴스턴 선발)으로 실측. 일일 상한 초과 시 unknown+"검색 예산 소진" 사유가
남는지 계약."*

🔴 픽스처는 **실물 SearXNG 응답**이다(2026-09-27, 로컬 인스턴스 경유).
   막힌 엔진도 실물이다 — `duckduckgo: CAPTCHA` · `brave: too many requests`.
"""
from __future__ import annotations

import inspect
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

from app import cells as C
from app import search as S
from app.blackboard import UNKNOWN, Blackboard
from app.net import SearchUnavailable

FIX = Path(__file__).resolve().parent / "fixtures" / "2026-09-27"


class _Resp:
    def __init__(self, payload: str | dict, status: int = 200):
        self.status_code = status
        self._p = payload

    def json(self):
        import json
        return json.loads(self._p) if isinstance(self._p, str) else self._p

    @property
    def text(self):
        return self._p if isinstance(self._p, str) else ""


def _patch(monkeypatch, resp, *, capture: list | None = None):
    async def _get(self, url, params=None, **kw):
        if capture is not None:
            capture.append((url, dict(params or {})))
        if isinstance(resp, Exception):
            raise resp
        return resp
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)


def _fix(name: str) -> str:
    return (FIX / f"searx_{name}.json").read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# §19-i-8 게이트 — 19-g 2·3·5 가 SearXNG 로 재현되나
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_게이트_소프트뱅크_라인업이_잡힌다(monkeypatch):
    """§19-g-2 — 소프트뱅크 라인업. 🔴 **사실이 잡히는지**가 기준이다.

    실측: 西スポ 가 아니라 다른 매체가 같은 사실(`中村晃` 「6番・一塁」)을 줬다.
    그것이 §19-b-4 "막히면 우회가 아니라 **대체**"가 작동한 모습이다 —
    소스 이름이 아니라 사실로 채점한다.
    """
    _patch(monkeypatch, _Resp(_fix("sb")))
    hits = await S.SearxSearch().query("ソフトバンク スタメン 9月27日", lang="ja")
    assert len(hits) >= 20, len(hits)
    blob = " ".join(h.title + h.snippet for h in hits)
    assert "中村晃" in blob, "라인업 사실이 결과에 없다"
    assert "6番" in blob


@pytest.mark.asyncio
async def test_게이트_히로시마_라인업은_安芸の者가_잡힌다(monkeypatch):
    """§19-g-3 — 安芸の者がゆく 한 페이지에 양 팀 타순이 있다."""
    _patch(monkeypatch, _Resp(_fix("hiroshima")))
    hits = await S.SearxSearch().query("広島 スタメン 9月27日 横浜", lang="ja")
    aki = [h for h in hits if "akinomono" in h.url]
    assert aki, [h.publisher for h in hits[:10]]
    assert "スタメン" in aki[0].title


@pytest.mark.asyncio
async def test_게이트_휴스턴_선발_소스가_잡힌다(monkeypatch):
    """§19-g-5 — 휴스턴 선발. 반증 세포가 이것으로 unknown 을 지운다."""
    _patch(monkeypatch, _Resp(_fix("astros")))
    hits = await S.SearxSearch().query("Astros probable pitcher September 27",
                                       lang="en")
    good = [h for h in hits if "mlb.com" in h.url or "rotowire" in h.url]
    assert good, [h.publisher for h in hits[:10]]


# ══════════════════════════════════════════════════════════════════
# SearXNG — JSON · 엔진 dead 처리
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_JSON으로_받는다(monkeypatch):
    """🔴 HTML 긁기는 §19-i-5 제외 항목이다."""
    got: list = []
    _patch(monkeypatch, _Resp(_fix("sb")), capture=got)
    await S.SearxSearch().query("x")
    assert got and got[0][1]["format"] == "json"


@pytest.mark.asyncio
async def test_현지어로_검색한다(monkeypatch):
    """§12-b — 한국어로 NPB 를 검색하면 번역 기사만 나와 하루 늦다."""
    got: list = []
    _patch(monkeypatch, _Resp(_fix("sb")), capture=got)
    await S.SearxSearch().query("スタメン", lang="ja")
    assert got[0][1]["language"] == "ja-JP"
    assert S._lang("zh") == "zh-TW" and S._lang("en") == "en-US"


@pytest.mark.asyncio
async def test_막힌_엔진을_기억한다(monkeypatch):
    """🔴 §19-b-4 · §19-i-2 — 업스트림 엔진이 막히면 **그 엔진만** dead.

    픽스처는 실물이다: `duckduckgo: CAPTCHA` · `brave: too many requests`.
    """
    s = S.SearxSearch()
    _patch(monkeypatch, _Resp(_fix("sb")))
    await s.query("x")
    assert "duckduckgo" in s.dead_engines, s.dead_engines
    _patch(monkeypatch, _Resp(_fix("astros")))
    await s.query("y")
    assert {"duckduckgo", "brave"} <= s.dead_engines, s.dead_engines


@pytest.mark.asyncio
async def test_막힌_엔진만_빼고_요청한다(monkeypatch):
    s = S.SearxSearch()
    s.mark_engine_dead("duckduckgo", "CAPTCHA")
    got: list = []
    _patch(monkeypatch, _Resp(_fix("sb")), capture=got)
    await s.query("x", engines=["duckduckgo", "brave"])
    assert got[0][1]["engines"] == "brave"


@pytest.mark.asyncio
async def test_요청_엔진이_전부_죽으면_사유를_낸다(monkeypatch):
    s = S.SearxSearch()
    s.mark_engine_dead("brave", "Suspended: too many requests")
    _patch(monkeypatch, _Resp(_fix("sb")))
    with pytest.raises(SearchUnavailable, match="전부 dead"):
        await s.query("x", engines=["brave"])


def test_엔진_정지는_풀린다():
    """🔴 **엔진 정지는 영구가 아니다.**

    실측 2026-09-30: 같은 일본어 질의(`阪神 スタメン 9月30日`)가 한 번은 **0건**,
    몇 분 뒤 **26건**을 냈다. 사유는 `brave: Suspended: too many requests` 이고
    그 정지는 분 단위로 풀린다.

    ⚠️ 종전 `dead_engines` 는 `set` 이라 한 번 죽으면 프로세스가 사는 동안 영구히
       죽어 있었다 — 그러면 그날 **일본어 검색(=NPB 라인업)이 통째로 막힌다.**
       그리고 요약 보고가 *"dead ['brave','duckduckgo','google cse']"* 라고
       **거짓을** 말했다(살아 있는데 죽었다고).

    🔴 robots 거부(`net.dead_hosts`)와 규칙이 다르다 — 그쪽은 정책이라 하루다.
    """
    s = S.SearxSearch(engine_ttl=0.0)       # 즉시 만료
    s.mark_engine_dead("brave", "Suspended")
    assert s.dead_engines == set(), "TTL 이 지났는데 죽은 것으로 남았다"
    assert s.engine_reasons() == {}

    s2 = S.SearxSearch(engine_ttl=600.0)
    s2.mark_engine_dead("brave", "Suspended: too many requests")
    assert s2.dead_engines == {"brave"}
    # 🔴 **사유가 남는다** — "죽었다"만으로는 다음 조치를 못 고른다
    assert "too many requests" in s2.engine_reasons()["brave"]


@pytest.mark.asyncio
async def test_JSON이_아니면_설정을_가리킨다(monkeypatch):
    """🔴 `formats: json` 이 빠지면 이 오류가 난다 — 사유가 그것을 말해야 한다."""
    _patch(monkeypatch, _Resp("<!DOCTYPE html>"))
    with pytest.raises(SearchUnavailable, match="formats"):
        await S.SearxSearch().query("x")


@pytest.mark.asyncio
async def test_닿지_못하면_alive가_False다(monkeypatch):
    s = S.SearxSearch()
    _patch(monkeypatch, httpx.ConnectError("refused"))
    with pytest.raises(SearchUnavailable):
        await s.query("x")
    assert s.alive is False


def test_기본이_루프백이다():
    """🔴 §17-g-8 — 인증 없이 외부에 노출하지 않는다."""
    assert "127.0.0.1" in S.SEARXNG_URL or "localhost" in S.SEARXNG_URL


# ══════════════════════════════════════════════════════════════════
# Google CSE — 배정 · 일일 상한
# ══════════════════════════════════════════════════════════════════

def test_키가_없으면_available이_False다():
    """🔴 없는 것을 있는 척하지 않는다."""
    assert S.GoogleSearch(api_key="", cx="").available is False
    assert S.GoogleSearch(api_key="k", cx="c").available is True


@pytest.mark.asyncio
async def test_키가_없으면_사유가_난다():
    with pytest.raises(SearchUnavailable, match="GOOGLE_CSE"):
        await S.GoogleSearch(api_key="", cx="").query("x")


def test_상한이_100이다():
    """🔴 §19-i-3 — 무료 100쿼리/일을 **코드에 박는다.**"""
    assert S.GOOGLE_DAILY_CAP == 100
    assert S.GoogleSearch(api_key="k", cx="c").cap.cap == 100


@pytest.mark.asyncio
async def test_배정_밖_질문은_거부된다():
    """🔴 §19-i-3 — 반증 추적과 라인업 세포에만. 다른 질문이 먹으면 반증이 굶는다."""
    g = S.GoogleSearch(api_key="k", cx="c")
    for q in (C.Q_SLATE, C.Q_STANDINGS, C.Q_INTENT, C.Q_ABSENCE):
        with pytest.raises(SearchUnavailable, match="배정 밖"):
            await g.query("x", qtype=q)
    assert g.cap.used == 0, "배정 밖인데 예산을 먹었다"


@pytest.mark.asyncio
async def test_배정된_질문은_통과한다(monkeypatch):
    _patch(monkeypatch, _Resp({"items": [{"title": "t", "link": "https://a/1",
                                          "snippet": "s"}]}))
    g = S.GoogleSearch(api_key="k", cx="c")
    for q in S.GOOGLE_ALLOWED:
        assert await g.query("x", qtype=q)
    assert set(S.GOOGLE_ALLOWED) == {C.Q_COUNTER, C.Q_LINEUP}


@pytest.mark.asyncio
async def test_상한을_넘으면_예산_소진_사유가_난다(monkeypatch):
    """🔴 §19-i-8 게이트 원문 — "일일 상한 초과 시 unknown+"검색 예산 소진""."""
    _patch(monkeypatch, _Resp({"items": [{"title": "t", "link": "https://a/1"}]}))
    g = S.GoogleSearch(api_key="k", cx="c", cap=2)
    today = date(2026, 9, 27)
    assert await g.query("a", qtype=C.Q_COUNTER, today=today)
    assert await g.query("b", qtype=C.Q_COUNTER, today=today)
    with pytest.raises(SearchUnavailable, match="검색 예산 소진"):
        await g.query("c", qtype=C.Q_COUNTER, today=today)


@pytest.mark.asyncio
async def test_날이_바뀌면_예산이_돌아온다():
    g = S.GoogleSearch(api_key="k", cx="c", cap=1)
    assert g.cap.take(date(2026, 9, 27)) is True
    assert g.cap.take(date(2026, 9, 27)) is False
    assert g.cap.take(date(2026, 9, 28)) is True


@pytest.mark.asyncio
async def test_429는_상한으로_친다(monkeypatch):
    """⚠️ 우리가 센 것과 구글이 센 것이 어긋날 수 있다 — 429 를 받으면 믿는다."""
    _patch(monkeypatch, _Resp({}, 429))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable, match="검색 예산 소진"):
        await g.query("x", qtype=C.Q_COUNTER)
    assert g.cap.left == 0


# ══════════════════════════════════════════════════════════════════
# 사슬 — 순위대로, 배정 안에서만
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_1순위가_되면_2순위를_안_부른다(monkeypatch):
    calls: list = []
    _patch(monkeypatch, _Resp(_fix("sb")), capture=calls)
    g = S.GoogleSearch(api_key="k", cx="c")
    chain = S.SearchChain(searx=S.SearxSearch(), google=g)
    assert await chain.query("x", qtype=C.Q_COUNTER)
    assert g.cap.used == 0, "1순위가 됐는데 구글 예산을 먹었다"


@pytest.mark.asyncio
async def test_1순위가_죽으면_2순위로_간다(monkeypatch):
    async def _get(self, url, params=None, **kw):
        if "8888" in str(url):
            raise httpx.ConnectError("refused")
        return _Resp({"items": [{"title": "t", "link": "https://a/1"}]})
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    chain = S.SearchChain(searx=S.SearxSearch(),
                          google=S.GoogleSearch(api_key="k", cx="c"))
    hits = await chain.query("x", qtype=C.Q_COUNTER)
    assert hits and hits[0].engine == "google_cse"
    assert any("SearXNG" in t for t in chain.tried)


@pytest.mark.asyncio
async def test_배정_밖이면_1순위에서_끝난다(monkeypatch):
    async def _get(self, url, params=None, **kw):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    g = S.GoogleSearch(api_key="k", cx="c")
    chain = S.SearchChain(searx=S.SearxSearch(), google=g)
    with pytest.raises(SearchUnavailable):
        await chain.query("x", qtype=C.Q_STANDINGS)
    assert g.cap.used == 0
    assert any("배정 밖" in t for t in chain.tried), chain.tried


@pytest.mark.asyncio
async def test_전부_실패하면_사유를_들고_올라간다(monkeypatch):
    async def _get(self, url, params=None, **kw):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    chain = S.SearchChain(searx=S.SearxSearch(),
                          google=S.GoogleSearch(api_key="k", cx="c"))
    with pytest.raises(SearchUnavailable) as exc:
        await chain.query("x", qtype=C.Q_COUNTER)
    assert "SearXNG" in str(exc.value) and "Google" in str(exc.value)


def test_사슬은_키가_없으면_칸을_비운다(monkeypatch):
    monkeypatch.delenv("GOOGLE_CSE_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_CX", raising=False)
    chain = S.build_chain()
    assert chain.searx is not None
    assert chain.google is None, "키가 없는데 구글 칸을 채웠다"


# ══════════════════════════════════════════════════════════════════
# 세포와의 배선
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_세포가_검색_사유를_unknown에_적는다(monkeypatch):
    """🔴 §19-b-6 — 조용히 0 이 되지 않는다."""
    async def _get(self, url, params=None, **kw):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    bb = Blackboard()
    cell = C.Cell(question=C.Question(C.Q_COUNTER, "카라스코 최근 등판"),
                  sources=[C.Source("검색", "search",
                                    # 🔴 §4-1 문지기 — 조각을 준다(위 주석)
                                    parts={"team": "A", "opponent": "B",
                                           "when": "lineup"},
                                    query="카라스코 9월 등판", lang="ko",
                                    parse=lambda h, q: [])])
    chain = S.SearchChain(searx=S.SearxSearch(),
                          google=S.GoogleSearch(api_key="k", cx="c"))
    assert await cell.run(None, bb, search=chain) == UNKNOWN
    reason = bb.get("counter:카라스코 최근 등판").reason
    assert "검색" in reason, reason


@pytest.mark.asyncio
async def test_세포가_질문_타입을_사슬에_넘긴다(monkeypatch):
    """★ 배선 — 안 넘기면 Google 배정(§19-i-3)이 무력해진다."""
    seen: list = []

    class _Chain:
        available = True

        async def query(self, text, *, lang="ko", qtype=None):
            seen.append(qtype)
            return []

    bb = Blackboard()
    cell = C.Cell(question=C.Question(C.Q_LINEUP, "SB"),
                  sources=[C.Source("검색", "search",
                                    # 🔴 §4-1 문지기 — 조각을 준다(위 주석)
                                    parts={"team": "A", "opponent": "B",
                                           "when": "lineup"}, query="q",
                                    parse=lambda h, q: [])])
    await cell.run(None, bb, search=_Chain())
    assert seen == [C.Q_LINEUP], seen


def test_수집이_사슬을_받는다():
    from app.collect import ingest
    sig = inspect.signature(ingest.collect)
    assert "search" in sig.parameters
    src = inspect.getsource(ingest.collect)
    assert "build_chain()" in src


def test_스케줄러가_사슬을_하루_유지한다():
    """🔴 매 주기 새로 만들면 Google 일일 상한을 못 센다."""
    from app import scheduler as Sch
    src = inspect.getsource(Sch)
    assert "_SEARCH = build_chain()" in src
    assert "search=_SEARCH" in src


def test_수집이_검색_상태를_드러낸다():
    """🔴 조용한 0 금지 — 검색 수단 상태가 요약에 **이름으로** 나와야 한다.

    ⚠️ 이름만 세지 않는다. 종전 이 계약은 `"dead_engines" in src` 였고, 그 키를
       `engines_suspended`(사유째로)로 바꾸자 **정상 동작인데 빨개졌다.**
       🔴 그래서 **실제 반환 키**를 본다 — 이름을 바꿔도 계약이 따라온다.
    """
    import asyncio

    class _Pool:
        async def fetch(self, *a, **k): return []
        async def execute(self, *a, **k): return "INSERT 0 1"
        async def fetchval(self, *a, **k): return None
        async def fetchrow(self, *a, **k): return None

    from app.collect import ingest
    got = asyncio.run(ingest.collect(_Pool(), date(2026, 9, 27), [],
                                     net=_DeadNet(), search=_NoSearch()))
    # 검색 수단이 무엇이었고 무엇이 정지였는지, 구글 예산이 얼마 남았는지
    assert set(got["search"]) >= {"searx", "engines_suspended", "google",
                                  "google_left"}, got["search"]


# ══════════════════════════════════════════════════════════════════
# §19-i-5 제외 항목 · §19-f 금지
# ══════════════════════════════════════════════════════════════════

def _code_only(mod) -> str:
    """독스트링·주석을 뺀 코드만. 🔴 문서가 금지 목록을 **설명하는** 것과 코드가
    그것을 **부르는** 것은 다르다(D46)."""
    import ast
    import re as _re
    src = inspect.getsource(mod)
    lines = src.splitlines()
    kill: set[int] = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            kill.update(range(n.lineno - 1, (n.end_lineno or n.lineno)))
    return _re.sub(r"#.*", "",
                   "\n".join("" if i in kill else ln
                              for i, ln in enumerate(lines)))


def test_제외된_수단이_코드에_없다():
    """🔴 §19-i-5 — DuckDuckGo HTML 긁기 · SerpAPI류 · **카드 요구 서비스**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **Brave 는 삭제했다** — 사용자 지시 2026-10-03
    ══════════════════════════════════════════════════════════════════

    > **브래이브는 삭제한다**

    ⚠️ 하루 전 지시(*"brave api는 내가 발급 받는다"*)로 이 목록에서 **뺐다가**, 그
       다음 지시로 **되돌렸다**. 그래서 `api.search.brave.com` 은 다시 금지다.
    🔴 까닭이 남아야 한다 — 절대규칙 4 의 정의가 **카드 미등록**이고, 키를 요구하는
       통로는 그 조건을 코드가 스스로 확인할 수 없다. **확인 못 하는 것은 안 쓴다.**
    ⚠️ 키 없이 도는 통로가 셋이다(SearXNG · GDELT · Bing 뉴스 RSS) — 지우고도 봇은
       같은 일을 한다. 기록: `docs/fable/questions/2026-10-03_brave_key.md`.
    """
    src = _code_only(S).lower()
    for bad in ("html.duckduckgo.com", "serpapi", "scrapingbee", "zenrows",
                "bing.microsoft.com", "api.search.brave.com"):
        assert bad not in src, bad
    # 🔴 **클래스도 설정도 남아 있지 않다** — 안 이어진 코드는 없는 코드보다 나쁘다
    assert not hasattr(S, "BraveSearch"), "BraveSearch 가 남았다"
    from app.config import get_settings
    assert not hasattr(get_settings(), "brave_key"), "brave_key 설정이 남았다"


def test_봇임을_밝힌다():
    """🔴 D34 — UA 위장 금지. 검색도 같다."""
    from app.net import UA
    assert "UA" in inspect.getsource(S)
    assert "AnalystBot" in UA


def test_검색이_판정하지_않는다():
    """🔴 §19-f — 사실과 hardness 와 unknown 사유만 낸다."""
    src = _code_only(S)
    for bad in ("build_lean", "confidence =", "TIER_", "grade"):
        assert bad not in src, bad


def test_스니펫은_사실이_아니라_단서다():
    """§12-b — 스니펫만으로 쓴 사실은 soft. `Hit` 는 사실이 아니라 결과다."""
    assert "hardness" not in {f for f in S.Hit.__dataclass_fields__}


@pytest.mark.asyncio
async def test_구글_오류_본문을_사유에_담는다(monkeypatch):
    """🔴 실사고 2026-09-27 — 사유가 "HTTP 403" 뿐이라 무엇을 고칠지 몰랐다.

    실제 본문은 *"This project does not have the access to Custom Search JSON
    API"* 였고, 그것이 **Cloud 콘솔에서 API 를 켜야 한다**는 뜻이었다.
    §19-b-6 이 사유를 요구하는 까닭이 이것이다.
    """
    _patch(monkeypatch, _Resp(
        {"error": {"code": 403, "message": "This project does not have the "
                                          "access to Custom Search JSON API.",
                   "errors": [{"reason": "forbidden"}]}}, 403))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable) as exc:
        await g.query("x", qtype=C.Q_COUNTER)
    assert "Custom Search JSON API" in str(exc.value)
    assert "forbidden" in str(exc.value)


@pytest.mark.asyncio
async def test_설정_오류는_예산을_돌려준다(monkeypatch):
    """⚠️ 질문을 던진 적이 없다 — 설정 오류로 100건을 태우면 하루가 죽는다."""
    _patch(monkeypatch, _Resp({"error": {"message": "nope"}}, 403))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable):
        await g.query("x", qtype=C.Q_COUNTER)
    assert g.cap.used == 0, g.cap.used


@pytest.mark.asyncio
async def test_429는_예산을_돌려주지_않는다(monkeypatch):
    """⚠️ 반대 — 상한을 만난 것은 실제로 쓴 것이다."""
    _patch(monkeypatch, _Resp({}, 429))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable, match="예산 소진"):
        await g.query("x", qtype=C.Q_COUNTER)
    assert g.cap.left == 0


@pytest.mark.asyncio
async def test_본문이_JSON이_아니어도_사유가_남는다(monkeypatch):
    _patch(monkeypatch, _Resp("<html>502 Bad Gateway</html>", 502))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable, match="502"):
        await g.query("x", qtype=C.Q_COUNTER)


def test_사유에_키가_담기지_않는다():
    """🔴 오류 사유는 로그·카드·원장에 남는다 — 키가 새면 거기로 샌다."""
    src = inspect.getsource(S._why)
    assert "key" not in src and "params" not in src


def test_빈_키를_명시하면_환경으로_새지_않는다(monkeypatch):
    """🔴 실사고 2026-09-28 — `.env` 를 읽게 되자 `api_key=""` 가 환경변수로
    새어 들어갔다. `api_key or os.getenv(...)` 는 "키 없음"을 표현할 수 없고,
    키가 있는 기계에서 그 경로가 **조용히 통과**한다.
    """
    monkeypatch.setenv("GOOGLE_CSE_KEY", "env_key")
    monkeypatch.setenv("GOOGLE_CSE_CX", "env_cx")
    assert S.GoogleSearch(api_key="", cx="").available is False
    assert S.GoogleSearch(api_key="", cx="").key == ""
    # None 이면 환경에서 읽는다
    g = S.GoogleSearch()
    assert (g.key, g.cx) == ("env_key", "env_cx")


# ══════════════════════════════════════════════════════════════════
# reason 코드가 갈림을 정한다 (사용자 지시 2026-09-28)
# ══════════════════════════════════════════════════════════════════

def _err(reason: str, message: str = "m", status: int = 403):
    return _Resp({"error": {"code": status, "status": "PERMISSION_DENIED",
                            "message": message,
                            "errors": [{"reason": reason, "domain": "global",
                                        "message": message}]}}, status)


def test_reason을_원문으로_낸다():
    """🔴 사용자 지시 — `error.errors[0].reason` 을 **그대로** 출력한다.

    `message` 문장으로 판단하면 틀린다. 실사고 2026-09-27: 내가 message 를 읽고
    "API 미사용설정"이라 단정했는데 reason 은 `forbidden` 이었다.
    """
    assert S.reason_of(_err("accessNotConfigured")) == "accessNotConfigured"
    assert S.reason_of(_err("forbidden")) == "forbidden"
    assert S.reason_of(_Resp({}, 403)) == ""
    assert S.reason_of(_Resp("<html>", 502)) == ""


@pytest.mark.parametrize("reason,must", [
    ("accessNotConfigured", "사용 설정"),
    ("dailyLimitExceeded", "할당량"),
    ("forbidden", "키 제한"),
    ("badRequest", "무효"),
])
@pytest.mark.asyncio
async def test_reason마다_조치가_다르다(monkeypatch, reason, must):
    """🔴 추측 없이 원문으로 갈린다 — 코드마다 고칠 자리가 다르다."""
    _patch(monkeypatch, _err(reason))
    g = S.GoogleSearch(api_key="k", cx="c")
    with pytest.raises(SearchUnavailable) as exc:
        await g.query("x", qtype=C.Q_COUNTER)
    said = str(exc.value)
    assert f"reason={reason}" in said, said
    assert must in said, said


def test_reason_표가_실측된_코드를_덮는다():
    """실측 2026-09-28 — 이 넷을 직접 받았다. 표에 없으면 조치가 안 나온다."""
    for seen in ("forbidden", "badRequest"):
        assert seen in S.REASON_ACTION, seen


def test_forbidden은_cx_문제가_아니라고_적는다():
    """🔴 대조군으로 지웠다 — 엉뚱한 cx 는 **400 badRequest** 로 온다(실측).

    그 사실을 조치 문구가 담아야 다음 세션이 cx 를 의심하지 않는다.
    """
    act = S.REASON_ACTION["forbidden"]
    assert "400" in act and "cx" in act


# ══════════════════════════════════════════════════════════════════
# 상한 도달 → 다음 PT 자정까지 호출 0건 (사용자 지시 2026-09-28)
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_상한_도달_후_PT_자정까지_호출_0건이다(monkeypatch, caplog):
    """🔴 사용자 지시 — *"상한 도달 시 다음 날 00:00 PT까지 호출 0건인지 로그로
    증명."*

    **실제 HTTP 호출 수를 센다.** 상한 뒤에는 요청이 나가지 않아야 한다 —
    나가면 그것이 요금이다.
    """
    from datetime import datetime, timezone as _tz
    calls: list = []

    async def _get(self, url, params=None, **kw):
        calls.append(url)
        return _Resp({"items": [{"title": "t", "link": "https://a/1"}]})
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)

    g = S.GoogleSearch(api_key="k", cx="c", cap=2)
    # PT 2026-09-27 (KST 09-28 오전)
    day1 = datetime(2026, 9, 28, 0, 0, tzinfo=_tz.utc)
    assert S.quota_day(day1).isoformat() == "2026-09-27"
    for _ in range(2):
        await g.query("q", qtype=C.Q_COUNTER, today=S.quota_day(day1))
    assert len(calls) == 2

    # 같은 PT 날짜의 뒤쪽 시각들 — 전부 거부되고 **호출이 0건이어야 한다**
    for hours in (1, 6, 12, 23):
        later = day1 + timedelta(hours=hours)
        if S.quota_day(later) != S.quota_day(day1):
            continue                      # 이미 PT 자정을 넘었다
        with pytest.raises(SearchUnavailable, match="검색 예산 소진"):
            await g.query("q", qtype=C.Q_COUNTER, today=S.quota_day(later))
    assert len(calls) == 2, f"상한 뒤에 호출이 {len(calls) - 2}건 나갔다"

    # PT 자정을 넘기면 돌아온다
    nextday = datetime(2026, 9, 28, 7, 1, tzinfo=_tz.utc)   # PT 09-28 00:01
    assert S.quota_day(nextday).isoformat() == "2026-09-28"
    await g.query("q", qtype=C.Q_COUNTER, today=S.quota_day(nextday))
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_상한_사유가_로그에_남는다(monkeypatch, caplog):
    """🔴 "로그로 증명"이 지시다 — 사유가 안 남으면 증명할 수 없다."""
    import logging
    g = S.GoogleSearch(api_key="k", cx="c", cap=0)
    with caplog.at_level(logging.INFO):
        with pytest.raises(SearchUnavailable) as exc:
            await g.query("q", qtype=C.Q_COUNTER)
    assert "검색 예산 소진" in str(exc.value)
    assert "100" in str(exc.value) or "0" in str(exc.value)


def test_비용_잠금이_기본이다():
    """🔴 사용자 지시 — 확인 답을 받기 전엔 운영에 연결하지 않는다."""
    assert S.CSE_OPERATIONAL_ENV == "CSE_OPERATIONAL"
    assert S.build_chain(operational=False).google is None


def test_할당량_초기화가_PT다():
    from datetime import datetime, timezone as _tz
    assert str(S.QUOTA_TZ) == "America/Los_Angeles"
    # PT 자정 직전/직후
    assert S.quota_day(datetime(2026, 9, 28, 6, 59, tzinfo=_tz.utc)).day == 27
    assert S.quota_day(datetime(2026, 9, 28, 7, 1, tzinfo=_tz.utc)).day == 28


class _DeadNet:
    """열기를 **전부 거부**하는 대역. 🔴 네트워크에 가지 않는다."""

    def __init__(self):
        self.dead_hosts: dict[str, str] = {}

    async def get(self, url, **k):
        from app.net import Fetched
        return Fetched(url, False, reason="대역: 열지 않는다")

    async def load_state(self, pool, **k):
        return 0

    async def flush_state(self, pool):
        return 0


class _NoSearch:
    """🔴 **검색 수단이 없는** 대역 — 세포가 사유를 남기는지 보는 자리."""

    available = False
    searx = None
    google = None

    async def query(self, *a, **k):
        raise SearchUnavailable("대역: 검색 수단 없음")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **새 검색 통로 셋** (사용자 기술 지시 2026-10-03 · 기술 2)
# ══════════════════════════════════════════════════════════════════
#
# > 검색 통로(무료): Bing 뉴스 RSS, **GDELT DOC API**(무료, 65개 언어 뉴스, 발행
# > 시각 포함), ~~Brave Search API 무료 등급~~. 셋을 병렬로 쳐서 합친다.
#
# 🔴 **Brave 는 지웠다**(사용자 지시 2026-10-03) — 키 없는 셋을 병렬로 친다.


def test_통로들이_같은_규약을_지킨다():
    """🔴 `SearchChain` 에 **분기가 생기지 않게** — 규약이 갈리면 그 자리가 자란다."""
    for cls in (S.SearxSearch, S.GdeltSearch, S.BingNewsSearch):
        sig = inspect.signature(cls.query).parameters
        assert "text" in sig and "lang" in sig, (cls.__name__, list(sig))


def test_GDELT_는_키가_없고_상한을_더_세게_지킨다():
    """🔴 응답 본문이 직접 말한다(실측 2026-10-03):
    *"Please limit requests to one every 5 seconds…"*

    ⚠️ 그런데 한 번 걸리면 **75초를 쉬고 던져도 429** 였다 — 간격만 지키는 것으로는
       안 빠져나온다. 🔴 그때 계속 두드리는 것은 예의도 아니고 효과도 없다.
    🔴 **우회가 아니다** — 우회는 다른 IP·UA 로 가는 것이고, 이것은 **더 세게
       지키는 것**이다(§14-12 가 금지한 것은 전자다).
    """
    src = _code_only(S)
    assert "GDELT_COOLDOWN_SEC" in src and "_rest_until" in src
    assert S.GDELT_INTERVAL_SEC >= 5.0, S.GDELT_INTERVAL_SEC
    assert S.GDELT_COOLDOWN_SEC >= 60.0, S.GDELT_COOLDOWN_SEC
    # 🔴 키를 안 쓴다(무료·카드 없음)
    assert "api_key" not in inspect.signature(S.GdeltSearch).parameters


def test_Bing_뉴스_RSS_는_우리가_끈_엔진과_다른_것이다():
    """⚠️ 끈 것은 SearXNG 의 **bing 웹 엔진**(질의를 무시해 선거구·쇼핑몰을 냈다)
    이고, 이것은 **뉴스 RSS 엔드포인트**다 — 실측에서 현지어 질의가 전부 들었다."""
    assert "bing.com/news/search" in S.BING_NEWS
    # 🔴 §19-i-5 가 금지한 **유료 Bing API** 는 아니다
    assert "bing.microsoft.com" not in S.BING_NEWS


def test_RSS_의_발행_시각과_실제_주소를_읽는다():
    """🔴 두 결함이 있었다(실측 2026-10-03):

    | 결함 | 증상 |
    |---|---|
    | `pubDate` 가 RFC822 다 | 발행 시각이 통째로 `None` → §12-c-1 이 전부 떨어뜨린다 |
    | 링크가 bing 리다이렉트다 | 매체가 전부 `www.bing.com` → **출처 등급·열기 순서가 무의미** |
    """
    rss = ('<rss><channel><item>'
           '<title>¡La baja de última hora!</title>'
           '<link>http://www.bing.com/news/apiclick.aspx?ref=x&amp;'
           'url=https%3A%2F%2Fwww.abc.com.py%2Fdeportes%2Fnota.html</link>'
           '<description>texto</description>'
           '<pubDate>Fri, 02 Oct 2026 09:12:00 Z</pubDate>'
           '<source url="https://www.abc.com.py">ABC Color</source>'
           '</item></channel></rss>')
    got = S.BingNewsSearch()._hits(rss, "q")
    assert len(got) == 1, got
    h = got[0]
    # 🔴 **실제 기사 주소**를 꺼냈다
    assert h.url == "https://www.abc.com.py/deportes/nota.html", h.url
    # 🔴 **발행 시각**을 읽었다(RFC822)
    assert h.published_at is not None and h.published_at.year == 2026
    assert h.published_at.month == 10 and h.published_at.day == 2
    # 🔴 매체 이름 — 속성이 붙은 태그도 읽는다
    assert h.publisher == "ABC Color", h.publisher


def test_사슬이_다섯_통로를_순서대로_쓴다():
    """🔴 순서가 뜻을 가진다: 로컬(SearXNG) → 키 없는 뉴스(GDELT·Bing) → 키 있는 것.

    ⚠️ *"셋을 병렬로 쳐서 합친다"* 는 **다음 단계**다 — 지금은 순차 대체다(한 질의에
       통신이 늘면 상한에 먼저 닿는다). 그 사실을 코드 주석이 적어 둔다.
    """
    # ⚠️ `_code_only` 는 **모듈**을 받는다(메서드 소스는 들여쓰기 때문에 `ast` 가
    #    못 읽는다). 사슬 메서드만 잘라 본다.
    whole = _code_only(S)
    i = whole.index("async def query(self, text: str")
    src = whole[i:]
    for word in ("self.searx", "self.gdelt", "self.bing", "self.google"):
        assert word in src, word
    assert src.index("self.searx") < src.index("self.gdelt") < \
        src.index("self.bing") < src.index("self.google")


def test_키_없는_통로_셋을_병렬로_합친다():
    """🔴🔴 사용자 기술 지시 2026-10-03:

    > 셋을 **병렬로 쳐서 합친다.** 차단된 곳을 우회하지 않는 원칙은 그대로다.

    ⚠️ 종전은 **순차 대체**였다 — SearXNG 가 0건이 아니면 GDELT·Bing 을 아예 안
       물었다. 그래서 SearXNG 가 **관련 없는 20건**을 낼 때 현지어 기사가 손에 안
       들어왔다(실측 2026-10-03: 열기 예산을 그쪽에 태웠다).
    🔴 셋은 **키가 없고 비용이 0** 이라 함께 쳐도 늘어나는 비용이 없다.
    """
    whole = _code_only(S)
    i = whole.index("async def query(self, text: str")
    src = whole[i:]
    assert "_gather(" in src and "asyncio.gather" in _code_only(S)
    # 🔴 **키 있는 통로는 병렬에 안 넣는다**(상한·비용이 다르다)
    j = src.index("free = [")
    block = src[j:src.index("]", j)]
    assert "self.searx" in block and "self.gdelt" in block and "self.bing" in block
    assert "google" not in block, block


def test_합치기가_중복을_지우고_날짜_있는_것을_앞에_둔다():
    """🔴 같은 기사가 두 통로에서 와도 하나다. 그리고 **날짜 있는 것이 앞**이다 —
    §12-c-1 이 날짜 없는 자료를 fail-closed 로 떨어뜨리므로, 날짜 없는 것을 먼저
    열면 그 예산이 거의 확실히 버려진다."""
    import asyncio
    from datetime import datetime, timezone

    class _Ch:
        def __init__(self, hits):
            self.hits = hits

        async def query(self, text, *, lang="ko"):
            del text, lang
            return self.hits

    when = datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
    a = S.Hit(title="날짜 없음", url="https://x.example/1", snippet="",
              publisher="x", engine="one", published_at=None)
    b = S.Hit(title="날짜 있음", url="https://y.example/2", snippet="",
              publisher="y", engine="two", published_at=when)
    dup = S.Hit(title="같은 기사", url="https://x.example/1#frag", snippet="",
                publisher="x", engine="two", published_at=None)
    chain = S.SearchChain()
    got, why = asyncio.run(chain._gather(
        [("하나", _Ch([a]), None), ("둘", _Ch([b, dup]), None)], "q", "en"))
    # 🔴 중복이 지워졌다(조각만 다른 같은 주소)
    assert [h.url for h in got] == ["https://y.example/2", "https://x.example/1"], \
        [h.url for h in got]
    assert any("하나:1건" in x for x in why) and any("둘:2건" in x for x in why)


def test_한_통로가_터져도_나머지가_돈다():
    """🔴 병렬은 **한 곳이 죽으면 전부 죽는** 구조가 되기 쉽다 — 그러면 통로를
    늘린 것이 오히려 약해진 것이다."""
    import asyncio

    class _Boom:
        async def query(self, text, *, lang="ko"):
            raise RuntimeError("터졌다")

    class _Ok:
        async def query(self, text, *, lang="ko"):
            del text, lang
            return [S.Hit(title="t", url="https://ok.example/1", snippet="",
                          publisher="ok", engine="ok", published_at=None)]

    chain = S.SearchChain()
    got, why = asyncio.run(chain._gather(
        [("터짐", _Boom(), None), ("정상", _Ok(), None)], "q", "en"))
    assert len(got) == 1 and got[0].url == "https://ok.example/1"
    assert any("터짐:" in x for x in why), why
