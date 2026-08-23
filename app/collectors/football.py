"""축구 수집기.

- 1순위: football-data.org (FOOTBALL_DATA_KEY) — 메이저 12개 대회 일정·결과·순위.
- API-Football 코드는 유지하되 비활성 폴백 (Free 플랜이 현재 시즌 미지원).
- 마이너 리그(J1·덴마크 등)는 The Odds API 이벤트 폴백 (odds.py).
"""

import logging
import re as _re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg

from app.collectors.base import ApiQuotaError, BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

EPL_LEAGUE_ID = 39

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------- 팀명 퍼지 매칭

_GENERIC_TOKENS = {
    "fc", "afc", "cf", "bk", "if", "fk", "sc", "ac", "club", "and", "the",
    "de", "united?", "fodbold", "boldklub",
}
_TOKEN_SYNONYMS = {"man": "manchester", "utd": "united", "spurs": "tottenham",
                   "wolves": "wolverhampton", "nottm": "nottingham"}


def team_tokens(name: str) -> set[str]:
    raw = _re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return {
        _TOKEN_SYNONYMS.get(t, t)
        for t in raw
        if t not in _GENERIC_TOKENS and len(t) > 1
    }


def similar_team(a: str, b: str) -> bool:
    return bool(team_tokens(a) & team_tokens(b))


def match_team_name(target: str, candidates: list[str]) -> str | None:
    """토큰 교집합 최대 후보. 동점(모호)이면 None."""
    tt = team_tokens(target)
    scored = sorted(((len(tt & team_tokens(c)), c) for c in candidates), reverse=True)
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


# ---------------------------------------------------------------- football-data.org

FD_STATUS = {"SCHEDULED": "scheduled", "TIMED": "scheduled", "IN_PLAY": "live",
             "PAUSED": "live", "FINISHED": "final"}


class FootballDataClient(BaseAPIClient):
    name = "football_data"
    base_url = "https://api.football-data.org/v4"

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        if mock is None:
            mock = settings.force_mock or not settings.football_data_key
        super().__init__(mock)
        self.headers = {"X-Auth-Token": settings.football_data_key or ""}

    async def fetch_matches(self, date_kst: str) -> dict:
        """KST 날짜에 걸치는 경기 (UTC로는 전날 15:00~당일 15:00) — 구독 대회 전체."""
        if self.mock:
            return self.load_mock("footballdata_matches.json")
        d = datetime.strptime(date_kst, "%Y-%m-%d").date()
        return await self._get(
            "/matches",
            params={"dateFrom": (d - timedelta(days=1)).isoformat(), "dateTo": d.isoformat()},
            headers=self.headers,
        )

    async def fetch_standings(self, competition: str = "PL") -> dict:
        if self.mock:
            return self.load_mock("football_standings.json")
        return await self._get(f"/competitions/{competition}/standings", headers=self.headers)


async def upsert_games_from_football_data(
    pool: asyncpg.Pool, date_kst: str, client: FootballDataClient | None = None
) -> list[str]:
    """football-data.org 경기를 games에 upsert (KST 날짜 필터). ext_id 목록 반환."""
    client = client or FootballDataClient()
    data = await client.fetch_matches(date_kst)
    ext_ids: list[str] = []
    for m in data.get("matches", []):
        starts = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
        if starts.astimezone(KST).strftime("%Y-%m-%d") != date_kst:
            continue
        ext_id = f"fd:{m['id']}"
        score = m.get("score", {}).get("fullTime", {})
        await pool.execute(
            """
            INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                               status, home_score, away_score)
            VALUES ('soccer', $1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (sport, ext_id) DO UPDATE SET
                starts_at = EXCLUDED.starts_at, status = EXCLUDED.status,
                home_score = coalesce(EXCLUDED.home_score, games.home_score),
                away_score = coalesce(EXCLUDED.away_score, games.away_score),
                updated_at = now()
            """,
            m["competition"]["name"], ext_id, starts,
            m["homeTeam"]["name"], m["awayTeam"]["name"],
            FD_STATUS.get(m["status"], "scheduled"),
            score.get("home"), score.get("away"),
        )
        ext_ids.append(ext_id)
    logger.info("[football_data] upserted %d matches for %s (KST)", len(ext_ids), date_kst)
    return ext_ids


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
