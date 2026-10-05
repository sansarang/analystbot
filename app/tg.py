"""텔레그램 발송. 🔴 **발송 스위치는 사용자만 켠다** — 기본은 꺼짐이다.

§14-10: 카드는 **최초 1회 + 라인업 확정 재판정 1회**뿐이다. `cards.seq` 가
그것을 센다. 같은 경기에 카드를 두 번 넘게 보내지 않는다.
🔴 미발송은 **전건에 사유가 붙는다**(조용한 0 금지) — `cards.skip_reason`.
"""
from __future__ import annotations

import logging

import httpx

from app.card import has_banned
from app.config import get_settings

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"



async def send(text: str, *, chat_id: str | None = None) -> bool:
    """한 건 보낸다. 🔴 스위치가 꺼져 있으면 **보내지 않고 False** 를 돌려준다."""
    s = get_settings()
    if bad := has_banned(text):
        logger.error("[tg] 금지 어구가 있어 보내지 않았다: %s", bad)
        return False
    if not s.send_enabled:
        logger.info("[tg] 스위치 꺼짐 — 보내지 않았다 (%d자)", len(text))
        return False
    if not s.telegram_bot_token:
        logger.info("[tg] 목 모드 — 토큰이 없다")
        return False
    target = chat_id or s.telegram_admin_chat_id
    if not target:
        logger.warning("[tg] 대상 채팅이 없다")
        return False
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(API.format(token=s.telegram_bot_token),
                           json={"chat_id": target, "text": text,
                                 "parse_mode": "Markdown"})
    ok = r.status_code == 200
    logger.info("[tg] status=%s ok=%s", r.status_code, ok)
    return ok


# 🔴 `send_card` 는 삭제했다 — `cards` 표(최초 1회 + 재판정 1회)와 함께 간다.
#    v4 STEP 7 카드·STEP 8 명단 재실행은 **단계 8** 에서 짓고(§9), 그때 "카드
#    1회 갱신"(v4 §1 방아쇠 재실행)을 다시 센다. 등급 상향/하향 개념은 없다.
