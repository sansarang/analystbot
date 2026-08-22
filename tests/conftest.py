"""테스트 공용 픽스처: 격리된 analystbot_test DB 생성 후 스키마 적용."""

import asyncpg
import pytest

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
