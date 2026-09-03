"""[크롤 위생] 공통 HTTP 클라이언트 — 정직하게, 가볍게, 한 번만.

🔴 **차단·안티봇 우회 금지.** 이 모듈은 상대 서버에 부담을 덜 주려고
   있는 것이지, 막힌 문을 여는 도구가 아니다. 차단당하면 **그 소스를
   포기하고 대체 소스로 간다.** 헤더를 돌리거나 지문을 숨기지 않는다.

⚠️ **User-Agent 를 로테이션하지 않는다.** 하나를 고정한다 — 로테이션은
   정체를 숨기려는 행위이고, 우리는 숨길 이유가 없다. 고정하면 상대가
   우리를 식별하고 필요하면 연락할 수 있다.

무엇을 하는가
  · 세션·쿠키 재사용 (KBO 기록실처럼 세션을 요구하는 소스가 있다 —
    매 요청 새 클라이언트로 만들면 0행이 온다, 실측 2026-09-02)
  · 조건부 요청(ETag / If-Modified-Since) — 안 바뀌었으면 **304 + 본문 없음**
  · 타임아웃·지수 백오프 (상수는 config 가 원본)
  · 요청 로그: 소스·바이트·304 여부 — 카나리아가 이 숫자로 드리프트를 본다
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

#: 🔴 **하나로 고정한다. 절대 로테이션하지 않는다.**
#   연락처를 밝히는 편이 서로에게 낫다 — 문제가 생기면 우리를 막기 전에
#   메일을 보낼 수 있다.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
              "AnalystBot/1.0 (+contact: operator)")

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko,en;q=0.8,ja;q=0.6",
    "Accept-Encoding": "gzip, deflate",
}


def _cfg():
    from app.config import get_settings

    return get_settings()


class PoliteClient:
    """소스 하나당 하나. 세션·조건부 헤더를 그 소스에 대해 기억한다."""

    def __init__(self, source: str, *, headers: dict | None = None):
        self.source = source
        self._extra = dict(headers or {})
        self._client = None
        #: URL → {"etag", "last_modified"}. 조건부 요청 재료.
        self._cond: dict[str, dict] = {}
        self.stats = {"requests": 0, "not_modified": 0, "bytes": 0, "failed": 0}

    async def __aenter__(self):
        import httpx

        s = _cfg()
        self._client = httpx.AsyncClient(
            timeout=float(s.crawl_timeout_sec), follow_redirects=True,
            headers={**BASE_HEADERS, **self._extra})
        return self

    async def __aexit__(self, *exc):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        return False

    def _cond_headers(self, url: str) -> dict:
        c = self._cond.get(url) or {}
        out = {}
        if c.get("etag"):
            out["If-None-Match"] = c["etag"]
        if c.get("last_modified"):
            out["If-Modified-Since"] = c["last_modified"]
        return out

    def _remember(self, url: str, resp) -> None:
        et, lm = resp.headers.get("ETag"), resp.headers.get("Last-Modified")
        if et or lm:
            self._cond[url] = {"etag": et, "last_modified": lm}

    async def get(self, url: str, *, params: dict | None = None,
                  conditional: bool = True, **kw):
        """GET. 반환 `httpx.Response`. 304 면 `resp.status_code == 304`.

        ⚠️ **304 를 실패로 다루지 마라.** "바뀐 게 없다"는 정상 응답이고,
           호출부는 직전 파싱 결과를 그대로 쓰면 된다.
        """
        return await self._request("GET", url, params=params,
                                   conditional=conditional, **kw)

    async def post(self, url: str, *, data=None, **kw):
        return await self._request("POST", url, data=data, conditional=False, **kw)

    async def _request(self, method: str, url: str, *, conditional: bool = True,
                       **kw):
        import httpx

        if self._client is None:
            raise RuntimeError("PoliteClient 는 async with 로 열어야 한다")
        s = _cfg()
        headers = dict(kw.pop("headers", {}) or {})
        if conditional and method == "GET":
            headers.update(self._cond_headers(url))
        last_exc = None
        for attempt in range(1, int(s.crawl_retries) + 1):
            t0 = time.monotonic()
            try:
                resp = await self._client.request(method, url, headers=headers, **kw)
            except Exception as exc:                     # 네트워크·타임아웃
                last_exc = exc
                self.stats["failed"] += 1
                wait = float(s.crawl_backoff_sec) * (2 ** (attempt - 1))
                logger.warning("[net] %s %s 실패(%d/%d) %.1fs 후 재시도: %s",
                               self.source, url, attempt, s.crawl_retries,
                               wait, exc)
                if attempt >= int(s.crawl_retries):
                    break
                await asyncio.sleep(wait)
                continue
            self.stats["requests"] += 1
            dt = (time.monotonic() - t0) * 1000
            if resp.status_code == 304:
                self.stats["not_modified"] += 1
                logger.info("[net] %s 304 변경 없음 %s (%.0fms)",
                            self.source, url, dt)
                return resp
            n = len(resp.content or b"")
            self.stats["bytes"] += n
            logger.info("[net] %s %s %s %dB (%.0fms)",
                        self.source, resp.status_code, url, n, dt)
            # 🔴 차단은 재시도하지 않는다. 문을 두드릴수록 나빠진다.
            if resp.status_code in (401, 403, 429):
                logger.warning("[net] 🔴 %s 차단/제한 %s — **우회하지 않는다.** "
                               "이 소스는 포기하고 대체 소스로 간다",
                               self.source, resp.status_code)
                return resp
            if resp.status_code >= 500 and attempt < int(s.crawl_retries):
                wait = float(s.crawl_backoff_sec) * (2 ** (attempt - 1))
                await asyncio.sleep(wait)
                continue
            if resp.status_code == 200 and method == "GET":
                self._remember(url, resp)
            return resp
        raise last_exc if last_exc else RuntimeError(f"{self.source} 요청 실패")
