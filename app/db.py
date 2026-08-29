"""asyncpg 풀 + 스키마 적용. `python -m app.db init` 으로 스키마 적용."""

import asyncio
import logging
import pathlib
import sys

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "db" / "schema.sql"

_pool: asyncpg.Pool | None = None
_schema_applied = False


async def get_pool(dsn: str | None = None) -> asyncpg.Pool:
    global _pool, _schema_applied
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn or get_settings().database_url)
    if not _schema_applied:
        # 봇·파이프라인·비교 스크립트도 스케줄러와 같이 스키마를 맞춘다.
        # 로컬에서 스케줄러가 안 떠 있으면 pitcher_appearances가 없어
        # 선발 최근 등판이 전부 빈다 (실측 2026-08-29).
        try:
            await apply_schema(_pool)
            _schema_applied = True
        except Exception as exc:
            logger.error("[db] 스키마 적용 실패 — pitcher_appearances 등이 없을 수 있다: %s",
                         exc)
    return _pool


async def close_pool() -> None:
    global _pool, _schema_applied
    if _pool is not None:
        await _pool.close()
        _pool = None
        _schema_applied = False


async def apply_schema(conn: asyncpg.Connection | asyncpg.Pool) -> None:
    await conn.execute(SCHEMA_PATH.read_text())


async def _init() -> None:
    pool = await get_pool()
    await apply_schema(pool)
    await close_pool()
    # ⚠️ 접속 문자열을 그대로 찍지 않는다 — **비밀번호가 배포 로그에 남는다.**
    #   실사고(2026-08-27): Railway pre-deploy 로그에 DB 비밀번호가 평문으로
    #   찍혀 있었다. 로그는 보관되고 공유되므로 한 번 새면 되돌릴 수 없다.
    from urllib.parse import urlparse

    u = urlparse(get_settings().database_url)
    print(f"schema applied: {u.hostname}:{u.port or 5432}/{(u.path or '/').lstrip('/')}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "init":
        sys.exit(f"unknown command: {sys.argv[1]} (usage: python -m app.db init)")
    asyncio.run(_init())
