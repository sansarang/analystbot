"""[크롤 위생 C1] 정직하게·가볍게·한 번만.

🔴 이 모듈은 상대 서버 부담을 덜려고 있는 것이지 **막힌 문을 여는 도구가
   아니다.** 차단당하면 그 소스를 포기한다 — 그 규율을 테스트로 잠근다.
"""
from pathlib import Path

import httpx
import pytest

from app.net.polite_client import BASE_HEADERS, USER_AGENT, PoliteClient

SRC = Path("app/net/polite_client.py").read_text(encoding="utf-8")


# ═════════ 규율 ═════════

def test_no_bypass_is_written_into_the_module():
    """우회 금지를 **docstring 에 명문화**한다 — 다음 사람이 읽는다."""
    head = SRC[:SRC.index('"""', 10)]
    assert "우회 금지" in head
    assert "포기" in head and "대체 소스" in head


def test_user_agent_is_fixed_not_rotated():
    """🔴 로테이션은 정체를 숨기려는 행위다 — 우리는 숨길 이유가 없다."""
    assert "random" not in SRC and "choice(" not in SRC
    assert "로테이션하지 않는다" in SRC
    assert "contact" in USER_AGENT, "연락처를 밝힌다"


def test_headers_are_one_set():
    assert set(BASE_HEADERS) == {"User-Agent", "Accept-Language", "Accept-Encoding"}


# ═════════ 동작 ═════════

def _transport(handler):
    """⚠️ conftest 가 **외부 HTTP 를 전면 차단**한다(localhost 만 통과).
    MockTransport 라 실제 연결은 없지만 호스트 검사는 통과해야 하므로
    테스트 URL 은 localhost 를 쓴다."""
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_conditional_request_sends_etag_then_gets_304():
    seen = {}

    def handler(req):
        seen.setdefault("n", 0)
        seen["n"] += 1
        if seen["n"] == 1:
            return httpx.Response(200, content=b"body", headers={"ETag": "W/x1"})
        seen["inm"] = req.headers.get("If-None-Match")
        return httpx.Response(304)

    async with PoliteClient("t") as c:
        c._client = httpx.AsyncClient(transport=_transport(handler),
                                      headers=BASE_HEADERS)
        r1 = await c.get("http://localhost/x")
        r2 = await c.get("http://localhost/x")
    assert r1.status_code == 200
    assert seen["inm"] == "W/x1", "ETag 를 다시 보내지 않았다"
    assert r2.status_code == 304
    assert c.stats["not_modified"] == 1


@pytest.mark.asyncio
async def test_304_is_not_a_failure():
    """"바뀐 게 없다"는 정상 응답이다 — 실패로 세면 카나리아가 오탐한다."""
    async with PoliteClient("t") as c:
        c._client = httpx.AsyncClient(
            transport=_transport(lambda r: httpx.Response(304)),
            headers=BASE_HEADERS)
        r = await c.get("http://localhost/x")
    assert r.status_code == 304 and c.stats["failed"] == 0


@pytest.mark.asyncio
async def test_blocked_is_not_retried():
    """🔴 차단은 재시도하지 않는다 — 두드릴수록 나빠진다."""
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(403)

    async with PoliteClient("t") as c:
        c._client = httpx.AsyncClient(transport=_transport(handler),
                                      headers=BASE_HEADERS)
        r = await c.get("http://localhost/x")
    assert r.status_code == 403 and calls["n"] == 1, "차단을 재시도했다"


@pytest.mark.asyncio
async def test_server_error_backs_off_and_retries(monkeypatch):
    calls = {"n": 0}
    slept = []

    async def no_sleep(x):
        slept.append(x)

    monkeypatch.setattr("asyncio.sleep", no_sleep)

    def handler(req):
        calls["n"] += 1
        return httpx.Response(500 if calls["n"] < 3 else 200, content=b"ok")

    async with PoliteClient("t") as c:
        c._client = httpx.AsyncClient(transport=_transport(handler),
                                      headers=BASE_HEADERS)
        r = await c.get("http://localhost/x")
    assert r.status_code == 200 and calls["n"] == 3
    assert slept and slept[1] > slept[0], "백오프가 지수가 아니다"


@pytest.mark.asyncio
async def test_stats_feed_the_canary():
    """카나리아가 드리프트를 보려면 바이트 수가 있어야 한다."""
    async with PoliteClient("t") as c:
        c._client = httpx.AsyncClient(
            transport=_transport(lambda r: httpx.Response(200, content=b"x" * 42)),
            headers=BASE_HEADERS)
        await c.get("http://localhost/x")
    assert c.stats["bytes"] == 42 and c.stats["requests"] == 1


def test_constants_come_from_config():
    """타임아웃·재시도·백오프는 config 가 원본(사본 금지)."""
    from app.config import get_settings

    s = get_settings()
    assert (s.crawl_timeout_sec, s.crawl_retries, s.crawl_backoff_sec) == \
        (20.0, 3, 1.5)
    for name in ("crawl_timeout_sec", "crawl_retries", "crawl_backoff_sec"):
        assert name in SRC


def test_migration_advances_one_source_at_a_time():
    """이관은 **소스당 커밋 1개**다 — 13개를 한 번에 옮기면 되돌릴 수가 없다.

    🔴 [2026-09-04] 카나리아 1건(`oddsportal`) 이관됨. 이 숫자를 올릴 때는
       직전 소스가 한 사이클 이상 정상 수집한 것을 로그로 확인한 뒤에 한다.
       한꺼번에 늘어나면 이 테스트가 반려한다.
    """
    import subprocess

    r = subprocess.run(["grep", "-rl", "--include=*.py", "polite_client",
                        "app/collectors"], capture_output=True, text=True)
    migrated = sorted(x for x in r.stdout.split() if x.strip())
    assert migrated == ["app/collectors/oddsportal.py"], (
        f"이관 목록이 바뀌었다: {migrated} — 소스당 커밋 1개 원칙")
