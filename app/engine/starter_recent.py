"""오늘 선발의 최근 2~3등판. 시즌 ERA는 넣지 않는다."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

RECENT_STARTS = 3

_FETCH = """
    SELECT a.opponent, a.innings, a.r, a.hits, a.k, a.bb,
           g.starts_at
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND a.pitcher = $2 AND a.is_starter
       AND g.starts_at < $3 AND g.status = 'final'
     ORDER BY g.starts_at DESC
     LIMIT $4
"""


def _aware(v) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def slim_start(row) -> dict:
    """등판 한 줄. ERA 키는 만들지 않는다."""
    def _get(k):
        if isinstance(row, dict):
            return row.get(k)
        try:
            return row[k]
        except (KeyError, IndexError, TypeError):
            return None

    out: dict = {}
    for k in ("opponent", "innings", "r", "hits", "k", "bb"):
        v = _get(k)
        if v is not None:
            out[k] = v
    dt = _aware(_get("starts_at"))
    if dt is not None:
        out["date"] = dt.date().isoformat()
    return out


def pitcher_name(jg: dict, side: str) -> str:
    r = jg.get("research") or {}
    p = r.get(f"{side}_pitcher") or {}
    if isinstance(p, dict):
        return (p.get("name") or "").strip()
    name = str(p or "").strip()
    if name:
        return name
    return str(jg.get(f"{side}_pitcher") or "").strip()


async def attach_starter_recent(jg: dict, pool) -> None:
    """research.{home,away}_starter_recent 을 채운다. pool 없으면 빈 목록."""
    research = jg.setdefault("research", {})
    sport = jg.get("sport") or ""
    before = _aware(jg.get("starts_at")) or datetime.now(UTC)
    for side in ("home", "away"):
        name = pitcher_name(jg, side)
        key = f"{side}_starter_recent"
        if not pool or not name or not sport:
            research.setdefault(key, [])
            continue
        try:
            rows = await pool.fetch(_FETCH, sport, name, before, RECENT_STARTS)
        except Exception as exc:
            logger.warning("[starter_recent] %s %s 조회 실패: %s", sport, name, exc)
            research.setdefault(key, [])
            continue
        research[key] = [slim_start(r) for r in rows]
