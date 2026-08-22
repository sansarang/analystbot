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


async def notify_quota(service: str, detail: str) -> bool:
    """크레딧/쿼터 소진 알림. 같은 서비스는 프로세스당 1회만 발송."""
    if service in _notified:
        return False
    _notified.add(service)
    return await send_telegram(
        f"⚠️ [AnalystBot] {service} API 크레딧/쿼터 소진\n"
        f"{detail[:300]}\n"
        f"키를 충전/교체하기 전까지 해당 모듈은 목/축소 모드로 동작합니다."
    )


_notified: set[str] = set()


def reset_notified() -> None:
    """테스트/재기동 시 발송 이력 초기화."""
    _notified.clear()
