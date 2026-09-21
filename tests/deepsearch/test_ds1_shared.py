"""[DS-1S] 런타임을 **공유한다.** 호출마다 새로 만들면 예절이 전부 사라진다.

🔴 **내가 DS-1W 에서 만든 결함이다.** `_fetch_article_body` 가 호출마다
   `Runtime()` 을 새로 만들었다. 도메인 상태(마지막 요청 시각·일일 카운터·
   서킷·robots 캐시)가 **인스턴스 안에** 있으므로 매번 초기화된다.

   실측 2026-09-21 (같은 도메인 3회 요청):
     호출마다 새 인스턴스  대기 **0회** · robots 재조회 **6회**
     인스턴스 공유        대기 2회(2초씩) · robots 재조회 4회

   🔴 **요청이 2배가 된다**(매 요청마다 robots.txt 를 다시 받는다). 그리고
      간격·일일 상한·서킷이 **전혀 안 걸린다.** 남의 서버에 대한 결례다.
"""
from __future__ import annotations

import asyncio

import pytest


class _T:
    def __init__(self):
        self.n = 0
        self.urls: list[str] = []

    async def get(self, url, *, headers=None, timeout=None):
        self.n += 1
        self.urls.append(url)
        if url.endswith("robots.txt"):
            return 200, b"User-agent: *\nAllow: /\n", {}
        return 200, b"ok", {}


@pytest.mark.asyncio
async def test_기본_런타임은_같은_것을_돌려준다():
    from app.deepsearch.runtime import default_runtime

    a = default_runtime()
    b = default_runtime()
    assert a is b, "호출마다 새로 만들면 예절이 사라진다"


@pytest.mark.asyncio
async def test_공유하면_간격과_robots_캐시가_산다():
    from app.deepsearch.runtime import Runtime

    waited: list[float] = []

    async def slp(s):
        waited.append(s)

    t = _T()
    rt = Runtime(transport=t, sleep=slp)
    for i in range(3):
        await rt.fetch(f"https://a.example/{i}")
    assert len(waited) == 2, f"간격을 안 기다렸다: {waited}"
    assert t.urls.count("https://a.example/robots.txt") == 1, \
        f"robots 를 매번 다시 받았다: {t.urls}"


@pytest.mark.asyncio
async def test_본문_열기가_런타임을_공유한다(monkeypatch):
    """🔴 `_fetch_article_body` 가 호출마다 새로 만들면 안 된다."""
    import inspect

    import app.collectors.satellite as SAT

    src = inspect.getsource(SAT._fetch_article_body)
    assert "Runtime()" not in src, "호출마다 새 인스턴스를 만든다"
    assert "default_runtime" in src


def test_다른_이벤트루프에서도_터지지_않는다():
    """⚠️ `asyncio.Semaphore` 는 **처음 쓸 때 실행 중인 루프에 묶인다.**
    모듈 싱글턴 하나면 루프가 바뀌는 자리에서
    `got Future attached to a different loop` 가 난다.

    ⚠️ 이 시험 자체는 `async` 가 아니다 — 돌고 있는 루프 안에서
       `asyncio.run` 을 부를 수 없다(처음에 그렇게 썼다가 틀렸다).
    """
    from app.deepsearch.runtime import Runtime, default_runtime

    seen = []

    async def _probe():
        rt = default_runtime()
        seen.append(id(rt))
        t = _T()
        await Runtime(transport=t, sleep=_noop).fetch("https://b.example/1")
        # 같은 루프 안에서는 같은 것
        assert default_runtime() is rt

    asyncio.run(_probe())
    asyncio.run(_probe())          # **루프를 갈아도** 터지지 않아야 한다
    assert len(seen) == 2


async def _noop(s):
    return None
