#!/usr/bin/env python
"""[운영 안정화 3c] API 차단 해제 — 사람이 명시적으로 부른다.

`api_guard` 의 차단은 **TTL이 없다.** 크레딧이 소진되면 걸리고, 키를 바꾸거나
여기서 풀기 전까지 시간으로는 풀리지 않는다. 그 설계 자체는 맞다 — 자동으로
풀면 잔액 없는 키로 계속 호출해 요금만 태운다.

문제는 **풀렸는지 아무도 몰랐다는 것**이다 (실측 2026-09-02: 배당이 차단
상태로 며칠간 멈춰 있었고 매 실행 로그는 `odds snapshot skipped — 차단 중`
뿐이었다). 워치독 `W-ODDS-BLOCKED` 가 이제 그 상태를 알리고, 해제는 여기서.

  python -m tools.unblock --list              # 지금 무엇이 막혀 있나
  python -m tools.unblock --provider odds     # 해제
  railway run python -m tools.unblock --list  # 운영에서

⚠️ **충전을 확인하고 풀어라.** 잔액이 없으면 곧바로 다시 차단된다.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("unblock")

PROVIDERS = ("odds", "anthropic", "perplexity", "grok", "football_data",
             "apifootball")


async def main() -> int:
    ap = argparse.ArgumentParser(description="API 차단 조회·해제")
    ap.add_argument("--list", action="store_true", help="차단 상태만 본다")
    ap.add_argument("--provider", default="", help="해제할 프로바이더")
    ap.add_argument("--all", action="store_true", help="전부 해제")
    a = ap.parse_args()

    from app.api_guard import block_info, clear_block

    blocked = []
    for name in PROVIDERS:
        try:
            info = await block_info(name)
        except Exception as exc:
            logger.warning("  %s 조회 실패: %s", name, exc)
            continue
        if not info:
            continue
        at = str(info.get("at") or "")
        days = ""
        try:
            days = f" · {(datetime.now(UTC) - datetime.fromisoformat(at)).days}일째"
        except Exception:
            pass
        blocked.append(name)
        logger.info("  🔴 %-14s %s%s  사유=%s  %s", name, at[:19], days,
                    info.get("reason"), (info.get("detail") or "")[:80])
    if not blocked:
        logger.info("차단된 프로바이더 없음")
        return 0
    if a.list or (not a.provider and not a.all):
        logger.info("해제하려면: --provider <이름> (또는 --all)")
        return 0
    targets = blocked if a.all else [a.provider]
    for name in targets:
        if name not in blocked:
            logger.warning("  %s 는 차단 상태가 아니다 — 건너뜀", name)
            continue
        await clear_block(name)
        logger.info("  ✅ %s 차단 해제", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
