"""[DEC-2] 결정 2 — open-meteo 이관 · daum 끄기 · tor 는 손대지 않는다.

사용자 결정 2026-09-21:
  "결정 2: open-meteo → `access_basis=api_terms`(근거 URL) 로 런타임 이관 ·
   daum 검색 → **끈다**(Bing RSS 가 대체, 요청 0 확인) ·
   tor_search → **이관·수정하지 않는다.** 호출부·7일 호출 수만 보고하고
   사용자 지시를 기다린다."

🔴 **`access_basis` 가 뭔가.** robots 가 거부해도 **그 API 자신의 약관**이
   프로그램 접근을 정하고 있으면 그 약관이 governing 이다. open-meteo 가
   그 경우다 — robots 는 `Disallow: /` 인데 **약관이 무료 API 한도를 명시**한다:
       10,000/일 · 5,000/시간 · 600/분 · CC-BY 4.0 · **비상업 전용**
       근거: https://open-meteo.com/en/terms

⚠️ **상업성 판단은 사용자 몫이다.** 무료 티어는 "private websites without
   ads/subscriptions · personal · research · education" 이라고 적혀 있다.
   이 봇이 거기 해당하는지는 내가 정할 일이 아니다 — 문서에 드러냈다.
"""
from __future__ import annotations

import pytest


def test_access_basis_가_설정에_있다():
    """🔴 근거 URL 없이 `api_terms` 라고 적으면 그게 거짓이다."""
    from app.deepsearch.runtime import load_config

    b = (load_config().get("access_basis") or {})
    om = b.get("api.open-meteo.com") or {}
    assert om.get("basis") == "api_terms", om
    assert str(om.get("evidence_url") or "").startswith("https://"), om
    assert om.get("daily_cap"), om
    # ⚠️ 비상업 조건을 숨기지 않는다
    assert "비상업" in str(om.get("note") or ""), om


def test_robots_거부여도_api_terms_면_지난다():
    """🔴 `access_basis` 가 robots 를 **덮는다** — 다만 그 자리에만."""
    from app.deepsearch.runtime import access_basis

    assert access_basis("api.open-meteo.com") == "api_terms"
    assert access_basis("search.daum.net") is None
    assert access_basis("news.google.com") is None


@pytest.mark.asyncio
async def test_open_meteo_가_런타임을_지나고_막히지_않는다(monkeypatch):
    from app.deepsearch.runtime import Runtime

    class _T:
        def __init__(self):
            self.urls = []

        async def get(self, url, *, headers=None, timeout=None):
            self.urls.append(url)
            if url.endswith("robots.txt"):
                return 200, b"User-agent: *\nDisallow: /\n", {}
            return 200, b'{"hourly":{}}', {}

    t = _T()
    rt = Runtime(transport=t, sleep=_noop)
    got = await rt.fetch("https://api.open-meteo.com/v1/forecast?latitude=1")
    assert got.status == 200, "api_terms 인데 막혔다"
    assert rt.robots_state("api.open-meteo.com") == "overridden"


@pytest.mark.asyncio
async def test_api_terms_가_아닌_곳은_그대로_막힌다():
    from app.deepsearch.runtime import Blocked, Runtime

    class _T:
        async def get(self, url, *, headers=None, timeout=None):
            if url.endswith("robots.txt"):
                return 200, b"User-agent: *\nDisallow: /\n", {}
            return 200, b"ok", {}

    rt = Runtime(transport=_T(), sleep=_noop)
    with pytest.raises(Blocked) as e:
        await rt.fetch("https://search.daum.net/search?q=x")
    assert e.value.reason == "robots"


def test_weather_가_런타임을_지난다():
    import inspect

    from app.collectors import weather

    src = inspect.getsource(weather)
    assert "default_runtime" in src, "아직 httpx 를 직접 부른다"


def test_daum_이_꺼져_있다():
    """🔴 Bing RSS 가 대체한다(DS-3). 요청 0 이어야 한다."""
    from app.collectors.source_gate import enabled

    assert enabled("daum_search") is False


@pytest.mark.asyncio
async def test_daum_을_부르면_요청이_안_나간다():
    from app.collectors.satellite import _daum_fetch
    from app.collectors.source_gate import SourceDisabled

    with pytest.raises(SourceDisabled) as e:
        await _daum_fetch("한화 이글스")
    assert "robots" in str(e.value)


def test_tor_는_건드리지_않았다():
    """⚠️ 사용자 지시: "이관·수정하지 않는다." 그대로 둔다."""
    import inspect

    from app.collectors import tor_search

    src = inspect.getsource(tor_search)
    assert "httpx" in src, "tor 를 손댔다 — 지시는 그대로 두라는 것이다"
    assert "default_runtime" not in src, "tor 를 런타임으로 옮겼다"


async def _noop(s):
    return None
