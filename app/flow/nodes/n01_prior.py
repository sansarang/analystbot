"""[v1.4] ① 사전값 — 자료12 team_elo(팀당 1값) → p_prior. 야구 2-way · 축구 3-way. 시즌 누적표 금지.

🔴 **STEP 1 스켈레톤이다.** 지금은 상태를 그대로 돌려준다(패스스루).
   실제 구현은 지시문의 해당 STEP 에서 붙인다 — 그 전에 채우지 않는다.
🔴 다른 노드를 import 하거나 호출하지 않는다. 분기는 `run.py` 가 한다.
🔴 자기 키(`n01_prior`)만 쓴다.
"""
from __future__ import annotations

NODE = "n01_prior"


def run(state, ctx):
    """① 사전값. 지금은 패스스루."""
    return state
