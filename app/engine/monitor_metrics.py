"""[감시 C3] 계측 카운터 — M-1 역행 · M-2 타순(자료3) 주입.

🔴 **로그는 사후에 세기 어렵다.** M 계측(C1)은 전부 `logger.info` 한 줄이라
   원인을 추적할 때는 훌륭하지만, 일일 요약에 "역행 r건 · 주입 p%"를 적으려면
   숫자가 필요하다. 이 모듈은 같은 지점에서 **세기만** 한다.

⚠️ 이 모듈은 아무것도 바꾸지 않는다 — 판정·게이트·발송 어디에도 값을
   돌려주지 않는다. 실패하면 조용히 0으로 남고, 그 실패가 판정을 막지 않는다.

⚠️ M-3(lineups 길이 이상)은 여기서 세지 않는다. `lineups` 테이블에 **행이
   남아 있어** DB 한 줄로 집계할 수 있다 — 이미 있는 사실을 카운터로 베끼면
   두 숫자가 어긋날 때 어느 쪽이 옳은지 알 수 없게 된다(사본 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

KEY = "monitor:{sport}:{date}"
TTL = 30 * 3600           # dispatch_stats 와 같은 슬레이트 수명


async def _bump(redis, sport: str, date: str, field: str, n: int = 1) -> None:
    if redis is None or not sport or not date:
        return
    try:
        key = KEY.format(sport=sport, date=date)
        await redis.hincrby(key, field, n)
        await redis.expire(key, TTL)
    except Exception as exc:
        logger.debug("[monitor] 계측 실패 %s.%s: %s", sport, field, exc)


async def note_materials(redis, sport: str, date: str, injected: bool) -> None:
    """[M-2] 판정 1건의 **타순 9명(자료3) 주입 여부.** 분모는 판정 횟수다.

    ⚠️ 수집률이 아니라 **주입률**이다. 2026-09-02 에 수집 로그는 18/18 인데
       카드 2장이 "자료8 부재"라고 적었다 — 두 숫자가 갈리는 지점을 본다.
    🔴 [2026-09-04] 자료8(타선 시즌)이 대원칙에 따라 폐지되면서 계측 대상을
       자료3 으로 옮겼다. 감시 대상이 사라진 게 아니라 자리를 옮긴 것이다.
    """
    await _bump(redis, sport, date, "mat_total")
    if injected:
        await _bump(redis, sport, date, "mat_injected")


async def note_lineup_regress(redis, sport: str, date: str) -> None:
    """[M-1] 확정 → 비확정 **역행** 1건.

    🔴 정상 전이(none→predicted→confirmed)는 세지 않는다. 세야 할 것은
       "확정이라고 해놓고 되돌아간" 경우뿐이다 — KBO 카드가 (잠정)을 다시
       달던 현상의 빈도를 이 숫자로 잡는다.
    """
    await _bump(redis, sport, date, "regress")


async def summary(redis, sport: str, date: str) -> dict:
    """{mat_total, mat_injected, regress}. 재료가 없으면 전부 0."""
    out = {"mat_total": 0, "mat_injected": 0, "regress": 0}
    if redis is None:
        return out
    try:
        raw = await redis.hgetall(KEY.format(sport=sport, date=date)) or {}
    except Exception as exc:
        logger.debug("[monitor] 집계 실패 %s: %s", sport, exc)
        return out
    for k, v in raw.items():
        k = k.decode() if isinstance(k, bytes) else k
        if k in out:
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
    return out
