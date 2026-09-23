"""[v1.4 STEP 7] ⑥ 채점 — **찾았는지 기계가 센다.**

🔴 규칙은 코드다. LLM 을 부르지 않는다.
🔴 핵심(is_core) 변수가 `refuted` 일 때 무엇을 하는가는 **가설이 정한다**
   (`refuted_means` · ④가 싣는다 · 근거 FORKS F-19). 종전에는 언제나
   철회였는데, 그러면 "무너뜨릴 근거를 못 찾았다"도 철회가 된다.
   `unknown` 비율이 문턱을 넘으면 **모름과반**(보드). 그 외 **확인됨**.
🔴 `unknown` 과 `refuted` 는 다르다 — "안 봤다"와 "봤는데 없다"를 섞으면
   채점이 거짓이 된다(CLAUDE.md 사본·조용한 0 금지와 같은 규율).
⚠️ 문턱은 `flow.unknown_ratio_board` 가 원본이다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R
from app.flow.labels import (CONFIRMED, R_RETRACT, REFUTED, REFUTED_MEANS,
                             UNKNOWN, UNRUN, V_OK, V_REFUTED, V_UNKNOWN)

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
    # 🔴 [HYC-3 2026-09-23] **"안 봤다"와 "볼 방법이 없다"를 가른다.**
    #    ⑤가 그 자리에서 표시한다 — 여기에 목록을 적지 않는다(사본 금지).
    unrun = [e["var"] for e in (state.n05_evidence or [])
             if e.get("status") == UNRUN]

    per_var: dict = {}
    for var in wanted:
        if var in unrun:
            per_var[var] = UNRUN
        else:
            per_var[var] = _judge(found.get(var)) if var in found else UNKNOWN

    # ⚠️ **미상을 숨기는 것이 아니다.** `per_var` 에는 그대로 남고 분모에서만
    #    빠진다. 실측(오늘 요미우리@히로시마): 미상 4/6 = 0.667 → 모름과반이
    #    미실행 3개를 빼면 1/3 = 0.333 → 확인됨.
    scored = [v for v in per_var.values() if v != UNRUN]
    # 🔴 **잴 것이 하나도 없으면 확인됨이 아니다.** 분모가 0 일 때 통과시키면
    #    "아무것도 안 보고 확인"이 된다.
    total = len(scored)
    n_unknown = sum(1 for v in scored if v == UNKNOWN)
    unknown_ratio = round(n_unknown / total, 4) if total else 1.0
    core_refuted = [k for k, v in per_var.items()
                    if v == REFUTED and wanted.get(k)]

    board_ratio = float(R.get("unknown_ratio_board", 0.5))
    # 🔴 [CNF-2 2026-09-20] **반증의 뜻은 가설이 정한다**(④가 싣는다).
    #    딥서치(FORKS F-19): absence of evidence 는 "그 주장이 참이었다면
    #    근거가 나왔을 것"인 만큼만 evidence of absence 다.
    #      철회 — 가설이 "픽을 세울 근거"였다. 없으면 픽이 선다는 말이 거짓이다.
    #      강화 — 가설이 "픽을 무너뜨릴 근거"였다. 없으면 픽이 단단하다.
    #      중립 — 파생 재료. 승패 판정을 건드리지 않는다.
    #    ⚠️ 종전에는 이 구분 없이 언제나 철회였다. 그대로 반증을 켜면
    #       결장 0명인 건강한 라인업이 **전부 철회**된다(반대 위험).
    #    ⚠️ 표의 **원본은 `labels.REFUTED_MEANS`** 하나다. 여기서 다시 적지
    #       않는다(노드끼리 import 하지 않는 계약 때문에 ④와 ⑥이 각자 읽는다).
    #       옛 스냅샷·주입 상태처럼 `refuted_means` 가 없으면 가설 id 로 되짚는다.
    means = str(hyp.get("refuted_means")
                or REFUTED_MEANS.get(hyp.get("id"), R_RETRACT))
    if core_refuted and means == R_RETRACT:
        verdict = V_REFUTED
    elif unknown_ratio > board_ratio:
        verdict = V_UNKNOWN
    else:
        verdict = V_OK

    state.n06_verdict = {"per_var": per_var, "unknown_ratio": unknown_ratio,
                         "verdict": verdict, "core_refuted": core_refuted,
                         # 🔴 조용히 빼지 않는다 — 무엇을 분모에서 뺐는지 남긴다.
                         "unrun": unrun, "scored": total,
                         "refuted_means": means}
    logger.info("[flow:n06] game=%s 변수 %d → 확인 %d · 반증 %d(뜻 %s) · 미상 %d → %s",
                state.game_id, total,
                sum(1 for v in per_var.values() if v == CONFIRMED),
                sum(1 for v in per_var.values() if v == REFUTED),
                means, n_unknown, verdict)
    return state
