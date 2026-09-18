"""[v1.4 STEP 8] ⑧ p_code — **시장 뼈대 + 조정.**

🔴 `p_code = clamp(p_market[pick] + Σadj/100, 0.05, 0.95)`.
   사전값(`p_prior`)은 **더하지 않는다** — 그것은 ③ 게이트와 카드 서술의 몫이다
   (`prior.py` 규약 · CLAUDE.md).
🔴 `model_w = 0` 축(`p_model`)은 **자리만** 두고 쓰지 않는다.
⚠️ 단위: `sum_adj_pp` 는 %p, `p_code_pick` 은 0~1 이다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

NODE = "n08_pcode"

P_MIN, P_MAX = 0.05, 0.95


async def run(state, ctx):
    """⑧ p_code."""
    side = state.pick_side
    p_mkt = ((state.n02_market or {}).get("p") or {}).get(side)
    if p_mkt is None:
        state.n08_pcode = {"p_code_pick": None, "sum_adj_pp": 0.0,
                           "p_model": None, "model_w": 0.0,
                           "reason": "시장 확률이 없다"}
        return state

    s = round(sum(a.get("pp", 0.0) for a in (state.n07_adjust or [])), 2)
    p = float(p_mkt) + s / 100.0
    p = max(P_MIN, min(P_MAX, p))

    state.n08_pcode = {"p_code_pick": round(p, 4), "sum_adj_pp": s,
                       # 🔴 자리만 둔다. `model_w=0` 이라 항등이다.
                       "p_model": None, "model_w": 0.0}
    logger.info("[flow:n08] game=%s p_market %.4f %+.2f%%p → p_code %.4f",
                state.game_id, float(p_mkt), s, p)
    return state
