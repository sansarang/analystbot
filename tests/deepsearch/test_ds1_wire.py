"""[DS-1 배선 1단] 기사 본문 열기를 **런타임으로** 모은다.

🔴 **왜 여기부터인가.** `_fetch_article_body` 는 검색 결과에서 온 **임의
   도메인**을 연다. 우리가 도메인을 미리 모르는 **유일한 자리**다.
   나머지 수집기는 도메인이 고정이라 [3] 감사에서 한 번 확인했다.
   그리고 DS-3 이 소스를 Bing 으로 바꾼 뒤로 여기 들어오는 도메인이 늘었다
   (실측: osen.co.kr · yna.co.kr · mt.co.kr · fnnews.com · msn.com …).

🔴 지금은 **robots 검사가 0건**이고 `httpx` 를 직접 부른다. 예절(도메인당
   동시 1 · 간격 2초 · 일일 상한)도, 서킷 브레이커도 없다.

⚠️ 범위를 **이 함수 하나**로 잡았다. `httpx` 를 직접 부르는 웹 수집 파일이
   23개인데, 한 커밋에 옮기면 무엇이 깨졌는지 못 가린다. 그중 `fotmob`·
   `tor_search` 는 **사용자 결정 대기 중**이라 지금 건드리면 안 된다.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_본문_열기가_런타임을_지난다(monkeypatch):
    import app.collectors.satellite as SAT

    seen: list[str] = []

    class _RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            seen.append(url)
            return Fetched(url=url, status=200,
                           body=b"<html><body><p>" + b"\xea\xb8\xb0\xec\x82\xac" * 40
                                + b"</p></body></html>")

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    body = await SAT._fetch_article_body("https://www.osen.co.kr/article/G1")
    assert seen == ["https://www.osen.co.kr/article/G1"]
    assert body, "본문이 비었다"


@pytest.mark.asyncio
async def test_robots_가_막으면_빈_문자열이다(monkeypatch):
    """🔴 막힌 것과 실패한 것을 **호출부가 구분할 필요는 없다** — 둘 다
    '본문 없음'이다. 다만 **사유는 로그에 남는다**(조용한 0 이 아니다)."""
    import app.collectors.satellite as SAT

    class _RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Blocked

            raise Blocked("robots", url)

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    assert await SAT._fetch_article_body("https://news.google.com/x") == ""


@pytest.mark.asyncio
async def test_실패해도_예외가_아니다(monkeypatch):
    import app.collectors.satellite as SAT

    class _RT:
        async def fetch(self, url, **kw):
            raise RuntimeError("망")

    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: _RT())
    assert await SAT._fetch_article_body("https://x/1") == ""
    assert await SAT._fetch_article_body(None) == ""


def test_httpx_를_직접_부르지_않는다():
    import inspect

    import app.collectors.satellite as SAT

    src = inspect.getsource(SAT._fetch_article_body)
    assert "httpx" not in src, "아직 직접 부른다"
    assert "Runtime" in src or "deepsearch" in src


def test_본문_상한을_새로_적지_않았다():
    """⚠️ 길이 상한의 원본은 `extract_body` 다 — 여기서 다시 자르지 않는다."""
    import inspect

    import app.collectors.satellite as SAT

    src = inspect.getsource(SAT._fetch_article_body)
    assert "extract_body" in src
    assert "1200" not in src, "상한을 베꼈다"
