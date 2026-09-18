"""[v1.4 STEP 7] ⑥ 채점 — **찾았는지 기계가 센다.**

🔴 규칙은 코드다. LLM 을 부르지 않는다.
🔴 핵심(is_core) 변수가 하나라도 `refuted` → **반박됨**(픽 철회).
   `unknown` 비율이 문턱을 넘으면 **모름과반**(보드). 그 외 **확인됨**.
🔴 `unknown` 과 `refuted` 는 다르다 — "안 봤다"와 "봤는데 없다"를 섞으면
   채점이 거짓이 된다(CLAUDE.md 사본·조용한 0 금지와 같은 규율).
⚠️ 문턱은 `flow.unknown_ratio_board` 가 원본이다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import (CONFIRMED, REFUTED, UNKNOWN, V_OK, V_REFUTED,
                             V_UNKNOWN)

logger = logging.getLogger(__name__)

NODE = "n06_verdict"


def _judge(evidence_value) -> str:
    """한 변수의 판정. 🔴 None 과 빈 값을 **구분한다.**

    · 값 없음/원문 없음 → `unknown` (안 봤다)
    · 빈 목록          → `refuted`  (봤는데 없다)
    · 값 있음          → `confirmed`
    """
    if evidence_value is None:
        return UNKNOWN
    if hasattr(evidence_value, "__len__") and len(evidence_value) == 0:
        return REFUTED
    return CONFIRMED


async def run(state, ctx):
    """⑥ 채점."""
    hyp = (state.n04_hyp or [{}])[0]
    wanted = {v["var"]: bool(v.get("is_core")) for v in (hyp.get("vars") or [])}
    found = {e["var"]: e.get("value") for e in (state.n05_evidence or [])}

    per_var: dict = {}
    for var in wanted:
        per_var[var] = _judge(found.get(var)) if var in found else UNKNOWN

    total = len(per_var) or 1
    n_unknown = sum(1 for v in per_var.values() if v == UNKNOWN)
    unknown_ratio = round(n_unknown / total, 4)
    core_refuted = [k for k, v in per_var.items()
                    if v == REFUTED and wanted.get(k)]

    board_ratio = float(R.get("unknown_ratio_board", 0.5))
    if core_refuted:
        verdict = V_REFUTED
    elif unknown_ratio > board_ratio:
        verdict = V_UNKNOWN
    else:
        verdict = V_OK

    state.n06_verdict = {"per_var": per_var, "unknown_ratio": unknown_ratio,
                         "verdict": verdict, "core_refuted": core_refuted}
    logger.info("[flow:n06] game=%s 변수 %d → 확인 %d · 반증 %d · 미상 %d → %s",
                state.game_id, total,
                sum(1 for v in per_var.values() if v == CONFIRMED),
                sum(1 for v in per_var.values() if v == REFUTED),
                n_unknown, verdict)
    return state
