"""[v1.4] ⑪ 값 판정 — edge = p_code − 1/배당. 동의 게이트에서만 승패 픽.

🔴 **STEP 1 스켈레톤이다.** 지금은 상태를 그대로 돌려준다(패스스루).
   실제 구현은 지시문의 해당 STEP 에서 붙인다 — 그 전에 채우지 않는다.
🔴 다른 노드를 import 하거나 호출하지 않는다. 분기는 `run.py` 가 한다.
🔴 자기 키(`n11_value`)만 쓴다.
"""
from __future__ import annotations

NODE = "n11_value"


def run(state, ctx):
    """⑪ 값 판정. 지금은 패스스루."""
    return state
