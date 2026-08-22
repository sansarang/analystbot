"""statsapi.mlb.com 수집기 — 일정+선발투수, 투수 시즌 스탯, 순위, 최종 스코어.

CLI: python -m app.collectors.mlb --date 2026-08-22
"""

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings
from app.db import close_pool, get_pool

logger = logging.getLogger(__name__)

PITCHER_CHUNK = 10


def chunked(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


class MLBClient(BaseAPIClient):
    name = "mlb"
    base_url = "https://statsapi.mlb.com/api/v1"

    def __init__(self, mock: bool | None = None):
        super().__init__(get_settings().mock_mlb if mock is None else mock)

    async def fetch_schedule(self, date: str) -> dict:
        """날짜별 일정 + 선발투수 (hydrate=probablePitcher)."""
        if self.mock:
            return self.load_mock("mlb_schedule.json")
        return await self._get(
            "/schedule",
            params={"sportId": 1, "date": date, "hydrate": "probablePitcher"},
        )

    async def fetch_pitcher_stats(self, person_ids: list[int]) -> list[dict]:
        """선발투수 시즌 스탯. personIds는 10명 단위로 분할 호출."""
        if self.mock:
            people = self.load_mock("mlb_pitchers.json")["people"]
            wanted = set(person_ids)
            return [p for p in people if p["id"] in wanted]
        people: list[dict] = []
        for chunk in chunked(person_ids, PITCHER_CHUNK):
            data = await self._get(
                "/people",
                params={
                    "personIds": ",".join(map(str, chunk)),
                    "hydrate": "stats(group=[pitching],type=[season])",
                },
            )
            people.extend(data.get("people", []))
        return people

    async def fetch_standings(self, season: int | None = None) -> dict:
        if self.mock:
            return self.load_mock("mlb_standings.json")
        params: dict[str, Any] = {"leagueId": "103,104"}
        if season:
            params["season"] = season
        return await self._get("/standings", params=params)

    async def fetch_final_scores(self, date: str) -> dict:
        """최종 스코어 포함 일정 (schedule 응답에 teams.*.score 포함)."""
        if self.mock:
            return self.load_mock("mlb_finals.json")
        return await self._get("/schedule", params={"sportId": 1, "date": date})


def _parse_games(schedule: dict) -> list[dict]:
    out = []
    for day in schedule.get("dates", []):
        for g in day.get("games", []):
            home, away = g["teams"]["home"], g["teams"]["away"]
            state = g["status"]["abstractGameState"]
            out.append({
                "ext_id": str(g["gamePk"]),
                "starts_at": datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00")),
                "home": home["team"]["name"],
                "away": away["team"]["name"],
                "home_pitcher": (home.get("probablePitcher") or {}).get("fullName"),
                "away_pitcher": (away.get("probablePitcher") or {}).get("fullName"),
                "status": {"Preview": "scheduled", "Live": "live", "Final": "final"}.get(state, "scheduled"),
                "home_score": home.get("score"),
                "away_score": away.get("score"),
            })
    return out


async def upsert_games(
    pool: asyncpg.Pool, date: str, client: MLBClient | None = None,
    schedule: dict | None = None,
) -> int:
    """일정(+최종 스코어)을 games에 upsert. 적재 행 수 반환."""
    client = client or MLBClient()
    games = _parse_games(schedule or await client.fetch_schedule(date))
    for g in games:
        await pool.execute(
            """
            INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                               home_pitcher, away_pitcher, status, home_score, away_score)
            VALUES ('mlb', 'MLB', $1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (sport, ext_id) DO UPDATE SET
                starts_at = EXCLUDED.starts_at,
                home_pitcher = coalesce(EXCLUDED.home_pitcher, games.home_pitcher),
                away_pitcher = coalesce(EXCLUDED.away_pitcher, games.away_pitcher),
                status = EXCLUDED.status,
                home_score = coalesce(EXCLUDED.home_score, games.home_score),
                away_score = coalesce(EXCLUDED.away_score, games.away_score),
                updated_at = now()
            """,
            g["ext_id"], g["starts_at"], g["home"], g["away"],
            g["home_pitcher"], g["away_pitcher"], g["status"],
            g["home_score"], g["away_score"],
        )
    logger.info("[mlb] upserted %d games for %s", len(games), date)
    return len(games)


async def upsert_final_scores(pool: asyncpg.Pool, date: str, client: MLBClient | None = None) -> int:
    """최종 스코어를 games에 반영. final 처리된 경기 수 반환."""
    client = client or MLBClient()
    finals = [g for g in _parse_games(await client.fetch_final_scores(date))
              if g["status"] == "final"]
    for g in finals:
        await pool.execute(
            """
            UPDATE games SET status = 'final', home_score = $2, away_score = $3,
                             updated_at = now()
            WHERE sport = 'mlb' AND ext_id = $1
            """,
            g["ext_id"], g["home_score"], g["away_score"],
        )
    return len(finals)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="MLB schedule collector")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    pool = await get_pool()
    try:
        n = await upsert_games(pool, args.date)
        print(f"upserted {n} games into games table for {args.date}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(_main())
