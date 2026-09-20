"""[OBS-2 2026-09-20] 관측 상태기계가 **한 번도 안 돌았다.**

🔴 실측 2026-09-20: 운영 `pick_ledger` 1,393행 **전건 `watch_state` NULL**.
   `app/engine/watch_state.py`(77줄)와 `app/engine/observer.py`(110줄)가
   **둘 다 호출부 0건**이었다 — 그리고 둘이 같은 6개 상태를 각자 선언했다
   (사본). 상태·전이의 원본은 전이 허용표를 가진 `watch_state` 하나다.

🔴 흐름이 아는 것만 쓴다. 조건 A/B 는 `market_view`(분석 LLM)·`swap_agree` 를
   요구하는데 v1.4 경로에 그 값이 없다 — **없는 값을 지어내 상태를 올리지
   않는다.** 여기서 배선하는 것은 관측/후보/종료 셋이다.
"""
from __future__ import annotations

import pytest


def test_상태_목록이_한_곳이다():
    """🔴 사본 금지 — `observer` 가 목록을 다시 선언하면 안 된다."""
    from app.engine import observer as O
    from app.engine import watch_state as W

    assert O.STATES is W.STATES, "observer 가 STATES 를 따로 만들었다"
    assert set(O.TERMINAL) <= set(W.STATES)


def test_흐름_상태는_게이트가_정한다():
    """보드고정은 관측 · 게이트 대상은 후보. 🔴 코드만 전이한다."""
    from app.flow.watch import state_of

    assert state_of(gate="보드고정", sent=False, started=False) == "관측"
    assert state_of(gate="동의", sent=False, started=False) == "후보"
    assert state_of(gate="시장과대", sent=False, started=False) == "후보"
    assert state_of(gate="가치의심", sent=False, started=False) == "후보"
    assert state_of(gate=None, sent=False, started=False) == "관측"


def test_발송되면_추천_킥오프면_종료():
    from app.flow.watch import state_of

    assert state_of(gate="동의", sent=True, started=False) == "추천"
    assert state_of(gate="동의", sent=False, started=True) == "종료"


def test_역방향_전이는_거부된다():
    """🔴 추천에서 후보로 돌아가면 이미 나간 카드를 되돌려야 한다."""
    from app.engine import watch_state as W
    from app.flow.watch import advance

    assert advance("관측", "후보") == "후보"
    assert advance("후보", "추천") == "후보", "후보→추천 직행은 허용표에 없다"
    assert advance("추천", "후보") == "추천"
    assert advance("종료", "관측") == "종료"
    assert W.next_state("추천", "후보").changed is False


@pytest.mark.asyncio
async def test_슬레이트가_상태를_기록한다():
    """🔴 배선 — `run_slate` 가 경기마다 상태를 남긴다(조용한 0 금지)."""
    import inspect

    from app.flow import bridge

    src = inspect.getsource(bridge.run_slate)
    assert "watch" in src, "run_slate 가 상태를 기록하지 않는다"
