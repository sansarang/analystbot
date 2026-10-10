"""🔴🔴 **§1 하위 과제 — 코드가 찾고, LLM 은 한 번 읽는다** (지시서 §1 · M128·M135).

> 에이전트 루프(LLM 이 검색어를 정하고 → 검색 → 다시 생각 → fetch → 다시 생각 →
> done)는 턴마다 추론 토큰을 쓰고 **40~88초**가 걸린다. 하위 8개 × 7턴이 26분과
> `budget_cut` 의 원인이다. 찾는 일은 **코드가**, 읽고 뽑는 일만 **LLM 이 한
> 번에** 하게 바꾼다.
>
> 결과: 하위당 LLM 호출 **1~2회**(전: 7턴). 목표 경기당 **6분 이하**.
> 에이전트 루프 코드는 **삭제하지 않고** 오픈월드 ⑥단(경기 찾기)에서만 쓴다 —
> 하위 과제 경로에서는 호출하지 않는다(M128).
> 추출 호출: `max_tokens` **4,000** · `reasoning_effort=low` (요청 본문에 실리는지
> 원장으로 확인) · 타임아웃 120초 · 재시도 1회 (M135).
> 예산 재조정 — 하위 출력 8,000 → **4,000**, 경기 64,000 → **40,000**,
> fetch 경기 16 → **24**.
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# 예산 재조정
# ══════════════════════════════════════════════════════════════════

def test_wo1_예산이_되돌아왔다():
    """🔴 *"상한을 올려서 budget_cut 해결"* 은 §8 금지 목록이다."""
    from app import rules
    b = rules.llm_budget()
    assert int(b["per_subtask"]["output_tokens"]) == 4_000, b["per_subtask"]
    # 🔴 수를 박지 않는다 — **하위 합계 + 2차 예비 = 경기 상한**이 불변식이다
    #    (실사고 2026-10-10: 하위 F 를 더하자 박아 둔 40_000·24 가 빨개졌다).
    sub = b["per_subtask"]
    from app.research import subtasks as _st
    n = 2 * len(_st.groups())
    assert int(b["per_match"]["output_tokens"]) == \
        int(sub["output_tokens"]) * n + int(sub.get("second_output_tokens") or 0), b
    assert int(b["per_match"]["tool_calls"]["fetch"]) == \
        int(sub["fetch"]) * n, b["per_match"]
    # 🔴 하위 8개 × 4,000 = 32,000 ≤ 경기 40,000 (2차 예비 8,000 이 그 차이다)
    assert 8 * 4_000 <= int(b["per_match"]["output_tokens"])


# ══════════════════════════════════════════════════════════════════
# M128 — 하위 경로에서 에이전트 루프를 부르지 않는다
# ══════════════════════════════════════════════════════════════════







# ══════════════════════════════════════════════════════════════════
# M135 — 추출 호출의 요청 본문
# ══════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════
# 거들
# ══════════════════════════════════════════════════════════════════

def _spy(monkeypatch, solar):
    seen = {"n": 0}

    def _chat(messages, **kw):
        seen["n"] += 1
        return {"choices": [{"message": {"content": '{"variables":[]}'}}],
                "usage": {"completion_tokens": 5, "prompt_tokens": 5}}

    monkeypatch.setattr(solar, "chat", _chat)
    return seen




def _ref():
    class _R:
        home, away = "Northern Ireland", "Georgia"
        home_id, away_id = "team:1", "team:2"
        competition = "UEFA Nations League B Grp. 2"
        sport = "soccer"
        langs = ("en",)
    return _R()


