"""모든 외부 API 클라이언트의 공통 베이스.

- 지수 백오프 최대 3회 재시도 + 타임아웃 (httpx)
- 429(레이트리밋) 전용 백오프: Retry-After 헤더 우선, 없으면 2s→6s→15s 3회
- 클래스 단위 동시 실행 제한(max_concurrency) + 요청 간 최소 간격(min_interval)
- 키 부재/강제 목 모드 시 mock_data/ 샘플 JSON 반환, 모드는 로그에 명시

에러 분류(중요): 429는 **레이트리밋**이지 크레딧 소진이 아니다.
잔액이 남아 있는데 "충전 필요" 알림을 보내던 오분류를 막기 위해
classify_api_error()로 credit/auth/rate_limit/server/other를 분리한다.
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
SERVER_STATUS = {500, 502, 503, 504}

# 크레딧/쿼터 소진으로 판정하는 본문 키워드 (401/403 판별용)
QUOTA_KEYWORDS = (
    "credit", "quota", "billing", "insufficient", "payment required",
    "usage limit", "limit reached", "out_of_usage", "request limit",
    "exceeded", "구독", "잔액",
)

# 429 본문에 이 표현이 있으면 '레이트리밋' — 잔액 문제가 아니다.
RATE_LIMIT_MARKERS = (
    "rate limit", "rate_limit", "ratelimit", "too many requests",
    "requests per", "slow down", "retry after", "concurrent",
)

# 429 본문에 이 표현이 있을 때만 '크레딧 소진'으로 승격 (월 사용량 상한 등)
CREDIT_MARKERS = (
    "insufficient", "credit", "billing", "payment", "usage limit",
    "limit reached", "out_of_usage", "구독", "잔액", "충전",
)


class ApiServiceError(RuntimeError):
    """외부 API 실패의 공통 베이스 — service/detail 보존."""

    def __init__(self, service: str, detail: str):
        self.service = service
        self.detail = detail
        super().__init__(f"{service}: {detail}")


class ApiQuotaError(ApiServiceError):
    """API 크레딧/쿼터 소진 — 재시도 무의미, 충전 안내를 보내야 하는 상태."""


class ApiAuthError(ApiServiceError):
    """API 키 오류(401/403) — 충전이 아니라 키 확인·교체가 필요한 상태."""


class ApiRateLimitError(ApiServiceError):
    """레이트리밋(429) 재시도 소진 — 내부 재시도·큐잉 대상. 사용자 알림 금지."""


class ProviderDisabledError(ApiServiceError):
    """의도적 미사용 — HTTP 금지, 알림 금지. mock(키 없음)도 오류도 아니다."""


class ProviderBlockedError(ApiServiceError):
    """크레딧 소진 회로 차단 — 키 변경 또는 수동 해제 전 HTTP 금지. 알림 금지."""


def classify_api_error(status: int, body: str) -> str:
    """HTTP 실패를 'credit' | 'auth' | 'rate_limit' | 'server' | 'other'로 분류.

    429는 기본이 rate_limit이며, 본문이 명시적으로 잔액/사용량 상한을 말할 때만
    credit으로 승격한다 (레이트리밋 문구가 함께 있으면 rate_limit 우선).
    """
    lowered = (body or "").lower()
    if status == 402:
        return "credit"
    if status == 429:
        if any(m in lowered for m in RATE_LIMIT_MARKERS):
            return "rate_limit"
        if any(k in lowered for k in CREDIT_MARKERS):
            return "credit"
        return "rate_limit"
    if status == 400:
        # Anthropic은 크레딧 소진을 402가 아니라 **400 invalid_request_error**로 준다
        # ("Your credit balance is too low..."). 400은 보통 진짜 잘못된 요청이므로
        # 본문이 명시적으로 잔액·결제를 말할 때만 credit으로 승격한다.
        return "credit" if any(k in lowered for k in CREDIT_MARKERS) else "other"
    if status in (401, 403):
        return "credit" if any(k in lowered for k in QUOTA_KEYWORDS) else "auth"
    if status in SERVER_STATUS:
        return "server"
    return "other"


def is_quota_error(status: int, body: str) -> bool:
    """크레딧/쿼터 소진 여부 (충전 안내 대상). 레이트리밋은 False."""
    return classify_api_error(status, body) == "credit"


def parse_retry_after(headers: Any) -> float | None:
    """Retry-After 헤더(초 단위)를 파싱. 날짜 형식이거나 없으면 None."""
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    if not raw:
        return None
    try:
        val = float(str(raw).strip())
    except ValueError:
        return None  # HTTP-date 형식은 지원하지 않음 — 기본 백오프 사용
    return max(0.0, min(val, 60.0))  # 과도한 대기 방지 상한 60s


# 클래스·이벤트루프 단위 스로틀 상태 (테스트가 루프를 갈아끼워도 안전하도록 루프별 분리)
_throttle_state: dict[tuple[str, int], dict] = {}


class BaseAPIClient:
    name: str = "base"
    base_url: str = ""
    timeout: float = 15.0
    max_retries: int = 3
    backoff_base: float = 0.5
    max_concurrency: int | None = None      # None → 제한 없음
    min_interval: float = 0.0               # 같은 클래스 요청 간 최소 간격(초)
    rate_limit_backoff: tuple[float, ...] = ()  # 429 전용 대기열 (비면 지수 백오프)

    def __init__(self, mock: bool):
        self.mock = mock
        self.last_headers: dict = {}  # 직전 응답 헤더 (쿼터 추적용)
        logger.info("[%s] client mode: %s", self.name, "MOCK" if mock else "LIVE")

    def load_mock(self, filename: str) -> Any:
        logger.info("[%s] serving mock data: %s", self.name, filename)
        return json.loads((MOCK_DIR / filename).read_text())

    # ------------------------------------------------------------ 스로틀

    def _state(self) -> dict:
        loop = asyncio.get_running_loop()
        key = (type(self).__name__, id(loop))
        st = _throttle_state.get(key)
        if st is None:
            st = {
                "sem": asyncio.Semaphore(self.max_concurrency or 1024),
                "lock": asyncio.Lock(),
                "last": 0.0,
            }
            _throttle_state[key] = st
        return st

    async def _send(
        self, method: str, url: str, params, headers, json_body
    ) -> httpx.Response:
        """동시 실행 제한 + 최소 간격을 지켜 1회 요청."""
        st = self._state()
        async with st["sem"]:
            if self.min_interval:
                async with st["lock"]:
                    loop = asyncio.get_running_loop()
                    wait = st["last"] + self.min_interval - loop.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    st["last"] = loop.time()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.request(
                    method, url, params=params, headers=headers, json=json_body
                )

    # ------------------------------------------------------------ 요청

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
        rl_schedule = self.rate_limit_backoff or tuple(
            self.backoff_base * (2**i) for i in range(self.max_retries - 1)
        )
        from app.api_guard import raise_if_unusable, trip_credit

        await raise_if_unusable(self.name)
        last_exc: Exception | None = None
        attempt = 0      # 5xx·전송 오류 재시도 횟수
        rl_hits = 0      # 429 재시도 횟수
        while True:
            try:
                resp = await self._send(method, url, params, headers, json_body)
                resp.raise_for_status()
                self.last_headers = dict(resp.headers)
                return resp.json()
            except httpx.HTTPStatusError as exc:
                code, body = exc.response.status_code, exc.response.text
                kind = classify_api_error(code, body)
                if kind == "credit":
                    await trip_credit(self.name, body[:300])
                    raise ApiQuotaError(self.name, body[:300]) from exc
                if kind == "auth":
                    raise ApiAuthError(self.name, body[:300]) from exc
                if kind == "rate_limit":
                    last_exc = exc
                    if rl_hits >= len(rl_schedule):
                        raise ApiRateLimitError(self.name, body[:300]) from exc
                    delay = parse_retry_after(exc.response.headers) or rl_schedule[rl_hits]
                    rl_hits += 1
                    logger.warning(
                        "[%s] 429 레이트리밋 — %.1fs 후 재시도 %d/%d",
                        self.name, delay, rl_hits, len(rl_schedule),
                    )
                    await asyncio.sleep(delay)
                    continue
                if kind != "server":
                    raise  # 그 외 4xx는 재시도 무의미
                last_exc = exc
            except httpx.TransportError as exc:
                last_exc = exc
            attempt += 1
            if attempt >= self.max_retries:
                break
            delay = self.backoff_base * (2 ** (attempt - 1))
            logger.warning(
                "[%s] retry %d/%d in %.1fs: %s",
                self.name, attempt, self.max_retries, delay, last_exc,
            )
            await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def _get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> Any:
        return await self._request("POST", path, **kwargs)
