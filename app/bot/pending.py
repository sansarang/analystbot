"""🔴🔴 **버튼이 가리키는 것을 들고 있는 자리** — 사용자 지시 2026-10-10 §1-3·§2-3.

🔴 `callback_data` 가 **64바이트**뿐이라 경기 열쇠·질문 글자를 그대로 못 싣는다.
   그래서 짧은 **토큰**을 주고 내용은 여기 둔다.

⚠️ **이 과정이 사는 동안만** 산다(봇 프로세스 하나다). 🔴 그것으로 충분한 까닭:
   버튼은 방금 보낸 카드에 붙고, 봇이 재시작하면 사용자가 다시 물으면 된다.
   ⚠️ 영구 저장을 쓰면 *"언제 지우나"* 가 새 문제로 생긴다(지금 필요 없다).
🔴 상한이 있다(`CAP`) — 오래된 것부터 버린다. 메모리가 조용히 자라지 않게.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: 🔴 들고 있는 카드 수 상한. ⚠️ 넘으면 **오래된 것부터** 버린다
CAP = 200


@dataclass
class Ask:
    """🔴 버튼 하나가 가리키는 **질문 한 건**."""

    asked: str = ""
    board_text: str = ""
    #: 🔴 고를 수 있는 후보들(§1-3) — 버튼 번호가 이 목록의 자리다
    picks: list[dict] = field(default_factory=list)
    #: 🔴 확정된(또는 고른) 경기 열쇠 — `pick_key` 로 못 박는 그 값
    key: str = ""
    #: 🔴 카드가 나간 메시지 — §2-3 이 **그 메시지를 고쳐 쓴다**
    chat_id: int | None = None
    message_id: int | None = None
    #: 🔴 라인업 감시 작업(§2-3) — `None` 이면 안 걸었다
    watch: Any = None


_BOX: dict[str, Ask] = {}
_SEQ = 0


def new(ask: Ask) -> str:
    """🔴 토큰을 발급한다 — **짧다**(콜백 64바이트 안에 들어가야 한다)."""
    global _SEQ
    _SEQ += 1
    token = f"a{_SEQ:x}"
    _BOX[token] = ask
    while len(_BOX) > CAP:
        old = next(iter(_BOX))
        box = _BOX.pop(old, None)
        said = getattr(box, "watch", None)
        if said is not None and not said.done():
            said.cancel()           # 🔴 감시도 함께 끈다(누수 금지)
    return token


def get(token: object) -> Ask | None:
    """🔴 그 토큰의 질문. ⚠️ 없으면 `None` — 호출부가 *"다시 물어 달라"* 고 말한다."""
    return _BOX.get(str(token or ""))


def tokens() -> list[str]:
    """🔴 살아 있는 토큰들 — `report` 가 이것으로 센다."""
    return list(_BOX)


def report() -> str:
    """🔴🔴 `/상태` 한 줄 — **감시 중인 경기**(§2-3). ⚠️ 운영자가 볼 유일한 눈이다.

    🔴 *"사용자가 누른 경기만 돈다"* 를 지키는지 사람이 확인할 자리다 — 누른 적
       없는데 감시가 돌고 있으면 그 자체가 결함이다.
    """
    live = []
    for tok in tokens():
        ask = get(tok)
        said = getattr(ask, "watch", None) if ask else None
        if said is not None and not said.done():
            live.append(f"`{getattr(ask, 'asked', '?')}`")
    return (f"🔔 **라인업 감시** {len(live)}건" + (" — " + " · ".join(live[:5])
                                              if live else " (없다)")
            + f" · 들고 있는 카드 {len(tokens())}장")
