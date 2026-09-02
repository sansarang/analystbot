#!/usr/bin/env python
"""[운영 안정화 0a] 하이픈 오염 타순 소급 교정.

`order.split("-")` 가 `Pete Crow-Armstrong`·`Ha-Seong Kim`·`Hao-Yu Lee` 를
두 조각으로 쪼개, 저장된 타순 배열이 10칸이 됐다. 슬롯이 통째로 밀려
라인업 의도(±3%p)와 T5 트리거가 **없는 '타순 이동'** 을 신호로 읽었다.

  실측 2026-09-02 (운영): lineup_events MLB 69건 · lineups MLB 84건

파서는 고쳤지만 **저장된 행은 그대로**다. 여기서 되돌린다:
  ① 명단 사전으로 인접 조각을 재결합 → 9명이 되면 **교정**
  ② 9명이 안 되면(빈 배열·부분 라인업) **contaminated=true 로 표시**해
     라인업 의도·T5 가 그 행을 쓰지 않게 한다

  python -m tools.repair_lineups --dry-run     # 무엇이 바뀔지만 본다
  railway run python -m tools.repair_lineups   # 운영에서 실행

⚠️ **되돌릴 수 없다.** 먼저 --dry-run 으로 건수를 확인하라.
⚠️ 교정은 재결합으로 9명이 **정확히** 될 때만 한다. 억지로 9명을 만들지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("repair")

TABLES = (("lineup_events", "observed_at"), ("lineups", "captured_at"))


def _as_list(val) -> list:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            got = json.loads(val)
            return got if isinstance(got, list) else []
        except ValueError:
            return []
    return []


def repair_order(items: list, known) -> list | None:
    """재결합해 9명이 되면 그 목록, 아니면 None.

    ⚠️ 9명이 정확히 될 때만 교정이다. 8명이나 10명이 남으면 **손대지 않는다** —
       모르는 것을 고친 척하면 그게 더 나쁘다.
    """
    from app.engine.lineup_diff import rejoin_hyphenated

    if len(items) == 9:
        return None                      # 이미 정상
    fixed = rejoin_hyphenated([str(x) for x in items], known)
    return fixed if len(fixed) == 9 else None


async def main() -> int:
    ap = argparse.ArgumentParser(description="오염 타순 소급 교정")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--season", type=int, default=0, help="명단 시즌 (기본: 올해)")
    a = ap.parse_args()

    from datetime import UTC, datetime

    from app.collectors.starter_season import _roster
    from app.db import close_pool, get_pool
    from app.engine.lineup_diff import NAME_REGISTRY

    season = a.season or datetime.now(UTC).year
    pool = await get_pool()
    try:
        try:
            await _roster(season, None)          # 사전을 채운다
        except Exception as exc:
            logger.error("명단 조회 실패 — 재결합 불가: %s", exc)
            return 2
        logger.info("실명 사전 %d개 (하이픈 이름)", len(NAME_REGISTRY))
        if not NAME_REGISTRY:
            logger.error("사전이 비었다 — 교정하면 추측이 된다. 중단")
            return 2

        total_fixed = total_marked = 0
        for table, ts in TABLES:
            try:
                rows = await pool.fetch(
                    f"""SELECT l.id, l.batting_order, g.sport, l.{ts} AS at
                          FROM {table} l JOIN games g ON g.id = l.game_id
                         WHERE l.batting_order IS NOT NULL
                           AND jsonb_typeof(l.batting_order) = 'array'
                           AND jsonb_array_length(l.batting_order) <> 9
                         ORDER BY l.id""")
            except Exception as exc:
                logger.error("%s 조회 실패: %s", table, exc)
                continue
            fixed = marked = 0
            for r in rows:
                items = _as_list(r["batting_order"])
                new = repair_order(items, NAME_REGISTRY)
                if new is not None:
                    fixed += 1
                    logger.info("  [교정] %s#%s %s %d명 → 9명  %s",
                                table, r["id"], r["sport"], len(items),
                                " / ".join(new[:3]) + " …")
                    if not a.dry_run:
                        await pool.execute(
                            f"UPDATE {table} SET batting_order = $1::jsonb,"
                            f"       contaminated = FALSE WHERE id = $2",
                            json.dumps(new, ensure_ascii=False), r["id"])
                else:
                    marked += 1
                    logger.info("  [표시] %s#%s %s %d명 — 재결합 불가, "
                                "판정에서 제외", table, r["id"], r["sport"],
                                len(items))
                    if not a.dry_run:
                        await pool.execute(
                            f"UPDATE {table} SET contaminated = TRUE WHERE id = $1",
                            r["id"])
            logger.info("%s: 대상 %d건 · 교정 %d · 표시 %d",
                        table, len(rows), fixed, marked)
            total_fixed += fixed
            total_marked += marked
        logger.info("%s합계 — 교정 %d건 · 표시 %d건",
                    "[dry-run] " if a.dry_run else "", total_fixed, total_marked)
        return 0
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
