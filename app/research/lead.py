"""🔴🔴 **§3 — 리드**(작업 지시서 2026-10-05). **리드는 코드다**(LLM 아님).

> `lead.py` 가 하는 일은 **넷뿐**이고, 그 밖의 일을 하면 계약 위반이다.
>  1. **병합** — 하위 8개의 `variables[]` 조각을 합친다
>  2. **장부 갱신** — 유형군 × 팀 칸마다 `searched`/`found`/`empty`/`not_tried`
>  3. **2차 보충(최대 1회)** — `not_tried`·`empty` 유형군만, 남은 예산 안에서
>  4. **깔때기 집계** — 하위별 한 줄 + 합계
>
> **리드가 하지 않는 것**: LLM 호출로 변수·가설·시나리오를 만들지 않는다(M60).
> 변수 내용을 고치지 않는다. 하위 결과를 버리지 않는다(버리는 건 검증층의
> 사유 코드만).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, TypedDict, Union

logger = logging.getLogger(__name__)

#: 🔴 세마포어는 **과정 전체**의 것이다 — 하위 8개가 공유해야 상한이 뜻을 갖는다.
#  ⚠️ LDR 의 속도 제한 모듈이 같은 결론을 적는다: *"에이전트가 호출마다 새
#     인스턴스를 만들어 per-instance 간격이 안 걸렸다."* 🔴 이 저장소도 같은
#     병을 GDELT 에서 겪었다(2026-10-05: 체인마다 벌점을 잊었다).
_GATES: dict[tuple[str, int], asyncio.Semaphore] = {}


def limits() -> dict[str, int]:
    """🔴 동시성 상한 — `config/llm.yaml` `budget.concurrency`(M66).

    ⚠️ 수를 코드에 박지 않는다(지시서 §2: *"전부 설정에 상수로"*).
    """
    from app import solar
    box = dict(solar.budget_cfg().get("concurrency") or {})
    if not box:
        raise KeyError("🔴 `budget.concurrency` 가 `config/llm.yaml` 에 없다")
    out = {str(k): int(v) for k, v in box.items()}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **429 를 받았으면 Solar 동시 호출을 낮춘다** — 사용자 지시 2026-10-06 ④
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 429면 Solar 동시 호출을 **2로 낮추고** `Retry-After` 를 따르는 재시도.
    #
    #  ⚠️ `solar_after_429` 가 설정에 **이미 있었는데 아무도 읽지 않았다**
    #     (#2 배선 — 안 이어진 코드는 없는 코드보다 나쁘다).
    #  🔴 낮춘 수는 `solar.solar_concurrency()` **한 곳**이 정한다(사본 금지).
    out["solar"] = solar.solar_concurrency()
    return out


def gate(name: str) -> asyncio.Semaphore:
    """🔴🔴 **그 통로의 세마포어**(M66) — 같은 이름이면 같은 객체다.

    ⚠️ `asyncio.Semaphore` 는 만든 이벤트 루프에 묶인다. 루프가 바뀌면 새로
       만든다 — 안 그러면 *"다른 루프의 future"* 로 터진다.
    """
    key = str(name)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    # 🔴 **루프별로** 든다 — `Semaphore` 는 만든 루프에 묶인다. ⚠️ 종전엔
    #    세마포어에 `_loop` 를 **붙여** 그것을 쟀다(pyright 가 그 자리를
    #    잡았다: `Cannot assign to attribute "_loop"`). 🔴 사전 열쇠에 루프를
    #    넣으면 남의 객체를 건드리지 않는다.
    box = (key, id(loop))
    got = _GATES.get(box)
    if got is None:
        got = asyncio.Semaphore(limits()[key])
        _GATES[box] = got
    return got




class SubtaskOut(TypedDict, total=False):
    """🔴🔴 **하위 에이전트 출력 꼴** — 사용자 지시 2026-10-05 (3번).

    > `lead.merge` 입력 타입을 **하위 에이전트 출력 타입 하나로 고정.**
    > **`dict(v)` 금지** — 필요하면 그 타입의 메서드로.

    ⚠️ 두 크래시가 **꼴 불일치**였다: `done.variables` 가 문자열, `merge` 가
       `Classified`. 🔴 `variables` 는 **판정층 변수 객체**(`Classified`)이거나
       **에이전트 변수 사전** 둘 다 올 수 있다 — 그래서 그 사실을 **타입에**
       적는다. 받는 쪽이 짐작하지 않는다.
    """

    name: str
    group: str
    kinds: tuple[str, ...]
    team_key: str
    searched: int
    fetched: int
    out: int
    secs: float
    verified: int
    failed: str
    variables: Sequence["VarLike"]


#: 🔴 변수 한 줄의 꼴 — **객체**(판정층)이거나 **사전**(에이전트 원형).
#  ⚠️ `Any` 가 아니다 — 둘뿐임을 적어 두면 세 번째가 들어올 때 타입이 막는다.
VarLike = Union[Mapping[str, object], object]

#: 🔴 2차 보충 횟수 — **한 번뿐**이다(M64). ⚠️ *"2차 뒤에도 비면 그대로
#  `gaps` 로 보고한다 — **3차는 없다**."*
SECOND_ROUNDS = 1

#: 🔴 2차가 돌 **대상 상태** — 지시서 §3-3: *"`not_tried`·`empty` 인 유형군만"*.
#
#  🔴🔴 **`budget_cut` 을 더했다** — 사용자 지시 2026-10-06 ③:
#     > 한 팀 하위 4개 중 **하나라도 `budget_cut`** 이면 2차 보충 대상.
#  ⚠️ 까닭: 예산에 막힌 하위는 변수를 **냈을 수도** 있어 `searched` 로 적히고,
#     그러면 2차가 그 칸을 건너뛴다. 🔴 실측 2026-10-06: 조지아 쪽 하위가
#     `6744/4000` 으로 막혀 판정층 변수 **0개**였는데 2차 대상 판정은 그 사실을
#     보지 못했다(상태만 보고 **왜** 비었는지는 안 봤다).
SECOND_STATES: tuple[str, ...] = ("not_tried", "empty", "budget_cut")






def _why(book, group: str, key: str, said: str) -> None:
    """🔴 장부 칸의 **사유** — `Book` 이 칸을 들면 그것을 쓰고, 없으면 만든다."""
    box = getattr(book, "whys", None)
    if box is None:
        box = {}
        book.whys = box
    box[(str(group), str(key))] = str(said)






def _k(n: object) -> str:
    """🔴 토큰을 `4.1k` 꼴로 — 자리를 아낀다(지시서 §3-4 의 예시 그대로).

    ⚠️ `object` 를 `int()` 에 바로 넣지 않는다 — pyright 가 그 자리를 잡았다.
       🔴 수가 아닌 것이 오면 **0** 이고, 그것이 거짓이 되지 않게 호출부가
       이름으로 적는다(#3).
    """
    got = int(n) if isinstance(n, (int, float, str)) and str(n).strip() else 0
    return f"{got / 1000:.1f}k" if got >= 1000 else str(got)


