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
    assert st == {"inserted": 0, "rejudged": 0, "unchanged": 1, "failed": 0}
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
    # [계약 갱신 2026-09-01] final_score 는 **"홈-원정"** 순이다.
    #   종전 f"{a}-{h}" 는 원정-홈이라 카드·중계 표기와 순서가 뒤집혀 있었다.
    #   기존 행은 소급 수정하지 않는다(어느 순서로 적힌 행인지 구분 불가해진다).
    assert got[won] == (True, "home", "7-2")
    assert got[lost] == (False, "away", "1-5")


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


# ---------------------------------------------------------------- 조용한 실패 방지
#
# 레저는 판정의 **유일한 영구 기록**이다 (analysis: 키는 12시간 TTL).
# 기록이 조용히 실패하면 캘리브레이션 표본에 소리 없이 구멍이 나고,
# 표본이 얇은 것인지 데이터가 샌 것인지 구분할 수 없게 된다.

async def test_partial_failure_is_counted_not_swallowed(db_pool):
    """한 경기 기록이 실패하면 나머지는 계속하되 **건수를 보고**한다."""
    gid = await _game(db_pool, 30)
    a = _analysis(gid)
    # game_id가 games에 없으면 FK 위반 → 그 행만 실패한다
    a["games"].append(_analysis(999_999_999)["games"][0])
    a["picks"].append({"game_id": 999_999_999, "market": "h2h", "recommended": False})
    st = await record_analysis(db_pool, a)
    assert st["inserted"] == 1
    assert st["failed"] == 1, "실패를 세지 않으면 호출자가 CRITICAL을 올릴 수 없다"


async def test_record_ledger_retries_once_then_logs_critical(monkeypatch, caplog):
    """전체 실패 시 1회 재시도하고, 그래도 실패하면 CRITICAL을 남긴다."""
    import logging

    import app.pipeline as pipemod

    calls = []

    async def broken(*a, **kw):
        calls.append(1)
        raise RuntimeError("pool down")

    monkeypatch.setattr("app.engine.pick_ledger.record_analysis", broken)
    monkeypatch.setattr("app.db.get_pool", broken)
    with caplog.at_level(logging.CRITICAL):
        await pipemod._record_ledger({"sport": "kbo", "date": DATE, "games": []})
    assert len(calls) == 2, "재시도가 1회여야 한다 (총 2회 시도)"
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
    assert "영구 기록" in caplog.text


async def test_record_ledger_logs_critical_on_partial_failure(monkeypatch, caplog):
    """예외가 없어도 일부 경기가 누락되면 CRITICAL이다 — 같은 종류의 손실이다."""
    import logging

    import app.pipeline as pipemod

    async def partial(pool, analysis):
        return {"inserted": 1, "rejudged": 0, "unchanged": 0, "failed": 2}

    async def fake_pool():
        return object()

    monkeypatch.setattr("app.engine.pick_ledger.record_analysis", partial)
    monkeypatch.setattr("app.db.get_pool", fake_pool)
    with caplog.at_level(logging.CRITICAL):
        await pipemod._record_ledger({"sport": "kbo", "date": DATE, "games": []})
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
    assert "2건" in caplog.text


async def test_record_ledger_never_raises_into_the_send_path(monkeypatch):
    """레저가 어떻게 실패하든 발송 경로로 예외가 나가지 않는다."""
    import app.pipeline as pipemod

    async def broken(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.db.get_pool", broken)
    await pipemod._record_ledger({"sport": "kbo", "date": DATE, "games": []})


# ---------------------------------------------------------------- 중복 병합 방어
#
# 🔴 실사고 2026-08-31: 중복 경기 병합이 pick_ledger를 이관하지 않아
#    DELETE FROM games 의 ON DELETE CASCADE가 판정 기록을 조용히 지웠다.
#    로컬 재현으로 확정했다(병합 1건 → 레저 1행 소멸).
#    CASCADE 자체는 옳다 — 진짜 경기가 지워지면 그 판정도 무의미하다.
#    잘못은 병합이 이관 목록에서 레저를 빠뜨린 것이다.

async def _dup_pair(pool) -> tuple[int, int]:
    """같은 경기가 두 ext_id로 갈라진 상황."""
    ids = []
    for ext in ("dupA", "dupB"):
        ids.append(await pool.fetchval(
            "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status,"
            " home_score,away_score) VALUES ('kbo','KBO',$1,"
            " now() - interval '3 hours','Doosan Bears','Kiwoom Heroes','final',5,2)"
            " RETURNING id", ext))
    return ids[0], ids[1]


async def test_merge_never_shrinks_the_ledger(db_pool):
    """🔴 이번 결함의 재발 방어선 — 병합 후 레저 행 수가 줄지 않는다."""
    from app.collectors.game_match import merge_duplicate_games

    keep, dup = await _dup_pair(db_pool)
    await record_analysis(db_pool, {**_analysis(dup), "date": DATE})
    before = await db_pool.fetchval("SELECT count(*) FROM pick_ledger")
    assert before == 1
    await merge_duplicate_games(db_pool)
    after = await db_pool.fetchval("SELECT count(*) FROM pick_ledger")
    assert after >= before, "병합이 판정 기록을 지웠다 — CASCADE 누락 재발"


async def test_merge_moves_ledger_to_the_kept_game(db_pool):
    """이관된 행은 살아남은 경기를 가리키고, 출처가 남는다."""
    from app.collectors.game_match import merge_duplicate_games

    keep, dup = await _dup_pair(db_pool)
    await record_analysis(db_pool, _analysis(dup))
    res = await merge_duplicate_games(db_pool)
    assert res["moved_ledger"] == 1
    row = await db_pool.fetchrow(
        "SELECT game_id, merged_from, is_final FROM pick_ledger")
    survivors = {keep, dup} - {row["game_id"]}
    assert row["game_id"] in (keep, dup) and survivors, "이관 대상이 모호하다"
    assert row["merged_from"] == dup, "병합 출처가 남지 않았다"
    assert row["is_final"] is True


async def test_merge_conflict_demotes_instead_of_deleting(db_pool):
    """양쪽에 같은 날짜 최종 행이 있으면 dup 쪽을 이력으로 낮춰 **보존**한다.

    판정 기록을 지우지 않는 것이 이 표의 존재 이유다. 그리고 그 이력 행이
    재판정 때문인지 병합 때문인지 구분되게 merged_from을 남긴다 —
    구분되지 않으면 캘리브레이션이 표본을 어떻게 셀지 정할 수 없다.
    """
    from app.collectors.game_match import merge_duplicate_games

    keep, dup = await _dup_pair(db_pool)
    await record_analysis(db_pool, _analysis(keep, p_home=0.61))
    await record_analysis(db_pool, _analysis(dup, p_home=0.66))
    assert await db_pool.fetchval("SELECT count(*) FROM pick_ledger") == 2
    await merge_duplicate_games(db_pool)
    rows = await db_pool.fetch(
        "SELECT p_home, is_final, merged_from FROM pick_ledger ORDER BY p_home")
    assert len(rows) == 2, "충돌 시 한쪽을 지웠다 — 보존해야 한다"
    finals = [r for r in rows if r["is_final"]]
    assert len(finals) == 1, "최종 행은 하나여야 한다"
    demoted = [r for r in rows if not r["is_final"]]
    assert demoted and demoted[0]["merged_from"] == dup, \
        "강등된 이력 행에 병합 출처가 없다 — 재판정과 구분되지 않는다"


def test_every_pick_ledger_column_is_also_added_by_alter():
    """🔴 이미 만들어진 표에는 CREATE TABLE 의 컬럼 추가가 반영되지 않는다.

    실사고 2026-08-31: merged_from 을 CREATE TABLE 안에만 넣고 배포했더니
    운영에서 `column "merged_from" does not exist` 가 났다. 스키마 적용은
    "완료"라고 로그를 남기므로 **성공한 것처럼 보였다.**

    이 저장소의 관례는 games·predictions 처럼 새 컬럼을 ALTER 로 따로 적는
    것이다. 나중에 붙인 컬럼이 그 관례를 지켰는지 파일로 확인한다.
    """
    from pathlib import Path

    sql = Path("db/schema.sql").read_text(encoding="utf-8")
    body = sql[sql.index("CREATE TABLE IF NOT EXISTS pick_ledger"):]
    body = body[:body.index(");")]
    declared = {ln.strip().split()[0] for ln in body.splitlines()[1:]
                if ln.strip() and not ln.strip().startswith("--")}
    # 표 생성 이후에 붙은 컬럼(초기 스키마에 없던 것)은 ALTER 가 있어야 한다
    for col in ("merged_from", "trial"):
        assert col in declared, f"{col}이 CREATE TABLE 에 없다"
        assert f"ALTER TABLE pick_ledger ADD COLUMN IF NOT EXISTS {col}" in sql, \
            f"{col}에 ALTER 가 없다 — 기존 운영 DB에는 생기지 않는다"


async def test_calibration_splits_by_league_not_by_trial(db_pool):
    """리그 축이 야구/축구를 가른다 — 시범 플래그가 하던 역할을 대신한다.

    2026-08-31 축구 실전 전환: trial 구분을 쓰지 않고 league 로 집계한다.
    """
    kbo = await _game(db_pool, 40, status="final", hs=6, aws=1)
    await record_analysis(db_pool, _analysis(kbo))
    epl = await db_pool.fetchval(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status,"
        " home_score,away_score) VALUES ('soccer','EPL','e1',"
        " now() - interval '3 hours','Arsenal','Chelsea','final',2,1)"
        " RETURNING id")
    a = _analysis(epl)
    a["sport"] = "soccer"
    a["games"][0].update({"sport": "soccer", "league": "EPL",
                          "home": "Arsenal", "away": "Chelsea"})
    await record_analysis(db_pool, a)
    await grade_pending(db_pool)
    data = await summarize(db_pool, days=7)
    labels = {g["label"] for g in data["leagues"]}
    assert {"KBO", "EPL"} <= labels, f"리그별로 갈리지 않았다: {labels}"
    assert await db_pool.fetchval(
        "SELECT count(*) FROM pick_ledger WHERE trial") == 0, \
        "신규 기록에 trial 이 세워졌다"


# ═══════════════ 시장을 판정 원장에 새긴다 (2026-09-07)
#
# 🔴 실측: 원장 621행 중 `market_prob` 0 · `divergence_pp` 0 · `odds` 0.
#    컬럼은 처음부터 있었는데 INSERT 가 안 썼다. 그래서 "시장 동의 게이트"가
#    실제로 도움이 되는지 **한 번도 잴 수 없었다.**

def test_시장값이_행에_실린다():
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 1, "matchup": {"p_home": 0.57, "우세": "home", "확신도": "중"},
          "p_claude": 0.57, "p_market_send": 0.64}
    row = _row_from_game(jg, {"sport": "mlb", "date": "2026-09-07"},
                         {1: {"odds": 1.85, "recommended": False}})
    assert row["market_prob"] == pytest.approx(0.64)
    assert row["odds"] == pytest.approx(1.85)
    # 부호는 `market_baseline_ledger.divergence` 와 같은 방향(우리 − 시장)
    assert row["divergence_pp"] == pytest.approx(-7.0)


def test_시장이_없으면_NULL_이고_기록을_막지_않는다():
    """⚠️ 수집 실패가 판정 기록을 막으면 원장이 통째로 빈다."""
    from app.engine.pick_ledger import _row_from_game

    row = _row_from_game({"game_id": 1, "p_claude": 0.57,
                          "matchup": {"p_home": 0.57, "우세": "home"}},
                         {"sport": "mlb", "date": "2026-09-07"}, {})
    assert row is not None and row["p_home"] == pytest.approx(0.57)
    assert row["market_prob"] is None and row["divergence_pp"] is None
    assert row["odds"] is None


def test_시장값은_같은_판정의_정의에_들어가지_않는다():
    """🔴 **가장 중요한 계약.** 시장은 스냅샷마다 흔들린다. 이걸 `_SIG_FIELDS`
    에 넣으면 배당이 갱신될 때마다 재판정 이력 행이 새로 생기고, 원장이
    한 경기당 수십 행으로 불어난다.

    ⚠️ 오늘 확신도를 잘못 읽은 원인이 바로 그 중복이었다 — 재판정 4.3배로
       부풀린 598행을 독립 표본처럼 세서 "확신도 하 62.5%" 라고 보고했다.
       접으면 134경기 · 58.8% 다.
    """
    from app.engine.pick_ledger import _SIG_FIELDS

    for f in ("market_prob", "divergence_pp", "odds"):
        assert f not in _SIG_FIELDS, f"{f} 가 재판정을 유발한다"


def test_판정_불변이면_시장_칸만_채운다():
    """판정이 배당보다 먼저 끝난 경기 — 그냥 넘기면 영영 NULL 로 남는다."""
    import inspect

    from app.engine import pick_ledger as pl

    src = inspect.getsource(pl.record_analysis)
    i = src.index('stats["unchanged"]')
    assert "_fill_market" in src[:i], "unchanged 경로에서 시장을 안 채운다"
    # 판정 칸은 건드리지 않는다
    fill = inspect.getsource(pl._fill_market)
    for banned in ("p_home", "favored", "confidence", "gate_result", "model"):
        assert f"{banned} " not in fill, f"시장 갱신이 {banned} 을 건드린다"
    assert "COALESCE" in fill, "한 번 새긴 시장값을 덮어쓰면 사후확신이 된다"


def test_배당_격리는_그대로다():
    """⚠️ 시장을 원장에 넣는 것과 **판정에 넣는 것**은 다르다.
    이 테스트가 그 선을 지킨다 — `market_prob` 은 판정 뒤 기록일 뿐이다."""
    from pathlib import Path

    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    for banned in ("p_market_send", "market_prob", "divergence_pp",
                   "odds_snapshots", "market_baseline"):
        assert banned not in src, f"판정 모듈이 {banned} 를 본다 — 배당 격리 위반"


def test_백필은_apply_없이는_쓰지_않는다():
    """1회성 도구가 기본값으로 운영 원장을 바꾸면 안 된다."""
    from pathlib import Path

    src = Path("tools/backfill_market.py").read_text(encoding="utf-8")
    assert 'add_argument("--apply", action="store_true"' in src
    assert "if args.apply:" in src
    assert "COALESCE(market_prob" in src, "덮어쓰기 금지"
    # 판정 칸을 쓰지 않는다
    assert "SET p_home" not in src and "gate_result =" not in src


# ═══════════════ 확신도 후보 — 재기만 한다 (2026-09-07)
#
# 🔴 교체를 승인받았으나 **배포 전 관문에서 떨어졌다.** 재료-결측 방식은
#    57경기 전부 `상` 이 나와 변별력 0 이었고, 넣으면 거부권이 11→0 건이 된다.
#    시장식은 변별력이 있지만 검증값이 CLOSE(백필)라 게이트가 보는 SEND 가
#    아니다. → 후보를 나란히 새기고 2주 뒤 SEND 로 고른다.

def test_후보는_게이트에_닿지_않는다():
    """🔴 **가장 중요한 계약.** 게이트는 자기신고만 읽는다."""
    import inspect

    from app.engine import pick_ledger as pl

    src = inspect.getsource(pl.gate_result_of)
    for banned in ("confidence_probe", "confidence.", "by_market",
                   "by_materials", "probe("):
        assert banned not in src, f"게이트가 후보를 읽는다: {banned}"
    assert "judge_confidence" in src


def test_후보는_재판정을_유발하지_않는다():
    from app.engine.pick_ledger import _SIG_FIELDS

    assert "confidence_probe" not in _SIG_FIELDS


def test_후보_네_종이_모두_새겨진다():
    import json

    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 1, "p_claude": 0.57, "p_market_send": 0.64,
          "matchup": {"p_home": 0.57, "우세": "home", "확신도": "중"}}
    row = _row_from_game(jg, {"sport": "mlb", "date": "2026-09-07"}, {})
    got = json.loads(row["confidence_probe"])
    assert got["자기신고"] == "중"
    assert got["시장괴리pp"] == pytest.approx(-7.0)
    assert got["시장동의"] is True          # 둘 다 홈
    assert got["A"] == "중" and got["B"] == "중" and got["C"] == "중"
    assert got["기준"] == "send", "CLOSE 백필과 섞이면 안 된다"


def test_시장이_없으면_시장식_후보는_None():
    """🔴 수집 실패가 거부권이 되면 안 된다 — 실측: 시장 미수집 34경기가
    오히려 61.8% 로 가장 잘 맞았다. `None` 을 `하` 로 읽으면 그 34경기를
    통째로 버린다."""
    import json

    from app.engine.pick_ledger import _row_from_game

    row = _row_from_game({"game_id": 1, "p_claude": 0.57,
                          "matchup": {"p_home": 0.57, "우세": "home"}},
                         {"sport": "mlb", "date": "2026-09-07"}, {})
    got = json.loads(row["confidence_probe"])
    assert got["A"] is None and got["B"] is None and got["C"] is None
    assert got["M"] is not None, "재료식은 시장 없이도 나온다"


@pytest.mark.parametrize("div,same,want", [
    # A — 거리만 본다
    (20.0, False, ("하", "하", "하")),
    (8.0, True, ("중", "중", "중")),
    (3.0, True, ("상", "상", "상")),
    # 방향이 갈릴 때 셋이 갈린다
    (12.0, False, ("중", "하", "하")),
    (3.0, False, ("상", "하", "중")),
])
def test_ABC_가_실제로_다른_규칙이다(div, same, want):
    """세 후보가 같은 답만 내면 비교할 이유가 없다."""
    from app.engine.confidence import by_market

    got = tuple(by_market(div, same, rule=r) for r in ("A", "B", "C"))
    assert got == want


def test_재료식은_변별력이_없다는_사실을_남긴다():
    """⚠️ 실측 57경기 전부 `상`. 지우면 "안 되더라"도 사라진다."""
    from app.engine.confidence import by_materials

    assert by_materials(0, False) == "상"
    assert by_materials(1, False) == "상"
    assert by_materials(2, False) == "중"
    assert by_materials(4, False) == "하"
    assert by_materials(0, True) == "중", "분기점 미해결이면 한 단계 내린다"


def test_후보_계산이_실패해도_원장_기록을_막지_않는다():
    """⚠️ 측정 장치가 본체를 죽이면 안 된다."""
    from app.engine.confidence import probe

    assert probe(None) == {}          # 예외가 밖으로 안 나온다


# ── [LED-1 2026-09-10] 한 경기에 최종 판정이 둘 있었다 ────────────────────
#   🔴 실측(운영 DB): `is_final` 209행 · 고유 경기 199 — **잉여 10건.**
#      원인은 조회 키가 `(game_id, date)` 였다는 것이다. 같은 경기가 다른
#      슬레이트 날짜로 한 번 더 들어오면 기존 행을 **못 찾고 새로 만든다.**
#      유니크 인덱스도 `(game_id, date)` 라 막지 못했다.
#
#      game=1853 Athletics@Texas (실제 8-5 홈승)
#        date=2026-09-01  p=0.60 home  hit=True    ← 올바른 슬레이트 날짜
#        date=2026-09-02  p=0.46 away  hit=False   ← 잉여. 방향이 반대다
#      한 경기에 상반된 "최종" 두 개가 남아, 어느 행을 읽느냐로 적중률이 바뀐다.
#      실제로 10건 전부 날짜가 달랐다.
#
#   ⚠️ 더블헤더는 game_id 가 따로 발급된다 — 한 경기 = 한 최종 판정이 맞다.

def test_final_lookup_is_keyed_on_game_only():
    """조회가 날짜를 함께 보면 같은 경기가 두 번 최종이 된다."""
    import pathlib

    import re

    src = pathlib.Path("app/engine/pick_ledger.py").read_text()
    # 🔴 **문장 단위로** 본다. 줄 단위로 보면 같은 파일의 다른 테이블
    #    (odds_snapshots 등) 조회가 걸려 오탐이 난다 — 규칙은 "pick_ledger 의
    #    최종 판정 조회"에만 해당한다.
    stmts = [s for s in re.split(r"\n\s*\n|\"\"\"", src)
             if "WHERE game_id" in s and "pick_ledger" in s]
    sql = [ln for s in stmts for ln in s.splitlines()
           if "WHERE game_id" in ln and not ln.lstrip().startswith("#")]
    assert sql, "최종 판정 조회문을 못 찾았다"
    for ln in sql:
        assert "is_final" in ln, ln
        assert "date" not in ln, f"조회가 아직 날짜로 갈린다: {ln.strip()!r}"


def test_schema_unique_index_is_game_only():
    """스키마도 같이 좁혀야 한다 — 코드만 고치면 과거 중복이 되살아난다.

    🔴 이 계약이 막는 것은 **날짜로 갈리는 것**이다. 종전에는 `(game_id, date)`
       였고, 그래서 같은 경기가 날짜별로 여러 최종 행을 가졌다.

    🔴 [LDG-1 2026-09-19] 인덱스가 `(game_id, judge_by)` 로 **넓어졌다.**
       사람이 건 픽(`fable_chat`·`user_mode_b`)을 봇 판정과 같은 경기에 나란히
       두어야 하기 때문이다(지시문 7-2 · docs/FORKS.md F-19). 날짜는 여전히
       들어가지 않으므로 이 계약의 원래 취지는 그대로다.
    """
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text()
    i = sql.index("DROP INDEX IF EXISTS idx_pick_ledger_final")
    body = sql[i:i + 260]
    assert "(game_id, judge_by)" in body, \
        f"유니크 인덱스가 판정자를 보지 않는다:\n{body[:200]}"
    assert " date" not in body.split("WHERE")[0], \
        f"유니크 인덱스가 아직 날짜를 포함한다:\n{body[:200]}"
