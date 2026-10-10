"""🔴🔴 **라인업 감시** — 사용자 지시 2026-10-10(재작성) §2-3.

> 카드에 버튼 `[🔔 라인업 나오면 다시 분석]` — 사용자가 **누른 경기만** 그
> 시각부터 **5분 간격**으로 사다리를 돌고, 확정되면 재분석해서 **원래 메시지를
> 고쳐 쓴다**(`"🔁 확정 XI 반영 — 바뀐 것 …"`). 누르지 않으면 돌지 않는다
> (자동 분석 아님).

🔴 **자동 분석이 아니다**(지시서 전제) — 이 파일의 어느 줄도 스스로 경기를 고르지
   않는다. 도는 것은 **사용자가 누른 그 경기 하나**뿐이고, 끄면 즉시 멈춘다.
⚠️ 발송 스위치(`SEND_ENABLED`)와 무관하다 — 사용자가 **누른 답**을 고쳐 쓰는 것이고
   §11-11 이 막는 것은 *봇이 스스로 보내는* 카드다.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

#: 🔴🔴 §2-3 — **5분 간격**(사용자가 적은 수). ⚠️ 두 곳에 적지 않는다
EVERY_SEC = 300
#: 🔴 §2-3 — 감시를 시작하는 시각(킥오프 기준 분). A-2 의 `T-75` 와 같은 수다
START_BEFORE_MIN = 75
#: 🔴 킥오프 뒤까지 돌지 않는다 — 그때는 예측이 아니다(§1-3)
STOP_AFTER_MIN = 0
#: 🔴 한 경기에 도는 **최대 횟수** — 상한 없이 도는 고리를 만들지 않는다
MAX_TICKS = 40


def start(bot, ask, *, pool, card) -> str:
    """🔴 그 경기 하나의 감시를 켠다. 사람에게 보일 **한 줄**을 돌려준다.

    ⚠️ 이미 걸려 있으면 **두 번 걸지 않는다**(같은 경기에 작업 둘이 돌면 메시지를
       서로 덮어쓴다).
    """
    if getattr(ask, "watch", None) is not None and not ask.watch.done():
        return "🔔 이미 감시 중이다"
    ask.watch = asyncio.create_task(_loop(bot, ask, card=card))
    logger.info("[watch] 켰다 — %s", ask.asked)
    return f"🔔 **라인업 감시를 켰다** — {EVERY_SEC // 60}분마다 사다리를 돈다"


def stop(ask) -> str:
    """🔴 감시를 끈다. ⚠️ 안 걸려 있으면 그 사실을 말한다."""
    said = getattr(ask, "watch", None)
    if said is None or said.done():
        return "🔔 감시가 걸려 있지 않다"
    said.cancel()
    ask.watch = None
    logger.info("[watch] 껐다 — %s", ask.asked)
    return "🔔 **감시를 껐다**"


async def _loop(bot, ask, *, card) -> None:
    """🔴 5분마다 **재분석을 돌려 확정 XI 인지 본다**. 확정되면 고쳐 쓰고 멈춘다.

    🔴 **라인업만 따로 받지 않는다** — 재분석(`again=True`)이 s2 를 다시 돌고 그
       s2 가 사다리를 돈다(`app/core/lineups.py` 의 표). ⚠️ 여기서 사다리를 또
       돌면 통로가 둘이 되고 한쪽만 고쳐진다(사본 금지).
    ⚠️ 돌 때마다 **돈이 든다**(s2·s6·s7). 그래서 상한(`MAX_TICKS`)과 킥오프 뒤
       중단이 있다.
    """
    from app.core import layer1
    for tick in range(MAX_TICKS):
        try:
            await asyncio.sleep(EVERY_SEC)
            body, got = await card()
            if got is None:
                continue
            if _past(got):
                await _say(bot, ask, "⏱ **킥오프가 지났다 — 감시를 멈춘다**"
                                     "(예측이 아니다)")
                return
            if not layer1.xi_confirmed(got):
                logger.info("[watch] %d번째 — 아직 확정 아니다(%s)",
                            tick + 1, ask.asked)
                continue
            # 🔴🔴 §2-3 — **원래 메시지를 고쳐 쓴다**
            await _edit(bot, ask, "🔁 **확정 XI 반영** — 아래 카드는 확정 "
                                  "라인업으로 다시 판정한 것이다\n\n" + body)
            logger.info("[watch] 확정 XI 로 고쳐 썼다 — %s", ask.asked)
            return
        except asyncio.CancelledError:
            logger.info("[watch] 취소됐다 — %s", ask.asked)
            raise
        except Exception as exc:                            # noqa: BLE001
            # ⚠️ 한 번 터져도 **감시를 잃지 않는다** — 다음 차례에 다시 본다
            logger.info("[watch] %d번째가 터졌다(계속 돈다) — %r", tick + 1, exc)
    await _say(bot, ask, f"🔔 감시를 {MAX_TICKS}번 돌고 멈췄다 — 확정 XI 를 "
                         f"못 받았다")


def _past(card) -> bool:
    """🔴 킥오프가 지났나 — "지금"은 `window.now_utc` 하나다(§4)."""
    from app import window as _w
    when = getattr(getattr(card, "match", None), "kickoff_utc", None)
    return when is not None and _w.now_utc() >= when


async def _edit(bot, ask, body: str) -> None:
    """🔴 §2-3 — **원래 메시지를 고쳐 쓴다**. 못 고치면 새로 보낸다(이유를 적는다)."""
    from app.bot.main import _split
    chunks = _split(body)
    if ask.chat_id is None or ask.message_id is None:
        await _say(bot, ask, chunks[0])
        return
    try:
        await bot.edit_message_text(chat_id=ask.chat_id,
                                    message_id=ask.message_id,
                                    text=chunks[0])
    except Exception as exc:                                # noqa: BLE001
        # ⚠️ 텔레그램은 **같은 글자**로 고치면 거부한다 — 그것도 여기로 온다
        logger.info("[watch] 고쳐쓰기 실패(새로 보낸다) — %r", exc)
        await _say(bot, ask, chunks[0])
    for chunk in chunks[1:]:
        await _say(bot, ask, chunk)


async def _say(bot, ask, body: str) -> None:
    """🔴 한 줄 알림. ⚠️ 보낼 자리를 모르면 **로그에만** 남긴다(조용히 삼키지 않는다)."""
    if ask.chat_id is None:
        logger.info("[watch] 보낼 자리를 모른다 — %s", body[:80])
        return
    await bot.send_message(chat_id=ask.chat_id, text=body)
