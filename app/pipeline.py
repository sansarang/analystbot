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
    # 4) Claude 판정 — 시작 전 경기만. 크레딧 소진 시 알림 후 목 판정 폴백 (크래시 금지)
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
    p_claude_by_id = {g["game_id"]: g for g in verdict["games"]}

    # 5) 사이드별 앙상블 → EV/켈리 → 검증 플래그·판정 제외 → 모드 적용
    mode = MODES.get(settings.report_mode, MODES["live_conservative"])
    stake_krw = int(settings.bankroll_krw * mode["flat_pct"]) if mode["staking"] == "flat" else None

    def blend(p_model_s: float | None, p_market_s: float, p_claude_s: float) -> float:
        """모델 무효면 모델 가중치를 빼고 시장+Claude만으로 재정규화."""
        if p_model_s is None:
            w = settings.ensemble_w_market + settings.ensemble_w_claude
            return (settings.ensemble_w_market * p_market_s
                    + settings.ensemble_w_claude * p_claude_s) / w
        return ensemble(
            p_model_s, p_market_s, p_claude_s,
            settings.ensemble_w_model, settings.ensemble_w_market, settings.ensemble_w_claude,
        )

    picks_out = []
    for jg in judge_games:
        v = p_claude_by_id.get(jg["game_id"])
        if v is not None:
            jg["p_claude"] = v["p_claude"]
            jg["verdict"] = v["verdict"]
            jg["excluded_picks"] = v["excluded_picks"]
            jg["judge_pass"] = bool(v.get("pass_recommended"))
            jg["judge_confidence"] = v.get("confidence", "medium")
        if jg["status"] != "scheduled":
            continue  # 이미 시작/종료된 경기는 분석 대상 아님
        market = jg["market_probs"]
        if v is None or not market or jg["home"] not in market or jg["away"] not in market:
            continue

        # 사이드별 확률: 축구는 무승부 질량 때문에 1-p_home ≠ p_away — 시장 3-way 기준
        p_draw_m = market.get("Draw", 0.0)
        p_claude_home = v["p_claude"]
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
            judge_excluded = f"판정: 패스 권장 — {v['verdict'][:120]}"
        elif jg.get("judge_confidence") == "low":
            judge_excluded = f"판정: 저신뢰 — {v['verdict'][:120]}"

        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "starts_at_kst": jg["starts_at_kst"], "pick": pick, "side": side,
            "p": round(p_side, 4), "p_claude": v["p_claude"],
            "model_valid": jg["model_valid"],
            "odds": odds, "ev": round(pick_ev, 4), "kelly": round(pick_kelly, 4),
            "stake_krw": stake_krw,
            "verdict": v["verdict"], "excluded_picks": v["excluded_picks"],
            "flags": flags, "judge_excluded": judge_excluded,
        }
        picks_out.append(entry)
        if flags:
            logger.warning(
                "[pipeline] suspicious pick flagged — %s @ %s | %s odds=%.2f: %s",
                jg["away"], jg["home"], pick, odds, "; ".join(flags),
            )

    picks_out.sort(key=lambda x: x["ev"], reverse=True)
    # 추천 = 플래그·판정제외 없음 + EV 임계 통과 + 모드별 픽 수 상한
    recommended = [
        p for p in picks_out
        if not p["flags"] and not p["judge_excluded"] and p["ev"] > settings.ev_threshold
    ][: mode["max_picks"]]
    for p in picks_out:
        p["recommended"] = p in recommended
    legs = []
    for p in recommended:
        await pool.execute(
            """
            INSERT INTO predictions (game_id, pick, model_p, odds, ev, kelly)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            p["game_id"], p["pick"], p["p"], p["odds"], p["ev"], p["kelly"],
        )
        legs.append({"game_id": p["game_id"], "pick": p["pick"],
                     "p": p["p"], "odds": p["odds"], "ev": p["ev"]})

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
    return {
        "sport": sport, "date": date,
        "mode": {"name": settings.report_mode, **mode, "stake_krw": stake_krw,
                 "bankroll_krw": settings.bankroll_krw},
        "games": judge_games, "picks": picks_out,
        "parlays": best_parlays(legs) if mode["allow_parlays"] else [],
        "news": news, "sources": sources, "verdict": verdict,
    }


# ---------------------------------------------------------------- 리포트 생성

REPORT_SYSTEM = """너는 20년 경력의 스포츠 베팅 수석 애널리스트다. 입력 JSON(경기·기록·배당·모델확률·전문가픽·속보)만을 근거로 심층 분석을 작성한다. 다음 원칙을 반드시 지켜라.

[데이터 규율]
1. 입력에 없는 수치를 만들어내지 마라. 없는 정보는 "미수집"으로 정직하게 표기한다.
2. 전문가 픽의 수치가 입력 stats와 모순되면 그 픽을 제외하고 사유를 남겨라.
3. 모든 주장에는 근거 수치를 병기하라. "우세"라고만 쓰는 것은 금지 — "원정 ERA 4.31 vs 홈 2.32라 우세"처럼 쓴다.

[분석 구조 — 경기당 이 순서로]
① 스토리라인 한 줄: 이 경기를 특별하게 만드는 맥락을 먼저 잡아라 (이적 후 첫 등판, 데뷔전, 연승/연패 충돌, 순위 경쟁, 개막전 등). 없으면 생략.
② 전력 비교: 양 팀 최근 폼·핵심 선수·홈원정 스플릿을 수치로. 야구는 선발투수 대결이 중심, 축구는 최근 5경기 득실과 상대전적이 중심.
③ 3자 대조: 시장(배당 암시확률) vs 모델 확률 vs 전문가 컨센서스를 나란히 놓고, 셋이 일치하는지 갈리는지를 명시하라. 갈리는 경기는 "왜 갈리는지"가 분석의 핵심이다 — 각 진영의 근거를 대조하라.
④ 전문가 인용: "[사이트] 이름(전적): 픽 — 근거" 형식의 한국어 1~2줄. 전적이 좋은 전문가(적중률 60%+ 또는 ROI 플러스)의 픽은 무게를 실어 다루고, 전적이 나쁜 전문가는 픽 자체보다 인용된 데이터만 취하라. 전적 미상이면 "(전적 미상)"으로 표기. expert_picks 배열에 없는 전문가·픽 생성 금지 — 비어 있으면 "전문가 픽 미수집".
⑤ 판단: 반드시 두 가지를 분리해서 결론 내라 — (a) 누가 이길 것인가 (b) 배당 대비 가치가 있는가. "이길 확률은 높지만 배당 1.45라 가치는 없다" 같은 결론이 정상이며 자주 나와야 한다. EV가 +20%를 넘으면 가치가 아니라 데이터 오류를 의심하고 플래그를 세워라.
⑥ 저분산 대안: 승패 단식이 고분산이면 핸디캡(+1.5 런라인, 더블찬스)이나 토탈 중 근거가 있는 저분산 마켓을 하나 제시하라.
⑦ 리스크 한 줄: 이 판단이 틀린다면 무엇 때문일지를 스스로 명시하라 (표본 부족, 불펜 소모, 로테이션 피로, 신인 변동성 등).

[문체]
- 한국어. 팀명은 한국어 표기 통일. 시각은 KST.
- 판단은 단정적이되 근거와 함께. 얼버무리지 마라. 단, 데이터가 반반이면 "저신뢰 경기, 패스 권장"이라고 정직하게 써라.
- 확신도가 가장 높은 경기와 가장 논쟁적인 경기를 리포트 서두에 한 줄씩 뽑아라.

[모드 준수 — 입력 mode 객체를 반드시 따른다]
- staking이 "flat"이면 켈리 % 표기 금지. 각 추천 픽에 "스테이크: {stake_krw:,}원 (자금 {flat_pct%})" 원화 플랫 스테이크로 표기한다.
- allow_parlays가 false면 "추천 조합"(파레이) 섹션 자체를 출력하지 않는다.
- 추천 픽은 recommended=true인 픽만, 최대 max_picks개.
- judge_excluded가 있는 픽은 "■ 판정 제외" 섹션에 사유와 함께 표기하고 추천하지 않는다.

[출력 형식]
- 정확히 3개 파트, 파트 사이에 구분자 줄 <<<PART>>> 단독 줄. 각 파트 3800자 이내의 텔레그램 플레인 텍스트.
- 파트1: 서두(확신도 최고 경기 1줄 + 가장 논쟁적인 경기 1줄) → "■ 오늘 경기 N건" 목록(KST 시각, status_label 있는 경기는 '[진행 중]'/'[종료]' 라벨 — 분석 제외 명시) → "■ 추천 픽"(recommended=true만: 확률·배당·EV·모드별 스테이크) → "■ 판정 제외"(judge_excluded 픽: 사유) → flags 있는 픽은 "⚠️ 데이터 검증 필요" 섹션에 분리(추천 금지) → parlays가 있을 때만 "■ 추천 조합".
- 파트2: 시작 전 경기마다 [분석 구조] ①~⑦ 순서로 작성. EV 상위 픽 경기와 논쟁적 경기는 전체(①~⑦), 나머지는 ②③⑤만 압축 3줄 이내.
- 파트3: "■ 속보 요약" + "📎 출처"(sources의 사이트명과 URL 그대로 나열) + [출력 마무리].

[출력 마무리]
- 마지막에 반드시: 오늘 픽들의 전제(예: "n일차 표본 기준"), 그리고 "※ 분석 정보용입니다. 베팅 손실 책임은 이용자 본인에게 있습니다." 고지."""


def _team_news_lines(news: str, home: str, away: str) -> list[str]:
    keys = {home.lower(), away.lower(), home.split()[-1].lower(), away.split()[-1].lower()}
    return [ln for ln in news.splitlines() if any(k in ln.lower() for k in keys)]


def render_game_section(jg: dict, news: str = "") -> str:
    """경기 1건 심층 템플릿 (목 리포트·특정 팀 질문 응답 공용)."""
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
        probs.append(f"시장: 홈 암시 {jg['p_market']:.0%}")
    else:
        probs.append("시장: 배당 미수집")
    probs.append(f"모델: {jg['p_model']:.1%}")
    if jg.get("p_claude") is not None:
        probs.append(f"Claude: {jg['p_claude']:.1%}")
    lines.append(". ".join(probs) + ".")

    eps = jg.get("expert_picks") or []
    if eps:
        for ep in eps[:4]:
            rec = f" (전적 {ep['record']})" if ep.get("record") else ""
            reason = f" — {ep['reasoning']}" if ep.get("reasoning") else ""
            lines.append(f"전문가: [{ep.get('site', '?')}] {ep.get('expert', '?')}: {ep['pick']}{reason}{rec}")
    else:
        lines.append("전문가: 전문가 픽 미수집")

    news_hits = _team_news_lines(news or "", jg["home"], jg["away"])
    lines.append("속보(Grok): " + (news_hits[0].strip() if news_hits else "특이사항 없음"))
    if jg.get("verdict"):
        lines.append(f"판단: {jg['verdict']}")
    return "\n".join(lines)


def _mock_report(analysis: dict) -> str:
    games, picks = analysis["games"], analysis["picks"]
    mode = analysis.get("mode", {})
    recommended = [p for p in picks if p.get("recommended")]
    judge_excluded = [p for p in picks if p.get("judge_excluded")]
    flagged = [p for p in picks if p.get("flags")]

    def stake_line(p: dict) -> str:
        if mode.get("staking") == "flat" and p.get("stake_krw"):
            return f"스테이크 {p['stake_krw']:,}원(자금 {mode.get('flat_pct', 0):.0%})"
        return f"켈리 {p['kelly'] * 100:.1f}%"

    # 파트1 — 일정 + 픽 (+모드에 따라 조합)
    p1 = [f"[AnalystBot] {analysis['date']} {analysis['sport'].upper()} 분석 "
          f"(KST 기준, 모드: {mode.get('name', '-')})", ""]
    p1.append(f"■ 오늘 경기 {len(games)}건 (시작 전 경기만 분석 대상)")
    for g in games:
        label = f" [{g['status_label']}]" if g.get("status_label") else ""
        p1.append(f"  {g['starts_at_kst']}  {g['away']} @ {g['home']}{label}")
    p1 += ["", f"■ 추천 픽 (최대 {mode.get('max_picks', '-')}건)"]
    if recommended:
        for p in recommended:
            p1.append(
                f"  {p['side']} 승 (vs {p['away'] if p['side'] == p['home'] else p['home']})"
                f" | p={p['p']:.2f} 배당={p['odds']:.2f} EV={p['ev']:+.3f} {stake_line(p)}"
            )
    else:
        p1.append("  기준(EV>+3%)을 넘는 추천 픽이 없습니다.")
    if judge_excluded:
        p1 += ["", "■ 판정 제외"]
        for p in judge_excluded:
            p1.append(f"  {p['side']} (EV={p['ev']:+.3f}) — {p['judge_excluded']}")
    if flagged:
        p1 += ["", "⚠️ 데이터 검증 필요 (추천 제외)"]
        for p in flagged:
            p1.append(f"  {p['side']} 배당={p['odds']:.2f} EV={p['ev']:+.3f} — {'; '.join(p['flags'])}")
    if mode.get("allow_parlays"):
        p1 += ["", "■ 추천 조합 (파레이)"]
        if analysis["parlays"]:
            for i, pl in enumerate(analysis["parlays"], 1):
                names = " + ".join(leg["pick"].split(":", 1)[1] for leg in pl["legs"])
                p1.append(f"  {i}) {names} | 배당 {pl['odds']:.2f} EV {pl['ev']:+.3f}")
        else:
            p1.append("  EV 플러스 레그가 부족해 추천 조합이 없습니다.")

    # 파트2 — 경기별 심층
    p2 = ["■ 경기별 심층 분석"]
    for g in games:
        if g.get("status") != "scheduled":
            continue
        p2 += ["", render_game_section(g, analysis.get("news", "")), "─" * 12]

    # 파트3 — 속보 + 출처
    p3 = ["■ 속보 요약"]
    p3 += [f"  {ln}" for ln in (analysis.get("news") or "(속보 없음)").splitlines()[:8]]
    p3 += ["", "📎 출처"]
    if analysis.get("sources"):
        for s in analysis["sources"]:
            p3.append(f"  [{s['site']}] {s['url']}")
    else:
        p3.append("  (이번 분석에 수집된 전문가 픽 출처 없음)")
    p3 += ["", "※ 분석 정보용입니다. 베팅 손실 책임은 이용자 본인에게 있습니다."]

    return SECTION_SEP.join(["\n".join(p1), "\n".join(p2), "\n".join(p3)])


async def generate_report(analysis: dict) -> str:
    settings = get_settings()
    if settings.mock_judge:  # ANTHROPIC_API_KEY 없으면 템플릿 리포트
        return _mock_report(analysis)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    payload = {k: analysis[k] for k in
               ("date", "sport", "mode", "games", "picks", "parlays", "news", "sources")}
    try:
        response = await client.messages.create(
            model=settings.report_model,
            # sonnet-5는 adaptive thinking 기본 활성 — max_tokens가 thinking+본문 합산 상한
            max_tokens=16000,
            system=REPORT_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
        )
    except anthropic.APIStatusError as exc:
        if is_quota_error(exc.status_code, str(exc)):
            logger.error("[pipeline] report quota exhausted — falling back to template")
            await notify_quota("anthropic(report)", str(exc))
            return _mock_report(analysis)
        raise
    text = "".join(b.text for b in response.content if b.type == "text")
    if not text.strip():
        logger.warning(
            "[pipeline] report model returned no text (stop_reason=%s) — template fallback",
            response.stop_reason,
        )
        return _mock_report(analysis)
    return text


# ---------------------------------------------------------------- 진입점

def mlb_slate_date() -> str:
    """MLB 슬레이트 날짜 = 미국 동부 기준 오늘 (KST 새벽·아침엔 전날 미국 경기)."""
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


async def run_pipeline(
    pool: asyncpg.Pool,
    redis: aioredis.Redis,
    sport: str = "mlb",
    date: str | None = None,
    force_refresh: bool = False,
    progress=None,
) -> str:
    settings = get_settings()
    # 날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 표기는 항상 KST.
    date = date or (mlb_slate_date() if sport == "mlb" else today_kst())
    cache_key = f"report:{sport}:{date}"
    if not force_refresh:
        cached = await redis.get(cache_key)
        if cached:
            logger.info("[pipeline] cache hit: %s", cache_key)
            return cached
    analysis = await build_analysis(pool, sport, date, progress=progress)
    # 특정 팀 질문이 슬레이트 캐시에서 경기를 추출할 수 있도록 분석 데이터도 캐시
    await redis.set(
        f"analysis:{sport}:{date}",
        json.dumps(analysis, ensure_ascii=False, default=str),
        ex=settings.report_cache_ttl,
    )
    await (progress or _noop_progress)(4, 4, "리포트 작성")
    try:
        report = await generate_report(analysis)
    except ApiQuotaError as exc:
        logger.error("[pipeline] report quota exhausted — template fallback: %s", exc)
        await notify_quota(exc.service, exc.detail)
        report = _mock_report(analysis)
    if settings.report_banner:
        report = f"{settings.report_banner}\n\n{report}"
    await redis.set(cache_key, report, ex=settings.report_cache_ttl)
    return report


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
