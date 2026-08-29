"""스키마 적용·테이블 존재·expert_ledger 뷰 집계 검증."""

from datetime import UTC, datetime

EXPECTED_TABLES = {"games", "odds_snapshots", "expert_picks", "predictions",
                   "pitcher_appearances"}


def test_get_pool_applies_schema_so_appearances_exist_without_scheduler():
    from pathlib import Path

    src = Path("app/db.py").read_text(encoding="utf-8")
    assert "await apply_schema(_pool)" in src
    assert "pitcher_appearances" in Path("db/schema.sql").read_text(encoding="utf-8")


async def test_tables_and_view_exist(db_pool):
    rows = await db_pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    assert EXPECTED_TABLES <= {r["tablename"] for r in rows}
    views = await db_pool.fetch(
        "SELECT viewname FROM pg_views WHERE schemaname = 'public'"
    )
    assert "expert_ledger" in {r["viewname"] for r in views}


async def test_schema_is_idempotent(db_pool):
    from app.db import apply_schema

    async with db_pool.acquire() as conn:
        await apply_schema(conn)  # 두 번 적용해도 에러 없어야 함


async def test_expert_ledger_aggregates(db_pool):
    game_id = await db_pool.fetchval(
        """
        INSERT INTO games (sport, league, ext_id, starts_at, home, away)
        VALUES ('mlb', 'MLB', 'g1', $1, 'New York Yankees', 'Boston Red Sox')
        RETURNING id
        """,
        datetime(2026, 8, 22, 23, 0, tzinfo=UTC),
    )
    picks = [
        ("Alice", "win", 2.0, "h2h:New York Yankees"),
        ("Alice", "win", 1.8, "totals:Over:8.5"),
        ("Alice", "loss", 1.9, "spreads:New York Yankees:-1.5"),
        ("Alice", "push", 1.9, "totals:Under:9"),
    ]
    for expert, result, odds, pick in picks:
        await db_pool.execute(
            """
            INSERT INTO expert_picks (game_id, expert, site, pick, odds, result)
            VALUES ($1, $2, 'Covers', $3, $4, $5)
            """,
            game_id, expert, pick, odds, result,
        )

    row = await db_pool.fetchrow("SELECT * FROM expert_ledger WHERE expert = 'Alice'")
    assert row["picks_total"] == 4
    assert (row["wins"], row["losses"], row["pushes"]) == (2, 1, 1)
    # hit_rate = 2/3, roi = (1.0 + 0.8 - 1) / 3
    assert float(row["hit_rate"]) == round(2 / 3, 4)
    assert float(row["roi"]) == round(0.8 / 3, 4)
    # 방금 넣은 픽이므로 90일 집계에도 포함
    assert row["graded_90d"] == 3
    assert float(row["roi_90d"]) == round(0.8 / 3, 4)
