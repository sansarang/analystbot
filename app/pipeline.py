"""파이프라인 오케스트레이터.

(일정+스탯 ∥ 배당 ∥ 딥서치) 병렬 수집 → 엔진 계산 → judge → 리포트 생성(Sonnet,
판정 JSON만 근거로 한국어) → Redis 30분 캐시.
"""

import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import asyncpg
import redis.asyncio as aioredis

from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer_games
from app.collectors.mlb import MLBClient, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds
from app.config import get_settings
from app.engine.consensus import consensus_scores, load_expert_weights
from app.engine.judge import Judge
from app.engine.parlay import best_parlays
from app.engine.value import devig, ensemble, ev, heuristic_model_prob, implied_prob, kelly
from app.research.grok import GrokClient
from app.research.perplexity import PerplexityClient, fetch_expert_picks, save_expert_picks

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def kst_hhmm(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%m/%d %H:%M")


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


async def _collect_soccer_stats(client: APIFootballClient) -> dict:
    """순위표 → 팀 승률(win/played). 축구는 투수 스탯 없음."""
    standings = await client.fetch_standings()
    win_pct: dict[str, float] = {}
    for entry in standings.get("response", []):
        for table in entry["league"].get("standings", []):
            for row in table:
                played = row["all"]["played"] or 1
                win_pct[row["team"]["name"]] = row["all"]["win"] / played
    return {"win_pct": win_pct, "era": {}}


async def _collect_research(
    pool: asyncpg.Pool, games: list[dict], date: str, league: str = "MLB"
) -> tuple[list[dict], str]:
    """딥서치는 보조 신호 — 실패(무효 키·타임아웃 등)해도 파이프라인은 계속 간다."""
    picks_task = fetch_expert_picks(games, date, league=league, client=PerplexityClient())
    news_task = GrokClient().live_briefing(games, date, league=league)
    picks_res, news_res = await asyncio.gather(picks_task, news_task, return_exceptions=True)

    if isinstance(picks_res, BaseException):
        logger.error("[pipeline] perplexity research failed, continuing without picks: %s", picks_res)
        picks: list[dict] = []
    else:
        picks, _citations = picks_res
        await save_expert_picks(pool, picks)

    if isinstance(news_res, BaseException):
        logger.error("[pipeline] grok briefing failed, continuing without news: %s", news_res)
        news = ""
    else:
        news = news_res
    return picks, news


async def _market_probs(pool: asyncpg.Pool, game_id: int, home: str, away: str) -> tuple[float | None, dict[str, float]]:
    """h2h 최신 스냅샷 → 북별 디빅 후 평균 홈 승률 + 사이드별 최고 배당."""
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
    home_probs = []
    for sides in by_book.values():
        if home in sides and away in sides:
            ph, _pa = devig([implied_prob(sides[home]), implied_prob(sides[away])])
            home_probs.append(ph)
    p_market = sum(home_probs) / len(home_probs) if home_probs else None
    return p_market, best_odds


# ---------------------------------------------------------------- 분석 본체

async def build_analysis(pool: asyncpg.Pool, sport: str, date: str) -> dict:
    settings = get_settings()

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
        stats_coro = _collect_soccer_stats(fb)
        league = "EPL"

    game_rows = await pool.fetch(
        """
        SELECT * FROM games
        WHERE sport = $1 AND ext_id = ANY($2::text[])
        ORDER BY starts_at
        """,
        sport, ext_ids,
    )
    games = [dict(r) for r in game_rows]

    # 2) 스탯 ∥ 배당 ∥ 딥서치 병렬 수집
    stats, _, (raw_picks, news) = await asyncio.gather(
        stats_coro,
        snapshot_odds(pool, sport, client=OddsClient()),
        _collect_research(pool, games, date, league),
    )

    # 3) 경기별 p_model / p_market / 전문가 컨센서스
    weights = await load_expert_weights(pool)
    judge_games = []
    for g in games:
        p_model = heuristic_model_prob(
            stats["win_pct"].get(g["home"], 0.5),
            stats["win_pct"].get(g["away"], 0.5),
            stats["era"].get(g["home_pitcher"]),
            stats["era"].get(g["away_pitcher"]),
        )
        p_market, best_odds = await _market_probs(pool, g["id"], g["home"], g["away"])
        pick_rows = await pool.fetch(
            "SELECT expert, pick, reasoning, record FROM expert_picks WHERE game_id = $1",
            g["id"],
        )
        judge_games.append({
            "game_id": g["id"],
            "home": g["home"], "away": g["away"],
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "p_model": round(p_model, 4),
            "p_market": round(p_market, 4) if p_market is not None else None,
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

    # 4) Claude 판정
    verdict = await Judge().judge({"date": date, "sport": sport,
                                   "games": judge_games, "breaking_news": news})
    p_claude_by_id = {g["game_id"]: g for g in verdict["games"]}

    # 5) 앙상블 → EV/켈리 → predictions 적재 + 파레이
    legs, picks_out = [], []
    for jg in judge_games:
        v = p_claude_by_id.get(jg["game_id"])
        if v is None or jg["p_market"] is None:
            continue
        p_final = ensemble(
            jg["p_model"], jg["p_market"], v["p_claude"],
            settings.ensemble_w_model, settings.ensemble_w_market, settings.ensemble_w_claude,
        )
        side, p_side = (jg["home"], p_final) if p_final >= 0.5 else (jg["away"], 1 - p_final)
        odds = jg["best_odds"].get(side)
        if not odds:
            continue
        pick = f"h2h:{side}"
        pick_ev = ev(p_side, odds)
        pick_kelly = kelly(p_side, odds, settings.kelly_fraction, settings.kelly_cap)
        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "starts_at_kst": jg["starts_at_kst"], "pick": pick, "side": side,
            "p": round(p_side, 4), "p_final_home": round(p_final, 4),
            "odds": odds, "ev": round(pick_ev, 4), "kelly": round(pick_kelly, 4),
            "verdict": v["verdict"], "excluded_picks": v["excluded_picks"],
        }
        picks_out.append(entry)
        if pick_ev > settings.ev_threshold:
            await pool.execute(
                """
                INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                jg["game_id"], pick, p_side, odds, pick_ev, pick_kelly,
            )
            legs.append({"game_id": jg["game_id"], "pick": pick,
                         "p": p_side, "odds": odds, "ev": pick_ev})

    picks_out.sort(key=lambda x: x["ev"], reverse=True)
    return {
        "sport": sport, "date": date,
        "games": judge_games, "picks": picks_out,
        "parlays": best_parlays(legs), "news": news,
        "verdict": verdict,
    }


# ---------------------------------------------------------------- 리포트 생성

REPORT_SYSTEM = """너는 스포츠 분석 리포트 작성자다. 입력 JSON(판정·계산 결과)만 근거로 한국어 리포트를 작성한다.
- 입력에 없는 수치를 만들어내지 않는다.
- 구성: ① 오늘 경기 목록(KST 시각) ② EV 상위 픽 (확률·배당·EV·켈리 비중) ③ 추천 조합(파레이) ④ 속보 요약 ⑤ 한 줄 주의 문구.
- 텔레그램 메시지용 플레인 텍스트, 이모지 절제, 4000자 이내."""


def _mock_report(analysis: dict) -> str:
    lines = [f"[AnalystBot] {analysis['date']} {analysis['sport'].upper()} 분석 (KST 기준)", ""]
    lines.append(f"■ 오늘 경기 {len(analysis['games'])}건")
    for g in analysis["games"]:
        lines.append(f"  {g['starts_at_kst']}  {g['away']} @ {g['home']}")
    top = analysis["picks"][:5]
    lines += ["", "■ EV 상위 픽"]
    if top:
        for p in top:
            lines.append(
                f"  {p['side']} 승 (vs {p['away'] if p['side'] == p['home'] else p['home']})"
                f" | p={p['p']:.2f} 배당={p['odds']:.2f} EV={p['ev']:+.3f} 켈리={p['kelly'] * 100:.1f}%"
            )
    else:
        lines.append("  기준(EV>+3%)을 넘는 픽이 없습니다.")
    lines += ["", "■ 추천 조합 (파레이)"]
    if analysis["parlays"]:
        for i, pl in enumerate(analysis["parlays"], 1):
            names = " + ".join(leg["pick"].split(":", 1)[1] for leg in pl["legs"])
            lines.append(f"  {i}) {names} | 배당 {pl['odds']:.2f} EV {pl['ev']:+.3f}")
    else:
        lines.append("  EV 플러스 레그가 부족해 추천 조합이 없습니다.")
    if analysis["news"]:
        lines += ["", "■ 속보", *[f"  {ln}" for ln in analysis["news"].splitlines()[:6]]]
    lines += ["", "※ 분석 정보용입니다. 베팅 손실 책임은 이용자 본인에게 있습니다."]
    return "\n".join(lines)


async def generate_report(analysis: dict) -> str:
    settings = get_settings()
    if settings.mock_judge:  # ANTHROPIC_API_KEY 없으면 템플릿 리포트
        return _mock_report(analysis)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    payload = {k: analysis[k] for k in ("date", "sport", "games", "picks", "parlays", "news")}
    response = await client.messages.create(
        model=settings.report_model,
        max_tokens=4000,
        system=REPORT_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
    )
    return next(b.text for b in response.content if b.type == "text")


# ---------------------------------------------------------------- 진입점

async def run_pipeline(
    pool: asyncpg.Pool,
    redis: aioredis.Redis,
    sport: str = "mlb",
    date: str | None = None,
    force_refresh: bool = False,
) -> str:
    settings = get_settings()
    date = date or today_kst()
    cache_key = f"report:{sport}:{date}"
    if not force_refresh:
        cached = await redis.get(cache_key)
        if cached:
            logger.info("[pipeline] cache hit: %s", cache_key)
            return cached
    analysis = await build_analysis(pool, sport, date)
    report = await generate_report(analysis)
    await redis.set(cache_key, report, ex=settings.report_cache_ttl)
    return report
