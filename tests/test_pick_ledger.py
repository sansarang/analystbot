"""[v1.1 0단계] 픽 레저 — 기록·이력·채점·캘리브레이션.

이 표의 존재 이유는 "규율이 맞는가"를 데이터로 묻는 것이다. 그러므로 여기서
가장 중요한 테스트는 **보드만·거부권 경기도 기록되는가**다 — 그 경기들이
캘리브레이션 데이터의 절반이고, 빠지면 거부권이 옳은지 영원히 모른다.
"""

import pytest

from app.engine.calibration import MIN_SAMPLE, render_report, summarize
from app.engine.pick_ledger import (
    GATE_BOARD_ONLY,
    GATE_RECOMMENDED,
    GATE_VETOED,
    gate_result_of,
    grade_pending,
    predicted_side,
    record_analysis,
)

DATE = "2026-08-30"


async def _game(pool, gid: int, *, home="Doosan Bears", away="Kiwoom Heroes",
                status="scheduled", hs=None, aws=None) -> int:
    row = await pool.fetchrow(
        """INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                              status, home_score, away_score)
           VALUES ('kbo','KBO',$1, now() + interval '2 hours', $2,$3,$4,$5,$6)
           RETURNING id""",
        f"t:{gid}", home, away, status, hs, aws)
    return row["id"]


def _analysis(gid: int, *, p_home=0.66, favored="home", conf="상",
              lineup="confirmed", recommended=True, model="claude-sonnet-5",
              judge_pass=False, judge_confidence="high"):
    jg = {
        "game_id": gid, "sport": "kbo", "league": "KBO",
        "home": "Doosan Bears", "away": "Kiwoom Heroes",
        "p_claude": p_home, "lineup_status": lineup, "model": model,
        "judge_pass": judge_pass, "judge_confidence": judge_confidence,
        "matchup": {"p_home": p_home, "우세": favored, "확신도": conf},
    }
    picks = [{"game_id": gid, "market": "h2h", "recommended": recommended}]
    return {"sport": "kbo", "date": DATE, "games": [jg], "picks": picks}


# ---------------------------------------------------------------- 게이트 분류

def test_veto_beats_recommendation():
    """확신도 '하'는 확률이 높아도 거부권이다 — 그 사실 자체가 측정 대상이다."""
    jg = {"judge_pass": True, "judge_confidence": "high"}
    assert gate_result_of(jg, {"recommended": True}) == GATE_VETOED
    jg2 = {"judge_pass": False, "judge_confidence": "low"}
    assert gate_result_of(jg2, {"recommended": True}) == GATE_VETOED


def test_recommended_and_board_only():
    jg = {"judge_pass": False, "judge_confidence": "high"}
    assert gate_result_of(jg, {"recommended": True}) == GATE_RECOMMENDED
    assert gate_result_of(jg, {"recommended": False}) == GATE_BOARD_ONLY
    assert gate_result_of(jg, None) == GATE_BOARD_ONLY


def test_predicted_side_resolves_toss_up():
    """'박빙'도 방향을 확정한다 — 안 하면 그 표본이 통째로 빠진다."""
    assert predicted_side("home", 0.4) == "home"
    assert predicted_side("away", 0.9) == "away"
    assert predicted_side("박빙", 0.55) == "home"
    assert predicted_side("박빙", 0.45) == "away"
    assert predicted_side("박빙", None) is None


# ---------------------------------------------------------------- 기록·이력

async def test_records_every_judgement_including_board_only(db_pool):
    """발송 여부와 무관하게 전건 기록 — 보드만·거부권이 절반이다."""
    g1 = await _game(db_pool, 1)
    g2 = await _game(db_pool, 2)
    g3 = await _game(db_pool, 3)
    a = _analysis(g1)
    a["games"] += [
        _analysis(g2, recommended=False)["games"][0],
        _analysis(g3, judge_confidence="low")["games"][0],
    ]
    a["picks"] += [
        {"game_id": g2, "market": "h2h", "recommended": False},
        {"game_id": g3, "market": "h2h", "recommended": True},
    ]
    st = await record_analysis(db_pool, a)
    assert st["inserted"] == 3
    got = {r["game_id"]: r["gate_result"] for r in
           await db_pool.fetch("SELECT game_id, gate_result FROM pick_ledger")}
    assert got == {g1: GATE_RECOMMENDED, g2: GATE_BOARD_ONLY, g3: GATE_VETOED}


async def test_unjudged_game_is_not_recorded(db_pool):
    """판정이 없으면 행을 만들지 않는다 — 레저는 판정의 원장이다."""
    gid = await _game(db_pool, 4)
    a = _analysis(gid)
    a["games"][0]["matchup"] = {}
    assert (await record_analysis(db_pool, a))["inserted"] == 0
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 0


async def test_resaving_same_judgement_adds_no_history(db_pool):
    """같은 분석을 다시 저장해도 이력이 늘지 않는다 (캐시 재저장 멱등)."""
    gid = await _game(db_pool, 5)
    a = _analysis(gid)
    await record_analysis(db_pool, a)
    st = await record_analysis(db_pool, a)
    assert st == {"inserted": 0, "rejudged": 0, "unchanged": 1}
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 1


async def test_rejudge_keeps_history_and_single_final(db_pool):
    """재판정은 옛 행을 보존하고(is_final=false) 새 행을 최종으로 올린다."""
    gid = await _game(db_pool, 6)
    await record_analysis(db_pool, _analysis(gid, p_home=0.54))
    await record_analysis(db_pool, _analysis(gid, p_home=0.52))
    rows = await db_pool.fetch(
        "SELECT p_home, is_final, rejudge_count FROM pick_ledger"
        " WHERE game_id = $1 ORDER BY id", gid)
    assert len(rows) == 2
    assert [r["is_final"] for r in rows] == [False, True]
    assert rows[1]["rejudge_count"] == 1
    assert await db_pool.fetchval(
        "SELECT count(*) FROM pick_ledger WHERE game_id=$1 AND is_final", gid) == 1


async def test_ledger_has_no_ttl_column_and_survives(db_pool):
    """영구 테이블이어야 한다 — Redis TTL 키로 만들지 말라는 규칙의 회귀 방어."""
    cols = {r["column_name"] for r in await db_pool.fetch(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = 'pick_ledger'")}
    assert "graded_at" in cols and "hit" in cols
    assert not {c for c in cols if "ttl" in c or "expire" in c}


# ---------------------------------------------------------------- 채점

async def test_grades_final_games_only(db_pool):
    """진행 중 경기는 건드리지 않는다."""
    live = await _game(db_pool, 7, status="live", hs=3, aws=1)
    await record_analysis(db_pool, _analysis(live))
    assert (await grade_pending(db_pool)) == {"graded": 0, "void": 0}
    assert await db_pool.fetchval(
        "SELECT count(*) FROM pick_ledger WHERE graded_at IS NULL") == 1


async def test_grades_hit_and_miss(db_pool):
    won = await _game(db_pool, 8, status="final", hs=7, aws=2)     # 홈 승
    lost = await _game(db_pool, 9, status="final", hs=1, aws=5)    # 원정 승
    await record_analysis(db_pool, _analysis(won, favored="home"))
    await record_analysis(db_pool, _analysis(lost, favored="home"))
    assert (await grade_pending(db_pool))["graded"] == 2
    got = {r["game_id"]: (r["hit"], r["winner"], r["final_score"])
           for r in await db_pool.fetch(
               "SELECT game_id, hit, winner, final_score FROM pick_ledger")}
    assert got[won] == (True, "home", "2-7")
    assert got[lost] == (False, "away", "5-1")


async def test_cancelled_game_is_voided_not_left_pending(db_pool):
    """우천취소는 void로 닫는다 — 미채점으로 남기면 결손과 구분되지 않는다."""
    gid = await _game(db_pool, 10, status="cancelled")
    await record_analysis(db_pool, _analysis(gid))
    assert (await grade_pending(db_pool)) == {"graded": 0, "void": 1}
    r = await db_pool.fetchrow("SELECT void, hit, graded_at FROM pick_ledger")
    assert r["void"] is True and r["hit"] is None and r["graded_at"] is not None


async def test_grading_is_idempotent(db_pool):
    gid = await _game(db_pool, 11, status="final", hs=4, aws=1)
    await record_analysis(db_pool, _analysis(gid))
    await grade_pending(db_pool)
    assert (await grade_pending(db_pool)) == {"graded": 0, "void": 0}


# ---------------------------------------------------------------- 캘리브레이션

async def test_calibration_uses_predicted_side_probability(db_pool):
    """원정 픽의 예측 확률은 1-p_home이다.

    p_home을 그대로 쓰면 원정 픽이 0.34 구간에 들어가 표가 통째로 어긋난다.
    """
    gid = await _game(db_pool, 12, status="final", hs=1, aws=6)
    await record_analysis(db_pool, _analysis(gid, p_home=0.34, favored="away"))
    await grade_pending(db_pool)
    data = await summarize(db_pool, days=7)
    hit_bucket = next(b for b in data["buckets"] if b["n"])
    assert hit_bucket["label"] == "0.65+"        # 원정 66%
    assert data["sides"][1]["label"] == "away" and data["sides"][1]["n"] == 1


async def test_thin_sample_reports_shortage_not_numbers(db_pool):
    """표본 30 미만이면 적중률을 내지 않는다."""
    gid = await _game(db_pool, 13, status="final", hs=9, aws=0)
    await record_analysis(db_pool, _analysis(gid))
    await grade_pending(db_pool)
    text = render_report(await summarize(db_pool, days=7), days=7)
    assert "표본 부족" in text
    assert "100.0%" not in text          # 1건으로 100% 적중을 주장하지 않는다
    assert str(MIN_SAMPLE) in text


async def test_empty_ledger_says_no_sample_not_bad_performance(db_pool):
    text = render_report(await summarize(db_pool, days=7), days=7)
    assert "채점된 픽이 없습니다" in text
    assert "성적이 나쁘다는 뜻이 아닙니다" in text


# ---------------------------------------------------------------- 판정 비개입

def test_judgement_paths_do_not_read_the_ledger():
    """레저는 측정 전용이다 — 판정·폼·매치업 코드가 이 모듈을 읽으면 안 된다.

    CLAUDE.md 판정 철학("채점 성적표는 판정에 쓰지 않는다")을 코드로 잠근다.
    기록은 남기되, 그 기록이 판정으로 되돌아오는 경로는 만들지 않는다.
    """
    from pathlib import Path

    for mod in ("app/engine/matchup.py", "app/engine/team_form.py",
                "app/engine/markets.py", "app/engine/scoring.py"):
        src = Path(mod).read_text(encoding="utf-8")
        assert "pick_ledger" not in src, f"{mod}가 픽 레저를 읽는다 — 판정 비개입 위반"
        assert "calibration" not in src, f"{mod}가 캘리브레이션을 읽는다 — 판정 비개입 위반"


# ---------------------------------------------------------------- 소급 백필 (1회성)

class _FakeRedis:
    """스캔·get·SET 표식만 흉내낸다. 실제 Redis 없이 백필 경로를 검사한다."""

    def __init__(self, data: dict):
        self.data = dict(data)
        self.sets: dict[str, set] = {}

    async def scan_iter(self, match=None, count=None):
        for k in list(self.data):
            yield k

    async def get(self, k):
        return self.data.get(k)

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    async def aclose(self):
        pass


async def test_backfill_records_slates_and_skips_per_game_keys(db_pool):
    """슬레이트 키만 쓴다 — 경기별 키에는 게이트·라인업이 없어 반쪽이다."""
    import json

    from app.engine.pick_ledger import backfill_from_redis

    gid = await _game(db_pool, 20)
    r = _FakeRedis({
        f"analysis:kbo:{DATE}": json.dumps(_analysis(gid), ensure_ascii=False),
        # 경기별 키 — 무시돼야 한다
        f"analysis:kbo:{gid}:{DATE}": json.dumps({"p_home": 0.66, "우세": "home"}),
        # since 이전 — 무시돼야 한다
        "analysis:kbo:2026-08-01": json.dumps(_analysis(gid), ensure_ascii=False),
    })
    st = await backfill_from_redis(db_pool, r, "2026-08-29")
    assert st["slates"] == 1 and st["inserted"] == 1
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 1


async def test_backfill_skips_already_seen_keys(db_pool):
    """이미 백필한 키는 건너뛴다 (기동마다 다시 훑지 않는다)."""
    import json

    from app.engine.pick_ledger import backfill_from_redis

    gid = await _game(db_pool, 21)
    r = _FakeRedis({f"analysis:kbo:{DATE}": json.dumps(_analysis(gid),
                                                       ensure_ascii=False)})
    await backfill_from_redis(db_pool, r, "2026-08-29")
    st = await backfill_from_redis(db_pool, r, "2026-08-29")
    assert st["seen"] == 1 and st["slates"] == 0 and st["inserted"] == 0


async def test_backfill_is_idempotent_even_without_the_marker(db_pool):
    """표식을 잃어도 이력 행이 늘지 않는다 — 멱등의 두 번째 겹."""
    import json

    from app.engine.pick_ledger import backfill_from_redis

    gid = await _game(db_pool, 22)
    r = _FakeRedis({f"analysis:kbo:{DATE}": json.dumps(_analysis(gid),
                                                       ensure_ascii=False)})
    await backfill_from_redis(db_pool, r, "2026-08-29")
    st = await backfill_from_redis(db_pool, r, "2026-08-29", skip_seen=False)
    assert st["unchanged"] == 1 and st["inserted"] == 0
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 1


async def test_backfill_dry_run_writes_nothing(db_pool):
    import json

    from app.engine.pick_ledger import backfill_from_redis

    gid = await _game(db_pool, 23)
    r = _FakeRedis({f"analysis:kbo:{DATE}": json.dumps(_analysis(gid),
                                                       ensure_ascii=False)})
    st = await backfill_from_redis(db_pool, r, "2026-08-29", dry_run=True)
    assert st["slates"] == 1 and st["inserted"] == 0
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 0


def test_startup_backfill_does_not_block_scheduler_start():
    """백필은 기동 경로에서 await 되지 않는다.

    await 하면 Redis 스캔이 스케줄러 시작을 지연시키고, 17시대 라인업 폴을
    놓치면 그날 발송이 통째로 밀린다. create_task로 떼어 놓았는지 소스로 잠근다.
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert "asyncio.create_task(startup_backfill_job())" in src
    assert "await startup_backfill_job()" not in src
    start = src.index("scheduler.start()")
    assert src.index("asyncio.create_task(startup_backfill_job())") > start, \
        "백필 태스크가 scheduler.start() 앞에 있다 — 기동이 밀린다"
