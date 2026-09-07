"""[1회성] 이미 끝난 경기의 판정 원장에 시장값을 소급해 새긴다.

🔴 왜: `pick_ledger` 는 `market_prob`·`divergence_pp` 컬럼을 처음부터 갖고
   있었지만 INSERT 가 쓰지 않아 **621행 전부 NULL** 이었다. 시장 신호가
   캘리브레이션에 한 번도 닿은 적이 없다.

기준은 **CLOSE**(시작 직전 마지막 스냅샷)다. SEND(카드 시점)는 나이 상한이
있어 사후에 재현되지 않는다 — 실측 2026-09-07: SEND 로는 138경기 전부
`stale`, CLOSE 로는 104경기(75.4%) 가 붙는다.

⚠️ **판정 칸은 건드리지 않는다.** 이력 행도 늘리지 않는다.
⚠️ 이미 값이 있는 행은 덮어쓰지 않는다 (`COALESCE`).
⚠️ 배당 격리는 그대로다 — 이건 판정이 끝난 뒤의 기록이고, 판정 프롬프트로
   가지 않는다.
⚠️ CLOSE 는 **판정 시점의 시장이 아니라 마감 근사**다. 실시간 게이트가 볼
   값(SEND)보다 정답에 가깝다 — 이 백필 행으로 "게이트가 이만큼 좋아진다"고
   말하면 사후확신이다. 캘리브레이션 재료로만 쓴다.

실행 (운영):
  railway ssh ... "PYTHONPATH=/app python /app/tools/backfill_market.py --apply"
`--apply` 없이 돌리면 **세기만 하고 쓰지 않는다.**
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections import Counter

logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다")
    ap.add_argument("--sport", default=None)
    args = ap.parse_args()

    import asyncpg

    from app.engine.market_baseline import CLOSE, p_market

    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"],
                                     min_size=1, max_size=4)
    try:
        rows = await pool.fetch(
            """SELECT pl.id, pl.game_id, pl.sport, pl.p_home,
                      pl.market_prob, g.home, g.away, g.starts_at
                 FROM pick_ledger pl JOIN games g ON g.id = pl.game_id
                WHERE ($1::text IS NULL OR pl.sport = $1)
                ORDER BY pl.id""", args.sport)
        print(f"대상 {len(rows)}행 ({'적용' if args.apply else '모의'})")

        stat: Counter = Counter()
        for r in rows:
            if r["market_prob"] is not None:
                stat["이미있음"] += 1
                continue
            snap = await p_market(pool, {"id": r["game_id"], "sport": r["sport"],
                                         "home": r["home"], "away": r["away"],
                                         "starts_at": r["starts_at"]},
                                  purpose=CLOSE)
            mkt = snap.get("p")
            if mkt is None:
                stat[snap.get("reason") or "?"] += 1
                continue
            our = r["p_home"]
            div = (round((float(our) - float(mkt)) * 100, 2)
                   if our is not None else None)
            stat["붙음"] += 1
            if args.apply:
                await pool.execute(
                    """UPDATE pick_ledger
                          SET market_prob   = COALESCE(market_prob, $2),
                              divergence_pp = COALESCE(divergence_pp, $3)
                        WHERE id = $1""", r["id"], float(mkt), div)

        for k, v in stat.most_common():
            print(f"   {k:20s} {v:5d}")
        after = await pool.fetchrow(
            "SELECT count(*) n, count(market_prob) m FROM pick_ledger")
        print(f"\n결과: market_prob {after['m']}/{after['n']}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
