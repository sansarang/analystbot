"""[D27] `llm.daily_call_cap` 을 **config 에서 안 읽는다.**

🔴 `_llm_budget_ok` 가 `app.flow.rules` 를 쓴다. 그 모듈은 경로에 `flow.`
   접두사를 붙이므로 `flow.llm.daily_call_cap` 을 찾는데, 실제 블록은
   **최상위 `llm:`** 이다:

    실측 2026-09-22 (운영 컨테이너):
      flow.rules.get("llm.daily_call_cap")   → None
      engine.rules.get("llm.daily_call_cap") → 200

🔴 **지금 증상이 없는 이유가 위험하다.** 코드의 폴백(`200`)이 config 값과
   우연히 같아서 아무도 몰랐다. `config/rules.yaml` 을 고쳐도 **반영되지
   않는다** — 상한을 내려도 LLM 이 계속 나간다.

⚠️ 같은 파일의 `get_depth`·`_article_cap` 은 `app.flow.rules` 가 **맞다** —
   `depth_fallback`·`depth_articles` 는 실제로 `flow:` 블록 안에 있다
   (실측: flow→'normal' / {'shallow':0,'normal':2,'deep':5}).
   그래서 이 수정은 **`_llm_budget_ok` 한 함수만** 건드린다.
"""
from __future__ import annotations

import pytest


class _Redis:
    """오늘 100번 썼다고 답하는 가짜 redis."""

    def __init__(self, used: int):
        self._used = used

    async def hget(self, key, field):
        return str(self._used)


@pytest.fixture
def cap50(monkeypatch):
    """config 에 상한 50 을 넣는다. `flow:` 블록도 **살려 둔다** —
    `depth_*` 가 거기서 와야 하므로 그것까지 깨면 다른 것을 재게 된다."""
    from app.engine import rules as R

    doc = {"llm": {"daily_call_cap": 50},
           "flow": {"depth_fallback": "normal",
                    "depth_articles": {"shallow": 0, "normal": 2, "deep": 5}}}
    monkeypatch.setattr(R, "_DOC", doc)
    return doc


@pytest.mark.asyncio
async def test_상한을_config_에서_읽는다(cap50):
    """🔴 config 가 50 이고 오늘 100번 썼으면 **막아야** 한다.

    HEAD 에서는 `flow.llm.daily_call_cap` 이 None 이라 코드 폴백 200 이 쓰이고
    100 < 200 이므로 **통과**한다 — 설정을 고쳐도 반영되지 않는다는 뜻이다.
    """
    from app.collectors import satellite as SAT

    assert await SAT._llm_budget_ok(_Redis(100)) is False, (
        "config 의 llm.daily_call_cap=50 이 반영되지 않았다 — "
        "코드 폴백 200 을 보고 있다(D27)")


@pytest.mark.asyncio
async def test_상한_안이면_통과한다(cap50):
    """⚠️ 반대 위험 — 막기만 하는 수정이 아니다."""
    from app.collectors import satellite as SAT

    assert await SAT._llm_budget_ok(_Redis(10)) is True


@pytest.mark.asyncio
async def test_redis_가_없으면_막지_않는다(cap50):
    """⚠️ 셀 수 없을 때 막으면 추출이 통째로 멈춘다(관측만)."""
    from app.collectors import satellite as SAT

    assert await SAT._llm_budget_ok(None) is True


def test_depth_는_여전히_flow_rules_다():
    """🔴 **같이 바꾸지 않는다.** `depth_*` 는 `flow:` 블록이 원본이다 —
    한꺼번에 engine 으로 옮기면 그쪽이 None 이 되어 조용히 폴백으로 돈다."""
    from app.engine import rules as R
    from app.flow import rules as FR

    assert FR.get("depth_fallback") is not None
    assert R.get("depth_fallback") is None, (
        "depth_fallback 이 최상위로 옮겨졌다면 이 계약을 다시 써야 한다")
    assert FR.get("llm.daily_call_cap") is None, (
        "flow.llm 블록이 생겼다면 D27 의 전제가 바뀐 것이다")
    assert R.get("llm.daily_call_cap") is not None
