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
