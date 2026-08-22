"""모든 외부 API 클라이언트의 공통 베이스.

- 지수 백오프 최대 3회 재시도 + 타임아웃 (httpx)
- 키 부재/강제 목 모드 시 mock_data/ 샘플 JSON 반환, 모드는 로그에 명시
"""

import asyncio
import json
import logging
import pathlib
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MOCK_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "mock_data"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BaseAPIClient:
    name: str = "base"
    base_url: str = ""
    timeout: float = 15.0
    max_retries: int = 3
    backoff_base: float = 0.5

    def __init__(self, mock: bool):
        self.mock = mock
        logger.info("[%s] client mode: %s", self.name, "MOCK" if mock else "LIVE")

    def load_mock(self, filename: str) -> Any:
        logger.info("[%s] serving mock data: %s", self.name, filename)
        return json.loads((MOCK_DIR / filename).read_text())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        json_body: dict | None = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(
                        method, url, params=params, headers=headers, json=json_body
                    )
                if resp.status_code in RETRYABLE_STATUS:
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in RETRYABLE_STATUS:
                    raise  # 4xx(429 제외)는 재시도 무의미
                last_exc = exc
            except httpx.TransportError as exc:
                last_exc = exc
            if attempt < self.max_retries - 1:
                delay = self.backoff_base * (2**attempt)
                logger.warning(
                    "[%s] retry %d/%d in %.1fs: %s",
                    self.name, attempt + 1, self.max_retries, delay, last_exc,
                )
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("POST", path, **kwargs)
