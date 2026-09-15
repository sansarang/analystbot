#!/usr/bin/env python
"""[U2 2026-09-15] 사람이 캡처한 배당을 `odds_snapshots` 에 넣는다.

🔴 **왜 필요한가.** ESPN core 는 8리그만 준다(epl·la_liga·serie_a·bundesliga·
   ligue1·eredivisie·kleague1·j1). ACL 엘리트·컵 대회·A매치는 파생 시장 소스가
   없다(오즈포털 경기 페이지는 JS 라 못 읽는다 — U2-b). 그 경기는 사람이 넣는다.

🔴 **`book='manual'` 로 남긴다.** 실소스와 섞이면 나중에 "이 값이 어디서 왔나"를
   못 가린다. 채점·이동 분석이 그 구분을 본다.

  python -m tools.manual_odds --game 8199 \
      --h2h 2.15,3.24,3.19 --ah -0.5:2.12/1.65 --ou 2.5:1.93/1.77 \
      --tag open_proxy

  --h2h  홈,무,원정 (소수배당)
  --ah   라인:홈배당/원정배당   라인은 **홈 기준**(원정은 부호를 뒤집어 저장)
  --ou   라인:오버/언더
  --tag  open | open_proxy | pre | lineup | late | close (원본은 odds_move)
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("manual_odds")

BOOK = "manual"
PROVIDER = "manual"


def parse_pair(spec: str) -> tuple[float, float, float]:
    """`라인:A/B` → (라인, A, B). 모양이 다르면 터진다 — 조용히 넘기지 않는다."""
    line, _, rest = str(spec).partition(":")
    a, _, b = rest.partition("/")
    return float(line), float(a), float(b)


def rows_for(home: str, away: str, *, h2h=None, ah=None, ou=None) -> list[dict]:
    """입력 → 적재 행. 🔴 핸디 라인은 홈 기준이고 원정은 부호를 뒤집는다."""
    out: list[dict] = []
    if h2h:
        for side, odd in zip((home, "Draw", away), h2h):
            out.append({"book": BOOK, "market": "h2h", "side": side,
                        "line": None, "odds": float(odd)})
    if ah:
        line, oh, oa = ah
        out.append({"book": BOOK, "market": "spreads", "side": home,
                    "line": round(line, 2), "odds": float(oh)})
        out.append({"book": BOOK, "market": "spreads", "side": away,
                    "line": round(-line, 2), "odds": float(oa)})
    if ou:
        line, over, under = ou
        out.append({"book": BOOK, "market": "totals", "side": "Over",
                    "line": round(line, 2), "odds": float(over)})
        out.append({"book": BOOK, "market": "totals", "side": "Under",
                    "line": round(line, 2), "odds": float(under)})
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description="사람이 캡처한 배당 입력")
    ap.add_argument("--game", type=int, required=True)
    ap.add_argument("--h2h", default="", help="홈,무,원정")
    ap.add_argument("--ah", default="", help="라인:홈/원정 (라인은 홈 기준)")
    ap.add_argument("--ou", default="", help="라인:오버/언더")
    ap.add_argument("--tag", default="", help="snap_tag")
    a = ap.parse_args()

    from app.collectors.odds_free import store_rows
    from app.db import get_pool
    from app.engine.odds_move import BASELINE_ORDER

    if a.tag and a.tag not in BASELINE_ORDER:
        logger.error("🔴 snap_tag %r 는 표에 없다 — 원본은 odds_move.BASELINE_ORDER %s",
                     a.tag, list(BASELINE_ORDER))
        return 2

    pool = await get_pool()
    g = await pool.fetchrow("SELECT id, home, away, league, starts_at FROM games "
                            "WHERE id = $1", a.game)
    if g is None:
        logger.error("🔴 game=%s 가 없다", a.game)
        return 2

    h2h = [float(x) for x in a.h2h.split(",")] if a.h2h else None
    if h2h and len(h2h) != 3:
        logger.error("🔴 --h2h 는 홈,무,원정 세 값이다: %r", a.h2h)
        return 2
    rows = rows_for(g["home"], g["away"], h2h=h2h,
                    ah=parse_pair(a.ah) if a.ah else None,
                    ou=parse_pair(a.ou) if a.ou else None)
    if not rows:
        logger.error("🔴 넣을 값이 없다 — --h2h/--ah/--ou 중 하나는 필요하다")
        return 2

    n = await store_rows(pool, a.game, rows, PROVIDER)
    if a.tag:
        # 🔴 방금 넣은 행에만 붙인다. 기존 태그는 덮지 않는다.
        await pool.execute(
            """UPDATE odds_snapshots SET snap_tag = $2
                WHERE game_id = $1 AND book = $3 AND snap_tag IS NULL""",
            a.game, a.tag, BOOK)
    logger.info("✅ game=%s %s@%s [%s] — %d행 적재 · book=%s · tag=%s",
                a.game, g["away"], g["home"], g["league"], n, BOOK, a.tag or "(없음)")
    for r in rows:
        logger.info("   %-8s %-22s line=%-6s %s", r["market"], r["side"],
                    r["line"], r["odds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
