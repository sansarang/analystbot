"""[v1.4 STEP 5] ④ 가설 — **무엇을 찾을지 먼저 정한다. LLM 을 부르지 않는다.**

🔴 CLAUDE.md "페이블처럼 분석한다": 가설은 코드가 세운다. 게이트 라벨 하나가
   들어가면 확인 변수 목록이 나온다 — 같은 라벨이면 언제나 같은 목록이다.
🔴 변수 목록·핵심 표시는 `config/rules.yaml` 의 `flow.adjust_prior_pp` 가
   원본이다. 여기 이름을 손으로 적지 않는다(사본 금지).
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import (AGREE, BOARD, DOUBT, OVER, PRIOR_ONLY,
                            R_NEUTRAL, REFUTED_MEANS)

logger = logging.getLogger(__name__)

NODE = "n04_hyp"

#: `동의` 에서 보는 파생 재료. 🔴 승패 근거가 아니라 **득점 환경**이다
#  (FORKS F-11: 최근 폼은 승패 예측력이 0 에 가깝다).
_DERIV_VARS = {"baseball": ("starter_recent3", "bullpen_3d", "lineup_out"),
               "soccer": ("xi_confirmed", "rotation_risk")}

#: 소스 힌트 — ⑤ 수집이 어디를 볼지 고르는 데 쓴다.
_HINT = {"baseball": "공식(statsapi·KBO·NPB) + 뉴스RSS",
         "soccer": "FotMob matchDetails"}


def _vars_of(sport: str, names) -> list:
    table = R.vars_for(sport)
    out = []
    for n in names:
        spec = table.get(n) or {}
        out.append({"var": n, "is_core": bool(spec.get("core")),
                    "source_hint": _HINT.get(sport, "")})
    return out


async def run(state, ctx):
    """④ 가설."""
    sport = (state.sport or "").lower()
    gate = (state.n03_gate or {}).get("gate")
    side = state.pick_side
    other = "away" if side == "home" else "home"
    allv = tuple(R.vars_for(sport).keys())

    if gate == OVER:
        hyp = {"id": "H_fade",
               "text": f"시장 반대편({other})을 세울 근거",
               "vars": _vars_of(sport, allv)}
    elif gate in (DOUBT, PRIOR_ONLY):
        # 🔴 [F-17] 시장이 없을 때의 가설은 **한 종류뿐이다** — 비교 대상이
        #    없으면 정직한 조사는 "내 생각을 깨는 것" 하나다.
        #    ⚠️ 시장이 오면 ③이 다시 분류한다. 방향이 뒤집힐 수 있고
        #       (시장 과대) 그건 결함이 아니라 **검증이 작동한 것**이다.
        hyp = {"id": "H_break",
               "text": f"우리 픽({side})을 무너뜨릴 근거"
                       + (" — 시장 전" if gate == PRIOR_ONLY else ""),
               "vars": _vars_of(sport, allv)}
    elif gate == AGREE:
        # 🔴 [FIX-4a 2026-09-20] **마켓을 여기서 지정한다.** ⑪이 종전에
        #    총점·팀토탈·핸디 전체에서 max(edge) 를 골랐고, 그 결과 핸디
        #    edge −46%p 가 best 로 뽑히는 경기까지 나왔다(실측).
        #    가설이 "파생만 본다"고 말했으면 **어느 파생인지**까지 말해야 한다.
        #    ⚠️ 쪽(오버/언더)은 여기서 정하지 않는다 — ⑪이 방향 증거로 정한다.
        hyp = {"id": "H_deriv",
               "text": "승패는 접고 파생만 본다",
               "market": "total",
               "vars": _vars_of(sport, _DERIV_VARS.get(sport, ()))}
    else:                                   # BOARD 는 run.py 가 이미 멈춘다
        hyp = {"id": "H_none", "text": "찾을 것이 없다", "vars": []}

    # 🔴 지정이 없으면 ⑪의 구조 후보는 0 이다(보드). 지어내지 않는다.
    hyp.setdefault("market", None)
    # 🔴 [CNF-2 2026-09-20] **반증이 무슨 뜻인지는 가설이 정한다.**
    #    딥서치(FORKS F-19): absence of evidence 는 "그 주장이 참이었다면
    #    근거가 나왔을 것"인 만큼만 evidence of absence 다. 그러면 뜻은
    #    가설의 **주장**에 달린다 — 게이트가 주장을 정하므로 여기서 싣는다.
    #      H_fade  "시장 반대편을 세울 근거" → 없으면 시장이 맞다  → 철회
    #      H_break "우리 픽을 무너뜨릴 근거" → 없으면 픽이 단단하다 → 강화
    #      H_deriv 파생 재료                                      → 중립
    #    ⚠️ 종전 ⑥은 게이트와 무관하게 **철회 하나만** 적용했다. 그대로
    #       반증을 켜면 결장 0명인 건강한 라인업이 전부 철회된다.
    hyp.setdefault("refuted_means", REFUTED_MEANS.get(hyp["id"], R_NEUTRAL))
    state.n04_hyp = [hyp]
    logger.info("[flow:n04] game=%s %s → %s · 변수 %d개 (핵심 %d)",
                state.game_id, gate, hyp["id"], len(hyp["vars"]),
                sum(1 for v in hyp["vars"] if v["is_core"]))
    return state
