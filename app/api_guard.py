"""프로바이더 호출 가드 — **disabled**(의도적 미사용)와 **blocked**(크레딧 소진).

mock(키 없음)도 오류도 아니다. disabled는 설정이고, blocked는 402 회로 차단기다.

차단 해제 조건은 둘뿐이다.
  (a) API 키가 바뀜 (지문 불일치 → 자동 해제)
  (b) `clear_block(name)` — 사람이 명시적으로 재시도
시간이 지났다고 풀지 않는다. TTL 없음.

429(레이트리밋)는 여기 넣지 않는다. `classify_api_error()`가 credit일 때만 trip.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.collectors.base import ProviderBlockedError, ProviderDisabledError
from app.config import get_settings

KST = ZoneInfo("Asia/Seoul")

logger = logging.getLogger(__name__)

BLOCK_KEY = "api:blocked:{}"

# 프로바이더 이름 → Settings 키 필드. 지문 비교로 "키가 바뀌었는가"를 본다.
_KEY_ATTR = {
    "grok": "xai_api_key",
    "perplexity": "pplx_api_key",
    "odds": "odds_api_key",
    "anthropic": "anthropic_api_key",
    "football": "apifootball_key",
    "football_data": "football_data_key",
}

# 테스트는 운영 Redis에 쓰지 않는다. conftest가 False로 둔다.
_network_redis = True
_redis_override = None
_memory: dict[str, str] = {}


def reset() -> None:
    """테스트용 — 메모리 차단 상태만 지운다. Redis 오버라이드는 호출부가 비운다."""
    _memory.clear()


def set_network_redis(on: bool) -> None:
    global _network_redis
    _network_redis = on


def set_redis(client) -> None:
    """테스트가 redis_client 픽스처를 넘길 때."""
    global _redis_override
    _redis_override = client


def is_disabled(name: str) -> bool:
    return get_settings().is_disabled(canonical_provider(name))


def canonical_provider(service: str) -> str:
    """알림·차단 키를 프로바이더 단위로 맞춘다. `anthropic(judge)` → `anthropic`."""
    lowered = (service or "").strip().lower()
    if not lowered:
        return "unknown"
    if lowered in _KEY_ATTR:
        return lowered
    for name in sorted(_KEY_ATTR, key=len, reverse=True):
        if name in lowered:
            return name
    return lowered


def key_fp(name: str) -> str:
    attr = _KEY_ATTR.get(name, "")
    raw = (getattr(get_settings(), attr, None) or "") if attr else ""
    return hashlib.sha256(str(raw).encode()).hexdigest()[:16]


def _parse(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def _get(key: str) -> str | None:
    if _redis_override is not None:
        return await _redis_override.get(key)
    if key in _memory:
        return _memory[key]
    if not _network_redis:
        return None
    r = None
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        return await r.get(key)
    except Exception as exc:
        logger.debug("[api_guard] redis get skip: %s", exc)
        return None
    finally:
        if r is not None:
            await r.aclose()


async def _set(key: str, val: str) -> None:
    _memory[key] = val
    if _redis_override is not None:
        await _redis_override.set(key, val)
        return
    if not _network_redis:
        return
    r = None
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await r.set(key, val)          # TTL 없음 — 시간으로 해제하지 않는다
    except Exception as exc:
        logger.debug("[api_guard] redis set skip: %s", exc)
    finally:
        if r is not None:
            await r.aclose()


async def _delete(key: str) -> None:
    _memory.pop(key, None)
    if _redis_override is not None:
        await _redis_override.delete(key)
        return
    if not _network_redis:
        return
    r = None
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await r.delete(key)
    except Exception as exc:
        logger.debug("[api_guard] redis del skip: %s", exc)
    finally:
        if r is not None:
            await r.aclose()


async def block_info(name: str) -> dict | None:
    name = canonical_provider(name)
    data = _parse(await _get(BLOCK_KEY.format(name)))
    if not data:
        return None
    if data.get("key_fp") != key_fp(name):
        logger.info("[api_guard] %s 키가 바뀜 — 차단 해제", name)
        await clear_block(name)
        return None
    return data


async def is_blocked(name: str) -> bool:
    return await block_info(name) is not None


async def trip_credit(name: str, detail: str) -> bool:
    """크레딧 소진으로 회로를 연다. 429는 호출하지 마라.

    새로 열렸을 때만 True. 그때 하루 1회 크레딧 알림을 보낸다.
    이미 열려 있으면 False — 알림도 없다 (호출부가 notify_quota를 또 불러도 막힌다).
    """
    name = canonical_provider(name)
    if is_disabled(name):
        return False
    if await is_blocked(name):
        return False
    payload = json.dumps({
        "reason": "credit",
        "at": datetime.now(UTC).isoformat(),
        "key_fp": key_fp(name),
        "detail": (detail or "")[:300],
    }, ensure_ascii=False)
    await _set(BLOCK_KEY.format(name), payload)
    logger.warning("[api_guard] %s 차단 (크레딧 소진) — 키 변경 또는 수동 해제 전 호출 없음",
                   name)
    try:
        from app.notify import notify_quota

        await notify_quota(name, detail, allow_when_blocked=True)
    except Exception as exc:
        logger.warning("[api_guard] %s 차단 알림 실패: %s", name, exc)
    return True


async def clear_block(name: str) -> None:
    """사람이 명시적으로 재시도할 때. 시간 경과로는 부르지 않는다."""
    name = canonical_provider(name)
    await _delete(BLOCK_KEY.format(name))
    logger.info("[api_guard] %s 차단 해제 (수동)", name)


async def raise_if_unusable(name: str) -> None:
    """HTTP 나가기 전. disabled → 알림 없음. blocked → 알림 없음(이미 소진 알림을 냈다)."""
    name = canonical_provider(name)
    if is_disabled(name):
        raise ProviderDisabledError(name, "disabled")
    info = await block_info(name)
    if info is not None:
        raise ProviderBlockedError(
            name, info.get("detail") or "credit exhausted")


def _kst_short(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(KST).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return "?"


async def prefetch_status_lines() -> list[str]:
    """프리페치 리포트 하단 — 실패 단계가 아니라 상태 한 줄. 🔴로 세지 않는다."""
    unused = sorted(get_settings().disabled_set())
    out: list[str] = []
    if unused:
        out.append("미사용: " + ", ".join(unused))
    # 🔴 **쓰지 않는 키의 차단은 상태가 아니다.** 무과금 전환(2026-09-02) 후
    #    `odds`(The Odds API)는 `ODDS_PROVIDER=free` 로 꺼져 있다. 그 차단을
    #    리포트에 계속 적으면 사용자가 "배당이 고장났다"로 읽는다 — 실제로는
    #    무료 소스로 바뀌었을 뿐이다.
    off = set(unused)
    try:
        from app.config import get_settings as _gs

        if (_gs().odds_provider or "free").lower() != "theodds":
            off.add("odds")
    except Exception:
        pass
    bits: list[str] = []
    for name in _KEY_ATTR:
        if name in off:
            continue
        info = await block_info(name)
        if not info:
            continue
        bits.append(f"{name}(크레딧 소진, {_kst_short(info.get('at'))})")
    if bits:
        out.append("차단 중: " + ", ".join(bits))
    return out
