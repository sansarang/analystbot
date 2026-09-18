"""[v1.4] 오케스트레이터 — **분기 로직은 이 파일에만 둔다** (지시문 STEP 1).

🔴 노드는 서로 부르지 않는다. 순서와 멈춤은 여기서만 정한다.
🔴 **멈춤은 실패가 아니다**(지시문 규율 9):
     ③ 보드 고정 · ⑥ 반박됨 · ⑥ 모름과반 · ⑪ 값 없음
   이 경로에서는 ⑫·⑬ 이 **호출되지 않아야** 하고, 호출되면 버그다.
   계약 테스트가 다섯 경로의 호출 목록을 정확히 대조한다.
⚠️ 스냅샷은 노드당 1행. `analysis_runs` 에 남는다 — 배선 오류 추적의 핵심이다.
"""
from __future__ import annotations

import logging

from app.flow.nodes import (n01_prior, n02_market, n03_gate, n04_hyp,
                            n05_evidence, n06_verdict, n07_adjust, n08_pcode,
                            n09_conf, n10_rejudge, n11_value, n12_text,
                            n13_send)
from app.flow.state import State

logger = logging.getLogger(__name__)

#: ⑤~⑨ — ⑩ 재판정이 **1회만** 다시 돌리는 구간.
RERUN_5_TO_9 = (n05_evidence, n06_verdict, n07_adjust, n08_pcode, n09_conf)


async def snapshot(state: State, node: str, ctx=None) -> None:
    """노드 1개 = 1행. 🔴 **기록 실패가 판정을 막지 않는다.**

    ⚠️ 그래도 조용히 실패하지 않는다 — 경고 한 줄을 남긴다.
    """
    state.trace.append(node)
    pool = getattr(ctx, "pool", None) if ctx is not None else None
    if pool is None:
        return
    try:
        await pool.execute(
            "INSERT INTO analysis_runs (run_id, game_id, node, snapshot_json) "
            "VALUES ($1, $2, $3, $4::jsonb)",
            state.run_id, state.game_id, node, state.to_json())
    except Exception as exc:
        logger.warning("[flow] 스냅샷 실패 run=%s node=%s: %s",
                       state.run_id, node, exc)


def finish(state: State, stop_reason: str | None) -> State:
    """멈춤 사유를 쓰고 끝낸다. 🔴 이 뒤로 노드를 부르지 않는다."""
    state.stop_reason = stop_reason
    return state


async def rerun_5_to_9(state: State, ctx) -> State:
    """⑩ 이 부르는 재실행. **⑤~⑨ 만** 다시 돈다."""
    for node in RERUN_5_TO_9:
        state = node.run(state, ctx)
        await snapshot(state, node.NODE + ":rerun", ctx)
    return state


async def run_game(game: dict, ctx) -> State:
    """경기 1건. 지시문 STEP 1 골격 — **이 순서를 바꾸지 않는다.**"""
    s = State.new(game)
    for node in (n01_prior, n02_market):
        s = node.run(s, ctx)
        await snapshot(s, node.NODE, ctx)

    s = n03_gate.run(s, ctx)
    await snapshot(s, n03_gate.NODE, ctx)
    if (s.n03_gate or {}).get("stop"):          # 보드 고정 → 수집도 하지 않는다
        return finish(s, "n03_freeze")

    s = n04_hyp.run(s, ctx)
    await snapshot(s, n04_hyp.NODE, ctx)
    s = n05_evidence.run(s, ctx)
    await snapshot(s, n05_evidence.NODE, ctx)
    s = n06_verdict.run(s, ctx)
    await snapshot(s, n06_verdict.NODE, ctx)

    verdict = (s.n06_verdict or {}).get("verdict")
    if verdict == "반박됨":                      # 픽 철회
        return finish(s, "n06_refuted")
    if verdict == "모름과반":                    # 보드로 내린다
        return finish(s, "n06_unknown")

    for node in (n07_adjust, n08_pcode, n09_conf):
        s = node.run(s, ctx)
        await snapshot(s, node.NODE, ctx)

    s = n10_rejudge.run(s, ctx)
    await snapshot(s, n10_rejudge.NODE, ctx)
    # 🔴 재판정은 **최대 1회**. 트리거가 있으면 ⑤~⑨ 를 다시 돌린다.
    if (s.n10_rejudge or {}).get("triggered"):
        s = await rerun_5_to_9(s, ctx)

    s = n11_value.run(s, ctx)
    await snapshot(s, n11_value.NODE, ctx)
    if (s.n11_value or {}).get("pick_type") == "보드":
        return finish(s, "n11_no_value")

    s = n12_text.run(s, ctx)
    await snapshot(s, n12_text.NODE, ctx)
    # 🔴 서술이 입력에 없는 사실을 지어내면 카드를 만들지 않는다(지시문 STEP 11).
    if (s.n12_text or {}).get("hallucination"):
        return finish(s, "n12_hallucination")

    s = n13_send.run(s, ctx)
    await snapshot(s, n13_send.NODE, ctx)
    return finish(s, None)
