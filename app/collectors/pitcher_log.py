"""등판 로그 적재. KBO 공식·NPB Yahoo /stats가 같은 표에 쓴다."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_UPSERT = """
    INSERT INTO pitcher_appearances (
        game_id, sport, team, opponent, pitcher, is_starter,
        innings, batters, hits, hr, k, bb, r, er, source)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
    ON CONFLICT (game_id, team, pitcher) DO UPDATE SET
        is_starter = EXCLUDED.is_starter,
        innings = EXCLUDED.innings,
        batters = EXCLUDED.batters,
        hits = EXCLUDED.hits,
        hr = EXCLUDED.hr,
        k = EXCLUDED.k,
        bb = EXCLUDED.bb,
        r = EXCLUDED.r,
        er = EXCLUDED.er,
        source = EXCLUDED.source
"""


async def record_appearances(pool, game_id, sport: str, home: str, away: str,
                             by_side: dict, source: str) -> int:
    """by_side: {"home": [appearance, ...], "away": [...]}. 반환: 적재 시도 수."""
    if not pool or not game_id:
        return 0
    n = 0
    for side in ("home", "away"):
        team, opp = (home, away) if side == "home" else (away, home)
        for i, p in enumerate(by_side.get(side) or []):
            name = (p.get("name") or "").strip()
            if not name:
                continue
            try:
                await pool.execute(
                    _UPSERT,
                    int(game_id), sport, team, opp, name,
                    bool(p.get("is_starter", i == 0)),
                    p.get("innings"), p.get("batters"),
                    p.get("hits"), p.get("hr"), p.get("k"), p.get("bb"),
                    p.get("r"), p.get("er"), source)
                n += 1
            except Exception as exc:
                logger.warning("[등판로그] 적재 실패 game=%s %s: %s",
                               game_id, name, exc)
    return n
