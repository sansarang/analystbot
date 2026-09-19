"""[v1.4 STEP 8] ⑨ 확신 — **코드가 정한다. LLM 금지.**

🔴 A: 핵심 변수 confirmed >= 2 **그리고** `|Σadj| >= 3`
   B: confirmed >= 1
   C: 그 외
🔴 LLM 자기신고를 쓰지 않는다 — 같은 격차를 매번 다르게 부른다
   (`comparator.py` 가 같은 이유를 적어 뒀다).
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import CONFIRMED, GRADE_A, GRADE_B, GRADE_C

logger = logging.getLogger(__name__)

NODE = "n09_conf"

#: A 등급의 조정 합 문턱(%p). 지시문 STEP 8 의 값.
A_MIN_ADJ_PP = 3.0
A_MIN_CORE = 2


async def run(state, ctx):
    """⑨ 확신."""
    per_var = (state.n06_verdict or {}).get("per_var") or {}
    core = set(R.core_vars((state.sport or "").lower()))
    n_conf = sum(1 for v in per_var.values() if v == CONFIRMED)
    n_core_conf = sum(1 for k, v in per_var.items()
                      if v == CONFIRMED and k in core)
    # 🔴 [FIX-3] **방향이 판정된 조정만** 센다. 방향 미상 행은 ⑦이 만들지
    #    않으므로 `n07_adjust` 에 남은 것이 곧 판정된 것이다 — 그 합을 쓴다.
    #    (`n08.sum_adj_pp` 는 캡·축소가 걸린 뒤 값이라 등급 판단과 다르다)
    sum_adj = abs(round(sum(float(a.get("pp") or 0.0)
                            for a in (state.n07_adjust or [])), 4))

    if n_core_conf >= A_MIN_CORE and sum_adj >= A_MIN_ADJ_PP:
        grade, why = GRADE_A, f"핵심 confirmed={n_core_conf} · |Σadj|={sum_adj:.1f}"
    elif n_conf >= 1:
        grade, why = GRADE_B, f"confirmed={n_conf}"
    else:
        grade, why = GRADE_C, "confirmed=0"

    # 🔴 [FIX-3] 구조 픽 등급은 **승패 등급을 물려받지 않는다.** 근거가 다르다 —
    #    승패는 핵심 변수 confirmed 수, 구조는 총점 방향 증거다(⑪이 채운다).
    state.n09_conf = {"grade": grade, "reason": why,
                      "confirmed": n_conf, "core_confirmed": n_core_conf,
                      "struct_grade": None,
                      "struct_reason": "⑪이 총점 방향 증거로 정한다"}
    logger.info("[flow:n09] game=%s 확신 %s (%s)", state.game_id, grade, why)
    return state
