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
from app.flow.labels import (AGREE, BOARD, DOUBT, NO_PRIOR, OVER,
                             PRIOR_ONLY)

logger = logging.getLogger(__name__)

NODE = "n03_gate"


async def run(state, ctx):
    """③ 게이트."""
    prior = state.n01_prior or {}
    market = state.n02_market or {}
    # 🔴 [SIDE-2] 괴리는 **우리 판단과 시장의 차이**다 — 우리 판단은 ①이
    #    정한 조사 방향이다. `pick_side` 로 재면 ⑧이 시장에서 만든 값과
    #    시장을 비교하게 되어 괴리가 정의상 0 에 붙는다.
    side = state.hyp_side

    p_prior = prior.get(f"p_{side}") if side else None
    p_mkt = (market.get("p") or {}).get(side) if side else None

    # 🔴 [F-17 2026-09-19] **사전값이 없을 때만 보드 고정이다.**
    #    사전값이 있는데 시장이 아직 없으면 — 그건 "찾을 것이 없다"가 아니라
    #    "비교 대상이 아직 없다"이다. 우리 판단은 이미 있고, 그것을 깨는 근거를
    #    찾는 것이 정직한 조사다.
    #    ⚠️ 이것이 이 봇의 순서다(CLAUDE.md "페이블처럼 분석한다"):
    #       판단을 먼저 적는다 → 무엇을 찾을지 먼저 정한다 → 시장은 검증한다.
    # 🔴 [PIPE-2 정정 2026-09-25] **`side` 에 매이면 안 된다.** 사전값이 없으면
    #    ①이 `hyp_side` 를 안 정하므로 `p_mkt`(쪽별 조회)가 None 이 되고, 그러면
    #    시장이 멀쩡히 있는데도 "시장도 없다"로 읽힌다 — 재생 실측에서 축구
    #    6경기(사전값 없음·시장 있음)가 그대로 얼었다.
    #    ⚠️ 시장의 유무는 **표 자체**로 판단한다.
    market_gone = bool(market.get("market_missing")) or not (market.get("p") or {})

    # 🔴 [PIPE-2 2026-09-25] **둘 다 없으면 여기서 멈춘다.** 사전값도 시장도
    #    없으면 비교할 것도 걸 가격도 없다 — 조사를 시작할 근거가 0 이다.
    #    ⚠️ 이 경로만 `BOARD` 를 남긴다. 아래 두 갈래는 멈추지 않는다.
    if p_prior is None and market_gone:
        state.n03_gate = {"gap_pp": None, "gate": BOARD, "stop": True,
                          "reason": "사전값도 시장도 없다 — 보드 고정",
                          "prior_suspect": False}
        logger.info("[flow:n03] game=%s 사전값·시장 둘 다 없음", state.game_id)
        return state

    if p_prior is None:
        # 🔴 [PIPE-2 2026-09-25] **멈추지 않는다.** 종전에는 보드 고정이라
        #    ①에서 즉사했고 수집·⑥⑦·서술이 통째로 안 돌았다(실측 축구
        #    23경기 중 10경기 — K리그1·에레디비시·리그앙은 elo 자체가 없다).
        #    사전값 품질 문제로 판정 전부를 죽이는 구조였다(v2 STEP 1-e).
        #    ⚠️ 승패 픽은 ⑪이 막는다 — 비교할 우리 판단이 없기 때문이다.
        state.n03_gate = {"gap_pp": None, "gate": NO_PRIOR, "stop": False,
                          "reason": "사전값이 없다 — 시장 단독 경로",
                          "prior_suspect": False,
                          "missing": (prior.get("missing") or [])}
        logger.info("[flow:n03] game=%s 사전값 없음 → 시장 단독", state.game_id)
        return state

    # ⚠️ 시장 표는 있는데 **우리 쪽 값이 없으면** 비교할 수 없다 — 사전값 단독과
    #    같은 자리다(지어낸 0 으로 gap 을 만들지 않는다).
    if market_gone or p_mkt is None:
        state.n03_gate = {"gap_pp": None, "gate": PRIOR_ONLY, "stop": False,
                          "prior_suspect": False,
                          "reason": f"시장이 아직 없다 — 사전값 {p_prior:.1%} 을 "
                                    "무너뜨릴 근거를 찾는다"}
        logger.info("[flow:n03] game=%s 시장 없음 → 사전값 단독 (p=%.3f)",
                    state.game_id, float(p_prior))
        return state

    gap = round((float(p_prior) - float(p_mkt)) * 100, 2)
    agree = float(R.get("gate_pp.agree", 4.0))
    freeze = float(R.get("gate_pp.freeze", 12.0))

    prior_suspect = False
    if abs(gap) >= freeze:
        # 🔴 [PIPE-2 2026-09-25] **괴리는 표시일 뿐 멈추지 않는다.**
        #    사전값(`team_elo`)에는 **선발이 없다** — 그래서 에이스 등판일마다
        #    |gap|≥12 가 나고 "데이터 오류"로 보드 고정됐다(실측 2026-09-25:
        #    HOU@ATH +16.1 · 한신 −18.2 · SSG +21.4 · 맨시티 −15.9 · 리즈 +18.4).
        #    ⚠️ 라벨은 부호대로 준다 — 방향을 잃으면 ④가 무엇을 찾을지 모른다.
        #    ⚠️ 의심 표지는 **③의 자기 칸**에 남긴다. `state` 에 새 속성을
        #       달면 `State` 가 dataclass 라 `asdict()` 에서 조용히 빠진다.
        gate, stop = (OVER if gap < 0 else DOUBT), False
        why = f"괴리 {gap:+.1f}%p — 사전값 의심(선발 미반영) · 진행"
        prior_suspect = True
    elif gap <= -agree:
        gate, stop = OVER, False
        why = f"시장이 {side} 를 {abs(gap):.1f}%p 높게 본다"
    elif gap >= agree:
        gate, stop = DOUBT, False
        why = f"우리가 {side} 를 {gap:.1f}%p 높게 본다 — 이유를 못 찾으면 사전값이 틀린 것"
    else:
        gate, stop = AGREE, False
        why = f"사전값과 시장이 {abs(gap):.1f}%p 차이 — 승패는 접고 파생만"

    state.n03_gate = {"gap_pp": gap, "gate": gate, "stop": stop, "reason": why,
                      "prior_suspect": prior_suspect}
    logger.info("[flow:n03] game=%s gap %+.2f%%p → %s", state.game_id, gap, gate)
    return state
