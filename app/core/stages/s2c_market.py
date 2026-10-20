"""🔴🔴 **s2c — ④ 시장 층.** 네 층 지시서 §2. `s1` 뒤, `s2` 와 **병렬**.

```
MatchRef (+사용자 보드) → (MarketProb 피드, MarketProb 사용자 보드)
```

🔴 **두 열을 섞지 않는다**(§2-6 · 불변식) — 피드 배당과 사용자 보드 배당은 **따로**다.
🔴 피드가 없으면 사용자 보드가 시장 열이 된다(§2-6 마지막 줄).
⚠️ 키·예산·매칭 중 하나라도 안 되면 `MarketProb(why=…)` 로 **사유만** 남는다.
"""
from __future__ import annotations

import logging

from app.core import odds
from app.core.schema import Board, MarketProb, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)


async def run(ref: MatchRef, *, pool, net, state: RunState,
              board: Board | None = None,
              reanalyze: bool = False) -> tuple[MarketProb, MarketProb]:
    """🔴 `(피드 시장, 사용자 보드 시장)`. ⚠️ 둘 다 비어도 **카드는 나온다**."""
    feed = await odds.from_feed(ref, pool=pool, net=net, state=state,
                               reanalyze=reanalyze)
    mine = odds.from_board(board, source="user_board")
    if feed.probs:
        state.note(f"s2c ④ {feed.basis} · 마켓 {len(feed.probs)}칸 · {feed.why}")
    else:
        state.note(f"s2c ④ {feed.why}")
    if mine.probs:
        state.note(f"s2c 사용자 보드 배당 {len(mine.probs)}칸")
    elif board is not None and getattr(board, "lines", None):
        state.note(f"s2c 사용자 보드 — {mine.why}")
    return feed, mine


def column(feed: MarketProb, user: MarketProb) -> tuple[MarketProb, str]:
    """🔴 §2-6 — **어느 것이 시장 열인가**. `(시장 열, 카드에 적을 말)`.

    피드가 있으면 피드가 시장 열이고 사용자 보드는 **옆 열**이다. 피드가 없으면
    사용자 보드가 시장 열이 된다.
    """
    if feed.probs:
        return feed, feed.basis
    if user.probs:
        return user, f"{user.basis}(피드 없음 — {feed.why})"
    return MarketProb(why=feed.why or "시장 없음"), ""
