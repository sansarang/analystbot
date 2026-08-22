"""asyncpg 풀 + 스키마 적용. `python -m app.db init` 으로 스키마 적용."""

import asyncio
import pathlib
import sys

import asyncpg

from app.config import get_settings

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_pool: asyncpg.Pool | None = None


async def get_pool(dsn: str | None = None) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn or get_settings().database_url)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def apply_schema(conn: asyncpg.Connection | asyncpg.Pool) -> None:
    await conn.execute(SCHEMA_PATH.read_text())


async def _init() -> None:
    pool = await get_pool()
    await apply_schema(pool)
    await close_pool()
    print("schema applied:", get_settings().database_url)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "init":
        sys.exit(f"unknown command: {sys.argv[1]} (usage: python -m app.db init)")
    asyncio.run(_init())
