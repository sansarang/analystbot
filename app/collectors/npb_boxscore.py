"""[§9-라인업 전적] NPB 종료 경기 Yahoo `/top` 打順 → lineup_events.

왜 필요한가 (2026-08-28 실측):
  KBO는 공식 박스스코어 백필이 있어 유사 타순 전적이 붙는다. NPB는
  `lineup_events` 0행 · 크롤러는 선발 투수만 넣었다. attach()는 종목 공용이라
  재료가 없으면 전적이 안 나온다.

⚠️ 이것은 **실제 출전 기록**이다. 발표 라인업(crawler)과 섞지 않는다.
⚠️ `/stats`·npb.jp 「最新のオーダー」는 교체·막판 타순이다. `/top`의
   `打順` 1~9번만 쓴다(실측: 대타 행 없음).
⚠️ 경기 매칭은 날짜 + 홈/원정. 날짜만으로 고르면 같은 날 6경기 중 아무거나 잡힌다.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.collectors.yahoo_npb import (
    TEAM_TO_ODDS,
    YahooNPBClient,
    parse_batting_orders,
    parse_finals,
    parse_pitching_stats,
    score_card_html,
)

logger = logging.getLogger(__name__)

NPB_TEAMS = tuple(TEAM_TO_ODDS.values())
JST = ZoneInfo("Asia/Tokyo")


async def fetch_final_lineups(game_id: str, client: YahooNPBClient) -> dict:
    """한 종료 경기 → {"home": [9], "away": [9]} 또는 빈 dict."""
    html = await client.game(game_id)
    lu = parse_batting_orders(html)
    if not lu["home"] or not lu["away"]:
        return {}
    return lu


async def backfill(pool, as_of: date | None = None, days: int = 14,
                   limit_per_team: int = 10,
                   client: YahooNPBClient | None = None) -> dict:
    """최근 종료 경기 선발 9명을 `source='boxscore'`로 적재한다."""
    from app.collectors.game_match import _FIND
    from app.collectors.lineup_history import record
    from app.collectors.pitcher_log import record_appearances

    client = client or YahooNPBClient()
    as_of = as_of or datetime.now(JST).date()
    stats = {"games": 0, "rows": 0, "appearances": 0,
             "skipped": 0, "no_game": 0, "teams": 0}
    per_team: dict[str, int] = {}
    seen: set[str] = set()

    for back in range(days):
        if per_team and min(per_team.values()) >= limit_per_team \
                and len(per_team) >= len(NPB_TEAMS):
            break
        day = (as_of - timedelta(days=back)).isoformat()
        try:
            html = score_card_html(await client.schedule(day))
            finals = parse_finals(html)
        except Exception as exc:
            logger.warning("[NPB백필] 일정 %s 실패: %s", day, exc)
            continue
        starts = datetime.fromisoformat(f"{day}T18:00:00").replace(
            tzinfo=JST).astimezone(UTC)
        for g in finals:
            gid = g["game_id"]
            if gid in seen:
                continue
            seen.add(gid)
            if (per_team.get(g["home"], 0) >= limit_per_team
                    and per_team.get(g["away"], 0) >= limit_per_team):
                continue
            gid_db = await pool.fetchval(
                "SELECT id FROM games WHERE sport = $1 AND ext_id = $2",
                "npb", f"yahoo:{gid}") if pool else None
            if gid_db is None and pool:
                gid_db = await pool.fetchval(
                    _FIND, "npb", g["home"], g["away"], starts, 20)
            if gid_db is None:
                stats["no_game"] += 1
                continue
            try:
                lu = await fetch_final_lineups(gid, client)
            except Exception as exc:
                logger.debug("[NPB백필] %s 조회 실패: %s", gid, exc)
                stats["skipped"] += 1
                continue
            if not lu:
                stats["skipped"] += 1
                continue
            pits = {"home": [], "away": []}
            try:
                pits = parse_pitching_stats(await client.stats(gid))
            except Exception as exc:
                logger.debug("[NPB백필] %s /stats 실패: %s", gid, exc)
            stats["games"] += 1
            for side in ("home", "away"):
                team = g[side]
                if per_team.get(team, 0) >= limit_per_team:
                    continue
                starter = next((p["name"] for p in (pits.get(side) or [])
                                if p.get("is_starter") and p.get("name")), None)
                if await record(pool, gid_db, side, team, lu[side],
                                starter=starter, source="boxscore"):
                    stats["rows"] += 1
                    per_team[team] = per_team.get(team, 0) + 1
            stats["appearances"] += await record_appearances(
                pool, gid_db, "npb", g["home"], g["away"], pits,
                source="boxscore")
    stats["teams"] = len(per_team)
    logger.info("[NPB백필] 경기 %d · 적재 %d행 · 등판 %d · %d팀 (건너뜀 %d · 경기없음 %d)",
                stats["games"], stats["rows"], stats.get("appearances", 0),
                stats["teams"],
                stats["skipped"], stats["no_game"])
    return stats
