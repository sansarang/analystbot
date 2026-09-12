"""SOC-9 — Flashscore 라인업을 `lineups` 테이블에 저장한다.

사용자 지시 2026-09-13: "lineups 테이블에 저장해라"

🔴 **실측 2026-09-12 23:52 (운영).** 라인업이 캐시에만 있고 DB에는 없었다:
     games 칼럼   lineup_status · lineup_confirmed_at   ← 상태만, 명단 없음
     lineups 테이블 804행 · 전부 야구(source=statsapi 등)
   그리고 그 실행은 12경기 전부 "라인업 아직 미발표"였다 — 킥오프 68분 전이라
   피드에 아직 없었다. 배선은 돌았지만 **끝까지 가본 적이 없다.**

⚠️ 새 테이블·새 컬럼을 만들지 않는다. 야구가 쓰는 `save_lineup` 을 그대로 쓴다.
   `batting_order`(jsonb) 에 선발 11명, `starter` 에 포메이션을 넣는다.
"""
import pytest

from app.collectors import flashscore as FS
from app.collectors import satellite as SAT
from app.collectors import satellite_soccer as SOC

_LU = ("LB÷x¬LC÷1¬~LD÷1-4-2-3-1¬LP÷a1¬LI÷Alisson¬LJ÷1¬"
       "~LP÷a2¬LI÷Van Dijk V.¬LJ÷4¬"
       "¬LC÷2¬~LD÷1-5-4-1¬LP÷b1¬LI÷Leno B.¬LJ÷17¬"
       "~LP÷b2¬LI÷Bassey C.¬LJ÷3¬")


class _Pool:
    def __init__(self): self.rows = []
    async def execute(self, sql, *a):
        self.rows.append((sql, a))


def _jg():
    from datetime import datetime, timezone
    return {"sport": "soccer", "game_id": 77, "league": "EPL",
            "home": "Liverpool FC", "away": "Fulham FC",
            "starts_at": datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc)}


@pytest.fixture
def _fs(monkeypatch):
    FS.cache_clear()

    async def _fx(today):
        return [{"id": "M1", "home": "liverpool", "away": "fulham",
                 "ts": int(_jg()["starts_at"].timestamp())}]

    async def _lu(mid):
        return FS.parse_lineup(_LU)

    monkeypatch.setattr(FS, "fixtures_for", _fx)
    monkeypatch.setattr(FS, "lineup_for", _lu)


@pytest.mark.asyncio
async def test_선발을_lineups_테이블에_넣는다(_fs):
    """🔴 사용자 지시. 새 테이블을 만들지 않고 야구가 쓰는 자리에 넣는다."""
    pool = _Pool()
    out = await SOC._fs_lineups(_jg(), "2026-09-13", pool)
    assert out, "기사가 없다"
    assert len(pool.rows) == 2, pool.rows          # 홈·원정 각 1행
    sql, args = pool.rows[0]
    assert "INSERT INTO lineups" in sql, sql
    gid, side, status, source = args[0], args[1], args[2], args[3]
    assert gid == 77 and side in ("home", "away")
    assert source == "flashscore", source
    assert "Alisson" in args[5], args[5]            # batting_order jsonb
    assert args[4] == "1-4-2-3-1", args[4]          # starter 자리 = 포메이션


@pytest.mark.asyncio
async def test_pool이_없어도_기사는_나온다(_fs):
    """⚠️ 반대 위험 — DB가 없다고 재료까지 잃으면 안 된다."""
    out = await SOC._fs_lineups(_jg(), "2026-09-13", None)
    assert len(out) == 2, out


@pytest.mark.asyncio
async def test_DB가_터져도_기사는_나온다(_fs, caplog):
    import logging

    class _Boom(_Pool):
        async def execute(self, sql, *a):
            raise RuntimeError("db down")

    with caplog.at_level(logging.WARNING):
        out = await SOC._fs_lineups(_jg(), "2026-09-13", _Boom())
    assert len(out) == 2, out
    assert "라인업 저장" in caplog.text, caplog.text


@pytest.mark.asyncio
async def test_라인업이_아직이면_아무것도_안_쓴다(monkeypatch, _fs):
    async def _empty(mid):
        return FS.parse_lineup("")
    monkeypatch.setattr(FS, "lineup_for", _empty)
    pool = _Pool()
    out = await SOC._fs_lineups(_jg(), "2026-09-13", pool)
    assert out == [] and pool.rows == []


def test_위성이_pool을_전달한다():
    """🔴 배선이 없으면 위 계약이 다 통과해도 운영에서는 저장이 0건이다."""
    import inspect

    assert "pool" in inspect.signature(SAT.gather).parameters
    assert "pool=pool" in inspect.getsource(SAT.run_satellite)
    assert "pool=pool" in inspect.getsource(SAT.gather)
