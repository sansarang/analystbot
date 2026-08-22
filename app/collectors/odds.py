"""The Odds API v4 수집기 — h2h/spreads/totals decimal 배당을 odds_snapshots에 적재."""

import logging

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

SPORT_KEYS = {"mlb": "baseball_mlb", "soccer": "soccer_epl"}


class OddsClient(BaseAPIClient):
    name = "odds"
    base_url = "https://api.the-odds-api.com/v4"

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        super().__init__(settings.mock_odds if mock is None else mock)
        self.api_key = settings.odds_api_key

    async def fetch_odds(self, sport_key: str = "baseball_mlb") -> list[dict]:
        if self.mock:
            return self.load_mock(f"odds_{'mlb' if 'baseball' in sport_key else 'soccer'}.json")
        return await self._get(
            f"/sports/{sport_key}/odds",
            params={
                "apiKey": self.api_key,
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "decimal",
            },
        )


async def snapshot_odds(
    pool: asyncpg.Pool, sport: str = "mlb", client: OddsClient | None = None
) -> int:
    """이벤트를 (home, away)로 games와 매칭해 스냅샷 행 적재. 적재 행 수 반환."""
    client = client or OddsClient()
    events = await client.fetch_odds(SPORT_KEYS[sport])

    rows = await pool.fetch(
        "SELECT id, home, away FROM games WHERE sport = $1 AND status != 'final'", sport
    )
    game_ids = {(r["home"], r["away"]): r["id"] for r in rows}

    inserted = 0
    for ev in events:
        game_id = game_ids.get((ev["home_team"], ev["away_team"]))
        if game_id is None:
            logger.warning("[odds] no game match: %s @ %s", ev["away_team"], ev["home_team"])
            continue
        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                for outcome in market.get("outcomes", []):
                    await pool.execute(
                        """
                        INSERT INTO odds_snapshots (game_id, book, market, side, line, odds)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        game_id, bm["key"], market["key"],
                        outcome["name"], outcome.get("point"), outcome["price"],
                    )
                    inserted += 1
    logger.info("[odds] inserted %d snapshot rows (%s)", inserted, sport)
    return inserted
