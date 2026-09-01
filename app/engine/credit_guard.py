"""Anthropic 잔액 400이면 같은 프로세스에서 추가 호출을 막는다.

실측 2026-08-29: 구 2단 해석이 크레딧을 소진한 뒤 폼·매치업이 팀마다
2회씩 400을 반복했다. 재시도는 일시 장애용이지 잔액 0을 위한 것이 아니다.
"""
from __future__ import annotations

import logging

from app.collectors.base import ApiQuotaError

logger = logging.getLogger(__name__)

_stopped_at: str | None = None


def stopped_at() -> str | None:
    return _stopped_at


def abort_if_credit_gone(where: str = "") -> None:
    """이미 소진이면 HTTP 없이 즉시 중단."""
    from app.llm.provider import _is_exhausted

    why = _is_exhausted("anthropic")
    if not why:
        return
    loc = where or _stopped_at or "anthropic"
    raise ApiQuotaError("anthropic", f"잔액 소진으로 중단 ({loc}): {why}")


def trip_credit(at: str, exc: BaseException) -> None:
    """첫 400에서 차단기를 내린다. 이후 호출은 abort_if_credit_gone.

    🔴 **사용자에게도 알린다.** 종전에는 로그만 남겼다 — `_mark_exhausted` 는
       프로세스 안의 플래그일 뿐이다. 그래서 Anthropic 잔액이 끊겨도 텔레그램
       알림이 가지 않았다. 알림은 `pipeline` 의 몇몇 호출부에만 붙어 있었고,
       그것도 예외가 거기까지 올라가야 했다 — `matchup`·`deepsearch`·
       `soccer_trial` 은 잡아서 삼키므로 그 경로로 소진되면 영원히 침묵했다
       (실측 2026-09-01: 감지 5곳 중 notify 호출 0곳).

    🔴 **`api_guard.trip_credit` 을 부르지 않는다.** 그쪽은 Redis 에 영구
       차단을 걸고 `clear_block()` 을 사람이 부르기 전까지 풀리지 않는다.
       종전 동작은 프로세스 안의 `_EXHAUSTED` 플래그라 **재시작하면 풀렸다** —
       실제로 오늘 사용자가 충전한 뒤 그렇게 복구됐다(2026-09-01).
       영구 차단으로 바꾸면 충전해도 수동 해제 전까지 막힌다. 알림만 붙인다.

    ⚠️ 동기 함수라 태스크로 띄운다. 알림 실패가 차단을 막아서는 안 된다.
    ⚠️ `notify_quota` 가 프로바이더당 KST 하루 1회 억제를 갖고 있어
       5분 폴링에서 알림이 쏟아지지 않는다.
    """
    global _stopped_at
    _stopped_at = at
    from app.llm.provider import _mark_exhausted

    _mark_exhausted("anthropic", f"{at}: {exc}")
    logger.error("[credit] 즉시 중단 at=%s: %s", at, exc)
    _notify_credit(at, exc)


def _notify_credit(at: str, exc: BaseException) -> None:
    """크레딧 소진을 텔레그램으로. 실패해도 조용히 넘어간다."""
    import asyncio

    async def _run() -> None:
        try:
            from app.notify import notify_quota

            await notify_quota("anthropic", f"{at}: {exc}",
                               allow_when_blocked=True)
        except Exception as e:      # 알림 실패가 차단을 막지 않는다
            logger.warning("[credit] 소진 알림 실패: %s", e)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:            # 이벤트 루프 밖(동기 테스트 등)
        logger.debug("[credit] 루프 없음 — 알림 생략")


def reset() -> None:
    """테스트용."""
    global _stopped_at
    _stopped_at = None
    from app.llm.provider import reset_exhausted

    reset_exhausted()
