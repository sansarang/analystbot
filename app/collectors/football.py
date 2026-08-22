"""API-Football 수집기 — 일정·순위·최근 폼·H2H. 키 없으면 목 모드."""

import logging
from datetime import datetime

import asyncpg

from app.collectors.base import ApiQuotaError, BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

EPL_LEAGUE_ID = 39


def check_apifootball_quota(data: dict) -> dict:
    """API-Football은 쿼터 초과를 HTTP 200 + errors 필드로 반환한다."""
    errors = data.get("errors")
    if errors and any(k in str(errors).lower() for k in ("limit", "request", "subscription")):
        raise ApiQuotaError("football", str(errors)[:300])
    return data


class APIFootballClient(BaseAPIClient):
    name = "football"
    base_url = "https://v3.football.api-sports.io"

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        super().__init__(settings.mock_football if mock is None else mock)
        self.headers = {"x-apisports-key": settings.apifootball_key or ""}

    async def fetch_fixtures(self, date: str, league: int = EPL_LEAGUE_ID) -> dict:
        if self.mock:
            return self.load_mock("football_fixtures.json")
        return check_apifootball_quota(await self._get(
            "/fixtures", params={"date": date, "league": league}, headers=self.headers
        ))

    async def fetch_standings(self, league: int = EPL_LEAGUE_ID, season: int = 2026) -> dict:
        if self.mock:
            return self.load_mock("football_standings.json")
        return check_apifootball_quota(await self._get(
            "/standings", params={"league": league, "season": season}, headers=self.headers
        ))

    async def fetch_team_form(self, team_id: int, last: int = 5) -> dict:
        """최근 폼 = 해당 팀의 최근 N경기."""
        if self.mock:
            return self.load_mock("football_h2h.json")
        return check_apifootball_quota(await self._get(
            "/fixtures", params={"team": team_id, "last": last}, headers=self.headers
        ))

    async def fetch_h2h(self, home_id: int, away_id: int, last: int = 5) -> dict:
        if self.mock:
            return self.load_mock("football_h2h.json")
        return check_apifootball_quota(await self._get(
            "/fixtures/headtohead",
            params={"h2h": f"{home_id}-{away_id}", "last": last},
            headers=self.headers,
        ))


async def upsert_games(
    pool: asyncpg.Pool, date: str, client: APIFootballClient | None = None,
    fixtures: dict | None = None,
) -> int:
    client = client or APIFootballClient()
    data = fixtures or await client.fetch_fixtures(date)
    count = 0
    for item in data.get("response", []):
        fx, teams, goals = item["fixture"], item["teams"], item["goals"]
        status = {"NS": "scheduled", "FT": "final"}.get(fx["status"]["short"], "live")
        await pool.execute(
            """
            INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                               status, home_score, away_score)
            VALUES ('soccer', $1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (sport, ext_id) DO UPDATE SET
                status = EXCLUDED.status,
                home_score = coalesce(EXCLUDED.home_score, games.home_score),
                away_score = coalesce(EXCLUDED.away_score, games.away_score),
                updated_at = now()
            """,
            item["league"]["name"], str(fx["id"]),
            datetime.fromisoformat(fx["date"]),
            teams["home"]["name"], teams["away"]["name"],
            status, goals["home"], goals["away"],
        )
        count += 1
    logger.info("[football] upserted %d fixtures for %s", count, date)
    return count
