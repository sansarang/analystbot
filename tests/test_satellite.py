"""[위성 Phase1] 계약 테스트 — 태어나는 날 함께.

위성은 **수집기**다. DB에 없는 경기 정보를 미리 긁어 캐시에 쌓고, 딥서치가
그 캐시를 읽는다. 이 테스트가 잠그는 것:

- 어댑터 산출 dict 가 `_inject_articles`(deepsearch.py) 가 읽는 키를 전부 갖는다
  (모양 계약 — 하나라도 빠지면 판정 경로에서 조용히 렌더가 깨진다).
- transactions 는 **그 경기 두 팀** 것만 남는다 (지금 RSS 의 76% 오라벨을 반복하지
  않는다 — 마이너 팀·상대 밖 팀은 버린다).
- 재료가 없으면 빈 리스트로 안전하게 끝난다 (조용한 0 금지 — 크래시하지 않는다).
- 캐시 왕복: `gather` 가 쓴 것을 `read_cache` 가 그대로 돌려준다.
"""
from __future__ import annotations

import pytest

from app.collectors import satellite


# _inject_articles(deepsearch.py) 가 실제로 읽는 키. 원본이 바뀌면 여기서 깨져야 한다.
_SHAPE_KEYS = ("title", "source", "age_h", "team", "body")


_SAMPLE_TX = {
    "transactions": [
        {"id": 1, "person": {"id": 11, "fullName": "Kyle Karros"},
         "typeCode": "SC", "typeDesc": "Status Change",
         "description": "Colorado Rockies activated 3B Kyle Karros from the 7-day injured list.",
         "date": "2026-09-07", "fromTeam": None,
         "toTeam": {"id": 115, "name": "Colorado Rockies"}},
        {"id": 2, "person": {"id": 22, "fullName": "Someone Else"},
         "typeCode": "REL", "typeDesc": "Released",
         "description": "ACL Brewers released OF Someone Else.",
         "date": "2026-09-07", "fromTeam": None,
         "toTeam": {"id": 406, "name": "ACL Brewers"}},
        {"id": 3, "person": {"id": 33, "fullName": "Trade Guy"},
         "typeCode": "TR", "typeDesc": "Trade",
         "description": "San Francisco Giants traded RHP Trade Guy to Colorado Rockies.",
         "date": "2026-09-08",
         "fromTeam": {"id": 137, "name": "San Francisco Giants"},
         "toTeam": {"id": 115, "name": "Colorado Rockies"}},
    ]
}


def test_transactions_filtered_to_game_teams():
    """경기가 SF@COL 이면 COL·SF 관련 트랜잭션만 남고 ACL Brewers 는 버린다."""
    teams = {"Colorado Rockies", "San Francisco Giants"}
    arts = satellite.transactions_to_articles(_SAMPLE_TX["transactions"], teams)
    descs = [a["title"] for a in arts]
    assert any("Kyle Karros" in d for d in descs)          # COL 활성화
    assert any("traded RHP Trade Guy" in d for d in descs)  # SF↔COL 트레이드
    assert not any("ACL Brewers" in d for d in descs)       # 마이너 팀 — 버린다
    assert len(arts) == 2


def test_article_shape_matches_inject_contract():
    """산출 dict 는 _inject_articles 가 읽는 키를 전부 가진다."""
    teams = {"Colorado Rockies", "San Francisco Giants"}
    arts = satellite.transactions_to_articles(_SAMPLE_TX["transactions"], teams)
    assert arts
    for a in arts:
        for k in _SHAPE_KEYS:
            assert k in a, f"기사 dict 에 {k} 키가 없다 — 판정 경로에서 렌더가 깨진다"
        assert a["body"], "본문이 비면 RSS 의 0% 본문 문제를 반복하는 것이다"
        assert a["team"] in teams


def test_empty_transactions_safe():
    """재료가 없으면 빈 리스트 — 크래시하지 않는다."""
    assert satellite.transactions_to_articles([], {"Colorado Rockies"}) == []
    assert satellite.transactions_to_articles(
        _SAMPLE_TX["transactions"], set()) == []


class _MemRedis:
    def __init__(self):
        self.store: dict = {}

    async def set(self, k, v, nx=False, ex=None):
        self.store[k] = v
        return True

    async def get(self, k):
        return self.store.get(k)

    async def expire(self, k, sec):
        return True


class _FakeMLB:
    def __init__(self, payload):
        self._payload = payload

    async def fetch_transactions(self, start, end):
        return self._payload


@pytest.mark.asyncio
async def test_gather_writes_and_read_cache_roundtrips():
    """gather 가 캐시에 쓰고, read_cache 가 그대로 돌려준다."""
    r = _MemRedis()
    jg = {"sport": "mlb", "game_id": 999,
          "home": "Colorado Rockies", "away": "San Francisco Giants"}
    n = await satellite.gather(jg, r, client=_FakeMLB(_SAMPLE_TX))
    assert n == 2
    got = await satellite.read_cache(r, "mlb", 999)
    assert len(got) == 2
    assert all(k in got[0] for k in _SHAPE_KEYS)


@pytest.mark.asyncio
async def test_read_cache_empty_when_absent():
    """캐시가 없으면 빈 리스트 — 딥서치는 news_rss 로 폴백한다(회귀 없음)."""
    r = _MemRedis()
    assert await satellite.read_cache(r, "mlb", 12345) == []


@pytest.mark.asyncio
async def test_gather_empty_still_writes_marker():
    """재료 0건이어도 gather 는 크래시하지 않고 0을 돌려준다(조용한 0 금지)."""
    r = _MemRedis()
    jg = {"sport": "mlb", "game_id": 7, "home": "X Team", "away": "Y Team"}
    n = await satellite.gather(jg, r, client=_FakeMLB({"transactions": []}))
    assert n == 0


# ── 증분 1b: run_satellite (대상 경기 선정 + 컷오프) ──────────────────────

from datetime import datetime, timedelta, timezone


class _FakePool:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


def _row(gid, sport, home, away, mins_ahead, now):
    return {"id": gid, "sport": sport, "home": home, "away": away,
            "starts_at": now + timedelta(minutes=mins_ahead)}


@pytest.mark.asyncio
async def test_run_satellite_gathers_due_games_and_skips_cutoff():
    """컷오프(T-N) 안에 든 경기는 더 긁지 않는다 — 위성이 정지한다."""
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    rows = [
        _row(1, "mlb", "Colorado Rockies", "San Francisco Giants", 300, now),  # 5h 전 → 수집
        _row(2, "mlb", "X Team", "Y Team", 5, now),                            # T-5분 → 정지
    ]
    r = _MemRedis()
    out = await satellite.run_satellite(
        _FakePool(rows), r, sports=["mlb"], now=now,
        cutoff_min=10, client=_FakeMLB(_SAMPLE_TX))
    assert out["games"] == 1                    # 컷오프 안 경기는 셈에서 빠진다
    assert await satellite.read_cache(r, "mlb", 1)   # 대상 경기는 캐시가 찼다
    assert await satellite.read_cache(r, "mlb", 2) == []  # 정지 경기는 안 긁었다


@pytest.mark.asyncio
async def test_run_satellite_no_adapter_sport_noop():
    """어댑터 없는 종목(kbo)은 지금은 건너뛴다 — 크래시하지 않는다."""
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    rows = [_row(9, "kbo", "한화 이글스", "LG 트윈스", 200, now)]
    r = _MemRedis()
    out = await satellite.run_satellite(
        _FakePool(rows), r, sports=["kbo"], now=now, client=_FakeMLB(_SAMPLE_TX))
    assert out["gathered"] == 0
