"""[운영 안정화 1] 슬레이트 가동률 — 대상 / 발송 / **사유별** 미발송.

🔴 **"조용한 0"은 결함이다.** 종전에는 카드가 안 나가도 로그 몇 줄뿐이라
   사용자가 "봇이 죽었나"와 "라인업이 안 떴나"를 구분할 수 없었다
   (실측 2026-09-01: KBO 5경기 판정이 14:00에 끝났는데 카드 0장).
   안 재면 못 지킨다 — 발송률을 숫자로 만들고 미발송에는 전건 사유를 붙인다.

⚠️ 이 모듈은 **세기만 한다.** 발송 여부를 바꾸지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

KEY = "dispatch:{sport}:{date}"
TTL = 30 * 3600           # 슬레이트 하루 + 여유

#: 발송으로 치는 결과. `unchanged`(양쪽 해시 동일)는 **이미 도달한 것**이다 —
#  미발송이 아니다. 이걸 실패로 세면 발송률이 영원히 100%가 안 된다.
DELIVERED = ("sent", "revised", "unchanged")

#: 대상이 아닌 결과 — 분모에서 뺀다. 아직 창이 안 열렸거나 이미 시작한 경기.
NOT_TARGET = ("window_not_open", "already_started", "not_supported", "void")

#: 사람이 읽는 사유. 코드에 없는 값이 오면 그대로 쓴다 — 숨기지 않는다.
REASON_KR = {
    "cache_missing": "판정 캐시 없음",
    "unjudged": "판정 없음",
    "both_hash_same": "변경 없음(이미 발송)",
    "send_failed": "텔레그램 발송 실패",
    "window_not_open": "발송 창 전",
    "already_started": "이미 시작",
    "not_supported": "대상 종목 아님",
    "void": "취소·중단",
    "sent": "발송",
    "revised": "수정 발송",
    "unchanged": "변경 없음",
    # 🔴 [2026-09-06] 픽은 경기당 두 장이다. 세 장째는 **조용히 사라지지
    #    않고** 사유가 붙어 여기 잡힌다 — "조용한 0"은 결함이다.
    "card_cap": "카드 2장 상한 도달",
    # 두 번째 자리는 **최종 판정 카드의 몫**이다. 예비 재판정이 먼저 그
    #   자리를 먹으면 정작 최종 픽이 상한에 막혀 못 나간다.
    "card_reserved": "2장째는 최종 카드 몫",
}


async def record(redis, sport: str, date: str, outcome: str) -> None:
    """결과 1건 기록. 실패해도 발송을 막지 않는다."""
    if redis is None or not sport or not date:
        return
    key = KEY.format(sport=sport, date=date)
    try:
        await redis.hincrby(key, outcome, 1)
        await redis.expire(key, TTL)
    except Exception as exc:
        logger.debug("[dispatch] 기록 실패 %s %s: %s", sport, outcome, exc)


async def summary(redis, sport: str, date: str) -> dict:
    """{target, sent, revised, unchanged, misses:{사유:건수}, raw:{...}}.

    `target` = 전체 − 대상 아님. 미발송은 **전건 사유**가 붙는다.
    """
    out = {"sport": sport, "date": date, "target": 0, "sent": 0,
           "revised": 0, "unchanged": 0, "misses": {}, "raw": {}}
    if redis is None:
        return out
    try:
        raw = await redis.hgetall(KEY.format(sport=sport, date=date)) or {}
    except Exception as exc:
        logger.debug("[dispatch] 조회 실패 %s: %s", sport, exc)
        return out
    counts = {k: int(v) for k, v in raw.items() if str(v).lstrip("-").isdigit()}
    out["raw"] = counts
    for name, n in counts.items():
        if name in NOT_TARGET:
            continue
        out["target"] += n
        if name in DELIVERED:
            out[name] = out.get(name, 0) + n
        else:
            out["misses"][REASON_KR.get(name, name)] = n
    return out


def delivered(stats: dict) -> int:
    return sum(stats.get(k, 0) for k in DELIVERED)


def rate(stats: dict) -> float | None:
    """발송률. 대상이 0이면 **None** — 0%가 아니다. 없는 실패를 만들지 않는다."""
    t = stats.get("target") or 0
    return None if t <= 0 else delivered(stats) / t


def render(stats: dict, label: str) -> list[str]:
    """요약 카드용 줄. 대상이 없으면 빈 목록 — 빈말을 넣지 않는다."""
    r = rate(stats)
    if r is None:
        return []
    line = f"📮 {label} 발송 {delivered(stats)}/{stats['target']} ({r:.0%})"
    out = [line]
    for reason, n in sorted(stats.get("misses", {}).items(), key=lambda kv: -kv[1]):
        out.append(f"   · 미발송 {n}건 — {reason}")
    return out
