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


def _ours_markets(model_probs: dict | None) -> dict:
    """`scoring.mlb_market_probs` 모양 → ⑪이 읽는 모양으로 옮긴다.

    🔴 **계산하지 않는다.** 분포의 원본은 `scoring` 이고 여기서는 이름만 맞춘다
       (사본 금지). 없는 마켓은 **넣지 않는다** — ⑪이 `None` 을 보고 건너뛴다.
    ⚠️ 라인 키가 JSON 을 거치면 문자열이 된다("7.5") — 숫자로 되돌린다.
    """
    mp = model_probs or {}
    out: dict = {}

    def _line(k):
        try:
            return float(k)
        except (TypeError, ValueError):
            return None

    for k, d in (mp.get("totals") or {}).items():
        line = _line(k)
        if line is None or not isinstance(d, dict):
            continue
        if d.get("Over") is not None:
            out.setdefault("total_over", {})[line] = float(d["Over"])
        if d.get("Under") is not None:
            out.setdefault("total_under", {})[line] = float(d["Under"])

    # 핸디는 **쪽이 네 가지**다(home_minus·away_plus·away_minus·home_plus).
    #   ⑪은 라인 하나에 확률 하나를 읽으므로 홈 기준(`home_minus`)만 싣는다 —
    #   원정 라인은 부호가 뒤집힌 같은 사건이라 ⑪이 배당 쪽에서 가른다.
    for k, d in (mp.get("spreads") or {}).items():
        line = _line(k)
        if line is None or not isinstance(d, dict):
            continue
        if d.get("home_minus") is not None:
            out.setdefault("ah", {})[line] = float(d["home_minus"])

    # 🔴 [MOD-1 2026-09-19] 팀토탈. ⑪의 후보 이름은
    #    `team_total_home_over` 꼴이다(`n11_value._structure_candidates`) —
    #    그 이름을 여기서 **새로 짓지 않고** 그쪽 규칙에 맞춘다.
    for side in ("home", "away"):
        for k, d in ((mp.get("team_totals") or {}).get(side) or {}).items():
            line = _line(k)
            if line is None or not isinstance(d, dict):
                continue
            for way in ("Over", "Under"):
                if d.get(way) is not None:
                    key = f"team_total_{side}_{way.lower()}"
                    out.setdefault(key, {})[line] = float(d[way])
    return out


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

    # 🔴 [2026-09-18] **파생 확률을 ⑪로 내려보낸다.** 여기까지 안 실으면
    #    ⑪의 구조 후보가 언제나 0 이고, `동의` 라벨이 만든 파생 가설이 쓰일
    #    자리가 없다(E2E 드라이런 2건이 그 상태였다).
    #    ⚠️ 우리가 계산하지 않는다 — `scoring` 이 낸 것을 이름만 맞춰 옮긴다.
    ours = _ours_markets((ctx.inject or {}).get("model_probs"))
    state.n08_pcode = {"p_code_pick": round(p, 4), "sum_adj_pp": s,
                       # 🔴 자리만 둔다. `model_w=0` 이라 항등이다.
                       "p_model": None, "model_w": 0.0,
                       "ours_markets": ours}
    if ours:
        logger.info("[flow:n08] game=%s 파생 확률 %s",
                    state.game_id, {k: len(v) for k, v in ours.items()})
    logger.info("[flow:n08] game=%s p_market %.4f %+.2f%%p → p_code %.4f",
                state.game_id, float(p_mkt), s, p)
    return state
