"""수집기 목 모드 검증 — 15경기 적재, 멱등성, 배당 스냅샷, 투수 스탯 분할."""

from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer
from app.collectors.mlb import MLBClient, chunked, upsert_final_scores, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds

DATE = "2026-08-22"


async def test_mlb_upsert_loads_15_games(db_pool):
    n = await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    assert n == 15
    rows = await db_pool.fetch("SELECT * FROM games WHERE sport = 'mlb'")
    assert len(rows) == 15
    assert all(r["home_pitcher"] and r["away_pitcher"] for r in rows)
    assert all(r["status"] == "scheduled" for r in rows)


async def test_mlb_upsert_is_idempotent(db_pool):
    client = MLBClient(mock=True)
    await upsert_games(db_pool, DATE, client=client)
    await upsert_games(db_pool, DATE, client=client)
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport = 'mlb'") == 15


async def test_mlb_final_scores(db_pool):
    client = MLBClient(mock=True)
    await upsert_games(db_pool, DATE, client=client)
    n = await upsert_final_scores(db_pool, DATE, client=client)
    assert n == 15
    row = await db_pool.fetchrow("SELECT * FROM games WHERE sport = 'mlb' LIMIT 1")
    assert row["status"] == "final"
    assert row["home_score"] is not None and row["away_score"] is not None


async def test_pitcher_stats_chunking_and_fetch():
    assert [len(c) for c in chunked(list(range(25)), 10)] == [10, 10, 5]
    client = MLBClient(mock=True)
    people = await client.fetch_pitcher_stats([600000, 600001])
    assert {p["id"] for p in people} == {600000, 600001}
    stat = people[0]["stats"][0]["splits"][0]["stat"]
    assert "era" in stat and "whip" in stat


async def test_odds_snapshot(db_pool):
    await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    n = await snapshot_odds(db_pool, "mlb", client=OddsClient(mock=True))
    # 15경기 × 3북 × (h2h 2 + spreads 2 + totals 2) = 270행
    assert n == 270
    rows = await db_pool.fetch(
        """
        SELECT market, count(*) AS c FROM odds_snapshots GROUP BY market
        """
    )
    assert {r["market"]: r["c"] for r in rows} == {"h2h": 90, "spreads": 90, "totals": 90}
    orphan = await db_pool.fetchval(
        "SELECT count(*) FROM odds_snapshots o LEFT JOIN games g ON g.id = o.game_id WHERE g.id IS NULL"
    )
    assert orphan == 0


async def test_odds_skips_inplay_and_matches_by_start_time(db_pool):
    """인플레이 이벤트 제외 + 연전(같은 매치업 복수 경기)은 시작 시각으로 매칭."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    # 같은 매치업 두 경기: 어제(연전 1차전)와 내일(2차전)
    ids = {}
    for ext, delta in (("g_yesterday", timedelta(days=-1)), ("g_tomorrow", timedelta(days=1))):
        ids[ext] = await db_pool.fetchval(
            "INSERT INTO games (sport, league, ext_id, starts_at, home, away) "
            "VALUES ('mlb', 'MLB', $1, $2, 'Home Nine', 'Away Nine') RETURNING id",
            ext, now + delta,
        )

    def make_event(commence):
        return {
            "home_team": "Home Nine", "away_team": "Away Nine",
            "commence_time": commence.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bookmakers": [{"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                {"name": "Home Nine", "price": 1.5}, {"name": "Away Nine", "price": 2.6}]}]}],
        }

    class FakeClient:
        mock = False  # 인플레이 필터 활성화 경로
        last_headers: dict = {}

        async def fetch_odds(self, sport_key):
            return [
                make_event(now - timedelta(hours=3)),   # 인플레이 → 스킵
                make_event(now + timedelta(days=1)),    # 내일 경기 → g_tomorrow에 매칭
            ]

    inserted = await snapshot_odds(db_pool, "mlb", client=FakeClient(),
                                   only_keys=["baseball_mlb"])
    assert inserted == 2  # 이벤트 1건 × h2h 2아웃컴
    rows = await db_pool.fetch(
        "SELECT game_id, count(*) c FROM odds_snapshots "
        "WHERE game_id = ANY($1::bigint[]) GROUP BY game_id",
        list(ids.values()),
    )
    assert {r["game_id"]: r["c"] for r in rows} == {ids["g_tomorrow"]: 2}


async def test_soccer_schedule_fallback_from_odds_events(db_pool):
    """API-Football이 시즌 미지원일 때 Odds API 이벤트로 KST 당일 경기만 적재."""
    from app.collectors.odds import upsert_games_from_odds_events

    class FakeClient:
        mock = False

        async def fetch_events(self, sport_key):
            if sport_key != "soccer_japan_j_league":
                return []
            return [
                {"id": "ev1", "commence_time": "2026-08-23T10:30:00Z",   # KST 8/23 19:30
                 "home_team": "FC Machida Zelvia", "away_team": "Urawa Red Diamonds"},
                {"id": "ev2", "commence_time": "2026-08-23T16:00:00Z",   # KST 8/24 01:00 → 제외
                 "home_team": "Gamba Osaka", "away_team": "FC Tokyo"},
            ]

    ext_ids = await upsert_games_from_odds_events(db_pool, "2026-08-23", client=FakeClient())
    assert ext_ids == ["odds:ev1"]
    row = await db_pool.fetchrow("SELECT * FROM games WHERE ext_id = 'odds:ev1'")
    assert row["home"] == "FC Machida Zelvia" and row["league"] == "J1 리그"
    # 멱등
    await upsert_games_from_odds_events(db_pool, "2026-08-23", client=FakeClient())
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='soccer'") == 1


async def test_football_fixtures(db_pool):
    n = await upsert_soccer(db_pool, DATE, client=APIFootballClient(mock=True))
    assert n == 5
    rows = await db_pool.fetch("SELECT * FROM games WHERE sport = 'soccer'")
    assert len(rows) == 5
    assert all(r["league"] == "Premier League" for r in rows)


async def test_football_standings_and_h2h():
    client = APIFootballClient(mock=True)
    standings = await client.fetch_standings()
    table = standings["response"][0]["league"]["standings"][0]
    assert table[0]["rank"] == 1 and "points" in table[0]
    h2h = await client.fetch_h2h(50, 60)
    assert len(h2h["response"]) == 5
