"""파이프라인 왕복 + 캐시 + 봇 유틸(분할·의도·시뮬레이터) 검증. 전부 목 모드."""

import re
from datetime import datetime, timedelta

import app.bot.main as botmod
import app.pipeline as pipemod
from app.bot.main import parse_intent_mock, resolve_date_arg, split_message
from app.pipeline import mlb_slate_date, run_pipeline, today_kst


def test_mlb_slate_date_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", mlb_slate_date())


def test_resolve_date_arg():
    assert resolve_date_arg(None, "mlb") is None
    assert resolve_date_arg("2026-08-25", "mlb") == "2026-08-25"
    base = datetime.strptime(mlb_slate_date(), "%Y-%m-%d")
    assert resolve_date_arg("tomorrow", "mlb") == (base + timedelta(days=1)).strftime("%Y-%m-%d")
    assert resolve_date_arg("내일", "mlb") == (base + timedelta(days=1)).strftime("%Y-%m-%d")
    assert resolve_date_arg("어제", "mlb") == (base - timedelta(days=1)).strftime("%Y-%m-%d")
    assert resolve_date_arg("nonsense", "mlb") is None  # 해석 불가 → 기본 날짜


async def test_run_pipeline_default_dates(db_pool, redis_client, monkeypatch):
    """MLB=미국 동부 오늘, 축구=KST 오늘이 기본 날짜."""
    captured = {}

    async def fake_build(pool, sport, date, **kwargs):
        captured[sport] = date
        return {}

    async def fake_report(analysis):
        return "r"

    monkeypatch.setattr(pipemod, "build_analysis", fake_build)
    monkeypatch.setattr(pipemod, "generate_report", fake_report)
    await run_pipeline(db_pool, redis_client, "mlb")
    await run_pipeline(db_pool, redis_client, "soccer")
    assert captured["mlb"] == mlb_slate_date()
    assert captured["soccer"] == today_kst()


async def test_started_games_labeled_and_excluded(db_pool, redis_client, monkeypatch):
    """진행 중/종료 경기는 KST 목록에 라벨만 붙고 분석(픽·predictions) 대상에서 제외."""
    from app.collectors.mlb import MLBClient, upsert_games

    await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    await db_pool.execute(
        "UPDATE games SET status='final', home_score=5, away_score=3 WHERE ext_id='750000'")
    await db_pool.execute("UPDATE games SET status='live' WHERE ext_id='750001'")

    async def noop_upsert(pool, date, client=None, schedule=None):
        return 0  # 파이프라인이 상태를 scheduled로 되돌리지 않게

    monkeypatch.setattr(pipemod, "upsert_games", noop_upsert)
    report = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    assert "[종료]" in report and "[진행 중]" in report
    started_preds = await db_pool.fetchval(
        "SELECT count(*) FROM predictions p JOIN games g ON g.id = p.game_id "
        "WHERE g.status != 'scheduled'")
    assert started_preds == 0

DATE = "2026-08-22"


async def test_pipeline_end_to_end(db_pool, redis_client):
    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    # 3분할 구조 + 경기 목록 · EV 픽 · 조합 · 심층 · 출처 섹션
    from app.pipeline import SECTION_SEP

    assert report.count(SECTION_SEP) == 2  # ①일정+픽 ②심층 ③속보+출처
    assert "오늘 경기 15건" in report
    assert "EV 상위 픽" in report
    assert "추천 조합" in report
    assert "경기별 심층 분석" in report
    assert "📎 출처" in report and "http" in report
    assert "베팅 손실 책임" in report
    # 수집·판정 부산물 확인
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'") == 15
    assert await db_pool.fetchval("SELECT count(*) FROM odds_snapshots") > 0
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") == 6


async def test_suspicious_picks_flagged_not_recommended(db_pool, redis_client):
    """EV>+20% 또는 모델-시장 괴리>25%p 픽은 ⚠️ 분리 표시 + 추천/predictions 제외."""
    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "데이터 검증 필요" in report  # 목 데이터에 EV 20% 초과 픽 존재
    bad = await db_pool.fetchval("SELECT count(*) FROM predictions WHERE ev > 0.20")
    assert bad == 0


async def test_pipeline_soccer_does_not_crash(db_pool, redis_client):
    report = await run_pipeline(db_pool, redis_client, sport="soccer", date=DATE)
    assert "오늘 경기 5건" in report
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='soccer'") == 5


async def test_pipeline_survives_research_failure(db_pool, redis_client, monkeypatch):
    """딥서치가 무효 키 등으로 실패해도 리포트는 나온다 (크래시 금지)."""
    from app.research.grok import GrokClient
    from app.research.perplexity import PerplexityClient

    async def boom(self, *a, **kw):
        raise RuntimeError("401 invalid key")

    monkeypatch.setattr(GrokClient, "live_briefing", boom)
    monkeypatch.setattr(PerplexityClient, "chat", boom)

    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "오늘 경기 15건" in report
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") == 0


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
    async def fake_answer(sport, date=None, progress=None):
        return f"report:{sport}"

    monkeypatch.setattr(botmod, "answer_query", fake_answer)
    assert await botmod.simulate("/mlb") == "report:mlb"
    assert await botmod.simulate("/soccer") == "report:soccer"
    assert await botmod.simulate("축구 분석 부탁") == "report:soccer"
    assert await botmod.simulate("오늘 야구 어때") == "report:mlb"


def test_route_query_scopes():
    """범위 유형별 동작 고정: 팀→1경기, MLB→전체, 픽→픽만, 모호→되묻기."""
    assert botmod.route_query("오늘 다저스 경기 어때?") == ("team", ("mlb", "Los Angeles Dodgers"))
    assert botmod.route_query("양키스 이길까") == ("team", ("mlb", "New York Yankees"))
    assert botmod.route_query("맨시티 경기 분석해줘") == ("team", ("soccer", "Manchester City"))
    assert botmod.route_query("오늘 MLB")[0] == "full"
    assert botmod.route_query("오늘 MLB 경기 알려줘")[0] == "full"
    assert botmod.route_query("오늘 언더독 픽 있어?")[0] == "picks"
    assert botmod.route_query("후안FC 경기 어때?")[0] == "ask"          # 사전에 없는 팀
    assert botmod.route_query("어때?", llm_teams=["후안FC"])[0] == "ask"  # LLM만 팀 인식


async def test_team_query_uses_slate_cache(monkeypatch, db_pool, redis_client):
    """특정 팀 질문은 전체 슬레이트 캐시에서 해당 경기만 추출한다 (파이프라인 재실행 금지)."""
    import json as _json

    from app.pipeline import mlb_slate_date

    async def fake_get_pool():
        return db_pool

    monkeypatch.setattr(botmod, "get_pool", fake_get_pool)
    monkeypatch.setattr(botmod.get_settings(), "redis_url", "redis://localhost:6379/15")

    game = {
        "game_id": 1, "home": "Los Angeles Dodgers", "away": "Pittsburgh Pirates",
        "starts_at_kst": "08/23 08:15", "status": "scheduled", "status_label": "",
        "p_model": 0.611, "p_market": 0.71, "p_claude": 0.65,
        "best_odds": {"Los Angeles Dodgers": 1.41, "Pittsburgh Pirates": 3.25},
        "stats": {"home_pitcher": "Tarik Skubal", "away_pitcher": "Jared Jones"},
        "expert_picks": [{"expert": "SBR", "site": "SBR", "pick": "spreads:Pittsburgh Pirates:+1.5",
                          "reasoning": "다저스 런라인 55-74", "record": "55-74",
                          "source_url": "https://sbr.com/x"}],
        "verdict": "원정 ERA 4.31 vs 홈 2.32라 홈 우세",
    }
    await redis_client.set(
        f"analysis:mlb:{mlb_slate_date()}",
        _json.dumps({"games": [game], "news": "LINE MOVE: Dodgers ML steamed to 1.41", "sources": []}),
    )

    async def boom(*a, **kw):
        raise AssertionError("캐시가 있는데 파이프라인을 재실행함")

    monkeypatch.setattr(botmod, "build_analysis", boom)
    reply = await botmod.answer_team_query("mlb", "Los Angeles Dodgers")
    assert "Los Angeles Dodgers(1.41)" in reply
    assert "SBR" in reply and "런라인" in reply       # 전문가 픽 + 근거
    assert "https://sbr.com/x" in reply               # 출처
    assert "판단:" in reply and "전체 슬레이트는 /mlb" in reply
    assert "속보(Grok): LINE MOVE: Dodgers ML steamed to 1.41" in reply
