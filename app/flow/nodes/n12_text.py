"""[v1.4] ⑫ 서술 — 확정 사실 JSON → 4문장. 배당·H2H·시즌 누적은 입력에 없다.

🔴 **STEP 1 스켈레톤이다.** 지금은 상태를 그대로 돌려준다(패스스루).
   실제 구현은 지시문의 해당 STEP 에서 붙인다 — 그 전에 채우지 않는다.
🔴 다른 노드를 import 하거나 호출하지 않는다. 분기는 `run.py` 가 한다.
🔴 자기 키(`n12_text`)만 쓴다.
"""
from __future__ import annotations

NODE = "n12_text"


def run(state, ctx):
    """⑫ 서술. 지금은 패스스루."""
    return state
