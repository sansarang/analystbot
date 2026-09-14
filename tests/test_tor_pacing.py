"""TOR-1 — DDG 속도 제한을 원장에 남기고 질의 간격을 넓힌다 (사용자 지시).

🔴 실측: 2026-09-12 15초 간격에도 1/3 만 통과 · 2026-09-14 경기당 2질의가
   전부 403. "검색했는데 0건"과 "막혀서 못 했다"는 다른 말이고, 뒤엣것이
   원장에 없으면 다음 사람이 같은 것을 또 잰다.
"""
import pytest

from app.collectors import satellite as SAT
from app.collectors import tor_search
from app.engine import game_trace as GT


class _Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *args):
        self.rows.append(args)
        return "INSERT 1"


def test_질의_간격은_30초다():
    assert tor_search.MIN_GAP_SEC == 30


@pytest.mark.asyncio
async def test_403_을_원장에_tor_rate_limited_로_남긴다(monkeypatch):
    import time

    async def _search(q, **k):
        tor_search.RATE_LIMITED_AT = time.monotonic()
        return []

    monkeypatch.setattr(tor_search, "search", _search)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "satellite_tor_enabled", True, raising=False)
    pool = _Pool()

    await SAT._tor_supplement({"game_id": 7433, "sport": "soccer",
                               "home": "Torino FC", "away": "AS Roma"},
                              [("Torino", "q1")], league="serie_a", pool=pool)

    assert len(pool.rows) == 1
    game_id, sport, _date, stage, summary, ref = pool.rows[0]
    assert game_id == 7433 and sport == "soccer"
    # 🔴 새 stage 를 만들지 않는다 — STAGES 가 원본이고 사건 이름은 ref 에 남는다.
    assert stage == GT.COLLECT and stage in GT.STAGES
    assert "tor_rate_limited" in summary and "tor_rate_limited" in ref


@pytest.mark.asyncio
async def test_403_이_없으면_원장에_안_남긴다(monkeypatch):
    async def _search(q, **k):
        return []

    monkeypatch.setattr(tor_search, "search", _search)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "satellite_tor_enabled", True, raising=False)
    pool = _Pool()

    await SAT._tor_supplement({"game_id": 1, "sport": "soccer",
                               "home": "A", "away": "B"},
                              [("A", "q")], league="serie_a", pool=pool)

    assert pool.rows == []
