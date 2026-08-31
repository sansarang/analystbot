"""[v1.1 0단계] 픽 레저 소급 백필 — Redis에 남은 슬레이트 분석을 레저로 옮긴다.

    python tools/backfill_ledger.py --since 2026-08-29
    python tools/backfill_ledger.py --since 2026-08-29 --dry-run

레저가 오늘부터 0건으로 시작하면 캘리브레이션이 한 주를 통째로 기다린다.
Redis에 남아 있는 판정은 이미 사실이므로 옮겨 담는다.

⚠️ 읽기만 한다 — Redis 키를 지우거나 고치지 않는다.
⚠️ `record_analysis`는 멱등이라 여러 번 돌려도 이력 행이 늘지 않는다.
⚠️ 슬레이트 키(`analysis:{sport}:{date}`)만 쓴다. 경기별 키
   (`analysis:{sport}:{game_id}:{date}`)에는 게이트 결과·라인업 상태가 없어
   레저의 절반이 빈다 — 반쪽 데이터로 캘리브레이션을 오염시키지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SLATE_KEY = re.compile(r"^analysis:(?P<sport>[a-z]+):(?P<date>\d{4}-\d{2}-\d{2})$")


async def main() -> int:
    ap = argparse.ArgumentParser(description="픽 레저 소급 백필")
    ap.add_argument("--since", default="2026-08-29", help="이 날짜 이후 (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 대상만 센다")
    args = ap.parse_args()

    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.db import close_pool, get_pool
    from app.engine.pick_ledger import grade_pending, record_analysis

    s = get_settings()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    pool = await get_pool()
    totals = {"slates": 0, "inserted": 0, "rejudged": 0, "unchanged": 0, "skipped": 0}
    try:
        keys = [k async for k in redis.scan_iter(match="analysis:*", count=500)]
        targets = []
        for k in sorted(keys):
            m = SLATE_KEY.match(k)
            if not m or m.group("date") < args.since:
                continue
            targets.append((k, m.group("sport"), m.group("date")))
        print(f"대상 슬레이트 {len(targets)}건 (since {args.since})")
        for key, sport, date in targets:
            raw = await redis.get(key)
            if not raw:
                totals["skipped"] += 1
                continue
            try:
                analysis = json.loads(raw)
            except json.JSONDecodeError:
                print(f"  ! {key} — JSON 파싱 실패, 건너뜀")
                totals["skipped"] += 1
                continue
            analysis.setdefault("sport", sport)
            analysis.setdefault("date", date)
            judged = sum(1 for g in analysis.get("games") or []
                         if (g.get("matchup") or {}).get("p_home") is not None)
            totals["slates"] += 1
            if args.dry_run:
                print(f"  {key}: 경기 {len(analysis.get('games') or [])}건 · 판정 {judged}건")
                continue
            st = await record_analysis(pool, analysis)
            for k2 in ("inserted", "rejudged", "unchanged"):
                totals[k2] += st[k2]
            print(f"  {key}: 판정 {judged}건 → 신규 {st['inserted']} · "
                  f"재판정 {st['rejudged']} · 변화없음 {st['unchanged']}")

        print(f"\n백필 합계: {totals}")
        if not args.dry_run:
            graded = await grade_pending(pool)
            print(f"즉시 채점: 채점 {graded['graded']}건 · void {graded['void']}건")
    finally:
        await redis.aclose()
        await close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
