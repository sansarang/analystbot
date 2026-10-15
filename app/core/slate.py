"""🔴🔴 **P0 — 3단 실행 시각표**(수정 지시 2026-10-13 밤 P0).

> 사전 실행: 경기 확정되면 **T−24h 기본 카드**(XI 없이) → **T−3h 갱신**(결장·
> 검색) → 확정 XI 뜨면 즉시 **⑲**(T−60~45분). 기본 카드는 킥오프 **3시간 전**
> 까지 반드시 나와 있어야 한다.
> 슬레이트 스케줄러: 그날 대상 경기 전부를 킥오프 순으로 큐에 올리고 **각 단계
> 시각을 카드 머리에 찍는다**(T−24h/T−3h/XI 확정 판 각각).
> 시간 상한: 카드 1장 **15분**. 넘는 단계는 ⬜ + 사유로 넘기고 카드를 낸다.
> 킥오프가 지난 카드는 **"사후 기록용"** 으로만 저장.

🔴 이 모듈은 **시각만 센다** — 확률·등급에 닿지 않는다(계약 SL1).
⚠️ 모든 시각은 **KST 로 표시**하고 속으로는 UTC 다(절대규칙 2).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

#: 🔴 단계 이름과 **킥오프 전 시간**(지시의 그 셋). `xi` 는 창(60~45분)이다.
STAGES: tuple[tuple[str, float], ...] = (
    ("기본", 24.0), ("갱신", 3.0), ("XI", 1.0))

#: 🔴 XI 단계의 창 — T−60분에 열고 T−45분까지 돈다
XI_OPEN_MIN, XI_CLOSE_MIN = 60, 45

#: 🔴🔴 카드 한 장의 **벽시계 상한**(분) — 넘는 단계는 ⬜ 로 넘긴다
#
#  ⚠️ 실측 2026-10-15: 수집이 **17~18분**이 걸려(③ 딥서치가 대부분) 마지막
#     단계 ⑯ 종합 평이 **늘 굶었다** — 남은 예산이 0이라 LLM 을 못 불렀고,
#     카드에는 `LLM_TIMEOUT` 으로만 찍혀 **공급자 장애처럼 보였다**.
#     (Svay Rieng 17분 · San Diego 18분 · 상한은 15분이었다)
#  🔴 15 → **20분**(사용자 결정 2026-10-15). ⚠️ 상한만 올리면 같은 병이
#     재발한다 — 그래서 `deadline.RESERVE_SEC`(⑯ 몫)을 **함께** 둔다.
CARD_CAP_MIN = 20.0


def times_of(kickoff: datetime) -> dict[str, datetime]:
    """🔴 그 경기의 단계 시각(UTC). `{기본, 갱신, XI, 킥오프}`."""
    if kickoff.tzinfo is None:
        raise ValueError("🔴 킥오프에 시간대가 없다 — naive 는 받지 않는다")
    out = {name: kickoff - timedelta(hours=hrs) for name, hrs in STAGES}
    out["킥오프"] = kickoff
    return out


def stage_of(kickoff: datetime, now: datetime) -> tuple[str, str]:
    """🔴🔴 **지금이 어느 단계인가**. `(단계, 사유)`.

    🔴 `사후` 는 킥오프를 지난 실행이다 — 카드는 **사후 기록용**으로만 쓴다.
    """
    if now.tzinfo is None:
        raise ValueError("🔴 `now` 에 시간대가 없다")
    box = times_of(kickoff)
    left = (kickoff - now).total_seconds() / 60.0
    if left < 0:
        return "사후", (f"🔴 **킥오프를 {abs(left):.0f}분 지났다** — 이 카드는 "
                        f"**사후 기록용**이다(예측이 아니다)")
    if left <= XI_OPEN_MIN:
        return "XI", (f"**XI 단계**(T−{left:.0f}분) — 확정 XI 가 뜨면 즉시 ⑲ "
                      f"재분석한다(창 T−{XI_OPEN_MIN}~{XI_CLOSE_MIN}분)")
    if left <= 3 * 60:
        return "갱신", (f"**갱신 단계**(T−{left / 60:.1f}h) — 결장·검색을 "
                        f"다시 받는다")
    if left <= 24 * 60:
        return "기본", (f"**기본 단계**(T−{left / 60:.1f}h) — XI 없이 바닥을 "
                        f"만든다(T−3h 까지 반드시 나와 있어야 한다)")
    return "대기", (f"⏳ 아직 멀다(T−{left / 60:.1f}h) — 큐에 올려 두고 "
                    f"T−24h 에 기본 카드를 낸다")


def head_of(kickoff: datetime, now: datetime) -> str:
    """🔴🔴 **카드 머리 한 줄** — 단계 시각표 + 지금 단계(전부 KST)."""
    box = times_of(kickoff)
    said, why = stage_of(kickoff, now)
    rows = " · ".join(
        f"{name} {box[name].astimezone(KST):%m-%d %H:%M}"
        for name in ("기본", "갱신", "XI"))
    return (f"⏱ **실행 단계** — 지금 {said} · {rows} · 킥오프 "
            f"{box['킥오프'].astimezone(KST):%m-%d %H:%M} KST(실행 "
            f"{now.astimezone(KST):%H:%M}) — {why}")


def queue(rows: list[dict], *, now: datetime) -> list[dict]:
    """🔴 그날 경기를 **킥오프 순**으로 큐에 올린다 — `{경기, 단계, 시각}`.

    ⚠️ 입력은 `{"name": 글자, "kickoff": datetime}` 줄이다(슬레이트가 준다).
    """
    out: list[dict] = []
    for one in sorted(rows or [], key=lambda r: r["kickoff"]):
        said, why = stage_of(one["kickoff"], now)
        out.append({"name": str(one.get("name") or ""),
                    "kickoff": one["kickoff"], "stage": said, "why": why,
                    "times": times_of(one["kickoff"])})
    return out
