"""파이프라인 오케스트레이터.

(일정+스탯 ∥ 배당 ∥ 딥서치) 병렬 수집 → 엔진 계산 → judge → 리포트 생성(Sonnet,
판정 JSON만 근거로 한국어) → Redis 30분 캐시.
"""

import asyncio
import json
import logging
import re
from functools import lru_cache
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import anthropic
import asyncpg
import redis.asyncio as aioredis

from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError
from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer_games
from app.collectors.mlb import MLBClient, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds
from app.config import get_settings
from app.engine.consensus import consensus_scores, load_expert_weights
from app.engine.judge import Judge
from app.engine.parlay import best_parlays
from app.engine.value import devig, ensemble, ev, heuristic_model_prob, implied_prob, kelly
from app.notify import notify_api_error
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
    sport: str = "mlb", redis=None, sequential: bool = False,
) -> tuple[str, list[str], dict, dict]:
    """Grok 속보(슬레이트 1콜) ∥ 경기별 심층 리서치.

    반환: (news, news_urls, research_map{game_id: dict}, statuses{game_id: str}).
    리서치는 보조 신호 — 실패해도 파이프라인은 계속 간다 ('리서치 미완' 마킹).

    sequential=True(프리페치)는 전 경기 동시 실행 대신 **경기 단위 순차** 처리다.
    실사고: MLB 10경기 + 축구 17경기를 동시에 리서치해 Perplexity 429를 유발했다.
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
    if sequential:
        # 리그·경기 단위 순차 — 속보 1콜만 병행하고 리서치는 한 건씩 (레이트리밋 방어)
        news_fut = asyncio.ensure_future(news_task)
        for g in scheduled:
            try:
                await one(g)
            except Exception as exc:  # 개별 경기 실패는 전체를 막지 않는다
                logger.warning("[pipeline] 순차 리서치 실패 %s: %s", g.get("home"), exc)
                statuses[g["id"]] = "missing"
        news_res = (await asyncio.gather(news_fut, return_exceptions=True))[0]
    else:
        results = await asyncio.gather(
            news_task, *(one(g) for g in scheduled), return_exceptions=True)
        news_res = results[0]
    try:
        if isinstance(news_res, BaseException):
            logger.error("[pipeline] grok briefing failed, continuing without news: %s", news_res)
            await notify_api_error(news_res)
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
    redis=None, sequential_research: bool = False,
) -> dict:
    """league_key 지정 시 그 리그만 수집·판정 (요청 범위 밖 API 호출 금지).

    sequential_research=True(프리페치)는 경기별 리서치를 순차 처리해 429를 피한다.
    """
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
        _collect_research(pool, games, date, league, sport=sport, redis=redis,
                          sequential=sequential_research),
    )

    # [감시] 리서치 수치 ↔ statsapi 실데이터 교차검증 표본 (지어내기 감시)
    if redis is not None:
        from app.research.crosscheck import crosscheck_sample

        try:
            await crosscheck_sample(redis, games, research_map, stats, sport)
        except Exception as exc:   # 감시 실패가 분석을 막지 않는다
            logger.warning("[pipeline] crosscheck 실패: %s", exc)

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
            "sport": sport,   # [4] 출력 문구의 종목 분기 기준 (야구/축구 용어 오용 방지)
            "home": g["home"], "away": g["away"], "league": g["league"],
            "starts_at": g["starts_at"].isoformat(),
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "status": g["status"],
            "research": research_map.get(g["id"]),
            "research_status": research_statuses.get(g["id"], "missing"),
            "status_label": STATUS_LABELS.get(g["status"], ""),
            "lineup_status": g.get("lineup_status") or "none",
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
        except (ApiQuotaError, ApiAuthError, ApiRateLimitError) as exc:
            logger.error("[pipeline] judge 실패(%s) — 목 판정으로 폴백: %s",
                         type(exc).__name__, exc)
            await notify_api_error(exc)   # 레이트리밋은 알림 없이 내부 처리
            verdict = Judge._mock_verdict(judge_payload)
    _attach_verdicts(judge_games, verdict)

    # 4b) 2차 검증 — 논쟁 경기(저신뢰 또는 |모델-시장|≥10%p)만 Grok에 반대 근거 1콜.
    #     전 경기 적용 금지(비용). 반대 근거가 실체적일 때만 judge 재산출.
    verdict = await _second_opinion(judge_games, verdict, date, sport, news)
    _attach_verdicts(judge_games, verdict)

    # 4c) [7] 전 마켓 배당 부착 + [4d] 데이터 제로 강등 → 5) 마켓 풀 픽 계산
    await _attach_alt_markets(pool, judge_games)
    _enforce_data_rules(judge_games)

    # [§3] 라인 무브먼트 — 확률이 아니라 **신뢰도**만 조정한다.
    #      확률 계산(_compute_picks) 이후에 실행해야 확률에 스며들지 않는다.
    async def _apply_line_moves(games: list[dict]) -> None:
        from app.engine.linemove import attach_line_move

        for g in games:
            if g.get("status") != "scheduled" or not g.get("market_board"):
                continue
            try:
                await attach_line_move(pool, g)
            except Exception as exc:
                logger.warning("[pipeline] 라인 이동 계산 실패 game=%s: %s", g.get("game_id"), exc)

    statcast_data = None
    if redis is not None:
        try:
            if sport == "mlb":
                from app.collectors.statcast import load as load_statcast

                statcast_data = await load_statcast(redis, date)
                if statcast_data and statcast_data[0]:
                    logger.info("[pipeline] Statcast 캐시 — 팀 %d개 / 투수 %d명",
                                len(statcast_data[0]), len(statcast_data[1]))
            else:
                from app.collectors.soccer_stats import load_xg, supported

                by_league = {}
                for label in {g.get("league") for g in judge_games if g.get("league")}:
                    if supported(label):
                        by_league[label] = await load_xg(redis, label, date)
                statcast_data = (by_league, {})
                total = sum(len(v) for v in by_league.values())
                if total:
                    logger.info("[pipeline] Understat xG 캐시 — %d리그 %d팀",
                                len(by_league), total)
        except Exception as exc:
            logger.warning("[pipeline] 통계 소스 로드 실패, 리서치 지표만 사용: %s", exc)

    picks_out, parlays, recommended = _compute_picks(settings, judge_games, sport, statcast_data)
    # 라인 이동으로 신뢰도가 바뀌면 등급·추천이 달라지므로 픽을 다시 계산한다
    await _apply_line_moves(judge_games)
    picks_out, parlays, recommended = _compute_picks(settings, judge_games, sport, statcast_data)

    # [B-1] 판정과 서술을 분리 — 판정 결론 + 마켓 보드 + 리서치를 입력으로 별도 서술 단계.
    #       마켓 보드가 만들어진 뒤에 실행해야 서술이 '어느 마켓이 살았는지'를 안다.
    from app.engine.narrator import attach_narratives

    try:
        await attach_narratives(judge_games, sport)
    except Exception as exc:   # 서술 실패는 분석을 막지 않는다 (결정적 렌더로 폴백)
        logger.warning("[pipeline] 서술 단계 실패, 결정적 렌더로 진행: %s", exc)

    # [6] 병렬 채점 — 경기력 기반 픽과 시장 반영 픽을 **둘 다** 기록해
    #     2~3주 뒤 어느 방식이 실제로 맞히는지 비교한다.
    for p in recommended:
        await pool.execute(
            """
            INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                     p_market, p_ensemble, lineup_status, p_legacy, method,
                                     p_heuristic, p_learned, p_claude)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'performance',
                    $11, $12, $13)
            """,
            p["game_id"], p["pick"], p["p"], p["odds"], p["ev"], p["kelly"],
            p.get("p_market_side"), p.get("p_ensemble_side"),
            p.get("lineup_status") or "none", p.get("p_legacy"),
            p.get("p_heuristic"), p.get("p_learned"), p.get("p_claude"),
        )
    for p in _legacy_recommended(settings, picks_out):
        await pool.execute(
            """
            INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                     p_market, p_ensemble, lineup_status, p_legacy, method)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'legacy')
            """,
            p["game_id"], p["pick"], p.get("p_legacy") or p["p"], p["odds"], p["ev"],
            p["kelly"], p.get("p_market_side"), p.get("p_ensemble_side"),
            p.get("lineup_status") or "none", p.get("p_legacy"),
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

    combos = build_tiered_parlays(approved_market_legs(judge_games), stake_krw, sport)

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


def _to_gid(value):
    """판정이 game_id를 문자열로 돌려줘도 매칭되게 정규화."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


async def _renarrate(games: list[dict], sport: str) -> None:
    """재판정된 경기의 서술을 다시 쓴다 — 판정이 바뀌었는데 글이 그대로면 안 된다."""
    if not games:
        return
    from app.engine.narrator import attach_narratives

    try:
        await attach_narratives(games, sport)
    except Exception as exc:
        logger.warning("[pipeline] 재서술 실패, 기존 서술 유지: %s", exc)


def _attach_verdicts(judge_games: list[dict], verdict: dict) -> None:
    by_id = {_to_gid(g.get("game_id")): g for g in verdict.get("games", [])}
    matched = 0
    for jg in judge_games:
        v = by_id.get(_to_gid(jg["game_id"]))
        if v is None:
            continue
        matched += 1
        jg["p_claude"] = v["p_claude"]
        jg["verdict"] = v["verdict"]
        jg["excluded_picks"] = v.get("excluded_picks", [])
        jg["judge_pass"] = bool(v.get("pass_recommended"))
        jg["judge_confidence"] = v.get("confidence", "medium")
        jg["reversal_factor"] = v.get("reversal_factor") or ""
        jg["conclusion_revised"] = bool(v.get("conclusion_revised"))
    targets = [g for g in judge_games if g.get("status") == "scheduled"]
    if targets and matched == 0:
        logger.error("[pipeline] 판정 부착 0건 — 분석 대상 %d경기 중 매칭 실패 "
                     "(판정 game_id=%s)", len(targets), list(by_id)[:5])
    elif matched < len(targets):
        logger.warning("[pipeline] 판정 부착 %d/%d경기 — 일부 경기 판정 누락",
                       matched, len(targets))


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


ODDS_STALE_HOURS = 3   # 이보다 오래된 스냅샷은 '개장 배당'으로 표기


async def _attach_alt_markets(pool: asyncpg.Pool, judge_games: list[dict]) -> None:
    """[7] 핸디캡·토탈 수집 배당 부착 + [A-3] 스냅샷 신선도 라벨.

    배당 조회는 북별 최신 스냅샷을 모으므로 (a)다른 북메이커 (b)마지막 프리게임
    스냅샷 폴백이 이미 내장돼 있다. 다만 그 스냅샷이 오래됐으면 현재가가 아니므로
    '(개장 배당)'으로 표기해 사용자가 구분할 수 있게 한다.
    """
    for jg in judge_games:
        if jg.get("status") != "scheduled":
            continue
        jg["alt_markets"] = await _alt_market_rows(pool, jg["game_id"], jg["home"], jg["away"])
        newest = await pool.fetchval(
            "SELECT max(captured_at) FROM odds_snapshots WHERE game_id = $1", jg["game_id"])
        if newest is not None:
            age_h = (datetime.now(UTC) - newest).total_seconds() / 3600
            jg["odds_stale"] = age_h > ODDS_STALE_HOURS
        else:
            jg["odds_stale"] = False


def _legacy_recommended(settings, picks: list[dict], n: int = 2) -> list[dict]:
    """[6] 참고용 시장 반영 방식이 골랐을 픽 — 기존 EV 기준으로 상위 N개.

    실제 추천에는 쓰지 않는다. 채점기가 두 방식을 나란히 집계하기 위한 기록이다.
    """
    pool = [p for p in picks
            if p.get("approved") and not p.get("judge_excluded")
            and p.get("ev") is not None and p["ev"] > settings.ev_threshold]
    pool.sort(key=lambda x: x["ev"], reverse=True)
    return pool[:n]


def _pick_state(jg: dict) -> tuple[str, str]:
    """[2-1] 픽 상태 — 라인업 확정 전은 예비 픽, 확정 후만 최종 픽."""
    from app.collectors.lineups import pick_state

    return pick_state(jg.get("lineup_status"))


def _learned_probs(jg: dict, research: dict, sport: str, settings) -> dict | None:
    """[§6-4] 학습 계수 λ 모델의 승패 확률. 아티팩트가 없으면 None.

    **추천에는 쓰지 않는다** — 병렬 채점으로 실전 성능을 비교하기 위한 기록이다.
    반영 여부는 검증 결과를 보고 사용자가 판단한다.
    """
    if sport != "mlb":
        return None
    try:
        from app.models.lambda_model import predict_game

        return predict_game(jg, research, settings)
    except Exception:
        return None


def qualifies(pick: dict, settings=None) -> bool:
    """[3-1][4] 추천 자격 = 승률 하한 AND 배당 하한. 원정 픽은 임계가 5%p 높다."""
    from app.config import get_settings

    s = settings or get_settings()
    p, odds = pick.get("p"), pick.get("odds")
    need = pick.get("required_prob") or s.min_win_prob
    if pick.get("two_source") is False:      # [6] 2-소스 룰은 추천 자격에만 적용
        return False
    if pick.get("edge_excess"):              # §0 시장 대비 괴리 과다 = 데이터 오류 의심
        return False
    return p is not None and odds is not None and p >= need and odds >= s.min_odds


def near_miss_picks(picks: list[dict], settings=None, n: int = 3) -> list[dict]:
    """[3-1] 자격 미달이어도 승률 상위 N개는 사유와 함께 보여준다 ('픽 없음'으로 끝내지 않는다)."""
    from app.config import get_settings

    s = settings or get_settings()
    pool = [p for p in picks if p.get("p") is not None and not qualifies(p, s)]
    pool.sort(key=lambda x: x["p"], reverse=True)
    out = []
    for p in pool[:n]:
        reasons = []
        if p["p"] < s.min_win_prob:
            reasons.append(f"승률 {p['p']:.0%} < {s.min_win_prob:.0%}")
        if (p.get("odds") or 0) < s.min_odds:
            reasons.append(f"배당 {p.get('odds') or 0:.2f} < {s.min_odds:.2f}")
        out.append({**p, "miss_reason": " · ".join(reasons) or "미승인"})
    return out


def approved_market_legs(games: list[dict]) -> list[dict]:
    """[9] 조합 후보 풀 = 전 마켓 승인 픽 (판정 제외·저신뢰 경기는 이미 미승인)."""
    legs = []
    for jg in games:
        if jg.get("status") != "scheduled":
            continue
        for c in jg.get("market_board") or []:
            if c.get("approved") and qualifies(c):
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
    settings, judge_games: list[dict], sport: str, statcast_data: tuple | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """jg(판정 부착 완료) → (전체 픽, 파레이, 추천 픽). DB 접근 없음 — 재판정 시 재사용.

    [7] 경기별 전 마켓 후보 평가 → jg["market_board"].
    [1][2][3] 승인 규칙(2-소스·괴리 검증·저분산 우선)은 engine.markets._approve.
    [5] p_final = λ*p_market + (1-λ)*p_ensemble (리그 성숙도 연동 수축).
    경기 대표 픽 = 승인 후보 중 EV 최대 (없으면 진단용 최고 EV 후보, 미승인 표기).
    """
    from app.engine.markets import build_board

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None

    def blend(p_model_s: float | None, p_market_s: float, p_claude_s: float) -> float:
        """[1-1] 경기력 앙상블 — **시장 확률은 쓰지 않는다**.

        p_final = 0.5*p_model + 0.5*p_claude. 배당은 "이기면 얼마 받는가"에만 쓴다.
        모델이 무효면 Claude 단독. (p_market_s는 병렬 채점·표시용으로만 받는다)
        """
        if p_model_s is None:
            return p_claude_s
        w_m, w_c = settings.ensemble_w_model, settings.ensemble_w_claude
        return (w_m * p_model_s + w_c * p_claude_s) / (w_m + w_c)

    def blend_legacy(p_model_s: float | None, p_market_s: float, p_claude_s: float) -> float:
        """[6] 병렬 채점용 — 기존 시장 반영 앙상블. 판정에는 쓰지 않는다."""
        if p_model_s is None:
            w = settings.legacy_w_market + settings.legacy_w_claude
            return (settings.legacy_w_market * p_market_s
                    + settings.legacy_w_claude * p_claude_s) / w
        return ensemble(p_model_s, p_market_s, p_claude_s,
                        settings.legacy_w_model, settings.legacy_w_market,
                        settings.legacy_w_claude)

    picks_out = []
    for jg in judge_games:
        if jg["status"] != "scheduled":
            continue
        # 판정을 못 받아도 마켓 보드는 만든다 — 다만 어떤 마켓도 추천하지 않는다.
        jg["judge_missing"] = "p_claude" not in jg
        if jg["judge_missing"]:
            logger.warning("[pipeline] game %s 판정 미수신 — 배당 %d개/알트 %d개로 "
                           "보드만 구성 (추천 제외)", jg["game_id"],
                           len(jg.get("best_odds") or {}), len(jg.get("alt_markets") or []))
        # [A-2] h2h 배당이 없다고 경기 전체를 죽이지 않는다 — 없는 마켓만 빠진다.
        market = jg.get("market_probs") or {}
        h2h_priced = bool(market) and jg["home"] in market and jg["away"] in market

        # 사이드별 확률: 축구는 무승부 질량 때문에 1-p_home ≠ p_away — 시장 3-way 기준
        p_draw_m = market.get("Draw", 0.0)
        p_final: dict[str, float] = {}
        p_ens: dict[str, float] = {}
        if jg["judge_missing"]:
            h2h_priced = False        # 앙상블 확률을 만들 수 없다 → h2h는 '근거 부족' 행
        p_claude_home = jg.get("p_claude") or 0.5
        p_claude_away = max(0.0, min(1.0, 1.0 - p_claude_home - p_draw_m))
        p3 = jg.get("p_model3")
        league_lam = "MLB" if sport == "mlb" else jg.get("league")
        sides = (
            (jg["home"], (p3[0] if p3 else (jg["p_model"] if jg.get("model_valid") else None)),
             market.get(jg["home"], 0.5), p_claude_home),
            (jg["away"], (p3[2] if p3 else ((1 - jg["p_model"]) if jg.get("model_valid") and sport == "mlb" else None)),
             market.get(jg["away"], 0.5), p_claude_away),
        ) if h2h_priced else ()
        # [2][3] 기대득점(λ) 분포 — 학술 방법론(포아송/스켈람)이 1순위 확률 소스다.
        #        분포가 서면 전 마켓 확률이 같은 분포에서 나오고, 경기력 조정(%p 가산)은
        #        중복 계산이 되므로 쓰지 않는다. 핵심 지표가 없을 때만 조정 방식으로 폴백.
        from app.engine.performance import WinProbAdjuster
        from app.engine.scoring import game_distribution
        from app.research.validate import sanitize_research

        research_clean, _ = sanitize_research(jg.get("research") or {}, sport)
        # [2-1] Statcast 지표를 얹는다 — 리서치 산문보다 정확한 1차 소스
        if sport == "mlb" and statcast_data:
            from app.collectors.statcast import merge_into_research

            filled = merge_into_research(research_clean, jg, *statcast_data)
            if filled:
                jg["statcast_filled"] = filled
        # [§2-3] Understat xG — 축구 λ의 1차 입력 (산문 파싱 대체)
        elif sport == "soccer" and statcast_data:
            from app.collectors.soccer_stats import merge_xg_into_research

            windows = (statcast_data[0] or {}).get(jg.get("league")) or {}
            filled = merge_xg_into_research(research_clean, jg, windows)
            if filled:
                jg["xg_filled"] = filled
        dist = game_distribution(jg, research_clean, sport, settings)
        jg["distribution"] = dist
        # [§6-4] (a) 임의 계수 모델의 확률을 따로 보존 (분포 = 현행 모델)
        if dist is not None:
            jg["p_heuristic"] = {
                jg["home"]: dist["probs"]["h2h"]["home"],
                jg["away"]: dist["probs"]["h2h"]["away"],
            }
        # [§6-4] (b) 학습 계수 모델 — 아티팩트가 있을 때만. 없으면 None으로 남는다.
        learned = _learned_probs(jg, research_clean, sport, settings)
        if learned:
            jg["p_learned"] = learned
        if dist is not None:
            jg["lambda_trace"] = dist["lam"].trace
            jg["lambda_missing"] = dist["lam"].missing
            jg["prob_cap_note"] = dist["capped"]
            jg["prob_raw_home"] = dist["raw_home"]
        else:
            jg["lambda_missing"] = (jg.get("lambda_missing") or []) + ["핵심 지표(타선·선발) 전무"]
        adjuster = WinProbAdjuster(settings)
        p_legacy: dict[str, float] = {}
        home_adj = None
        for side, p_model_s, p_market_s, p_claude_s in sides:
            if not (jg.get("best_odds") or {}).get(side):
                continue
            if dist is not None:
                # 모델 확률 = 기대득점 분포. Claude 판정과 반반으로 결합한다.
                p_model_s = (dist["probs"]["h2h"]["home"] if side == jg["home"]
                             else dist["probs"]["h2h"]["away"])
            pe = blend(p_model_s, p_market_s, p_claude_s)
            p_ens[side] = round(pe, 4)
            p_legacy[side] = round(blend_legacy(p_model_s, p_market_s, p_claude_s), 4)
            if dist is not None:
                from app.engine.scoring import cap_probability

                capped, note = cap_probability(pe, sport, settings)
                p_final[side] = round(capped, 4)
                if note and side == jg["home"]:
                    jg["prob_cap_note"] = note
            elif side == jg["home"]:
                home_adj = adjuster.adjust(pe, jg, research_clean, sport)
                p_final[side] = home_adj["p"]
            else:
                p_final[side] = round(pe, 4)   # 원정은 홈 조정폭을 반대로 받는다(아래)
        # 홈 조정폭을 원정에 대칭 반영 (분포 경로는 이미 양쪽이 계산돼 있다)
        if dist is None and home_adj is not None and jg["away"] in p_final:
            shift = home_adj["p"] - p_ens.get(jg["home"], home_adj["p"])
            p_final[jg["away"]] = round(max(0.02, min(0.96, p_final[jg["away"]] - shift)), 4)
        jg["prob_adjust"] = home_adj          # 조정 과정 trace (상세 데이터 표시용)
        jg["p_legacy"] = p_legacy             # [6] 병렬 채점용 시장 반영 확률

        # [7][8] 전 마켓 후보 생성·승인 → 마켓 보드
        # [2] 전 마켓 보드 — 판정 유무·배당 유무와 무관하게 항상 전 행을 만든다
        cands = build_board(jg, sport, p_final)
        jg["market_board"] = cands
        priced = [c for c in cands if c.get("ev") is not None]
        if not priced:
            continue                       # 대표 픽은 못 뽑지만 보드는 이미 채워졌다
        approved = [c for c in priced if c.get("approved")]
        rep = (max(approved, key=lambda c: c["ev"]) if approved
               else max((c for c in priced if c["market"] == "h2h"),
                        key=lambda c: c["ev"],
                        default=max(priced, key=lambda c: c["ev"])))

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
            "desc": rep["desc"], "p": rep["p"], "p_claude": jg.get("p_claude"),
            "model_valid": jg.get("model_valid", False),
            "confidence": jg.get("judge_confidence", "medium"),
            "odds": rep["odds"], "ev": rep["ev"], "kelly": round(pick_kelly, 4),
            "stake_krw": stake_krw,
            "verdict": jg.get("verdict", ""), "excluded_picks": jg.get("excluded_picks", []),
            "flags": rep.get("flags", []), "judge_excluded": judge_excluded,
            "approved": bool(rep.get("approved")),
            "reject_reason": rep.get("reject_reason"),
            "axes": rep.get("axes_kr"),
            "grade": rep.get("grade"),
            # 추천 자격 판정에 쓰이는 필드 — 빠지면 qualifies()가 무력화된다
            # [§6-4] 세 방식 확률을 함께 실어 실전 결과로 비교한다
            "p_heuristic": (jg.get("p_heuristic") or {}).get(rep["side"]),
            "p_learned": (jg.get("p_learned") or {}).get(rep["side"]),
            "two_source": rep.get("two_source"),
            "required_prob": rep.get("required_prob"),
            "edge": rep.get("edge"),
            "edge_excess": rep.get("edge_excess"),
            "lineup_status": jg.get("lineup_status") or "none",
            "pick_state": _pick_state(jg)[0], "pick_state_label": _pick_state(jg)[1],
            "p_legacy": (jg.get("p_legacy") or {}).get(rep["side"]),
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
        if p["approved"] and not p["judge_excluded"] and qualifies(p, settings)
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


_GENERIC_TEAM_TOKENS = frozenset({
    "fc", "cf", "sc", "ac", "club", "united", "city", "town", "de", "the", "and", "st.",
})


@lru_cache(maxsize=1)
def _shared_team_tokens() -> frozenset[str]:
    """둘 이상의 구단이 공유하는 팀명 토큰.

    실사고: `home.split()[-1]` = "sox"로 매칭해 **Boston Red Sox 속보가
    Chicago White Sox 경기 카드에 붙었다.** 공유 토큰은 식별자가 될 수 없다.
    """
    from collections import Counter

    from app.bot.aliases import TEAM_ALIASES

    officials = {official for _sport, official in TEAM_ALIASES.values()}
    counts: Counter[str] = Counter()
    for name in officials:
        counts.update(set(name.lower().split()))
    return frozenset(tok for tok, n in counts.items() if n > 1)


def _news_keys(team: str) -> set[str]:
    """그 팀만 가리키는 매칭 키 — 정식명·한국어명 + 공유되지 않는 고유 토큰."""
    keys = {team.lower().strip(), _kr(team).lower().strip()}
    shared = _shared_team_tokens() | _GENERIC_TEAM_TOKENS
    for tok in team.lower().split():
        tok = tok.strip(".")
        if len(tok) >= 4 and tok not in shared:
            keys.add(tok)
    return {k for k in keys if k}


_SENT_END = re.compile(r"[.!?]['\")\]]?\s|[다요음함짐움됨]\.\s*$|[.!?]$")


_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d)?)\s*%")


def scrub_conflicting_probs(text, allowed: set[int]) -> str:
    """[2] 확률 소스 단일화 — p_final과 다른 승률 수치를 판정문에서 걷어낸다.

    같은 경기·같은 팀의 확률이 두 개 나오면 읽는 사람은 무엇을 믿을지 모른다.
    판정문이 자기 추정치를 다시 쓰면(예: "모델 레즈 63.2%") 보드의 77%와 충돌한다.
    허용 목록(p_final에서 나온 값)에 없는 % 수치가 든 **절**을 통째로 버린다.
    (ERA·WHIP·승률 .592 같은 %가 아닌 수치는 건드리지 않는다)
    """
    s = str(text or "")
    if not s:
        return ""
    out = []
    for chunk in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*", s):
        hits = [round(float(m.group(1))) for m in _PCT_RE.finditer(chunk)]
        if hits and any(h not in allowed for h in hits):
            continue        # p_final과 다른 확률이 섞인 문장은 버린다
        out.append(chunk)
    return " ".join(x for x in out if x.strip()).strip()


def allowed_prob_pcts(jg: dict) -> set[int]:
    """이 경기에서 인용이 허용되는 승률 퍼센트 — p_final 계열만."""
    allowed: set[int] = set()
    for c in jg.get("market_board") or []:
        if c.get("p") is not None:
            allowed.add(round(c["p"] * 100))
    adj = jg.get("prob_adjust") or {}
    for key in ("p_home", "p_away"):
        if adj.get(key) is not None:
            allowed.add(round(adj[key] * 100))
    # 반올림 경계 흡수
    return {v + d for v in list(allowed) for d in (-1, 0, 1)}


def clip_sentences(text, limit: int) -> str:
    """[C] 문장 완결성 보장 절단 — 잘린 문장은 버린다.

    실사고: "선발 최근: … 최근 구간에서도 경 / 원정 ?"처럼 단어 중간에서 끊긴 문장이
    데이터인 척 출력됐다. 한도 안에 들어가는 **마지막 완결 문장까지만** 남기고,
    완결 문장이 하나도 없으면 빈 문자열을 돌려 그 줄 자체를 생략하게 한다.
    """
    s = str(text or "").strip()
    if not s:
        return ""
    if len(s) <= limit:
        return s
    head = s[:limit]
    cut = -1
    for m in re.finditer(r"[.!?]|[다요음함짐움됨](?=\s|$)", head):
        cut = m.end()
    if cut <= 0:
        return ""      # 완결 문장 없음 → 줄 생략
    return head[:cut].strip()


def _team_news_lines(news: str, home: str, away: str) -> list[str]:
    """이 경기 두 팀을 실제로 가리키는 속보 줄만 고른다 (다른 경기 속보 혼입 금지)."""
    keys = _news_keys(home) | _news_keys(away)
    out = []
    for ln in news.splitlines():
        low = ln.lower()
        if any(re.search(rf"(?<![0-9a-z]){re.escape(k)}(?![0-9a-z])", low) for k in keys):
            out.append(ln)
    return out


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
    # [3-2] EV·기대값 표현 전면 금지 — 기본층은 승률과 실수령액으로만 말한다
    r"기대값", r"기댓값", r"이득\s*[+\-]", r"기대\s*수익률",
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
    """[3] 신호등은 **마켓 단위** 판정의 최고 등급이다 — 경기 단위 일괄 패스 금지.

    승패에 가치가 없어도 언더 8.5가 승인되면 그 경기는 🟢이다.
    진짜 🔴은 "전 마켓을 검토했으나 어느 마켓도 승인 기준을 못 넘김"일 때뿐이며,
    그때도 마켓 보드는 전 행이 출력되고 신호등 옆에 사유를 밝힌다.
    """
    from app.engine.markets import GRADE_BLANK, best_market, board_grade, rejection_summary

    board = jg.get("market_board") or []
    if not board:
        return "🔴", "패스 — 마켓 보드를 만들지 못했습니다 (파이프라인 오류)", 1

    if all(c.get("grade") == GRADE_BLANK for c in board):
        return "🔴", "패스 — 전 마켓 배당을 한 건도 수집하지 못했습니다", 1
    if jg.get("judge_missing"):
        return ("🔴", "패스 — 판정 미수신으로 전 마켓 추천 불가 (배당은 아래 보드에 표시)", 1)

    grade = board_grade(board)
    top = best_market(board) or {}
    if grade in ("🔴", GRADE_BLANK):
        return "🔴", ("패스 — 전 마켓 검토 결과 기준 미달: "
                      + rejection_summary(board)), 2

    conf = jg.get("judge_confidence", "medium")
    desc, note = top.get("desc", "?"), top.get("grade_note", "")
    if grade == "🟢":
        stars = 5 if conf == "high" else 4
        return "🟢", f"추천 — {desc}가 걸 만합니다 ({note})", stars
    stars = 3 if conf == "high" else 2
    return "🟡", f"소액만 — {desc} 정도가 볼 만한 자리입니다 ({note})", stars


def _guard_basic(text: str, where: str) -> str:
    """기본층 금지어 런타임 검증 — 위반은 코드 버그이므로 에러 로그로 즉시 드러낸다."""
    v = basic_layer_violations(text)
    if v:
        logger.error("[2layer] 기본층 금지어 검출 (%s): %s", where, v)
    return text


NO_MATERIAL_MSG = "최신 데이터 수집에 실패해 분석할 수 없습니다."

# [4] 종목별 용어 — 야구는 라인업 발표, 축구는 킥오프
LINEUP_MOMENT = {"mlb": "경기 시작 전 라인업 발표", "soccer": "킥오프 직전"}

_DIGIT_RE = re.compile(r"\d")


def _sport_of(jg: dict) -> str:
    """[4] 경기 객체에서 종목 판정 — 문구의 종목 오용(야구에 '킥오프')을 막는다."""
    if jg.get("sport") in ("mlb", "soccer"):
        return jg["sport"]
    if jg.get("league") == "MLB":
        return "mlb"
    st = jg.get("stats") or {}
    if st.get("home_pitcher") or st.get("away_pitcher") or jg.get("home_pitcher"):
        return "mlb"
    return "soccer"


def _player_names(jg: dict, research: dict) -> list[str]:
    """그 경기 고유 식별에 쓸 선수 이름 (선발·결장자)."""
    names: list[str] = []
    st = jg.get("stats") or {}
    for key in ("home_pitcher", "away_pitcher"):
        if st.get(key):
            names.append(str(st[key]))
        block = research.get(key) or {}
        if isinstance(block, dict) and block.get("name"):
            names.append(str(block["name"]))
    for item in research.get("absences") or []:
        names += re.findall(r"[A-Z][a-z]+(?: [A-Z][a-z]+)+", str(item))
    return [n for n in names if n]


def line_is_game_specific(line: str, names: list[str]) -> bool:
    """[3] 각 줄은 그 경기 고유의 숫자나 선수 이름을 최소 1개 포함해야 한다."""
    return bool(_DIGIT_RE.search(line)) or any(n in line for n in names)


def _pick_line(candidates: list[str], names: list[str], used: set[str] | None) -> str | None:
    """[3] 고유 수치/이름을 포함하고 다른 경기와 겹치지 않는 첫 문장. 없으면 None(줄 생략)."""
    for cand in candidates:
        if not cand or not line_is_game_specific(cand, names):
            continue
        if used is not None and cand in used:
            continue  # 다른 경기에서 이미 쓴 문장 → 다음 후보로 재생성
        if used is not None:
            used.add(cand)
        return cand
    return None


def _value_candidates(jg: dict, home_kr: str, away_kr: str) -> list[str]:
    """[3-3] '걸 만한가' — 마켓 보드 최고 등급 마켓 하나를 **돈으로** 말한다.

    "레즈 승 @1.61 — 10번 중 6번 이기는 계산, 이기면 1만 원당 6,100원 수익"
    EV·기대값 표현은 쓰지 않는다 (기본층 금지어).
    """
    from app.config import get_settings
    from app.engine.markets import best_market, payout_10k, rejection_summary

    s = get_settings()
    board = jg.get("market_board") or []
    out: list[str] = []
    if not board:
        out.append(f"걸 만한가? {home_kr} vs {away_kr}는 배당을 수집하지 못해 판단할 수 없습니다.")
        return out

    top = best_market(board) or {}
    grade, desc, odds, prob = (top.get("grade"), top.get("desc", "?"),
                               top.get("odds"), top.get("p"))
    h2h = next((c for c in board if c["market"] == "h2h"), None)
    h2h_dead = h2h is not None and h2h.get("grade") == "🔴"

    if grade in ("🟢", "🟡") and odds and prob is not None:
        lead = "승패는 볼 게 없지만 " if h2h_dead and top["market"] != "h2h" else ""
        tail = "걸 만합니다" if grade == "🟢" else "소액이면 볼 만합니다"
        out.append(f"걸 만한가? {lead}{desc} @{odds:.2f} — {_times_out_of_ten(prob)} "
                   f"이기는 계산, 이기면 1만 원당 {payout_10k(odds):,}원 수익. {tail}.")
        if top["market"] != "h2h":
            out.append(f"걸 만한가? 승패 대신 {desc} @{odds:.2f}가 이 경기 최선입니다 — "
                       f"{_times_out_of_ten(prob)} 적중, 1만 원당 {payout_10k(odds):,}원.")
        return out

    # 전 마켓 기준 미달 — 무엇이 왜 미달인지 밝힌다
    out.append(f"걸 만한가? 전 마켓을 봤지만 승률 {s.min_win_prob:.0%}·배당 {s.min_odds:.2f} "
               f"기준을 넘는 자리가 없습니다 — {rejection_summary(board)}.")
    return out


def _caution_candidates(jg: dict, research: dict, sport: str) -> list[str]:
    """[3][4] '조심할 점' 후보 — 그 경기 고유 수치·이름 기반, 종목 용어 분리."""
    out: list[str] = []
    absences = research.get("absences") or []
    if absences:
        out.append(f"결장 변수: {str(absences[0])[:70]}")
    reversal = research.get("form_reversal") or []
    if reversal:
        out.append(f"시즌 평균과 최근 폼이 어긋납니다 — {str(reversal[0])[:70]}")
    draw_p = (jg.get("market_probs") or {}).get("Draw") or 0
    if sport == "soccer" and draw_p >= 0.28:
        out.append(f"무승부 확률이 {draw_p:.0%}로 높은 유형의 경기입니다.")
    if not jg.get("model_valid") and jg.get("p_market") is not None:
        out.append(f"이 리그는 통계 표본이 부족해 시장 확률({jg['p_market']:.0%}) 외에 "
                   f"기댈 숫자가 거의 없습니다.")
    if sport == "mlb":
        st = jg.get("stats") or {}
        hp = st.get("home_pitcher") or (research.get("home_pitcher") or {}).get("name")
        ap = st.get("away_pitcher") or (research.get("away_pitcher") or {}).get("name")
        if hp or ap:
            out.append(f"선발 예고({hp or '?'} vs {ap or '?'})는 "
                       f"{LINEUP_MOMENT['mlb']}에서 바뀔 수 있습니다.")
    elif jg.get("starts_at_kst"):
        out.append(f"부상·라인업 변수는 {LINEUP_MOMENT['soccer']}({jg['starts_at_kst']})에 "
                   f"바뀔 수 있습니다.")
    return out


def render_game_easy(jg: dict, news: str = "", used: set[str] | None = None) -> str:
    """심층 분석 2층 출력: 쉬운 요약 6줄 + <<DETAIL>> 뒤에 전문 상세(접힘용).

    데이터를 줄이지 않는다 — 표현만 바꾼다. 전문 수치는 전부 상세에 보존.
    used: 여러 경기를 함께 낼 때 문장 중복을 막는 공유 집합 ([3]).
    """
    from app.research.validate import research_materials, sanitize_research

    home_kr, away_kr = _kr(jg["home"]), _kr(jg["away"])
    sport = _sport_of(jg)
    research, _ = sanitize_research(jg.get("research") or {}, sport)
    names = _player_names(jg, research)
    signal, reason, stars = classify_signal(jg)
    lines = [f"{jg['starts_at_kst']} {home_kr} vs {away_kr} [{jg.get('league', '?')}]"]
    lines.append(f"{signal} {reason}")
    state_label = jg.get("pick_state_label") or _pick_state(jg)[1]
    if jg.get("lineup_confirmed_kst"):
        state_label += f" (확정 {jg['lineup_confirmed_kst']})"
    lines.append(state_label)

    # 누가 이길까 — 우세한 쪽 기준 '10번 중 N번' 화법
    ph = None
    if jg.get("p_claude") is not None:
        ph = jg["p_claude"]
    elif jg.get("p_market") is not None:
        ph = jg["p_market"]
    # 서술(맥락·인과)이 붙은 경기는 그 줄이 '누가 이길까'의 역할을 대신한다 —
    # 기본층 분량을 6~8줄로 유지하기 위해 중복 줄을 넣지 않는다.
    has_narrative = bool((jg.get("narrative") or {}).get("causal"))
    if ph is not None and not has_narrative:
        fav, p_fav = (home_kr, ph) if ph >= 0.5 else (away_kr, 1 - ph - ((jg.get("market_probs") or {}).get("Draw", 0)))
        p_fav = max(0.05, min(0.95, p_fav))
        lines.append(f"누가 이길까? 봇 계산으론 {fav}{_ga(fav)} {_times_out_of_ten(p_fav)} 이기는 그림입니다.")
    elif ph is None and not has_narrative:
        lines.append("누가 이길까? 데이터가 부족해 저희도 판단을 보류합니다.")

    # [B-2] ① 맥락 · ② 인과 — 서술 단계(narrator) 결과.
    # 서술 줄은 narrator.clean_line이 이미 각주·필드나열·빈말을 걸렀다. 여기서는
    # 문장 완결성과 경기 간 중복만 본다 (한국어 선수명은 names에 없으므로 수치 검사 미적용).
    from app.engine.narrator import clean_line as _narr_clean

    nar = jg.get("narrative") or {}
    for key in ("context", "causal"):
        line = clip_sentences(_narr_clean(nar.get(key)), 220)
        if line and (used is None or line not in used):
            if used is not None:
                used.add(line)
            lines.append(line)

    # 걸 만한가 — 전 마켓 중 최적 하나를 골라 결론까지 문장으로 ([8])
    value_line = _pick_line(_value_candidates(jg, home_kr, away_kr), names, used)
    if value_line:
        lines.append(value_line)

    # [B-2] ③ 승부처 — 이 경기가 어디서 갈리는지 한 문장
    decider = clip_sentences(_narr_clean(nar.get("decider")), 200)
    if decider:
        lines.append(f"승부처: {decider}")

    # [5] 승률 조정 근거 — 무엇이 승률을 얼마나 움직였는지
    adj_case = clip_sentences(_narr_clean(nar.get("adjustment_case")), 200)
    if adj_case and (used is None or adj_case not in used):
        if used is not None:
            used.add(adj_case)
        lines.append(adj_case)

    # [4] ④ 추천 마켓 근거 — 최고 등급 마켓을 왜 그 자리로 보는지
    market_case = clip_sentences(_narr_clean(nar.get("market_case")), 200)
    if market_case and (used is None or market_case not in used):
        if used is not None:
            used.add(market_case)
        lines.append(market_case)

    # 조심할 점 — 고유 수치·이름이 없으면 줄 자체를 생략 ([3])
    if not any(research_materials(research).values()) and jg.get("p_market") is not None:
        caution = _pick_line(
            [f"조심할 점: 최신 데이터(최근 폼·전문가 픽·결장) 수집에 실패해 "
             f"시장 확률 {jg['p_market']:.0%} 외에 근거가 없습니다."], names, used)
    else:
        caution = _pick_line(_caution_candidates(jg, research, sport), names, used)
        caution = f"조심할 점: {caution}" if caution else None
    if caution:
        lines.append(caution)
    lines.append(f"신뢰도 {_stars(stars)}")

    # [B-5] 재료가 부족하면 길이를 채우지 말고, 왜 짧은지 밝힌다
    missing = clip_sentences((jg.get("narrative") or {}).get("missing"), 160)
    if missing and len(lines) <= 5:
        lines.append(f"({missing})")

    detail = render_game_section(jg, news)
    return _guard_basic("\n".join(lines[:9]) + DETAIL_SEP + detail, "game_easy")


def render_games_easy(games: list[dict], news: str = "") -> list[str]:
    """[3] 여러 경기를 함께 낼 때 — 경기 간 동일 문장이 나오지 않도록 공유 집합으로 렌더."""
    used: set[str] = set()
    return [render_game_easy(g, news, used=used) for g in games]


def sorted_board(jg: dict) -> list[dict]:
    """마켓 보드 정렬 — 등급 높은 순, 같은 등급이면 EV 큰 순. 배당 미수집 행은 뒤로."""
    from app.engine.markets import GRADE_RANK

    return sorted(
        jg.get("market_board") or [],
        key=lambda c: (-GRADE_RANK.get(c.get("grade"), 0), -(c.get("ev") if c.get("ev") is not None else -9)),
    )


def board_row(c: dict, confidence: str | None = None) -> str:
    """[2][3-3] 마켓 보드 1행 — 돈으로 말한다. 배당이 없어도 행은 남긴다.

    형식: 마켓 | 배당 | 승률 | 1만원 수익 | 신호등 | 근거 | ★
    """
    from app.engine.markets import payout_10k, row_stars

    odds = f"{c['odds']:.2f}" if c.get("odds") else "배당 미수집"
    prob = f"{c['p']:.0%}" if c.get("p") is not None else "—"
    money = f"{payout_10k(c['odds']):,}원" if c.get("odds") else "—"
    grade = c.get("grade") or "⚪"
    note = c.get("grade_note") or c.get("reject_reason") or "—"
    stars = row_stars(c, confidence)
    star_txt = _stars(stars) if stars else "—"
    return f"{c['desc']} | {odds} | {prob} | {money} | {grade} | {note} | {star_txt}"


def render_game_section(jg: dict, news: str = "") -> str:
    """경기 1건 심층 ①~⑦ (버튼 응답·팀 질문 공용). 25줄 상한. 전면 한국어.

    [1] 리서치 값은 렌더 직전 sanitize_research를 통과한다 — 프롬프트 문구·
        "확인 불가" 산문이 데이터 자리에 출력되는 것을 캐시 구데이터까지 포함해 차단.
    [2] recent_form·전문가 픽·결장 정보가 모두 비면 심층 분석을 만들지 않는다.
    """
    from app.research.validate import research_materials, sanitize_research

    home_kr, away_kr = _kr(jg["home"]), _kr(jg["away"])
    sport = _sport_of(jg)
    ho = jg.get("best_odds", {}).get(jg["home"])
    ao = jg.get("best_odds", {}).get(jg["away"])
    matchup = (f"{home_kr}({ho:.2f}) vs {away_kr}({ao:.2f})"
               if ho and ao else f"{home_kr} vs {away_kr}")
    st = jg.get("stats") or {}
    pitchers = ""
    if sport == "mlb" and (st.get("home_pitcher") or st.get("away_pitcher")):
        pitchers = f" | {st.get('home_pitcher') or '?'} vs {st.get('away_pitcher') or '?'}"
    label = f" [{jg['status_label']}]" if jg.get("status_label") else ""
    header = f"{jg['starts_at_kst']} [{jg.get('league', '?')}] {matchup}{pitchers}{label}"

    research, dropped = sanitize_research(jg.get("research") or {}, sport)
    mats = research_materials(research)
    if not any(mats.values()):
        # [2] 재료 없음 → 분석 생성 금지. 실패 사실만 알린다.
        why = " (수집된 응답이 데이터가 아니라 무효 처리)" if dropped else ""
        return "\n".join([header, f"⚠️ 리서치 실패{why}", NO_MATERIAL_MSG])

    lines = [header]
    hr, ar = research.get("home_recent_form") or {}, research.get("away_recent_form") or {}
    if hr.get("form") or ar.get("form"):
        lines.append(f"최근 폼: {home_kr} {hr.get('form') or '?'} · {away_kr} {ar.get('form') or '?'}")
    if sport == "mlb":
        hp, ap = research.get("home_pitcher") or {}, research.get("away_pitcher") or {}
        if hp.get("last5") or ap.get("last5"):
            h5 = clip_sentences(hp.get("last5"), 110)
            a5 = clip_sentences(ap.get("last5"), 110)
            if h5 or a5:   # 잘린 문장만 남는 경우 줄째로 생략
                lines.append(f"선발 최근: 홈 {h5 or '—'} / 원정 {a5 or '—'}")
    if research.get("absences"):
        absent = clip_sentences("; ".join(str(x) for x in research["absences"][:2]), 180)
        if absent:
            lines.append(f"결장: {absent}")
    if research.get("form_reversal"):
        rev = clip_sentences("; ".join(str(x) for x in research["form_reversal"][:2]), 180)
        if rev:
            lines.append(f"⚠️ 폼 역전: {rev}")
    if jg.get("research_status") in ("missing", "invalid"):
        lines.append("⚠️ 리서치 실패 — 최신 데이터를 수집하지 못했습니다")
    elif jg.get("research_status") == "stale_fallback":
        lines.append("⚠️ 리서치 미완 — 새벽 데이터 기준")

    # [2-3] 기대득점 λ 산출 과정 — 타선→선발→구장→날씨→불펜→좌우→홈 순서 그대로
    if jg.get("lambda_trace"):
        lines.append("λ 산출: " + " → ".join(jg["lambda_trace"]))
    if jg.get("prob_cap_note"):
        lines.append(f"⚠️ {jg['prob_cap_note']} — 계산 결과가 현실 범위를 벗어나 절사했습니다")
    if jg.get("lambda_missing"):
        lines.append("(미수집·보정 생략) " + ", ".join(jg["lambda_missing"][:6]))

    # [§3] 라인 이동 — 확률이 아니라 신뢰도 근거로만 표시한다
    lm = jg.get("line_move") or {}
    if lm.get("line"):
        lines.append(f"{lm['desc']} {lm['line']}")
        if lm.get("warning"):
            lines.append(f"⚠️ {lm['warning']}")

    # [1] 승률 조정 과정 — **대표 마켓의 대상팀 기준**으로 통일해 출력한다.
    #     보드는 대상팀 승률을 쓰는데 조정 과정만 홈 기준이면 두 기준이 섞여 읽을 수 없다.
    from app.engine.markets import best_market
    from app.engine.performance import trace_for

    adjust = jg.get("prob_adjust") or {}
    if adjust.get("trace") and not jg.get("lambda_trace"):
        target = (best_market(jg.get("market_board") or []) or {}).get("side") or jg["home"]
        if target not in (jg["home"], jg["away"]):
            target = jg["home"]          # 토탈·핸디 등 팀이 아닌 사이드는 홈 기준 유지
        lines.append("승률 조정: " + " → ".join(trace_for(adjust, target)))
    if adjust.get("unused"):
        lines.append("(확률 미반영) " + ", ".join(adjust["unused"]) + " — 서술 참고용")

    # [2] 확률 소스 단일화 — 같은 팀 승률이 화면에 2개 이상 나오면 안 된다.
    #     모델·Claude·시장 확률은 p_final의 **입력값**이지 별도 결론이 아니므로 표기하지 않는다.
    #     (시장 확률은 predictions.p_market에 기록돼 병렬 채점에 쓰인다)
    if not jg.get("model_valid"):
        lines.append("모델: 무효(올 시즌 실데이터 없음) — 판정·전문가 근거로만 평가")

    ps = jg.get("pick_summary")
    if ps:  # 보드·카드와 동일한 p_final 하나만 인용
        flag_txt = f" ⚠️{ps['flags'][0]}" if ps.get("flags") else ""
        ok_txt = "" if ps.get("approved") else f" [제외: {ps.get('reject_reason')}]"
        lines.append(
            f"대표 마켓: {ps.get('desc') or _kr(ps['side'])} @{ps['odds']:.2f} — "
            f"승률 {ps['p_final']:.0%} (근거: {ps.get('axes') or '?'}){ok_txt}{flag_txt}")

    # [2] ⑧ 마켓 보드 — 전 마켓을 **항상** 행으로. 배당이 없어도 행을 지우지 않는다.
    #     형식: 마켓명 | 배당 | 봇 확률 | EV | 신호등 | 근거 한 줄 | ★
    lines.append("⑧ 마켓 보드 (마켓 | 배당 | 승률 | 1만원 수익 | 신호등 | 근거 | 신뢰도):")
    for c in sorted_board(jg):
        lines.append("  " + board_row(c, jg.get("judge_confidence")))

    from app.engine.narrator import clean_line as _nclean

    expert_note = clip_sentences(_nclean((jg.get("narrative") or {}).get("expert_note")), 200)
    eps = jg.get("expert_picks") or []
    if expert_note:
        lines.append(f"전문가 요약: {expert_note}")
    if eps:
        for ep in eps[:3]:
            rec = f" (전적 {ep['record']})" if ep.get("record") else " (전적 미상 — 0.5표)"
            ep_reason = clip_sentences(ep.get("reasoning"), 150)
            reason = f" — {ep_reason}" if ep_reason else ""
            adopt = "" if ep.get("adopted", True) else " [불채택 — 해당 마켓 전적 마이너스, 인용 데이터만 참고]"
            lines.append(f"전문가: [{ep.get('site', '?')}] {ep.get('expert', '?')}: {ep['pick']}{reason}{rec}{adopt}")
    else:
        lines.append("전문가: 전문가 픽 미수집")

    news_hits = _team_news_lines(news or "", jg["home"], jg["away"])
    hit = clip_sentences(news_hits[0], 200) if news_hits else ""
    lines.append(f"속보: {hit or '특이사항 없음'}")
    for note in jg.get("breaking_changes", []) or []:
        lines.append(f"🔄 {note[:150]}")
    if jg.get("verdict"):
        # [2] 판정문이 자기 확률을 다시 쓰면 보드와 충돌한다 — p_final 계열만 남긴다
        v = scrub_conflicting_probs(jg["verdict"], allowed_prob_pcts(jg))
        verdict_txt = clip_sentences(v, 600)
        if verdict_txt:
            lines.append(f"판단: {verdict_txt}" + ("…" if len(verdict_txt) < len(v) else ""))
        if jg.get("reversal_factor"):
            rf = clip_sentences(
                scrub_conflicting_probs(jg["reversal_factor"], allowed_prob_pcts(jg)), 200)
            if rf:
                lines.append(f"반전 요인: {rf}")
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

    # 판정 실패를 '추천 없음'으로 위장하지 않는다 — 재료 없으면 정직하게 실패를 알린다
    judged = [g for g in scheduled if g.get("p_claude") is not None]
    if scheduled and not judged:
        lines.append("")
        lines.append("⚠️ 판정 실패 — 오늘 경기 판정을 받지 못해 분석을 완료하지 못했습니다.")
        lines.append("추천·조합을 낼 수 없습니다. (관망 권장이 아니라 '분석 미완'입니다)")
        detail.append(f"판정 부착 0건 / 분석 대상 {len(scheduled)}경기 — judge 응답 확인 필요")
        return _guard_basic("\n".join(lines[:20])[:3500] + DETAIL_SEP + "\n".join(detail[:20]), "card")

    lines.append("")
    lines.append("🎯 오늘의 추천")
    if recommended:
        for p in recommended:
            stake = f" (권장 {p['stake_krw']:,}원)" if p.get("stake_krw") else ""
            from app.engine.markets import breakeven_odds, payout_10k

            lines.append(
                f"· {p.get('desc') or _kr(p['side'])} @{p['odds']:.2f} — "
                f"{_kr(p['home'])} vs {_kr(p['away'])}, "
                f"{_times_out_of_ten(p['p'])} 이기는 계산, "
                f"이기면 1만 원당 {payout_10k(p['odds']):,}원 수익"
                f" [{p.get('league', '?')} {p['starts_at_kst'][-5:]}]{stake}")
            be = breakeven_odds(p["p"])
            detail.append(
                f"{p.get('desc')}: 승률 {p['p']:.1%} / 배당 {p['odds']:.2f} / "
                f"손익분기 배당 {be} / 시장 환산 {1 / p['odds']:.1%} / "
                f"근거 {p.get('axes') or '?'} / 판정 신뢰도 {p.get('confidence')}")
    else:
        s = get_settings()
        lines.append(f"승률 {s.min_win_prob:.0%}·배당 {s.min_odds:.2f} 기준을 넘는 픽이 없습니다.")
        near = near_miss_picks(picks, s)
        if near:
            lines.append(f"— 조건 미달 · 승률 상위 {len(near)}:")
            for p in near:
                lines.append(f"  · {p.get('desc') or _kr(p['side'])} @{(p.get('odds') or 0):.2f} "
                             f"승률 {p['p']:.0%} — {p['miss_reason']}")
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
            money = f"1만 원당 {c.get('payout_10k', 0):,}원" if c.get("payout_10k") else ""
            lines.append(f"조합 {i}({c['tier']}): {legs_txt} @{c['odds']:.2f} "
                         f"(적중률 {c['p']:.0%}, {money}) — {c['stake_note']}{relax}")
            detail.append(f"조합 {i} 레그별 승률: " + ", ".join(
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
             and qualifies(p, settings)]
    clean.sort(key=lambda x: x["ev"], reverse=True)
    recommended = clean[: mode["max_picks"]]
    for p in picks:
        p["recommended"] = p in recommended
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    urls = {ep.get("source_url") for g in games for ep in g.get("expert_picks", [])}
    sources = [s for s in analysis.get("sources", []) if s["url"] in urls]
    return {
        **analysis, "games": games, "picks": picks,
        "combos": build_tiered_parlays(approved_market_legs(games), stake_krw,
                                       analysis.get("sport")),
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
    ev_ok = sorted([p for p in clean if qualifies(p, settings)],
                   key=lambda x: x["p"], reverse=True)
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
    analysis["combos"] = build_tiered_parlays(
        approved_market_legs(analysis["games"]), stake_krw, analysis.get("sport"))
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
        await notify_api_error(exc)
    _enforce_data_rules(analysis["games"])
    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport)
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    await _renarrate(refreshed, sport)   # [B-1] 재판정된 경기는 서술도 다시 쓴다
    from app.engine.parlay import build_tiered_parlays

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None
    analysis["combos"] = build_tiered_parlays(
        approved_market_legs(analysis["games"]), stake_krw, analysis.get("sport"))
    meta["refreshed"] = len(refreshed)
    logger.info("[pipeline] freshness gate: %d games re-researched & re-judged", len(refreshed))
    return len(refreshed)


async def rejudge_after_lineup(game: dict, lineup: dict) -> bool:
    """[2-3] 확정 라인업 수신 → 그 경기만 재판정. 승률·신호등·추천·조합을 갱신한다.

    확정 선발이 예고와 다르면 그 선발의 최근 성적을 다시 조회해야 하므로
    리서치를 강제 갱신한 뒤 판정을 다시 받는다.
    """
    from app.collectors.lineups import pick_state
    from app.db import get_pool
    from app.research.deep import get_game_research

    settings = get_settings()
    sport = game.get("sport", "mlb")
    date = default_date(sport)
    pool = await get_pool()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await redis.get(f"analysis:{sport}:{date}")
        if not raw:
            return False
        analysis = json.loads(raw)
        jg = next((g for g in analysis["games"] if g["game_id"] == game["id"]), None)
        if jg is None or jg.get("status") != "scheduled":
            return False

        before = (jg.get("pick_summary") or {}).get("desc")
        jg["lineup_status"] = lineup["status"]
        jg["lineup_notes"] = lineup.get("notes") or []
        # statsapi 부상자 명단을 리서치 결장자에 병합 — 승률 조정이 읽는 경로다.
        # (리서치가 결장자를 놓쳐도 1차 소스로 메운다)
        il = [s for side in ("home", "away") for s in (lineup.get("injuries") or {}).get(side, [])]
        if il:
            research = jg.setdefault("research", {})
            existing = research.get("absences") or []
            known = " ".join(str(x) for x in existing)
            research["absences"] = existing + [s for s in il if s.split("의 ")[-1][:12] not in known]
            jg["il_source"] = "statsapi"
        state, label = pick_state(lineup["status"])
        jg["pick_state"], jg["pick_state_label"] = state, label
        # 확정 선발이 바뀌었으면 그 선발의 최근 성적을 다시 조회한다
        if any("선발 변경" in n or "불일치" in n for n in jg["lineup_notes"]):
            for side, key in (("home", "home_pitcher"), ("away", "away_pitcher")):
                if lineup["starters"].get(side):
                    jg.setdefault("stats", {})[key] = lineup["starters"][side]
            data, _status = await get_game_research(redis, jg, sport, force=True)
            if data:
                jg["research"] = data

        payload = {
            "date": date, "sport": sport, "games": [jg],
            "breaking_news": analysis.get("news", ""),
            "instruction": ("확정 라인업이 수신됐다. 확정 선발·타순·결장을 반영해 "
                            "경기력 기준으로 승률을 재산출하라. 배당은 보지 마라."),
        }
        try:
            verdict = await Judge().judge(payload)
            _attach_verdicts([jg], verdict)
        except Exception as exc:
            logger.warning("[pipeline] 라인업 재판정 실패: %s", exc)
            await notify_api_error(exc)

        _enforce_data_rules(analysis["games"])
        picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport)
        analysis["picks"], analysis["parlays"] = picks_out, parlays
        analysis["combos"] = build_tiered_parlays(
            approved_market_legs(analysis["games"]),
            int(settings.bankroll_krw * MODES[settings.report_mode]["flat_pct"])
            if MODES.get(settings.report_mode, {}).get("staking") == "flat" else None,
            sport)
        await _renarrate([jg], sport)

        after = (jg.get("pick_summary") or {}).get("desc")
        note = "🔄 라인업 반영: " + "; ".join(jg["lineup_notes"][:2]) if jg["lineup_notes"] else \
               "🔄 라인업 확정 반영"
        if before != after:
            note += f" — 픽 변경: {before or '없음'} → {after or '없음'}"
        jg["breaking_changes"] = (jg.get("breaking_changes") or []) + [note]
        analysis.setdefault("lineup_notes", []).append(note)

        card = await generate_card(analysis)
        await _save_caches(redis, analysis, card)
        logger.info("[pipeline] 라인업 재판정 완료 game=%s (%s)", game["id"], note[:80])
        return True
    finally:
        await redis.aclose()


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
            await notify_api_error(exc)
        _enforce_data_rules(analysis["games"])
        picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport)
        analysis["picks"], analysis["parlays"] = picks_out, parlays
        await _renarrate([jg], sport)    # [B-1] 재판정된 경기는 서술도 다시 쓴다
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
    sequential_research: bool = False,
) -> str:
    """결론 카드(단일 메시지)를 반환. 심층·속보·출처는 분석 캐시에서 버튼으로 제공.

    sequential_research: 프리페치용 — 경기별 리서치를 순차 처리(레이트리밋 방어).
    """
    settings = get_settings()
    # 날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 표기는 항상 KST.
    date = date or default_date(sport)
    if not force_refresh:
        cached = await redis.get(f"card:{sport}:{date}")
        if cached:
            logger.info("[pipeline] cache hit: card:%s:%s", sport, date)
            # 속보의 결론 반영: 캐시 응답 전에 최신 체크 → 중대 변화 시 재판정
            return await _freshness_gate(redis, sport, date, cached)
    analysis = await build_analysis(pool, sport, date, progress=progress, redis=redis,
                                    sequential_research=sequential_research)
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
