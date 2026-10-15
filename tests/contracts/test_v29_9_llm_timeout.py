"""🔴🔴 **LLM 타임아웃은 카드 상한 안이다** — 사용자 지시 2026-10-15.

> 타임아웃부터 고쳐라

⚠️ 실사고 2026-10-15(MLS 10:30): 공급자가 응답을 안 끊어 봇이 **27분** 멈췄다.
   ① 소켓 상한(120초)이 **호출마다** 다시 서고 `ask` 는 두 번 부른다.
   ② 🔴 카드 상한이 **안 걸려 있었다** — 러너가 `st.deadline` 에 꽂았고
      읽는 칸은 `st.clock` 이다.
"""
from __future__ import annotations

import time

import pytest

from app.core import deadline as dl
from app.core.schema import DropReason, LlmFail
from app.core.state import RunState
from pydantic import BaseModel


class Out(BaseModel):
    said: str


def test_시계가_없으면_설정값_그대로다() -> None:
    secs, why = dl.call_cap_sec(None, 120)
    assert secs == 120 and why == ""


def test_남은_시간_안으로_깎는다() -> None:
    secs, why = dl.call_cap_sec(dl.Deadline(1.0), 120)      # 1분 남았다
    assert secs < 120, "🔴 안 깎았다"
    assert secs <= 60 * dl.CALL_SHARE + 1, secs
    assert "깎았다" in why, why


def test_바닥이면_부르지_않는다() -> None:
    """🔴 `0` 이고 **사유가 있다**(#3 조용한 0 금지)."""
    got = dl.Deadline(0.1)                                  # 6초
    secs, why = dl.call_cap_sec(got, 120)
    assert secs == 0.0
    assert "부르지 않았다" in why, why


def test_상한을_넘긴_시계는_안_부른다() -> None:
    got = dl.Deadline(0.001)
    time.sleep(0.1)
    secs, why = dl.call_cap_sec(got, 120)
    assert secs == 0.0 and why, why


def test_ask_는_상한이_바닥이면_망에_안_나간다() -> None:
    """🔴🔴 **망에 나가는 자리를 아예 안 부른다** — 사유는 `llm_timeout`."""
    from app.core import llm
    st = RunState()
    st.clock = dl.Deadline(0.05)                            # 3초
    called: list = []

    def _never(url, key, body, timeout):                    # noqa: ANN001
        called.append(url)
        raise AssertionError("🔴 망에 나갔다")

    got = llm.ask(provider="solar", purpose="spell",
                  messages=[llm.Message(role="user", content="x")],
                  out=Out, state=st, _post=_never)
    assert isinstance(got, LlmFail), got
    assert got.reason == DropReason.LLM_TIMEOUT, got.reason
    assert not called, "🔴 상한이 바닥인데 호출했다"


def test_ask_가_받은_초를_그대로_소켓에_넘긴다() -> None:
    """🔴 깎은 초가 **실제 호출 인자**로 가야 한다(표시만이면 뜻이 없다)."""
    from app.core import llm
    st = RunState()
    st.clock = dl.Deadline(1.0)                             # 60초
    saw: list = []

    def _spy(url, key, body, timeout):                      # noqa: ANN001
        saw.append(int(timeout))
        return {"choices": [{"message": {"content": '{"said":"x"}'}}],
                "usage": {}}

    got = llm.ask(provider="solar", purpose="spell",
                  messages=[llm.Message(role="user", content="x")],
                  out=Out, state=st, _post=_spy)
    assert saw, "🔴 호출이 안 갔다"
    assert saw[0] <= 60 * dl.CALL_SHARE + 1, saw
    assert isinstance(got, Out), got


def test_러너는_시계를_clock_에_꽂는다() -> None:
    """🔴 `st.deadline` 은 **아무도 안 읽는다** — 그 자리에 꽂으면 상한이 없다."""
    said = __import__("pathlib").Path("tools/run_collect.py").read_text()
    assert "st.clock = " in said, "🔴 러너가 clock 에 안 꽂는다"
    assert "st.deadline = " not in said, "🔴 안 읽는 칸에 다시 꽂았다"


@pytest.mark.parametrize("name", ["MIN_CALL_SEC", "CALL_SHARE"])
def test_값은_한_곳에_있다(name: str) -> None:
    assert hasattr(dl, name), f"🔴 {name} 이 `core/deadline` 에 없다"
