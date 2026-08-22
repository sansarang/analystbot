"""파이프라인 왕복 + 캐시 + 봇 유틸(분할·의도·시뮬레이터) 검증. 전부 목 모드."""

import app.bot.main as botmod
from app.bot.main import parse_intent_mock, split_message
from app.pipeline import run_pipeline

DATE = "2026-08-22"


async def test_pipeline_end_to_end(db_pool, redis_client):
    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    # 경기 목록 · EV 상위 픽 · 추천 조합 섹션이 있어야 한다
    assert "오늘 경기 15건" in report
    assert "EV 상위 픽" in report
    assert "추천 조합" in report
    assert "베팅 손실 책임" in report
    # 수집·판정 부산물 확인
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'") == 15
    assert await db_pool.fetchval("SELECT count(*) FROM odds_snapshots") > 0
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") == 6


async def test_pipeline_soccer_does_not_crash(db_pool, redis_client):
    report = await run_pipeline(db_pool, redis_client, sport="soccer", date=DATE)
    assert "오늘 경기 5건" in report
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='soccer'") == 5


async def test_pipeline_uses_cache(db_pool, redis_client):
    first = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    preds = await db_pool.fetchval("SELECT count(*) FROM predictions")
    snaps = await db_pool.fetchval("SELECT count(*) FROM odds_snapshots")

    second = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert second == first
    # 캐시 히트면 재수집/재적재가 없어야 한다
    assert await db_pool.fetchval("SELECT count(*) FROM predictions") == preds
    assert await db_pool.fetchval("SELECT count(*) FROM odds_snapshots") == snaps

    ttl = await redis_client.ttl(f"report:mlb:{DATE}")
    assert 0 < ttl <= 1800


def test_split_message_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 80 for i in range(300))
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")
    assert split_message("short") == ["short"]


def test_parse_intent_mock():
    assert parse_intent_mock("오늘 야구 픽 알려줘")["sport"] == "mlb"
    intent = parse_intent_mock("EPL 축구 2026-08-22 간단 요약")
    assert intent["sport"] == "soccer"
    assert intent["date"] == "2026-08-22"
    assert intent["depth"] == "brief"


async def test_simulator_routes(monkeypatch):
    async def fake_answer(sport, date=None):
        return f"report:{sport}"

    monkeypatch.setattr(botmod, "answer_query", fake_answer)
    assert await botmod.simulate("/mlb") == "report:mlb"
    assert await botmod.simulate("/soccer") == "report:soccer"
    assert await botmod.simulate("축구 분석 부탁") == "report:soccer"
    assert await botmod.simulate("오늘 야구 어때") == "report:mlb"
