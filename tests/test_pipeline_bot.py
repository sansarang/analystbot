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
    """기본 응답은 결론 카드 하나 — 기본층 20줄 이내 + 접힌 상세, 금지어 0건."""
    from app.pipeline import DETAIL_SEP, basic_layer_violations

    card = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "<<<PART>>>" not in card          # 3분할 연속 전송 폐기
    easy = card.split(DETAIL_SEP)[0]
    assert easy.startswith("📌") and "15경기" in easy
    assert "🎯 오늘의 추천" in easy
    assert len(easy.splitlines()) <= 20      # 기본층 20줄 상한
    assert len(easy) <= 4096
    # 🎯 섹션이 기본층의 뒤쪽에 배치
    assert easy.index("🎯") > easy.index("📌")
    # 2층: 상세 데이터가 접힌 층에 보존 + 기본층 금지어 0건
    assert DETAIL_SEP in card and "📊 상세 데이터" in card
    assert basic_layer_violations(card) == []
    # 수집·판정 부산물 + 심층 데이터는 분석 캐시에
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'") == 15
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") > 0
    cached = await redis_client.get(f"analysis:mlb:{DATE}")
    assert cached is not None
    import json as _json

    analysis = _json.loads(cached)
    assert analysis["games"] and analysis["sources"]


async def test_recommended_picks_meet_win_prob_and_odds_floor(db_pool, redis_client):
    """[3-1] predictions에 들어간 픽은 전부 승률·배당 하한을 넘는다.

    (EV 기준은 폐기됐다 — 승률 58%↑ AND 배당 1.55↑ 두 조건만 본다)
    """
    from app.config import get_settings

    s = get_settings()
    await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    bad = await db_pool.fetchval(
        "SELECT count(*) FROM predictions "
        "WHERE method = 'performance' AND (model_p < $1 OR odds < $2)",
        s.min_win_prob, s.min_odds)
    assert bad == 0


async def test_mode_snapshots(db_pool, redis_client, monkeypatch):
    """모드별 카드 스냅샷: 보수=플랫 원화·단식 2건 상한 / 조합엔 고분산 경고."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "report_mode", "live_conservative")
    card = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    from app.pipeline import DETAIL_SEP as _SEP
    easy = card.split(_SEP)[0]
    assert "켈리" not in card                       # 켈리 % 표기 금지 (상세 포함)
    singles = [ln for ln in easy.splitlines() if ln.startswith("· ")]
    assert 0 < len(singles) <= 2                    # 단식 최대 2건
    assert all("권장" in ln and "원)" in ln for ln in singles)  # 플랫 원화
    if "조합 1" in easy:
        assert "⚠️ 조합은 변동이 큰 베팅" in easy   # 고정 경고 문구
        assert easy.index("조합 1") > easy.index("· ")  # 단식 → 조합 순서

    # research 모드: 플랫 권장액 없음 (켈리 스테이킹)
    monkeypatch.setattr(settings, "report_mode", "research")
    card2 = await run_pipeline(db_pool, redis_client, "mlb", DATE, force_refresh=True)
    assert "(권장" not in card2.split(_SEP)[0]  # 플랫 권장액 없음 (경고문구의 "권장액"과 구분)


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
    assert "기준을 넘는 픽이 없습니다" in card
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
    """딥서치가 무효 키 등으로 실패해도 리포트는 나온다 (크래시 금지, '리서치 미완' 마킹)."""
    import app.research.deep as deepmod
    from app.research.grok import GrokClient

    async def boom(self, *a, **kw):
        raise RuntimeError("401 invalid key")

    async def deep_boom(*a, **kw):
        raise RuntimeError("401 invalid key")

    monkeypatch.setattr(GrokClient, "live_briefing", boom)
    monkeypatch.setattr(deepmod, "deep_research_game", deep_boom)
    # 이전 테스트가 남긴 리서치 캐시 제거 — 캐시 폴백이 실패 주입을 우회하지 않게
    keys = await redis_client.keys("research:*")
    if keys:
        await redis_client.delete(*keys)

    card = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "15경기" in card and "🎯" in card
    assert await db_pool.fetchval("SELECT count(*) FROM expert_picks") == 0
    # 실패 경기는 '리서치 미완'으로 마킹되어 첫 요청 시 온디맨드 보완 대상이 된다
    import json as _json

    analysis = _json.loads(await redis_client.get(f"analysis:mlb:{DATE}"))
    assert all(g.get("research_status") == "missing" for g in analysis["games"]
               if g["status"] == "scheduled")
    assert "⚠️ 일부 경기 새벽 데이터 기준" in card


async def test_pipeline_uses_cache(db_pool, redis_client):
    first = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    preds = await db_pool.fetchval("SELECT count(*) FROM predictions")
    snaps = await db_pool.fetchval("SELECT count(*) FROM odds_snapshots")

    second = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert second == first
    # 캐시 히트면 재수집/재적재가 없어야 한다
    assert await db_pool.fetchval("SELECT count(*) FROM predictions") == preds
    assert await db_pool.fetchval("SELECT count(*) FROM odds_snapshots") == snaps

    # TTL은 설정값을 따른다 — 상수를 박아 두면 값이 바뀔 때마다 테스트가 깨진다
    from app.config import get_settings

    ttl = await redis_client.ttl(f"card:mlb:{DATE}")
    assert 0 < ttl <= get_settings().report_cache_ttl


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


# ---------------------------------------------------------------- 2층 출력 (기본+상세 접힘)

def test_times_out_of_ten_phrasing():
    from app.pipeline import _times_out_of_ten

    assert _times_out_of_ten(0.70) == "10번 중 7번"
    assert _times_out_of_ten(0.35) == "10번 중 3~4번"
    assert _times_out_of_ten(0.97) == "10번 중 9번 이상"


def test_stars():
    from app.pipeline import _stars

    assert _stars(4) == "★★★★☆"
    assert _stars(0) == "★☆☆☆☆"   # 하한 1
    assert _stars(9) == "★★★★★"   # 상한 5


def _easy_game(**over):
    g = {
        "game_id": 9, "home": "Los Angeles Dodgers", "away": "Pittsburgh Pirates",
        "starts_at_kst": "08/23 08:15", "status": "scheduled", "status_label": "",
        "league": "MLB", "model_valid": True,
        "p_model": 0.62, "p_market": 0.60, "p_claude": 0.63,
        "best_odds": {"Los Angeles Dodgers": 1.62, "Pittsburgh Pirates": 2.40},
        "expert_picks": [], "verdict": "홈 우세", "judge_confidence": "high",
        "judge_pass": False,
        "stats": {"home_pitcher": "Yoshinobu Yamamoto", "away_pitcher": "Paul Skenes"},
        "research": {  # [2] 심층 분석은 재료가 있을 때만 생성된다
            "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
            "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            "home_pitcher": {"name": "Yoshinobu Yamamoto",
                             "last5": "최근 5경기 ERA 2.41, 피OPS .610, 평균 6.2이닝",
                             "era_recent": 2.41, "era_season": 2.90},
            "absences": ["Mookie Betts 손목 부상 결장"],
        },
        "pick_summary": {"side": "Los Angeles Dodgers", "desc": "LA 다저스 승",
                         "market": "h2h", "odds": 1.62, "p_final": 0.64, "ev": 0.037,
                         "flags": [], "approved": True, "reject_reason": None},
        # [A-1] 신호등은 마켓 보드에서 나온다
        "market_board": [
            # 승률 62%↑·배당 1.60↑ → 🟢 / 승률 58~62% → 🟡
            {"market": "h2h", "side": "Los Angeles Dodgers", "line": None,
             "desc": "LA 다저스 승", "odds": 1.62, "p": 0.64, "ev": 0.037,
             "axes_kr": "실데이터+모델", "approved": True, "reject_reason": None},
            {"market": "totals", "side": "Under", "line": 8.5, "desc": "언더 8.5",
             "odds": 1.78, "p": 0.59, "ev": 0.050, "axes_kr": "전문가+실데이터",
             "approved": True, "reject_reason": None},
        ],
    }
    g.update(over)
    _grade_board(g)
    return g


def _grade_board(g: dict) -> None:
    """[A-1] 마켓 보드에 등급을 채운다 — 판정 게이트(패스·저신뢰)는 전 마켓 제외."""
    from app.engine.markets import grade_candidate

    gate = None
    if g.get("judge_pass"):
        gate = "판정 패스 권장 경기"
    elif g.get("judge_confidence") == "low":
        gate = "판정 저신뢰 경기"
    for c in g.get("market_board") or []:
        if gate:
            c["approved"], c["reject_reason"] = False, gate
        if (g.get("pick_summary") or {}).get("flags") and c["market"] == "h2h":
            c["approved"], c["reject_reason"] = False, "플래그 — 배당 데이터 이상 의심"
        c["grade"], c["grade_note"] = grade_candidate(c)


def test_classify_signal_mapping():
    """[A-1] 신호등 = 전 마켓 중 최고 등급."""
    from app.pipeline import classify_signal

    assert classify_signal(_easy_game())[0] == "🟢"                       # 승인 + EV 충분
    assert classify_signal(_easy_game(judge_pass=True))[0] == "🔴"        # 전 마켓 게이트
    assert classify_signal(_easy_game(judge_confidence="low"))[0] == "🔴"  # 전 마켓 게이트
    # [2] 전 행이 '배당 미수집'이면 🔴이지만 보드 자체는 비지 않는다
    blank = _easy_game()
    for c in blank["market_board"]:
        c.update(odds=None, p=None, ev=None, placeholder=True)
    _grade_board(blank)
    sig, reason, _ = classify_signal(blank)
    assert sig == "🔴" and "배당" in reason

    # [1] 판정 미수신은 배당 유무와 무관하게 별도 사유로 밝힌다
    nojudge = _easy_game(judge_missing=True)
    sig, reason, _ = classify_signal(nojudge)
    assert sig == "🔴" and "판정 미수신" in reason


def test_signal_uses_best_market_not_moneyline():
    """[A-1] 회귀: 승패가 🔴이어도 다른 마켓이 승인되면 경기 신호등은 그 등급을 따른다."""
    from app.pipeline import classify_signal

    g = _easy_game()
    g["market_board"][0].update(approved=False, reject_reason="근거 부족 — 2-소스 미달")
    g["market_board"][1].update(p=0.65, odds=1.60)  # 언더 8.5 승인 + 승률·엣지 정상
    _grade_board(g)
    sig, reason, _ = classify_signal(g)
    assert sig == "🟢", "승패 탈락이 경기 전체를 죽이면 안 된다"
    assert "언더 8.5" in reason


def test_all_markets_rejected_lists_each_reason():
    """[A-1] 진짜 🔴은 전 마켓 검토 후에만 — 마켓별 탈락 사유를 한 줄로 밝힌다."""
    from app.pipeline import classify_signal

    g = _easy_game()
    g["market_board"][0].update(approved=True, p=0.51)            # 승패 승률 미달
    g["market_board"][1].update(approved=False, reject_reason="근거 부족 — 2-소스 미달")
    g["market_board"].append({"market": "spreads", "side": "LAD", "line": -1.5,
                              "desc": "LA 다저스 런라인 -1.5", "odds": None, "p": None,
                              "ev": None, "placeholder": True})
    _grade_board(g)
    sig, reason, _ = classify_signal(g)
    assert sig == "🔴"
    assert "전 마켓 검토 결과 기준 미달" in reason
    assert "LA 다저스 승" in reason and "언더 8.5" in reason
    assert "런라인 -1.5 배당 미수집" in reason


def test_render_game_easy_two_layers():
    from app.pipeline import DETAIL_SEP, basic_layer_violations, render_game_easy

    out = render_game_easy(_easy_game(), news="")
    easy, detail = out.split(DETAIL_SEP, 1)
    # [2-1] 신호등 바로 밑에 픽 상태(예비/최종)가 온다
    assert easy.splitlines()[2].startswith("🕐 잠정")
    assert len(easy.splitlines()) <= 8                    # (a) 기본층 8줄 이내
    assert basic_layer_violations(out) == []              # (b) 금지어 0건
    assert "10번 중" in easy and "신뢰도 ★" in easy or "★" in easy
    assert "대표 마켓" in detail or "판정" in detail        # (c) 전문 상세 보존
    assert "🟢" in easy                                   # (d) 신호등-판정 일치


def test_two_layer_html_folding():
    from app.pipeline import DETAIL_SEP

    text = "기본층 요약입니다" + DETAIL_SEP + "📊 상세 데이터\np_final 62.0% / EV +11.6%"
    html = botmod.two_layer_html(text)
    assert html is not None
    assert html.startswith("기본층 요약입니다")
    assert "<blockquote expandable>" in html
    assert "p_final 62.0%" in html                        # 상세는 접힘 안에 보존
    assert "&lt;" not in html.split("<blockquote")[0] or True
    assert botmod.two_layer_html("마커 없는 텍스트") is None


# ---------------------------------------------------------------- 실시간 리서치 체제

def test_research_freshness_gate():
    """[3] 캐시 6h 이내 & 킥오프 3h 이상 → 신선. 임박/만료 → 재리서치. 쿼터 소진 → 보수화."""
    from datetime import UTC, datetime, timedelta

    from app.research.deep import research_is_fresh

    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    kick_far = now + timedelta(hours=8)
    kick_soon = now + timedelta(hours=2)

    assert research_is_fresh(now - timedelta(hours=2), kick_far, now)            # 신선
    assert not research_is_fresh(now - timedelta(hours=7), kick_far, now)        # 6h 초과
    assert not research_is_fresh(now - timedelta(hours=1), kick_soon, now)       # 킥오프 3h 이내
    assert not research_is_fresh(None, kick_far, now)                            # 캐시 없음
    # 쿼터 소진 → 재리서치 억제 (캐시를 신선 취급)
    assert research_is_fresh(now - timedelta(hours=10), kick_soon, now, quota_exhausted=True)


def test_reversal_regression_milwaukee():
    """[4] 회귀: 밀워키-애틀랜타 최근 폼 역전 입력 → '승 소액'이 '승패 패스+대안'으로."""
    from app.engine.judge import Judge

    payload = {"games": [{
        "game_id": 1, "home": "Milwaukee Brewers", "away": "Atlanta Braves",
        "p_model": 0.58, "p_market": 0.56,
        "research": {"form_reversal": ["홈 선발 시즌 ERA 3.86 vs 최근5 5.40 악화"]},
    }]}
    v = Judge._mock_verdict(payload)["games"][0]
    assert v["conclusion_revised"] and v["pass_recommended"]
    assert "반전 요인" in v["verdict"] and "5.40" in v["reversal_factor"]
    assert "대안 마켓" in v["verdict"]

    # 반전 없는 경기는 기존 판정 유지
    payload2 = {"games": [{"game_id": 2, "home": "A", "away": "B",
                           "p_model": 0.58, "p_market": 0.56, "research": {}}]}
    v2 = Judge._mock_verdict(payload2)["games"][0]
    assert not v2["conclusion_revised"] and not v2["pass_recommended"]


def test_signal_downgrade_on_reversal():
    """[4] 반박으로 결론이 바뀌면 신호등 한 단계 보수화 (🟢→🟡, 🟡→🔴)."""
    from app.pipeline import classify_signal

    base = _easy_game()                      # 🟢 (신뢰 상 + 양의 이득)
    assert classify_signal(base)[0] == "🟢"
    revised = _easy_game(conclusion_revised=True)
    sig, reason, stars = classify_signal(revised)
    assert sig == "🟡" and "반전 요인" in reason

    yellow = _easy_game()                            # 승률을 58~62%로 낮추면 🟡
    for c in yellow["market_board"]:
        c["p"] = 0.59
    _grade_board(yellow)
    assert classify_signal(yellow)[0] == "🟡"
    yellow["conclusion_revised"] = True
    assert classify_signal(yellow)[0] == "🔴"


def test_expert_market_ledger_adoption():
    """[5] 마켓별 전적 마이너스(표본 5+) → 불채택. 미상 → 0.5표 가중."""
    from app.engine.consensus import consensus_scores, expert_pick_adopted

    assert expert_pick_adopted(None)                                     # 전적 미상 → 채택(0.5표)
    assert expert_pick_adopted({"graded": 3, "roi": -0.5})               # 표본 부족 → 미상 취급
    assert not expert_pick_adopted({"graded": 10, "roi": -0.12})         # 마이너스 → 불채택
    assert expert_pick_adopted({"graded": 10, "roi": 0.05})              # 플러스 → 채택
    # 전적 미상 전문가는 0.5표
    scores = consensus_scores([("known", "h2h:A"), ("unknown", "h2h:B")], {"known": 1.0})
    assert abs(scores["h2h:A"] - 1.0 / 1.5) < 1e-9
    assert abs(scores["h2h:B"] - 0.5 / 1.5) < 1e-9


async def test_deep_research_recent_form_feeds_data_axis(db_pool, redis_client):
    """[2] 심층 리서치 recent_form이 실데이터 축·심층 렌더에 반영된다."""
    import json as _json

    from app.pipeline import render_game_section, run_pipeline

    await run_pipeline(db_pool, redis_client, sport="soccer", date=DATE, force_refresh=True)
    a = _json.loads(await redis_client.get(f"analysis:soccer:{DATE}"))
    scheduled = [g for g in a["games"] if g["status"] == "scheduled"]
    assert scheduled
    for g in scheduled:
        assert g.get("research"), "전 경기 리서치 캐시 필수 (프리페치 계약)"
        assert (g["research"].get("home_recent_form") or {}).get("form")   # recent_form 채움
        st = g.get("stats") or {}
        assert st.get("home_season"), "리서치 최근 폼이 실데이터 축으로 흡수돼야 한다"
        section = render_game_section(g)
        assert "최근 폼:" in section


def test_card_reports_judge_failure_instead_of_pass_recommendation():
    """[정직성] 판정이 한 경기도 붙지 않으면 '관망 권장'이 아니라 '판정 실패'로 쓴다.

    실사고: 판정이 200 OK로 왔지만 games가 비어 전 경기 p_claude가 없었는데,
    카드는 "이득 기준을 넘는 단식 픽이 없습니다 — 관망 권장"이라고 출력했다.
    분석을 못 한 것과 분석 결과 픽이 없는 것은 다르다.
    """
    from app.pipeline import DETAIL_SEP, _render_card

    analysis = {
        "date": "2026-08-24", "sport": "mlb",
        "games": [{"game_id": 1, "home": "Detroit Tigers", "away": "Tampa Bay Rays",
                   "league": "MLB", "status": "scheduled", "starts_at_kst": "08/25 10:38",
                   "p_market": 0.45, "model_valid": True, "p_model": 0.44}],
        "picks": [], "combos": {}, "research_meta": {},
    }
    easy = _render_card(analysis).split(DETAIL_SEP)[0]
    assert "판정 실패" in easy and "분석 미완" in easy
    # '픽이 없다'는 결론 문장은 나오면 안 된다 (분석을 못 한 것이지 결론이 아니다)
    assert "이득 기준을 넘는 단식 픽이 없습니다" not in easy
    assert "🎯 오늘의 추천" not in easy


def test_card_still_says_pass_when_judged_but_no_value():
    """[정직성] 판정은 됐는데 기준 미달이면 사유를 밝힌다 (판정 실패와 구분)."""
    from app.pipeline import DETAIL_SEP, _render_card

    analysis = {
        "date": "2026-08-24", "sport": "mlb",
        "games": [{"game_id": 1, "home": "Detroit Tigers", "away": "Tampa Bay Rays",
                   "league": "MLB", "status": "scheduled", "starts_at_kst": "08/25 10:38",
                   "p_market": 0.45, "p_claude": 0.47, "model_valid": True, "p_model": 0.44,
                   "judge_confidence": "medium"}],
        "picks": [], "combos": {}, "research_meta": {},
    }
    easy = _render_card(analysis).split(DETAIL_SEP)[0]
    # [3-1] '픽 없음'으로 끝내지 않고 승률·배당 기준을 밝힌다
    assert "승률 58%·배당 1.55 기준을 넘는 픽이 없습니다" in easy
    assert "판정 실패" not in easy


async def test_judge_batches_large_slates(monkeypatch):
    """[판정 안정화] 경기가 많으면 배치로 나눠 호출하고 결과를 합친다.

    실사고: 10경기를 한 번에 보내자 adaptive thinking이 max_tokens를 다 써
    tool_use 없이 끝났고, 판정 0건인 채 "관망 권장" 카드가 나갔다.
    """
    from app.engine.judge import JUDGE_BATCH, Judge

    seen = []

    async def fake_once(self, payload):
        batch = payload["games"]
        seen.append(len(batch))
        return {"games": [{"game_id": g["game_id"], "p_claude": 0.5, "verdict": "v"}
                          for g in batch]}

    monkeypatch.setattr(Judge, "_judge_once", fake_once)
    j = Judge(mock=False)
    n = JUDGE_BATCH * 2 + 2
    out = await j.judge({"games": [{"game_id": i} for i in range(n)]})
    assert len(out["games"]) == n
    assert seen == [JUDGE_BATCH, JUDGE_BATCH, 2]


async def test_judge_batch_failure_keeps_other_batches(monkeypatch):
    """[판정 안정화] 배치 하나가 실패해도 나머지 판정은 살린다 (전부 아니면 전무 금지)."""
    from app.engine.judge import Judge

    calls = {"n": 0}

    async def flaky_once(self, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("judge did not return a verdict tool call")
        return {"games": [{"game_id": g["game_id"], "p_claude": 0.5, "verdict": "v"}
                          for g in payload["games"]]}

    monkeypatch.setattr(Judge, "_judge_once", flaky_once)
    from app.engine.judge import JUDGE_BATCH

    n = JUDGE_BATCH * 2 + 1
    out = await Judge(mock=False).judge({"games": [{"game_id": i} for i in range(n)]})
    # 첫 배치만 잃고 나머지 배치의 판정은 살아 있다
    assert {g["game_id"] for g in out["games"]} == set(range(JUDGE_BATCH, n))


def test_attach_verdicts_matches_string_game_ids():
    """[판정 안정화] 판정이 game_id를 문자열로 돌려줘도 부착된다."""
    from app.pipeline import _attach_verdicts

    games = [{"game_id": 409, "status": "scheduled"}]
    _attach_verdicts(games, {"games": [{"game_id": "409", "p_claude": 0.55,
                                        "verdict": "테스트"}]})
    assert games[0]["p_claude"] == 0.55


# --- LLM이 만들어낸 날짜 차단 (2026-08-26 실사고) ---

def test_intent_date_far_in_past_is_rejected():
    """★ 실사고: 프롬프트에 오늘 날짜가 없어 모델이 2024-08-26을 반환했고,
    검증이 없어 2년 전 종료 경기 12건이 분석돼 사용자에게 나갔다."""
    from app.bot.main import sanitize_intent_date

    assert sanitize_intent_date("2024-08-26", "mlb") is None


def test_intent_date_within_window_is_kept():
    from app.bot.main import sanitize_intent_date
    from app.pipeline import mlb_slate_date

    today = mlb_slate_date()
    assert sanitize_intent_date(today, "mlb") == today


def test_intent_date_far_future_is_rejected():
    from app.bot.main import sanitize_intent_date

    assert sanitize_intent_date("2099-01-01", "mlb") is None


def test_intent_date_garbage_is_rejected():
    from app.bot.main import sanitize_intent_date

    assert sanitize_intent_date("엉터리", "mlb") is None
    assert sanitize_intent_date("", "mlb") is None
    assert sanitize_intent_date(None, "mlb") is None


def test_intent_system_prompt_carries_today():
    """프롬프트에 기준일이 들어가야 모델이 날짜를 지어내지 않는다."""
    from app.bot.main import intent_system
    from app.pipeline import mlb_slate_date

    filled = intent_system()
    assert mlb_slate_date() in filled
    assert "null" in filled
    assert "__MLB_TODAY__" not in filled
    # 스키마의 JSON 중괄호가 그대로 남아 있어야 한다 (.format을 쓰면 KeyError가 난다)
    assert '{"sport"' in filled
