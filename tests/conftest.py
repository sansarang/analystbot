"""테스트 공용 픽스처: 격리된 analystbot_test DB 생성 후 스키마 적용."""

import os

# 테스트는 외부 API를 절대 치지 않는다 — config를 읽기 전에 강제 목 모드 고정.
os.environ.setdefault("FORCE_MOCK", "true")

import asyncpg
import pytest
import redis.asyncio as aioredis

from app.db import apply_schema

ADMIN_DSN = "postgresql://analyst:analyst@localhost:5432/postgres"
TEST_DB = "analystbot_test"
TEST_DSN = f"postgresql://analyst:analyst@localhost:5432/{TEST_DB}"


@pytest.fixture
async def db_pool():
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    await admin.execute(f"CREATE DATABASE {TEST_DB}")
    await admin.close()

    pool = await asyncpg.create_pool(TEST_DSN)
    async with pool.acquire() as conn:
        await apply_schema(conn)
    yield pool
    await pool.close()


@pytest.fixture
async def redis_client():
    r = aioredis.from_url("redis://localhost:6379/15", decode_responses=True)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


# ---------------------------------------------------------------- 외부 발신 차단

@pytest.fixture(autouse=True)
def _no_outbound_telegram(monkeypatch, request):
    """테스트는 절대 실제 텔레그램으로 발송하지 않는다.

    실사고(2026-08-25): [7] 단계 실패 알림을 붙인 뒤 `pytest`를 돌릴 때마다
    build_analysis가 테스트 픽스처로 실패 알림을 만들어 **관리자 채팅으로
    실제 발송**했다. "λ 0/5"·"리서치 13/15" 같은 실슬레이트에 없는 숫자가
    1~2분 간격으로 쏟아진 원인이 이것이다. 억제 로직 문제가 아니라
    테스트가 외부로 나간 문제였다.

    가드는 send_telegram을 **차단 스텁**으로 갈아끼운다. 스텁은 예외를 던지지 않고
    False를 반환하며 발송 시도를 기록한다 — 예외로 만들면 "토큰이 없으면 조용히
    False" 같은 정상 경로 테스트가 깨진다. 자체적으로 send_telegram을 대체하는
    테스트(test_alerts·test_quota)는 이 스텁을 덮어쓰므로 영향을 받지 않는다.

    httpx.AsyncClient를 갈아끼우는 방식은 쓰지 않는다 — 모듈 전역이라
    스로틀·수집기 테스트까지 함께 깨진다.
    """
    blocked: list[str] = []

    async def _blocked(text: str) -> bool:
        blocked.append(text)
        return False

    import app.alerts as alerts_mod
    import app.notify as notify_mod

    # 발송 지점은 **하나**다 — alerts는 notify 모듈 속성으로 부른다.
    #   (종전에는 alerts가 함수를 자기 이름공간에 묶어 두 곳을 다 막아야 했고,
    #    한쪽만 막으면 조용히 새어 나갔다.)
    monkeypatch.setattr(notify_mod, "send_telegram", _blocked)
    assert not hasattr(alerts_mod, "send_telegram"), \
        "alerts가 send_telegram을 다시 자기 이름공간에 묶었다 — 발송 지점이 갈라진다"

    # 억제 상태도 격리한다. 안 하면 테스트가 **운영 Redis의 알림 예산**
    # (alert:budget, 10분 12건)을 갉아먹어 실제 장애 알림이 막힌다.
    # 실측(2026-08-25): 테스트를 돌린 뒤 KBO 파싱 실패 알림이 예산 초과로 억제됐다.
    class _MemRedis:
        def __init__(self):
            self.store: dict = {}

        async def set(self, k, v, nx=False, ex=None):
            if nx and k in self.store:
                return None
            self.store[k] = v
            return True

        async def get(self, k):
            return self.store.get(k)

        async def incr(self, k):
            self.store[k] = int(self.store.get(k, 0)) + 1
            return self.store[k]

        async def expire(self, k, sec):
            return True

        async def delete(self, *ks):
            for k in ks:
                self.store.pop(k, None)

        async def keys(self, pattern):
            return list(self.store)

        async def aclose(self):
            pass

    _mem = _MemRedis()

    async def _fake_redis():
        return _mem

    monkeypatch.setattr(alerts_mod, "_redis", _fake_redis)
    yield
    if blocked:
        # 새 코드가 알림 경로를 늘렸다는 신호 — 조용히 넘기지 않는다
        print(f"\n[conftest] 테스트 중 텔레그램 발송 {len(blocked)}건 차단됨 "
              f"(첫 건: {blocked[0][:80]!r})")


@pytest.fixture(autouse=True)
def _no_outbound_collectors(monkeypatch):
    """테스트는 외부 수집 API(Open-Meteo·statsapi 라인업)를 호출하지 않는다.

    실사고(2026-08-25): 파이프라인에 날씨·결장 수집을 붙이자 `pytest`가
    16초 → 107초가 됐다. build_analysis가 테스트에서도 실제 HTTP를 때린 것이다.
    테스트는 hermetic해야 한다 — 필요하면 각 테스트가 직접 되돌려 쓴다.
    """
    async def _empty(*a, **kw):
        return {}

    import app.collectors.absences as absences_mod
    import app.collectors.weather as weather_mod

    monkeypatch.setattr(weather_mod, "fetch_for_games", _empty)
    monkeypatch.setattr(absences_mod, "fetch_for_games", _empty)
