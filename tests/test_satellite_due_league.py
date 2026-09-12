"""SOC-5 — 위성이 경기의 **리그를 모른 채** 어댑터를 불렀다. 축구는 늘 빈손.

🔴 **실측 2026-09-12 22:11 (운영 수동 실행).** 대상 12경기 전부:

     [satellite] 축구 (리그 없음) — 이 리그는 위성 소스가 없다
     [satellite] 수집 사이클 — 대상 12경기 · 기사 0건 (soccer)

   원인은 `_DUE_SQL` 이 `league` 를 **뽑지 않고**, `run_satellite` 가 만드는
   `jg` 에도 그 키가 없다는 것이다. 야구 어댑터는 리그를 안 보므로 아무도
   몰랐다. 축구 어댑터는 리그로 소스를 가르므로(`_SOCCER_SOURCE`) **전부
   "소스 없음"으로 떨어졌다.**

   → SAT-S1~S3 로 만든 축구 위성은 `run_satellite` 를 통해서는 **한 번도
     재료를 가져온 적이 없다.** 직접 `gather_soccer` 를 부른 실측만 있었다.
"""

import pytest

from app.collectors import satellite as SAT


class _Rows(list):
    pass


class _Pool:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        self._sql = sql
        return self._rows


class _Row(dict):
    def __getitem__(self, k):  # asyncpg Record 처럼 쓴다
        return dict.__getitem__(self, k)


def _row(**kw):
    from datetime import datetime, timedelta, timezone

    base = {"id": 1, "sport": "soccer", "home": "SS Lazio", "away": "AC Milan",
            "league": "세리에A",
            "starts_at": datetime.now(timezone.utc) + timedelta(hours=3)}
    base.update(kw)
    return _Row(base)


def test_대상_조회가_리그를_뽑는다():
    """🔴 SQL 이 `league` 를 안 뽑으면 아래 계약은 영원히 못 지킨다."""
    assert "league" in SAT._DUE_SQL, SAT._DUE_SQL


@pytest.mark.asyncio
async def test_어댑터가_리그를_받는다(monkeypatch):
    """🔴 실측된 결함 그대로 — 리그가 없으면 축구는 '소스 없음'으로 떨어진다."""
    seen = {}

    async def _gather(jg, redis, client=None, now=None, pool=None):
        seen.update(jg)
        return 3

    monkeypatch.setattr(SAT, "gather", _gather)
    out = await SAT.run_satellite(_Pool([_row()]), None, sports=["soccer"])
    assert seen.get("league") == "세리에A", seen
    assert out == {"games": 1, "gathered": 3}, out


@pytest.mark.asyncio
async def test_야구는_그대로다(monkeypatch):
    """⚠️ 반대 위험 — 야구 어댑터는 리그를 안 본다. 키가 늘어도 동작 불변."""
    seen = {}

    async def _gather(jg, redis, client=None, now=None, pool=None):
        seen.update(jg)
        return 12

    monkeypatch.setattr(SAT, "gather", _gather)
    await SAT.run_satellite(_Pool([_row(sport="kbo", league="KBO")]), None,
                            sports=["kbo"])
    for k in ("sport", "game_id", "home", "away", "starts_at"):
        assert k in seen, (k, seen)
    assert seen["sport"] == "kbo"
