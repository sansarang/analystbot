"""[v1.4 STEP 4] ③ 게이트 — 사전값과 시장의 **괴리로 조사할 자리를 고른다.**

🔴 `gap` 은 **픽 후보 팀 기준**이다. 홈 기준으로 고정하면 픽이 원정일 때
   분기가 뒤집힌다(지시문 STEP 4 "흔한 오류").
🔴 시장이 없거나 사전값이 없으면 **보드 고정** — 없는 것을 0.5 로 읽지 않는다.
🔴 `|gap| >= 12` 도 보드 고정이다. 그만큼 벌어지면 우리 쪽 데이터 오류를 의심한다.
⚠️ 문턱은 `config/rules.yaml` 의 `flow.gate_pp` 가 원본이다. 여기 숫자를 적지 않는다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import AGREE, BOARD, DOUBT, OVER

logger = logging.getLogger(__name__)

NODE = "n03_gate"


async def run(state, ctx):
    """③ 게이트."""
    prior = state.n01_prior or {}
    market = state.n02_market or {}
    side = state.pick_side

    p_prior = prior.get(f"p_{side}") if side else None
    p_mkt = (market.get("p") or {}).get(side) if side else None

    if market.get("market_missing") or p_prior is None or p_mkt is None:
        why = ("시장 확률이 없다" if market.get("market_missing")
               else "사전값이 없다" if p_prior is None else "픽 쪽 시장값이 없다")
        state.n03_gate = {"gap_pp": None, "gate": BOARD, "stop": True,
                          "reason": f"{why} — 보드 고정"}
        logger.info("[flow:n03] game=%s %s", state.game_id, why)
        return state

    gap = round((float(p_prior) - float(p_mkt)) * 100, 2)
    agree = float(R.get("gate_pp.agree", 4.0))
    freeze = float(R.get("gate_pp.freeze", 12.0))

    if abs(gap) >= freeze:
        gate, stop = BOARD, True
        why = f"괴리 {gap:+.1f}%p — 데이터 오류 의심, 보드 고정"
    elif gap <= -agree:
        gate, stop = OVER, False
        why = f"시장이 {side} 를 {abs(gap):.1f}%p 높게 본다"
    elif gap >= agree:
        gate, stop = DOUBT, False
        why = f"우리가 {side} 를 {gap:.1f}%p 높게 본다 — 이유를 못 찾으면 사전값이 틀린 것"
    else:
        gate, stop = AGREE, False
        why = f"사전값과 시장이 {abs(gap):.1f}%p 차이 — 승패는 접고 파생만"

    state.n03_gate = {"gap_pp": gap, "gate": gate, "stop": stop, "reason": why}
    logger.info("[flow:n03] game=%s gap %+.2f%%p → %s", state.game_id, gap, gate)
    return state
