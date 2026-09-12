"""SOC-4 — 일정 소스 하나가 막히면 축구 분석이 통째로 죽었다.

🔴 **실측 2026-09-12 22:03 (운영 수동 실행).** football-data 로 12경기를
   이미 받아 놓고도 파이프라인이 예외로 끝났다:

     ProviderBlockedError: odds: deploy pre-trip: already OUT_OF_USAGE_CREDITS

   배당 API 는 2026-08-27부터 크레딧 소진 상태다. 그 이벤트 조회는
   **2순위 소스**다 — football-data 에 없는 리그(J1·K리그1·덴마크)만 담당한다.
   1순위가 성공했는데 2순위가 막혀 전 슬레이트가 0이 되는 것은 결함이다.

⚠️ 반대 위험: 삼키면 "소스가 막혔다"와 "경기가 없다"를 못 가른다.
   그래서 **경고 로그에 소스 이름과 그 소스가 담당하는 리그**를 남긴다.
"""

import pytest

from app.collectors.base import ProviderBlockedError


@pytest.mark.asyncio
async def test_배당이_막혀도_메이저_리그는_산다(monkeypatch, caplog):
    import logging

    from app import pipeline as P

    async def _fd(pool, date, client=None, league_key=None):
        return ["fd:1", "fd:2"]

    async def _odds(pool, date, only_keys=None):
        raise ProviderBlockedError("odds: already OUT_OF_USAGE_CREDITS")

    monkeypatch.setattr("app.collectors.football.upsert_games_from_football_data", _fd)
    monkeypatch.setattr("app.collectors.odds.upsert_games_from_odds_events", _odds)

    with caplog.at_level(logging.WARNING):
        ids = await P._load_soccer_fixtures(None, "2026-09-13", None, _FakeFD())
    assert ids == ["fd:1", "fd:2"], ids
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "배당" in msg or "odds" in msg, msg
    # 🔴 조용한 0 금지 — 무엇을 못 받았는지 말해야 한다
    assert "J1" in msg or "K리그1" in msg or "덴마크" in msg, msg


@pytest.mark.asyncio
async def test_football_data가_막혀도_배당_리그는_산다(monkeypatch, caplog):
    import logging

    from app import pipeline as P

    async def _fd(pool, date, client=None, league_key=None):
        raise ProviderBlockedError("football_data: auth")

    async def _odds(pool, date, only_keys=None):
        return ["odds:9"]

    monkeypatch.setattr("app.collectors.football.upsert_games_from_football_data", _fd)
    monkeypatch.setattr("app.collectors.odds.upsert_games_from_odds_events", _odds)

    with caplog.at_level(logging.WARNING):
        ids = await P._load_soccer_fixtures(None, "2026-09-13", None, _FakeFD())
    assert ids == ["odds:9"], ids


@pytest.mark.asyncio
async def test_둘_다_막히면_빈손이지_예외가_아니다(monkeypatch, caplog):
    import logging

    from app import pipeline as P

    async def _boom(*a, **kw):
        raise ProviderBlockedError("막힘")

    monkeypatch.setattr("app.collectors.football.upsert_games_from_football_data", _boom)
    monkeypatch.setattr("app.collectors.odds.upsert_games_from_odds_events", _boom)

    with caplog.at_level(logging.WARNING):
        ids = await P._load_soccer_fixtures(None, "2026-09-13", None, _FakeFD())
    assert ids == []
    # 두 소스 다 이름이 남아야 한다
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert msg.count("일정 소스 실패") == 2, msg


class _FakeFD:
    mock = False


@pytest.mark.asyncio
async def test_목모드_football_data는_부르지_않는다(monkeypatch):
    """기존 동작 유지 — 키가 없으면 목 클라이언트라 조회하지 않는다."""
    from app import pipeline as P

    called = []

    async def _fd(pool, date, client=None, league_key=None):
        called.append(1)
        return ["fd:1"]

    async def _odds(pool, date, only_keys=None):
        return []

    monkeypatch.setattr("app.collectors.football.upsert_games_from_football_data", _fd)
    monkeypatch.setattr("app.collectors.odds.upsert_games_from_odds_events", _odds)

    class _Mock:
        mock = True

    ids = await P._load_soccer_fixtures(None, "2026-09-13", None, _Mock())
    assert ids == [] and not called
