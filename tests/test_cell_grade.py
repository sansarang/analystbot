"""[#63] 칸별 사후 채점 — 기록·집계 회로.

⚠️ 이 테스트가 지키는 것은 "▲를 준 팀이 이겼는가"의 **부호 방향**이다.
   여기가 뒤집히면 2주 뒤 나오는 칸별 적중률이 통째로 거짓말이 된다.
"""
import asyncio

import pytest

from app.engine import cell_grade as CG


# ------------------------------------------------------------- 기록 (DB 없이)

class _FakePool:
    def __init__(self):
        self.rows = []

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                class _Con:
                    async def executemany(self, sql, rows):
                        pool.rows.extend(rows)
                return _Con()

            async def __aexit__(self, *a):
                return False
        return _Ctx()


CARD = {"bullpen": {"facts": ["직전 9명 투입", "구원 37타자"]},
        "starter": {"facts": ["ERA 4.0"]}}


def test_records_symbol_reason_and_fact_count():
    pool = _FakePool()
    v = {"bullpen": {"symbol": "▼", "reason": "직전 9명 투입", "provider": "groq/x"},
         "starter": {"symbol": "▲", "reason": "ERA 4.0", "provider": "groq/x"}}
    n = asyncio.run(CG.record_verdicts(pool, 7, "home", "KIA", v, CARD))
    assert n == 2
    by_cell = {r[3]: r for r in pool.rows}
    assert by_cell["bullpen"][4] == "▼"
    assert by_cell["bullpen"][6] == 2, "사실 개수가 붙지 않았다"
    assert by_cell["starter"][6] == 1
    assert by_cell["starter"][7] == "groq/x"


def test_dropped_cells_are_never_recorded():
    """🔴 폐기된 칸을 채점하면 안 된다 — 판정하지 않은 것의 적중률은 없다."""
    pool = _FakePool()
    n = asyncio.run(CG.record_verdicts(pool, 7, "home", "KIA", {}, CARD))
    assert n == 0 and pool.rows == []


def test_garbage_symbol_is_rejected():
    pool = _FakePool()
    v = {"bullpen": {"symbol": "위", "reason": "직전 9명 투입"}}
    assert asyncio.run(CG.record_verdicts(pool, 7, "home", "KIA", v, CARD)) == 0


def test_bad_side_is_rejected():
    """side가 틀리면 승패 대조가 통째로 뒤집힌다 — 조용히 넘기면 안 된다."""
    pool = _FakePool()
    v = {"bullpen": {"symbol": "▲", "reason": "x"}}
    assert asyncio.run(CG.record_verdicts(pool, 7, "middle", "KIA", v, CARD)) == 0


def test_no_pool_is_a_noop_not_a_crash():
    """키·DB 없이도 크래시하지 않는다(절대 규칙 3)."""
    v = {"bullpen": {"symbol": "▲", "reason": "x"}}
    assert asyncio.run(CG.record_verdicts(None, 7, "home", "KIA", v, CARD)) == 0


# ------------------------------------------------------------- 집계 표기

def test_thin_sample_hides_the_number():
    """🔴 얇은 표본의 적중률을 보여주면 그 숫자가 근거로 쓰인다."""
    out = CG.format_ledger([{"sport": "kbo", "cell": "bullpen", "decided": 4,
                             "hits": 4, "pushes": 0, "neutrals": 0,
                             "hit_rate": 1.0, "verdict": "표본 부족"}])
    assert "100" not in out and "표본 부족" in out


def test_sufficient_sample_shows_the_number():
    out = CG.format_ledger([{"sport": "kbo", "cell": "bullpen", "decided": 40,
                             "hits": 24, "pushes": 0, "neutrals": 0,
                             "hit_rate": 0.6, "verdict": "판단 가능"}])
    assert "24/40" in out and "60.0%" in out


# ------------------------------------------------------------- 뷰 (실 DB)

DDL_CASES = [
    # (side, symbol, home_score, away_score, 기대 결과)
    ("home", "▲", 5, 3, "hit"),    # ▲ 준 홈이 이김
    ("home", "▲", 3, 5, "miss"),
    ("home", "▼", 3, 5, "hit"),    # ▼ 준 홈이 짐
    ("away", "▲", 3, 5, "hit"),    # ▲ 준 원정이 이김
    ("away", "▼", 3, 5, "miss"),
    ("home", "▲", 4, 4, "push"),   # 무승부
]


@pytest.mark.asyncio
async def test_cell_ledger_view_scores_direction_correctly():
    """실 DB에서 부호 방향을 검증한다. DB가 없으면 건너뛴다."""
    asyncpg = pytest.importorskip("asyncpg")
    from app.config import get_settings
    try:
        con = await asyncpg.connect(get_settings().database_url)
    except Exception:
        pytest.skip("DB 없음")
    try:
        await con.execute("BEGIN")
        for i, (side, sym, hs, aws, want) in enumerate(DDL_CASES):
            gid = await con.fetchval("""
                INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                                   status, home_score, away_score)
                VALUES ('celltest','T',$1, now(),'H','A','final',$2,$3)
                RETURNING id""", f"celltest:{i}", hs, aws)
            await con.execute("""
                INSERT INTO cell_verdicts (game_id, side, team, cell, symbol)
                VALUES ($1,$2,'T','bullpen',$3)""", gid, side, sym)
        rows = await con.fetch(
            "SELECT decided, hits, pushes FROM cell_ledger WHERE sport='celltest'")
        assert rows, "뷰가 아무것도 돌려주지 않았다"
        r = rows[0]
        want_hits = sum(1 for c in DDL_CASES if c[4] == "hit")
        want_dec = sum(1 for c in DDL_CASES if c[4] in ("hit", "miss"))
        assert r["decided"] == want_dec, f"채점 대상 수 불일치: {dict(r)}"
        assert r["hits"] == want_hits, f"🔴 부호 방향이 뒤집혔다: {dict(r)}"
        assert r["pushes"] == 1
    finally:
        await con.execute("ROLLBACK")
        await con.close()
