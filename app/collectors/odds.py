"""The Odds API v4 수집기 — h2h/spreads/totals decimal 배당을 odds_snapshots에 적재.

주의 (실사고 이력):
- 이미 시작한 경기는 인플레이 배당(스코어 따라 요동)이 내려오므로 적재하지 않는다.
- 같은 매치업이 연전으로 여러 경기 있을 수 있어 (home, away) 이름만으로 매칭하면
  다른 날짜 경기에 배당이 붙는다 → 시작 시각(±2h)까지 맞는 경기에만 매칭한다.
"""

import logging
from datetime import UTC, datetime, timedelta

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

SPORT_KEYS: dict[str, list[str]] = {
    "mlb": ["baseball_mlb"],
    "soccer": ["soccer_epl", "soccer_japan_j_league", "soccer_denmark_superliga"],
}
SOCCER_LEAGUE_LABELS = {
    "soccer_epl": "EPL",
    "soccer_japan_j_league": "J1 리그",
    "soccer_denmark_superliga": "덴마크 수페르리가",
}

MATCH_WINDOW = timedelta(hours=2)  # 이벤트 commence_time ↔ games.starts_at 허용 오차


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

    async def fetch_events(self, sport_key: str) -> list[dict]:
        """예정 이벤트 목록 (배당 없음, 저비용) — 일정 소스 폴백용."""
        if self.mock:
            return self.load_mock(f"odds_{'mlb' if 'baseball' in sport_key else 'soccer'}.json")
        return await self._get(
            f"/sports/{sport_key}/events", params={"apiKey": self.api_key}
        )


def _match_game(candidates: list, commence: datetime) -> int | None:
    """같은 매치업 후보 중 시작 시각이 ±2h 내에서 가장 가까운 경기를 고른다."""
    best_id, best_diff = None, MATCH_WINDOW
    for game_id, starts_at in candidates:
        diff = abs(starts_at - commence)
        if diff <= best_diff:
            best_id, best_diff = game_id, diff
    return best_id


async def snapshot_odds(
    pool: asyncpg.Pool, sport: str = "mlb", client: OddsClient | None = None
) -> int:
    """이벤트를 (home, away, 시작시각)으로 games와 매칭해 스냅샷 적재. 적재 행 수 반환."""
    client = client or OddsClient()
    keys = SPORT_KEYS[sport]
    if client.mock:
        keys = keys[:1]  # 목 파일은 리그 구분 없이 하나 — 중복 적재 방지
    events: list[dict] = []
    for sport_key in keys:
        events.extend(await client.fetch_odds(sport_key))

    rows = await pool.fetch(
        "SELECT id, home, away, starts_at FROM games WHERE sport = $1 AND status = 'scheduled'",
        sport,
    )
    game_ids: dict[tuple[str, str], list] = {}
    for r in rows:
        game_ids.setdefault((r["home"], r["away"]), []).append((r["id"], r["starts_at"]))

    now = datetime.now(UTC)
    inserted = skipped_inplay = 0
    for ev in events:
        commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        # 인플레이 배당 배제 (목 모드는 고정 샘플이라 시간 비교를 건너뜀)
        if not client.mock and commence <= now:
            skipped_inplay += 1
            continue
        game_id = _match_game(game_ids.get((ev["home_team"], ev["away_team"]), []), commence)
        if game_id is None:
            logger.warning(
                "[odds] no game match: %s @ %s (%s)",
                ev["away_team"], ev["home_team"], ev["commence_time"],
            )
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
    logger.info(
        "[odds] inserted %d snapshot rows (%s), skipped %d in-play events",
        inserted, sport, skipped_inplay,
    )
    return inserted


async def upsert_games_from_odds_events(
    pool: asyncpg.Pool, date: str, client: OddsClient | None = None
) -> list[str]:
    """축구 일정 폴백 — API-Football이 현재 시즌을 못 줄 때 Odds API 이벤트로 적재.

    KST 기준 해당 날짜 경기만. ext_id는 'odds:<event id>'. 적재한 ext_id 목록 반환.
    주의: 이 경로로 적재된 경기는 최종 스코어 소스가 없어 자동 채점이 불가하다.
    """
    from zoneinfo import ZoneInfo

    kst = ZoneInfo("Asia/Seoul")
    client = client or OddsClient()
    keys = SPORT_KEYS["soccer"]
    if client.mock:
        keys = keys[:1]
    ext_ids: list[str] = []
    for sport_key in keys:
        for ev in await client.fetch_events(sport_key):
            commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if commence.astimezone(kst).strftime("%Y-%m-%d") != date:
                continue
            ext_id = f"odds:{ev['id']}"
            await pool.execute(
                """
                INSERT INTO games (sport, league, ext_id, starts_at, home, away, status)
                VALUES ('soccer', $1, $2, $3, $4, $5, 'scheduled')
                ON CONFLICT (sport, ext_id) DO UPDATE SET
                    starts_at = EXCLUDED.starts_at, updated_at = now()
                """,
                SOCCER_LEAGUE_LABELS.get(sport_key, sport_key), ext_id,
                commence, ev["home_team"], ev["away_team"],
            )
            ext_ids.append(ext_id)
    logger.info("[odds] soccer schedule fallback: %d games for %s (KST)", len(ext_ids), date)
    return ext_ids
