#!/usr/bin/env python
"""[운영 안정화 3a] 수동 재발송 — 1커맨드.

크레딧 소진·캐시 유실로 카드가 안 나간 슬레이트를 사람이 되돌린다.

  python -m tools.resend --sport mlb                 # 오늘 슬레이트, 안 나간 것만
  python -m tools.resend --sport kbo --date 2026-09-02
  python -m tools.resend --sport npb --force         # 이미 보낸 것도 다시
  python -m tools.resend --sport mlb --rebuild       # 판정 캐시부터 다시 만든다
  python -m tools.resend --sport mlb --dry-run       # 무엇이 나갈지만 본다

⚠️ **서버에서 돌린다.** 로컬 Redis·DB는 운영과 다른 저장소라, 로컬에서 돌리면
   카드는 나가도 서버 상태는 그대로다 (실측 2026-09-01에 겪었다).
   `railway run python -m tools.resend --sport mlb` 로 쓴다.
⚠️ `--force` 는 발송 서명을 지운다. 같은 카드를 두 번 받게 되므로,
   "안 왔다"가 확실할 때만 쓴다.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date as date_cls

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("resend")


async def main() -> int:
    ap = argparse.ArgumentParser(description="카드 수동 재발송")
    ap.add_argument("--sport", required=True, choices=("mlb", "kbo", "npb"))
    ap.add_argument("--date", default="", help="슬레이트 날짜 (기본: 종목별 오늘)")
    ap.add_argument("--game", type=int, default=0, help="이 경기만")
    ap.add_argument("--force", action="store_true", help="이미 보낸 것도 다시")
    ap.add_argument("--rebuild", action="store_true", help="판정 캐시부터 재생성")
    ap.add_argument("--dry-run", action="store_true", help="발송 없이 대상만 출력")
    a = ap.parse_args()

    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.db import close_pool, get_pool
    from app.engine.pregame_push import (
        SPORTS, cache_date, card_sig_key, in_send_window, send_game_prediction,
        still_upcoming,
    )
    from app.pipeline import ensure_analysis_cache

    if a.sport not in SPORTS:
        logger.error("지원하지 않는 종목: %s", a.sport)
        return 2
    s = get_settings()
    pool = await get_pool()
    redis = aioredis.from_url(s.redis_url, decode_responses=True)
    slate = a.date or cache_date(a.sport)
    tz = "America/New_York" if a.sport == "mlb" else "Asia/Seoul"
    try:
        rows = await pool.fetch(
            f"""SELECT id, sport, home, away, starts_at, league FROM games
                 WHERE sport = $1 AND status = 'scheduled'
                   AND (starts_at AT TIME ZONE '{tz}')::date = $2
                 ORDER BY starts_at, id""",
            a.sport, date_cls.fromisoformat(slate))
        if a.game:
            rows = [r for r in rows if r["id"] == a.game]
        logger.info("[resend] %s %s — 경기 %d건", a.sport.upper(), slate, len(rows))
        if not rows:
            logger.warning("[resend] 대상 없음 — 날짜·종목을 확인하라")
            return 1

        if a.rebuild:
            # 구제 잠금을 풀고 캐시를 다시 만든다 — 사람이 명시적으로 요청한 것이다.
            from app.pipeline import _RESCUE_FAIL_KEY, _RESCUE_KEY

            for k in (_RESCUE_KEY, _RESCUE_FAIL_KEY):
                await redis.delete(k.format(sport=a.sport, date=slate))
            await redis.delete(f"{_RESCUE_FAIL_KEY.format(sport=a.sport, date=slate)}:lock")
            logger.info("[resend] 판정 캐시 재생성 중 (수 분 걸린다)…")
            ok = await ensure_analysis_cache(pool, redis, a.sport, slate)
            logger.info("[resend] 캐시 재생성 %s", "성공" if ok else "실패")
            if not ok:
                logger.error("[resend] 판정이 없으므로 발송하지 않는다")
                return 1

        from datetime import UTC, datetime

        now = datetime.now(UTC)
        targets = []
        for r in rows:
            why = ""
            if not still_upcoming(r["starts_at"], now):
                why = "이미 시작"
            elif not in_send_window(a.sport, r["starts_at"], now):
                why = "발송 창 전"
            elif await redis.get(card_sig_key(r["id"])) and not a.force:
                why = "이미 발송 (--force 로 재발송)"
            mark = "→ 발송" if not why else f"× {why}"
            logger.info("  %s %s @ %s  %s", r["id"], r["away"], r["home"], mark)
            if not why:
                targets.append(r)
        if a.dry_run:
            logger.info("[resend] --dry-run — 발송 %d건 예정, 실제 발송 없음",
                        len(targets))
            return 0
        if a.force:
            for r in targets:
                await redis.delete(card_sig_key(r["id"]))
        sent = 0
        for r in targets:
            res = await send_game_prediction(redis, r, slate, now=now)
            logger.info("  game=%s → %s", r["id"], res)
            sent += res in ("sent", "revised")
        logger.info("[resend] 완료 — 발송 %d/%d", sent, len(targets))
        return 0 if sent == len(targets) else 1
    finally:
        await redis.aclose()
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
