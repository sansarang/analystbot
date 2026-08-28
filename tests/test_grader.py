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
    assert set(jobs) == {"prefetch_evening", "prefetch_dawn", "prefetch_asia",
                         "odds_snapshot_30m", "grade_yesterday",
                         "elo_refresh_weekly", "research_retry_45m", "lineup_poll_30m",
                         "statcast_daily", "soccerdata_daily", "park_weekly",
                         "kbo_lineup_history",
                         # [7-5] 하트비트가 있어야 /health가 스케줄러 생존을 안다
                         "heartbeat_2m"}
    assert "0:02:00" in str(jobs["heartbeat_2m"].trigger)
    assert "day_of_week='mon'" in str(jobs["elo_refresh_weekly"].trigger)
    assert str(jobs["prefetch_evening"].trigger) == "cron[hour='21', minute='0']"
    assert str(jobs["prefetch_dawn"].trigger) == "cron[hour='4', minute='30']"
    assert str(jobs["prefetch_asia"].trigger) == "cron[hour='14', minute='0']"
    assert str(jobs["grade_yesterday"].trigger) == "cron[hour='13', minute='0']"
    assert "0:30:00" in str(jobs["odds_snapshot_30m"].trigger)


# ---------------------------------------------------------------- [6] 병렬 채점

async def _pred(db_pool, method, result, pnl, p=0.60, odds=1.80):
    row = await db_pool.fetchrow(
        """
        INSERT INTO games (sport, league, ext_id, starts_at, home, away)
        VALUES ('mlb', 'MLB', $1, now(), 'H', 'A')
        ON CONFLICT (sport, ext_id) DO UPDATE SET home = EXCLUDED.home
        RETURNING id
        """,
        f"parallel-{method}-{result}-{pnl}",
    )
    await db_pool.execute(
        """
        INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                 method, result, pnl)
        VALUES ($1, 'h2h:H', $2, $3, 0.0, 0.0, $4, $5, $6)
        """,
        row["id"], p, odds, method, result, pnl,
    )


async def test_method_ledger_separates_two_approaches(db_pool):
    """[6] 경기력 기반과 시장 반영 픽을 따로 집계해 나란히 비교할 수 있어야 한다."""
    from app.grader import method_ledger

    await db_pool.execute("DELETE FROM predictions")
    await _pred(db_pool, "performance", "win", 0.80)
    await _pred(db_pool, "performance", "loss", -1.0)
    await _pred(db_pool, "legacy", "win", 0.90)

    ledger = {m["method"]: m for m in await method_ledger(db_pool)}
    assert set(ledger) == {"performance", "legacy"}
    assert ledger["performance"]["graded"] == 2
    assert ledger["performance"]["hit_rate"] == 0.5
    assert ledger["legacy"]["hit_rate"] == 1.0
    assert abs(ledger["performance"]["pnl_units"] - (-0.2)) < 1e-6


async def test_performance_report_shows_both_methods(db_pool):
    """[6] 성적표에 두 방식이 나란히 표시되고, 표본이 적으면 판단 보류를 명시한다."""
    from app.bot.main import render_performance

    await db_pool.execute("DELETE FROM predictions")
    await _pred(db_pool, "performance", "win", 0.80)
    await _pred(db_pool, "legacy", "loss", -1.0)

    out = await render_performance(db_pool)
    assert "방식 비교" in out
    assert "경기력 기반(현행)" in out and "참고 방식" in out
    assert "200~300건 전에는 우열을 판단하지 않습니다" in out


# ---------------------------------------------------------------- [§7] Brier·캘리브레이션

def test_brier_score_rewards_calibration():
    """[§7] Brier = mean((예측 - 실제)^2). 항상 50%를 찍으면 0.250이 기준선이다."""
    from app.grader import brier_score

    # 자신 있게 맞힌 예측이 가장 좋다
    confident_right = brier_score([{"model_p": 0.90, "result": "win"}] * 4)
    coin_flip = brier_score([{"model_p": 0.50, "result": "win"}] * 4)
    confident_wrong = brier_score([{"model_p": 0.90, "result": "loss"}] * 4)
    assert confident_right < coin_flip < confident_wrong
    assert coin_flip == 0.25          # 기준선
    assert brier_score([]) is None
    # 미채점·푸시는 세지 않는다
    assert brier_score([{"model_p": 0.6, "result": None},
                        {"model_p": 0.6, "result": "push"}]) is None


def test_calibration_bands_report_actual_vs_predicted():
    """[§7] "60%라고 한 픽이 정말 60% 이겼나" — 구간별 실제 승률."""
    from app.grader import calibration_bands

    rows = ([{"model_p": 0.62, "result": "win"}] * 6
            + [{"model_p": 0.62, "result": "loss"}] * 4
            + [{"model_p": 0.72, "result": "loss"}] * 2)
    bands = {b["band"]: b for b in calibration_bands(rows)}
    b60 = bands["60%~65%"]
    assert b60["n"] == 10 and b60["actual"] == 0.6
    assert abs(b60["gap"]) < 0.03            # 예측 62.5% vs 실제 60% — 잘 맞음
    b70 = bands["70%~100%"]
    assert b70["actual"] == 0.0 and b70["gap"] < -0.5   # 과신 구간이 드러난다


def test_calibration_skips_empty_bands():
    from app.grader import calibration_bands

    assert calibration_bands([]) == []
    bands = calibration_bands([{"model_p": 0.51, "result": "win"}])
    assert len(bands) == 1 and bands[0]["band"] == "50%~55%"


async def test_method_ledger_includes_brier_and_calibration(db_pool):
    """[§7] 두 방식 비교에 Brier와 캘리브레이션이 함께 나온다."""
    from app.grader import method_ledger

    await db_pool.execute("DELETE FROM predictions")
    for res, pnl, p in (("win", 0.8, 0.62), ("loss", -1.0, 0.61), ("win", 0.7, 0.63)):
        await _pred(db_pool, "performance", res, pnl, p=p)
    ledger = {m["method"]: m for m in await method_ledger(db_pool)}
    perf = ledger["performance"]
    assert perf["brier"] is not None and 0 < perf["brier"] < 0.5
    assert perf["calibration"] and perf["calibration"][0]["band"] == "60%~65%"


# ---------------------------------------------------------------- [§6-4] 3방식 병렬 기록

async def _pred3(db_pool, result, pnl, ph, pl, pc):
    row = await db_pool.fetchrow(
        "INSERT INTO games (sport, league, ext_id, starts_at, home, away) "
        "VALUES ('mlb','MLB',$1, now(), 'H','A') "
        "ON CONFLICT (sport, ext_id) DO UPDATE SET home = EXCLUDED.home RETURNING id",
        f"three-{result}-{ph}-{pl}-{pc}")
    await db_pool.execute(
        """
        INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly, result, pnl,
                                 p_heuristic, p_learned, p_claude)
        VALUES ($1, 'h2h:H', $2, 1.80, 0.0, 0.0, $3, $4, $5, $6, $7)
        """,
        row["id"], ph, result, pnl, ph, pl, pc)


async def test_three_way_ledger_compares_same_sample(db_pool):
    """[§6-4] 세 방식이 **같은 픽**을 어떻게 봤는지 비교한다 (표본이 갈리지 않는다)."""
    from app.grader import three_way_ledger

    await db_pool.execute("DELETE FROM predictions")
    await _pred3(db_pool, "win", 0.8, 0.62, 0.55, 0.70)
    await _pred3(db_pool, "loss", -1.0, 0.61, 0.52, 0.68)

    ledger = {m["method"]: m for m in await three_way_ledger(db_pool)}
    assert set(ledger) == {"p_heuristic", "p_learned", "p_claude"}
    assert all(m["n"] == 2 for m in ledger.values())      # 동일 표본
    assert ledger["p_heuristic"]["label"] == "임의 계수 λ"
    assert all(m["brier"] is not None for m in ledger.values())


async def test_three_way_ledger_handles_missing_column(db_pool):
    """[§6-4] 학습 아티팩트가 없으면 p_learned가 비어 있다 — 그 방식만 n=0."""
    from app.grader import three_way_ledger

    await db_pool.execute("DELETE FROM predictions")
    await _pred3(db_pool, "win", 0.8, 0.62, None, 0.70)
    ledger = {m["method"]: m for m in await three_way_ledger(db_pool)}
    assert ledger["p_learned"]["n"] == 0
    assert ledger["p_heuristic"]["n"] == 1


async def _fake_pool():
    return None


# --- grading_job은 야구·축구 둘 다 채점한다 (2026-08-25: 축구가 영원히 미채점) ---

@pytest.mark.asyncio
async def test_grading_job_covers_all_sports(monkeypatch):
    seen: list[str] = []

    async def fake_grade_date(pool, date, sport="mlb"):
        seen.append(sport)
        return {"predictions": 1, "expert_picks": 0, "unparseable": 0}

    import app.scheduler as sched

    monkeypatch.setattr(sched, "grade_date", fake_grade_date)
    monkeypatch.setattr(sched, "get_pool", _fake_pool)
    await sched.grading_job()
    assert seen == ["mlb", "soccer", "kbo", "npb"]   # [§8-14] NPB 추가


@pytest.mark.asyncio
async def test_grading_job_continues_after_one_sport_fails(monkeypatch):
    """한 종목이 터져도 다른 종목 채점은 계속돼야 한다."""
    seen: list[str] = []

    async def fake_grade_date(pool, date, sport="mlb"):
        seen.append(sport)
        if sport == "mlb":
            raise RuntimeError("statsapi 다운")
        return {"predictions": 2, "expert_picks": 0, "unparseable": 0}

    import app.scheduler as sched

    monkeypatch.setattr(sched, "grade_date", fake_grade_date)
    monkeypatch.setattr(sched, "get_pool", _fake_pool)
    out = await sched.grading_job()
    assert seen == ["mlb", "soccer", "kbo", "npb"]   # [§8-14] NPB 추가
    assert "soccer" in out and "kbo" in out and "mlb" not in out


def test_jobs_survive_missed_run_window():
    """★ 실사고(2026-08-26): 04:00 프리페치가 10분 늦었다고 건너뛰어졌다.

    APScheduler 기본 misfire_grace_time은 1초다 — 노트북이 잠들면
    하루 1회 잡이 매일 사라진다.
    """
    scheduler = build_scheduler()
    for job in scheduler.get_jobs():
        assert job.misfire_grace_time and job.misfire_grace_time >= 60, job.id
        assert job.coalesce is True, f"{job.id}: 밀린 실행이 쌓이면 안 된다"
        assert job.max_instances == 1, f"{job.id}: 동시 실행 금지"
    pf = {j.id: j for j in scheduler.get_jobs()}["prefetch_dawn"]
    assert pf.misfire_grace_time >= 3600, "일 1회 잡은 넉넉한 유예가 필요하다"


# ---------------------------------------------------------------- [§8-18] CLV 제거

def test_clv_is_removed():
    """[§8-18] CLV(마감 배당 대비 가치) 수집을 삭제했다.

    우리 가격을 시장 마감가와 비교하는 지표라 **시장에 앵커링**된다.
    "시장보다 좋은 가격을 잡았나"가 아니라 **"우리가 맞혔나"**가 유일한 질문이다.
    """
    import app.grader as g

    assert not hasattr(g, "closing_odds_for")
    assert not hasattr(g, "clv_ledger")


def test_grading_records_result_without_money(db_pool):
    """채점은 적중/빗나감만 남긴다 — 마감 배당을 더 이상 채우지 않는다."""
    from pathlib import Path

    src = Path("app/grader.py").read_text(encoding="utf-8")
    assert "closing_odds = $" not in src, "채점이 아직 마감 배당을 쓰고 있다"
