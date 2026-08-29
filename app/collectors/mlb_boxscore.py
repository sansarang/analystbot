"""[§9-라인업 전적] MLB 종료 경기 statsapi boxscore → lineup_events.

KBO 공식·NPB Yahoo `/top`과 같다. 사이트만 statsapi다.
`source='boxscore'` — 발표 라인업(crawler 스냅샷)과 섞지 않는다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.collectors.lineups import MLBLineupClient, parse_boxscore
from app.collectors.mlb import MLBClient, upsert_games

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def parse_mlb_ip(v) -> float | None:
    """statsapi inningsPitched. '5.1' = 5이닝 1아웃, '5.2' = 2아웃."""
    s = str(v or "").strip()
    if not s or s in (".", "-", "—"):
        return None
    try:
        if "." in s:
            whole, frac = s.split(".", 1)
            outs = int(frac[0]) if frac else 0
            if outs not in (0, 1, 2):
                return float(s)
            return int(whole or 0) + outs / 3.0
        return float(int(s))
    except (TypeError, ValueError):
        return None


def parse_pitching(box: dict) -> dict[str, list[dict]]:
    """boxscore → {"home": [appearance, ...], "away": [...]}."""
    out: dict[str, list[dict]] = {"home": [], "away": []}
    teams = (box or {}).get("teams") or {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        players = team.get("players") or {}
        for i, pid in enumerate(team.get("pitchers") or []):
            key = pid if str(pid).startswith("ID") else f"ID{pid}"
            pdata = players.get(key) or {}
            person = pdata.get("person") or {}
            name = (person.get("fullName") or "").strip()
            if not name:
                continue
            st = ((pdata.get("stats") or {}).get("pitching") or {})
            out[side].append({
                "name": name,
                "is_starter": i == 0,
                "innings": parse_mlb_ip(st.get("inningsPitched")),
                "batters": st.get("battersFaced"),
                "hits": st.get("hits"),
                "hr": st.get("homeRuns"),
                "k": st.get("strikeOuts"),
                "bb": st.get("baseOnBalls"),
                "r": st.get("runs"),
                "er": st.get("earnedRuns"),
            })
    return out


def order_text(parsed_side: dict) -> str:
    names = parsed_side.get("batting_order") or []
    return "-".join(n for n in names if n)


async def backfill(pool, as_of: date | None = None, days: int = 14,
                   limit_per_team: int = 10,
                   schedule_client: MLBClient | None = None,
                   lineup_client: MLBLineupClient | None = None) -> dict:
    """최근 종료 경기 선발 9명·등판을 `source='boxscore'`로 적재한다."""
    from app.collectors.lineup_history import record
    from app.collectors.pitcher_log import record_appearances

    as_of = as_of or datetime.now(ET).date()
    schedule_client = schedule_client or MLBClient()
    lineup_client = lineup_client or MLBLineupClient()
    stats = {"games": 0, "rows": 0, "appearances": 0, "skipped": 0,
             "no_game": 0, "teams": 0}
    per_team: dict[str, int] = {}

    for back in range(days):
        day = (as_of - timedelta(days=back)).isoformat()
        try:
            await upsert_games(pool, day, client=schedule_client)
        except Exception as exc:
            logger.warning("[MLB백필] 일정 %s 적재 실패: %s", day, exc)
        try:
            sched = await schedule_client.fetch_schedule(day)
        except Exception as exc:
            logger.warning("[MLB백필] 일정 %s 조회 실패: %s", day, exc)
            continue
        from app.collectors.mlb import _parse_games

        for g in _parse_games(sched):
            if g.get("status") != "final":
                stats["skipped"] += 1
                continue
            gid_db = await pool.fetchval(
                "SELECT id FROM games WHERE sport = $1 AND ext_id = $2",
                "mlb", g["ext_id"]) if pool else None
            if gid_db is None:
                stats["no_game"] += 1
                continue
            try:
                box = await lineup_client.fetch_boxscore(g["ext_id"])
            except Exception as exc:
                logger.debug("[MLB백필] %s boxscore 실패: %s", g["ext_id"], exc)
                stats["skipped"] += 1
                continue
            parsed = parse_boxscore(box)
            if not parsed.get("confirmed"):
                stats["skipped"] += 1
                continue
            pits = parse_pitching(box)
            stats["games"] += 1
            for side in ("home", "away"):
                team = g[side]
                if per_team.get(team, 0) >= limit_per_team:
                    continue
                text = order_text(parsed.get(side) or {})
                starter = next((p["name"] for p in (pits.get(side) or [])
                                if p.get("is_starter") and p.get("name")), None)
                if await record(pool, gid_db, side, team, text,
                                starter=starter, source="boxscore"):
                    stats["rows"] += 1
                    per_team[team] = per_team.get(team, 0) + 1
            stats["appearances"] += await record_appearances(
                pool, gid_db, "mlb", g["home"], g["away"], pits,
                source="boxscore")
    stats["teams"] = len(per_team)
    logger.info("[MLB백필] 경기 %d · 적재 %d행 · 등판 %d · %d팀 (건너뜀 %d · 경기없음 %d)",
                stats["games"], stats["rows"], stats.get("appearances", 0),
                stats["teams"], stats["skipped"], stats["no_game"])
    return stats
