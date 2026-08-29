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
    """첫 400에서 차단기를 내린다. 이후 호출은 abort_if_credit_gone."""
    global _stopped_at
    _stopped_at = at
    from app.llm.provider import _mark_exhausted

    _mark_exhausted("anthropic", f"{at}: {exc}")
    logger.error("[credit] 즉시 중단 at=%s: %s", at, exc)


def reset() -> None:
    """테스트용."""
    global _stopped_at
    _stopped_at = None
    from app.llm.provider import reset_exhausted

    reset_exhausted()
