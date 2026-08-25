"""채점기 검증 — ML/핸디캡/토탈 판정 로직(핸디캡 동점 push 포함) + DB 왕복 + 스케줄러 잡."""

import pytest

from app.collectors.mlb import MLBClient, upsert_games
from app.grader import grade_date, grade_pick, pnl_for
from app.scheduler import build_scheduler

HOME, AWAY = "New York Yankees", "Athletics"
DATE = "2026-08-22"


def test_grade_moneyline():
    assert grade_pick(f"h2h:{HOME}", HOME, AWAY, 5, 3) == "win"
    assert grade_pick(f"h2h:{HOME}", HOME, AWAY, 2, 3) == "loss"
    assert grade_pick(f"h2h:{AWAY}", HOME, AWAY, 2, 3) == "win"
    assert grade_pick(f"h2h:{HOME}", HOME, AWAY, 2, 2) == "loss"  # 무승부 → ML 패
    assert grade_pick("h2h:Dodgers", HOME, AWAY, 5, 3) is None    # 경기 무관 팀


def test_grade_totals_with_push():
    assert grade_pick("totals:Over:8.5", HOME, AWAY, 5, 4) == "win"    # 9 > 8.5
    assert grade_pick("totals:Under:8.5", HOME, AWAY, 5, 4) == "loss"
    assert grade_pick("totals:Over:9", HOME, AWAY, 5, 4) == "push"     # 9 == 9
    assert grade_pick("totals:Under:9", HOME, AWAY, 5, 4) == "push"
    assert grade_pick("totals:Under:10", HOME, AWAY, 5, 4) == "win"


def test_grade_spreads_with_push():
    # 홈 -1.5: 2점차 승 → 커버
    assert grade_pick(f"spreads:{HOME}:-1.5", HOME, AWAY, 6, 4) == "win"
    assert grade_pick(f"spreads:{HOME}:-1.5", HOME, AWAY, 5, 4) == "loss"
    # 핸디캡 동점 push: 홈 -1, 정확히 1점차 → 6-1 == 5
    assert grade_pick(f"spreads:{HOME}:-1", HOME, AWAY, 6, 5) == "push"
    # 원정 +1.5: 1점차 패 → 커버
    assert grade_pick(f"spreads:{AWAY}:+1.5", HOME, AWAY, 5, 4) == "win"
    assert grade_pick(f"spreads:{AWAY}:+1.5", HOME, AWAY, 6, 4) == "loss"


def test_pnl():
    assert pnl_for("win", 2.1) == 1.1
    assert pnl_for("win", None) == pytest.approx(0.91)  # 배당 없으면 1.91 가정
    assert pnl_for("loss", 2.1) == -1.0
    assert pnl_for("push", 2.1) == 0.0


async def test_grade_date_roundtrip(db_pool):
    await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    game = await db_pool.fetchrow("SELECT * FROM games WHERE sport='mlb' LIMIT 1")

    await db_pool.execute(
        """
        INSERT INTO expert_picks (game_id, expert, site, pick, odds)
        VALUES ($1, 'Alice', 'Covers', $2, 2.0), ($1, 'Bob', 'SBR', $3, 1.9)
        """,
        game["id"], f"h2h:{game['home']}", "totals:Over:0.5",
    )
    await db_pool.execute(
        "INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly) "
        "VALUES ($1, $2, 0.6, 2.0, 0.2, 0.05)",
        game["id"], f"h2h:{game['home']}",
    )

    counts = await grade_date(db_pool, DATE, "mlb")  # 목 final 스코어 반영 후 채점
    assert counts["expert_picks"] == 2
    assert counts["predictions"] == 1

    graded = await db_pool.fetchrow(
        "SELECT g.home_score, g.away_score, p.result, p.pnl FROM predictions p "
        "JOIN games g ON g.id = p.game_id WHERE p.game_id = $1", game["id"],
    )
    expected = "win" if graded["home_score"] > graded["away_score"] else "loss"
    assert graded["result"] == expected
    assert float(graded["pnl"]) == (1.0 if expected == "win" else -1.0)

    # expert_ledger 뷰 자동 갱신 확인 (총점 0.5 초과 → Over는 항상 win)
    ledger = await db_pool.fetchrow("SELECT * FROM expert_ledger WHERE expert = 'Bob'")
    assert ledger["wins"] == 1 and ledger["picks_total"] == 1

    # 재실행 시 이미 채점된 픽은 건너뜀 (멱등)
    counts2 = await grade_date(db_pool, DATE, "mlb")
    assert counts2["expert_picks"] == 0 and counts2["predictions"] == 0


def test_scheduler_jobs_registered():
    scheduler = build_scheduler()
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {"prefetch_daily", "odds_snapshot_30m", "grade_yesterday",
                         "elo_refresh_weekly", "research_retry_45m", "lineup_poll_30m"}
    assert "day_of_week='mon'" in str(jobs["elo_refresh_weekly"].trigger)
    assert str(jobs["prefetch_daily"].trigger) == "cron[hour='4', minute='0']"
    assert str(jobs["grade_yesterday"].trigger) == "cron[hour='13', minute='0']"
    assert "0:30:00" in str(jobs["odds_snapshot_30m"].trigger)
