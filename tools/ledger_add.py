"""[LDG-1] 원장에 **사람이 건 픽**을 한 줄 넣는다.

🔴 봇이 아니라 사람(페이블 채팅 판정 · 승률 모드)이 건 픽을 같은 `game_id` 로
   나란히 둔다. 그래야 "봇 vs 페이블"을 숫자로 비교할 수 있다(지시문 7-2).
🔴 **모르는 값을 받지 않는다.** 판정자·마켓이 목록 밖이면 거부하고 1로 나간다.
   조용히 NULL 로 넣으면 유니크가 풀리고(→ docs/FORKS.md F-19) 집계에서 사라진다.
⚠️ 채점·CLV 는 여기서 채우지 않는다 — 결과 적재 잡의 몫이다(지시문 7-3).

사용:
  tools/ledger_add.py --game 10098 --judge_by fable_chat \
      --market team_total_away --line 3.5 --side under --odds 1.90
"""
from __future__ import annotations

import argparse
import asyncio
import sys

#: 판정자. 🔴 이 목록이 원본이다 — 스키마 주석에 손으로 옮겨 적지 않는다.
JUDGES = ("bot_v14", "fable_chat", "user_mode_b")

#: 마켓 **계열**. 팀토탈만 `_home`·`_away` 접미사를 받는다.
MARKETS = ("ml", "ah", "total", "team_total", "f5")

#: 접미사를 허용하는 계열.
SIDED = ("team_total",)


def valid_market(m: str) -> bool:
    """`ml` 같은 계열 그대로, 또는 `team_total_away` 처럼 접미사가 붙은 것."""
    m = str(m or "")
    if m in MARKETS:
        return True
    for fam in SIDED:
        if m in (f"{fam}_home", f"{fam}_away"):
            return True
    return False


def build_row(*, game_id: int, sport: str, league: str | None, date: str,
              judge_by: str, market: str, line: float | None, side: str,
              odds: float | None, note: str | None) -> dict:
    """인자 → `pick_ledger` 한 행. 🔴 모르는 값이면 `SystemExit`."""
    if judge_by not in JUDGES:
        raise SystemExit(f"🔴 모르는 판정자: {judge_by} (가능: {', '.join(JUDGES)})")
    if not valid_market(market):
        raise SystemExit(f"🔴 모르는 마켓: {market} (계열: {', '.join(MARKETS)}"
                         f" · 접미사는 {', '.join(SIDED)} 만)")
    return {
        "game_id": int(game_id), "sport": sport, "league": league, "date": date,
        "judge_by": judge_by, "market": market, "market_side": side,
        "line": float(line) if line is not None else None,
        "odds_taken": float(odds) if odds is not None else None,
        "is_final": True,
        # 🔴 승패 마켓일 때만 `predicted_side` 를 채운다 — over/under 를 거기
        #    넣으면 그 칸의 뜻이 둘이 되고, 적중 채점이 틀린다.
        "predicted_side": side if side in ("home", "away") else None,
        "cancel_reason": note,
    }


_INSERT = """
    INSERT INTO pick_ledger (game_id, sport, league, date, judge_by, market,
                             market_side, line, odds_taken, is_final,
                             predicted_side, cancel_reason)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
    RETURNING id, judged_at
"""


async def _run(a) -> int:
    from app.db import close_pool, get_pool

    pool = await get_pool()
    try:
        g = await pool.fetchrow(
            "SELECT id, sport, league, home, away,"
            " (starts_at AT TIME ZONE 'Asia/Seoul')::date::text d"
            "  FROM games WHERE id = $1", int(a.game))
        if g is None:
            print(f"🔴 그런 경기가 없다: game_id={a.game}", file=sys.stderr)
            return 1
        row = build_row(game_id=g["id"], sport=g["sport"], league=g["league"],
                        date=a.date or g["d"], judge_by=a.judge_by,
                        market=a.market, line=a.line, side=a.side,
                        odds=a.odds, note=a.note)
        rec = await pool.fetchrow(_INSERT, *[row[k] for k in (
            "game_id", "sport", "league", "date", "judge_by", "market",
            "market_side", "line", "odds_taken", "is_final",
            "predicted_side", "cancel_reason")])
        print(f"넣음 id={rec['id']} · {g['away']} @ {g['home']} · "
              f"{row['judge_by']} · {row['market']} "
              f"{row['market_side']}{'' if row['line'] is None else ' ' + str(row['line'])}"
              f" @ {row['odds_taken']}")
        return 0
    finally:
        await close_pool()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="원장에 사람이 건 픽을 넣는다")
    ap.add_argument("--game", required=True, type=int, help="games.id")
    ap.add_argument("--judge_by", required=True, choices=list(JUDGES))
    ap.add_argument("--market", required=True)
    ap.add_argument("--side", required=True,
                    help="over|under|home|away|draw")
    ap.add_argument("--line", type=float, default=None)
    ap.add_argument("--odds", type=float, default=None, help="실제로 받은 배당")
    ap.add_argument("--date", default=None, help="슬레이트 날짜(기본: 경기 KST 날짜)")
    ap.add_argument("--note", default=None)
    return asyncio.run(_run(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
