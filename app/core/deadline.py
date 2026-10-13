"""🔴🔴 **P0 — 카드 한 장의 벽시계 상한**(수정 지시 2026-10-13 밤 P0).

> 시간 상한: 카드 1장 **15분**. 넘는 단계는 **⬜ + 사유로 넘기고 카드를 낸다**.

🔴 왜 — 오늘 실측: 세 카드 실행에 **2h17m** 이 걸려 상하이–대전 카드가 **킥오프
   뒤**에 나왔다. 늦은 카드는 예측이 아니다.
🔴 **멈추는 것이 아니라 넘긴다** — 남은 단계는 ⬜ 와 사유를 남기고 카드가 나간다
   (#3 조용한 0 금지).
⚠️ 시계는 **단조 시계**(`time.monotonic`)다 — 벽시계가 바뀌어도 안 흔들린다.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class Deadline:
    """🔴 남은 시간을 아는 하나의 물건. `None` 이면 상한이 없다."""

    def __init__(self, cap_min: float | None) -> None:
        self.cap_min = (float(cap_min) if cap_min else None)
        self.t0 = time.monotonic()
        #: 🔴 넘겨서 **건너뛴 단계** — 카드가 이 목록을 적는다
        self.skipped: list[str] = []

    def used_min(self) -> float:
        return (time.monotonic() - self.t0) / 60.0

    def left_min(self) -> float:
        if self.cap_min is None:
            return float("inf")
        return self.cap_min - self.used_min()

    def over(self) -> bool:
        return self.left_min() <= 0

    def skip(self, stage: str) -> str:
        """🔴 그 단계를 넘긴다 — **사유를 돌려주고 기록한다**."""
        said = (f"⬜ **상한 {self.cap_min:g}분을 넘겨 건너뛰었다**"
                f"({self.used_min():.1f}분 썼다) — `{stage}`")
        self.skipped.append(str(stage))
        logger.info("[deadline] %s", said)
        return said

    def said_of(self) -> str:
        """🔴 카드 한 줄 — 상한과 건너뛴 단계."""
        if self.cap_min is None:
            return "⏱ 상한 없음"
        head = (f"⏱ **상한 {self.cap_min:g}분** · 쓴 시간 "
                f"{self.used_min():.1f}분")
        if not self.skipped:
            return head + " · 건너뛴 단계 **없다**"
        return head + " · 🔴 건너뛴 단계 — " + " · ".join(self.skipped)
