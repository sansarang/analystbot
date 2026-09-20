"""[W1 / wiring_first §W1] 커버리지 보고 — **리그별 칸 채움률.**

    python -m tools.coverage_report [--days 7] [--out docs/COVERAGE_<날짜>.md]

🔴 **이 표의 시계열이 배선 완성도의 증거다.** 이후 단계(W2~W11)는 전부
   "이 숫자가 어떻게 변했나"로 보고한다.
🔴 **조회만 한다.** SELECT 뿐이고 DB·Redis·컨테이너 상태를 바꾸지 않는다.
⚠️ 모르는 칸은 `—` 가 아니라 **0% 와 사유**로 적는다. 빈칸은 "안 쟀다"와
   "0 이다"를 섞어 버린다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
logger = logging.getLogger(__name__)

#: 🔴 칸 이름의 원본. 보고서 열이 이 순서로 나온다.
COLUMNS: tuple = (
    "결과", "예고선발", "확정라인업", "불펜3일", "투구수",
    "배당 open", "배당 close", "총점", "핸디", "기사출처",
)

_SQL_GAMES = """
    SELECT sport, league,
           count(*)                                              AS games,
           count(*) FILTER (WHERE status = 'final')               AS finals,
           count(*) FILTER (WHERE home_pitcher IS NOT NULL
                              AND away_pitcher IS NOT NULL)       AS starters,
           count(*) FILTER (WHERE lineup_status IN ('confirmed','official'))
                                                                  AS lineups,
           count(venue_name)                                      AS venues
      FROM games
     WHERE starts_at BETWEEN now() - ($1::int * interval '1 day') AND now()
     GROUP BY 1, 2
"""

_SQL_ODDS = """
    SELECT g.sport, g.league, o.market,
           count(DISTINCT o.game_id)                                   AS games,
           count(DISTINCT o.game_id) FILTER (WHERE o.snap_tag = 'open')  AS opens,
           count(DISTINCT o.game_id) FILTER (WHERE o.snap_tag = 'close') AS closes
      FROM odds_snapshots o
      JOIN games g ON g.id = o.game_id
     WHERE g.starts_at BETWEEN now() - ($1::int * interval '1 day') AND now()
     GROUP BY 1, 2, 3
"""

_SQL_PITCH = """
    SELECT g.league,
           count(DISTINCT pa.game_id)                          AS games,
           count(*)                                            AS rows,
           count(pa.pitches)                                   AS with_pitches,
           max((g.starts_at AT TIME ZONE 'Asia/Seoul')::date)  AS last_d
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     WHERE g.starts_at BETWEEN now() - ($1::int * interval '1 day') AND now()
     GROUP BY 1
"""


def _pct(n, d) -> str:
    """채움률. 🔴 분모가 0 이면 **0% 가 아니라 '대상없음'** 이다."""
    try:
        n, d = int(n or 0), int(d or 0)
    except (TypeError, ValueError):
        return "?"
    if d <= 0:
        return "대상없음"
    return f"{n / d:.0%} ({n}/{d})"


async def gather(pool, redis, *, days: int = 7) -> dict:
    """리그별 칸 채움률. 🔴 한 질의가 실패해도 나머지는 낸다."""
    out: dict = {"days": days, "leagues": {}, "notes": [],
                 "measured_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}

    async def _fetch(label, sql):
        try:
            return [dict(r) for r in await pool.fetch(sql, days)]
        except Exception as exc:
            out["notes"].append(f"{label} 조회 실패: {exc}")
            return []

    for r in await _fetch("games", _SQL_GAMES):
        key = f"{r['sport']}/{r['league']}"
        out["leagues"][key] = {
            "games": r["games"],
            "결과": _pct(r["finals"], r["games"]),
            "예고선발": _pct(r["starters"], r["games"]),
            "확정라인업": _pct(r["lineups"], r["games"]),
            "구장": _pct(r["venues"], r["games"]),
        }

    odds: dict = {}
    for r in await _fetch("odds", _SQL_ODDS):
        key = f"{r['sport']}/{r['league']}"
        odds.setdefault(key, {})[r["market"]] = r
    for key, box in out["leagues"].items():
        h2h = (odds.get(key) or {}).get("h2h") or {}
        box["배당 open"] = _pct(h2h.get("opens"), box["games"])
        box["배당 close"] = _pct(h2h.get("closes"), box["games"])
        box["총점"] = _pct(((odds.get(key) or {}).get("totals") or {}).get("games"),
                          box["games"])
        box["핸디"] = _pct(((odds.get(key) or {}).get("spreads") or {}).get("games"),
                          box["games"])

    pitch = {r["league"]: r for r in await _fetch("pitch", _SQL_PITCH)}
    for key, box in out["leagues"].items():
        league = key.split("/", 1)[-1]
        p = pitch.get(league)
        if p is None:
            box["불펜3일"] = "대상없음"
            box["투구수"] = "대상없음"
            continue
        box["불펜3일"] = _pct(p["games"], box["games"])
        box["투구수"] = _pct(p["with_pitches"], p["rows"])
        box["등판 최신"] = str(p["last_d"])

    # 기사 출처 — 🔴 규칙 원본은 `n05_evidence.card_trust` 다(사본 금지).
    try:
        from app.collectors.satellite import EXTRACT_KEY
        from app.flow.nodes.n05_evidence import card_trust

        tot = ok = 0
        pat = EXTRACT_KEY.format(sport="*", game_id="*")
        async for k in redis.scan_iter(match=pat, count=500):
            raw = await redis.get(k)
            if not raw:
                continue
            box = json.loads(raw)
            for side in ("home", "away"):
                card = ((box or {}).get("teams") or {}).get(side)
                if not card:
                    continue
                tot += 1
                ok += 1 if card_trust(box, card)[0] else 0
        out["sources"] = {"통과": ok, "전체": tot, "비율": _pct(ok, tot)}
    except Exception as exc:
        out["notes"].append(f"기사 출처 조회 실패: {exc}")
    return out


def render(doc: dict) -> str:
    """보고서 markdown. ⚠️ 200행을 넘기지 않는다(지시문 W10)."""
    L = [f"# COVERAGE {doc.get('measured_at_kst')} KST",
         "",
         f"최근 **{doc.get('days')}일** 경기 기준 · 조회 전용 · 판정에 쓰지 않는다.",
         "",
         "| 리그 | 경기 | 결과 | 예고선발 | 확정라인업 | 배당 open | 배당 close "
         "| 총점 | 핸디 | 불펜3일 | 투구수 | 구장 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(doc.get("leagues") or {}):
        b = doc["leagues"][key]
        L.append("| " + " | ".join(str(x) for x in (
            key, b.get("games"), b.get("결과"), b.get("예고선발"),
            b.get("확정라인업"), b.get("배당 open"), b.get("배당 close"),
            b.get("총점"), b.get("핸디"), b.get("불펜3일"),
            b.get("투구수"), b.get("구장"))) + " |")
    src = doc.get("sources") or {}
    L += ["", f"**기사 카드 출처 검사 통과**: {src.get('비율', '못 쟀다')}", ""]
    for n in (doc.get("notes") or []):
        L.append(f"- ⚠️ {n}")
    return "\n".join(L) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.db import close_pool, get_pool

    logging.basicConfig(level=logging.INFO)
    pool = await get_pool()
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        doc = await gather(pool, r, days=args.days)
        text = render(doc)
        out = args.out or (
            f"docs/COVERAGE_{datetime.now(KST):%Y-%m-%d}.md")
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out).write_text(text, encoding="utf-8")
        print(text)
        print(f"→ {out}")
    finally:
        await r.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
