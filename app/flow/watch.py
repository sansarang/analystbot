"""[OBS-2 2026-09-20] v1.4 흐름 → 관측 상태. **순수 함수다.**

🔴 상태 이름·전이 허용표의 원본은 `app/engine/watch_state.py` 하나다.
   여기서 목록을 다시 적지 않는다(사본 금지 — `observer.py` 가 같은 6개를
   따로 선언하고 있었고 그것이 이 수정의 발단이다).
🔴 **흐름이 아는 것만 올린다.** `추천대기` 는 조건 A 가 `market_view`(분석
   LLM 판단)와 `swap_agree` 를 요구하는데 v1.4 경로에 그 값이 없다 —
   없는 값을 지어내 상태를 올리지 않는다.
🔴 **역방향 전이는 없다.** 재실행이 `추천` 을 `후보` 로 되돌리면 이미 나간
   카드를 되돌려야 한다. 전이는 반드시 허용표를 지난다.
⚠️ DB·LLM·HTTP 를 부르지 않는다(`gate.py`·`hypothesis.py` 와 같은 규칙).
"""
from __future__ import annotations

from app.engine.watch_state import (CANDIDATE, DONE, OBSERVE, PICKED,
                                    next_state)
from app.flow.labels import BOARD

#: 🔴 게이트 라벨의 원본은 `flow.labels` 다. `보드고정` 만 관측에 머문다 —
#   나머지 셋(동의·시장과대·가치의심)은 전부 조사 대상이므로 후보다.
_OBSERVE_GATES = (BOARD, None, "")


def state_of(*, gate: str | None, sent: bool, started: bool) -> str:
    """이 경기가 지금 어느 상태인가. 🔴 순서가 있다 — 뒤가 이긴다.

    ⚠️ `종료` 를 `추천` 보다 뒤에 두지 않는다. 킥오프가 지났으면 발송
       여부와 무관하게 끝난 경기다.
    """
    if started:
        return DONE
    if sent:
        return PICKED
    if gate in _OBSERVE_GATES:
        return OBSERVE
    return CANDIDATE


def advance(current: str | None, want: str) -> str:
    """허용표를 지난 전이 결과. 거부되면 **현재 상태 그대로**다.

    🔴 예외를 던지지 않는다 — 상태기계가 판정을 막으면 안 된다
       (`watch_state.next_state` 가 이미 그렇게 적혀 있다).
    """
    return next_state(current or OBSERVE, want).state
