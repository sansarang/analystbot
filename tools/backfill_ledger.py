"""[v1.1 0단계] 픽 레저 소급 백필 CLI — Redis에 남은 슬레이트 분석을 레저로 옮긴다.

    python tools/backfill_ledger.py --since 2026-08-29
    python tools/backfill_ledger.py --since 2026-08-29 --dry-run
    python tools/backfill_ledger.py --since 2026-08-29 --again   # 표식 무시하고 재실행

집계 로직은 `app/engine/pick_ledger.backfill_from_redis`에 있다 — 스케줄러
기동 백필과 **같은 코드**를 쓴다. 도구와 운영이 다르게 돌면 건수를 믿을 수 없다.

⚠️ 읽기만 한다 — Redis 키를 지우거나 고치지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> int:
    ap = argparse.ArgumentParser(description="픽 레저 소급 백필")
    ap.add_argument("--since", default="2026-08-29", help="이 날짜 이후 (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 대상만 센다")
    ap.add_argument("--again", action="store_true",
                    help="처리 표식을 무시하고 다시 훑는다 (record는 여전히 멱등)")
    args = ap.parse_args()

    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.db import close_pool, get_pool
    from app.engine.pick_ledger import backfill_from_redis, grade_pending

    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    pool = await get_pool()
    try:
        stats = await backfill_from_redis(
            pool, redis, args.since,
            dry_run=args.dry_run, skip_seen=not args.again)
        print(f"백필({args.since} 이후): {stats}")
        if not args.dry_run:
            graded = await grade_pending(pool)
            print(f"즉시 채점: 채점 {graded['graded']}건 · void {graded['void']}건")
    finally:
        await redis.aclose()
        await close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
