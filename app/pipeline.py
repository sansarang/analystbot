"""파이프라인 오케스트레이터.

(일정+스탯 ∥ 배당 ∥ 딥서치) 병렬 수집 → 엔진 계산 → judge → 리포트 생성(Sonnet,
판정 JSON만 근거로 한국어) → Redis 30분 캐시.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import asyncpg
import redis.asyncio as aioredis

from app.collectors.base import ApiQuotaError, is_quota_error
from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer_games
from app.collectors.mlb import MLBClient, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds
from app.config import get_settings
from app.engine.consensus import consensus_scores, load_expert_weights
from app.engine.judge import Judge
from app.engine.parlay import best_parlays
from app.engine.value import devig, ensemble, ev, heuristic_model_prob, implied_prob, kelly
from app.notify import notify_quota
from app.research.grok import GrokClient
from app.research.perplexity import PerplexityClient, fetch_expert_picks, save_expert_picks

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def kst_hhmm(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%m/%d %H:%M")


# 시작 전(scheduled) 경기만 분석 대상. 나머지는 목록에 라벨만 붙인다.
STATUS_LABELS = {"live": "진행 중", "final": "종료"}

# 리포트 3분할 구분자: ①일정+픽 ②경기별 심층 ③속보+출처
SECTION_SEP = "\n<<<PART>>>\n"

# 리포트 모드 — live_conservative: 조합 금지·플랫 스테이크(자금 1%)·하루 최대 2픽
MODES = {
    "live_conservative": {
        "allow_parlays": False, "max_picks": 2,
        "staking": "flat", "flat_pct": 0.01,
    },
    "research": {
        "allow_parlays": True, "max_picks": 10,
        "staking": "kelly", "flat_pct": 0.0,
    },
}

# 마크다운 링크 정리: [[1]](url) 인용 마커 제거, [텍스트](url) → 텍스트
_MD_CITATION_RE = re.compile(r"\[\[?\d+\]?\]\((https?://[^)\s]+)\)")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
_URL_RE = re.compile(r"https?://[^)\s\]]+")


def strip_md_links(text: str) -> str:
    text = _MD_CITATION_RE.sub("", text)
    return _MD_LINK_RE.sub(lambda m: m.group(1), text)


def extract_urls(text: str) -> list[str]:
    seen, out = set(), []
    for u in _URL_RE.findall(text):
        u = u.rstrip(".,")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

# 데이터 검증 플래그 기준 — 정상 시장에서 나오기 힘든 수치는 추천에서 제외하고 표시만.
EV_FLAG_MAX = 0.20        # EV +20% 초과
MODEL_GAP_MAX = 0.25      # |모델확률 - 배당 암시확률| 25%p 초과


# ---------------------------------------------------------------- 수집 (숫자 + 의견)

def _wp(win_pct: dict[str, float], team: str) -> float | None:
    """승률 조회 — standings가 축약 팀명('Rays')을 줄 때 접미사 매칭 폴백."""
    if team in win_pct:
        return win_pct[team]
    for name, v in win_pct.items():
        if team.endswith(name) or name.endswith(team):
            return v
    return None


async def _collect_mlb_stats(client: MLBClient, schedule: dict) -> dict:
    """팀 승률 + 선발투수 ERA 매핑."""
    standings = await client.fetch_standings()
    win_pct: dict[str, float] = {}
    for record in standings.get("records", []):
        for tr in record.get("teamRecords", []):
            win_pct[tr["team"]["name"]] = float(tr["winningPercentage"])

    pitcher_ids: dict[str, int] = {}
    for day in schedule.get("dates", []):
        for g in day.get("games", []):
            for side in ("home", "away"):
                p = g["teams"][side].get("probablePitcher")
                if p:
                    pitcher_ids[p["fullName"]] = p["id"]
    people = await client.fetch_pitcher_stats(list(pitcher_ids.values()))
    era: dict[str, float] = {}
    for person in people:
        try:
            stat = person["stats"][0]["splits"][0]["stat"]
            era[person["fullName"]] = float(stat["era"])
        except (KeyError, IndexError, ValueError):
            continue
    return {"win_pct": win_pct, "era": era}


async def _collect_soccer_stats(labels: set[str] | None = None) -> dict:
    """축구 모델(Elo) + [4a] football-data.org 리그 순위·폼 (경기 있는 메이저 리그만).

    로컬 Elo 아티팩트가 없으면 모델 없이 진행 (해당 경기 '모델 무효' 정직 표기).
    """
    from app.collectors.football import FootballDataClient, fetch_league_seasons
    from app.leagues import LEAGUES
    from app.models.soccer_elo import SoccerElo

    try:
        elo = await asyncio.to_thread(SoccerElo.load)
    except FileNotFoundError:
        logger.warning("[pipeline] Elo 아티팩트 없음 — python -m app.models.soccer_elo --refresh 필요")
        elo = None
    seasons: dict[str, dict] = {}
    fd = FootballDataClient()
    if not fd.mock:
        for cfg in LEAGUES.values():
            if cfg.get("fd_code") and (labels is None or cfg["label"] in labels):
                seasons[cfg["label"]] = await fetch_league_seasons(fd, cfg["fd_code"])
    return {"elo": elo, "win_pct": {}, "era": {}, "seasons": seasons}


async def _collect_research(
    pool: asyncpg.Pool, games: list[dict], date: str, league: str = "MLB",
    sport: str = "mlb", redis=None,
) -> tuple[str, list[str], dict, dict]:
    """Grok 속보(슬레이트 1콜) ∥ 경기별 심층 리서치(세마포어 동시 처리).

    반환: (news, news_urls, research_map{game_id: dict}, statuses{game_id: str}).
    리서치는 보조 신호 — 실패해도 파이프라인은 계속 간다 ('리서치 미완' 마킹).
    """
    import redis.asyncio as aioredis

    from app.research.deep import RESEARCH_CONCURRENCY, get_game_research

    news_task = GrokClient().live_briefing(games, date, league=league)
    own_redis = redis is None
    if own_redis:
        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    sem = asyncio.Semaphore(RESEARCH_CONCURRENCY)
    research_map: dict[int, dict | None] = {}
    statuses: dict[int, str] = {}

    async def one(g: dict) -> None:
        async with sem:
            data, status = await get_game_research(
                redis, {**g, "game_id": g["id"]}, sport)
        research_map[g["id"]] = data
        statuses[g["id"]] = status
        if data and data.get("expert_picks"):
            picks = [{**pk, "game": f"{g['away']} @ {g['home']}"}
                     for pk in data["expert_picks"] if isinstance(pk, dict)]
            try:
                await save_expert_picks(pool, picks)
            except Exception as exc:
                logger.warning("[pipeline] expert pick save failed: %s", exc)

    scheduled = [g for g in games if g.get("status") == "scheduled"]
    results = await asyncio.gather(
        news_task, *(one(g) for g in scheduled), return_exceptions=True)
    news_res = results[0]
    try:
        if isinstance(news_res, BaseException):
            logger.error("[pipeline] grok briefing failed, continuing without news: %s", news_res)
            if isinstance(news_res, ApiQuotaError):
                await notify_quota(news_res.service, news_res.detail)
            news = ""
        else:
            news = news_res
    finally:
        if own_redis:
            await redis.aclose()
    # 마크다운 링크 병합 깨짐 방지: 본문에서 링크 제거, URL은 출처로 분리 수집
    news_urls = extract_urls(news)
    news = strip_md_links(news)
    return news, news_urls, research_map, statuses


async def _market_probs(
    pool: asyncpg.Pool, game_id: int, home: str, away: str
) -> tuple[dict[str, float] | None, dict[str, float]]:
    """h2h 최신 스냅샷 → 북별 디빅 후 평균 확률(dict) + 사이드별 최고 배당.

    중요: 디빅은 북이 제시한 '모든' 아웃컴으로 정규화한다.
    야구는 홈/원정 2-way, 축구는 홈/무/원정 3-way — 무승부를 빼고 2-way로
    정규화하면 승/패 확률이 부풀어 전 경기 +EV 착시가 난다 (실사고 이력).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (book, side) book, side, odds
        FROM odds_snapshots
        WHERE game_id = $1 AND market = 'h2h'
        ORDER BY book, side, captured_at DESC
        """,
        game_id,
    )
    from app.collectors.football import similar_team

    def canon(side: str) -> str:
        """배당 아웃컴명을 games 팀명으로 정규화 (소스별 표기 차이 흡수)."""
        if side in (home, away, "Draw"):
            return side
        if similar_team(side, home):
            return home
        if similar_team(side, away):
            return away
        return side

    by_book: dict[str, dict[str, float]] = {}
    best_odds: dict[str, float] = {}
    for r in rows:
        side = canon(r["side"])
        by_book.setdefault(r["book"], {})[side] = float(r["odds"])
        best_odds[side] = max(best_odds.get(side, 0.0), float(r["odds"]))

    sums: dict[str, list[float]] = {}
    for sides in by_book.values():
        if home not in sides or away not in sides:
            continue
        names = list(sides.keys())  # 북이 제시한 전 아웃컴 (Draw 포함 시 3-way)
        devigged = devig([implied_prob(sides[n]) for n in names])
        for name, p in zip(names, devigged):
            sums.setdefault(name, []).append(p)
    if not sums:
        return None, best_odds
    probs = {name: sum(ps) / len(ps) for name, ps in sums.items()}
    return probs, best_odds


def _game_stats(stats: dict, research: dict | None, g: dict, sport: str) -> dict:
    """판정 입력 스탯 — [4a] fd 순위표 + 심층 리서치 최근 폼을 실데이터로 포함."""
    out = {
        "home_win_pct": _wp(stats["win_pct"], g["home"]),
        "away_win_pct": _wp(stats["win_pct"], g["away"]),
        "home_pitcher": g.get("home_pitcher"),
        "home_pitcher_era": stats["era"].get(g.get("home_pitcher")),
        "away_pitcher": g.get("away_pitcher"),
        "away_pitcher_era": stats["era"].get(g.get("away_pitcher")),
    }
    research = research or {}
    out["predicted_scores"] = research.get("predicted_scores") or []
    if sport != "soccer":
        return out
    from app.collectors.football import season_for_team

    league_seasons = (stats.get("seasons") or {}).get(g["league"]) or {}
    season_h = season_for_team(league_seasons, g["home"])
    season_a = season_for_team(league_seasons, g["away"])
    hr = research.get("home_recent_form") or {}
    ar = research.get("away_recent_form") or {}
    if season_h is None and (hr.get("form") or hr.get("rank")):
        season_h = {"form": hr.get("form") or "", "position": hr.get("rank"),
                    "points": None, "played": 5 if hr.get("gf5") is not None else None,
                    "gf": hr.get("gf5"), "ga": hr.get("ga5"), "source": "딥서치"}
    if season_a is None and (ar.get("form") or ar.get("rank")):
        season_a = {"form": ar.get("form") or "", "position": ar.get("rank"),
                    "points": None, "played": 5 if ar.get("gf5") is not None else None,
                    "gf": ar.get("gf5"), "ga": ar.get("ga5"), "source": "딥서치"}
    out["home_season"], out["away_season"] = season_h, season_a
    return out


# ---------------------------------------------------------------- 분석 본체

async def _noop_progress(step: int, total: int, label: str) -> None:
    return None


async def build_analysis(
    pool: asyncpg.Pool, sport: str, date: str,
    team: str | None = None, league_key: str | None = None, progress=None,
    redis=None,
) -> dict:
    """league_key 지정 시 그 리그만 수집·판정 (요청 범위 밖 API 호출 금지)."""
    settings = get_settings()
    progress = progress or _noop_progress
    await progress(1, 4, "일정·스탯 수집")

    # 1) 일정 fetch + upsert (이후 단계가 games 행에 의존)
    if sport == "mlb":
        mlb = MLBClient()
        schedule = await mlb.fetch_schedule(date)
        await upsert_games(pool, date, client=mlb, schedule=schedule)
        ext_ids = [
            str(g["gamePk"]) for day in schedule.get("dates", []) for g in day.get("games", [])
        ]
        stats_coro = _collect_mlb_stats(mlb, schedule)
        league = "MLB"
    else:
        fb = APIFootballClient()
        fixtures = await fb.fetch_fixtures(date)
        await upsert_soccer_games(pool, date, client=fb, fixtures=fixtures)
        ext_ids = [str(i["fixture"]["id"]) for i in fixtures.get("response", [])]
        if not ext_ids:
            # API-Football Free 플랜은 현재 시즌 미지원(비활성 폴백으로 유지) →
            # 1순위 football-data.org(메이저), 2순위 Odds API 이벤트(마이너, 중복 제외)
            from app.collectors.football import FootballDataClient, upsert_games_from_football_data
            from app.collectors.odds import upsert_games_from_odds_events
            from app.leagues import LEAGUES

            only_keys = [LEAGUES[league_key]["odds_key"]] if league_key else None
            fd = FootballDataClient()
            if not fd.mock:
                ext_ids += await upsert_games_from_football_data(
                    pool, date, client=fd, league_key=league_key)
            ext_ids += await upsert_games_from_odds_events(pool, date, only_keys=only_keys)
        stats_coro = None  # 경기 확정 후 생성 — 순위표는 경기 있는 리그만 조회
        league = "soccer"

    game_rows = await pool.fetch(
        """
        SELECT * FROM games
        WHERE sport = $1 AND ext_id = ANY($2::text[])
        ORDER BY starts_at
        """,
        sport, ext_ids,
    )
    games = [dict(r) for r in game_rows]
    if league_key:  # 리그 지정 요청 — 그 리그 경기만 (다른 리그 언급 금지)
        from app.leagues import LEAGUES

        games = [g for g in games if g["league"] == LEAGUES[league_key]["label"]]
    if team:  # 특정 팀 질문 — 그 경기 1건만 분석 (전체 파이프라인 낭비 금지)
        from app.collectors.football import similar_team

        games = [g for g in games
                 if similar_team(g["home"], team) or similar_team(g["away"], team)]
    if (team or league_key) and not games:
        if stats_coro is not None:
            stats_coro.close()  # 미사용 코루틴 정리
        return {"sport": sport, "date": date, "games": [], "picks": [],
                "parlays": [], "combos": {}, "news": "", "sources": [],
                "verdict": {"games": []}, "mode": {"name": settings.report_mode}}

    # 배당 조회는 경기가 있는 리그 키만 (크레딧 절약)
    if sport == "mlb":
        active_keys = ["baseball_mlb"]
    else:
        from app.leagues import LEAGUES as _L

        labels_present = {g["league"] for g in games}
        active_keys = [c["odds_key"] for c in _L.values() if c["label"] in labels_present]

    await progress(2, 4, "배당·딥서치 수집")
    if stats_coro is None:
        stats_coro = _collect_soccer_stats({g["league"] for g in games})
    # 2) 스탯 ∥ 배당 ∥ 딥서치 병렬 수집 (딥서치도 요청 범위의 경기로만 한정)
    stats, _, (news, news_urls, research_map, research_statuses) = await asyncio.gather(
        stats_coro,
        snapshot_odds(pool, sport, client=OddsClient(), only_keys=active_keys),
        _collect_research(pool, games, date, league, sport=sport, redis=redis),
    )

    # 3) 경기별 p_model / p_market / 전문가 컨센서스 (+마켓별 전적 분리 [5])
    from app.engine.consensus import expert_pick_adopted, load_expert_market_ledger

    weights = await load_expert_weights(pool)
    market_ledger = await load_expert_market_ledger(pool)
    judge_games = []
    for g in games:
        p_model3 = None
        if sport == "mlb":
            p_model = heuristic_model_prob(
                _wp(stats["win_pct"], g["home"]) or 0.5,
                _wp(stats["win_pct"], g["away"]) or 0.5,
                stats["era"].get(g["home_pitcher"]),
                stats["era"].get(g["away_pitcher"]),
            )
            model_valid = True
        else:
            elo = stats.get("elo")
            p_model3 = elo.probs(g["home"], g["away"], g["league"]) if elo else None
            if p_model3:
                p_model, model_valid = p_model3[0], True
            else:
                p_model, model_valid = 0.5, False  # 모델 무효 — 앙상블에서 제외
        market_probs, best_odds = await _market_probs(pool, g["id"], g["home"], g["away"])
        p_market = round(market_probs[g["home"]], 4) if market_probs and g["home"] in market_probs else None
        pick_rows = await pool.fetch(
            "SELECT expert, site, source_url, pick, reasoning, record "
            "FROM expert_picks WHERE game_id = $1",
            g["id"],
        )
        eps = []
        for r in pick_rows:
            ep = dict(r)
            led = market_ledger.get((ep["expert"], (ep["pick"] or "").split(":")[0]))
            ep["ledger"] = led
            ep["adopted"] = expert_pick_adopted(led)
            eps.append(ep)
        judge_games.append({
            "game_id": g["id"],
            "home": g["home"], "away": g["away"], "league": g["league"],
            "starts_at": g["starts_at"].isoformat(),
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "status": g["status"],
            "research": research_map.get(g["id"]),
            "research_status": research_statuses.get(g["id"], "missing"),
            "status_label": STATUS_LABELS.get(g["status"], ""),
            "p_model": round(p_model, 4),
            "model_valid": model_valid,
            "p_model3": [round(x, 4) for x in p_model3] if p_model3 else None,
            "p_market": p_market,
            "market_probs": (
                {k: round(v, 4) for k, v in market_probs.items()} if market_probs else None
            ),
            "best_odds": best_odds,
            "stats": _game_stats(stats, research_map.get(g["id"]), g, sport),
            "expert_picks": eps,
            "consensus": consensus_scores(
                [(r["expert"], r["pick"]) for r in pick_rows], weights
            ),
        })

    await progress(3, 4, "Claude 판정")
    # 4) Claude 판정 — JUDGE_MODEL 고정. Grok은 정보 수집 전용(판정 금지).
    #    시작 전 경기만. 크레딧 소진 시 알림 후 목 판정 폴백 (크래시 금지)
    upcoming = [g for g in judge_games if g["status"] == "scheduled"]
    judge_payload = {"date": date, "sport": sport,
                     "games": upcoming, "breaking_news": news}
    if not upcoming:
        verdict: dict = {"games": []}
    else:
        try:
            verdict = await Judge().judge(judge_payload)
        except ApiQuotaError as exc:
            logger.error("[pipeline] judge quota exhausted — falling back to mock verdict: %s", exc)
            await notify_quota(exc.service, exc.detail)
            verdict = Judge._mock_verdict(judge_payload)
    _attach_verdicts(judge_games, verdict)

    # 4b) 2차 검증 — 논쟁 경기(저신뢰 또는 |모델-시장|≥10%p)만 Grok에 반대 근거 1콜.
    #     전 경기 적용 금지(비용). 반대 근거가 실체적일 때만 judge 재산출.
    verdict = await _second_opinion(judge_games, verdict, date, sport, news)
    _attach_verdicts(judge_games, verdict)

    # 4c) [7] 전 마켓 배당 부착 + [4d] 데이터 제로 강등 → 5) 마켓 풀 픽 계산
    await _attach_alt_markets(pool, judge_games)
    _enforce_data_rules(judge_games)
    picks_out, parlays, recommended = _compute_picks(settings, judge_games, sport)
    for p in recommended:
        await pool.execute(
            """
            INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                     p_market, p_ensemble)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            p["game_id"], p["pick"], p["p"], p["odds"], p["ev"], p["kelly"],
            p.get("p_market_side"), p.get("p_ensemble_side"),
        )

    sources, seen_urls = [], set()
    for jg in judge_games:
        for ep in jg.get("expert_picks", []):
            url = ep.get("source_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({"site": ep.get("site", "?"), "url": url})
    for url in news_urls:
        if url not in seen_urls:
            seen_urls.add(url)
            sources.append({"site": "Grok 검색", "url": url})
    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None

    # [9] 등급제 조합 — 전 마켓 승인 레그 풀에서 구성 (승무패 전용 구조 폐지)
    from app.engine.parlay import build_tiered_parlays

    combos = build_tiered_parlays(approved_market_legs(judge_games), stake_krw)

    from app.research.deep import DAILY_RESEARCH_CAP, research_calls_today
    if redis is not None:
        calls_today = await research_calls_today(redis)
    else:
        import redis.asyncio as _aioredis
        _r = _aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            calls_today = await research_calls_today(_r)
        finally:
            await _r.aclose()
    research_meta = {
        "refreshed": sum(1 for s in research_statuses.values() if s == "refreshed"),
        "stale_fallback": sum(1 for s in research_statuses.values() if s == "stale_fallback"),
        "missing": sum(1 for s in research_statuses.values() if s == "missing"),
        "quota": calls_today >= DAILY_RESEARCH_CAP,
    }
    return {
        "sport": sport, "date": date,
        "research_meta": research_meta,
        "mode": {"name": settings.report_mode, **mode,
                 "stake_krw": stake_krw, "bankroll_krw": settings.bankroll_krw},
        "games": judge_games, "picks": picks_out,
        "parlays": parlays, "combos": combos,
        "news": news, "sources": sources, "verdict": verdict,
    }


def _attach_verdicts(judge_games: list[dict], verdict: dict) -> None:
    by_id = {g["game_id"]: g for g in verdict.get("games", [])}
    for jg in judge_games:
        v = by_id.get(jg["game_id"])
        if v is None:
            continue
        jg["p_claude"] = v["p_claude"]
        jg["verdict"] = v["verdict"]
        jg["excluded_picks"] = v.get("excluded_picks", [])
        jg["judge_pass"] = bool(v.get("pass_recommended"))
        jg["judge_confidence"] = v.get("confidence", "medium")
        jg["reversal_factor"] = v.get("reversal_factor") or ""
        jg["conclusion_revised"] = bool(v.get("conclusion_revised"))


def _enforce_data_rules(judge_games: list[dict]) -> None:
    """[4d] 판정 입력에 올 시즌 실데이터 0건 → 신뢰도 자동 '낮음' + 추천 자격 박탈."""
    from app.engine.markets import has_season_data

    for jg in judge_games:
        if jg.get("status") != "scheduled" or "p_claude" not in jg:
            continue
        if not has_season_data(jg):
            jg["data_zero"] = True
            if jg.get("judge_confidence") != "low":
                jg["judge_confidence"] = "low"
                jg["verdict"] = ((jg.get("verdict") or "")
                                 + " [자동 강등: 올 시즌 실데이터 0건 — 신뢰도 낮음, 추천 제외]")


async def _attach_alt_markets(pool: asyncpg.Pool, judge_games: list[dict]) -> None:
    """[7] 핸디캡·토탈 수집 배당을 경기 객체에 부착 (디빅 확률 + 사이드별 최고 배당)."""
    for jg in judge_games:
        if jg.get("status") != "scheduled":
            continue
        jg["alt_markets"] = await _alt_market_rows(pool, jg["game_id"], jg["home"], jg["away"])


def approved_market_legs(games: list[dict]) -> list[dict]:
    """[9] 조합 후보 풀 = 전 마켓 승인 픽 (판정 제외·저신뢰 경기는 이미 미승인)."""
    legs = []
    for jg in games:
        if jg.get("status") != "scheduled":
            continue
        for c in jg.get("market_board") or []:
            if c.get("approved"):
                legs.append({
                    "game_id": jg["game_id"], "desc": c["desc"], "market": c["market"],
                    "odds": c["odds"], "p": c["p"],
                    "confidence": jg.get("judge_confidence", "medium"),
                    "league": jg.get("league"), "starts_at_kst": jg["starts_at_kst"],
                })
    return legs


DISPUTE_GAP = 0.10  # |모델 - 시장| 10%p 이상이면 논쟁 경기


def _disputed_games(judge_games: list[dict]) -> list[dict]:
    out = []
    for jg in judge_games:
        if jg["status"] != "scheduled" or "p_claude" not in jg:
            continue
        low_conf = jg.get("judge_confidence") == "low"
        gap = (
            jg["model_valid"] and jg["p_market"] is not None
            and abs(jg["p_model"] - jg["p_market"]) >= DISPUTE_GAP
        )
        if low_conf or gap:
            out.append(jg)
    return out


async def _second_opinion(
    judge_games: list[dict], verdict: dict, date: str, sport: str, news: str
) -> dict:
    """논쟁 경기 한정 Grok 반대 근거 1콜 → 실체적이면 judge 재산출 (Grok은 판정 안 함)."""
    from app.research.grok import GrokClient

    disputed = _disputed_games(judge_games)
    if not disputed:
        return verdict
    items = [
        f"- {jg['away']} @ {jg['home']}: 판정={jg['verdict'][:150]} "
        f"(p_claude={jg['p_claude']}, 모델={jg['p_model']}, 시장={jg['p_market']})"
        for jg in disputed
    ]
    try:
        counter = await GrokClient().counter_briefing(items)
    except Exception as exc:  # 2차 검증 실패는 1차 판정 유지
        logger.warning("[pipeline] counter briefing failed: %s", exc)
        return verdict
    if not counter.strip() or "반대 근거 없음" == counter.strip():
        return verdict
    logger.info("[pipeline] second opinion for %d disputed games", len(disputed))
    payload = {
        "date": date, "sport": sport, "games": disputed, "breaking_news": news,
        "counter_evidence": counter,
        "instruction": (
            "위 논쟁 경기들의 기존 판정에 대해 수집된 반대 근거(counter_evidence)가 있다. "
            "반대 근거가 실체적이면 반영해 p_claude와 판정을 재산출하고, "
            "실체가 없으면 기존 판정을 유지하라."
        ),
    }
    try:
        second = await Judge().judge(payload)
    except (ApiQuotaError, Exception) as exc:
        logger.warning("[pipeline] second-opinion judge failed: %s", exc)
        return verdict
    merged = {g["game_id"]: g for g in verdict.get("games", [])}
    for g in second.get("games", []):
        if g["game_id"] in merged:
            g["second_opinion"] = True
            merged[g["game_id"]] = g
    return {"games": list(merged.values())}


def _compute_picks(
    settings, judge_games: list[dict], sport: str
) -> tuple[list[dict], list[dict], list[dict]]:
    """jg(판정 부착 완료) → (전체 픽, 파레이, 추천 픽). DB 접근 없음 — 재판정 시 재사용.

    [7] 경기별 전 마켓 후보 평가 → jg["market_board"].
    [1][2][3] 승인 규칙(2-소스·괴리 검증·저분산 우선)은 engine.markets._approve.
    [5] p_final = λ*p_market + (1-λ)*p_ensemble (리그 성숙도 연동 수축).
    경기 대표 픽 = 승인 후보 중 EV 최대 (없으면 진단용 최고 EV 후보, 미승인 표기).
    """
    from app.engine.markets import build_candidates, shrink

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None

    def blend(p_model_s: float | None, p_market_s: float, p_claude_s: float) -> float:
        if p_model_s is None:  # 모델 무효 → 시장+Claude만으로 재정규화
            w = settings.ensemble_w_market + settings.ensemble_w_claude
            return (settings.ensemble_w_market * p_market_s
                    + settings.ensemble_w_claude * p_claude_s) / w
        return ensemble(
            p_model_s, p_market_s, p_claude_s,
            settings.ensemble_w_model, settings.ensemble_w_market, settings.ensemble_w_claude,
        )

    picks_out = []
    for jg in judge_games:
        if jg["status"] != "scheduled" or "p_claude" not in jg:
            continue
        market = jg.get("market_probs")
        if not market or jg["home"] not in market or jg["away"] not in market:
            jg["market_board"] = []
            continue

        # 사이드별 확률: 축구는 무승부 질량 때문에 1-p_home ≠ p_away — 시장 3-way 기준
        p_draw_m = market.get("Draw", 0.0)
        p_claude_home = jg["p_claude"]
        p_claude_away = max(0.0, min(1.0, 1.0 - p_claude_home - p_draw_m))
        p3 = jg.get("p_model3")
        league_lam = "MLB" if sport == "mlb" else jg.get("league")
        p_final: dict[str, float] = {}
        p_ens: dict[str, float] = {}
        for side, p_model_s, p_market_s, p_claude_s in (
            (jg["home"], (p3[0] if p3 else (jg["p_model"] if jg.get("model_valid") else None)),
             market[jg["home"]], p_claude_home),
            (jg["away"], (p3[2] if p3 else ((1 - jg["p_model"]) if jg.get("model_valid") and sport == "mlb" else None)),
             market[jg["away"]], p_claude_away),
        ):
            if not (jg.get("best_odds") or {}).get(side):
                continue
            pe = blend(p_model_s, p_market_s, p_claude_s)
            p_ens[side] = round(pe, 4)
            p_final[side] = round(shrink(pe, p_market_s, league_lam), 4)

        # [7][8] 전 마켓 후보 생성·승인 → 마켓 보드
        cands = build_candidates(jg, sport, p_final)
        jg["market_board"] = cands
        if not cands:
            continue
        approved = [c for c in cands if c.get("approved")]
        rep = (max(approved, key=lambda c: c["ev"]) if approved
               else max((c for c in cands if c["market"] == "h2h"),
                        key=lambda c: c["ev"],
                        default=max(cands, key=lambda c: c["ev"])))

        pick = f"{rep['market']}:{rep['side']}" + (
            f":{rep['line']:g}" if rep.get("line") is not None else "")
        pick_kelly = kelly(rep["p"], rep["odds"], settings.kelly_fraction, settings.kelly_cap)
        # 판정 제외: Claude가 패스 권장/저신뢰로 본 경기는 추천 목록에서 뺀다
        judge_excluded = None
        if jg.get("judge_pass"):
            judge_excluded = f"판정: 패스 권장 — {(jg.get('verdict') or '')[:120]}"
        elif jg.get("judge_confidence") == "low":
            judge_excluded = f"판정: 저신뢰 — {(jg.get('verdict') or '')[:120]}"

        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "league": jg.get("league") or ("MLB" if sport == "mlb" else "?"),
            "starts_at_kst": jg["starts_at_kst"], "pick": pick,
            "market": rep["market"], "side": rep["side"], "line": rep.get("line"),
            "desc": rep["desc"], "p": rep["p"], "p_claude": jg["p_claude"],
            "model_valid": jg["model_valid"],
            "confidence": jg.get("judge_confidence", "medium"),
            "odds": rep["odds"], "ev": rep["ev"], "kelly": round(pick_kelly, 4),
            "stake_krw": stake_krw,
            "verdict": jg.get("verdict", ""), "excluded_picks": jg.get("excluded_picks", []),
            "flags": rep.get("flags", []), "judge_excluded": judge_excluded,
            "approved": bool(rep.get("approved")),
            "reject_reason": rep.get("reject_reason"),
            "axes": rep.get("axes_kr"),
            "p_market_side": market.get(rep["side"]) if rep["market"] == "h2h" else None,
            "p_ensemble_side": p_ens.get(rep["side"]),
        }
        picks_out.append(entry)
        # 카드·심층이 같은 숫자를 인용하도록 요약을 경기 객체에도 부착 [단일 확률 소스]
        jg["pick_summary"] = {
            "side": rep["side"], "desc": rep["desc"], "market": rep["market"],
            "odds": rep["odds"], "p_final": rep["p"], "ev": rep["ev"],
            "flags": rep.get("flags", []), "approved": bool(rep.get("approved")),
            "reject_reason": rep.get("reject_reason"), "axes": rep.get("axes_kr"),
        }
        for c in cands:
            if c.get("flags"):
                logger.warning(
                    "[pipeline] suspicious pick flagged — %s @ %s | %s odds=%.2f: %s",
                    jg["away"], jg["home"], c["desc"], c["odds"], "; ".join(c["flags"]),
                )

    picks_out.sort(key=lambda x: x["ev"], reverse=True)
    # 단식 추천 = [1]~[3] 승인 + 판정 통과 + EV 임계 통과 + 모드별 픽 수 상한
    clean = [
        p for p in picks_out
        if p["approved"] and not p["judge_excluded"] and p["ev"] > settings.ev_threshold
    ]
    recommended = clean[: mode["max_picks"]]
    for p in picks_out:
        p["recommended"] = p in recommended
    legs = [{"game_id": p["game_id"], "pick": p["pick"], "p": p["p"],
             "odds": p["odds"], "ev": p["ev"]} for p in clean]
    return picks_out, best_parlays(legs), recommended


# ---------------------------------------------------------------- 리포트 생성

# 영어 문장 검출 (한국어 출력 규율 검증용): 5단어 이상 연속 영단어
_EN_SENT_RE = re.compile(r"\b[A-Za-z][a-z]+(?:\s+[A-Za-z'’\-]+){4,}")

# 보이지 않는 문자 (URL 병합 버그 원인: U+FFFC·제로폭 등)
_INVISIBLE = dict.fromkeys(map(ord, "\ufffc\u200b\u200c\u200d\u200e\u200f\ufeff\u2060"))


def contains_english_sentence(text: str) -> bool:
    return bool(_EN_SENT_RE.search(text))


def clean_invisible(text: str) -> str:
    return (text or "").translate(_INVISIBLE).strip()


def _kr(name: str) -> str:
    from app.bot.aliases import kr_team

    return kr_team(name)


def _team_news_lines(news: str, home: str, away: str) -> list[str]:
    keys = {home.lower(), away.lower(), home.split()[-1].lower(), away.split()[-1].lower(),
            _kr(home).lower(), _kr(away).lower()}
    return [ln for ln in news.splitlines() if any(k in ln.lower() for k in keys)]


async def _alt_market_rows(
    pool: asyncpg.Pool, game_id: int, home: str = "", away: str = "",
) -> list[dict]:
    """핸디캡·토탈 수집 배당 전 라인 — 북별 2-way 디빅 평균 확률 + 최고 배당.

    (구 _low_var_candidates의 일반화 — 필터 없이 전 라인을 마켓 보드 후보로 넘긴다.)
    """
    from collections import defaultdict

    rows = await pool.fetch(
        "SELECT DISTINCT ON (book, market, side, line) book, market, side, line, odds "
        "FROM odds_snapshots WHERE game_id = $1 AND market IN ('spreads', 'totals') "
        "ORDER BY book, market, side, line, captured_at DESC",
        game_id,
    )
    from app.collectors.football import similar_team

    def canon(side: str) -> str:
        if side in (home, away) or side in ("Over", "Under"):
            return side
        if home and similar_team(side, home):
            return home
        if away and similar_team(side, away):
            return away
        return side

    pair: dict = defaultdict(dict)
    best: dict = {}
    for r in rows:
        if r["line"] is None:
            continue
        line, odds = float(r["line"]), float(r["odds"])
        side = canon(r["side"])
        pair[(r["book"], r["market"], abs(line))][(side, line)] = odds
        bk = (r["market"], side, line)
        best[bk] = max(best.get(bk, 0.0), odds)
    probs: dict = defaultdict(list)
    for k, sides in pair.items():
        if len(sides) != 2:
            continue
        (s1, o1), (s2, o2) = list(sides.items())
        p1, p2 = devig([implied_prob(o1), implied_prob(o2)])
        probs[(k[1], s1[0], s1[1])].append(p1)
        probs[(k[1], s2[0], s2[1])].append(p2)
    out = [
        {"market": market, "side": side, "line": line,
         "p": round(sum(ps) / len(ps), 4), "odds": best[(market, side, line)]}
        for (market, side, line), ps in probs.items()
    ]
    out.sort(key=lambda x: x["p"], reverse=True)
    return out[:8]


# 기본층(항상 보이는 부분)과 접힌 전문층을 나누는 마커 — 봇이 blockquote로 변환
DETAIL_SEP = "\n<<DETAIL>>\n"

# 기본층 금지어 — 전문 용어는 접힌 상세에서만 (치환 검증기)
FORBIDDEN_BASIC_TERMS = [
    r"\bp_final\b", r"\bp_model\b", r"\bp_claude\b", r"\bEV\b", r"켈리",
    r"디비그", r"암시\s*확률", r"3자\s*대조", r"플래그", r"괴리",
]
_FORBIDDEN_RES = [re.compile(p) for p in FORBIDDEN_BASIC_TERMS]


def basic_layer_violations(text: str) -> list[str]:
    """기본층 텍스트에서 금지 전문 용어 검출 (0건이어야 통과)."""
    basic = text.split(DETAIL_SEP)[0]
    return [p.pattern for p in _FORBIDDEN_RES if p.search(basic)]


def _times_out_of_ten(p: float) -> str:
    """확률 → '10번 중 N번' 화법."""
    lo = int(p * 10)
    if lo >= 9:
        return "10번 중 9번 이상"
    if lo < 1:
        return "10번 중 1번도 안 되는 수준"
    if abs(p * 10 - lo) < 0.15:
        return f"10번 중 {lo}번"
    return f"10번 중 {lo}~{lo + 1}번"


def _ga(word: str) -> str:
    """한글 받침에 따라 이/가 조사 선택."""
    if word and "가" <= word[-1] <= "힣" and (ord(word[-1]) - 0xAC00) % 28:
        return "이"
    return "가"


def _stars(n: int) -> str:
    n = max(1, min(5, n))
    return "★" * n + "☆" * (5 - n)


def classify_signal(jg: dict) -> tuple[str, str, int]:
    """신호등 판정 + [4] 반박 검증으로 결론이 바뀐 경기는 한 단계 보수화."""
    sig, reason, stars = _classify_base(jg)
    if jg.get("conclusion_revised"):
        if sig == "🟢":
            return "🟡", "소액만 — 반박 검증에서 반전 요인이 나와 한 단계 보수 전환했습니다", max(1, stars - 1)
        if sig == "🟡":
            return "🔴", "패스 — 반박 검증에서 반전 요인이 나와 보수 전환했습니다", max(1, stars - 1)
    return sig, reason, stars


def _classify_base(jg: dict) -> tuple[str, str, int]:
    """신호등 판정 → (이모지, 굵은 한 문장 이유, 별점 1~5).

    🟢 판정 통과+신뢰도 상 / 🟡 가치 있으나 고분산·신뢰 보통 /
    🔴 플래그·방향충돌·신뢰 낮음·이득 없음.
    """
    ps = jg.get("pick_summary") or {}
    conf = jg.get("judge_confidence", "medium")
    ev_val = ps.get("ev")
    conflict = (
        jg.get("model_valid") and jg.get("p_market") is not None
        and (jg["p_model"] - 0.5) * (jg["p_market"] - 0.5) < 0
    )
    if ps.get("flags"):
        return "🔴", "패스 — 배당 숫자가 이상해서 계산에서 제외한 경기입니다", 1
    if jg.get("judge_pass") or conf == "low":
        return "🔴", "패스 — 데이터끼리 서로 싸우는 경기입니다. 저희도 모르겠으면 안 거는 게 답입니다", 2
    if ps and ps.get("approved") is False:
        rr = ps.get("reject_reason") or ""
        if "시장이 아는" in rr:
            return "🔴", "패스 — 시장이 아는 정보가 있을 수 있는 가격입니다", 2
        if "저분산" in rr:
            return "🟡", "소액만 — 승패 대신 안전한 마켓만 볼 경기입니다", 3
        return "🔴", "패스 — 근거가 한 축뿐이라 추천 기준(독립 근거 2개)에 못 미칩니다", 2
    if conflict:
        return "🔴", "패스 — 시장과 통계가 서로 반대 방향을 보고 있습니다", 2
    if ev_val is None or jg.get("p_market") is None:
        return "🔴", "패스 — 배당 정보가 없어 판단할 수 없습니다", 2
    if ev_val <= 0:
        return "🔴", "패스 — 이길 팀은 보이는데 배당이 박해서 남는 게 없습니다", 3 if conf == "high" else 2
    if conf == "high":
        return "🟢", "추천 — 배당이 실력보다 후하게 붙어 있습니다", 4
    return "🟡", "소액만 — 이득은 보이지만 확신이 부족한 경기입니다", 3


def _guard_basic(text: str, where: str) -> str:
    """기본층 금지어 런타임 검증 — 위반은 코드 버그이므로 에러 로그로 즉시 드러낸다."""
    v = basic_layer_violations(text)
    if v:
        logger.error("[2layer] 기본층 금지어 검출 (%s): %s", where, v)
    return text


def render_game_easy(jg: dict, news: str = "") -> str:
    """심층 분석 2층 출력: 쉬운 요약 6줄 + <<DETAIL>> 뒤에 전문 상세(접힘용).

    데이터를 줄이지 않는다 — 표현만 바꾼다. 전문 수치는 전부 상세에 보존.
    """
    home_kr, away_kr = _kr(jg["home"]), _kr(jg["away"])
    signal, reason, stars = classify_signal(jg)
    lines = [f"{jg['starts_at_kst']} {home_kr} vs {away_kr} [{jg.get('league', '?')}]"]
    lines.append(f"{signal} {reason}")

    # 누가 이길까 — 우세한 쪽 기준 '10번 중 N번' 화법
    ph = None
    if jg.get("p_claude") is not None:
        ph = jg["p_claude"]
    elif jg.get("p_market") is not None:
        ph = jg["p_market"]
    if ph is not None:
        fav, p_fav = (home_kr, ph) if ph >= 0.5 else (away_kr, 1 - ph - ((jg.get("market_probs") or {}).get("Draw", 0)))
        p_fav = max(0.05, min(0.95, p_fav))
        lines.append(f"누가 이길까? 봇 계산으론 {fav}{_ga(fav)} {_times_out_of_ten(p_fav)} 이기는 그림입니다.")
    else:
        lines.append("누가 이길까? 데이터가 부족해 저희도 판단을 보류합니다.")

    # 걸 만한가 — 전 마켓 중 최적 하나를 골라 결론까지 문장으로 ([8])
    ps = jg.get("pick_summary") or {}
    if ps.get("flags"):
        lines.append("걸 만한가? 숫자가 이상해서 이 경기는 계산을 신뢰하지 않습니다.")
    elif ps.get("ev") is None:
        lines.append("걸 만한가? 배당이 아직 없어 이득 계산이 불가능합니다.")
    elif ps.get("approved"):
        if ps.get("market") == "h2h":
            lines.append(f"걸 만한가? {_kr(ps['side'])} 승 배당(@{ps['odds']:.2f})이 실력보다 후하게 붙어 있어 걸어볼 만합니다.")
        else:
            lines.append(f"걸 만한가? 승패보다는 {ps.get('desc')}(@{ps['odds']:.2f})가 걸 만한 자리입니다.")
    else:
        rr = ps.get("reject_reason") or ""
        if "시장이 아는" in rr:
            lines.append("걸 만한가? 배당 움직임에 시장만 아는 정보가 있을 수 있어 피하는 게 안전합니다.")
        elif "저분산" in rr:
            lines.append("걸 만한가? 확신이 부족해 승패 단식은 피하는 날입니다.")
        elif "근거 부족" in rr or "지지 축" in rr:
            lines.append("걸 만한가? 근거가 한 축뿐이라 추천 기준(독립 근거 2개)에 못 미칩니다.")
        elif ps.get("ev", 0) > 0:
            lines.append("걸 만한가? 이득이 아주 약간 있는 정도라 무리할 이유는 없습니다.")
        else:
            lines.append("걸 만한가? 지금 배당엔 이득이 없습니다. 이겨도 남는 게 없는 가격입니다.")

    # 조심할 점
    draw_p = (jg.get("market_probs") or {}).get("Draw") or 0
    if not jg.get("model_valid"):
        caution = "이 리그는 통계 데이터가 부족해서 감으로 잡은 부분이 있습니다."
    elif draw_p >= 0.28:
        caution = "무승부가 자주 나오는 유형의 경기입니다."
    else:
        caution = "부상·라인업 변수는 킥오프 직전에 바뀔 수 있습니다."
    lines.append(f"조심할 점: {caution}")
    lines.append(f"신뢰도 {_stars(stars)}")

    detail = render_game_section(jg, news)
    return _guard_basic("\n".join(lines[:6]) + DETAIL_SEP + detail, "game_easy")


def render_game_section(jg: dict, news: str = "") -> str:
    """경기 1건 심층 ①~⑦ (버튼 응답·팀 질문 공용). 25줄 상한. 전면 한국어."""
    home_kr, away_kr = _kr(jg["home"]), _kr(jg["away"])
    ho = jg.get("best_odds", {}).get(jg["home"])
    ao = jg.get("best_odds", {}).get(jg["away"])
    matchup = (f"{home_kr}({ho:.2f}) vs {away_kr}({ao:.2f})"
               if ho and ao else f"{home_kr} vs {away_kr}")
    st = jg.get("stats") or {}
    pitchers = ""
    if st.get("home_pitcher") or st.get("away_pitcher"):
        pitchers = f" | {st.get('home_pitcher') or '?'} vs {st.get('away_pitcher') or '?'}"
    label = f" [{jg['status_label']}]" if jg.get("status_label") else ""
    lines = [f"{jg['starts_at_kst']} [{jg.get('league', '?')}] {matchup}{pitchers}{label}"]

    research = jg.get("research") or {}
    hr, ar = research.get("home_recent_form") or {}, research.get("away_recent_form") or {}
    if hr.get("form") or ar.get("form"):
        lines.append(f"최근 폼: {home_kr} {hr.get('form') or '?'} · {away_kr} {ar.get('form') or '?'}")
    hp, ap = research.get("home_pitcher") or {}, research.get("away_pitcher") or {}
    if hp.get("last5") or ap.get("last5"):
        lines.append(f"선발 최근: 홈 {str(hp.get('last5') or '?')[:80]} / 원정 {str(ap.get('last5') or '?')[:80]}")
    if research.get("form_reversal"):
        lines.append("⚠️ 폼 역전: " + "; ".join(str(x) for x in research["form_reversal"][:2])[:180])
    if jg.get("research_status") in ("missing", "stale_fallback"):
        lines.append("⚠️ 리서치 미완 — 새벽 데이터/시즌 평균 기준")

    probs = []
    if jg.get("p_market") is not None:
        probs.append(f"시장: 홈 {jg['p_market']:.0%}")
        draw = (jg.get("market_probs") or {}).get("Draw")
        if draw:
            probs.append(f"무 {draw:.0%}")
    else:
        probs.append("시장: 배당 미수집")
    if jg.get("model_valid"):
        p3 = jg.get("p_model3")
        probs.append(f"모델: {p3[0]:.0%}/{p3[1]:.0%}/{p3[2]:.0%}" if p3 else f"모델: {jg['p_model']:.1%}")
    else:
        probs.append("모델: 무효(데이터 없음)")
    if jg.get("p_claude") is not None:
        probs.append(f"Claude: {jg['p_claude']:.0%}")
    lines.append(". ".join(probs) + ".")

    ps = jg.get("pick_summary")
    if ps:  # 카드와 동일한 앙상블(p_final) 수치만 인용 — 확률 소스 단일화
        flag_txt = f" ⚠️{ps['flags'][0]}" if ps.get("flags") else ""
        ok_txt = "" if ps.get("approved") else f" [제외: {ps.get('reject_reason')}]"
        lines.append(
            f"밸류: {ps.get('desc') or _kr(ps['side'])} @{ps['odds']:.2f} — p_final {ps['p_final']:.0%}, "
            f"EV {ps['ev']:+.1%} (근거: {ps.get('axes') or '?'}){ok_txt}{flag_txt}")

    board = jg.get("market_board") or []
    if board:  # ⑧ 마켓 보드 — 전 마켓 한 줄 판정
        lines.append("⑧ 마켓 보드:")
        ordered = sorted(board, key=lambda c: (not c.get("approved"), -c["ev"]))
        for c in ordered[:6]:
            if c.get("approved"):
                verdict_txt = f"✅추천후보 EV {c['ev']:+.1%} · 근거 {c.get('axes_kr', '?')}"
                if c.get("basis") == "시장 기준":
                    verdict_txt += "(시장 기준)"
            else:
                verdict_txt = f"제외 — {c.get('reject_reason')}"
            lines.append(f"  {c['desc']} @{c['odds']:.2f} ({verdict_txt})")

    eps = jg.get("expert_picks") or []
    if eps:
        for ep in eps[:3]:
            rec = f" (전적 {ep['record']})" if ep.get("record") else " (전적 미상 — 0.5표)"
            reason = f" — {ep['reasoning'][:150]}" if ep.get("reasoning") else ""
            adopt = "" if ep.get("adopted", True) else " [불채택 — 해당 마켓 전적 마이너스, 인용 데이터만 참고]"
            lines.append(f"전문가: [{ep.get('site', '?')}] {ep.get('expert', '?')}: {ep['pick']}{reason}{rec}{adopt}")
    else:
        lines.append("전문가: 전문가 픽 미수집")

    news_hits = _team_news_lines(news or "", jg["home"], jg["away"])
    lines.append("속보: " + (news_hits[0].strip()[:200] if news_hits else "특이사항 없음"))
    for note in jg.get("breaking_changes", []) or []:
        lines.append(f"🔄 {note[:150]}")
    if jg.get("verdict"):
        v = jg["verdict"]
        lines.append(f"판단: {v[:600]}" + ("…" if len(v) > 600 else ""))
        if jg.get("reversal_factor"):
            lines.append(f"반전 요인: {jg['reversal_factor'][:200]}")
        if jg.get("judge_confidence"):
            tag = {"high": "높음", "medium": "보통", "low": "낮음(참고만)"}
            second = " · 2차 검증 반영" if jg.get("second_opinion") else ""
            lines.append(f"신뢰도: {tag.get(jg['judge_confidence'], '?')}{second}")
    return "\n".join(lines[:36])


def render_news(analysis: dict) -> str:
    """📰 부상·속보 — 분석 대상 경기 관련만, 경기별 매핑. 15줄 상한."""
    news = (analysis.get("news") or "").strip()
    scheduled = [g for g in analysis.get("games", []) if g.get("status") == "scheduled"]
    lines: list[str] = []
    for g in scheduled:
        hits = _team_news_lines(news, g["home"], g["away"])
        for h in hits[:2]:
            lines.append(f"[{_kr(g['home'])} vs {_kr(g['away'])}] {h.strip()[:160]}")
    if not lines:
        return "분석 대상 경기 관련 속보가 없습니다."
    return "\n".join(lines[:15])


def render_sources(analysis: dict) -> str:
    """📎 출처 — 항목별 리스트를 개행으로만 연결 + 보이지 않는 문자 제거 (플레인)."""
    sources = analysis.get("sources") or []
    if not sources:
        return "이번 분석에 수집된 출처가 없습니다."
    items = [
        f"- {clean_invisible(s['site'])}: {clean_invisible(s['url'])}"
        for s in sources[:30]
    ]
    return "\n".join(items)


def default_date(sport: str) -> str:
    return mlb_slate_date() if sport == "mlb" else today_kst()


def _render_card(analysis: dict) -> str:
    """결론 카드 2층: 보이는 줄은 쉬운 말(20줄), 수치 근거는 <<DETAIL>> 뒤(접힘)."""
    games = analysis.get("games", [])
    scheduled = [g for g in games if g.get("status") == "scheduled"]
    picks = analysis.get("picks", [])
    recommended = [p for p in picks if p.get("recommended")]
    combos_info = analysis.get("combos") or {}
    sport_kr = "MLB" if analysis.get("sport") == "mlb" else "축구"
    league_set = {g.get("league") for g in games}
    scope = f" ({next(iter(league_set))})" if len(league_set) == 1 and games else ""

    lines = [f"📌 {analysis.get('date')} {sport_kr}{scope} {len(games)}경기"]
    detail = ["📊 상세 데이터"]
    meta = analysis.get("research_meta") or {}
    if meta.get("refreshed"):
        lines.append(f"🔍 {meta['refreshed']}경기 최신 재조사 반영")
    if meta.get("stale_fallback") or meta.get("missing"):
        lines.append("⚠️ 일부 경기 새벽 데이터 기준 (최신 재조사 실패·미완)")
    if meta.get("quota"):
        lines.append("⚠️ 금일 리서치 쿼터 소진 — 이후 분석은 캐시 기준")
    if analysis.get("quota_warning"):
        lines.append("⚠️ 배당 데이터 잔여 쿼터 부족 — 배당 갱신이 지연될 수 있습니다")
    scored = [g for g in scheduled if g.get("p_market") is not None and g.get("p_claude") is not None]
    if scored:
        surest = max(scored, key=lambda g: {"high": 2, "medium": 1, "low": 0}.get(g.get("judge_confidence", "medium"), 1) * 100 - abs(g["p_claude"] - g["p_market"]) * 100)
        disputed = max(scored, key=lambda g: abs(g["p_claude"] - g["p_market"]))
        lines.append(f"가장 자신 있는 경기: {_kr(surest['home'])} vs {_kr(surest['away'])} — 시장과 봇 판단이 같은 곳을 봅니다")
        lines.append(f"데이터가 갈리는 경기: {_kr(disputed['home'])} vs {_kr(disputed['away'])} — 서로 다른 답을 내놓은 경기입니다")
        detail.append(f"확신도 최고: {_kr(surest['home'])} vs {_kr(surest['away'])} — 시장 {surest['p_market']:.0%} / 판정 {surest['p_claude']:.0%} (신뢰도 {surest.get('judge_confidence')})")
        detail.append(f"논쟁: {_kr(disputed['home'])} vs {_kr(disputed['away'])} — 시장 {disputed['p_market']:.0%} vs 판정 {disputed['p_claude']:.0%}")
    for g in scheduled:
        if g.get("breaking_note"):
            lines.append(g["breaking_note"])
    if analysis.get("parlay_rebuilt_note"):
        lines.append(analysis["parlay_rebuilt_note"])

    lines.append("")
    lines.append("🎯 오늘의 추천")
    if recommended:
        for p in recommended:
            stake = f" (권장 {p['stake_krw']:,}원)" if p.get("stake_krw") else ""
            lines.append(
                f"· {p.get('desc') or _kr(p['side'])} @{p['odds']:.2f} — "
                f"{_kr(p['home'])} vs {_kr(p['away'])}, "
                f"{_times_out_of_ten(p['p'])} 적중하는 계산인데 배당이 후한 편입니다"
                f" [{p.get('league', '?')} {p['starts_at_kst'][-5:]}]{stake}")
            detail.append(
                f"{p.get('desc')}: p_final {p['p']:.1%} / EV {p['ev']:+.1%} / "
                f"배당에 깔린 확률 {1 / p['odds']:.1%} / 근거 {p.get('axes') or '?'} / "
                f"판정 신뢰도 {p.get('confidence')}")
    else:
        lines.append("오늘은 배당 대비 이득 기준을 넘는 단식 픽이 없습니다 — 관망 권장")
    if combos_info.get("reason"):
        lines.append(f"조합: {combos_info['reason']}")
    else:
        for i, c in enumerate(combos_info.get("combos", []), 1):
            if not c.get("ok"):
                lines.append(f"조합 {i}({c['tier']}): {c['reason']}")
                continue
            legs_txt = " + ".join(
                f"{leg['desc']}[{leg.get('league', '?')} {leg['starts_at_kst'][-5:]}]"
                for leg in c["legs"])
            relax = " (범위 완화)" if c.get("relaxed") else ""
            lines.append(f"조합 {i}({c['tier']}): {legs_txt} @{c['odds']:.2f} "
                         f"(적중률 {c['p']:.0%}) — {c['stake_note']}{relax}")
            detail.append(f"조합 {i} 레그별 확률: " + ", ".join(
                f"{leg['desc']} {leg['p']:.0%}@{leg['odds']:.2f}" for leg in c["legs"]))
        if combos_info.get("all_fail_prob") is not None:
            lines.append(f"세 조합 모두 실패할 확률 ≈ {combos_info['all_fail_prob']:.0%}")
        if combos_info.get("low_confidence"):
            lines.append("⚠️ 오늘은 확신이 낮은 날 — 권장액 절반만")
    lines.append("⚠️ 조합은 변동이 큰 베팅 — 단식 권장액의 절반 이하 소액만")

    easy = "\n".join(lines[:20])[:3500]
    return _guard_basic(easy + DETAIL_SEP + "\n".join(detail[:20]), "card")


async def generate_card(analysis: dict) -> str:
    """결론 카드 생성 — 결정적 렌더 (LLM 미사용: 한국어·수치 일관성 보장)."""
    return _render_card(analysis)


def rescope_analysis(analysis: dict, league_label: str) -> dict:
    """전체 슬레이트 분석 → 리그 스코프 뷰 (재계산·API 콜 없음, 캐시 추출 전용)."""
    from app.engine.parlay import build_tiered_parlays

    settings = get_settings()
    games = [g for g in analysis["games"] if g.get("league") == league_label]
    ids = {g["game_id"] for g in games}
    picks = [dict(p) for p in analysis.get("picks", []) if p["game_id"] in ids]
    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    clean = [p for p in picks if p.get("approved") and not p["judge_excluded"]
             and p["ev"] > settings.ev_threshold]
    clean.sort(key=lambda x: x["ev"], reverse=True)
    recommended = clean[: mode["max_picks"]]
    for p in picks:
        p["recommended"] = p in recommended
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    urls = {ep.get("source_url") for g in games for ep in g.get("expert_picks", [])}
    sources = [s for s in analysis.get("sources", []) if s["url"] in urls]
    return {
        **analysis, "games": games, "picks": picks,
        "combos": build_tiered_parlays(approved_market_legs(games), stake_krw),
        "sources": sources,
    }


def render_full_reco(analyses: list[dict]) -> str:
    """🎯 전체 추천 카드 — 후보 풀은 그날 전체 슬레이트(MLB+축구 전 리그)."""
    from app.engine.parlay import build_tiered_parlays

    settings = get_settings()
    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    all_picks = [p for a in analyses for p in a.get("picks", [])]
    clean = [p for p in all_picks if p.get("approved") and not p["judge_excluded"]]
    ev_ok = sorted([p for p in clean if p["ev"] > settings.ev_threshold],
                   key=lambda x: x["ev"], reverse=True)
    singles = ev_ok[: mode["max_picks"]]
    all_games = [g for a in analyses for g in a.get("games", [])]
    combos = build_tiered_parlays(approved_market_legs(all_games), stake_krw)

    covered = " + ".join(
        ("MLB" if a["sport"] == "mlb" else "축구") for a in analyses)
    lines = [f"🎯 오늘 전체 추천픽 (후보 풀: {covered} 전체 슬레이트)"]
    detail = ["📊 상세 데이터"]
    if singles:
        for p in singles:
            stake = f" (권장 {p['stake_krw']:,}원)" if p.get("stake_krw") else ""
            lines.append(f"· {p.get('desc') or _kr(p['side'])} @{p['odds']:.2f} — "
                         f"{_kr(p['home'])} vs {_kr(p['away'])}, "
                         f"{_times_out_of_ten(p['p'])} 적중하는 계산이고 배당이 후한 편입니다"
                         f" [{p.get('league', '?')} {p['starts_at_kst'][-5:]}]{stake}")
            detail.append(f"{p.get('desc')}: p_final {p['p']:.1%} / EV {p['ev']:+.1%} / "
                          f"배당에 깔린 확률 {1 / p['odds']:.1%} / 근거 {p.get('axes') or '?'}")
    else:
        lines.append("오늘은 배당 대비 이득 기준을 넘는 단식 픽이 없습니다 — 관망 권장")
    if combos.get("reason"):
        lines.append(f"조합: {combos['reason']}")
    else:
        for i, c in enumerate(combos.get("combos", []), 1):
            if not c.get("ok"):
                lines.append(f"조합 {i}({c['tier']}): {c['reason']}")
                continue
            legs_txt = " + ".join(
                f"{leg['desc']}[{leg.get('league', '?')} {leg['starts_at_kst'][-5:]}]"
                for leg in c["legs"])
            relax = " (범위 완화)" if c.get("relaxed") else ""
            lines.append(f"조합 {i}({c['tier']}): {legs_txt} @{c['odds']:.2f} "
                         f"(적중률 {c['p']:.0%}) — {c['stake_note']}{relax}")
        if combos.get("all_fail_prob") is not None:
            lines.append(f"세 조합 모두 실패 확률 ≈ {combos['all_fail_prob']:.0%}")
        if combos.get("low_confidence"):
            lines.append("⚠️ 오늘은 확신도 낮음 — 권장액 절반")
    lines.append("⚠️ 조합은 변동이 큰 베팅 — 단식 권장액의 절반 이하 소액만")
    return _guard_basic("\n".join(lines[:20])[:3500] + DETAIL_SEP + "\n".join(detail[:15]), "full_reco")


# ---------------------------------------------------------------- 진입점

def mlb_slate_date() -> str:
    """MLB 슬레이트 날짜 = 미국 동부 기준 오늘 (KST 새벽·아침엔 전날 미국 경기)."""
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


async def _save_caches(redis: aioredis.Redis, analysis: dict, card: str) -> None:
    settings = get_settings()
    sport, date = analysis["sport"], analysis["date"]
    await redis.set(f"analysis:{sport}:{date}",
                    json.dumps(analysis, ensure_ascii=False, default=str),
                    ex=settings.report_cache_ttl)
    await redis.set(f"card:{sport}:{date}", card, ex=settings.report_cache_ttl)


async def _rejudge_after_breaking(analysis: dict, changes: list[dict]) -> dict:
    """중대 속보 변화 경기만 judge 재실행 → verdict·픽·조합 갱신 + 🔄 표시."""
    from app.collectors.football import similar_team

    settings = get_settings()
    affected = []
    for ch in changes:
        try:
            away, home = (s.strip() for s in ch["game"].split("@"))
        except ValueError:
            continue
        for jg in analysis["games"]:
            if (jg["status"] == "scheduled"
                    and similar_team(jg["home"], home) and similar_team(jg["away"], away)):
                jg.setdefault("breaking_changes", []).append(ch["change"])
                if jg not in affected:
                    affected.append(jg)
    if not affected:
        return analysis

    payload = {
        "date": analysis["date"], "sport": analysis["sport"], "games": affected,
        "breaking_news": analysis["news"],
        "instruction": (
            "각 경기의 breaking_changes에 판정 이후 발생한 중대 속보가 있다. "
            "기존 판정(verdict·p_claude)을 재검토해 재산출하라."
        ),
    }
    try:
        verdict2 = await Judge().judge(payload)
    except (ApiQuotaError, Exception) as exc:
        logger.warning("[pipeline] breaking re-judge failed, keeping cached verdicts: %s", exc)
        return analysis

    old_reco = {p["pick"] for p in analysis["picks"] if p.get("recommended")}
    old_parlay_legs = {
        leg["pick"] for pl in analysis.get("parlays", []) for leg in pl["legs"]
    }
    by_id = {g["game_id"]: g for g in verdict2.get("games", [])}
    for jg in affected:
        v = by_id.get(jg["game_id"])
        if not v:
            continue
        old_p = jg.get("p_claude")
        jg["p_claude"] = v["p_claude"]
        jg["verdict"] = v["verdict"]
        jg["judge_pass"] = bool(v.get("pass_recommended"))
        jg["judge_confidence"] = v.get("confidence", "medium")
        jg["reversal_factor"] = v.get("reversal_factor") or ""
        jg["conclusion_revised"] = bool(v.get("conclusion_revised"))
        jg["excluded_picks"] = v.get("excluded_picks", [])
        change_txt = "; ".join(jg.get("breaking_changes", []))[:120]
        old_txt = f"{old_p:.0%}" if old_p is not None else "?"
        jg["breaking_note"] = (
            f"🔄 속보 반영: {change_txt} → 승률 계산 {old_txt}→{v['p_claude']:.0%}"
            + (", 패스로 전환" if jg["judge_pass"] else "")
        )

    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], analysis["sport"])
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    # 조합도 재구성 (판정 뒤집힌 레그 반영) — 전 마켓 승인 풀 기준
    from app.engine.parlay import build_tiered_parlays

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    analysis["combos"] = build_tiered_parlays(approved_market_legs(analysis["games"]), stake_krw)
    flipped = old_reco - {p["pick"] for p in picks_out if p.get("recommended")}
    if flipped & old_parlay_legs:
        analysis["parlay_rebuilt_note"] = (
            "⚠️ 속보로 판정이 뒤집힌 픽이 기존 조합에 포함되어 있어 조합을 재구성했습니다."
        )
    logger.info("[pipeline] re-judged %d games after breaking news", len(affected))
    return analysis


async def _refresh_stale_research(
    pool: asyncpg.Pool, redis: aioredis.Redis, analysis: dict,
) -> int:
    """[3] 캐시 응답 전 — 신선도 게이트 위반 경기만 재리서치 + 해당 경기 재판정.

    반환: 재조사된 경기 수. 실패 경기는 구캐시 폴백('새벽 데이터 기준' 표기).
    """
    from app.research.deep import RESEARCH_CONCURRENCY, get_game_research

    settings = get_settings()
    sport = analysis["sport"]
    scheduled = [g for g in analysis["games"] if g.get("status") == "scheduled"]
    if not scheduled:
        return 0
    sem = asyncio.Semaphore(RESEARCH_CONCURRENCY)
    refreshed: list[dict] = []

    async def one(jg: dict) -> None:
        async with sem:
            data, status = await get_game_research(redis, jg, sport)
        jg["research_status"] = status
        if status == "refreshed" and data is not None:
            jg["research"] = data
            refreshed.append(jg)

    await asyncio.gather(*(one(jg) for jg in scheduled))
    meta = analysis.setdefault("research_meta", {})
    meta["stale_fallback"] = sum(
        1 for g in scheduled if g.get("research_status") == "stale_fallback")
    if not refreshed:
        return 0

    # 재조사 경기만 재판정 → 픽·조합 재계산
    payload = {
        "date": analysis["date"], "sport": sport, "games": refreshed,
        "breaking_news": analysis.get("news", ""),
        "instruction": "각 경기의 research가 방금 최신으로 갱신되었다. 최신 데이터 기준으로 판정을 재산출하라.",
    }
    try:
        verdict = await Judge().judge(payload)
        _attach_verdicts(refreshed, verdict)
    except Exception as exc:
        logger.warning("[pipeline] refresh re-judge failed, keeping verdicts: %s", exc)
        if isinstance(exc, ApiQuotaError):
            await notify_quota(exc.service, exc.detail)
    _enforce_data_rules(analysis["games"])
    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport)
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    from app.engine.parlay import build_tiered_parlays

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    analysis["combos"] = build_tiered_parlays(approved_market_legs(analysis["games"]), stake_krw)
    meta["refreshed"] = len(refreshed)
    logger.info("[pipeline] freshness gate: %d games re-researched & re-judged", len(refreshed))
    return len(refreshed)


async def ensure_game_fresh(sport: str, date: str, game_id: int) -> tuple[dict | None, bool]:
    """경기 버튼·팀 질문용 — 해당 경기만 신선도 게이트 적용 후 (analysis, 재조사 여부) 반환."""
    from app.db import get_pool
    from app.research.deep import get_game_research

    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await redis.get(f"analysis:{sport}:{date}")
        if not raw:
            return None, False
        analysis = json.loads(raw)
        jg = next((g for g in analysis["games"] if g["game_id"] == game_id), None)
        if jg is None or jg.get("status") != "scheduled":
            return analysis, False
        data, status = await get_game_research(redis, jg, sport)
        jg["research_status"] = status
        if status != "refreshed" or data is None:
            return analysis, False
        jg["research"] = data
        settings = get_settings()
        payload = {
            "date": date, "sport": sport, "games": [jg],
            "breaking_news": analysis.get("news", ""),
            "instruction": "이 경기의 research가 방금 최신으로 갱신되었다. 최신 데이터 기준으로 판정을 재산출하라.",
        }
        try:
            verdict = await Judge().judge(payload)
            _attach_verdicts([jg], verdict)
        except Exception as exc:
            logger.warning("[pipeline] single-game re-judge failed: %s", exc)
            if isinstance(exc, ApiQuotaError):
                await notify_quota(exc.service, exc.detail)
        _enforce_data_rules(analysis["games"])
        picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport)
        analysis["picks"], analysis["parlays"] = picks_out, parlays
        meta = analysis.setdefault("research_meta", {})
        meta["refreshed"] = (meta.get("refreshed") or 0) + 1
        await redis.set(f"analysis:{sport}:{date}", json.dumps(analysis, ensure_ascii=False, default=str),
                        ex=settings.report_cache_ttl)
        card = await generate_card(analysis)
        await redis.set(f"card:{sport}:{date}", card, ex=settings.report_cache_ttl)
        return analysis, True
    finally:
        await redis.aclose()


async def _freshness_gate(
    redis: aioredis.Redis, sport: str, date: str, cached_card: str
) -> str:
    """캐시 응답 전에 Grok 최신 체크 — 중대 변화 시 해당 경기만 재판정 후 카드 갱신.

    변화 없으면 5분간 재확인 생략(freshcheck 키) 후 캐시 즉답 (추가 판정 콜 0).
    """
    from app.research.grok import GrokClient

    settings = get_settings()
    fresh_key = f"freshcheck:{sport}:{date}"
    if settings.mock_grok or await redis.get(fresh_key):
        return cached_card
    raw = await redis.get(f"analysis:{sport}:{date}")
    if not raw:
        return cached_card
    analysis = json.loads(raw)
    upcoming = [g for g in analysis["games"] if g["status"] == "scheduled"]
    if not upcoming:
        await redis.set(fresh_key, "1", ex=300)
        return cached_card
    # [3] 리서치 신선도 게이트 — 6시간 초과·킥오프 3시간 이내 경기 재리서치+재판정
    from app.db import get_pool as _get_pool

    refreshed_n = 0
    try:
        refreshed_n = await _refresh_stale_research(await _get_pool(), redis, analysis)
    except Exception as exc:
        logger.warning("[pipeline] stale-research refresh failed, serving cache: %s", exc)
    if refreshed_n:
        card = await generate_card(analysis)
        if settings.report_banner:
            card = f"{settings.report_banner}\n\n{card}"
        await _save_caches(redis, analysis, card)
        cached_card = card
    try:
        changes = await GrokClient().delta_check(analysis.get("news", ""), upcoming, date)
    except Exception as exc:
        logger.warning("[pipeline] delta check failed, serving cache: %s", exc)
        return cached_card
    if not changes:
        await redis.set(fresh_key, "1", ex=300)
        return cached_card
    logger.info("[pipeline] breaking changes detected: %s", changes)
    analysis = await _rejudge_after_breaking(analysis, changes)
    card = await generate_card(analysis)
    if settings.report_banner:
        card = f"{settings.report_banner}\n\n{card}"
    await _save_caches(redis, analysis, card)
    await redis.set(fresh_key, "1", ex=300)
    return card


async def run_pipeline(
    pool: asyncpg.Pool,
    redis: aioredis.Redis,
    sport: str = "mlb",
    date: str | None = None,
    force_refresh: bool = False,
    progress=None,
) -> str:
    """결론 카드(단일 메시지)를 반환. 심층·속보·출처는 분석 캐시에서 버튼으로 제공."""
    settings = get_settings()
    # 날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 표기는 항상 KST.
    date = date or default_date(sport)
    if not force_refresh:
        cached = await redis.get(f"card:{sport}:{date}")
        if cached:
            logger.info("[pipeline] cache hit: card:%s:%s", sport, date)
            # 속보의 결론 반영: 캐시 응답 전에 최신 체크 → 중대 변화 시 재판정
            return await _freshness_gate(redis, sport, date, cached)
    analysis = await build_analysis(pool, sport, date, progress=progress, redis=redis)
    await (progress or _noop_progress)(4, 4, "결론 카드 작성")
    remaining = await redis.get("odds_quota_remaining")
    if remaining is not None and int(remaining) < 100:
        analysis["quota_warning"] = True
    card = await generate_card(analysis)
    if settings.report_banner:
        card = f"{settings.report_banner}\n\n{card}"
    await _save_caches(redis, analysis, card)
    return card


async def _cli() -> None:
    """텔레그램 없이 파이프라인 직접 호출: python -m app.pipeline --sport mlb"""
    import argparse
    import time

    import redis.asyncio as aioredis_

    from app.db import close_pool, get_pool

    parser = argparse.ArgumentParser(description="AnalystBot pipeline CLI")
    parser.add_argument("--sport", default="mlb", choices=["mlb", "soccer"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (기본: MLB는 미국 동부 오늘)")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    date = args.date or (mlb_slate_date() if args.sport == "mlb" else today_kst())
    pool = await get_pool()
    redis = aioredis_.from_url(get_settings().redis_url, decode_responses=True)
    try:
        t0 = time.monotonic()
        report = await run_pipeline(pool, redis, args.sport, date, args.force_refresh)
        elapsed = time.monotonic() - t0
        print(report)
        print(f"\n[elapsed {elapsed:.2f}s]")
    finally:
        await redis.aclose()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(_cli())
