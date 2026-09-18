"""[v1.4 STEP 12] ⑬ 발송 — **경기당 한 번. 침묵이 기본.**

🔴 조건 셋이 다 참일 때만 보낸다: 픽이 보드가 아니고, 서술이 있고, 아직 안 보냈다.
🔴 **멱등이다.** 같은 `game_id` 로 이미 보냈으면 차단한다 — 재판정 뒤 두 장이
   나가는 것이 지시문 STEP 9 가 경고한 결함이다.
🔴 발송 함수를 새로 만들지 않는다 — `app/notify.send_telegram` 을 부른다.
"""
from __future__ import annotations

import logging

from app.flow.labels import PICK_BOARD

logger = logging.getLogger(__name__)

NODE = "n13_send"

SENT_KEY = "flow:sent:{game_id}"


def _card(state) -> str:
    val = state.n11_value or {}
    st = val.get("structure") or {}
    pick = (f"{st.get('market')} {st.get('line')} @{st.get('odds')}"
            if val.get("pick_type") != "승패"
            else f"{getattr(state, state.pick_side or 'home', '')} 승 "
                 f"@{((state.n02_market or {}).get('odds') or {}).get(state.pick_side)}")
    lines = [
        f"[{state.league}] {state.away} @ {state.home}",
        f"킥오프 {state.kickoff_utc}",
        f"픽 {val.get('pick_type')} · {pick}",
        f"확률 {(state.n08_pcode or {}).get('p_code_pick')} · "
        f"확신 {(state.n09_conf or {}).get('grade')}",
        "",
    ]
    lines += (state.n12_text or {}).get("sentences") or []
    urls = [e.get("source_url") for e in (state.n05_evidence or [])
            if e.get("source_url")][:2]
    if urls:
        lines += ["", *urls]
    return "\n".join(lines)


async def _already_sent(state, ctx) -> bool:
    if ctx.redis is None:
        return False
    try:
        return bool(await ctx.redis.get(SENT_KEY.format(game_id=state.game_id)))
    except Exception:
        return False


async def run(state, ctx):
    """⑬ 발송."""
    val = state.n11_value or {}
    if val.get("pick_type") == PICK_BOARD:
        state.n13_send = {"sent": False, "message_id": None, "why": "보드"}
        return state
    if not ((state.n12_text or {}).get("sentences")):
        state.n13_send = {"sent": False, "message_id": None, "why": "서술 없음"}
        return state
    if await _already_sent(state, ctx):
        logger.info("[flow:n13] game=%s 이미 보냈다 — 차단", state.game_id)
        state.n13_send = {"sent": False, "message_id": None, "why": "중복"}
        return state

    text = _card(state)
    if "send" in (ctx.inject or {}):
        ok = bool(ctx.inject["send"](text))
    else:
        from app import notify as _n

        ok = await _n.send_telegram(text, disable_web_page_preview=True)

    if ok and ctx.redis is not None:
        try:
            await ctx.redis.set(SENT_KEY.format(game_id=state.game_id), "1",
                                ex=24 * 3600)
        except Exception as exc:
            logger.warning("[flow:n13] 발송 표시 실패 game=%s: %s",
                           state.game_id, exc)
    state.n13_send = {"sent": bool(ok), "message_id": None}
    logger.info("[flow:n13] game=%s 발송 %s", state.game_id, ok)
    return state
