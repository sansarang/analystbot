"""[LED-1 2026-09-10] 한 경기에 둘 이상인 최종 판정을 하나로 정리한다.

    python tools/dedupe_final_picks.py --dry-run     # 대상만 본다 (기본)
    python tools/dedupe_final_picks.py --apply       # 실제로 낮춘다

🔴 **행을 지우지 않는다.** 잉여 행을 `is_final = FALSE` 로 낮춰 이력으로 남기고
   판정 기록을 지우지 않는 것이 이 표의 존재 이유다
   (`app/collectors/game_match.py:349` 가 같은 태도를 문서화했다).
   ⚠️ 표식 컬럼은 쓰지 않는다 — `merged_from` 은 bigint 다. 대신 **되돌리는
      UPDATE 문을 그대로 출력**하니 그것을 보관하라.

남길 행을 고르는 규칙 — **경기의 올바른 슬레이트 날짜와 일치하는 행**:
   MLB      = 미국 동부 기준 `starts_at` 의 날짜
   KBO·NPB  = KST 기준 `starts_at` 의 날짜
날짜가 하나도 안 맞으면 **가장 이른 판정**을 남긴다 (그 경기의 원래 슬레이트에
기록된 것이 그쪽일 가능성이 높다). 어느 경우든 무엇을 골랐는지 출력한다.

⚠️ 이 도구가 먼저 돌아야 `idx_pick_ledger_final (game_id) WHERE is_final`
   유니크 인덱스가 만들어진다. 중복이 남아 있으면 인덱스 생성이 실패한다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

KST = timezone(timedelta(hours=9))
ET = timezone(timedelta(hours=-4))      # 시즌 중 EDT. 날짜 경계 판정용이다.


def slate_date(sport: str, starts_at):
    """그 경기가 속한 슬레이트 날짜. CLAUDE.md 규칙 5 와 같은 기준이다."""
    if starts_at is None:
        return None
    tz = ET if (sport or "").lower() == "mlb" else KST
    # 🔴 **문자열로 돌려준다.** `pick_ledger.date` 는 TEXT 라 date 객체와
    #    비교하면 **항상 False** 가 되고, 조용히 "가장 이른 판정" 으로
    #    떨어진다. 실측(첫 dry-run): 10건 전부 그렇게 빠졌고 그중 2건
    #    (game=3238·3722)은 그 바람에 **틀린 행을 남길** 뻔했다.
    return starts_at.astimezone(tz).date().isoformat()


async def main() -> int:
    ap = argparse.ArgumentParser(description="중복 최종 판정 정리 (LED-1)")
    ap.add_argument("--apply", action="store_true", help="실제로 낮춘다")
    args = ap.parse_args()

    from app.db import close_pool, get_pool

    pool = await get_pool()
    demote: list[tuple[int, int, str]] = []
    try:
        async with pool.acquire() as c:
            dups = await c.fetch("""
                SELECT game_id FROM pick_ledger WHERE is_final
                GROUP BY game_id HAVING count(*) > 1 ORDER BY game_id""")
            print(f"중복 경기 {len(dups)}건\n")
            for d in dups:
                rows = await c.fetch("""
                    SELECT l.id, l.date, l.sport, l.p_home, l.favored, l.hit,
                           g.starts_at, g.away, g.home
                    FROM pick_ledger l LEFT JOIN games g ON g.id = l.game_id
                    WHERE l.is_final AND l.game_id = $1
                    ORDER BY l.judged_at""", d["game_id"])
                want = slate_date(rows[0]["sport"], rows[0]["starts_at"])
                keep = next((r for r in rows
                             if want and str(r["date"]) == want), rows[0])
                why = ("슬레이트 날짜 일치" if want and str(keep["date"]) == want
                       else "🔴 날짜 불일치 — 가장 이른 판정")
                print(f"game={d['game_id']} {str(rows[0]['away'])[:14]}@{str(rows[0]['home'])[:14]}"
                      f"  올바른 슬레이트={want}")
                for r in rows:
                    tag = f"KEEP ({why})" if r["id"] == keep["id"] else "→ 이력으로"
                    print(f"   id={r['id']:4d} date={r['date']} p={r['p_home']} "
                          f"{str(r['favored']):5s} hit={r['hit']}   {tag}")
                    if r["id"] != keep["id"]:
                        demote.append((r["id"], d["game_id"], str(r["date"])))
                print()

            print(f"낮출 행 {len(demote)}개")
            if not args.apply:
                print("\n(--dry-run 기본. 실제로 적용하려면 --apply)")
                return 0
            ids = [rid for rid, _g, _d in demote]
            # 🔴 표식 컬럼을 쓰지 않는다. `merged_from` 은 **bigint**(다른 경기
            #    id 참조)라 문자열을 넣으면 트랜잭션이 통째로 롤백된다 —
            #    실측 첫 시도가 그렇게 조용히 실패했다
            #    (invalid input syntax for type bigint: "LED-1").
            #    되돌리기는 아래 id 목록으로 한다.
            print("되돌리려면:")
            print(f"  UPDATE pick_ledger SET is_final = TRUE "
                  f"WHERE id IN ({', '.join(map(str, ids))});")
            async with c.transaction():
                for rid in ids:
                    await c.execute(
                        "UPDATE pick_ledger SET is_final = FALSE WHERE id = $1", rid)
            left = await c.fetchval("""SELECT count(*) FROM (
                SELECT game_id FROM pick_ledger WHERE is_final
                GROUP BY game_id HAVING count(*) > 1) x""")
            n, u = await c.fetchrow("""SELECT count(*), count(DISTINCT game_id)
                                       FROM pick_ledger WHERE is_final""")
            print(f"✅ 적용 완료 — 남은 중복 {left}건 · is_final {n}행 / 고유 {u}경기")
            if left:
                print("🔴 중복이 남았다 — 유니크 인덱스 생성이 실패한다")
                return 1
    finally:
        await close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
