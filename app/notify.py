"""운영 알림 — API 크레딧/쿼터 소진 시 텔레그램 관리자에게 메시지 발송.

TELEGRAM_BOT_TOKEN + TELEGRAM_ADMIN_CHAT_ID가 없으면 로그 경고로 대체 (크래시 금지).
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_telegram(text: str) -> bool:
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_admin_chat_id):
        logger.warning("[notify] telegram 미설정 — 알림을 로그로 대체:\n%s", text)
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": settings.telegram_admin_chat_id, "text": text},
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


async def notify_quota(service: str, detail: str) -> bool:
    """크레딧/쿼터 소진 알림 — 충전 페이지까지 안내. 같은 서비스는 프로세스당 1회만 발송."""
    if service in _notified:
        return False
    _notified.add(service)
    url = recharge_url(service)
    charge_line = f"💳 여기서 충전하세요: {url}\n" if url else "💳 해당 서비스 콘솔에서 크레딧을 충전하세요.\n"
    return await send_telegram(
        f"⚠️ [AnalystBot] {service} API 크레딧/쿼터 소진 — 충전이 필요합니다\n"
        f"{detail[:300]}\n"
        f"{charge_line}"
        f"충전/키 교체 전까지 해당 모듈은 목/축소 모드로 동작합니다."
    )


_notified: set[str] = set()


def reset_notified() -> None:
    """테스트/재기동 시 발송 이력 초기화."""
    _notified.clear()
