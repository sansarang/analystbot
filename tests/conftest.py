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
