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
        return {"sport": sport, "date": date}

    async def fake_card(analysis):
        return "r"

    monkeypatch.setattr(pipemod, "build_analysis", fake_build)
    monkeypatch.setattr(pipemod, "generate_card", fake_card)
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
    await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    started_preds = await db_pool.fetchval(
        "SELECT count(*) FROM predictions p JOIN games g ON g.id = p.game_id "
        "WHERE g.status != 'scheduled'")
    assert started_preds == 0
    # 시작/종료 경기 라벨은 심층 섹션(render_game_section)에 표기
    from app.pipeline import render_game_section

    analysis = await db_pool.fetchrow("SELECT 1")  # placeholder no-op
    g = {"home": "A", "away": "B", "starts_at_kst": "08/23 08:15", "status": "final",
         "status_label": "종료", "best_odds": {}, "p_model": 0.5, "model_valid": False,
         "market_probs": None, "p_market": None, "stats": {}, "expert_picks": []}
    assert "[종료]" in render_game_section(g)

DATE = "2026-08-22"


async def test_pipeline_end_to_end_card(db_pool, redis_client):
    """기본 응답은 결론 카드 하나 — 20줄 이내, 🎯 추천 섹션으로 끝난다."""
    card = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "<<<PART>>>" not in card          # 3분할 연속 전송 폐기
    assert card.startswith("📌") and "15경기" in card
    assert "🎯 오늘의 추천" in card
    assert len(card.splitlines()) <= 20      # 결론 카드 20줄 상한
    assert len(card) <= 4096
    # 🎯 섹션이 카드의 마지막에 배치
    assert card.index("🎯") > card.index("📌")
    # 수집·판정 부산물 + 심층 데이터는 분석 캐시에
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'") == 15
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") == 6
    cached = await redis_client.get(f"analysis:mlb:{DATE}")
    assert cached is not None
    import json as _json

    analysis = _json.loads(cached)
    assert analysis["games"] and analysis["sources"]


async def test_suspicious_picks_not_in_predictions(db_pool, redis_client):
    """EV>+20% 또는 모델-시장 괴리>25%p 픽은 추천·predictions에서 제외."""
    await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    bad = await db_pool.fetchval("SELECT count(*) FROM predictions WHERE ev > 0.20")
    assert bad == 0


async def test_mode_snapshots(db_pool, redis_client, monkeypatch):
    """모드별 카드 스냅샷: 보수=플랫 원화·단식 2건 상한 / 조합엔 고분산 경고."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "report_mode", "live_conservative")
    card = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    assert "켈리" not in card                       # 켈리 % 표기 금지
    singles = [ln for ln in card.splitlines() if ln.startswith("· ")]
    assert 0 < len(singles) <= 2                    # 단식 최대 2건
    assert all("권장" in ln and "원)" in ln for ln in singles)  # 플랫 원화
    if "조합 1" in card:
        assert "⚠️ 조합은 고분산" in card           # 고정 경고 문구
        assert card.index("조합 1") > card.index("· ")  # 단식 → 조합 순서

    # research 모드: 플랫 권장액 없음 (켈리 스테이킹)
    monkeypatch.setattr(settings, "report_mode", "research")
    card2 = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    assert "(권장" not in card2  # 플랫 권장액 없음 (경고문구의 "권장액"과 구분)


async def test_judge_pass_excluded_from_recommendations(db_pool, redis_client, monkeypatch):
    """Claude 판정이 '패스 권장'인 픽은 추천 목록·predictions에서 빠지고 사유 표기."""
    from app.engine.judge import Judge

    original = Judge._mock_verdict

    def pass_all(payload):
        verdict = original(payload)
        for g in verdict["games"]:
            g["pass_recommended"] = True
            g["verdict"] = "데이터 반반, 저신뢰 경기 — 패스 권장"
        return verdict

    monkeypatch.setattr(Judge, "_mock_verdict", staticmethod(pass_all))
    card = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    # 전 경기 패스 권장 → 추천·조합 없음 + 관망 정직 표기 + predictions 0건
    assert "관망 권장" in card
    assert "조합 1" not in card
    assert await db_pool.fetchval(
        "SELECT count(*) FROM predictions WHERE created_at > now() - interval '1 minute'"
    ) == 0


def test_strip_md_links():
    from app.pipeline import extract_urls, strip_md_links

    text = "라인 이동 확인[[1]](https://x.com/a/1) 및 [기사](https://news.com/b)."
    assert strip_md_links(text) == "라인 이동 확인 및 기사."
    assert extract_urls(text) == ["https://x.com/a/1", "https://news.com/b"]


async def test_pipeline_soccer_does_not_crash(db_pool, redis_client):
    card = await run_pipeline(db_pool, redis_client, sport="soccer", date=DATE)
    assert "5경기" in card and "🎯" in card
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='soccer'") == 5


async def test_pipeline_survives_research_failure(db_pool, redis_client, monkeypatch):
    """딥서치가 무효 키 등으로 실패해도 리포트는 나온다 (크래시 금지)."""
    from app.research.grok import GrokClient
    from app.research.perplexity import PerplexityClient

    async def boom(self, *a, **kw):
        raise RuntimeError("401 invalid key")

    monkeypatch.setattr(GrokClient, "live_briefing", boom)
    monkeypatch.setattr(PerplexityClient, "chat", boom)

    card = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "15경기" in card and "🎯" in card
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

    ttl = await redis_client.ttl(f"card:mlb:{DATE}")
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
    assert "LA 다저스(1.41)" in reply  # 한국어 표기
    assert "SBR" in reply and "런라인" in reply       # 전문가 픽 + 근거
    assert "https://sbr.com/x" in reply               # 출처
    assert "판단:" in reply and "전체 슬레이트는 /mlb" in reply
    assert "속보: LINE MOVE: Dodgers ML steamed to 1.41" in reply
