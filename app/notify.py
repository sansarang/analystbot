"""운영 알림 — API 크레딧/쿼터 소진 시 텔레그램 관리자에게 메시지 발송.

TELEGRAM_BOT_TOKEN + TELEGRAM_ADMIN_CHAT_ID가 없으면 로그 경고로 대체 (크래시 금지).
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_telegram(text: str, *, parse_mode: str | None = None,
                        disable_web_page_preview: bool = False) -> bool:
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_admin_chat_id):
        logger.warning("[notify] telegram 미설정 — 알림을 로그로 대체:\n%s", text)
        return False
    payload: dict = {
        "chat_id": settings.telegram_admin_chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if disable_web_page_preview:
        payload["disable_web_page_preview"] = True
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("[notify] telegram 발송 실패 %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.error("[notify] telegram 발송 실패: %s", exc)
        return False


# 서비스별 크레딧 충전/결제 페이지 — 소진 알림에 바로 안내
RECHARGE_URLS = {
    "anthropic": "https://console.anthropic.com/settings/billing",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "grok": "https://console.x.ai",
    "odds": "https://the-odds-api.com/#get-access",
    "football_data": "https://www.football-data.org/pricing",
    "football": "https://dashboard.api-football.com",
}


def recharge_url(service: str) -> str | None:
    lowered = service.lower()
    for key, url in RECHARGE_URLS.items():
        if key in lowered:
            return url
    return None


async def _suppressed_send(key: str, text: str, *, window_sec: int | None = None) -> bool:
    """억제를 **프로세스 경계를 넘어** 적용해 발송한다.

    🔴 종전에는 프로세스 내 집합(`_notified`)으로만 막았다. 봇·스케줄러·수동
       실행이 각자 자기 집합을 갖고, 재기동하면 집합이 비므로 **같은 알림이
       11:05·11:15·11:26 세 번 나갔다**(실측 2026-08-27).
       억제는 Redis에 있어야 한다 — `alerts._send`가 이미 그 장치다.

    Redis가 없으면 `alerts._claim`이 프로세스 내 시간 기반 폴백으로 내려간다.
    인증 오류는 30분에 1회, 크레딧 소진은 KST 하루 1회.
    """
    from app.alerts import _send

    return await _send(key, text, window_sec=window_sec)


async def notify_quota(service: str, detail: str, *,
                       allow_when_blocked: bool = False) -> bool:
    """크레딧/쿼터 소진 알림 — 충전 페이지까지 안내. 프로바이더당 KST 하루 1회.

    이미 회로가 열린 프로바이더는 보내지 않는다. 첫 알림은 `trip_credit`이
    `allow_when_blocked=True`로 이 함수를 부른다 — `_request`가 차단을 먼저
    기록한 뒤 예외를 올려도 첫 건이 사라지지 않게.

    주의: 레이트리밋(429)은 잔액 문제가 아니므로 이 알림 대상이 아니다.
    분류는 collectors.base.classify_api_error가 담당한다.
    """
    from app.alerts import quota_window_sec
    from app.api_guard import canonical_provider, is_blocked, is_disabled

    name = canonical_provider(service)
    if is_disabled(name):
        logger.info("[notify] %s 미사용 — 크레딧 알림 생략", name)
        return False
    if not allow_when_blocked and await is_blocked(name):
        logger.info("[notify] %s 이미 차단 — 크레딧 알림 생략", name)
        return False
    url = recharge_url(service)
    charge_line = f"💳 여기서 충전하세요: {url}\n" if url else "💳 해당 서비스 콘솔에서 크레딧을 충전하세요.\n"
    return await _suppressed_send(
        f"quota:{name}",
        f"⚠️ [AnalystBot] {service} API 크레딧/쿼터 소진 — 충전이 필요합니다\n"
        f"{detail[:300]}\n"
        f"{charge_line}"
        f"충전/키 교체 전까지 해당 모듈은 목/축소 모드로 동작합니다.",
        window_sec=quota_window_sec(),
    )


async def notify_auth(service: str, detail: str) -> bool:
    """키 오류(401/403) 알림 — 충전이 아니라 키 확인·교체 안내. 30분에 1회."""
    return await _suppressed_send(
        f"auth:{service}",
        f"⚠️ [AnalystBot] {service} API 키 오류 — 인증에 실패했습니다 (잔액 문제 아님)\n"
        f"{detail[:300]}\n"
        f"🔑 .env의 키 값이 유효한지 확인하거나 새 키로 교체해 주세요."
    )


async def notify_api_error(exc: Exception) -> bool:
    """API 예외를 종류에 맞는 알림으로 라우팅.

    - ApiQuotaError(크레딧 소진) → 충전 안내
    - ApiAuthError(키 오류)      → 키 교체 안내
    - ApiRateLimitError(429)     → **알림 없음** (내부 재시도·큐 재처리 대상)
    """
    from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError
    from app.collectors.base import ProviderBlockedError, ProviderDisabledError

    if isinstance(exc, (ProviderDisabledError, ProviderBlockedError)):
        logger.info("[notify] %s %s — 알림 생략 (%s)",
                    exc.service, type(exc).__name__, exc.detail[:80])
        return False
    if isinstance(exc, ApiRateLimitError):
        logger.warning("[notify] %s 레이트리밋 — 사용자 알림 생략, 재시도로 처리: %s",
                       exc.service, exc.detail[:120])
        return False
    if isinstance(exc, ApiAuthError):
        return await notify_auth(exc.service, exc.detail)
    if isinstance(exc, ApiQuotaError):
        return await notify_quota(exc.service, exc.detail)
    return False


_notified: set[str] = set()      # 옛 호환용 — 억제는 alerts(Redis)가 담당한다


def reset_notified() -> None:
    """테스트/재기동 시 발송 이력 초기화. 억제 상태도 함께 비운다."""
    _notified.clear()
    from app.alerts import reset

    reset()
