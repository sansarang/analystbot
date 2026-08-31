"""[v1.1 0단계] 캘리브레이션 집계 CLI.

    python tools/calibration.py                 # 최근 7일
    python tools/calibration.py --days 30
    python tools/calibration.py --days 30 --sport kbo
    python tools/calibration.py --days 30 --json

집계 로직은 `app/engine/calibration.py`에 있다 — 스케줄러 주간 리포트 잡과
같은 코드를 쓴다. 도구와 운영이 다른 계산을 하면 표를 믿을 수 없다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> int:
    ap = argparse.ArgumentParser(description="픽 레저 캘리브레이션 집계")
    ap.add_argument("--days", type=int, default=7, help="집계 기간 (기본 7일)")
    ap.add_argument("--sport", default=None, help="mlb|kbo|npb|soccer (기본 전체)")
    ap.add_argument("--json", action="store_true", help="원자료를 JSON으로 출력")
    args = ap.parse_args()

    from app.db import close_pool, get_pool
    from app.engine.calibration import render_report, summarize

    pool = await get_pool()
    try:
        data = await summarize(pool, days=args.days, sport=args.sport)
    finally:
        await close_pool()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_report(data, days=args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
