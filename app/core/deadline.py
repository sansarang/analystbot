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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **LLM 한 번 호출도 남은 예산 안이다** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 타임아웃부터 고쳐라
#
#  ⚠️ 실사고 2026-10-15(MLS 10:30 두 경기): 공급자가 응답을 끊지 않아 봇이
#     **27분**을 `_ssl__SSLSocket_read` 에서 멈췄다(CPU 0% · 외부 작업 0).
#     ① `config/llm.yaml` 의 `timeout_sec: 120` 은 **소켓 한 번**의 상한이고
#        `llm.ask` 는 스키마 재요청으로 **두 번** 부른다 → 호출당 4분.
#        단계마다 여러 번 부르니 카드 하나가 27분이 됐다.
#     ② 🔴 그런데 더 나쁜 것 — 카드 상한(15분)이 **안 걸려 있었다**:
#        러너가 시계를 `st.deadline` 에 꽂았고 읽는 칸은 `st.clock` 이다.
#  🔴 그래서 호출마다 **남은 예산 안으로 깎고**, 남은 게 바닥이면 **안 부른다**
#     (#3 조용한 0 금지 — 왜 안 불렀는지 사유로 남긴다).

#: 🔴 LLM 한 번에 줄 수 있는 **최소** 초 — 이보다 적게 남으면 부르지 않는다
MIN_CALL_SEC = 20.0
#: 🔴 한 번 호출이 **남은 예산에서 가져갈 몫** — 1.0 이면 남은 전부를 쓴다.
#   ⚠️ 한 호출이 전부를 먹으면 뒤 단계가 통째로 ⬜ 가 된다.
CALL_SHARE = 0.5

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **마지막 단계 몫을 떼어 둔다** — 사용자 결정 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-15: 상한(15분)을 **수집이 다 써서**(17~18분) 마지막 단계
#     ⑯ 종합 평이 늘 굶었다 — 공급자는 멀쩡한데(solar 0.9초·deepseek 0.7초)
#     평이 **매번 비었다**.
#  🔴 상한을 올리는 것만으로는 **같은 병이 재발한다**(상한은 총량만 막고 순서를
#     안 지킨다). 그래서 **그 단계 몫을 처음부터 예약**한다 — 앞 단계는 이
#     초를 **못 쓴다**.
#: 🔴 ⑯ 종합 평에 남겨 두는 초
RESERVE_SEC = 90.0
#: 🔴 그 예약을 **쓸 수 있는** 목적(=마지막 단계)
RESERVED_PURPOSES: tuple[str, ...] = ("commentary",)


def call_cap_sec(clock: object | None, want: float, *,
                 reserved: bool = False) -> tuple[float, str]:
    """🔴🔴 그 호출에 줄 **초** — 남은 예산 안으로 깎는다. `(초, 사유)`.

    `0` 이면 **부르지 않는다**(사유를 그대로 카드·보고에 적는다).
    🔴 시계가 없으면 설정값 그대로다(상한 없는 실행 — 시험·도구).
    🔴 `reserved=False` 면 **⑯ 몫(`RESERVE_SEC`)을 뺀 나머지**만 쓴다.
    """
    want = float(want or 0.0)
    left = getattr(clock, "left_min", None)
    if left is None:
        return want, ""
    secs = float(left()) * 60.0
    if not reserved:
        # 🔴 앞 단계는 **예약분을 못 쓴다**
        secs -= RESERVE_SEC
    if secs <= MIN_CALL_SEC:
        return 0.0, (f"⏱ **남은 시간이 {secs:.0f}초다**(상한 "
                     f"{getattr(clock, 'cap_min', 0) or 0:g}분) — LLM 을 "
                     f"부르지 않았다")
    give = min(want, secs * CALL_SHARE)
    if give < MIN_CALL_SEC:
        give = min(want, MIN_CALL_SEC)
    if give < want:
        return give, (f"⏱ 타임아웃을 {want:.0f}초 → **{give:.0f}초**로 깎았다"
                      f"(남은 {secs:.0f}초의 {CALL_SHARE:g})")
    return give, ""
