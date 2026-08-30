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

from app.collectors.base import (
    ApiAuthError, ApiQuotaError, ApiRateLimitError,
    ProviderBlockedError, ProviderDisabledError,
)
from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer_games
from app.collectors.mlb import (
    MLBClient, parse_recent_form, parse_standings, upsert_games, _parse_games,
)
from app.collectors.odds import (
    LEAGUE_LABEL_BY_SPORT, OddsClient, SPORT_KEYS, snapshot_odds,
)
from app.config import get_settings
from app.engine.consensus import consensus_scores, load_expert_weights
from app.engine.judge import Judge
from app.engine.parlay import best_parlays
from app.engine.value import devig, ensemble, ev, implied_prob
from app.notify import notify_api_error
from app.research.grok import GrokClient
from app.research.perplexity import PerplexityClient, save_expert_picks

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


# 계측 분모로 쓰는 실제 대상 수 — **추측하지 말고 소스에서 확인한 값만 쓴다.**
MLB_PARKS = 30      # 실측 2026-08-27: app.collectors.park.load()가 30팀 반환
KBO_TEAMS = 10
NPB_TEAMS = 12          # yahoo_npb.TEAM_TO_ODDS 12구단 (실측)
KBO_PARKS = 9


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def kst_hhmm(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%m/%d %H:%M")


# 시작 전(scheduled) 경기만 분석 대상. 나머지는 목록에 라벨만 붙인다.
STATUS_LABELS = {"live": "진행 중", "final": "종료"}


def mark_finals_as_sim(games: list[dict]) -> list[dict]:
    """종료·진행 중 경기를 분석 회로에 태우기 위해 예정으로 바꾼다.

    점수는 `_sim_actual`에만 남긴다. 판정 입력·λ에 실제 결과가 들어가면
    시뮬레이션이 아니라 결과 누수다. DB 행은 건드리지 않는다.
    """
    out = []
    for raw in games:
        g = dict(raw)
        if g.get("status") in ("final", "live"):
            g["_sim_actual"] = {
                "status": g["status"],
                "home_score": g.get("home_score"),
                "away_score": g.get("away_score"),
            }
            g["status"] = "scheduled"
            g["home_score"] = None
            g["away_score"] = None
        out.append(g)
    return out


def sim_scoreboard(games: list[dict]) -> str:
    """시뮬레이션 채점. `_sim_actual`이 있는 경기만."""
    def hit(pred_home, hs, aws):
        if hs is None or aws is None or hs == aws or pred_home is None:
            return None
        if float(pred_home) == 0.5:
            return "push"
        return "hit" if (float(pred_home) > 0.5) == (hs > aws) else "miss"

    def rate(marks):
        rows = [x for x in marks if x and x != "push"]
        h, m = rows.count("hit"), rows.count("miss")
        n = h + m
        return "n=0" if not n else f"{h}/{n} = {h / n:.1%}"

    lines = ["--- 시뮬레이션 채점 (종료 점수 vs 파이프라인 승률) ---"]
    lam_m, cl_m, fn_m = [], [], []
    for jg in games:
        act = jg.get("_sim_actual") or {}
        hs, aws = act.get("home_score"), act.get("away_score")
        if hs is None or aws is None:
            continue
        pm, pc = jg.get("p_model"), jg.get("p_claude")
        ph = jg.get("p_heuristic")
        if isinstance(ph, dict) and jg.get("home") in ph:
            pm = ph[jg["home"]]
        pf = jg.get("p_final")
        if isinstance(pf, dict):
            pf = pf.get(jg.get("home"))
        if pf is None and pm is not None and pc is not None:
            pf = 0.5 * float(pm) + 0.5 * float(pc)
        actual = "홈승" if hs > aws else "원정승" if aws > hs else "무"

        def pct(x):
            return "—" if x is None else f"{float(x):.1%}"

        lines.append(
            f"{jg.get('away')} @ {jg.get('home')}  실제 {aws}-{hs} {actual}  "
            f"λ={pct(pm)} claude={pct(pc)} final={pct(pf)}")
        lam_m.append(hit(pm, hs, aws))
        cl_m.append(hit(pc, hs, aws))
        fn_m.append(hit(pf, hs, aws))
    lines.append(f"λ p_model: {rate(lam_m)}")
    lines.append(f"p_claude: {rate(cl_m)}")
    lines.append(f"p_final: {rate(fn_m)}")
    return "\n".join(lines)

# 리포트 3분할 구분자: ①일정+픽 ②경기별 심층 ③속보+출처
SECTION_SEP = "\n<<<PART>>>\n"

# 리포트 모드 — live_conservative: 조합 금지·하루 최대 2픽
# [§8-18] 스테이킹(staking·flat_pct)을 뺐다 — 봇은 얼마를 걸라고 말하지 않는다.
MODES = {
    "live_conservative": {"allow_parlays": False, "max_picks": 2},
    "research": {"allow_parlays": True, "max_picks": 10},
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
    """팀 승률 + 선발투수 ERA + 순위표 + 최근 3경기 폼. 휴리스틱 승률 모델에는 쓰지 않는다."""
    from datetime import date as date_cls, timedelta

    standings = await client.fetch_standings()
    id_to_name: dict[int, str] = {}
    try:
        teams = await client.fetch_teams()
        for t in (teams or {}).get("teams") or []:
            if t.get("id") and t.get("name"):
                id_to_name[int(t["id"])] = t["name"]
    except Exception as exc:
        logger.warning("[pipeline] MLB 팀 명단 조회 실패 — 순위표 짧은 이름 그대로: %s",
                       exc)
    table = parse_standings(standings, id_to_name)
    win_pct = {k: v["win_pct"] for k, v in table.items()
               if v.get("win_pct") is not None}

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
    form: dict[str, dict] = {}
    days = schedule.get("dates") or []
    slate = days[0].get("date") if days else None
    if slate:
        try:
            start = (date_cls.fromisoformat(slate) - timedelta(days=14)).isoformat()
            form = parse_recent_form(
                await client.fetch_schedule_range(start, slate),
                before=slate, standings=table)
            if form and not client.mock:
                from app.collectors.lineups import MLBLineupClient
                from app.collectors.mlb_boxscore import apply_boxscores

                boxes: dict = {}
                pks = {str(r.get("game_id")) for pkt in form.values()
                       for r in (pkt.get("games") or []) if r.get("game_id")}
                lu = MLBLineupClient()
                for pk in pks:
                    try:
                        boxes[pk] = await lu.fetch_boxscore(pk)
                    except Exception as exc:
                        logger.debug("[pipeline] MLB box %s 생략: %s", pk, exc)
                apply_boxscores(form, boxes)
        except Exception as extra:
            logger.warning("[pipeline] MLB 최근 3경기 조회 실패: %s", extra)
    return {"elo": None, "win_pct": win_pct, "era": era,
            "standings": table, "form": form}


async def _empty_stats() -> dict:
    """[§8-14] KBO·NPB용 빈 스탯. 순위표·ERA 소스가 없으므로 '실데이터 축'이 서지 않는다.

    없는 것을 있는 척하지 않는다 — 2-소스 룰이 그만큼 엄격해지는 것이 정상이다.
    """
    return {"elo": None, "win_pct": {}, "era": {}, "seasons": {}}


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
    sport: str = "mlb", redis=None, sequential: bool = False, force: bool = False,
) -> tuple[str, list[str], dict, dict]:
    """Grok 속보(슬레이트 1콜) ∥ 경기별 심층 리서치.

    반환: (news, news_urls, research_map{game_id: dict}, statuses{game_id: str}).
    리서치는 보조 신호 — 실패해도 파이프라인은 계속 간다 ('리서치 미완' 마킹).

    sequential=True(프리페치)는 전 경기 동시 실행 대신 **경기 단위 순차** 처리다.
    실사고: MLB 10경기 + 축구 17경기를 동시에 리서치해 Perplexity 429를 유발했다.
    """
    import redis.asyncio as aioredis

    from app.research.deep import RESEARCH_CONCURRENCY, get_game_research

    # [A-5단계] 리그별 스위치. 꺼진 종목은 **외부 유료 API를 한 번도 부르지 않는다.**
    #   KBO·NPB는 크롤링으로 완전 대체됐다(2026-08-27). 팬 여론(Grok)도
    #   `coverage.UNCOLLECTED`에 '미수집'으로 선언돼 있으므로 함께 끈다 —
    #   카드가 "미수집"이라고 말하면서 뒤에서 호출하면 표기가 거짓이 된다.
    _use_deep = get_settings().deepsearch_enabled(sport)
    if get_settings().is_disabled("perplexity"):
        _use_deep = False

    async def _empty() -> str:
        return ""

    if _use_deep:
        if get_settings().is_disabled("grok"):
            logger.info("[pipeline] grok disabled — 속보·여론 호출 생략")
            news_task, sentiment_task = _empty(), _empty()
        else:
            _grok = GrokClient()
            news_task = _grok.live_briefing(games, date, league=league)
            # [§8-21] X·커뮤니티 여론 — **별도 호출**이다. 속보 프롬프트에 얹으면
            #   요구가 쌓여 모델이 검색을 포기한다(실사고: 채움률 6/10 → 0/10).
            sentiment_task = _grok.sentiment(games, date, league=league)
    else:
        logger.info("[pipeline] %s — 딥서치·여론 비활성(크롤링 전용)", sport)
        news_task, sentiment_task = _empty(), _empty()
    own_redis = redis is None
    if own_redis:
        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    sem = asyncio.Semaphore(RESEARCH_CONCURRENCY)
    research_map: dict[int, dict | None] = {}
    statuses: dict[int, str] = {}

    async def one(g: dict) -> None:
        if not _use_deep:
            # 딥서치를 안 부른다. 상태를 'off'로 남겨 계측이 "실패"와 구분한다 —
            # 끈 것과 못 받은 것을 섞으면 리포트가 거짓 경보를 낸다.
            research_map[g["id"]] = None
            statuses[g["id"]] = "off"
            return
        async with sem:
            data, status = await get_game_research(
                redis, {**g, "game_id": g["id"]}, sport, force=force)
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
        sent_fut = asyncio.ensure_future(sentiment_task)
        for g in scheduled:
            try:
                await one(g)
            except Exception as exc:  # 개별 경기 실패는 전체를 막지 않는다
                logger.warning("[pipeline] 순차 리서치 실패 %s: %s", g.get("home"), exc)
                statuses[g["id"]] = "missing"
        news_res, sent_res = await asyncio.gather(
            news_fut, sent_fut, return_exceptions=True)
    else:
        results = await asyncio.gather(
            news_task, sentiment_task, *(one(g) for g in scheduled),
            return_exceptions=True)
        news_res, sent_res = results[0], results[1]
    try:
        if isinstance(news_res, BaseException):
            logger.error("[pipeline] grok briefing failed, continuing without news: %s", news_res)
            await notify_api_error(news_res)
            news = ""
        else:
            news = news_res
        sentiment = "" if isinstance(sent_res, BaseException) else (sent_res or "")
        if isinstance(sent_res, BaseException):
            logger.warning("[pipeline] 여론 수집 실패, 없이 진행: %s", sent_res)
    finally:
        if own_redis:
            await redis.aclose()
    # 마크다운 링크 병합 깨짐 방지: 본문에서 링크 제거, URL은 출처로 분리 수집
    news_urls = extract_urls(news)
    news = strip_md_links(news)
    return news, news_urls, research_map, statuses, strip_md_links(sentiment)


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


def _count_by(values) -> dict:
    """[7-2] 상태 문자열 빈도 — 실패 사유 분포를 알림에 싣기 위한 집계."""
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


# [§9 게이트 ③] 출처는 **수집기가 아니라 원본(origin)** 기준이다.
#   네이버를 파이썬 수집기와 Go 크롤러가 각각 긁었다고 "2개 소스 일치(교차)"로
#   세면 **같은 원본이 스스로를 확증**하는 가짜 교차검증이 된다.
SRC_KBO_OFFICIAL = "official_record"   # koreabaseball.com 기록실·일정 · statsapi
SRC_PORTAL = "portal"                  # 네이버 스포츠 · Yahoo!スポーツ
SRC_WEATHER = "weather_api"            # Open-Meteo (다투는 값이 아니다)
SRC_NEWS = "news"                      # 스포츠조선 등 기사 — 원문 인용 발췌
SRC_STATCAST = "statcast"              # Baseball Savant (statsapi와 다른 원본)


def _absorb(research: dict, filled: list[str], source: str) -> list[tuple]:
    """[§9] 병합된 필드를 **게이트① 통과 → 출처 각인** 순서로 흡수한다.

    ⚠️ 순서가 중요하다. 물리 범위 밖 값을 먼저 버리지 않으면, 그 값에 출처가
       각인돼 게이트③에서 "단일 소스지만 사용 가능"으로 통과해버린다.
    """
    from app.engine.physical import screen
    from app.engine.provenance import stamp

    dropped = screen(research, filled)
    bad = {d[0] for d in dropped}
    stamp(research, [f for f in (filled or []) if f not in bad], source)
    return dropped


def _merge_mlb(research: dict, jg: dict, ctx: dict) -> list[str]:
    """KBO `elif sport == "kbo"`와 대칭. statsapi 이름·ERA·순위 → Statcast.

    반환: 실행된 병합 이름. 필드 각인은 `_absorb`가 한다.
    """
    from app.collectors.statcast import enrich_mlb_research

    done: list[str] = []
    official: list[str] = []
    for side in ("home", "away"):
        name = (jg.get(f"{side}_pitcher") or "").strip()
        if not name:
            name = str((jg.get("stats") or {}).get(f"{side}_pitcher") or "").strip()
        if name:
            blk = research.setdefault(f"{side}_pitcher", {})
            if not blk.get("name"):
                blk["name"] = name
                official.append(f"{side}_pitcher.name")
            if not jg.get(f"{side}_pitcher"):
                jg[f"{side}_pitcher"] = name
        era = (jg.get("stats") or {}).get(f"{side}_pitcher_era")
        if era is None and name:
            era = (ctx.get("era") or {}).get(name)
        if era is not None:
            blk = research.setdefault(f"{side}_pitcher", {})
            if blk.get("era_season") is None:
                blk["era_season"] = era
                official.append(f"{side}_pitcher.era_season")
    if official:
        _absorb(research, official, SRC_KBO_OFFICIAL)
        done.append("mlb_statsapi")

    table = ctx.get("standings") or {}
    st_filled: list[str] = []
    for side in ("home", "away"):
        row = table.get(jg.get(side) or "")
        if not row:
            continue
        blk = research.setdefault(f"{side}_standing", {})
        for k, v in row.items():
            if v is not None and blk.get(k) is None:
                blk[k] = v
                st_filled.append(f"{side}_standing.{k}")
    if st_filled:
        _absorb(research, st_filled, SRC_KBO_OFFICIAL)
        done.append("mlb_standings")

    notes = enrich_mlb_research(research, jg, ctx)
    savant: list[str] = []
    for side in ("home", "away"):
        off = research.get(f"{side}_offense") or {}
        for k in ("xwoba_30d", "ops", "obp_30d"):
            if off.get(k) is not None:
                savant.append(f"{side}_offense.{k}")
        p = research.get(f"{side}_pitcher") or {}
        for k in ("xwoba_allowed", "throws", "ip_avg_recent"):
            if p.get(k) is not None:
                savant.append(f"{side}_pitcher.{k}")
    if research.get("park") or research.get("park_factor") is not None:
        if research.get("park"):
            savant.append("park")
        if research.get("park_factor") is not None:
            savant.append("park_factor")
    if savant:
        _absorb(research, savant, SRC_STATCAST)
        done.append("statcast")
    if notes:
        done.append("mlb_enrich")

    usage_f: list[str] = []
    bullpen = ctx.get("bullpen") or {}
    for side, key in (("home", "home"), ("away", "away")):
        b = bullpen.get(jg.get(key)) or {}
        pitches = b.get("bp_pitches_3d")
        if pitches is None:
            continue
        u = research.setdefault(f"{side}_usage", {})
        if u.get("bp_pitches_3d") is None:
            u["bp_pitches_3d"] = pitches
            usage_f.append(f"{side}_usage.bp_pitches_3d")
    form = ctx.get("form") or {}
    for side in ("home", "away"):
        row = form.get(jg.get(side) or "")
        if not row:
            continue
        u = research.setdefault(f"{side}_usage", {})
        for k, v in row.items():
            if v is not None and u.get(k) is None:
                u[k] = v
                usage_f.append(f"{side}_usage.{k}")
    if usage_f:
        bp_f = [f for f in usage_f if "bp_pitches" in f]
        form_f = [f for f in usage_f if f not in bp_f]
        if bp_f:
            _absorb(research, bp_f, SRC_STATCAST)
        if form_f:
            _absorb(research, form_f, SRC_KBO_OFFICIAL)
        done.append("mlb_usage")

    info = (ctx.get("absences") or {}).get(jg.get("game_id")) or {}
    lu = info.get("lineup") or {}
    lu_f: list[str] = []
    prev_status = jg.get("lineup_status") or "none"
    if lu.get("confirmed") and prev_status != "conflict":
        jg["lineup_status"] = "confirmed"
    elif prev_status == "none" and any(
            len((lu.get(s) or {}).get("batting_order") or []) for s in ("home", "away")):
        jg["lineup_status"] = "predicted"
    for side in ("home", "away"):
        order = (lu.get(side) or {}).get("batting_order") or []
        if len(order) < 9:
            continue
        blk = research.setdefault(f"{side}_lineup", {})
        if not blk.get("order"):
            blk["order"] = "-".join(order)
            blk.setdefault("source", "statsapi")
            lu_f.append(f"{side}_lineup.order")
    if lu_f:
        _absorb(research, lu_f, SRC_KBO_OFFICIAL)
        done.append("mlb_lineup")
    return done


def merge_source_data(research: dict, jg: dict, sport: str,
                      statcast_data: dict | None) -> list[str]:
    """[§8-30] 수집 소스를 research에 병합한다. 반환: 실행된 병합 이름들.

    **종목 숫자 소스와 날씨·크롤러는 서로 독립이다.** 하나가 없다고 다른 하나가
    건너뛰어지면 안 된다.

    실사고(2026-08-27) — 조용한 데이터 손실 2건:
      이 로직이 `build_analysis` 안에 인라인으로 있을 때, 네이버 병합이
      `if statcast_data.get("weather"):` **안에** 들어가 있었고
      `elif sport == "npb"`가 `if sport == "kbo"`가 아니라 **그 날씨 if**에
      붙어 있었다. 조건 도달을 실행으로 확인한 결과:

      · **NPB** — 돔경기가 하나라도 있으면 `weather`가 truthy가 돼
        **Yahoo 병합이 아예 실행되지 않았다.** NPB 12팀 중 5팀이 돔이라
        사실상 상시 발생했고, Yahoo는 선발 ERA의 숫자 소스다
        (선발 ERA·타선·최근폼이 통째로 사라진다).
      · **KBO** — 날씨 조회가 실패하면 네이버 병합이 함께 날아갔다
        (선발 ERA·WHIP·평균이닝·손잡이·구종·최근폼·순위).

      둘 다 로그에도 상태값에도 흔적이 남지 않는다. 그래서 **함수로 빼
      테스트가 조건 도달을 직접 확인**하게 했다(test_source_merge.py).
    """
    if not isinstance(statcast_data, dict):
        return []
    done: list[str] = []
    gkey = f"{jg.get('away')}@{jg.get('home')}"

    # 크롤러는 **이름·타순**을 가장 빨리 안다. 공식 ERA는 그 이름 뒤에 채운다.
    # 마지막에 두면 이름이 바뀌며 직전에 채운 ERA가 지워진다(라인업 폴링 경로).
    # ⚠️ 크롤러도 네이버·Yahoo를 긁는다 — 같은 출처다. 수집기가 다르다고
    #    다른 소스로 세면 가짜 교차검증이 된다.
    if statcast_data.get("crawler"):
        from app.collectors.crawler_feed import merge_into_research as _mc

        _absorb(research, _mc(research, jg, statcast_data["crawler"],
                            statcast_data.get("crawler_changes") or []), SRC_PORTAL)
        done.append("crawler")

    if sport == "kbo":
        from app.collectors.kbo_park import merge_into_research as _mp
        from app.collectors.kbo_stats import merge_into_research as _mk
        from app.collectors.naver_kbo import merge_into_research as _mn

        _absorb(research, _mk(research, jg, statcast_data.get("kbo_teams") or {},
                            statcast_data.get("kbo_pitchers") or {}),
              SRC_KBO_OFFICIAL)
        done.append("kbo_stats")
        # 파크팩터가 `park`를 확정값으로 쓰고 네이버는 setdefault라,
        # 이 순서(_mp → _mn)를 지켜야 구장 표기가 덮이지 않는다.
        _absorb(research, _mp(research, jg, statcast_data.get("parks") or {}),
              SRC_KBO_OFFICIAL)
        done.append("kbo_park")
        nv = (statcast_data.get("naver") or {}).get(gkey)
        if nv:
            _absorb(research, _mn(research, jg, nv), SRC_PORTAL)
            done.append("naver")
            mapped = nv.get("naver_status_mapped")
            if not mapped:
                from app.collectors.naver_kbo import status_from_naver as _ns
                mapped = _ns(nv.get("naver_status"))
            # 기록실 0-0 을 live 로 굳히면 예정 경기가 분석에서 빠진다
            # (실측 2026-08-29 game 1447 LG@롯데, 네이버는 경기전).
            if mapped == "scheduled" and jg.get("status") == "live":
                hs, aws = jg.get("home_score"), jg.get("away_score")
                if (hs or 0) == 0 and (aws or 0) == 0:
                    jg["status"] = "scheduled"
                    jg["status_label"] = ""
                    logger.info("[pipeline] 네이버 경기전 — live 0-0 철회 game=%s",
                                jg.get("game_id"))
            elif mapped in ("live", "final", "cancelled") and jg.get("status") == "scheduled":
                jg["status"] = mapped
                jg["status_label"] = STATUS_LABELS.get(mapped, "")
            ho = [p for p in ((research.get("home_lineup") or {}).get("order") or "").split("-") if p.strip()]
            ao = [p for p in ((research.get("away_lineup") or {}).get("order") or "").split("-") if p.strip()]
            if len(ho) >= 9 and len(ao) >= 9:
                prev = jg.get("lineup_status") or "none"
                if prev in ("none", "predicted"):
                    jg["lineup_status"] = "confirmed"
                    jg["lineup_source"] = "네이버"
                    logger.info("[pipeline] KBO 타순 확정 game=%s n=%d/%d",
                                jg.get("game_id"), len(ho), len(ao))
        if statcast_data.get("kbo_usage"):
            from app.collectors.kbo_usage import merge_into_research as _mu

            _absorb(research, _mu(research, jg, statcast_data["kbo_usage"]), SRC_PORTAL)
            done.append("kbo_usage")
        # ⚠️ 등록 명단 병합은 **투수 소모 뒤**여야 한다 — 주전(타석 상위 9명)이
        #    먼저 산출돼야 "주전인데 말소됐다"를 판정할 수 있다.
        if statcast_data.get("kbo_roster"):
            from app.collectors.kbo_roster import merge_into_research as _mr

            _absorb(research, _mr(research, jg, statcast_data["kbo_roster"]),
                    SRC_KBO_OFFICIAL)
            done.append("kbo_roster")
        if statcast_data.get("kbo_news") is not None:
            from app.collectors.kbo_news import merge_into_research as _mnews

            _absorb(research, _mnews(research, jg, statcast_data["kbo_news"]),
                    SRC_NEWS)
            done.append("kbo_news")
        # [§8-34] 카드 ④칸("무게") — 순위·게임차·잔여경기.
        #   그날 프리뷰 5경기가 10팀 순위를 모두 담고 있어 **추가 HTTP가 없다**
        #   (순위 전용 엔드포인트는 403이다 — 2026-08-27 실측).
        if statcast_data.get("naver"):
            from app.collectors.naver_kbo import build_standings
            from app.collectors.naver_kbo import merge_standings_into_research as _ms

            _absorb(research, _ms(research, jg, build_standings(statcast_data["naver"])),
                  SRC_PORTAL)
            done.append("standings")
    elif sport == "npb":
        from app.collectors.npb_stats import merge_into_research as _ms
        from app.collectors.yahoo_npb import merge_into_research as _my

        yv = (statcast_data.get("yahoo") or {}).get(gkey)
        if yv:
            _absorb(research, _my(research, jg, yv), SRC_PORTAL)
            done.append("yahoo")
        # 공식 팀 OBP는 Yahoo 선발 뒤에 얹는다 — 타선 숫자를 덮고 ERA는 안 건드린다.
        _absorb(research, _ms(research, jg, statcast_data.get("npb_teams") or {}),
                SRC_KBO_OFFICIAL)
        done.append("npb_stats")
        if statcast_data.get("npb_form"):
            from app.collectors.npb_form import merge_into_research as _mf

            _absorb(research, _mf(research, jg, statcast_data["npb_form"]), SRC_PORTAL)
            done.append("npb_form")
    elif sport == "mlb":
        done.extend(_merge_mlb(research, jg, statcast_data))

    # [A-1단계] 딥서치가 주던 필드를 **이미 수집한 값으로 직접 산출**한다.
    #   빈칸만 채운다 — 축구는 아직 딥서치가 채우므로 덮으면 안 된다.
    #   ⚠️ 소스는 파생이므로 원본 소스를 그대로 각인한다(새 출처가 아니다).
    if sport in ("kbo", "npb", "mlb"):
        from app.engine.derive import apply as _derive

        _absorb(research, _derive(research, jg, statcast_data.get("kbo_usage")),
                SRC_PORTAL)

    if statcast_data.get("weather"):
        from app.collectors.weather import merge_into_research as _mw

        _mw(research, jg, statcast_data["weather"])
        # ⚠️ **채워진 경우에만** 각인한다. 돔구장은 `weather`를 채우지 않는데
        #   그대로 각인하면 게이트 ③이 "관측 없음 → 미확인"으로 잡아 분포를
        #   오염시킨다(실측 2026-08-27: 미확인 4건이 전부 이것이었다).
        if research.get("weather"):
            _absorb(research, ["weather"], SRC_WEATHER)
        done.append("weather")
    return done


async def load_source_bundle(redis, sport: str, date: str) -> dict:
    """Redis 캐시에서만 읽는다. HTTP 재수집은 하지 않는다.

    라인업 폴링이 30분마다 공식 기록실을 치면 안 된다. 숫자가 없으면 그 칸은
    비운 채로 병합한다 — 없는 값을 만들어 넣지 않는다.
    """
    from app.collectors.crawler_feed import load_changes, load_snapshot

    bundle: dict = {
        "crawler": await load_snapshot(redis, sport, date),
        "crawler_changes": await load_changes(redis, sport, date),
    }
    if sport == "kbo":
        from app.collectors.kbo_park import load as load_park
        from app.collectors.kbo_roster import load as load_roster
        from app.collectors.kbo_stats import load as load_kbo_stats
        from app.collectors.kbo_usage import load as load_usage
        from app.collectors.naver_kbo import load as load_naver

        kteams, kpitchers = await load_kbo_stats(redis, date)
        bundle.update({
            "kbo_teams": kteams or {},
            "kbo_pitchers": kpitchers or {},
            "parks": await load_park(redis) or {},
            "naver": await load_naver(redis, date) or {},
            "kbo_usage": await load_usage(redis, date) or {},
            "kbo_roster": await load_roster(redis, date) or {},
        })
    elif sport == "npb":
        from app.collectors.npb_stats import load as load_npb_stats
        from app.collectors.yahoo_npb import load as load_yahoo
        from app.collectors.npb_form import load as load_npb_form

        bundle["yahoo"] = await load_yahoo(redis, date) or {}
        bundle["npb_teams"] = await load_npb_stats(redis, date) or {}
        bundle["npb_form"] = await load_npb_form(redis, date) or {}
    elif sport == "mlb":
        from app.collectors.mlb import load_ctx as load_mlb_ctx
        from app.collectors.park import load as load_parks
        from app.collectors.statcast import load as load_statcast

        off, pit, bp, bat, league = await load_statcast(redis, date)
        ctx = await load_mlb_ctx(redis, date)
        bundle.update({
            "offense": off or {}, "pitchers": pit or {}, "bullpen": bp or {},
            "batters": bat or {}, "league": league or {},
            "parks": await load_parks(redis) or {},
            "standings": ctx.get("standings") or {},
            "form": ctx.get("form") or {},
            "era": ctx.get("era") or {},
            "weather": ctx.get("weather") or {},
            "absences": ctx.get("absences") or {},
        })
    return bundle


def analysis_cache_ready(raw: str | None, date: str) -> bool:
    """당일 예정 경기에 Claude 판정(`p_claude`)이 붙어 있는가.

    키만 있으면 준비됨으로 치면 안 된다. 실측 2026-08-28: 캐시는 있는데
    `p_claude`가 전원 null이라 승률 없는 카드를 보낼 뻔했다.
    다음날 경기가 같은 키에 섞여 있어도 **요청 날짜**만 본다.
    """
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return False
    try:
        _y, m, d = date.split("-")
        mmdd = f"{int(m):02d}/{int(d):02d}"
    except (ValueError, AttributeError):
        return False
    games = []
    for g in data.get("games") or []:
        if g.get("status") not in (None, "scheduled"):
            continue
        stamp = str(g.get("starts_at_kst") or g.get("starts_at") or "")
        if stamp.startswith(mmdd) or date in stamp:
            games.append(g)
    if not games:
        return False
    return all(isinstance(g.get("p_claude"), (int, float)) for g in games)


async def ensure_analysis_cache(pool, redis, sport: str, date: str) -> bool:
    """라인업 재판정 전에 `analysis:{sport}:{date}` 가 있게 한다.

    키가 있어도 당일 판정이 없으면 파이프라인을 1회 돌린다.
    프리페치가 KBO·NPB를 안 돌던 구멍: 그날 사용자가 안 물어보면
    폴링이 타순을 잡아도 `rejudge_after_lineup`이 즉시 False를 반환했다.
    """
    raw = await redis.get(f"analysis:{sport}:{date}")
    if analysis_cache_ready(raw, date):
        return True
    logger.info("[pipeline] analysis 캐시 없음·무판정 — %s %s 파이프라인 1회",
                sport, date)
    try:
        await run_pipeline(pool, redis, sport=sport, date=date,
                           force_refresh=True, sequential_research=True)
    except Exception as exc:
        logger.warning("[pipeline] analysis 캐시 생성 실패 %s %s: %s",
                       sport, date, exc)
        return False
    raw = await redis.get(f"analysis:{sport}:{date}")
    ready = analysis_cache_ready(raw, date)
    if not ready:
        logger.warning("[pipeline] analysis 캐시 재생성 후에도 당일 판정 없음 — %s %s",
                       sport, date)
    return ready


def starter_change_notes(research: dict, before: dict) -> list[str]:
    """병합 전후 선발 이름이 달라진 줄. 없으면 빈 목록."""
    notes = []
    for side, label in (("home", "홈"), ("away", "원정")):
        old = (before.get(side) or "").strip()
        new = (((research.get(f"{side}_pitcher") or {}).get("name")) or "").strip()
        if old and new and old != new:
            notes.append(f"{label} 선발 변경: {old} → {new}")
    return notes


async def build_analysis(
    pool: asyncpg.Pool, sport: str, date: str,
    team: str | None = None, league_key: str | None = None, progress=None,
    redis=None, sequential_research: bool = False,
    stages_out: list | None = None, force_research: bool = False,
    include_final: bool = False,
) -> dict:
    """league_key 지정 시 그 리그만 수집·판정 (요청 범위 밖 API 호출 금지).

    sequential_research=True(프리페치)는 경기별 리서치를 순차 처리해 429를 피한다.
    """
    settings = get_settings()
    progress = progress or _noop_progress

    # [7-2] 단계별 계측 — 끝나면 실패 **요약 1건**으로 묶어 알린다.
    from app.alerts import StageResult

    stages: list = stages_out if stages_out is not None else []

    async def record(name, ok, total, *, cause=None, detail="", impact="",
                     exc=None, unit="경기", expect_full=True, zero_ok=False):
        """단계 결과를 기록한다. **여기서 발송하지 않는다.**

        🔴 종전에는 단계마다 즉시 발송해 한 번의 분석에서 알림이 7~8건 쏟아졌고,
           정작 카드가 안 보였다(실측 2026-08-27).

        ⚠️ `unit`은 ok/total이 무엇을 세는지다. 기본 "경기"를 그대로 두고 팀 수·
           값 개수를 넣으면 "출처 대조 438경기" 같은 거짓 숫자가 나간다.
        ⚠️ `expect_full=False`는 부분 수집이 정상인 단계(기사·결장·날씨 등).
        """
        from app.alerts import classify_exception, our_frames

        st = StageResult(
            name=name, ok=ok, total=total,
            cause=cause or (classify_exception(exc) if exc is not None else None),
            detail=detail or (f"{type(exc).__name__}: {exc}" if exc is not None else ""),
            frames=our_frames(exc) if exc is not None else [],
            impact=impact, unit=unit, expect_full=expect_full, zero_ok=zero_ok,
        )
        stages.append(st)
        if st.severity != "정상":
            logger.warning("[pipeline] 단계 %s — %s", st.severity, st.line())
        return st

    await progress(1, 4, "일정·스탯 수집")

    # 1) 일정 fetch + upsert (이후 단계가 games 행에 의존)
    schedule_stale = False      # 일정 갱신에 실패해 DB 기존 일정으로 갔는가
    if sport == "mlb":
        mlb = MLBClient()
        schedule = await mlb.fetch_schedule(date)
        await upsert_games(pool, date, client=mlb, schedule=schedule)
        parsed = _parse_games(schedule)
        if include_final:
            ext_ids = [g["ext_id"] for g in parsed]
        else:
            ext_ids = [g["ext_id"] for g in parsed if g["status"] == "scheduled"]
        stats_coro = _collect_mlb_stats(mlb, schedule)
        league = "MLB"
    elif sport in ("kbo", "npb"):
        # [Odds 이관 2026-08-27] KBO·NPB 일정은 **공식 소스**에서 온다.
        #   KBO = koreabaseball.com · NPB = Yahoo!スポーツ.
        #   🔴 종전에는 Odds API `/scores`가 유일한 소스였고, 크레딧이 마르면
        #     응답 전체가 "크레딧 소진" 한 줄로 대체됐다. 이 두 종목은 배당을
        #     판정에 쓰지 않으므로(#38·#39) 배당 때문에 죽을 이유가 없다.
        #   ⚠️ Statcast에 해당하는 타구 데이터가 없다 → λ를 산출할 수 없다.
        #      p_model은 무효가 되고 확률은 **판정(p_claude) 단독**으로 간다.
        #      그래서 2-소스 룰의 '모델' 축이 서지 않으며, 추천 자격은 대부분
        #      통과하지 못한다 — 이는 버그가 아니라 **의도된 보수성**이다.
        counts = {"scheduled": 0, "final": 0, "total": 0}
        try:
            if sport == "kbo":
                from app.collectors.kbo import upsert_schedule as _upsert_sched
            else:
                from app.collectors.yahoo_npb import upsert_schedule as _upsert_sched
            counts = await _upsert_sched(pool, date)
        except Exception as exc:
            # 공식 소스가 죽어도 DB의 기존 일정으로 간다 — 없는 것을 만들지는 않는다.
            logger.warning("[pipeline] %s 일정 갱신 실패(%s) — DB의 기존 일정으로 진행",
                           sport, type(exc).__name__)
            schedule_stale = True
        from datetime import date as date_cls

        day = date_cls.fromisoformat(date)
        # asyncpg Date 코덱은 str에 toordinal이 없어 터진다.
        # 실측 2026-08-28 17:25: `$2::date` + '2026-08-28' → 파이프라인 실패,
        # 시그만 남아 다음 폴링이 재시도를 스킵했다.
        if include_final:
            rows = await pool.fetch(
                """
                SELECT ext_id FROM games
                 WHERE sport = $1
                   AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2
                   AND status = ANY($3::text[])
                """,
                sport, day, ["scheduled", "final", "live"])
        else:
            # 요청 날짜만. 실측 2026-08-28: `starts_at >= now()-12h`만 있으면
            # 다음날·모레 scheduled까지 한 캐시에 섞여 15경기가 됐다.
            rows = await pool.fetch(
                """SELECT ext_id FROM games WHERE sport = $1 AND status = 'scheduled'
                     AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2
                     AND starts_at >= now() - interval '12 hours'""",
                sport, day)
        ext_ids = [r["ext_id"] for r in rows]
        stats_coro = _empty_stats()
        league = LEAGUE_LABEL_BY_SPORT.get(sport, sport.upper())
        logger.info("[pipeline] %s 일정 %d건 (예정 %d / 종료 %d)%s",
                    league, len(ext_ids), counts["scheduled"], counts["final"],
                    " ⚠️ 공식 소스 실패 — 기존 일정" if schedule_stale else "")
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
    if include_final:
        games = mark_finals_as_sim(games)
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
    if sport in ("mlb", "kbo", "npb"):
        # 야구는 배당·토탈 라인을 조회하지 않는다. snapshot_odds 도 0을 반환한다.
        active_keys = []
    else:
        from app.leagues import LEAGUES as _L

        labels_present = {g["league"] for g in games}
        active_keys = [c["odds_key"] for c in _L.values() if c["label"] in labels_present]

    await progress(2, 4, "배당·딥서치 수집")
    if stats_coro is None:
        stats_coro = _collect_soccer_stats({g["league"] for g in games})
    # 2) 스탯 ∥ 배당 ∥ 딥서치 병렬 수집 (딥서치도 요청 범위의 경기로만 한정)
    async def _odds_or_none():
        """배당 실패가 분석을 죽이지 않는다 — 배당은 표시용이고 판정에 안 쓴다."""
        if not active_keys:
            return []          # 조회할 리그가 없다 — API를 부르지 않는다
        try:
            return await snapshot_odds(pool, sport, client=OddsClient(),
                                       only_keys=active_keys)
        except (ProviderDisabledError, ProviderBlockedError):
            logger.info("[pipeline] 배당 스냅샷 생략 — odds disabled/blocked")
            return []
        except (ApiQuotaError, ApiAuthError) as exc:
            logger.warning("[pipeline] 배당 스냅샷 생략(%s) — 전 마켓 ⚪로 나간다",
                           type(exc).__name__)
            return []

    stats, _odds_rows, (news, news_urls, research_map, research_statuses,
                        sentiment) = await asyncio.gather(
        stats_coro,
        _odds_or_none(),
        _collect_research(pool, games, date, league, sport=sport, redis=redis,
                          sequential=sequential_research, force=force_research),
    )

    # 🔴 종전 분모가 `len(games) or 1` — 분자와 같아 **절대 실패할 수 없었다.**
    #   일정에 몇 경기가 있어야 하는지는 미리 알 수 없다. 그러면 분모를 지어내지
    #   말고 **이분법(있었나/없었나)**으로 재는 것이 정직하다. 개수는 detail에.
    await record("경기 적재", 1 if games else 0, 1, unit="건",
                 detail=f"{len(games)}경기 적재",
                 cause=None if games else "missing",
                 impact="분석할 경기가 없습니다")
    # [§8-10] 배당 수집 — 종전 미계측. 0건이면 전 마켓이 ⚪(배당 미수집)로 나가는데
    #         그 사실이 어디에도 기록되지 않았다.
    _sched_now = [g for g in games if g.get("status") == "scheduled"]
    if sport not in ("mlb", "kbo", "npb") and active_keys:
        from app.api_guard import is_blocked, is_disabled

        _odds_unusable = is_disabled("odds") or await is_blocked("odds")
        if _odds_unusable:
            await record("배당 수집", 0, max(1, len(_sched_now)),
                         cause=None,
                         detail="odds 미사용 또는 크레딧 차단",
                         unit="경기", expect_full=False, zero_ok=True,
                         impact="배당 표시가 비고 축구 마켓 가격이 빠집니다")
        else:
            await record("배당 수집", int(_odds_rows or 0), max(1, len(_sched_now)),
                         cause=None if _odds_rows else "missing",
                         detail=f"스냅샷 {_odds_rows or 0}행 / 예정 {len(_sched_now)}경기",
                         unit="경기", expect_full=False,
                         impact="배당 표시가 비고 축구 마켓 가격이 빠집니다")
    # 분모는 **예정 경기**다. 리서치는 scheduled 경기만 조사하므로 전체 경기를
    # 분모로 쓰면 저녁 시간대(진행 중 경기 다수)에 "5/15 실패"처럼 잘못 경보한다.
    # (실측 2026-08-26 10:00: 15경기 중 6경기만 예정이었는데 5/15로 표시됐다)
    _sched_ids = {g["id"] for g in games if g.get("status") == "scheduled"}
    # [A-5단계] `off`는 **끈 것**이지 실패가 아니다. `stale_fallback`은 구캐시가
    #   있어 분석은 된다 — 못 받은 것(`missing`)과 섞으면 거짓 경보다.
    _OK_STATES = ("refreshed", "cached", "off", "stale_fallback")
    _ok_research = sum(1 for gid, st in research_statuses.items()
                       if gid in _sched_ids and st in _OK_STATES)
    _deep_off = (not get_settings().deepsearch_enabled(sport)
                 or get_settings().is_disabled("perplexity"))
    if not _deep_off:
        await record("여론 수집", 1 if sentiment.strip() else 0, 1,
                     cause=None if sentiment.strip() else "missing",
                     detail=f"{len(sentiment)}자" if sentiment else "",
                     unit="건",
                     impact="팬 여론·목격담 없이 판정합니다")
    _research_detail = "딥서치 비활성 — 크롤링 전용"
    if not _deep_off:
        _bad = {k: v for k, v in _count_by(research_statuses.values()).items()
                if k not in _OK_STATES}
        _research_detail = ", ".join(f"{k}:{v}" for k, v in sorted(_bad.items()))
    # 분모는 예정 경기다. 전체 경기 수와 비교하면 끝난 경기 때문에 🔴가 된다.
    _research_total = len(_sched_ids) or len(games)
    if _deep_off:
        _research_cause = None
        _ok_research = _research_total
    elif _ok_research == _research_total:
        _research_cause = None
    elif _ok_research == 0:
        _research_cause = "missing"
    else:
        _research_cause = None     # 일부만 실패 → 🟡 부분. 전량만 🔴
    await record("리서치", _ok_research, _research_total,
                 cause=_research_cause,
                 detail=_research_detail,
                 unit="경기",
                 impact="해당 경기는 결장·불펜 정보 없이 판정됩니다")

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
        if sport == "soccer":
            elo = stats.get("elo")
            p_model3 = elo.probs(g["home"], g["away"], g["league"]) if elo else None
            if p_model3:
                p_model, model_valid = p_model3[0], True
            else:
                p_model, model_valid = 0.5, False  # 모델 무효 — 앙상블에서 제외
        else:
            # 야구(MLB·KBO·NPB) — 모델은 λ 분포. 승률+ERA 휴리스틱 없음.
            p_model, model_valid = 0.5, False
        if sport in ("mlb", "kbo", "npb"):
            # 승부 배당·암시확률은 야구 판정에 넣지 않는다. 잔여 h2h 스냅샷도 무시.
            market_probs, best_odds = None, {}
        else:
            market_probs, best_odds = await _market_probs(
                pool, g["id"], g["home"], g["away"])
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
            # [§2] 선발 투수명 — Statcast 투수 지표(허용 xwOBA)를 붙이는 키다.
            #      이게 빠지면 merge_into_research가 투수를 못 찾아 λ의
            #      '상대 선발 억제력'이 통째로 누락된다 (2026-08-25 실측: 14/14경기).
            "home_pitcher": g.get("home_pitcher"),
            "away_pitcher": g.get("away_pitcher"),
            # [§2] 결장 수집(boxscore 조회)의 키. 빠지면 absences가 통째로 0이 된다
            # — 선발 투수명 누락과 같은 유형의 사고였다(2026-08-26 실측: 결장 0경기).
            "ext_id": g.get("ext_id"),
            "starts_at": g["starts_at"].isoformat(),
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "status": g["status"],
            "_sim_actual": g.get("_sim_actual"),
            # [3] 강제 재조사 트리거 — 라인업이 방금 확정됐거나 선발이 바뀌면
            #     6시간 캐시라도 내용이 실제로 달라진다 (deep.needs_refresh)
            "lineup_just_confirmed": bool(
                g.get("lineup_status") == "confirmed"
                and g.get("lineup_confirmed_at") is not None
                and (datetime.now(UTC) - g["lineup_confirmed_at"]).total_seconds() < 3600),
            "starter_changed": bool(g.get("lineup_status") == "conflict"),
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

    # [§8-24] 🔴 **수집을 판정보다 먼저** 한다.
    #   실사고(2026-08-26): 이 블록이 판정 뒤에 있어 **판정이 크롤링 데이터를 아예
    #   못 봤다.** 네이버가 류현진 ERA 4.02·황동하 4.82를 받아왔는데 판정은
    #   "ERA 미수집으로 비교 불가"라며 전 경기를 저신뢰로 내렸다.
    #   수집한 정보가 판정에 도달하지 않으면 수집한 의미가 없다.
    statcast_data = None
    if redis is not None:
        try:
            if sport == "mlb":
                from app.collectors.absences import fetch_for_games as fetch_absences
                from app.collectors.park import load as load_parks
                from app.collectors.statcast import load as load_statcast
                from app.collectors.statcast import refresh as refresh_statcast
                from app.collectors.weather import fetch_for_games as fetch_weather

                off, pit, bp, bat, league = await load_statcast(redis, date)
                if not off:
                    try:
                        await refresh_statcast(redis, date)
                        off, pit, bp, bat, league = await load_statcast(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] Statcast 재수집 실패: %s", exc)
                # [§2] 수치는 전부 정식 API로 — Perplexity 쿼터와 무관하다.
                #      실패해도 해당 항목만 비고 파이프라인은 계속 간다.
                upcoming_rows = [g for g in judge_games if g.get("status") == "scheduled"]
                try:
                    weather = await fetch_weather(upcoming_rows)
                except Exception as exc:
                    logger.warning("[pipeline] 날씨 수집 실패: %s", exc)
                    weather = {}
                try:
                    absences = await fetch_absences(upcoming_rows)
                except Exception as exc:
                    logger.warning("[pipeline] 결장 수집 실패: %s", exc)
                    absences = {}
                statcast_data = {
                    "offense": off, "pitchers": pit, "bullpen": bp, "batters": bat,
                    "league": league, "parks": await load_parks(redis),
                    "weather": weather, "absences": absences,
                    "standings": (stats or {}).get("standings") or {},
                    "era": (stats or {}).get("era") or {},
                    "form": (stats or {}).get("form") or {},
                }
                try:
                    from app.collectors.mlb import save_ctx as save_mlb_ctx

                    await save_mlb_ctx(redis, date, statcast_data)
                except Exception as exc:
                    logger.warning("[pipeline] MLB ctx 캐시 저장 실패: %s", exc)
                logger.info("[pipeline] 정식 API 입력 — 타선 %d팀 / 투수 %d명 / 불펜 %d팀 / "
                            "타자랭킹 %d팀 / 구장 %d개 / 날씨 %d경기 / 결장 %d경기 / "
                            "리그평균 %s",
                            len(off), len(pit), len(bp), len(bat),
                            len(statcast_data["parks"]), len(weather), len(absences),
                            league or "없음(상수 사용)")
                # [§8-10] 종전 미계측 3단계. 결장 0/15 사고가 늦게 발견된 이유가 이것이다
                #         — 조용히 비어도 아무 데도 기록되지 않았다.
                _n = max(1, len(upcoming_rows))
                await record("날씨", len(weather), _n,
                             cause=None if weather else "missing",
                             unit="경기", expect_full=False,
                             impact="구장 날씨가 토탈 λ에 반영되지 않습니다")
                await record("결장", len(absences), _n,
                             cause=None if absences else "missing",
                             unit="경기", expect_full=False,
                             impact="결장 선수가 승률 조정에 반영되지 않습니다")
                # 🔴 분모가 **자기 자신**이었다 — ok == total이라 이 계측은 절대
                #   실패할 수 없었다. 계측이 아니라 장식이다.
                #   MLB는 30구장이다(실측 2026-08-27: park.load()가 30팀 반환).
                await record("구장", len(statcast_data["parks"]), MLB_PARKS,
                             cause=None if statcast_data["parks"] else "missing",
                             unit="구장",
                             impact="파크팩터 없이 리그 평균으로 λ를 냅니다")
            elif sport == "kbo":
                # [§8-14] KBO 공식 기록실 숫자 지표 — 딥서치가 숫자를 못 가져오는
                #   것이 실측으로 확인돼(2026-08-26) 정식 기록을 1차 소스로 쓴다.
                #   ⚠️ **시즌 누적**이다 — MLB의 15경기 창(§8-6)과 성격이 다르며
                #      research에 window="season"으로 표기된다.
                from app.collectors.kbo_stats import load as load_kbo_stats
                from app.collectors.kbo_stats import refresh as refresh_kbo_stats

                # [§8-19] 네이버 크롤링 — **LLM 0회.** 선발·구종·폼·순위·상대전적.
                #   딥서치보다 먼저 돌려 빈칸을 줄인다(딥서치는 남은 것만 조회).
                from app.collectors.naver_kbo import load as load_naver
                from app.collectors.naver_kbo import refresh as refresh_naver

                naver = await load_naver(redis, date)
                if not naver:
                    try:
                        await refresh_naver(redis, date)
                        naver = await load_naver(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] 네이버 KBO 수집 실패: %s", exc)
                        naver = {}
                kteams, kpitchers = await load_kbo_stats(redis, date)
                if not kteams:
                    try:
                        await refresh_kbo_stats(redis, date)
                        kteams, kpitchers = await load_kbo_stats(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] KBO 지표 수집 실패: %s", exc)
                # [§8-25] 파크팩터 — 잠실 0.89 vs 사직 1.21. 이게 빠지면
                #   λ가 구장 효과를 통째로 놓친다(매번 '파크팩터 미확보'였다).
                from app.collectors.crawler_feed import load_changes, load_snapshot
                from app.collectors.kbo_park import load as load_park
                from app.collectors.kbo_park import refresh as refresh_park

                parks = await load_park(redis)
                if not parks:
                    try:
                        await refresh_park(redis)
                        parks = await load_park(redis)
                    except Exception as exc:
                        logger.warning("[pipeline] KBO 파크팩터 산출 실패: %s", exc)
                # [§8-26] 날씨 — 구장 좌표를 넣어 MLB 수집기를 그대로 쓴다.
                #   고척은 돔이라 조회하지 않는다(dome=True만 남긴다).
                from app.collectors.weather import fetch_for_games as fetch_weather

                _up = [g for g in judge_games if g.get("status") == "scheduled"]
                try:
                    kweather = await fetch_weather(_up, redis=redis)
                except Exception as exc:
                    logger.warning("[pipeline] KBO 날씨 수집 실패: %s", exc)
                    kweather = {}
                # [§8-33] 투수 소모 — 카드 ①칸. **가장 중요한 칸이다.**
                #   "어제 불펜 5명이 26타자를 상대했다"는 시즌 ERA보다 오늘 승패를
                #   잘 설명하는데, λ는 시즌 누적만 봐서 통째로 놓쳤다.
                #   실측(2026-08-26): KIA 투수 9명·구원 37타자 vs 삼성 4명·11타자.
                from app.collectors.kbo_usage import load as load_usage
                from app.collectors.kbo_usage import refresh as refresh_usage

                usage = await load_usage(redis, date)
                if not usage:
                    try:
                        await refresh_usage(redis, date)
                        usage = await load_usage(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] KBO 투수 소모 수집 실패: %s", exc)
                        usage = {}
                # [A-2단계] 1군 등록 명단 — 결장 판정의 절반. **LLM 0회.**
                #   KBO는 **말소로 결장을 알린다.** 그동안 이 정보는 Perplexity
                #   산문에서만 왔는데, 공식 명단이 공개돼 있고 파싱하면 끝난다.
                from app.collectors.kbo_roster import load as load_roster
                from app.collectors.kbo_roster import refresh as refresh_roster

                roster = await load_roster(redis, date)
                if not roster:
                    try:
                        await refresh_roster(redis, date)
                        roster = await load_roster(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] KBO 등록 명단 수집 실패: %s", exc)
                        roster = {}
                # [A-3단계] 경기 전 기사 **원문 발췌**. 요약하지 않는다.
                #   직접 인용만 뽑으므로 기자의 전망·평가가 섞이지 않는다.
                #   ⚠️ 게시 시각이 경기 시작 **이전**인 것만 — 경기 후 기사는 누출이다.
                from app.collectors.kbo_news import fetch_for_games as fetch_news

                try:
                    news_quotes = await fetch_news(_up, date)
                except Exception as exc:      # 기사 실패가 분석을 막지 않는다
                    logger.warning("[pipeline] KBO 기사 발췌 실패: %s", exc)
                    news_quotes = {}
                statcast_data = {"kbo_teams": kteams, "kbo_pitchers": kpitchers,
                                 "naver": naver, "parks": parks, "weather": kweather,
                                 "kbo_usage": usage, "kbo_roster": roster,
                                 "kbo_news": news_quotes,
                                 "crawler": await load_snapshot(redis, "kbo", date),
                                 "crawler_changes": await load_changes(redis, "kbo", date)}
                await record("날씨", len(kweather), max(1, len(_up)),
                             cause=None if kweather else "missing",
                             unit="경기", expect_full=False,
                             impact="기온·바람이 토탈 λ에 반영되지 않습니다")
                logger.info("[pipeline] KBO 지표 — 팀 %d / 투수 %d",
                            len(kteams), len(kpitchers))
                await record("네이버 수집", len(naver), max(1, len(games)),
                             cause=None if naver else "missing",
                             detail=f"{len(naver)}경기 · 선발·폼·순위 (LLM 0회)",
                             unit="경기",
                             impact="선발·최근폼을 딥서치에만 의존하게 됩니다")
                await record("투수 소모", len(usage), KBO_TEAMS,
                             cause=None if usage else "missing",
                             detail=f"{len(usage)}팀 · 최근 3경기 등판 (LLM 0회)",
                             unit="팀",
                             impact="카드 ①칸(불펜 가용)이 '모름'으로 나갑니다")
                await record("기사 발췌", len(news_quotes), max(1, len(_up)),
                             cause=None if news_quotes else "missing",
                             detail=f"{len(news_quotes)}경기 인용 (원문 그대로·LLM 0회)",
                             unit="경기", expect_full=False,
                             impact="감독 발언·로테이션 계획이 빠집니다")
                await record("1군 등록", len(roster), KBO_TEAMS,
                             cause=None if roster else "missing",
                             detail=f"{len(roster)}팀 명단 (LLM 0회)",
                             unit="팀",
                             impact="결장 판정이 딥서치 산문에만 의존합니다")
                await record("파크팩터", len(parks), KBO_PARKS,
                             cause=None if parks else "missing",
                             detail=f"구장 {len(parks)}/9 실측",
                             unit="구장",
                             impact="구장 효과 없이 λ를 냅니다 (잠실 0.89 · 사직 1.21)")
                await record("KBO 지표", len(kteams), KBO_TEAMS,
                             cause=None if kteams else "missing",
                             detail=f"팀 {len(kteams)}/10 · 투수 {len(kpitchers)}명",
                             unit="팀",
                             impact="숫자 지표 없이 서술만으로 판정하게 됩니다")
            elif sport == "npb":
                # [§8-20] Yahoo 선발·불펜 + npb.jp 팀 타격(OBP). 둘 다 LLM 0회.
                from app.collectors.npb_stats import load as load_npb_stats
                from app.collectors.npb_stats import refresh as refresh_npb_stats
                from app.collectors.yahoo_npb import load as load_yahoo
                from app.collectors.yahoo_npb import refresh as refresh_yahoo

                yh = await load_yahoo(redis, date)
                if not yh:
                    try:
                        await refresh_yahoo(redis, date)
                        yh = await load_yahoo(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] Yahoo NPB 수집 실패: %s", exc)
                        yh = {}
                nteams = await load_npb_stats(redis, date)
                if not nteams:
                    try:
                        await refresh_npb_stats(redis, date)
                        nteams = await load_npb_stats(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] NPB 지표 수집 실패: %s", exc)
                        nteams = {}
                from app.collectors.npb_form import lacks_opponent_context
                from app.collectors.npb_form import load as load_npb_form
                from app.collectors.npb_form import refresh as refresh_npb_form
                from app.collectors.yahoo_npb import YahooNPBClient as _YahooStandings
                from app.collectors.yahoo_npb import parse_standings as _parse_npb_standings

                npb_standings: dict = {}
                try:
                    npb_standings = _parse_npb_standings(
                        await _YahooStandings().standings())
                except Exception as exc:
                    logger.warning("[pipeline] NPB 순위표 실패: %s", exc)
                    npb_standings = {}
                nform = await load_npb_form(redis, date)
                if not nform or (npb_standings and lacks_opponent_context(nform)):
                    try:
                        await refresh_npb_form(
                            redis, date, standings=npb_standings or None)
                        nform = await load_npb_form(redis, date)
                    except Exception as exc:
                        logger.warning("[pipeline] NPB 최근 3경기 수집 실패: %s", exc)
                        nform = {}
                from app.collectors.crawler_feed import load_changes, load_snapshot

                from app.collectors.weather import fetch_for_games as fetch_weather

                _up = [g for g in judge_games if g.get("status") == "scheduled"]
                try:
                    nweather = await fetch_weather(_up, redis=redis)
                except Exception as exc:
                    logger.warning("[pipeline] NPB 날씨 수집 실패: %s", exc)
                    nweather = {}
                statcast_data = {"yahoo": yh, "npb_teams": nteams,
                                 "npb_form": nform,
                                 "weather": nweather,
                                 "crawler": await load_snapshot(redis, "npb", date),
                                 "crawler_changes": await load_changes(redis, "npb", date)}
                await record("날씨", len(nweather), max(1, len(_up)),
                             cause=None if nweather else "missing",
                             unit="경기", expect_full=False,
                             impact="기온·바람이 토탈 λ에 반영되지 않습니다")
                await record("Yahoo 수집", len(yh), max(1, len(games)),
                             cause=None if yh else "missing",
                             detail=f"{len(yh)}경기 · 선발·불펜 (LLM 0회)",
                             unit="경기",
                             impact="NPB는 선발 지표 없이 판정 단독으로 갑니다")
                await record("NPB 지표", len(nteams), NPB_TEAMS,
                             cause=None if nteams else "missing",
                             detail=f"팀 {len(nteams)}/12 · 시즌 OBP",
                             unit="팀",
                             impact="팀 타선 없이 선발 ERA만으로 λ를 냅니다")
                await record("NPB 최근 3경기", len(nform), NPB_TEAMS,
                             cause=None if nform else "missing",
                             detail=f"{len(nform)}팀 · Yahoo 박스스코어",
                             unit="팀", expect_full=False,
                             impact="검증 전 NPB 추천은 게이트에서 탈락합니다")
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

    # [§8-24] 병합 결과를 **jg["research"]에 되돌린다.**
    #   `_compute_picks`는 지역 사본(research_clean)에만 병합해서 λ는 크롤링 값을
    #   쓰지만 **판정 페이로드는 원본**을 봤다. 같은 재료로 판단해야 한다.
    if statcast_data:
        from collections import Counter

        from app.engine.provenance import distribution, strip_unusable
        from app.research.validate import sanitize_research

        _prov_dist: Counter = Counter()
        _prov_blocked: list[str] = []

        for _jg in judge_games:
            if _jg.get("status") != "scheduled":
                continue
            _r, _ = sanitize_research(_jg.get("research") or {}, sport)
            merge_source_data(_r, _jg, sport, statcast_data)
            # [§9 게이트 ③] 미확인·모순 값은 **판정 입력에서 실제로 뺀다.**
            #   표시만 하고 남겨두면 다음 단계가 그것을 사실로 읽는다.
            _blocked = strip_unusable(_r)
            if _blocked:
                logger.info("[pipeline] 게이트③ 차단 %s — %s",
                            _jg.get("game_id"), ", ".join(_blocked[:6]))
                _prov_blocked.extend(_blocked)
            _d = distribution(_r)
            # [§9 게이트③] **모순은 즉시 보이게 한다.** 두 공식 소스가 처음으로
            #   갈리는 날이 라벨 체계의 실증 시점이다 — 조용히 지나가면 안 된다.
            #   (실측 2026-08-27: 2소스 대조 20건 전부 일치. 불일치는 아직 0건이다)
            if _d.get("모순"):
                logger.warning(
                    "[pipeline] 🔬 출처 모순 %d건 — 소스가 처음으로 갈렸다 "
                    "(경기 %s). 라벨 체계 실증 시점이다.",
                    _d["모순"], _jg.get("game_id"))
            _prov_dist.update(_d)
            _jg["research"] = _r

        if sport == "mlb" and redis is not None:
            from app.collectors.crawler_feed import upsert_snapshot_game

            for _jg in judge_games:
                if _jg.get("status") != "scheduled":
                    continue
                try:
                    await upsert_snapshot_game(redis, "mlb", date, _jg)
                except Exception as exc:
                    logger.warning("[pipeline] MLB 스냅샷 기록 실패 game=%s: %s",
                                   _jg.get("game_id"), exc)

        # [§9 게이트 ③] 라벨 분포를 남긴다.
        #   ⚠️ **단일이 압도적이면 교차검증이 실질적으로 작동하지 않는다는 신호다** —
        #     소스가 사실상 하나뿐이라는 뜻이고, 그 소스가 틀리면 걸러낼 방법이 없다.
        # `대조됨`은 라벨 합계에 들어가면 안 된다 — 라벨과 **직교하는** 지표다.
        _crosschecked = _prov_dist.pop("대조됨", 0)
        _n = sum(_prov_dist.values())
        if _n:
            _cross = _crosschecked
            # MLB·KBO·NPB는 공식 1소스다. 대조됨=0은 교차검증 실패가 아니라 구조다
            # (실측 2026-08-29 MLB 아침 알림: 출처 대조 0/N 🔴).
            _one_axis = sport in ("mlb", "kbo", "npb")
            await record("출처 대조", _cross, _n,
                         cause=None if (_cross or _one_axis) else "missing",
                         detail=(f"2소스 대조 {_crosschecked} · " + " · ".join(
                             f"{k} {_prov_dist.get(k, 0)}"
                             for k in ("확정", "교차", "단일", "미확인", "모순"))),
                         unit="값", expect_full=False, zero_ok=_one_axis,
                         impact="단일 소스 비중이 높으면 그 소스가 틀려도 걸러낼 수 없습니다")

    # 야구 구 리서치 빈칸 보충은 쓰지 않는다. 축구 딥서치는 `_collect_research`.

    from app.engine.scoring import BASEBALL_SPORTS as _BB_SKIP_OLD
    if sport not in _BB_SKIP_OLD:
        await _attach_lineup_intent(pool, judge_games, sport, record)
        await _attach_cell_verdicts(pool, judge_games, sport, record, redis)
        await _attach_card_compare(judge_games, sport, record)

    await progress(3, 4, "Claude 판정")
    # 4) Claude 판정 — JUDGE_MODEL 고정. Grok은 정보 수집 전용(판정 금지).
    #    시작 전 경기만. 크레딧 소진 시 알림 후 목 판정 폴백 (크래시 금지)
    upcoming = [g for g in judge_games if g["status"] == "scheduled"]
    if include_final:
        from app.engine.lineup_record import strip_outcome_for_judge

        upcoming = [strip_outcome_for_judge(g) for g in upcoming]
    _prepare_games_for_judge(upcoming, sport)
    # [§8-21] 여론을 판정에 넘긴다. **확률 계수로 만들지 않는다** — 동조 신호인지
    #   역행 신호(팬심 편향)인지 측정된 적이 없다. 판정이 읽고 스스로 판단한다.
    from app.engine.scoring import BASEBALL_SPORTS as _BB
    judge_payload = {"date": date, "sport": sport, "games": upcoming,
                     "breaking_news": news, "fan_sentiment": sentiment}
    verdict: dict = {"games": []}
    if sport in _BB:
        # 야구: 팀 폼(캐시) + 매치업. 구 Judge는 축구·병행 검증용으로 남긴다.
        bb_redis, bb_close = redis, False
        if bb_redis is None:
            bb_redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
            bb_close = True
        try:
            try:
                await _run_baseball_forms(bb_redis, sport, date, upcoming, record)
            except ApiQuotaError as exc:
                logger.error("[pipeline] 팀 경기력 크레딧 소진(%s) — 슬레이트 중단: %s",
                             sport, exc)
                await notify_api_error(exc)
                await record("팀 폼", 0, len(upcoming), exc=exc,
                             unit="팀",
                             impact="잔액 소진. 이후 폼·매치업 호출을 멈춥니다")
                raise
            if upcoming:
                try:
                    _judged = await _run_baseball_matchups(bb_redis, date, upcoming)
                except (ApiQuotaError, ApiAuthError, ApiRateLimitError) as exc:
                    logger.error("[pipeline] matchup 실패(%s): %s",
                                 type(exc).__name__, exc)
                    await notify_api_error(exc)
                    _judged = 0
                    await record("매치업 판정", 0, len(upcoming), exc=exc,
                                 unit="경기",
                                 impact="추천이 생성되지 않습니다 (보드만 표시)")
                    if isinstance(exc, ApiQuotaError):
                        raise
                except Exception as exc:
                    logger.exception("[pipeline] matchup 예기치 못한 실패: %s", exc)
                    _judged = 0
                    await record("매치업 판정", 0, len(upcoming), exc=exc,
                                 unit="경기",
                                 impact="추천이 생성되지 않습니다 (보드만 표시)")
                if upcoming and not any(st.name == "매치업 판정" for st in stages):
                    _parse_n = sum(1 for g in upcoming
                                   if (g.get("matchup") or {}).get("p_home") is not None)
                    _j_cause = None
                    if _judged != len(upcoming):
                        _j_cause = "parse_fail" if _parse_n == 0 else None
                    await record("매치업 판정", _judged, len(upcoming),
                                 cause=_j_cause,
                                 detail=f"model 필드 {sum(1 for g in upcoming if g.get('model'))}/{len(upcoming)}",
                                 unit="경기",
                                 impact="판정 못 받은 경기는 추천에서 제외됩니다")
        finally:
            if bb_close:
                await bb_redis.aclose()
    elif not upcoming:
        verdict = {"games": []}
    else:
        try:
            verdict = await Judge().judge(judge_payload)
        except (ApiQuotaError, ApiAuthError, ApiRateLimitError) as exc:
            logger.error("[pipeline] judge 실패(%s) — 목 판정으로 폴백: %s",
                         type(exc).__name__, exc)
            await notify_api_error(exc)   # 레이트리밋은 알림 없이 내부 처리
            verdict = Judge._mock_verdict(judge_payload)
            await record("판정", 0, len(upcoming), exc=exc,
                         unit="경기",
                         impact="추천·조합이 생성되지 않습니다 (마켓 보드만 표시)")
        except Exception as exc:
            logger.exception("[pipeline] judge 예기치 못한 실패: %s", exc)
            verdict = {"games": []}
            await record("판정", 0, len(upcoming), exc=exc,
                         unit="경기",
                         impact="추천·조합이 생성되지 않습니다 (마켓 보드만 표시)")
        if upcoming and not any(st.name == "판정" for st in stages):
            _judged = _verdict_hits(verdict, upcoming)
            _j_cause = None if _judged == len(upcoming) else (
                "missing" if _judged == 0 else None)
            await record("판정", _judged, len(upcoming),
                         cause=_j_cause,
                         unit="경기",
                         impact="판정 못 받은 경기는 추천에서 제외됩니다")
        _attach_verdicts(judge_games, verdict)

        # 4b) 2차 검증 — 논쟁 경기만 Grok 반대 근거. 야구 매치업은 덮지 않는다.
        verdict = await _second_opinion(judge_games, verdict, date, sport, news)
        _attach_verdicts(judge_games, verdict)

    # 4c) 축구만 알트 마켓·라인무브. 야구는 승패만.
    if sport not in _BB:
        await _attach_alt_markets(pool, judge_games)
        _enforce_data_rules(judge_games)

    # [§3] 라인 무브먼트 — 확률이 아니라 **신뢰도**만 조정한다.
    #      확률 계산(_compute_picks) 이후에 실행해야 확률에 스며들지 않는다.
    async def _apply_line_moves(games: list[dict]) -> None:
        from app.engine.linemove import attach_line_move

        for g in games:
            if (g.get("sport") or sport) in _BB:
                continue
            if g.get("status") != "scheduled" or not g.get("market_board"):
                continue
            try:
                await attach_line_move(pool, g)
            except Exception as exc:
                logger.warning("[pipeline] 라인 이동 계산 실패 game=%s: %s", g.get("game_id"), exc)


    picks_out, parlays, recommended = _compute_picks(
        settings, judge_games, sport, statcast_data, news=news, sentiment=sentiment)
    # 라인 이동으로 신뢰도가 바뀌면 등급·추천이 달라지므로 픽을 다시 계산한다
    await _apply_line_moves(judge_games)
    picks_out, parlays, recommended = _compute_picks(
        settings, judge_games, sport, statcast_data, news=news, sentiment=sentiment)

    # [B-1] 판정과 서술을 분리 — 판정 결론 + 마켓 보드 + 리서치를 입력으로 별도 서술 단계.
    #       마켓 보드가 만들어진 뒤에 실행해야 서술이 '어느 마켓이 살았는지'를 안다.
    from app.engine.narrator import attach_narratives

    from app.engine.scoring import lambda_persisted

    _scheduled = [g for g in judge_games if g.get("status") == "scheduled"]
    if sport not in _BB and _scheduled:
        _lam_ok = sum(1 for g in _scheduled if lambda_persisted(g))
        await record("λ 산출", _lam_ok, len(_scheduled),
                     cause=None if _lam_ok == len(_scheduled) else "missing",
                     detail=(", ".join(sorted({m for g in _scheduled
                                               for m in (g.get("lambda_missing") or [])}))[:150]),
                     unit="경기",
                     impact="확률이 폴백(경기력 %p 조정)으로 계산됩니다")
    if _scheduled:
        # [§8-10] 라인업 확정률 — 종전 미계측. "잠정/최종" 2단계 표시의 근거인데
        #         소스가 통째로 죽어도 조용히 전부 '잠정'으로 나갔다.
        # [§8-16] KBO·NPB도 잰다. 네이티브 API가 없을 뿐 **딥서치가 소스다** —
        #         계측을 끄면 "라인업을 못 받고 있다"는 사실 자체가 안 보인다.
        _lineup_ok = sum(1 for g in _scheduled
                         if (g.get("lineup_status") or "none") != "none")
        # [라인업 발표 시각] 0건은 **아직 발표 전**일 수도, 수집 실패일 수도 있다.
        #   시각으로만 구분된다 — 종전에는 킥오프 6시간 전 0건도 실패로 분류돼
        #   매일 거짓 실패 알림이 나갔다.
        from app.engine.lineup_timing import classify as _lineup_classify, observe

        _ln_ok, _ln_why = _lineup_classify(_scheduled, _lineup_ok, sport)
        _ln_detail = ", ".join(f"{k}:{v}" for k, v in sorted(_count_by(
            (g.get("lineup_status") or "none") for g in _scheduled).items()))
        if sport in _BB:
            await record("라인업 수집", _lineup_ok, len(_scheduled),
                         cause=None if (_lineup_ok or _ln_ok) else "missing",
                         detail=f"{_ln_detail}{' · ' + _ln_why if _ln_why else ''}",
                         unit="경기", expect_full=False, zero_ok=_ln_ok,
                         impact="전 경기가 '잠정'으로 표기되어 최종 픽 자격을 얻지 못합니다")
        else:
            await record("라인업", _lineup_ok, len(_scheduled),
                         cause=None if (_lineup_ok or _ln_ok) else "missing",
                         detail=f"{_ln_detail}{' · ' + _ln_why if _ln_why else ''}",
                         unit="경기", expect_full=False, zero_ok=_ln_ok,
                         impact="전 경기가 '잠정'으로 표기되어 최종 픽 자격을 얻지 못합니다")
        # 관행값을 실측으로 바꿀 재료 — 경기별 **첫** 수집 시각과 킥오프의 차이
        if redis is not None:
            for _g in _scheduled:
                if (_g.get("lineup_status") or "none") != "none":
                    await observe(redis, sport, _g.get("game_id"), _g.get("starts_at"))
        # [§8-10] 픽 선정 — 0건이 '오늘은 관망'인지 '파이프라인이 깨졌는지' 구분되지
        #         않았다. 실사고(2026-08-26): 추천 6건이 렌더에서 통째로 사라졌는데
        #         카드는 "기준 넘는 픽 없음"이라고만 했다(§8-9).
        # [§8-15] **추천 0건은 실패가 아니다.** 자격 미달(판정 저신뢰·승률 미달)은
        #   정상 동작이며, 그것을 실패로 알리면 "오늘은 걸 만한 게 없다"는 정상 결과가
        #   매번 🔴 알림으로 나간다(실사고 2026-08-26 14:48: KBO 1경기 판정 저신뢰로
        #   전 마켓 제외 → '픽 선정 0/1 실패' 알림 발송).
        #   진짜 실패는 **마켓 보드 자체가 비었을 때**다 — 그건 확률을 못 만든 것이다.
        _board_rows = sum(len(g.get("market_board") or []) for g in _scheduled)
        if sport in _BB:
            from app.engine.pregame_push import in_send_window, minutes_until_start
            _gate_ok = 0
            for _g in _scheduled:
                left = minutes_until_start(_g.get("starts_at"))
                open_w = in_send_window(sport, _g.get("starts_at"))
                has_m = bool((_g.get("matchup") or {}).get("p_home") is not None
                             and _g.get("model"))
                if has_m:
                    _gate_ok += 1
                logger.info(
                    "[pipeline] 창 sport=%s game=%s 잔여=%.0fm 창=%s 판정=%s",
                    sport, _g.get("game_id"), -1 if left is None else left,
                    "진입" if open_w else "이탈", "있음" if has_m else "없음")
            await record("게이트·발송", _gate_ok, len(_scheduled),
                         cause=None if _gate_ok else "missing",
                         detail=f"판정 {_gate_ok} · 추천 {len(recommended)} · 예정 {len(_scheduled)}",
                         unit="경기", expect_full=False, zero_ok=True,
                         impact="판정 없는 경기는 카드를 보내지 않습니다")
        else:
            await record("픽 선정", _board_rows, max(1, _board_rows),
                         cause=None if _board_rows else "missing",
                         detail=f"보드 {_board_rows}행 / 추천 {len(recommended)}건 / "
                                f"예정 {len(_scheduled)}경기",
                         unit="행",
                         impact="마켓 보드가 비어 확률을 만들지 못했습니다")
    if sport not in _BB:
        try:
            _narrated = await attach_narratives(judge_games, sport)
            if _scheduled:
                await record("서술", _narrated, len(_scheduled),
                             cause=None if _narrated else "missing",
                             unit="경기",
                             impact="심층 서술 없이 결정적 렌더로 나갑니다")
        except Exception as exc:   # 서술 실패는 분석을 막지 않는다 (결정적 렌더로 폴백)
            logger.warning("[pipeline] 서술 단계 실패, 결정적 렌더로 진행: %s", exc)
            await record("서술", 0, len(_scheduled) or 1, exc=exc,
                         unit="경기",
                         impact="심층 서술 없이 결정적 렌더로 나갑니다")

    # [6] 병렬 채점 — 경기력 기반 픽과 시장 반영 픽을 **둘 다** 기록해
    #     2~3주 뒤 어느 방식이 실제로 맞히는지 비교한다.
    # 시뮬레이션(종료 경기를 예정으로 돌린 경우)은 사후 예측을 채점 테이블에
    # 넣지 않는다 — 끝난 경기의 픽이 실채점을 오염시킨다.
    if not include_final:
        for p in recommended:
            await pool.execute(
                """
                INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                         p_market, p_ensemble, lineup_status, p_legacy, method,
                                         p_heuristic, p_learned, p_claude, lam_total)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'performance',
                        $11, $12, $13, $14)
                """,
                p["game_id"], p["pick"], p["p"], p["odds"], p["ev"], p["kelly"],
                p.get("p_market_side"), p.get("p_ensemble_side"),
                p.get("lineup_status") or "none", p.get("p_legacy"),
                p.get("p_heuristic"), p.get("p_learned"), p.get("p_claude"),
                p.get("lam_total"),          # [§8-18] 점수 MAE의 근거
            )
        # [§8-38] **전 경기·전 마켓을 기록한다** (method='shadow').
        #   실사고(2026-08-27): `for p in recommended`만 저장해서, 추천이 0건이면
        #   저장도 0건 → 채점 대상 0건 → **판정 성능을 영원히 측정할 수 없었다.**
        #   실제로 predictions 20행 전부 p_claude가 NULL이었고, 그 때문에
        #   "불펜 과소모 문턱을 얼마로 할까" 같은 질문에 답할 방법이 없었다.
        #   → 추천 여부와 무관하게 전부 남긴다. 임계값은 이 기록 위에서 실측으로 정한다.
        #   ⚠️ 같은 슬레이트를 여러 번 돌리면 중복되므로 **먼저 지우고 넣는다.**
        _shadow_gids = [g["game_id"] for g in judge_games
                        if g.get("status") == "scheduled" and g.get("market_board")]
        if _shadow_gids:
            await pool.execute(
                "DELETE FROM predictions WHERE method = 'shadow' AND game_id = ANY($1::int[])",
                _shadow_gids)
            _n_shadow = 0
            for jg in judge_games:
                if jg.get("status") != "scheduled":
                    continue
                for c in jg.get("market_board") or []:
                    if c.get("p") is None:
                        continue          # 확률을 못 낸 행은 채점 대상이 아니다
                    await pool.execute(
                        """
                        INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly,
                                                 p_market, p_ensemble, lineup_status,
                                                 p_legacy, method, p_heuristic, p_learned,
                                                 p_claude, lam_total)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'shadow',
                                $11, $12, $13, $14)
                        """,
                        # odds/ev/kelly는 없을 수 있다(배당 미수집 마켓). 스테이킹은
                        # §8-18에서 제거됐고 배당 의존도 없앴으므로 **NULL 그대로 둔다** —
                        # 0으로 채우면 "배당 1.00"·"EV 0"으로 오독된다.
                        jg["game_id"], c.get("pick") or c.get("desc"), c["p"],
                        c.get("odds"), c.get("ev"), c.get("kelly"),
                        c.get("p_market_side"), c.get("p_ensemble_side"),
                        jg.get("lineup_status") or "none", c.get("p_legacy"),
                        c.get("p_heuristic"), c.get("p_learned"),
                        jg.get("p_claude"), jg.get("lam_total"))
                    _n_shadow += 1
            await record("예측 기록", _n_shadow, max(1, _n_shadow),
                         cause=None if _n_shadow else "missing",
                         detail=f"전 마켓 {_n_shadow}행 ({len(_shadow_gids)}경기)",
                         unit="건",
                         impact="기록이 없으면 임계값을 실측으로 정할 수 없습니다")

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
    stake_krw = None    # [§8-18] 스테이킹 제거

    # [9] 등급제 조합 — 전 마켓 승인 레그 풀에서 구성 (승무패 전용 구조 폐지)
    from app.engine.parlay import _numeric as _odds_num, build_tiered_parlays

    _legs = approved_market_legs(judge_games)
    try:
        combos = build_tiered_parlays(_legs, stake_krw, sport)
    except Exception as exc:
        logger.warning("[pipeline] 조합 구성 실패 — 단식 분석은 유지: %s", exc)
        combos = {"combos": [], "reason": "조합 계산 실패", "all_fail_prob": None}
        _legs = []
    # [§8-10] 조합 구성 — 종전 미계측. 레그 풀이 비면 조합이 조용히 0건이 되는데
    #         단식과 **같은 풀**을 쓴다는 계약이 깨졌는지 여기서 드러난다(§8-9 사고).
    # [§8-15] 승인 레그가 0이면 조합 0이 **정상 결과**다(자격 미달). 실패로 알리지 않는다.
    #   레그가 있는데 조합이 0일 때만 구성 로직 실패다.
    _combo_n = len((combos or {}).get("combos") or [])
    _priced_legs = [l for l in _legs if _odds_num(l.get("odds"))]
    # 배당이 있는 레그가 있는데 조합이 0일 때만 구성 실패다.
    # 야구는 승부 배당을 조회하지 않으므로 승인 레그가 있어도 조합 0이 정상
    # (실측 2026-08-29 MLB: 조합 0건 / 승인 레그 8개 🔴).
    if _priced_legs:
        await record("조합 구성", _combo_n, max(1, _combo_n),
                     cause=None if _combo_n else "missing",
                     detail=f"조합 {_combo_n}건 / 승인 레그 {len(_legs)}개"
                            f" (배당 있는 레그 {len(_priced_legs)}개)",
                     unit="건",
                     impact="승인 레그가 있는데 조합을 만들지 못했습니다")
    else:
        await record("조합 구성", 0, 0, cause=None, zero_ok=True,
                     detail=f"배당 있는 레그 0개 / 승인 레그 {len(_legs)}개",
                     unit="건", expect_full=False,
                     impact="야구는 배당이 없어 조합을 만들지 않습니다")

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
    # [7-2] **분석 1회 = 실패 알림 1건.** 단계마다 보내지 않는다.
    #   프리페치는 `prefetch_report`가 전 단계를 이미 싣고 나가므로(stages_out을
    #   넘겨준다) 여기서 또 보내면 같은 내용이 두 번 간다.
    if stages_out is None:
        from app.alerts import stages_summary

        try:
            await stages_summary(stages, where=f"{sport} 분석")
        except Exception as exc:          # 알림 실패가 분석을 막지 않는다
            logger.warning("[pipeline] 단계 요약 알림 실패: %s", exc)

    return {
        "sport": sport, "date": date,
        "research_meta": research_meta,
        # [7-4] 이 리포트를 만든 데이터의 결함 — 카드 상단 경고의 근거
        "stages": [{"name": st.name, "ok": st.ok, "total": st.total,
                    "cause": st.cause, "impact": st.impact,
                    # 단위·심각도를 함께 실어야 표시 계층이 "N경기"를 잘못 붙이지
                    # 않는다. 팀 수·값 개수를 경기로 표시한 사고가 있었다.
                    "unit": st.unit, "severity": st.severity} for st in stages],
        "mode": {"name": settings.report_mode, **mode,
                 },
        "games": judge_games, "picks": picks_out,
        # [§8-9] 추천 단식을 **목록 그대로** 싣는다.
        #   실사고(2026-08-26): 카드가 `picks`(경기당 대표 1건)에서 recommended
        #   플래그로 다시 걸러냈는데, 자격을 통과한 단식이 대표와 **다른 마켓**이면
        #   플래그가 붙을 자리가 없어 항상 0건이 됐다. 그러면서 같은 픽을 조합
        #   레그로는 추천했다 — 문서에 기록된 그 사고의 재발이다.
        "recommended": recommended,
        "parlays": parlays, "combos": combos,
        "news": news, "sentiment": sentiment,
        "sources": sources, "verdict": verdict,
        "include_final": include_final,
    }


def _to_gid(value):
    """판정이 game_id를 문자열로 돌려줘도 매칭되게 정규화."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _verdict_hits(verdict: dict, upcoming: list[dict]) -> int:
    """판정이 요청 예정 경기 중 몇 건을 돌려줬는가. 중복·초과 ID는 세지 않는다.

    실측: `len(verdict["games"])`를 분자로 쓰면 8/7이 나온다. 분자는 분모를
    넘을 수 없다.
    """
    got = {_to_gid(g.get("game_id")) for g in (verdict.get("games") or [])}
    return sum(1 for g in upcoming if _to_gid(g.get("game_id")) in got)


async def _renarrate(games: list[dict], sport: str) -> None:
    """재판정된 경기의 서술을 다시 쓴다 — 판정이 바뀌었는데 글이 그대로면 안 된다."""
    if not games:
        return
    from app.engine.narrator import attach_narratives

    try:
        await attach_narratives(games, sport)
    except Exception as exc:
        logger.warning("[pipeline] 재서술 실패, 기존 서술 유지: %s", exc)


def _prepare_games_for_judge(games: list[dict], sport: str) -> None:
    """판정 직전에 오늘 9명·결장 계수 크기를 얹는다. 실패해도 그 경기만 건너뛴다."""
    from app.engine.lineup_diff import attach_lineup_view

    for jg in games or []:
        try:
            attach_lineup_view(jg, sport or jg.get("sport"))
        except Exception as exc:
            logger.warning("[pipeline] 오늘9명 부착 실패 game=%s: %s",
                           jg.get("game_id"), exc)


async def _run_baseball_forms(redis, sport: str, date: str, games: list[dict],
                              record=None) -> None:
    """낮 프리페치: 팀당 폼 1회. 저녁 재판정은 이 함수를 부르지 않는다."""
    from app.engine.scoring import BASEBALL_SPORTS
    from app.engine.team_form import analyze_games

    if sport not in BASEBALL_SPORTS or not games:
        return
    r, close = redis, False
    if r is None:
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        close = True
    try:
        forms = await analyze_games(r, sport, date, games)
    finally:
        if close:
            await r.aclose()
    if record is not None:
        n_ok = sum(1 for f in forms.values() if not f.get("unavailable"))
        from collections import Counter
        causes = Counter(
            (f.get("cause") or "parse_fail")
            for f in forms.values() if f.get("unavailable"))
        detail = "성공 %d" % n_ok
        if causes:
            detail += " · unavailable " + ",".join(f"{k}:{v}" for k, v in sorted(causes.items()))
        cause = None
        if forms and n_ok < len(forms):
            cause = causes.most_common(1)[0][0] if causes else "missing"
        await record(
            "팀 폼", n_ok, len(forms),
            cause=cause,
            detail=detail,
            unit="팀",
            impact="평가 불가 팀은 추천에서 제외됩니다")


async def _run_baseball_matchups(redis, date: str, games: list[dict]) -> int:
    """라인업 확정·변경 시 경기당 매치업. 폼 캐시 히트면 재분석하지 않는다."""
    from app.engine.matchup import judge_matchup
    from app.engine.starter_recent import attach_starter_recent

    pool = None
    try:
        from app.db import get_pool

        pool = await get_pool()
    except Exception as exc:
        logger.debug("[pipeline] 선발 등판 조회 생략: %s", exc)
    n = 0
    for jg in games:
        try:
            await attach_starter_recent(jg, pool)
        except Exception as exc:
            logger.warning("[pipeline] 선발 최근 등판 실패 game=%s: %s",
                           jg.get("game_id"), exc)
        if await judge_matchup(jg, redis, date):
            n += 1
    return n


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


async def _attach_card_compare(judge_games: list[dict], sport: str,
                               record=None) -> None:
    """[§9-3단] 카드 두 장 → `jg["compare"]`. 실패해도 카드는 그대로 나간다.

    ⚠️ **여기서 확률을 만들지 않는다.** 3단은 우세한 쪽·확신도·근거 칸만 준다.
       숫자가 필요하면 그것은 다른 단계의 일이다(그리고 지금은 없다).
    """
    from app.engine.comparator import compare_game

    live = [jg for jg in judge_games if jg.get("status") == "scheduled"]
    if not live:
        return
    ok = 0
    for jg in live:
        jg["compare"] = {}
        try:
            v = await compare_game(jg)
        except ApiQuotaError:
            raise
        except Exception as exc:      # 한 경기가 죽어도 슬레이트는 계속 간다
            logger.warning("[3단] %s 대조 실패: %s", jg.get("game_id"), exc)
            continue
        if v:
            jg["compare"] = v
            ok += 1
    if record is not None:
        await record("3단 대조", ok, len(live),
                     cause=None if ok else "missing",
                     detail="카드만 보고 우세 판정 (원본 사실 차단)",
                     unit="경기", expect_full=True,
                     impact="카드는 나가지만 어느 쪽이 유리한지는 표시되지 않습니다")


async def _attach_cell_verdicts(pool, judge_games: list[dict], sport: str,
                                record=None, redis=None) -> None:
    """[§9-2단] 5칸 카드 + 해석봇 ▲▼를 각 경기에 붙인다.

    붙이는 것: `jg["card"]`(사실 층) · `jg["cells"]`(부호·사유) ·
               `jg["cells_status"]`("판정" | "판정 미수행").

    ⚠️ **LLM이 전부 죽어도 사실은 나간다.** 그때 부호를 비우고 상태를
       "판정 미수행"으로 명시한다 — 빈칸을 '='로 채우면 판정한 것처럼 보인다
       (실사고 2026-08-27: 3중 폴백 전멸로 한화 사이드 5칸이 판정 불가였다).
    """
    from app.engine.card import build_card
    from app.engine.interpreter import interpret_slate

    live = [jg for jg in judge_games if jg.get("status") == "scheduled"]
    if not live:
        return
    pairs = [(jg, jg.get("research") or {}) for jg in live]
    for jg, res in pairs:
        jg["card"] = build_card(jg, res)
        jg["home_kr"], jg["away_kr"] = _kr(jg.get("home")), _kr(jg.get("away"))
        jg["cells"] = {"home": {}, "away": {}}
        jg["cells_status"] = "판정 미수행"
    # [§9-6번째 칸] 득점 환경 — 승패 칸과 **별도로** 판정한다.
    #   기준선도 별도다(지표가 다르므로 다섯 칸 기준선을 쓰면 안 된다).
    from app.engine.card_markets import league_total_baseline
    from app.engine.interpreter import interpret_scoring, scoring_baselines

    _sc_base = scoring_baselines([jg["card"].get("scoring") or {} for jg in live])
    # 라인 비교 기준 — **실측 리그 중앙값**. 3경기 표본은 잡음이 커서 못 쓴다.
    try:
        _tot_base = await league_total_baseline(pool, sport)
    except Exception as exc:
        logger.warning("[2단-득점] 리그 총득점 기준 조회 실패: %s", exc)
        _tot_base = {"median": None, "n": 0}
    if _tot_base.get("median") is None:
        logger.info("[2단-득점] 리그 총득점 표본 %d — 언더오버 판정 보류",
                    _tot_base.get("n", 0))
    for jg in live:
        jg["total_baseline"] = _tot_base
    for jg in live:
        jg["scoring"] = {}
        try:
            jg["scoring"] = await interpret_scoring(
                jg["card"].get("scoring") or {}, baselines=_sc_base)
        except ApiQuotaError:
            raise
        except Exception as exc:
            logger.warning("[2단-득점] %s 실패: %s", jg.get("game_id"), exc)
        # 채점 적재 — 기준 총득점을 함께 남긴다. 없으면 채점할 수 없다.
        if pool and (jg.get("scoring") or {}).get("level"):
            from app.engine.cell_grade import record_scoring

            _cell = jg["card"].get("scoring") or {}
            try:
                # ⚠️ 채점 기준은 **라인 비교에 쓴 것과 같아야 한다.** 다른 기준으로
                #   채점하면 "그 판정이 맞았나"가 아니라 다른 질문에 답하게 된다.
                await record_scoring(
                    pool, jg.get("game_id"), jg["scoring"]["level"],
                    jg["scoring"].get("reason") or "",
                    _tot_base.get("median"),
                    _cell.get("facts"), jg["scoring"].get("provider"))
            except Exception as exc:
                logger.warning("[2단-득점] 기록 실패 %s: %s", jg.get("game_id"), exc)
    try:
        out = await interpret_slate(pairs, pool=pool)
    except ApiQuotaError:
        raise
    except Exception as exc:
        logger.warning("[pipeline] 2단 해석 실패 — 사실만 내보낸다: %s", exc)
        out = {}
    judged = 0
    stranded = []
    for jg in live:
        v = out.get(jg.get("game_id")) or {}
        n = len(v.get("home") or {}) + len(v.get("away") or {})
        if n:
            jg["cells"] = v
            jg["cells_status"] = "판정"
            judged += n
        else:
            # [#73] 전 provider 전멸 — 이번 응답은 "판정 미수행"으로 정직하게
            #   나가고, 다음 사이클에 자동 재처리하도록 큐에 넣는다.
            stranded.append(jg)
    if stranded and redis is not None:
        from app.engine.cell_grade import queue_retry

        for jg in stranded:
            await queue_retry(redis, sport, str(jg.get("starts_at_kst") or "")[:10]
                              or "", jg.get("game_id"))
        logger.warning("[2단] %d경기 판정 0건 — 재시도 큐 적재", len(stranded))
    offered = sum(1 for jg in live for side in ("home", "away")
                  for c in jg["card"][side].values() if c.get("facts"))
    if record is not None:
        _sc_ok = sum(1 for jg in live if (jg.get("scoring") or {}).get("level"))
        await record("득점 환경", _sc_ok, len(live),
                     cause=None if _sc_ok else "missing",
                     detail="다득점/보통/저득점 3단 · 언더오버 판정의 근거",
                     unit="경기", expect_full=True,
                     impact="언더오버 판정이 생성되지 않습니다")
        # ⚠️ 단위는 **경기**로 센다. 공용 한계 문구가 "N경기"를 붙이므로
        #   칸 수를 넣으면 "2단 해석 45경기"처럼 없는 경기가 표시된다
        #   (실측 2026-08-27: 5경기 슬레이트에 45경기로 나갔다).
        #   칸 수는 detail에 적는다.
        games_judged = sum(1 for jg in live if jg.get("cells_status") == "판정")
        await record("2단 해석", games_judged, len(live),
                     cause=None if games_judged else "missing",
                     detail=f"제시 {offered}칸 → 판정 {judged}칸 "
                            f"(인용 없음·방향 오독은 폐기)",
                     unit="경기",
                     impact="판정이 0이면 카드에 ▲▼가 없고 사실만 나갑니다")


async def _totals_line_numbers(pool: asyncpg.Pool, game_id: int) -> list[float]:
    """야구 언더오버용 — 스냅샷에서 **라인 숫자만**. 가격·암시확률은 버린다.

    정수 라인은 푸시 문제가 있어 반 점(x.5)만 남긴다 (`_default_total_lines`와 같음).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT line FROM odds_snapshots
         WHERE game_id = $1 AND market = 'totals' AND line IS NOT NULL
        """,
        game_id,
    )
    lines = {float(r["line"]) for r in rows
             if r["line"] is not None and abs(float(r["line"]) % 1 - 0.5) < 1e-9}
    return sorted(lines)


async def _attach_alt_markets(pool: asyncpg.Pool, judge_games: list[dict]) -> None:
    """[7] 핸디캡·토탈 수집 배당 부착 + [A-3] 스냅샷 신선도 라벨.

    ⚠️ **야구는 알트 마켓이 없다** — 마켓은 승패만이다 (DISCIPLINE 1-A-1).
       호출부(build_analysis)에도 `if sport not in _BB:` 가드가 있지만,
       호출부 가드는 하나만 빠져도 뚫린다 — 실측 2026-08-29에 실제로 뚫렸다.
       그래서 함수 진입부에서도 막는다. rejudge_card_stack과 같은 방식이다.

    축구는 북별 최신 스냅샷을 모으므로 (a)다른 북메이커 (b)마지막 프리게임
    스냅샷 폴백이 이미 내장돼 있다. 다만 그 스냅샷이 오래됐으면 현재가가 아니므로
    '(개장 배당)'으로 표기해 사용자가 구분할 수 있게 한다.
    """
    from app.engine.scoring import BASEBALL_SPORTS

    for jg in judge_games:
        if jg.get("status") != "scheduled":
            continue
        sport = jg.get("sport") or ""
        if sport in BASEBALL_SPORTS:
            jg["alt_markets"] = []
            jg["odds_stale"] = False
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
    """추천 게이트.

    야구: 승률 하한(원정 +5%p) + 라인업 확정. 2-소스 없음.
      NPB는 `npb_last3_verified` 전까지 자동 탈락 (보드만).
      폼·매치업 불가(`form_unavailable`)도 탈락.
    축구: 승률 하한 + 2-소스. 라인업 게이트 없음.
    확신도 '하'/패스 권장은 `_approve` 거부권 — 여기 조건이 아니다.
    """
    from app.config import get_settings
    from app.engine.scoring import BASEBALL_SPORTS

    s = settings or get_settings()
    p = pick.get("p")
    need = pick.get("required_prob") or s.min_win_prob
    sport = pick.get("sport")
    if sport in BASEBALL_SPORTS:
        if sport == "npb" and not s.npb_last3_verified:
            return False
        if pick.get("form_unavailable"):
            return False
        from app.collectors.lineups import pick_state as _ps

        state = pick.get("pick_state")
        if state is None:
            state = _ps(pick.get("lineup_status"))[0]
        if state != "final":
            return False
    elif pick.get("two_source") is False:
        return False
    return p is not None and p >= need


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
        from app.engine.scoring import BASEBALL_SPORTS
        from app.collectors.lineups import pick_state as _ps

        if p.get("sport") in BASEBALL_SPORTS:
            if p.get("sport") == "npb" and not s.npb_last3_verified:
                reasons.append("NPB 최근 3경기 미검증")
            if p.get("form_unavailable"):
                reasons.append("팀 경기력 평가 불가")
            st = p.get("pick_state") or _ps(p.get("lineup_status"))[0]
            if st != "final":
                reasons.append("라인업 확정 전 (잠정)")
        elif p.get("two_source") is False:
            reasons.append("2-소스 미달")

        out.append({**p, "miss_reason": " · ".join(reasons) or "미승인"})
    return out


def approved_market_legs(games: list[dict]) -> list[dict]:
    """[9] 조합 후보 풀 = 전 마켓 승인 픽 (판정 제외·저신뢰 경기는 이미 미승인)."""
    legs = []
    for jg in games:
        if jg.get("status") != "scheduled":
            continue
        for c in jg.get("market_board") or []:
            wrapped = {**c, "sport": jg.get("sport"),
                       "lineup_status": jg.get("lineup_status") or "none",
                       "pick_state": _pick_state(jg)[0],
                       "form_unavailable": bool(jg.get("form_unavailable"))}
            if c.get("approved") and qualifies(wrapped):
                legs.append({
                    "game_id": jg["game_id"], "desc": c["desc"], "market": c["market"],
                    "odds": c["odds"], "p": c["p"],
                    "confidence": jg.get("judge_confidence", "medium"),
                    "league": jg.get("league"), "starts_at_kst": jg["starts_at_kst"],
                })
    return legs


def qualified_singles(games: list[dict], settings=None,
                      per_game: int = 1) -> list[dict]:
    """[단식 후보] 조합과 **같은 풀**(마켓 보드 전체)에서 자격을 통과한 픽.

    실사고(2026-08-26): 단식은 `picks`(경기당 대표 1건)에서만 뽑았다.
    대표는 EV 최고 마켓이 자동 선정되는데, 그것이 자격 미달이면 같은 경기의
    **자격을 통과하는 다른 마켓이 통째로 심사에서 빠졌다.**
    실제로 "워싱턴 승 62.1% @1.70 (3축 지지)"이 자격을 넉넉히 통과하는데도
    같은 경기 "언더 8.5"가 대표로 뽑히는 바람에 단식 0건이 됐고,
    사용자에게는 "단식 없음 — 관망"이라 하면서 **같은 베팅을 조합 레그로 추천**했다.

    per_game: 한 경기에서 최대 몇 개까지 — 기본 1.
      같은 경기의 두 마켓은 상관돼 있어(승패와 런라인) 둘 다 추천하면
      같은 경기를 두 번 세는 셈이 된다. 승률 높은 쪽 하나만 남긴다.
    """
    from app.config import get_settings

    settings = settings or get_settings()
    by_game: dict = {}
    for jg in games:
        if jg.get("status") != "scheduled":
            continue
        for c in jg.get("market_board") or []:
            wrapped = {**c, "sport": jg.get("sport"),
                       "lineup_status": jg.get("lineup_status") or "none",
                       "pick_state": _pick_state(jg)[0],
                       "form_unavailable": bool(jg.get("form_unavailable"))}
            if not (c.get("approved") and qualifies(wrapped, settings)):
                continue
            # 다운스트림(DB 적재·속보 비교·렌더)이 쓰는 필드를 전부 채운다.
            # 대표 픽 엔트리와 같은 계약이어야 한다 — 빠지면 KeyError로 죽는다.
            rep = next((x for x in (jg.get("pick_summary"),) if x), {}) or {}
            entry = {
                "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
                "sport": jg.get("sport"),
                "pick_state": wrapped["pick_state"],
                "pick": f"{c['market']}:{c.get('side')}",
                "desc": c["desc"], "market": c["market"], "side": c.get("side"),
                "line": c.get("line"), "odds": c["odds"], "p": c["p"],
                "ev": c.get("ev") if c.get("ev") is not None else 0.0,
                "kelly": 0.0,
                "lam_total": ((jg.get("lam") or {}).get("home", 0)
                              + (jg.get("lam") or {}).get("away", 0)) or None,
                "axes": c.get("axes_kr"), "grade": c.get("grade"),
                "confidence": jg.get("judge_confidence", "medium"),
                "judge_excluded": None,
                "league": jg.get("league"), "starts_at_kst": jg["starts_at_kst"],
                "lineup_status": jg.get("lineup_status") or "none",
                "p_legacy": (jg.get("p_legacy") or {}).get(c.get("side")),
                "p_market_side": None,
                "p_ensemble_side": None,
                # 세 방식 확률은 승패 기준이므로 h2h일 때만 기록한다
                "p_heuristic": ((jg.get("p_heuristic") or {}).get(c.get("side"))
                                if c["market"] == "h2h" else None),
                "p_learned": ((jg.get("p_learned") or {}).get(c.get("side"))
                              if c["market"] == "h2h" else None),
                "p_claude": ((jg.get("p_claude_side") or {}).get(c.get("side"))
                             if c["market"] == "h2h" else None),
                "approved": True,
                "reject_reason": None,
                "stake_krw": None,
                "_rep": rep,
            }
            by_game.setdefault(jg["game_id"], []).append(entry)
    out: list[dict] = []
    for entries in by_game.values():
        entries.sort(key=lambda x: -x["p"])
        out += entries[:per_game]
    out.sort(key=lambda x: -x["p"])
    return out


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

    if get_settings().is_disabled("grok"):
        return verdict
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
    _prepare_games_for_judge(disputed, sport)
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
    news: str = "", sentiment: str = "",
) -> tuple[list[dict], list[dict], list[dict]]:
    """jg(판정 부착 완료) → (전체 픽, 파레이, 추천 픽). DB 접근 없음 — 재판정 시 재사용.

    [7] 경기별 전 마켓 후보 평가 → jg["market_board"].
    [1][2][3] 승인 규칙(2-소스·괴리 검증·저분산 우선)은 engine.markets._approve.
    [5] p_final = 0.5*p_model + 0.5*p_claude (시장 가중치 0).
    경기 대표 픽 = 승인 후보 중 승률 최대 (없으면 h2h, 없으면 보드 최고 승률).
    """
    from app.engine.markets import build_board

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = None    # [§8-18] 스테이킹 제거

    def blend(p_model_s: float | None, p_market_s: float, p_claude_s: float) -> float:
        """[1-1] 경기력 앙상블 — **시장 확률은 쓰지 않는다**.

        p_final = 0.5*p_model + 0.5*p_claude. 배당은 "이기면 얼마 받는가"에만 쓴다.
        모델이 무효거나 야구 승패 λ가 동전 던지기면 Claude 단독.
        토탈은 이 함수를 거치지 않는다. (p_market_s는 병렬 채점·표시용으로만 받는다)
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
        from app.engine.scoring import BASEBALL_SPORTS
        market = jg.get("market_probs") or {}
        if sport in BASEBALL_SPORTS:
            ph = jg.get("p_claude")
            jg["distribution"] = None
            jg["lam"] = None
            jg["lambda_trace"] = []
            jg["lambda_missing"] = []
            jg["p_heuristic"] = None
            jg["p_learned"] = None
            jg["h2h_lambda_unused"] = True
            # 야구에 **구 모델 축은 없다.** λ를 안 쓰므로 p_model·p_model3도 없고,
            # model_valid는 "λ/Elo 모델이 이 경기를 평가했는가"를 뜻한다.
            # True로 두면 markets._axis_model이 없는 jg["p_model"]을 인덱싱해
            # KeyError로 야구 슬레이트가 통째로 죽는다 (실측 2026-08-30).
            # 판정 유무는 judge_missing·form_unavailable이 이미 들고 있다.
            jg["model_valid"] = False
            jg["prob_adjust"] = None
            p_final: dict[str, float] = {}
            p_ens: dict[str, float] = {}
            if ph is not None:
                pa = round(max(0.0, min(1.0, 1.0 - float(ph))), 4)
                p_final = {jg["home"]: round(float(ph), 4), jg["away"]: pa}
                p_ens = dict(p_final)
            jg["p_final"] = p_final
            jg["p_legacy"] = {}
            if ph is not None:
                jg["p_claude_side"] = {
                    jg["home"]: round(float(ph), 4),
                    jg["away"]: round(max(0.0, min(1.0, 1.0 - float(ph))), 4),
                }
            cands = build_board(jg, sport, p_final)
            jg["market_board"] = cands
            scored = [c for c in cands if c.get("p") is not None]
            if not scored:
                continue
            approved = [c for c in scored if c.get("approved")]
            h2h = [c for c in scored if c["market"] == "h2h"]
            pool_rep = approved or h2h or scored
            rep = max(pool_rep, key=lambda c: c["p"])
            pick = f"{rep['market']}:{rep['side']}" + (
                f":{rep['line']:g}" if rep.get("line") is not None else "")
            judge_excluded = None
            if jg.get("judge_pass"):
                judge_excluded = f"판정: 패스 권장 — {(jg.get('verdict') or '')[:120]}"
            elif jg.get("judge_confidence") == "low":
                judge_excluded = f"판정: 저신뢰 — {(jg.get('verdict') or '')[:120]}"
            entry = {
                "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
                "sport": sport,
                "league": jg.get("league") or ("MLB" if sport == "mlb" else "?"),
                "starts_at_kst": jg["starts_at_kst"], "pick": pick,
                "market": rep["market"], "side": rep["side"], "line": rep.get("line"),
                "desc": rep["desc"], "p": rep["p"],
                "p_claude": ((jg.get("p_claude_side") or {}).get(rep["side"])
                             if rep["market"] == "h2h" else None),
                "model_valid": jg.get("model_valid", False),
                "confidence": jg.get("judge_confidence", "medium"),
                "odds": rep["odds"], "ev": rep["ev"], "kelly": 0.0,
                "lam_total": None,
                "stake_krw": stake_krw,
                "verdict": jg.get("verdict", ""), "excluded_picks": jg.get("excluded_picks", []),
                "flags": rep.get("flags", []), "judge_excluded": judge_excluded,
                "approved": bool(rep.get("approved")),
                "reject_reason": rep.get("reject_reason"),
                "axes": rep.get("axes_kr"),
                "grade": rep.get("grade"),
                "p_heuristic": None,
                "p_learned": None,
                "two_source": True,
                "required_prob": rep.get("required_prob"),
                "edge": None,
                "lineup_status": jg.get("lineup_status") or "none",
                "pick_state": _pick_state(jg)[0], "pick_state_label": _pick_state(jg)[1],
                "form_unavailable": bool(jg.get("form_unavailable")),
                "p_legacy": None,
                "p_market_side": None,
                "p_ensemble_side": p_ens.get(rep["side"]),
            }
            picks_out.append(entry)
            jg["pick_summary"] = {
                "side": rep["side"], "desc": rep["desc"], "market": rep["market"],
                "odds": rep["odds"], "p_final": rep["p"], "ev": rep["ev"],
                "flags": rep.get("flags", []), "approved": bool(rep.get("approved")),
                "reject_reason": rep.get("reject_reason"), "axes": rep.get("axes_kr"),
            }
            continue
        # [A-2] h2h 배당이 없다고 경기 전체를 죽이지 않는다 — 없는 마켓만 빠진다.
        #        배당은 행의 가격이다. 앙상블·경기력 조정의 전제가 아니다.
        #        야구 승부는 배당을 보지 않는다. 언더오버는 라인 숫자만.
        market = jg.get("market_probs") or {}

        # 사이드별 확률: 축구는 무승부 질량 때문에 1-p_home ≠ p_away — 시장 3-way 기준
        p_draw_m = market.get("Draw", 0.0)
        p_final: dict[str, float] = {}
        p_ens: dict[str, float] = {}
        p_claude_home = jg.get("p_claude") or 0.5
        p_claude_away = max(0.0, min(1.0, 1.0 - p_claude_home - p_draw_m))
        # [§6-4] jg["p_claude"]는 **홈 기준 스칼라**다. 병렬 채점이 원정 픽에
        #        홈 확률을 기록하면 세 방식 비교가 통째로 어긋나므로
        #        사이드별로 풀어 둔다 (p_heuristic·p_learned와 기준을 맞춘다).
        jg["p_claude_side"] = {jg["home"]: round(p_claude_home, 4),
                               jg["away"]: round(p_claude_away, 4)}
        p3 = jg.get("p_model3")
        league_lam = "MLB" if sport == "mlb" else jg.get("league")
        sides = () if jg["judge_missing"] else (
            (jg["home"], (p3[0] if p3 else (jg["p_model"] if jg.get("model_valid") else None)),
             market.get(jg["home"], 0.5), p_claude_home),
            (jg["away"], (p3[2] if p3 else ((1 - jg["p_model"]) if jg.get("model_valid") and sport == "mlb" else None)),
             market.get(jg["away"], 0.5), p_claude_away),
        )
        # [2][3] 기대득점(λ) 분포 — 학술 방법론(포아송/스켈람)이 1순위 확률 소스다.
        #        분포가 서면 전 마켓 확률이 같은 분포에서 나오고, 경기력 조정(%p 가산)은
        #        중복 계산이 되므로 쓰지 않는다. 핵심 지표가 없을 때만 조정 방식으로 폴백.
        from app.engine.performance import WinProbAdjuster
        from app.engine.scoring import (
            BASEBALL_SPORTS, game_distribution, h2h_lambda_has_signal,
        )
        from app.research.validate import sanitize_research

        research_clean, _ = sanitize_research(jg.get("research") or {}, sport)
        # [2-1] Statcast 지표를 얹는다 — 리서치 산문보다 정확한 1차 소스
        if sport == "mlb" and statcast_data:
            from app.collectors.statcast import enrich_mlb_research

            filled = enrich_mlb_research(research_clean, jg, statcast_data)
            # 카드·today_nine은 jg["research"]를 읽는다. sanitize 복사본만
            # 채우면 λ는 살아도 칸은 비었다 (실측 2026-08-29 아침 카드).
            enrich_mlb_research(jg.setdefault("research", {}), jg, statcast_data)
            if filled:
                jg["statcast_filled"] = filled
        # [§8-14] KBO 공식 기록 — 딥서치 산문보다 정식 기록이 우선이다
        elif sport == "kbo" and statcast_data:
            from app.collectors.kbo_stats import merge_into_research as merge_kbo
            from app.collectors.naver_kbo import merge_into_research as merge_naver

            from app.collectors.kbo_park import merge_into_research as merge_park

            filled = merge_kbo(research_clean, jg,
                               statcast_data.get("kbo_teams") or {},
                               statcast_data.get("kbo_pitchers") or {})
            filled += merge_park(research_clean, jg, statcast_data.get("parks") or {})
            from app.collectors.weather import merge_into_research as merge_wx

            if merge_wx(research_clean, jg, statcast_data.get("weather") or {}):
                filled.append("weather")
            # [§8-19] 네이버 크롤링이 **가장 마지막**에 얹힌다 — 선발 시즌 성적·구종·
            #   최근 폼은 구단 발표 기반이라 공식 집계보다도 그 경기에 가깝다.
            nv = (statcast_data.get("naver") or {}).get(f"{jg['away']}@{jg['home']}")
            if nv:
                filled += merge_naver(research_clean, jg, nv)
            if filled:
                jg["kbo_filled"] = filled
        elif sport == "npb" and statcast_data:
            from app.collectors.npb_stats import merge_into_research as merge_npb
            from app.collectors.yahoo_npb import merge_into_research as merge_yahoo

            yv = (statcast_data.get("yahoo") or {}).get(f"{jg['away']}@{jg['home']}")
            f2 = merge_yahoo(research_clean, jg, yv) if yv else []
            f2 = list(f2) + merge_npb(research_clean, jg,
                                      statcast_data.get("npb_teams") or {})
            from app.collectors.weather import merge_into_research as merge_wx

            if merge_wx(research_clean, jg, statcast_data.get("weather") or {}):
                f2 = list(f2) + ["weather"]
            if f2:
                jg["npb_filled"] = f2
        # [§2-3] Understat xG — 축구 λ의 1차 입력 (산문 파싱 대체)
        elif sport == "soccer" and statcast_data:
            from app.collectors.soccer_stats import merge_xg_into_research

            windows = (statcast_data[0] or {}).get(jg.get("league")) or {}
            filled = merge_xg_into_research(research_clean, jg, windows)
            if filled:
                jg["xg_filled"] = filled
        from app.collectors.lineups import STATUS_CONFIRMED, STATUS_PREDICTED

        # [§8-23] Go 크롤러 스냅샷 — 10분 주기라 **가장 최신**이다.
        #   경기 직전 선발 교체는 시장이 늦게 반영하는 몇 안 되는 신호다.
        #   ⚠️ 축구는 statcast_data가 **튜플**이다(xG 캐시). dict가 아니면 건너뛴다.
        _crawl_snap = (statcast_data.get("crawler") or {}
                       if isinstance(statcast_data, dict) else {})
        if _crawl_snap:
            from app.collectors.crawler_feed import merge_into_research as merge_crawl

            _cf = merge_crawl(research_clean, jg, _crawl_snap)
            if _cf:
                jg["crawler_filled"] = _cf

        # [§8-22] 소스 교차검증 — 크롤링·딥서치·X가 같은 선발을 말하는지 대조한다.
        #   실사고(2026-08-26 NC@LG): 딥서치·네이버는 "구창모", X 구단 공식은 "박준현".
        #   한쪽을 조용히 고르면 왜 틀렸는지 영원히 모른다 — 갈리면 표시하고
        #   **최종 픽 자격을 박탈**한다(라인업 2단계 규율).
        if sport in ("kbo", "npb"):
            from app.research.crosscheck_sources import apply as crosscheck_apply
            from app.research.crosscheck_sources import extract_starters_from_text

            _srcs: dict[str, dict] = {}
            _crawl = (statcast_data or {}).get("naver") or (statcast_data or {}).get("yahoo") or {}
            _cv = _crawl.get(f"{jg['away']}@{jg['home']}") or {}
            if _cv:
                _srcs["portal"] = {
                    "home": (_cv.get("home_pitcher") or {}).get("name"),
                    "away": (_cv.get("away_pitcher") or {}).get("name")}
            if _crawl_snap:
                _cg = _crawl_snap.get(f"{jg['away']}@{jg['home']}") or {}
                if _cg.get("home_pitcher") or _cg.get("away_pitcher"):
                    # 10분 주기 크롤러가 포털 스냅샷보다 최신이다
                    _srcs["official_x"] = {"home": _cg.get("home_pitcher"),
                                           "away": _cg.get("away_pitcher")}
            _rp = research_clean or {}
            if _rp.get("home_pitcher") or _rp.get("away_pitcher"):
                _srcs["deep_search"] = {
                    "home": (_rp.get("home_pitcher") or {}).get("name"),
                    "away": (_rp.get("away_pitcher") or {}).get("name")}
            # X·속보 텍스트에서 선발 언급을 뽑는다 (구단 공식 계정이 가장 빠르다)
            _x = extract_starters_from_text(f"{news}\n{sentiment}",
                                            (jg["home"], jg["away"]))
            if _x.get("any"):
                jg["x_starter_mention"] = _x["any"]
            if len(_srcs) >= 2:
                jg["crosscheck"] = crosscheck_apply(research_clean, jg, _srcs)

        # [§8-16] 라인업 — 네이티브 API(statsapi)는 MLB 전용이다. KBO·NPB는
        #   **딥서치가 소스다**(Perplexity 스키마 lineup + Grok 속보 브리핑).
        #   "다른 곳을 찾으면 된다" — 소스가 없는 게 아니라 경로가 없었을 뿐이다.
        #   ⚠️ projected를 confirmed로 승격하지 않는다(라인업 2단계 규율).
        if (jg.get("lineup_status") or "none") == "none":
            _lu = (research_clean or {}).get("lineup") or {}
            if _lu.get("status") == "confirmed":
                jg["lineup_status"] = STATUS_CONFIRMED
                jg["lineup_source"] = _lu.get("source") or "딥서치"
            elif _lu.get("status") == "projected":
                # ⚠️ 기존 상수는 "predicted"다. "projected"를 쓰면 pick_state가
                #    모르는 값이라 조용히 '잠정'으로만 떨어진다 — 계약을 맞춘다.
                jg["lineup_status"] = STATUS_PREDICTED
                jg["lineup_source"] = _lu.get("source") or "딥서치"
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
            jg["model_valid"] = True
            # [§9] λ 값 자체를 스칼라로 남긴다 — LambdaResult는 JSON 캐시에서
            #      default=str로 뭉개져 검증 때 읽을 수 없다.
            jg["lam"] = {"home": dist["lam"].home, "away": dist["lam"].away}
            jg["lambda_trace"] = dist["lam"].trace
            jg["lambda_missing"] = dist["lam"].missing
            jg["prob_cap_note"] = dist["capped"]
            jg["prob_raw_home"] = dist["raw_home"]
        else:
            # 이전 계산의 trace를 남기고 missing만 붙이면 카드가 모순된다
            # (실측 2026-08-29: xwOBA 트레이스 + '핵심 지표 전무').
            jg["model_valid"] = False
            jg["lam"] = None
            jg["lambda_trace"] = []
            jg["lambda_missing"] = ["핵심 지표(타선·선발) 전무"]
            jg["prob_cap_note"] = None
            jg["prob_raw_home"] = None
        adjuster = WinProbAdjuster(settings)
        p_legacy: dict[str, float] = {}
        home_adj = None
        # 야구 승패: λ가 동전 던지기면 결합하지 않는다. 축구·토탈은 기존.
        h2h_use_lam = True
        if dist is not None and sport in BASEBALL_SPORTS:
            h2h_use_lam = h2h_lambda_has_signal(dist["probs"]["h2h"]["home"], settings)
            jg["h2h_lambda_unused"] = not h2h_use_lam
        for side, p_model_s, p_market_s, p_claude_s in sides:
            if dist is not None:
                # 모델 확률 = 기대득점 분포. 변별이 있을 때만 Claude와 반반.
                p_lam = (dist["probs"]["h2h"]["home"] if side == jg["home"]
                         else dist["probs"]["h2h"]["away"])
                p_model_s = p_lam if h2h_use_lam else None
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
        jg["p_final"] = p_final               # 홈/원정 키. 시뮬레이션 채점이 쓴다

        # [7][8] 전 마켓 후보 생성·승인 → 마켓 보드
        # [2] 전 마켓 보드 — 판정 유무·배당 유무와 무관하게 항상 전 행을 만든다
        cands = build_board(jg, sport, p_final)
        jg["market_board"] = cands
        # 대표 픽은 승률로 고른다. EV는 배당이 있어야 나와서, 야구 승부를
        # "배당 없음 → 픽 없음"으로 죽였다.
        scored = [c for c in cands if c.get("p") is not None]
        if not scored:
            continue                       # 대표 픽은 못 뽑지만 보드는 이미 채워졌다
        approved = [c for c in scored if c.get("approved")]
        h2h = [c for c in scored if c["market"] == "h2h"]
        pool_rep = approved or h2h or scored
        rep = max(pool_rep, key=lambda c: c["p"])

        pick = f"{rep['market']}:{rep['side']}" + (
            f":{rep['line']:g}" if rep.get("line") is not None else "")
        pick_kelly = 0.0        # [§8-18] 켈리 제거
        # 판정 제외: Claude가 패스 권장/저신뢰로 본 경기는 추천 목록에서 뺀다
        judge_excluded = None
        if jg.get("judge_pass"):
            judge_excluded = f"판정: 패스 권장 — {(jg.get('verdict') or '')[:120]}"
        elif jg.get("judge_confidence") == "low":
            judge_excluded = f"판정: 저신뢰 — {(jg.get('verdict') or '')[:120]}"

        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "sport": sport,
            "league": jg.get("league") or ("MLB" if sport == "mlb" else "?"),
            "starts_at_kst": jg["starts_at_kst"], "pick": pick,
            "market": rep["market"], "side": rep["side"], "line": rep.get("line"),
            "desc": rep["desc"], "p": rep["p"],
            "p_claude": ((jg.get("p_claude_side") or {}).get(rep["side"])
                         if rep["market"] == "h2h" else None),
            "model_valid": jg.get("model_valid", False),
            "confidence": jg.get("judge_confidence", "medium"),
            "odds": rep["odds"], "ev": rep["ev"], "kelly": round(pick_kelly, 4),
            "lam_total": ((jg.get("lam") or {}).get("home", 0)
                          + (jg.get("lam") or {}).get("away", 0)) or None,
            "stake_krw": stake_krw,
            "verdict": jg.get("verdict", ""), "excluded_picks": jg.get("excluded_picks", []),
            "flags": rep.get("flags", []), "judge_excluded": judge_excluded,
            "approved": bool(rep.get("approved")),
            "reject_reason": rep.get("reject_reason"),
            "axes": rep.get("axes_kr"),
            "grade": rep.get("grade"),
            # 추천 자격 판정에 쓰이는 필드 — 빠지면 qualifies()가 무력화된다
            # [§6-4] 세 방식 확률을 함께 실어 실전 결과로 비교한다
            # 세 방식 확률은 **승패(h2h) 기준**이다. 토탈·핸디 픽에 h2h 확률을
            # 기록하면 그 픽의 결과로 채점돼 원장이 오염된다 → h2h일 때만 기록.
            "p_heuristic": ((jg.get("p_heuristic") or {}).get(rep["side"])
                            if rep["market"] == "h2h" else None),
            "p_learned": ((jg.get("p_learned") or {}).get(rep["side"])
                          if rep["market"] == "h2h" else None),
            "two_source": rep.get("two_source"),
            "required_prob": rep.get("required_prob"),
            "edge": rep.get("edge"),
            "lineup_status": jg.get("lineup_status") or "none",
            "pick_state": _pick_state(jg)[0], "pick_state_label": _pick_state(jg)[1],
            "form_unavailable": bool(jg.get("form_unavailable")),
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
                    "[pipeline] suspicious pick flagged — %s @ %s | %s odds=%s: %s",
                    jg["away"], jg["home"], c["desc"], c.get("odds"),
                    "; ".join(c["flags"]),
                )

    picks_out.sort(key=lambda x: x.get("p") or 0, reverse=True)
    # 단식 추천 = **마켓 보드 전체**에서 자격 통과 (조합과 같은 풀).
    # 경기당 대표 픽 1건에서만 뽑으면 자격 있는 다른 마켓이 심사에서 빠진다.
    board = qualified_singles(judge_games, settings)
    excluded_games = {p["game_id"] for p in picks_out if p.get("judge_excluded")}
    clean = [b for b in board if b["game_id"] not in excluded_games]
    recommended = clean[: mode["max_picks"]]
    # [§8-18] 스테이킹 제거 — 봇은 얼마를 걸라고 말하지 않는다.
    for r in recommended:
        r["stake_krw"] = stake_krw
    rec_keys = {(r["game_id"], r["desc"]) for r in recommended}
    for p in picks_out:
        p["recommended"] = (p["game_id"], p.get("desc")) in rec_keys
    legs = [{"game_id": p["game_id"], "pick": p["pick"], "p": p["p"],
             "odds": p["odds"], "ev": p.get("ev") or 0.0} for p in clean]
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


def matchup(jg: dict) -> str:
    """[§8-29] 경기 표기 — **원정 @ 홈.**

    실사고(2026-08-27): 카드가 `홈 vs 원정` 순서로 찍혀 읽는 사람이 정반대로 이해했다.
    한국·일본·미국 스포츠 매체는 모두 **원정을 먼저** 쓴다("NC vs LG" = LG 홈).
    데이터는 정확했는데(KBO 공식·크롤러 모두 KIA 홈) **표기만 뒤집혀 있었다** —
    조용한 오독이라 아무도 알아채지 못했다.

    → 관례에 기대지 않고 `@`로 못 박는다. `A @ B`는 B가 홈이다.
    """
    return f"{_kr(jg.get('away') or '?')} @ {_kr(jg.get('home') or '?')}"


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

# [§8-13] 카드 길이 상한. 종전 20줄/3500자는 "추천 2건"만 싣던 시절 값이다.
#   전 경기·전 마켓 보드는 경기당 2~3줄이라 15경기면 40줄을 넘는다.
#   텔레그램 4096자 분할은 bot.main.split_message가 담당한다.
# [§8-27] 배당 없이도 마켓 행을 만들면서 경기당 줄이 늘었다 — 상한을 올린다.
#   텔레그램 4096자 분할은 bot.main.split_message가 담당한다.
CARD_MAX_LINES = 140
CARD_MAX_CHARS = 20000
DETAIL_MAX_LINES = 200

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
            return "🟡", "보수 — 반박 검증에서 반전 요인이 나와 한 단계 낮췄습니다", max(1, stars - 1)
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
        return "🔴", "패스 — 전 마켓 확률을 산출하지 못했습니다", 1
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



# ---------------------------------------------------------------- [§8-13] 경기별 별점 보드

# 마켓 표기 축약 — 한 줄에 여러 마켓을 담기 위한 것. 종목 용어는 그대로 지킨다.
_MARKET_ORDER = {"h2h": 0, "dc": 1, "spreads": 2, "totals": 3, "f5": 4, "btts": 5}


def _short_desc(c: dict, jg: dict) -> str:
    """보드 한 줄에 들어갈 짧은 마켓 표기. 원문 desc가 길면 줄인다."""
    d = c.get("desc") or "?"
    return d.replace("(5이닝) ", "").replace(" 더블찬스", "DC").strip()


def board_stars(c: dict, jg: dict, s) -> tuple[int, str]:
    """[§8-13] 보드용 별점 — **가중 모델이 아니라 충족한 조건의 개수**다.

    별 하나 = 사용자가 직접 확인할 수 있는 조건 하나. 임의 가중치를 발명하지 않는다
    (측정된 근거가 없는 가중치는 DISCIPLINE 5-1 위반이다).

      ★ 승률 ≥ min_win_prob (58%)
      ★ 승률 ≥ signal_green_prob (62%)
      ★ 근거 축 2개 이상 (2-소스 룰)
      ★ 판정 신뢰도 high
    [§8-18] 배당 조건은 뺐다 — 시장 기준이다.

    ⚠ 는 별을 깎지 않고 **따로 표시**한다 — 종전 등급 방식은 시장 괴리 하나로
    전 행이 🔴(★1)이 되어 보드에 변별력이 사라졌다(실측: 15경기 중 12경기가 전부 ★1).
    """
    p = c.get("p")
    if p is None:
        return 0, ""
    # 하한: 승률 50% 미만이면 별을 주지 않는다.
    #   배당·근거 축만으로 별이 붙으면 "승률 39.6%인데 ★★"처럼 오해를 부른다
    #   (실측 렌더에서 실제로 나왔다). 지는 쪽이 더 많은 마켓은 조건 충족이 아니다.
    #   ⚠️ EV로 자르지 않는다 — EV 기준은 폐기됐다(승률·배당 하한만 본다).
    if p < 0.50:
        return 0, ""
    n = 0
    if p >= s.min_win_prob:
        n += 1
    if p >= s.signal_green_prob:
        n += 1
    from app.engine.markets import axes_count

    if axes_count(c.get("axes") or {}) >= 2:
        n += 1
    if jg.get("judge_confidence") == "high":
        n += 1
    warn = ""
    if jg.get("judge_confidence") == "low" or jg.get("judge_pass"):
        warn = "⚠"          # 판정 저신뢰·패스 권장
    return n, warn


def star_rows(jg: dict) -> list[dict]:
    """[§8-13] 한 경기의 전 마켓을 **별점 순**으로. 배당 미수집 행도 버리지 않는다.

    봇이 2건을 고르는 대신 **전 마켓을 나열하고 판단은 사용자가 한다**는 원칙의 구현.
    """
    from app.config import get_settings

    s = get_settings()
    rows = []
    for c in jg.get("market_board") or []:
        stars, warn = board_stars(c, jg, s)
        rows.append({
            "stars": stars, "warn": warn,
            "desc": _short_desc(c, jg),
            "p": c.get("p"), "odds": c.get("odds"),
            "grade": c.get("grade"), "axes": c.get("axes_kr"),
            "reject": c.get("reject_reason"), "market": c.get("market"),
            "order": _MARKET_ORDER.get(c.get("market"), 9),
        })
    rows.sort(key=lambda r: (-r["stars"], -(r["p"] or 0), r["order"]))
    return rows


def render_star_board(games: list[dict]) -> tuple[list[str], list[str]]:
    """[§8-13] 전 경기 · 전 마켓 별점 보드. 반환 (기본층 줄, 심층 줄).

    기본층: 경기당 2줄(헤더 + 마켓 나열). 심층: 마켓 행마다 근거 1줄 + λ 산출 과정.
    """
    lines: list[str] = []
    detail: list[str] = []
    scheduled = [g for g in games if g.get("status") == "scheduled"]
    if not scheduled:
        return lines, detail

    lines.append("")
    lines.append("📋 경기별 마켓 — 별점 순 (판단은 직접 하십시오)")
    for i, g in enumerate(scheduled, 1):
        rows = star_rows(g)
        if not rows:
            continue
        kick = (g.get("starts_at_kst") or "")[-5:]
        head = f"{i}. {matchup(g)}" + (f" [{kick}]" if kick else "")
        lines.append(head)
        priced = [r for r in rows if r["p"] is not None]
        unpriced = [r for r in rows if r["p"] is None]
        if priced:
            cells = [f"{('★' * r['stars']) if r['stars'] else '─'}{r['warn']} "
                     f"{r['desc']} {r['p']:.0%}" for r in priced]
            # 한 줄에 3개씩 — 6개를 한 줄에 넣으면 180자가 되어 모바일에서 깨진다
            for k in range(0, len(cells), 3):
                lines.append("   " + " │ ".join(cells[k:k + 3]))
        if unpriced:
            lines.append("   ⚪ 확률 미산출: " + ", ".join(r["desc"] for r in unpriced))

        # ── 심층: 이 경기의 근거를 마켓 행마다 1:1로 남긴다 ──
        detail.append(f"■ {matchup(g)}")
        for r in priced:
            # [§8-18] 돈·손익분기·시장 환산을 뺐다. 남는 것은 확률과 근거뿐이다.
            detail.append(
                f"  {('★' * r['stars']) if r['stars'] else '─'}{r['warn']} {r['desc']}: "
                f"승률 {r['p']:.1%} / 근거 {r['axes'] or '없음'}"
                + (f" / 제외: {r['reject']}" if r.get("reject") else ""))
        for r in unpriced:
            detail.append(f"  ─ {r['desc']}: 확률 미산출 — 재료 부족")
        if g.get("lambda_trace"):
            detail.append("  λ 산출: " + " → ".join(g["lambda_trace"]))
        if g.get("lambda_missing"):
            detail.append("  λ 미확보 입력: " + ", ".join(g["lambda_missing"]))
        if g.get("p_claude") is not None:
            detail.append(f"  판정 승률(홈) {g['p_claude']:.1%} "
                          f"· 신뢰도 {g.get('judge_confidence') or '?'}")
        if g.get("verdict"):
            detail.append(f"  판정 근거: {str(g['verdict'])[:300]}")
        unused = ((g.get("prob_adjust") or {}).get("unused")) or []
        if unused:
            detail.append("  (확률 미반영) " + ", ".join(unused))
    return lines, detail

def _guard_basic(text: str, where: str) -> str:
    """기본층 금지어 런타임 검증 — 위반은 코드 버그이므로 에러 로그로 즉시 드러낸다."""
    v = basic_layer_violations(text)
    if v:
        logger.error("[2layer] 기본층 금지어 검출 (%s): %s", where, v)
    return text


NO_MATERIAL_MSG = "최신 데이터 수집에 실패해 분석할 수 없습니다."

# [4] 종목별 용어 — 야구는 라인업 발표, 축구는 킥오프
LINEUP_MOMENT = {
    "mlb": "경기 시작 전 라인업 발표",
    "kbo": "경기 시작 전 라인업 발표",
    "npb": "경기 시작 전 라인업 발표",
    "soccer": "킥오프 직전",
}

_DIGIT_RE = re.compile(r"\d")


def _sport_of(jg: dict) -> str:
    """[4] 경기 객체에서 종목 판정 — 문구의 종목 오용(야구에 '킥오프')을 막는다.

    [§8-14] KBO·NPB도 야구다. 여기서 'soccer'로 떨어지면 카드에 '킥오프 직전'·'핸디'
    같은 축구 용어가 나간다 — 종목별 용어 분리 규율 위반이다.
    """
    if jg.get("sport") in ("mlb", "soccer"):
        return jg["sport"]
    if jg.get("sport") in ("kbo", "npb"):
        return "mlb"                      # 야구 용어(런라인·라인업 발표)를 쓴다
    if jg.get("league") in ("MLB", "KBO", "NPB"):
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

    "레즈 승 — 10번 중 6번 이기는 계산"
    EV·기대값 표현은 쓰지 않는다 (기본층 금지어).
    """
    from app.config import get_settings
    from app.engine.markets import best_market, rejection_summary

    s = get_settings()
    board = jg.get("market_board") or []
    out: list[str] = []
    if not board:
        out.append(f"걸 만한가? {away_kr} @ {home_kr}는 배당을 수집하지 못해 판단할 수 없습니다.")
        return out

    top = best_market(board) or {}
    grade, desc, odds, prob = (top.get("grade"), top.get("desc", "?"),
                               top.get("odds"), top.get("p"))
    h2h = next((c for c in board if c["market"] == "h2h"), None)
    h2h_dead = h2h is not None and h2h.get("grade") == "🔴"

    if grade in ("🟢", "🟡") and prob is not None:
        lead = "승패는 볼 게 없지만 " if h2h_dead and top["market"] != "h2h" else ""
        tail = "걸 만합니다" if grade == "🟢" else "소액이면 볼 만합니다"
        price = _odds_tag(odds)
        out.append(f"걸 만한가? {lead}{desc}{price} — {_times_out_of_ten(prob)} "
                   f"이기는 계산. {tail}.")
        if top["market"] != "h2h":
            out.append(f"걸 만한가? 승패 대신 {desc}{price}가 이 경기 최선입니다 — "
                       f"{_times_out_of_ten(prob)} 적중.")
        return out

    # 전 마켓 기준 미달 — 무엇이 왜 미달인지 밝힌다
    out.append(f"걸 만한가? 전 마켓을 봤지만 승률 {s.min_win_prob:.0%} "
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
    if sport in ("mlb", "kbo", "npb"):
        st = jg.get("stats") or {}
        hp = st.get("home_pitcher") or (research.get("home_pitcher") or {}).get("name")
        ap = st.get("away_pitcher") or (research.get("away_pitcher") or {}).get("name")
        if hp or ap:
            out.append(f"선발 예고({hp or '?'} vs {ap or '?'})는 "
                       f"{LINEUP_MOMENT.get(sport, LINEUP_MOMENT['mlb'])}에서 바뀔 수 있습니다.")
    elif jg.get("starts_at_kst"):
        out.append(f"부상·라인업 변수는 {LINEUP_MOMENT['soccer']}({jg['starts_at_kst']})에 "
                   f"바뀔 수 있습니다.")
    return out


def render_game_easy(jg: dict, news: str = "", used: set[str] | None = None) -> str:
    """심층 분석 2층 출력: 쉬운 요약 6줄 + <<DETAIL>> 뒤에 전문 상세(접힘용).

    데이터를 줄이지 않는다 — 표현만 바꾼다. 전문 수치는 전부 상세에 보존.
    used: 여러 경기를 함께 낼 때 문장 중복을 막는 공유 집합 ([3]).
    """
    sport = jg.get("sport") or _sport_of(jg)
    if sport in ("mlb", "kbo", "npb") and jg.get("matchup"):
        from app.engine.form_card import render_form_card

        return render_form_card(jg, sport)
    from app.research.validate import research_materials, sanitize_research

    home_kr, away_kr = _kr(jg["home"]), _kr(jg["away"])
    sport = _sport_of(jg)
    research, _ = sanitize_research(jg.get("research") or {}, sport)
    names = _player_names(jg, research)
    signal, reason, stars = classify_signal(jg)
    lines = [f"{jg['starts_at_kst']} {away_kr} @ {home_kr} [{jg.get('league', '?')}]"]
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
    # [§9-2단] 5칸 카드 요약은 **서술 예산(9줄) 위에 얹는다.**
    #   ⚠️ 상한을 10으로 올리면 카드가 없는 경기까지 서술 한 줄이 더 새어 나간다
    #     (실측: 카드 없는 MLB 경기가 9줄 → 10줄이 됐다). 예산은 그대로 두고
    #     카드 줄만 추가한다 — 새 기능이 기존 출력을 바꾸면 안 된다.
    from app.engine.card import card_summary_line, compare_lines

    visible = lines[:9]
    _card_line = card_summary_line(jg)
    if _card_line:
        visible.insert(2, _card_line)
    # [§9-3단] **결론이 맨 위다.** 3줄(우세·유리 칸·반대 칸)로 고정하고
    #   긴 서술은 접힌 상세로 내린다 — 문단 안에 결론이 파묻히면 안 보인다.
    for _i, _ln in enumerate(compare_lines(jg)):
        visible.insert(_i, _ln)
    # 카드 기반 마켓(언더오버·핸디캡)은 결론 바로 아래 한 줄로 모은다
    from app.engine.card_markets import market_calls

    _mk = market_calls(jg)
    if _mk:
        visible.insert(len(compare_lines(jg)),
                       "🎯 " + " · ".join(c["desc"] for c in _mk))      # 신호등 바로 아래
    return _guard_basic("\n".join(visible) + DETAIL_SEP + detail, "game_easy")


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


def _odds_tag(odds) -> str:
    """가격이 있으면 ' @1.62'. 야구 승부는 배당을 조회하지 않아 빈 문자열."""
    try:
        return f" @{float(odds):.2f}"
    except (TypeError, ValueError):
        return ""


def _odds_slash(odds) -> str:
    try:
        return f" / 배당 {float(odds):.2f}"
    except (TypeError, ValueError):
        return ""


def board_row(c: dict, confidence: str | None = None) -> str:
    """[2][3-3] 마켓 보드 1행 — 돈으로 말한다. 배당이 없어도 행은 남긴다.

    형식: 마켓 | 승률 | 신호등 | 근거 | ★
    [§8-18] 배당·1만원 수익 열을 뺐다 — 봇은 가격도 돈도 말하지 않는다.
    """
    from app.engine.markets import row_stars

    prob = f"{c['p']:.0%}" if c.get("p") is not None else "확률 미산출"
    grade = c.get("grade") or "⚪"
    note = c.get("grade_note") or c.get("reject_reason") or "—"
    stars = row_stars(c, confidence)
    star_txt = _stars(stars) if stars else "—"
    return f"{c['desc']} | {prob} | {grade} | {note} | {star_txt}"


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
               if ho and ao else f"{away_kr} @ {home_kr}")
    st = jg.get("stats") or {}
    pitchers = ""
    if sport == "mlb" and (st.get("home_pitcher") or st.get("away_pitcher")):
        # [§8-29] 팀 표기가 '원정 @ 홈'이므로 선발도 원정 먼저 — 순서가 엇갈리면 더 헷갈린다
        pitchers = f" | {st.get('away_pitcher') or '?'} vs {st.get('home_pitcher') or '?'}"
    label = f" [{jg['status_label']}]" if jg.get("status_label") else ""
    header = f"{jg['starts_at_kst']} [{jg.get('league', '?')}] {matchup}{pitchers}{label}"

    research, dropped = sanitize_research(jg.get("research") or {}, sport)
    mats = research_materials(research)
    if not any(mats.values()):
        # [2] 재료 없음 → 분석 생성 금지. 실패 사실만 알린다.
        why = " (수집된 응답이 데이터가 아니라 무효 처리)" if dropped else ""
        return "\n".join([header, f"⚠️ 리서치 실패{why}", NO_MATERIAL_MSG])

    lines = [header]
    # [§9-2단] **상태 카드가 먼저다.** 5칸 ▲▼가 이 봇의 결론 근거이고,
    #   서술은 그 뒤를 설명할 뿐이다. 판정이 없으면 사실만 나가되 그 사실을 밝힌다.
    from app.engine.card import CELLS as _CELLS, compare_lines, render_state_card

    _cmp = compare_lines(jg)
    if _cmp:
        lines.extend(_cmp)
        _v = jg.get("compare") or {}
        _basis = _v.get("basis_cells") or []
        if _basis:
            _labels = dict(_CELLS)
            lines.append("  근거 칸: " + ", ".join(_labels.get(k, k) for k in _basis))
        # 긴 서술은 **여기**(접힌 상세)에만 둔다 — 기본층은 3줄로 끝낸다.
        if _v.get("reason"):
            lines.append(f"  판정 근거: {_v['reason']}")
    lines.extend(render_state_card(jg))
    # [§9-6번째 칸] 득점 환경 + 카드 기반 마켓 — 근거 칸을 함께 쓴다
    from app.engine.card_markets import render_market_calls

    _sc = jg.get("scoring") or {}
    if _sc.get("level"):
        lines.append(f"💥 득점 환경: {_sc['level']} — {_sc.get('reason', '')}")
    lines.extend(render_market_calls(jg))
    # [§9-라인업 의도] 평소 대비 무엇이 달라졌고 그것이 무슨 뜻인지
    from app.engine.lineup_intent import render as render_lineup_intent

    lines.extend(render_lineup_intent(jg))
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
            f"대표 마켓: {ps.get('desc') or _kr(ps['side'])}{_odds_tag(ps.get('odds'))} — "
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
        text = (note or "")[:150]
        lines.append(text if text.startswith("🔄") else f"🔄 {text}")
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
            lines.append(f"[{matchup(g)}] {h.strip()[:160]}")
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


# [7-4] 단계 실패 → 사용자가 읽을 한계 문구 (없으면 None)
_STAGE_LIMIT_KR = {
    "판정": "판정 미수행",
    "λ 산출": "λ 미산출",
    "리서치": "리서치 미완",
    "서술": "심층 서술 없음",
    "경기 적재": "일정 수집 실패",
}
_CAUSE_KR = {
    "credit": "크레딧 부족", "auth": "키 오류", "rate_limit": "레이트리밋",
    "parse": "파싱 실패", "timeout": "타임아웃", "missing": "데이터 없음",
    "exception": "오류",
}


def data_limitation_line(analysis: dict) -> str | None:
    """[7-4] 이 리포트를 만든 데이터의 결함 한 줄. 결함이 없으면 None.

    실사고(2026-08-25): λ 0/15 · judge 0/15로 사실상 빈 리포트가 나갔는데
    카드에는 아무 표시도 없었다. 사용자가 정상 분석으로 오해할 수 있었다.
    """
    stages = analysis.get("stages") or []
    bad = []
    for st in stages:
        total, ok = st.get("total") or 0, st.get("ok") or 0
        # ⚠️ **부분 수집은 한계가 아니다.** 5경기 중 3경기에만 기사가 있는 것은
        #   정상인데 종전에는 이 줄에 "기사 발췌 2경기"로 실려 나갔다.
        #   심각도가 '정상'이면 싣지 않는다(옛 캐시는 severity가 없으므로 폴백).
        sev = st.get("severity")
        if sev == "정상":
            continue
        if sev is None and (not total or ok >= total):
            continue
        if sev is not None and sev not in ("부분", "실패"):
            continue
        if not total and sev is None:
            continue
        label = _STAGE_LIMIT_KR.get(st.get("name"), st.get("name"))
        cause = _CAUSE_KR.get(st.get("cause") or "", "")
        # ⚠️ 단위는 스테이지가 선언한 것을 쓴다. 기본 "경기"를 하드코딩하면
        #   팀 수·값 개수가 경기로 둔갑한다(실측: 5경기 슬레이트에 438경기).
        unit = st.get("unit") or "경기"
        scope = "" if ok == 0 else f" {total - ok}{unit}"
        bad.append(f"{label}{scope}" + (f"({cause})" if cause else ""))
    if not bad:
        return None
    basis = ("시장 배당과 폼 데이터만 반영됨"
             if any("판정" in b or "λ" in b for b in bad) else "일부 근거가 얕음")
    return f"⚠️ 이 리포트의 한계: {' · '.join(bad)} — {basis}"


def _render_card(analysis: dict) -> str:
    """결론 카드 2층: 보이는 줄은 쉬운 말(20줄), 수치 근거는 <<DETAIL>> 뒤(접힘)."""
    games = analysis.get("games", [])
    scheduled = [g for g in games if g.get("status") == "scheduled"]
    picks = analysis.get("picks", [])
    # [§8-9] 추천은 파이프라인이 만든 목록을 그대로 쓴다. `picks`에서 플래그로
    #        재계산하면 대표 픽과 다른 마켓의 추천이 통째로 사라진다.
    #        (옛 캐시 호환: 목록이 없으면 종전 플래그 방식으로 폴백)
    recommended = analysis.get("recommended")
    if recommended is None:
        recommended = [p for p in picks if p.get("recommended")]
    combos_info = analysis.get("combos") or {}
    sport_kr = {"mlb": "MLB", "kbo": "KBO", "npb": "NPB"}.get(
        analysis.get("sport"), "축구")
    league_set = {g.get("league") for g in games}
    scope = f" ({next(iter(league_set))})" if len(league_set) == 1 and games else ""

    lines = [f"📌 {analysis.get('date')} {sport_kr}{scope} {len(games)}경기"]
    # [7-4] 데이터에 결함이 있으면 **반드시 맨 위에** 표시한다.
    #       결함이 있는데 정상 리포트처럼 내보내는 것을 금지한다.
    limit_line = data_limitation_line(analysis)
    if limit_line:
        lines.append(limit_line)
    # [A-4단계] **어떤 근거 위에 선 판정인지 밝힌다.** 축이 줄어든 사실을 숨기면
    #   같은 신호등이 종목마다 다른 무게를 갖게 된다(KBO는 전문가 축이 없다).
    from app.engine.coverage import coverage_note

    _cov = coverage_note(analysis.get("sport") or "")
    if _cov:
        lines.append(_cov)
    detail = ["📊 상세 데이터"]
    meta = analysis.get("research_meta") or {}
    if meta.get("refreshed"):
        lines.append(f"🔍 {meta['refreshed']}경기 최신 재조사 반영")
    if meta.get("stale_fallback") or meta.get("missing"):
        lines.append("⚠️ 일부 경기 새벽 데이터 기준 (최신 재조사 실패·미완)")
    if meta.get("quota"):
        lines.append("⚠️ 금일 리서치 쿼터 소진 — 이후 분석은 캐시 기준")
    # 배당을 쓰지 않는 종목에는 배당 경고를 띄우지 않는다 — 사용자가 고칠 수도
    # 없고 이 리포트와 무관한 경고다.
    if analysis.get("quota_warning") and analysis.get("sport") not in ("kbo", "npb", "mlb"):
        lines.append("⚠️ 배당 데이터 잔여 쿼터 부족 — 배당 갱신이 지연될 수 있습니다")
    scored = [g for g in scheduled if g.get("p_market") is not None and g.get("p_claude") is not None]
    if scored:
        surest = max(scored, key=lambda g: {"high": 2, "medium": 1, "low": 0}.get(g.get("judge_confidence", "medium"), 1) * 100 - abs(g["p_claude"] - g["p_market"]) * 100)
        disputed = max(scored, key=lambda g: abs(g["p_claude"] - g["p_market"]))
        lines.append(f"가장 자신 있는 경기: {matchup(surest)} — 시장과 봇 판단이 같은 곳을 봅니다")
        lines.append(f"데이터가 갈리는 경기: {matchup(disputed)} — 서로 다른 답을 내놓은 경기입니다")
        detail.append(f"확신도 최고: {matchup(surest)} — 시장 {surest['p_market']:.0%} / 판정 {surest['p_claude']:.0%} (신뢰도 {surest.get('judge_confidence')})")
        detail.append(f"논쟁: {matchup(disputed)} — 시장 {disputed['p_market']:.0%} vs 판정 {disputed['p_claude']:.0%}")
    for g in scheduled:
        if g.get("breaking_note"):
            lines.append(g["breaking_note"])
    if analysis.get("parlay_rebuilt_note"):
        lines.append(analysis["parlay_rebuilt_note"])

    # [§9-3단] **첫 화면에 경기별 결론을 한 줄씩.** 드릴다운을 눌러야 결론이
    #   보이면 결론이 없는 것과 다르지 않다.
    #   ⚠️ 판정 못 한 경기도 남긴다 — 조용히 빠지면 분석된 것으로 오인된다.
    if scheduled:
        from app.engine.card import slate_compare_row

        _rows = [slate_compare_row(g) for g in scheduled]
        if any("우세" in r or "우열" in r for r in _rows):
            lines.append("")
            lines.extend(_rows)
            _none = sum(1 for r in _rows if "판정 미수행" in r)
            if _none:
                lines.append(f"({_none}경기는 판정을 받지 못했습니다)")

    # 판정 실패를 '추천 없음'으로 위장하지 않는다 — 재료 없으면 정직하게 실패를 알린다
    judged = [g for g in scheduled if g.get("p_claude") is not None]
    if scheduled and not judged:
        lines.append("")
        lines.append("⚠️ 판정 실패 — 오늘 경기 판정을 받지 못해 분석을 완료하지 못했습니다.")
        lines.append("추천·조합을 낼 수 없습니다. (관망 권장이 아니라 '분석 미완'입니다)")
        detail.append(f"판정 부착 0건 / 분석 대상 {len(scheduled)}경기 — judge 응답 확인 필요")
        # [§9-2단] **판정이 실패해도 수집한 사실은 내보낸다.**
        #   종전에는 여기서 그냥 끝나 5칸 카드가 통째로 사라졌다 — 크롤링으로
        #   모은 사실이 다 있는데 화면에는 "판정 실패" 두 줄뿐이었다.
        #   판정 여부를 위장하지 않으면서 사실은 보여주는 것이 옳다.
        from app.engine.card import card_summary_line, compare_line, render_state_card

        _shown = 0
        for g in scheduled:
            summary = card_summary_line(g)
            if not summary:
                continue
            _shown += 1
            # 3단 결론이 있으면 그것을 쓴다 — 카드 요약보다 결론이 앞선다.
            lines.append(f"{_kr(g['away'])} @ {_kr(g['home'])} "
                         f"{compare_line(g) or summary}")
            detail.extend(render_state_card(g))
        if _shown:
            lines.insert(len(lines) - _shown,
                         "🃏 수집한 사실은 아래에 그대로 있습니다 (판정만 미수행)")
        return _guard_basic("\n".join(lines[:20])[:3500] + DETAIL_SEP + "\n".join(detail[:60]), "card")

    # [§8-13] **봇이 고르지 않는다.** 전 경기·전 마켓을 별점 순으로 나열하고
    #   판단은 사용자가 한다. 근거 수치는 심층(<<DETAIL>>)에 마켓 행마다 1:1로 붙는다.
    #   종전에는 봇이 상위 2건만 "오늘의 추천"으로 골라 내보내, 자격을 통과한 나머지
    #   마켓이 기본층에서 통째로 보이지 않았다.
    board_lines, board_detail = render_star_board(games)
    lines.extend(board_lines)
    detail.extend(board_detail)
    _s = get_settings()
    lines.append("")
    lines.append(f"★ = 충족한 조건 수: 승률 {_s.min_win_prob:.0%}↑ / {_s.signal_green_prob:.0%}↑ / "
                 f"근거 2축↑ / 판정 신뢰도 높음")
    lines.append("⚠ = 판정 신뢰도가 낮음 — 별점과 별개로 한 번 더 확인하십시오")
    # 자격 통과 여부는 **기본층**에 쓴다 — "기준을 넘는 게 있었나"는 접으면 안 되는 정보다.
    if recommended:
        _stake = next((r.get("stake_krw") for r in recommended if r.get("stake_krw")), None)
        lines.append("자격 통과(승률 + 2-소스): "
                     + ", ".join(f"{r['desc']} {r['p']:.0%}"
                                 for r in recommended)
                     + (f" — 건당 플랫 {_stake:,}원" if _stake else ""))
        detail.extend(
            f"{r['desc']}: 승률 {r['p']:.1%}{_odds_slash(r.get('odds'))} / "
            f"근거 {r.get('axes') or '?'} / 판정 신뢰도 {r.get('confidence')}"
            for r in recommended)
    else:
        lines.append(f"자격(승률 {_s.min_win_prob:.0%}·2-소스)을 "
                     f"통과한 마켓 없음 — 위 보드의 별점은 상대 비교용입니다")
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
            money = ""
            lines.append(f"참고 조합 {i}({c['tier']}): {legs_txt} @{c['odds']:.2f} "
                         f"(적중률 {c['p']:.0%}, {money}) — {c['stake_note']}{relax}")
            detail.append(f"조합 {i} 레그별 승률: " + ", ".join(
                f"{leg['desc']} {leg['p']:.0%}@{leg['odds']:.2f}" for leg in c["legs"]))
        if combos_info.get("all_fail_prob") is not None:
            lines.append(f"세 조합 모두 실패할 확률 ≈ {combos_info['all_fail_prob']:.0%}")
        if combos_info.get("low_confidence"):
            lines.append("⚠️ 오늘은 확신이 낮은 날입니다")
    lines.append("⚠️ 조합은 하나만 빗나가도 전부 실패합니다")

    # [§8-13] 전 경기·전 마켓을 싣기 때문에 20줄 상한으로는 잘린다.
    #   텔레그램 4096자 분할은 bot.main.split_message가 처리하므로 여기서 자르지 않는다.
    #   심층도 경기당 여러 줄이 붙으므로 함께 올린다.
    easy = "\n".join(lines[:CARD_MAX_LINES])[:CARD_MAX_CHARS]
    return _guard_basic(easy + DETAIL_SEP + "\n".join(detail[:DETAIL_MAX_LINES]), "card")


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
    # [§8-9] 스코프 뷰도 **마켓 보드 전체**에서 뽑는다 — 전체 슬레이트와 같은 풀이어야
    #        "전체에선 추천인데 리그로 좁히면 사라진다"는 모순이 생기지 않는다.
    recommended = qualified_singles(games, settings)[: mode["max_picks"]]
    _stake = None       # [§8-18] 스테이킹 제거
    for r in recommended:
        r["stake_krw"] = _stake
    rec_keys = {(r["game_id"], r["desc"]) for r in recommended}
    for p in picks:
        p["recommended"] = (p["game_id"], p.get("desc")) in rec_keys
    stake_krw = None    # [§8-18] 스테이킹 제거
    urls = {ep.get("source_url") for g in games for ep in g.get("expert_picks", [])}
    sources = [s for s in analysis.get("sources", []) if s["url"] in urls]
    return {
        **analysis, "games": games, "picks": picks, "recommended": recommended,
        "combos": build_tiered_parlays(approved_market_legs(games), stake_krw,
                                       analysis.get("sport")),
        "sources": sources,
    }


def _reco_reject_detail(games: list[dict], settings, top: int = 8) -> list[str]:
    """단식이 0건일 때 '왜 없는지'를 상세에 적는다.

    마켓 보드에서 승인됐지만 자격을 통과하지 못한 행을 승률 순으로 보여 주고,
    각 행이 어느 조건에 걸렸는지 밝힌다. "없습니다"만 남기면 사용자는
    기준이 빡빡한 건지 데이터가 없는 건지 구분할 수 없다.
    """
    rows = []
    for jg in games:
        if jg.get("status") != "scheduled":
            continue
        for c in jg.get("market_board") or []:
            if not c.get("approved") or c.get("p") is None or not c.get("odds"):
                continue
            if qualifies(c, settings):
                continue
            req = c.get("required_prob") or settings.min_win_prob
            why = []
            if c["p"] < req:
                why.append(f"승률 {c['p']:.0%}<{req:.0%}")

            if not c.get("two_source"):
                why.append("2소스 미달")
            if False:
                why.append(f"시장 대비 괴리 {c.get('edge', 0):+.0%}")
            rows.append((c["p"], f"   · {c['desc']}: {', '.join(why) or '기타'}"))
    if not rows:
        return ["  자격을 통과하지 못한 마켓도 없습니다 — 배당·판정이 부족한 슬레이트입니다."]
    rows.sort(key=lambda x: -x[0])
    return ([f"── 단식 0건 사유 (승인 {len(rows)}행 중 상위 {min(top, len(rows))})"]
            + [t for _, t in rows[:top]])


def render_full_reco(analyses: list[dict]) -> str:
    """🎯 전체 추천 카드 — 후보 풀은 그날 전체 슬레이트(MLB+축구 전 리그)."""
    from app.engine.parlay import build_tiered_parlays

    settings = get_settings()
    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = None    # [§8-18] 스테이킹 제거
    all_games = [g for a in analyses for g in a.get("games", [])]
    # 조합과 **같은 풀**에서 단식을 뽑는다 — 경기당 대표 픽 1건에 묶으면
    # 자격 있는 마켓이 심사에서 빠져 "단식 없음"과 "조합 추천"이 모순된다.
    excluded = {p["game_id"] for a in analyses for p in a.get("picks", [])
                if p.get("judge_excluded")}
    singles = [b for b in qualified_singles(all_games, settings)
               if b["game_id"] not in excluded][: mode["max_picks"]]
    for b in singles:
        b["stake_krw"] = stake_krw
    combos = build_tiered_parlays(approved_market_legs(all_games), stake_krw)

    covered = " + ".join(
        ("MLB" if a["sport"] == "mlb" else "축구") for a in analyses)
    lines = [f"🎯 오늘 전체 추천픽 (후보 풀: {covered} 전체 슬레이트)"]
    detail = ["📊 상세 데이터"]
    if singles:
        for p in singles:
            stake = f" (권장 {p['stake_krw']:,}원)" if p.get("stake_krw") else ""
            lines.append(f"· {p.get('desc') or _kr(p['side'])}{_odds_tag(p.get('odds'))} — "
                         f"{matchup(p)}, "
                         f"{_times_out_of_ten(p['p'])} 적중하는 계산"
                         f"{'이고 배당이 후한 편입니다' if p.get('odds') else '입니다'}"
                         f" [{p.get('league', '?')} {p['starts_at_kst'][-5:]}]{stake}")
            ev_txt = f" / EV {p['ev']:+.1%}" if p.get("ev") is not None else ""
            implied = (f" / 배당에 깔린 확률 {1 / p['odds']:.1%}"
                       if p.get("odds") else "")
            detail.append(f"{p.get('desc')}: p_final {p['p']:.1%}{ev_txt}"
                          f"{implied} / 근거 {p.get('axes') or '?'}")
    else:
        lines.append("오늘은 배당 대비 이득 기준을 넘는 단식 픽이 없습니다 — 관망 권장")
        # 단식이 없을 때야말로 "왜 없는지"가 상세의 핵심이다.
        # 이게 없으면 접힌 영역이 헤더만 남아 '(내용 없음)'으로 보인다.
        detail += _reco_reject_detail(all_games, settings)
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
            lines.append(f"참고 조합 {i}({c['tier']}): {legs_txt} @{c['odds']:.2f} "
                         f"(적중률 {c['p']:.0%}) — {c['stake_note']}{relax}")
        if combos.get("all_fail_prob") is not None:
            lines.append(f"세 조합 모두 실패 확률 ≈ {combos['all_fail_prob']:.0%}")
        if combos.get("low_confidence"):
            lines.append("⚠️ 오늘은 확신도 낮음 — 권장액 절반")
        # 조합 레그의 근거를 상세에 남긴다 — 보이는 층은 한 줄이라 판단 재료가 없다
        for i, c in enumerate(combos.get("combos", []), 1):
            if not c.get("ok"):
                continue
            detail.append(f"── 조합 {i}({c['tier']}) 합산 @{c['odds']:.2f} "
                          f"· 적중률 {c['p']:.1%}")
            for leg in c["legs"]:
                detail.append(
                    f"   · {leg['desc']}: p {leg['p']:.1%} / 배당 {leg['odds']:.2f}"
                    f" (배당 내재 {1 / leg['odds']:.1%}) / 신뢰도 "
                    f"{leg.get('confidence', '?')}")
    lines.append("⚠️ 조합은 하나만 빗나가도 전부 실패합니다")
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

    _prepare_games_for_judge(affected, analysis.get("sport") or "")
    sport = analysis.get("sport") or ""
    from app.engine.scoring import BASEBALL_SPORTS

    old_ps = {jg["game_id"]: jg.get("p_claude") for jg in affected}
    if sport in BASEBALL_SPORTS:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            await _run_baseball_matchups(r, analysis["date"], affected)
        except (ApiQuotaError, Exception) as exc:
            logger.warning("[pipeline] breaking matchup failed, keeping cached verdicts: %s", exc)
            return analysis
        finally:
            await r.aclose()
        for jg in affected:
            old_p = old_ps.get(jg["game_id"])
            p = jg.get("p_claude")
            change_txt = "; ".join(jg.get("breaking_changes", []))[:120]
            old_txt = f"{old_p:.0%}" if old_p is not None else "?"
            new_txt = f"{p:.0%}" if p is not None else "?"
            jg["breaking_note"] = (
                f"🔄 속보 반영: {change_txt} → 승률 계산 {old_txt}→{new_txt}"
                + (", 패스로 전환" if jg.get("judge_pass") else "")
            )
    else:
        payload = {
            "date": analysis["date"], "sport": sport, "games": affected,
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
        by_id = {g["game_id"]: g for g in verdict2.get("games", [])}
        for jg in affected:
            v = by_id.get(jg["game_id"])
            if not v:
                continue
            old_p = old_ps.get(jg["game_id"])
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

    old_reco = {p["pick"] for p in analysis["picks"] if p.get("recommended")}
    old_parlay_legs = {
        leg["pick"] for pl in analysis.get("parlays", []) for leg in pl["legs"]
    }
    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], analysis["sport"],
                                            news=analysis.get("news") or "",
                                            sentiment=analysis.get("sentiment") or "")
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    # 조합도 재구성 (판정 뒤집힌 레그 반영) — 전 마켓 승인 풀 기준
    from app.engine.parlay import build_tiered_parlays

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = None    # [§8-18] 스테이킹 제거
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
    _prepare_games_for_judge(refreshed, sport)
    from app.engine.scoring import BASEBALL_SPORTS
    if sport in BASEBALL_SPORTS:
        try:
            await _run_baseball_matchups(redis, analysis["date"], refreshed)
        except Exception as exc:
            logger.warning("[pipeline] refresh matchup failed, keeping verdicts: %s", exc)
            await notify_api_error(exc)
    else:
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
    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport,
                                            news=analysis.get("news") or "",
                                            sentiment=analysis.get("sentiment") or "")
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    await _renarrate(refreshed, sport)   # [B-1] 재판정된 경기는 서술도 다시 쓴다
    from app.engine.parlay import build_tiered_parlays

    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = None    # [§8-18] 스테이킹 제거
    analysis["combos"] = build_tiered_parlays(
        approved_market_legs(analysis["games"]), stake_krw, analysis.get("sport"))
    meta["refreshed"] = len(refreshed)
    logger.info("[pipeline] freshness gate: %d games re-researched & re-judged", len(refreshed))
    return len(refreshed)


async def rejudge_after_lineup(game: dict, lineup: dict) -> bool:
    """[2-3] 라인업 수신 → 그 경기만 재판정. 승률·신호등·추천·조합을 갱신한다.

    야구는 낮에 캐시한 팀 폼을 재호출하지 않고 매치업만 돌린다.
    KBO·NPB는 최신 크롤을 research에 병합한 뒤 결장·매치업 순으로 다시 돌린다.
    딥서치 force는 쓰지 않는다 — 폴링 30분마다 크레딧을 쓰면 안 된다.
    MLB는 선발 변경·불일치일 때만 리서치를 강제 갱신한다.
    축구는 구 Judge 경로를 유지한다.
    """
    from app.collectors.lineups import pick_state
    from app.db import get_pool
    from app.engine.parlay import build_tiered_parlays
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
        if jg is None or jg.get("status") not in ("scheduled",):
            return False
        if jg.get("judgement_void"):
            return False

        before = (jg.get("pick_summary") or {}).get("desc")
        before_names = {
            "home": ((jg.get("research") or {}).get("home_pitcher") or {}).get("name") or "",
            "away": ((jg.get("research") or {}).get("away_pitcher") or {}).get("name") or "",
        }
        jg["lineup_status"] = lineup["status"]
        notes = list(lineup.get("notes") or [])
        jg["lineup_notes"] = notes
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
        bundle = None
        if sport in ("kbo", "npb", "mlb"):
            try:
                bundle = await load_source_bundle(redis, sport, date)
                research = jg.setdefault("research", {})
                if sport == "mlb":
                    from app.collectors.lineups import apply_lineup_poll_to_research

                    apply_lineup_poll_to_research(research, jg, lineup)
                merge_source_data(research, jg, sport, bundle)
                if sport == "mlb":
                    apply_lineup_poll_to_research(research, jg, lineup)
                notes += starter_change_notes(jg["research"], before_names)
                jg["lineup_notes"] = notes
            except Exception as exc:
                logger.warning("[pipeline] 라인업 소스 병합 실패: %s", exc)
        elif any("선발 변경" in n or "불일치" in n for n in notes):
            for side, key in (("home", "home_pitcher"), ("away", "away_pitcher")):
                if (lineup.get("starters") or {}).get(side):
                    jg.setdefault("stats", {})[key] = lineup["starters"][side]
            data, _status = await get_game_research(redis, jg, sport, force=True)
            if data:
                jg["research"] = data
        # λ가 읽는 absences·타순을 Judge보다 먼저 채운다
        if settings.lineup_intent_enabled:
            try:
                await _lineup_intent_one(pool, jg, sport, final=(state == "final"))
            except Exception as exc:
                logger.warning("[pipeline] 라인업 의도 산출 실패: %s", exc)

        _prepare_games_for_judge([jg], sport)
        from app.engine.scoring import BASEBALL_SPORTS
        if sport in BASEBALL_SPORTS:
            try:
                await _run_baseball_matchups(redis, date, [jg])
            except Exception as exc:
                logger.warning("[pipeline] 라인업 매치업 실패: %s", exc)
                await notify_api_error(exc)
        else:
            payload = {
                "date": date, "sport": sport, "games": [jg],
                "breaking_news": analysis.get("news", ""),
                "instruction": ("확정 라인업이 수신됐다. 확정 선발·타순·결장과 "
                                "today_nine·lineup_matchup·lineup_record·pitcher_matchup를 반영해 "
                                "경기력 기준으로 승률을 재산출하라. 배당은 보지 마라. "
                                "승부는 오늘 9명이다. 결장 건수로 사이드를 뒤집지 마라. "
                                "유사 타순 전적·맞대결 ERA는 표본 3 미만이면 승률 근거로 쓰지 마라. "
                                "era_vs_opponent는 시즌 상대팀이지 오늘 9명이 아니다."),
            }
            try:
                verdict = await Judge().judge(payload)
                _attach_verdicts([jg], verdict)
            except Exception as exc:
                logger.warning("[pipeline] 라인업 재판정 실패: %s", exc)
                await notify_api_error(exc)

        # [8] **세 마켓을 모두 갱신한다.** 승패만 다시 계산하면 라인업 변경이
        #   총득점·점수차에 준 영향이 반영되지 않는다.
        card_note = ""
        try:
            card_note = await rejudge_card_stack(pool, jg, sport, redis)
        except Exception as exc:
            logger.warning("[pipeline] 카드 재판정 실패: %s", exc)

        _enforce_data_rules(analysis["games"])
        picks_out, parlays, _reco = _compute_picks(
            settings, analysis["games"], sport, bundle,
            news=analysis.get("news") or "",
            sentiment=analysis.get("sentiment") or "")
        analysis["picks"], analysis["parlays"] = picks_out, parlays
        analysis["combos"] = build_tiered_parlays(
            approved_market_legs(analysis["games"]),
            None,    # [§8-18] 스테이킹 제거
            sport)
        await _renarrate([jg], sport)

        after = (jg.get("pick_summary") or {}).get("desc")
        note = "🔄 라인업 반영: " + "; ".join(jg["lineup_notes"][:2]) if jg["lineup_notes"] else \
               "🔄 라인업 확정 반영"
        if before != after:
            note += f" — 픽 변경: {before or '없음'} → {after or '없음'}"
        jg["breaking_changes"] = (jg.get("breaking_changes") or []) + [note]
        analysis.setdefault("lineup_notes", []).append(note)
        if card_note:
            jg["breaking_changes"].append(card_note)
            analysis["lineup_notes"].append(card_note)

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
        _prepare_games_for_judge([jg], sport)
        from app.engine.scoring import BASEBALL_SPORTS
        if sport in BASEBALL_SPORTS:
            try:
                await _run_baseball_matchups(redis, date, [jg])
            except Exception as exc:
                logger.warning("[pipeline] single-game matchup failed: %s", exc)
                await notify_api_error(exc)
        else:
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
        picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], sport,
                                            news=analysis.get("news") or "",
                                            sentiment=analysis.get("sentiment") or "")
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
    if settings.is_disabled("grok") or settings.mock_grok or await redis.get(fresh_key):
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
    # [A-1단계] 변화 감지를 **Go 크롤러 diff로 대체**한다 (LLM 0회).
    #   종전에는 Grok에게 "이전 브리핑 대비 뭐가 바뀌었나"를 물었다. 그런데
    #   크롤러가 이미 10분마다 스냅샷을 비교해 선발 교체·라인업 변경·경기 상태를
    #   **필드 단위로 정확히** 잡고 있다. LLM에게 산문을 비교시키는 것보다
    #   정확하고, 비용이 0이며, 크레딧이 끊겨도 동작한다.
    #   ⚠️ 야구 3리그는 크롤러·statsapi diff. 축구만 Grok을 유지한다.
    try:
        if sport in ("kbo", "npb", "mlb"):
            from app.collectors.crawler_feed import load_changes, notable_rows

            changes = notable_rows(await load_changes(redis, sport, date))
        else:
            changes = await GrokClient().delta_check(
                analysis.get("news", ""), upcoming, date)
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
    stages_out: list | None = None,
    force_research: bool = False,
    include_final: bool = False,
) -> str:
    """결론 카드(단일 메시지)를 반환. 심층·속보·출처는 분석 캐시에서 버튼으로 제공.

    sequential_research: 프리페치용 — 경기별 리서치를 순차 처리(레이트리밋 방어).
    """
    settings = get_settings()
    # 날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 표기는 항상 KST.
    date = date or default_date(sport)
    if not force_refresh and not include_final:
        cached = await redis.get(f"card:{sport}:{date}")
        if cached:
            logger.info("[pipeline] cache hit: card:%s:%s", sport, date)
            # 속보의 결론 반영: 캐시 응답 전에 최신 체크 → 중대 변화 시 재판정
            return await _freshness_gate(redis, sport, date, cached)
    analysis = await build_analysis(pool, sport, date, progress=progress, redis=redis,
                                    sequential_research=sequential_research,
                                    stages_out=stages_out,
                                    force_research=force_research,
                                    include_final=include_final)
    await (progress or _noop_progress)(4, 4, "결론 카드 작성")
    remaining = await redis.get("odds_quota_remaining")
    if remaining is not None and int(remaining) < 100:
        analysis["quota_warning"] = True
    try:
        card = await generate_card(analysis)
        if settings.report_banner:
            card = f"{settings.report_banner}\n\n{card}"
        if include_final:
            card = f"{card}\n\n{sim_scoreboard(analysis.get('games') or [])}"
    except Exception as exc:
        logger.warning("[pipeline] 결론 카드 렌더 실패 — 분석 캐시는 남긴다: %s", exc)
        card = "결론 카드를 만들지 못했습니다."
    if not include_final:
        await _save_caches(redis, analysis, card)
    return card


async def _cli() -> None:
    """텔레그램 없이 파이프라인 직접 호출: python -m app.pipeline --sport mlb"""
    import argparse
    import time

    import redis.asyncio as aioredis_

    from app.db import close_pool, get_pool

    parser = argparse.ArgumentParser(description="AnalystBot pipeline CLI")
    parser.add_argument("--sport", default="mlb",
                        choices=["mlb", "soccer", "kbo", "npb"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (기본: MLB는 미국 동부 오늘)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="카드 캐시를 건너뛰고 다시 렌더 (리서치는 신선도 게이트 유지)")
    parser.add_argument("--force", action="store_true",
                        help="전 경기 리서치를 강제 재조사 (콜 비용 발생 — 수동 실행 전용)")
    parser.add_argument("--include-final", action="store_true",
                        help="종료 경기도 분석 회로에 태운다(시뮬레이션). "
                             "오늘 운영 기본은 제외. 예측 테이블에는 쓰지 않는다.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    date = args.date or (mlb_slate_date() if args.sport == "mlb" else today_kst())
    pool = await get_pool()
    redis = aioredis_.from_url(get_settings().redis_url, decode_responses=True)
    try:
        t0 = time.monotonic()
        report = await run_pipeline(pool, redis, args.sport, date,
                                    args.force_refresh or args.force,
                                    force_research=args.force,
                                    include_final=args.include_final)
        elapsed = time.monotonic() - t0
        print(report)
        print(f"\n[elapsed {elapsed:.2f}s]")
    finally:
        await redis.aclose()
        await close_pool()


# ─────────────────────────────────── [§9-라인업 의도] 평소 대비 변경점 회로

async def _lineup_intent_one(pool, jg: dict, sport: str, final: bool = False) -> None:
    """한 경기의 라인업 의도. **경기 하나가 실패해도 슬레이트는 계속 간다** —
    예외는 호출부가 잡고 그 경기만 건너뛴다."""
    from app.collectors import lineup_history as LH
    from app.engine import lineup_intent as LI
    from app.engine.interpreter import interpret_lineup_intent
    from app.engine.lineup_diff import (bullpen_absences, diff_lineup,
                                        merge_absences_from_diff,
                                        parse_order, summarize)

    res = jg.get("research") or {}
    intent = {"headline": {}, "items": {}, "changes": {},
              "_compared": False, "_sides": 0, "_new": 0}
    per_side: dict[str, list] = {}
    for side in ("home", "away"):
        order = ((res.get(f"{side}_lineup") or {}).get("order") or "").strip()
        team = jg.get(side)
        if order and pool:
            if await LH.record(pool, jg.get("game_id"), side, team, order,
                               starter=(res.get(f"{side}_pitcher") or {}).get("name"),
                               is_final=final):
                intent["_new"] += 1
        usual = await LH.usual(pool, sport, team, jg.get("starts_at")) if pool else {}
        today = parse_order(order)
        changes = diff_lineup(today, usual) if (today and usual) else []
        roster = (res.get(f"{side}_roster") or {}).get("registered")
        keys = (res.get(f"{side}_usage") or {}).get("key_relievers")
        changes = changes + bullpen_absences(roster, keys)
        merge_absences_from_diff(res, team, changes, usual)
        summary = summarize(changes, usual)
        if usual:
            intent["_sides"] += 1
        per_side[side] = changes
        intent["headline"][side] = summary["headline"]
        intent["changes"][side] = changes
        LI.merge_changes_into_research(res, side, changes, summary["headline"])
    intent["_compared"] = intent["_sides"] == 2
    for side in ("home", "away"):
        items = []
        if per_side[side]:
            quotes = [q for q in (res.get("news_quotes") or []) if isinstance(q, str)]
            try:
                items = await interpret_lineup_intent(
                    per_side[side], jg.get(f"{side}_kr") or jg.get(side), quotes)
            except Exception as exc:   # [D-4] 해석만 빠지고 나머지는 산다
                logger.warning("[2단-라인업] %s 해석 실패 — 사실만 남긴다: %s",
                               jg.get(side), exc)
        intent["items"][side] = items
        if pool and items:
            await LI.record_verdicts(pool, jg.get("game_id"), side,
                                     jg.get(f"{side}_kr") or jg.get(side), items)
    intent["scoring"] = LI.scoring_direction(intent["items"].get("home"),
                                             intent["items"].get("away"))
    intent["handicap"] = LI.handicap_note(per_side["home"], per_side["away"])
    jg["lineup_intent"] = intent
    jg["research"] = res
    # 확정 9명의 유사 전적 + 양 팀 맞대기. 계수는 만들지 않는다.
    try:
        from app.engine.lineup_record import attach as attach_lineup_record
        await attach_lineup_record(pool, jg, sport)
    except Exception as exc:
        logger.warning("[라인업전적] 부착 실패 game=%s: %s", jg.get("game_id"), exc)
    try:
        from app.engine.pitcher_matchup import attach as attach_pitcher_matchup
        await attach_pitcher_matchup(pool, jg, sport)
    except Exception as exc:
        logger.warning("[투수맞대결] 부착 실패 game=%s: %s", jg.get("game_id"), exc)


async def _attach_lineup_intent(pool, judge_games: list[dict], sport: str,
                                record=None, final: bool = False) -> None:
    """관측 적재 → 평소 대조 → 변경점 사실화 → 2단 해석 → 채점 적재.

    ⚠️ **research에 사실을 넣은 뒤 카드를 만들어야** 변경점이 칸에 실린다.
       이 함수는 `_attach_cell_verdicts` **앞**에서 호출된다.
    """
    # [E-1 비상 스위치] 끄면 이 회로 전체를 건너뛴다 — 기존 5칸 판정은 그대로 간다.
    if not get_settings().lineup_intent_enabled:
        logger.info("[라인업의도] 비활성(LINEUP_INTENT_ENABLED=false) — 건너뜀")
        return
    live = [jg for jg in judge_games if jg.get("status") == "scheduled"]
    if not live:
        return
    changed, compared, sides = 0, 0, 0
    for jg in live:
        try:
            await _lineup_intent_one(pool, jg, sport, final)
        except ApiQuotaError:
            raise
        except Exception as exc:      # [E-3] 한 경기 실패가 슬레이트를 죽이지 않는다
            logger.warning("[라인업의도] %s 실패 — 이 경기만 건너뜀: %s",
                           jg.get("game_id"), exc)
            jg["lineup_intent"] = {}
            continue
        it = jg.get("lineup_intent") or {}
        compared += 1 if it.get("_compared") else 0
        sides += it.get("_sides", 0)
        changed += it.get("_new", 0)
    if record is not None:
        await record("라인업 의도", compared, len(live),
                     cause=None,
                     detail=f"평소 대조 {sides}팀 · 새 라인업 관측 {changed}건",
                     unit="경기", expect_full=False, zero_ok=not compared,
                     impact="평소 대비 변경점을 읽지 못해 감독 의도가 빠집니다")


def _final_minutes(sport: str | None, settings=None) -> int:
    """종목별 최종 라인업 창(분). KBO 60 · NPB 30 · 그 외 lineup_final_minutes."""
    s = settings or get_settings()
    if sport == "kbo":
        return s.lineup_final_minutes_kbo
    if sport == "npb":
        return s.lineup_final_minutes_npb
    return s.lineup_final_minutes


def is_final_window(starts_at, now=None, settings=None, sport: str | None = None) -> bool:
    """[2] 지금이 '최종 라인업' 구간인가 — 경기 N분 전 이내."""
    from app.engine.lineup_timing import _parse

    d = _parse(starts_at)
    if d is None:
        return False
    now = now or datetime.now(UTC)
    left = (d - now).total_seconds() / 60
    return 0 <= left <= _final_minutes(sport, settings)


def _market_snapshot(jg: dict) -> dict:
    """[8] 세 마켓의 현재 판정 — 재판정 전후 비교용."""
    from app.engine.card_markets import market_calls

    cmp_ = jg.get("compare") or {}
    calls = {c["market"]: c["desc"] for c in market_calls(jg)}
    return {"승패": (f"{cmp_.get('favored')}/{cmp_.get('confidence')}"
                    if cmp_.get("favored") else None),
            "득점": (jg.get("scoring") or {}).get("level"),
            "핸디": calls.get("handicap"), "언더오버": calls.get("totals")}


def _market_delta(before: dict, after: dict) -> str:
    """무엇이 바뀌어 어느 마켓 판정이 어떻게 달라졌는지 한 줄."""
    bits = [f"{k} {before.get(k) or '없음'} → {after.get(k) or '없음'}"
            for k in ("승패", "득점", "핸디", "언더오버")
            if before.get(k) != after.get(k)]
    return " · ".join(bits)


async def rejudge_card_stack(pool, jg: dict, sport: str, redis=None) -> str:
    """[2][8] 최종 라인업으로 **카드 전체를 다시 돌린다.**

    승패만 다시 계산하지 않는다 — 득점 환경 칸과 언더오버·핸디캡 판정까지
    함께 갱신한다. 라인업 변경은 승패보다 총득점에 더 크게 영향을 준다.

    반환: 사람이 읽을 변경 요약(없으면 빈 문자열).
    """
    from app.engine.card import build_card
    from app.engine.card_markets import league_total_baseline
    from app.engine.comparator import compare_game
    from app.engine.interpreter import (interpret_scoring, interpret_side,
                                        scoring_baselines)

    before = _market_snapshot(jg)
    # [2] 최종 확정 구간(KBO 60분·NPB 30분·그 외 30분)에 들어왔을 때만 '최종'.
    #   무조건 final=True로 적으면 3시간 전 라인업도 최종이 된다.
    final = is_final_window(jg.get("starts_at"), sport=sport)
    await _attach_lineup_intent(pool, [jg], sport, None, final=final)
    res = jg.get("research") or {}
    jg["card"] = build_card(jg, res)
    jg["cells"] = {"home": {}, "away": {}}
    for side in ("home", "away"):
        try:
            jg["cells"][side] = await interpret_side(
                jg["card"][side], jg.get(f"{side}_kr") or jg.get(side))
        except Exception as exc:
            logger.warning("[재판정] 2단 %s 실패: %s", jg.get(side), exc)
    jg["cells_status"] = ("판정" if any(jg["cells"].values()) else "판정 미수행")
    try:
        jg["scoring"] = await interpret_scoring(
            jg["card"].get("scoring") or {},
            baselines=scoring_baselines([jg["card"].get("scoring") or {}]))
    except Exception as exc:
        logger.warning("[재판정] 득점 환경 실패: %s", exc)
    try:
        jg["total_baseline"] = await league_total_baseline(pool, sport)
    except Exception:
        pass
    try:
        jg["compare"] = await compare_game(jg)
    except Exception as exc:
        logger.warning("[재판정] 3단 실패: %s", exc)
    delta = _market_delta(before, _market_snapshot(jg))
    if not delta:
        return ""
    head = (jg.get("lineup_intent") or {}).get("headline") or {}
    what = " / ".join(v for v in head.values() if v and "변경 없음" not in v)
    return f"🔄 최종 라인업 반영: {what or '라인업 확정'} — {delta}"


if __name__ == "__main__":
    asyncio.run(_cli())
