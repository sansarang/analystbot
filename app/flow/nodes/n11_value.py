"""[v1.4 STEP 10] ⑪ 값 판정 — **가격에 값이 있는가.**

🔴 `edge = p_code − 1/배당`. 요구확률 자리에 `p_market`(devig)을 넣으면 edge 가
   늘 마진만큼 양수로 나온다 — 지시문 STEP 10 의 "흔한 오류"이고 거짓 픽의 뿌리다.
🔴 **승패 픽은 `동의` 게이트에서만** 만든다(v1.4 "시장 동의 시에만 추천").
   시장과대·가치의심에서는 구조(파생) 픽만 허용한다.
🔴 모델이 없는 파생 마켓은 `None` 이다 — **추측 확률로 픽을 만들지 않는다.**
⚠️ 문턱 `edge_min_pp` 는 `config/rules.yaml` 이 원본이다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import AGREE, PICK_BOARD, PICK_ML, PICK_STRUCT
from app.flow.odds_math import required_prob

logger = logging.getLogger(__name__)

NODE = "n11_value"


def _structure_candidates(state) -> list:
    """파생 마켓 후보. **코드 확률이 없으면 후보가 아니다.**

    🔴 총점·팀토탈·핸디의 우리 확률은 `model_probs`(scoring)가 원본이다.
       없으면 `None` 이고, 그때는 그 마켓을 건너뛴다 — 0.5 로 채우지 않는다.
    """
    der = (state.n02_market or {}).get("derivatives") or {}
    ours = (state.n08_pcode or {}).get("ours_markets") or {}
    out = []
    for name, book in (("total", der.get("total") or {}),
                       ("team_total_home", der.get("team_total_home") or {}),
                       ("team_total_away", der.get("team_total_away") or {})):
        line = book.get("line")
        for side in ("over", "under"):
            odds = book.get(side)
            if odds is None:
                continue
            p_ours = (ours.get(f"{name}_{side}") or {}).get(line)
            if p_ours is None:
                continue                      # 모델 없음 — 추측 금지
            out.append({"market": f"{name}_{side}", "line": line,
                        "odds": float(odds),
                        "edge_pp": round((float(p_ours) - required_prob(odds)) * 100, 2)})
    for ah in (der.get("ah") or []):
        p_ours = (ours.get("ah") or {}).get(ah.get("line"))
        if p_ours is None:
            continue
        out.append({"market": "ah", "line": ah.get("line"),
                    "odds": float(ah["odds"]),
                    "edge_pp": round((float(p_ours) - required_prob(ah["odds"])) * 100, 2)})
    return out


async def run(state, ctx):
    """⑪ 값 판정."""
    side = state.pick_side
    odds = (state.n02_market or {}).get("odds") or {}
    p_code = (state.n08_pcode or {}).get("p_code_pick")
    gate = (state.n03_gate or {}).get("gate")
    edge_min = float(R.get("edge_min_pp", 2.0))

    ml_edge = None
    if p_code is not None and odds.get(side):
        ml_edge = round((float(p_code) - required_prob(odds[side])) * 100, 2)

    # 🔴 승패는 `동의` 에서만. 다른 게이트에서는 만들지 않는다.
    if gate == AGREE and ml_edge is not None and ml_edge >= edge_min:
        state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_ML,
                           "structure": None}
        logger.info("[flow:n11] game=%s 승패 픽 · edge %+.2f%%p",
                    state.game_id, ml_edge)
        return state

    cands = _structure_candidates(state)
    best = max(cands, key=lambda c: c["edge_pp"]) if cands else None
    if best and best["edge_pp"] >= edge_min:
        state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_STRUCT,
                           "structure": best, "n_candidates": len(cands)}
        logger.info("[flow:n11] game=%s 구조 픽 %s %+.2f%%p",
                    state.game_id, best["market"], best["edge_pp"])
        return state

    state.n11_value = {"ml_edge_pp": ml_edge, "pick_type": PICK_BOARD,
                       "structure": best, "n_candidates": len(cands)}
    logger.info("[flow:n11] game=%s 보드 — ml_edge %s · 구조 후보 %d",
                state.game_id, ml_edge, len(cands))
    return state
