"""[§8-23] Go 크롤러 연동 — Redis를 통해서만 주고받는다.

⚠️ 크롤러는 **Postgres를 직접 건드리지 않는다.** 스키마 결합을 피하고,
   교차검증을 통과한 값만 파이썬이 DB에 반영하게 한다.
⚠️ **크롤러가 없어도 파이프라인은 돈다.** 파이썬 수집기가 같은 소스를 직접 긁는다 —
   크롤러는 그것을 더 자주(10분) 돌려 **변화를 잡는** 역할이다.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors.crawler_feed import (
    STALE_MINUTES,
    is_alive,
    load_changes,
    load_snapshot,
    merge_into_research,
    notable_changes,
)


class FakeRedis:
    def __init__(self, store=None, lists=None):
        self.store = store or {}
        self.lists = lists or {}

    async def get(self, k):
        return self.store.get(k)

    async def lrange(self, k, a, b):
        return self.lists.get(k, [])


@pytest.mark.asyncio
async def test_missing_snapshot_is_not_an_error():
    """크롤러가 아직 안 돌았어도 파이프라인은 계속 간다."""
    assert await load_snapshot(FakeRedis(), "kbo", "2026-08-26") == {}


@pytest.mark.asyncio
async def test_corrupt_snapshot_is_ignored():
    """손상된 캐시가 파이프라인을 죽이면 안 된다."""
    r = FakeRedis({"crawl:kbo:2026-08-26:latest": "{깨진 json"})
    assert await load_snapshot(r, "kbo", "2026-08-26") == {}


@pytest.mark.asyncio
async def test_snapshot_round_trip():
    snap = {"NC Dinos@LG Twins": {"home_pitcher": "임찬규", "away_pitcher": "구창모"}}
    r = FakeRedis({"crawl:kbo:2026-08-26:latest": json.dumps(snap, ensure_ascii=False)})
    assert await load_snapshot(r, "kbo", "2026-08-26") == snap


@pytest.mark.asyncio
async def test_dead_crawler_is_detected():
    """[§8-23] ⚠️ **조용한 정지가 가장 위험하다** — 데이터가 어제 값으로 굳어도 모른다."""
    old = (datetime.now(UTC) - timedelta(minutes=STALE_MINUTES + 10)).isoformat()
    ok, msg = await is_alive(FakeRedis({"crawl:heartbeat": old}))
    assert ok is False and "멈춤" in msg

    ok2, _ = await is_alive(FakeRedis())
    assert ok2 is False                      # 하트비트 자체가 없으면 미실행

    fresh = datetime.now(UTC).isoformat()
    ok3, msg3 = await is_alive(FakeRedis({"crawl:heartbeat": fresh}))
    assert ok3 is True and "정상" in msg3


@pytest.mark.asyncio
async def test_changes_are_read_oldest_first():
    rows = [json.dumps({"game": "A@B", "field": "home_pitcher",
                        "from": "임찬규", "to": "최원태",
                        "at": "2026-08-26T18:20:00+09:00"}, ensure_ascii=False)]
    r = FakeRedis(lists={"crawl:kbo:2026-08-26:changes": rows})
    got = await load_changes(r, "kbo", "2026-08-26")
    assert got[0]["to"] == "최원태"


def test_notable_reports_starter_change_with_time():
    """**언제 바뀌었는지**가 정보다 — 경기 직전 교체는 시장이 늦게 반영한다."""
    out = notable_changes([
        {"game": "NC@LG", "field": "home_pitcher", "from": "임찬규",
         "to": "최원태", "at": "2026-08-26T18:20:00+09:00"},
        {"game": "NC@LG", "field": "stadium", "from": "잠실", "to": "잠실",
         "at": "2026-08-26T18:20:00+09:00"},
    ])
    assert len(out) == 1                     # 구장 변경은 잡음
    assert "18:20" in out[0] and "임찬규 → 최원태" in out[0]


def test_merge_takes_name_only():
    """[§8-23] 크롤러는 **이름만** 준다 — 성적은 공식 소스가 담당한다.

    크롤러의 역할은 '누가 나오나'를 가장 빨리 아는 것이다.
    """
    research = {"home_pitcher": {"name": "임찬규", "era_season": 4.14}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    snap = {"NC Dinos@LG Twins": {"home_pitcher": "최원태", "away_pitcher": "구창모"}}
    filled = merge_into_research(research, jg, snap)
    assert research["home_pitcher"]["name"] == "최원태"
    # ⚠️ 이름이 바뀌면 이전 투수의 ERA는 그 사람 것이 아니다
    assert "era_season" not in research["home_pitcher"]
    assert "home_pitcher.name" in filled


def test_merge_is_noop_when_game_absent():
    research = {"home_pitcher": {"name": "임찬규", "era_season": 4.14}}
    assert merge_into_research(research, {"home": "X", "away": "Y"},
                               {"A@B": {"home_pitcher": "Z"}}) == []
    assert research["home_pitcher"]["era_season"] == 4.14


def test_merge_keeps_stats_when_name_unchanged():
    """같은 투수면 아무것도 건드리지 않는다 — 정상 경기를 망치면 안 된다."""
    research = {"home_pitcher": {"name": "임찬규", "era_season": 4.14}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    snap = {"NC Dinos@LG Twins": {"home_pitcher": "임찬규"}}
    assert merge_into_research(research, jg, snap) == []
    assert research["home_pitcher"]["era_season"] == 4.14
