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


async def _collect_soccer_stats() -> dict:
    """축구 모델 = football-data.co.uk 무료 CSV 기반 Elo (app/models/soccer_elo.py).

    로컬 아티팩트가 없으면 모델 없이 진행 (해당 경기 '모델 무효' 정직 표기).
    """
    from app.models.soccer_elo import SoccerElo

    try:
        elo = await asyncio.to_thread(SoccerElo.load)
    except FileNotFoundError:
        logger.warning("[pipeline] Elo 아티팩트 없음 — python -m app.models.soccer_elo --refresh 필요")
        elo = None
    return {"elo": elo, "win_pct": {}, "era": {}}


async def _collect_research(
    pool: asyncpg.Pool, games: list[dict], date: str, league: str = "MLB",
    sport: str = "mlb",
) -> tuple[list[dict], str, list[str]]:
    """딥서치는 보조 신호 — 실패(무효 키·타임아웃 등)해도 파이프라인은 계속 간다."""
    picks_task = fetch_expert_picks(
        games, date, league=league, sport=sport, client=PerplexityClient())
    news_task = GrokClient().live_briefing(games, date, league=league)
    picks_res, news_res = await asyncio.gather(picks_task, news_task, return_exceptions=True)

    if isinstance(picks_res, BaseException):
        logger.error("[pipeline] perplexity research failed, continuing without picks: %s", picks_res)
        if isinstance(picks_res, ApiQuotaError):
            await notify_quota(picks_res.service, picks_res.detail)
        picks: list[dict] = []
    else:
        picks, _citations = picks_res
        await save_expert_picks(pool, picks)

    if isinstance(news_res, BaseException):
        logger.error("[pipeline] grok briefing failed, continuing without news: %s", news_res)
        if isinstance(news_res, ApiQuotaError):
            await notify_quota(news_res.service, news_res.detail)
        news = ""
    else:
        news = news_res
    # 마크다운 링크 병합 깨짐 방지: 본문에서 링크 제거, URL은 출처로 분리 수집
    news_urls = extract_urls(news)
    news = strip_md_links(news)
    return picks, news, news_urls


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
    by_book: dict[str, dict[str, float]] = {}
    best_odds: dict[str, float] = {}
    for r in rows:
        by_book.setdefault(r["book"], {})[r["side"]] = float(r["odds"])
        best_odds[r["side"]] = max(best_odds.get(r["side"], 0.0), float(r["odds"]))

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


# ---------------------------------------------------------------- 분석 본체

async def _noop_progress(step: int, total: int, label: str) -> None:
    return None


async def build_analysis(
    pool: asyncpg.Pool, sport: str, date: str,
    team: str | None = None, progress=None,
) -> dict:
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

            fd = FootballDataClient()
            if not fd.mock:
                ext_ids += await upsert_games_from_football_data(pool, date, client=fd)
            ext_ids += await upsert_games_from_odds_events(pool, date)
        stats_coro = _collect_soccer_stats()
        league = "soccer (EPL·J1·수페르리가 등)"

    game_rows = await pool.fetch(
        """
        SELECT * FROM games
        WHERE sport = $1 AND ext_id = ANY($2::text[])
        ORDER BY starts_at
        """,
        sport, ext_ids,
    )
    games = [dict(r) for r in game_rows]
    if team:  # 특정 팀 질문 — 그 경기 1건만 분석 (전체 파이프라인 낭비 금지)
        games = [g for g in games if team in (g["home"], g["away"])]
        if not games:
            return {"sport": sport, "date": date, "games": [], "picks": [],
                    "parlays": [], "news": "", "sources": [], "verdict": {"games": []}}

    await progress(2, 4, "배당·딥서치 수집")
    # 2) 스탯 ∥ 배당 ∥ 딥서치 병렬 수집
    stats, _, (raw_picks, news, news_urls) = await asyncio.gather(
        stats_coro,
        snapshot_odds(pool, sport, client=OddsClient()),
        _collect_research(pool, games, date, league, sport=sport),
    )

    # 3) 경기별 p_model / p_market / 전문가 컨센서스
    weights = await load_expert_weights(pool)
    judge_games = []
    for g in games:
        p_model3 = None
        if sport == "mlb":
            p_model = heuristic_model_prob(
                stats["win_pct"].get(g["home"], 0.5),
                stats["win_pct"].get(g["away"], 0.5),
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
        judge_games.append({
            "game_id": g["id"],
            "home": g["home"], "away": g["away"], "league": g["league"],
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "status": g["status"],
            "status_label": STATUS_LABELS.get(g["status"], ""),
            "p_model": round(p_model, 4),
            "model_valid": model_valid,
            "p_model3": [round(x, 4) for x in p_model3] if p_model3 else None,
            "p_market": p_market,
            "market_probs": (
                {k: round(v, 4) for k, v in market_probs.items()} if market_probs else None
            ),
            "best_odds": best_odds,
            "stats": {
                "home_win_pct": stats["win_pct"].get(g["home"]),
                "away_win_pct": stats["win_pct"].get(g["away"]),
                "home_pitcher": g["home_pitcher"],
                "home_pitcher_era": stats["era"].get(g["home_pitcher"]),
                "away_pitcher": g["away_pitcher"],
                "away_pitcher_era": stats["era"].get(g["away_pitcher"]),
            },
            "expert_picks": [dict(r) for r in pick_rows],
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

    # 5) 사이드별 앙상블 → EV/켈리 → 검증 플래그·판정 제외 → 모드 적용
    picks_out, parlays, recommended = _compute_picks(settings, judge_games, sport)
    for p in recommended:
        await pool.execute(
            """
            INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            p["game_id"], p["pick"], p["p"], p["odds"], p["ev"], p["kelly"],
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
    return {
        "sport": sport, "date": date,
        "mode": {"name": settings.report_mode, **mode,
                 "stake_krw": int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None,
                 "bankroll_krw": settings.bankroll_krw},
        "games": judge_games, "picks": picks_out,
        "parlays": parlays,
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
    """jg(판정 부착 완료) → (전체 픽, 조합, 추천 픽). DB 접근 없음 — 재판정 시 재사용."""
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
        market = jg["market_probs"]
        if not market or jg["home"] not in market or jg["away"] not in market:
            continue

        # 사이드별 확률: 축구는 무승부 질량 때문에 1-p_home ≠ p_away — 시장 3-way 기준
        p_draw_m = market.get("Draw", 0.0)
        p_claude_home = jg["p_claude"]
        p_claude_away = max(0.0, min(1.0, 1.0 - p_claude_home - p_draw_m))
        p3 = jg["p_model3"]
        candidates = []
        for side, p_model_s, p_market_s, p_claude_s in (
            (jg["home"], (p3[0] if p3 else (jg["p_model"] if jg["model_valid"] else None)),
             market[jg["home"]], p_claude_home),
            (jg["away"], (p3[2] if p3 else ((1 - jg["p_model"]) if jg["model_valid"] and sport == "mlb" else None)),
             market[jg["away"]], p_claude_away),
        ):
            odds = jg["best_odds"].get(side)
            if not odds:
                continue
            p_side = blend(p_model_s, p_market_s, p_claude_s)
            candidates.append((ev(p_side, odds), side, p_side, odds, p_model_s))
        if not candidates:
            continue
        pick_ev, side, p_side, odds, p_model_s = max(candidates)
        pick = f"h2h:{side}"
        pick_kelly = kelly(p_side, odds, settings.kelly_fraction, settings.kelly_cap)

        # 데이터 검증 가드
        implied = implied_prob(odds)
        flags = []
        if pick_ev > EV_FLAG_MAX:
            flags.append(f"EV {pick_ev:+.1%} > +20% (배당 데이터 이상 의심)")
        if p_model_s is not None and abs(p_model_s - implied) > MODEL_GAP_MAX:
            flags.append(f"모델 {p_model_s:.0%} vs 배당 암시 {implied:.0%} 괴리 >25%p")
        # 판정 제외: Claude가 패스 권장/저신뢰로 본 경기는 추천 목록에서 뺀다
        judge_excluded = None
        if jg.get("judge_pass"):
            judge_excluded = f"판정: 패스 권장 — {jg['verdict'][:120]}"
        elif jg.get("judge_confidence") == "low":
            judge_excluded = f"판정: 저신뢰 — {jg['verdict'][:120]}"

        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "starts_at_kst": jg["starts_at_kst"], "pick": pick, "side": side,
            "p": round(p_side, 4), "p_claude": jg["p_claude"],
            "model_valid": jg["model_valid"],
            "odds": odds, "ev": round(pick_ev, 4), "kelly": round(pick_kelly, 4),
            "stake_krw": stake_krw,
            "verdict": jg["verdict"], "excluded_picks": jg["excluded_picks"],
            "flags": flags, "judge_excluded": judge_excluded,
        }
        picks_out.append(entry)
        if flags:
            logger.warning(
                "[pipeline] suspicious pick flagged — %s @ %s | %s odds=%.2f: %s",
                jg["away"], jg["home"], pick, odds, "; ".join(flags),
            )

    picks_out.sort(key=lambda x: x["ev"], reverse=True)
    # 단식 추천 = 플래그·판정제외 없음 + EV 임계 통과 + 모드별 픽 수 상한
    clean = [
        p for p in picks_out
        if not p["flags"] and not p["judge_excluded"] and p["ev"] > settings.ev_threshold
    ]
    recommended = clean[: mode["max_picks"]]
    for p in picks_out:
        p["recommended"] = p in recommended
    # 조합 레그 = 판정 제외·플래그 없는 +EV 픽 전체 (단식 상한과 무관)
    legs = [{"game_id": p["game_id"], "pick": p["pick"], "p": p["p"],
             "odds": p["odds"], "ev": p["ev"]} for p in clean]
    return picks_out, best_parlays(legs), recommended


# ---------------------------------------------------------------- 리포트 생성

CARD_SYSTEM = """너는 20년 경력의 스포츠 베팅 수석 애널리스트다. 입력 JSON(경기·픽·조합·판정)만을 근거로 텔레그램 '결론 카드' 하나를 작성한다.

[데이터 규율]
- 입력에 없는 수치·팀·근거를 만들어내지 마라. 근거 한 줄에도 수치를 1개 이상 병기하라 ("우세" 단독 금지).
- 한국어, 팀명 한국어 표기 통일, 시각은 KST.

[결론 카드 — 유일한 출력, 최대 20줄, 4096자 미만. 초과 시 분할이 아니라 압축]
구성 순서:
1) 헤더 3줄: "📌 {날짜} {종목} {경기수}경기" / "확신도 최고: {경기} — {근거 수치 한 줄}" / "논쟁: {경기} — {갈리는 지점 한 줄}"
2) games[].breaking_note 가 있으면 그대로 각 1줄 ("🔄 속보 반영: ..."). parlay_rebuilt_note 가 있으면 그 줄도.
3) 🎯 오늘의 추천 (카드의 마지막 섹션):
   - 단식: recommended=true 픽마다 "· {팀} 승 @{배당} — {근거 한 줄} (권장 {stake_krw:,}원)" — 최대 2줄
   - 조합: parlays 배열 순서대로 "조합 {n}: {팀A+팀B(+...)} @{합산배당} (적중률 {p:.0%})" 각 1줄, 최대 3줄
   - 조합이 1개 이상이면 바로 아래 고정 문구: "⚠️ 조합은 고분산 — 단식 권장액의 절반 이하 소액만"
   - recommended가 없으면: "오늘은 기준(EV +5%↑)을 넘는 픽 없음 — 관망 권장"
- 경기별 심층·전문가 인용·속보 상세·출처는 카드에 쓰지 마라 (버튼 섹션 전용).
- 켈리 % 표기 금지(모드가 flat일 때). 인사말·마무리 문구 불필요."""


def _team_news_lines(news: str, home: str, away: str) -> list[str]:
    keys = {home.lower(), away.lower(), home.split()[-1].lower(), away.split()[-1].lower()}
    return [ln for ln in news.splitlines() if any(k in ln.lower() for k in keys)]


def render_game_section(jg: dict, news: str = "") -> str:
    """경기 1건 심층 ①~⑦ (버튼 응답·팀 질문 공용). 25줄 상한."""
    ho = jg.get("best_odds", {}).get(jg["home"])
    ao = jg.get("best_odds", {}).get(jg["away"])
    matchup = (
        f"{jg['home']}({ho:.2f}) vs {jg['away']}({ao:.2f})"
        if ho and ao else f"{jg['home']} vs {jg['away']}"
    )
    st = jg.get("stats") or {}
    pitchers = ""
    if st.get("home_pitcher") or st.get("away_pitcher"):
        pitchers = f" | {st.get('home_pitcher') or '?'} vs {st.get('away_pitcher') or '?'}"
    label = f" [{jg['status_label']}]" if jg.get("status_label") else ""
    lines = [f"{jg['starts_at_kst']} {matchup}{pitchers}{label}"]

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
        probs.append(
            f"모델: {p3[0]:.0%}/{p3[1]:.0%}/{p3[2]:.0%}" if p3 else f"모델: {jg['p_model']:.1%}"
        )
    else:
        probs.append("모델: 무효(데이터 없음)")
    if jg.get("p_claude") is not None:
        probs.append(f"Claude: {jg['p_claude']:.0%}")
    lines.append(". ".join(probs) + ".")

    eps = jg.get("expert_picks") or []
    if eps:
        for ep in eps[:3]:
            rec = f" (전적 {ep['record']})" if ep.get("record") else " (전적 미상)"
            reason = f" — {ep['reasoning'][:150]}" if ep.get("reasoning") else ""
            lines.append(f"전문가: [{ep.get('site', '?')}] {ep.get('expert', '?')}: {ep['pick']}{reason}{rec}")
    else:
        lines.append("전문가: 전문가 픽 미수집")

    news_hits = _team_news_lines(news or "", jg["home"], jg["away"])
    lines.append("속보(Grok): " + (news_hits[0].strip()[:200] if news_hits else "특이사항 없음"))
    for note in jg.get("breaking_changes", []) or []:
        lines.append(f"🔄 {note[:150]}")
    if jg.get("verdict"):
        v = jg["verdict"]
        lines.append(f"판단: {v[:600]}" + ("…" if len(v) > 600 else ""))
        if jg.get("judge_confidence"):
            tag = {"high": "높음", "medium": "보통", "low": "낮음(참고만)"}
            second = " · 2차 검증 반영" if jg.get("second_opinion") else ""
            lines.append(f"신뢰도: {tag.get(jg['judge_confidence'], '?')}{second}")
    return "\n".join(lines[:25])


def render_news(analysis: dict) -> str:
    """📰 부상·속보 섹션 — 15줄 상한."""
    news = (analysis.get("news") or "").strip()
    if not news:
        return "수집된 속보가 없습니다."
    return "\n".join(news.splitlines()[:15])


def render_sources(analysis: dict) -> str:
    """📎 출처 — '- 사이트명: URL' 플레인 텍스트."""
    sources = analysis.get("sources") or []
    if not sources:
        return "이번 분석에 수집된 출처가 없습니다."
    return "\n".join(f"- {s['site']}: {s['url']}" for s in sources[:30])


def default_date(sport: str) -> str:
    return mlb_slate_date() if sport == "mlb" else today_kst()


def _mock_card(analysis: dict) -> str:
    games = [g for g in analysis["games"] if g["status"] == "scheduled"]
    picks = analysis["picks"]
    recommended = [p for p in picks if p.get("recommended")]
    lines = [f"📌 {analysis['date']} {analysis['sport'].upper()} {len(analysis['games'])}경기"]
    scored = [g for g in games if g.get("p_market") is not None and g.get("model_valid")]
    if scored:
        surest = min(scored, key=lambda g: abs(g["p_model"] - g["p_market"]))
        disputed = max(scored, key=lambda g: abs(g["p_model"] - g["p_market"]))
        lines.append(
            f"확신도 최고: {surest['home']} vs {surest['away']} — "
            f"모델 {surest['p_model']:.0%} vs 시장 {surest['p_market']:.0%} 수렴")
        lines.append(
            f"논쟁: {disputed['home']} vs {disputed['away']} — "
            f"모델 {disputed['p_model']:.0%} vs 시장 {disputed['p_market']:.0%} 괴리")
    for g in games:
        if g.get("breaking_note"):
            lines.append(g["breaking_note"])
    if analysis.get("parlay_rebuilt_note"):
        lines.append(analysis["parlay_rebuilt_note"])
    lines.append("")
    lines.append("🎯 오늘의 추천")
    if recommended:
        for p in recommended:
            opp = p["away"] if p["side"] == p["home"] else p["home"]
            stake = f" (권장 {p['stake_krw']:,}원)" if p.get("stake_krw") else ""
            lines.append(f"· {p['side']} 승 @{p['odds']:.2f} — vs {opp}, p={p['p']:.0%} EV{p['ev']:+.1%}{stake}")
        for i, pl in enumerate(analysis.get("parlays", [])[:3], 1):
            names = "+".join(leg["pick"].split(":", 1)[1] for leg in pl["legs"])
            lines.append(f"조합 {i}: {names} @{pl['odds']:.2f} (적중률 {pl['p']:.0%})")
        if analysis.get("parlays"):
            lines.append("⚠️ 조합은 고분산 — 단식 권장액의 절반 이하 소액만")
    else:
        lines.append("오늘은 기준(EV +5%↑)을 넘는 픽 없음 — 관망 권장")
    return "\n".join(lines[:20])


async def generate_card(analysis: dict) -> str:
    """결론 카드 생성 — Sonnet. 키 없으면 결정적 목 카드."""
    settings = get_settings()
    if settings.mock_judge:
        return _mock_card(analysis)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    payload = {k: analysis[k] for k in
               ("date", "sport", "mode", "picks", "parlays")}
    payload["parlay_rebuilt_note"] = analysis.get("parlay_rebuilt_note")
    payload["games"] = [
        {k: g.get(k) for k in ("game_id", "home", "away", "league", "starts_at_kst",
                               "status", "p_model", "model_valid", "p_market",
                               "p_claude", "judge_confidence", "breaking_note", "verdict")}
        for g in analysis["games"]
    ]
    try:
        response = await client.messages.create(
            model=settings.report_model,
            max_tokens=16000,
            system=CARD_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
        )
    except anthropic.APIStatusError as exc:
        if is_quota_error(exc.status_code, str(exc)):
            logger.error("[pipeline] card quota exhausted — falling back to template")
            await notify_quota("anthropic(report)", str(exc))
            return _mock_card(analysis)
        raise
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        logger.warning("[pipeline] card model returned no text (stop_reason=%s)", response.stop_reason)
        return _mock_card(analysis)
    return text


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
        jg["excluded_picks"] = v.get("excluded_picks", [])
        change_txt = "; ".join(jg.get("breaking_changes", []))[:120]
        old_txt = f"{old_p:.0%}" if old_p is not None else "?"
        jg["breaking_note"] = (
            f"🔄 속보 반영: {change_txt} → p_claude {old_txt}→{v['p_claude']:.0%}"
            + (", 패스로 전환" if jg["judge_pass"] else "")
        )

    picks_out, parlays, _reco = _compute_picks(settings, analysis["games"], analysis["sport"])
    analysis["picks"], analysis["parlays"] = picks_out, parlays
    flipped = old_reco - {p["pick"] for p in picks_out if p.get("recommended")}
    if flipped & old_parlay_legs:
        analysis["parlay_rebuilt_note"] = (
            "⚠️ 속보로 판정이 뒤집힌 픽이 기존 조합에 포함되어 있어 조합을 재구성했습니다."
        )
    logger.info("[pipeline] re-judged %d games after breaking news", len(affected))
    return analysis


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
    analysis = await build_analysis(pool, sport, date, progress=progress)
    await (progress or _noop_progress)(4, 4, "결론 카드 작성")
    try:
        card = await generate_card(analysis)
    except ApiQuotaError as exc:
        logger.error("[pipeline] card quota exhausted — template fallback: %s", exc)
        await notify_quota(exc.service, exc.detail)
        card = _mock_card(analysis)
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
