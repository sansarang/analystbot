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
            # API-Football 플랜이 현재 시즌 미지원 → Odds API 이벤트로 일정 폴백
            from app.collectors.odds import upsert_games_from_odds_events

            ext_ids = await upsert_games_from_odds_events(pool, date)
        stats_coro = _collect_soccer_stats(fb)
        league = "soccer (EPL·J1·수페르리가)"

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
            "SELECT expert, site, source_url, pick, reasoning, record "
            "FROM expert_picks WHERE game_id = $1",
            g["id"],
        )
        judge_games.append({
            "game_id": g["id"],
            "home": g["home"], "away": g["away"],
            "starts_at_kst": kst_hhmm(g["starts_at"]),
            "status": g["status"],
            "status_label": STATUS_LABELS.get(g["status"], ""),
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

    # 5) 앙상블 → EV/켈리 → 검증 플래그 → predictions 적재 + 파레이
    legs, picks_out = [], []
    for jg in judge_games:
        v = p_claude_by_id.get(jg["game_id"])
        if v is not None:
            jg["p_claude"] = v["p_claude"]
            jg["verdict"] = v["verdict"]
            jg["excluded_picks"] = v["excluded_picks"]
        if jg["status"] != "scheduled":
            continue  # 이미 시작/종료된 경기는 분석 대상 아님
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

        # 데이터 검증 가드: 정상 시장에서 나오기 힘든 수치는 추천/파레이/predictions 제외
        implied = implied_prob(odds)
        p_model_side = jg["p_model"] if side == jg["home"] else round(1 - jg["p_model"], 4)
        flags = []
        if pick_ev > EV_FLAG_MAX:
            flags.append(f"EV {pick_ev:+.1%} > +20% (배당 데이터 이상 의심)")
        if abs(p_model_side - implied) > MODEL_GAP_MAX:
            flags.append(
                f"모델 {p_model_side:.0%} vs 배당 암시 {implied:.0%} 괴리 >25%p"
            )

        entry = {
            "game_id": jg["game_id"], "home": jg["home"], "away": jg["away"],
            "starts_at_kst": jg["starts_at_kst"], "pick": pick, "side": side,
            "p": round(p_side, 4), "p_final_home": round(p_final, 4),
            "p_claude": v["p_claude"],
            "odds": odds, "ev": round(pick_ev, 4), "kelly": round(pick_kelly, 4),
            "verdict": v["verdict"], "excluded_picks": v["excluded_picks"],
            "flags": flags,
        }
        picks_out.append(entry)
        if flags:
            logger.warning(
                "[pipeline] suspicious pick flagged — %s @ %s | %s odds=%.2f: %s",
                jg["away"], jg["home"], pick, odds, "; ".join(flags),
            )
            continue
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
    sources, seen_urls = [], set()
    for jg in judge_games:
        for ep in jg.get("expert_picks", []):
            url = ep.get("source_url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append({"site": ep.get("site", "?"), "url": url})
    return {
        "sport": sport, "date": date,
        "games": judge_games, "picks": picks_out,
        "parlays": best_parlays(legs), "news": news,
        "sources": sources, "verdict": verdict,
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

[출력 형식]
- 정확히 3개 파트, 파트 사이에 구분자 줄 <<<PART>>> 단독 줄. 각 파트 3800자 이내의 텔레그램 플레인 텍스트.
- 파트1: 서두(확신도 최고 경기 1줄 + 가장 논쟁적인 경기 1줄) → "■ 오늘 경기 N건" 목록(KST 시각, status_label 있는 경기는 '[진행 중]'/'[종료]' 라벨 — 분석 제외 명시) → "■ EV 상위 픽"(flags가 빈 픽만: 확률·배당·EV·켈리) → flags 있는 픽은 "⚠️ 데이터 검증 필요" 섹션에 분리(추천 금지) → "■ 추천 조합"(parlays).
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
    clean = [p for p in picks if not p.get("flags")]
    flagged = [p for p in picks if p.get("flags")]

    # 파트1 — 일정 + 픽 + 조합
    p1 = [f"[AnalystBot] {analysis['date']} {analysis['sport'].upper()} 분석 (KST 기준)", ""]
    p1.append(f"■ 오늘 경기 {len(games)}건 (시작 전 경기만 분석 대상)")
    for g in games:
        label = f" [{g['status_label']}]" if g.get("status_label") else ""
        p1.append(f"  {g['starts_at_kst']}  {g['away']} @ {g['home']}{label}")
    p1 += ["", "■ EV 상위 픽"]
    if clean:
        for p in clean[:5]:
            p1.append(
                f"  {p['side']} 승 (vs {p['away'] if p['side'] == p['home'] else p['home']})"
                f" | p={p['p']:.2f} 배당={p['odds']:.2f} EV={p['ev']:+.3f} 켈리={p['kelly'] * 100:.1f}%"
            )
    else:
        p1.append("  기준(EV>+3%)을 넘는 픽이 없습니다.")
    if flagged:
        p1 += ["", "⚠️ 데이터 검증 필요 (추천 제외)"]
        for p in flagged:
            p1.append(f"  {p['side']} 배당={p['odds']:.2f} EV={p['ev']:+.3f} — {'; '.join(p['flags'])}")
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
    payload = {k: analysis[k] for k in ("date", "sport", "games", "picks", "parlays", "news")}
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
