"""FOT-5 — 선발 이력 + 시즌 소급 적재 (사용자 지시).

🔴 실측 2026-09-14: FotMob 은 과거 날짜도 준다(`lineupType="standard"`,
   선발 11 + 벤치). 그래서 개막~오늘 소급 적재가 가능하다.
🔴 리그 **이름**으로 거르면 안 된다 — "Serie A" 는 이탈리아와 에콰도르가
   같이 쓴다(실측: Delfín vs Técnico Universitario 가 섞였다).
"""
import pytest

from app.collectors import fotmob as FM


class _Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *args):
        self.rows.append(args)
        return "INSERT 1"


def _lineup(lt="confirmed"):
    return {"match_id": 5749678, "lineup_type": lt,
            "home": {"team_id": 9804,
                     "starters": [{"id": 1, "name": "Perri"},
                                  {"id": 0, "name": "id 없는 선수"},
                                  {"id": None, "name": "id 없는 선수2"}],
                     "bench": [{"id": 5, "name": "Ngonge"}]},
            "away": {"team_id": 8686, "starters": [{"id": 3, "name": "Svilar"}],
                     "bench": []}}


@pytest.mark.asyncio
async def test_선발과_벤치를_남기고_id_없는_행은_건너뛴다():
    """🔴 0을 키로 쓰면 서로 다른 선수가 한 사람이 된다."""
    pool = _Pool()

    n = await FM.save_lineup_history(pool, _lineup())

    assert n == 3, "Perri·Ngonge·Svilar 만 남는다"
    ids = [a[2] for a in pool.rows]
    assert 0 not in ids and None not in ids
    started = {a[2]: a[4] for a in pool.rows}
    assert started[1] is True and started[5] is False


@pytest.mark.asyncio
async def test_lineup_type_을_그대로_남긴다():
    """confirmed(T-60 이후)와 standard(경기 후)를 **따로** 세야 정직하다."""
    pool = _Pool()

    await FM.save_lineup_history(pool, _lineup("standard"))

    assert {a[6] for a in pool.rows} == {"standard"}


@pytest.mark.asyncio
async def test_소급_적재는_국가_코드로_거른다(monkeypatch):
    seen = []

    async def _slate(d):
        return [{"id": 1, "ccode": "ITA", "league": "Serie A",
                 "home": "Torino", "away": "Roma"},
                {"id": 2, "ccode": "ECU", "league": "Serie A",
                 "home": "Delfín", "away": "Técnico Universitario"}]

    async def _lu(mid):
        seen.append(mid)
        return _lineup("standard")

    monkeypatch.setattr(FM, "slate", _slate)
    monkeypatch.setattr(FM, "match_lineup", _lu)

    # 🔴 [FOT-STOP 2026-09-21 사용자 결정] 소급 루프는 **관문**을 지난다.
    #    이 시험의 대상은 **국가 코드 필터**이지 관문이 아니므로 열고 시험한다.
    #    ⚠️ 관문 자체는 `tests/test_fot_stop.py` 가 따로 잠근다.
    out = await FM.backfill(_Pool(), ["20260906"], bulk_allowed=True)

    assert seen == [1], "에콰도르 세리에A 를 열면 안 된다"
    assert out == {"ITA Serie A": 1}
    assert "ITA" in FM.BACKFILL_CCODES and "ECU" not in FM.BACKFILL_CCODES


def test_스키마에_이력_표가_있다():
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS lineup_history" in sql
    for col in ("player_id", "player_name", "started", "minutes",
                "lineup_type", "kickoff_utc", "team_id"):
        assert col in sql.split("lineup_history")[1][:900], col


# ── LH-1: 리그·킥오프 칸

@pytest.mark.asyncio
async def test_적재할_때_리그와_킥오프를_함께_남긴다():
    """🔴 [LH-2] **타입까지 단언한다.** 가짜 풀은 값만 받아 적어서 타입을
    못 잡는다 — 그래서 `$n::date` 에 문자열을 넘긴 결함이 하루에 두 번 났다
    (ODP-2 아침 · LH-1 밤, 18,507행 갱신 전부 실패).
    """
    from datetime import date, datetime

    pool = _Pool()

    await FM.save_lineup_history(pool, _lineup("standard"),
                                 kickoff_utc="2026-09-14T16:30:00.000Z",
                                 league="Serie A", ccode="ITA")

    args = pool.rows[0]
    assert args[8] == "Serie A" and args[9] == "ITA"
    assert isinstance(args[7], datetime), "TIMESTAMPTZ 에 문자열을 넘기면 안 된다"
    assert args[10] == date(2026, 9, 14), "$::date 는 date 객체만 받는다"
    assert not isinstance(args[10], str)


@pytest.mark.asyncio
async def test_역매핑은_날짜별_목록만_쓴다(monkeypatch):
    """🔴 사용자 지시: 경기 상세 재호출 금지. 목록에 ccode·league·utc 가 있다."""
    detail_calls = []

    async def _slate(d):
        return [{"id": 5749678, "ccode": "ITA", "league": "Serie A",
                 "home": "Torino", "away": "Roma",
                 "utc": "2026-09-14T16:30:00.000Z"}]

    async def _detail(mid):
        detail_calls.append(mid)
        return {}

    monkeypatch.setattr(FM, "slate", _slate)
    monkeypatch.setattr(FM, "match_lineup", _detail)

    class _P:
        def __init__(self):
            self.args = []

        async def execute(self, sql, *a):
            self.args.append(a)
            return "UPDATE 42"

    p = _P()
    out = await FM.backfill_meta(p, ["20260914"])

    assert out == {"20260914": 42}
    assert not detail_calls, "경기 상세를 부르면 안 된다"
    from datetime import date

    assert p.args[0] == (5749678, "Serie A", "ITA", date(2026, 9, 14))
    assert not isinstance(p.args[0][3], str), "역매핑도 date 객체여야 한다"


def test_스키마에_리그_칸이_있다():
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text()
    for col in ("league", "ccode", "kickoff_date"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in sql, col
