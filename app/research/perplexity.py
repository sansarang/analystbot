"""Perplexity sonar-pro 딥서치 — 전문가 픽 수집 → expert_picks 저장.

응답의 수치(배당 등)는 신뢰하지 않는다. 배당은 odds_snapshots(API)에서 붙인다.
JSON 파싱 실패 시 1회 재요청.
"""

import json
import logging
import re

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings
from app.research.normalize import normalize_pick

logger = logging.getLogger(__name__)

# 종목별 소스 목록 — 야구는 미국 사이트, 축구는 유럽/글로벌 사이트가 픽을 낸다.
SPORT_SOURCES = {
    "mlb": "Covers, RotoWire, Athlon Sports, Dimers, and SBR (Sportsbook Review)",
    "soccer": "SportsGambler, MightyTips, Sports Mole, Dimers, Forebet, and WhoScored",
}

MINOR_LEAGUE_FALLBACK = """
If those sites have no picks for a match (common for minor leagues like the Danish Superliga or J1 League), search generally for "<league name> <home team> vs <away team> prediction" and use any reputable prediction site you find — include its real URL.
For K League 1 matches, search KOREAN sources instead: "K리그 분석", "K리그 예상", 네이버 스포츠, 스포츠조선 등 — cite their real URLs.
For Danish Superliga, J1 League and K League matches you MUST also find and include each team's LAST 5 MATCH RESULTS and CURRENT LEAGUE POSITION — put them in the "home_form"/"away_form"/"home_rank"/"away_rank" fields. This is mandatory, not optional."""

PROMPT = """Find published expert picks for these {league} games on {date} (UTC), focusing on {sources}:

{games_block}
{fallback}
Output ONLY a JSON array (no prose), one object per pick:
[{{"expert": "...", "site": "...", "source_url": "...", "game": "<away> @ <home>", "pick": "...", "reasoning": "...", "record": "...", "home_form": "WDLWW or null", "away_form": "...", "home_rank": 3, "away_rank": 9, "predicted_score": "2-1 or null"}}]
Include "home_form"/"away_form" (last 5 results, most recent first) and "home_rank"/"away_rank" (league table position) whenever the source or your search provides them. Include "predicted_score" when the site publishes one.
"pick" must be one of: "<team> ML", "<team> +/-<line>", "Over <line>", "Under <line>".
"reasoning" MUST be written in KOREAN (한국어로 근거를 요약·번역하라; 선수·팀 이름만 원어 허용). Do not output English sentences in "reasoning"."""

RETRY_SUFFIX = "\n\nYour previous answer was not parseable JSON. Return ONLY the JSON array, nothing else."


def normalize_response(raw: dict) -> dict:
    """Sonar/Agent 응답을 공통 {choices:[{message:{content}}], citations:[...]} 형태로.

    Agent API는 typed output 배열(`{"type": "message", "content":[{"text": ...}]}`,
    `{"type": "search_results", "results":[{"url": ...}]}`)을 돌려준다 —
    호출부가 응답 형태에 의존하지 않도록 여기서 한 겹 흡수한다.
    """
    if not isinstance(raw, dict) or "output" not in raw:
        return raw
    text_parts: list[str] = []
    citations: list[str] = list(raw.get("citations") or [])
    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("text"):
                    text_parts.append(str(block["text"]))
                elif isinstance(block, str):
                    text_parts.append(block)
        elif item.get("type") == "search_results":
            citations += [
                r["url"] for r in item.get("results") or []
                if isinstance(r, dict) and r.get("url")
            ]
    return {
        "choices": [{"message": {"role": "assistant", "content": "\n".join(text_parts)}}],
        "citations": list(dict.fromkeys(citations)),
    }


class PerplexityClient(BaseAPIClient):
    """Perplexity 클라이언트 — 엔드포인트·모델은 config에서 주입(마이그레이션 대비).

    레이트리밋 방어: 동시 실행 pplx_max_concurrency(기본 2), 요청 간 최소 간격
    pplx_min_interval(기본 1.5s), 429는 Retry-After 우선 + 2s→6s→15s 3회 재시도.

    2026-09-27 Sonar Chat Completions 종료 → PPLX_API_MODE=agent 로 전환하면
    {"preset", "input"} 요청 + typed output 응답을 쓰고, 호출부는 그대로 둔다.
    """

    name = "perplexity"
    timeout = 60.0
    rate_limit_backoff = (2.0, 6.0, 15.0)

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        super().__init__(settings.mock_perplexity if mock is None else mock)
        self.api_key = settings.pplx_api_key
        self.base_url = settings.pplx_base_url
        self.mode = settings.pplx_api_mode
        self.model = settings.pplx_model
        self.agent_preset = settings.pplx_agent_preset
        self.chat_path = settings.pplx_chat_path
        self.agent_path = settings.pplx_agent_path
        self.max_concurrency = settings.pplx_max_concurrency
        self.min_interval = settings.pplx_min_interval
        self.calls = 0   # 실제 발생 콜 수 (재요청 포함) — 일 상한 집계용

    async def chat(self, prompt: str) -> dict:
        """프롬프트 1콜 → Sonar 형태({choices, citations})로 정규화해 반환."""
        if self.mock:
            return self.load_mock("perplexity_picks.json")
        self.calls += 1
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.mode == "agent":
            raw = await self._post(
                self.agent_path, headers=headers,
                json_body={"preset": self.agent_preset, "input": prompt},
            )
        else:
            raw = await self._post(
                self.chat_path, headers=headers,
                json_body={"model": self.model,
                           "messages": [{"role": "user", "content": prompt}]},
            )
        return normalize_response(raw)


def extract_json_array(content: str) -> list[dict]:
    m = re.search(r"```json\s*(\[.*?\])\s*```", content, re.S)
    if not m:
        m = re.search(r"(\[.*\])", content, re.S)
    if not m:
        raise ValueError("no JSON array found in response")
    return json.loads(m.group(1))


# ⚠️ 미사용 — 실운영 경로는 deep_research_game의 응답에 expert_picks가 함께 온다.
#    (2026-08-25 확인: app/ 안에 호출처 없음. 테스트만 참조한다.)
#    별도 슬레이트 조회가 필요해지면 반드시 `_record_call`로 쿼터에 집계할 것.
async def fetch_expert_picks(
    games: list[dict], date: str, league: str = "MLB", sport: str = "mlb",
    client: PerplexityClient | None = None,
) -> tuple[list[dict], list[str]]:
    """games: [{home, away}, ...] → (픽 리스트, citations). 파싱 실패 시 1회 재요청."""
    client = client or PerplexityClient()
    games_block = "\n".join(
        f"- {g['away']} @ {g['home']}"
        + (f" ({g['league']})" if g.get("league") else "")
        for g in games
    )
    prompt = PROMPT.format(
        league=league, date=date, games_block=games_block,
        sources=SPORT_SOURCES.get(sport, SPORT_SOURCES["mlb"]),
        fallback=MINOR_LEAGUE_FALLBACK if sport == "soccer" else "",
    )

    resp = await client.chat(prompt)
    try:
        picks = extract_json_array(resp["choices"][0]["message"]["content"])
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("[perplexity] JSON parse failed (%s) — re-requesting once", exc)
        resp = await client.chat(prompt + RETRY_SUFFIX)
        picks = extract_json_array(resp["choices"][0]["message"]["content"])
    return picks, resp.get("citations", [])


async def _latest_odds_for_pick(pool: asyncpg.Pool, game_id: int, pick: str) -> float | None:
    """정규화된 픽의 최신 배당을 odds_snapshots에서 조회 (없으면 None)."""
    parts = pick.split(":")
    market, side = parts[0], parts[1]
    return await pool.fetchval(
        """
        SELECT odds FROM odds_snapshots
        WHERE game_id = $1 AND market = $2 AND side = $3
        ORDER BY captured_at DESC LIMIT 1
        """,
        game_id, market, side,
    )


async def save_expert_picks(pool: asyncpg.Pool, picks: list[dict]) -> int:
    """픽을 games와 매칭·정규화해 expert_picks에 저장. 저장 행 수 반환."""
    saved = 0
    for p in picks:
        try:
            away, home = (s.strip() for s in p["game"].split("@"))
        except (KeyError, ValueError):
            logger.warning("[perplexity] unmatchable game field: %r", p.get("game"))
            continue
        row = await pool.fetchrow(
            "SELECT id, home, away FROM games WHERE home = $1 AND away = $2", home, away
        )
        if row is None:
            logger.warning("[perplexity] no game in DB for %s @ %s", away, home)
            continue
        normalized = normalize_pick(p.get("pick", ""), row["home"], row["away"])
        if normalized is None:
            logger.warning("[perplexity] unparseable pick: %r", p.get("pick"))
            continue
        odds = await _latest_odds_for_pick(pool, row["id"], normalized)
        result = await pool.execute(
            """
            INSERT INTO expert_picks (game_id, expert, site, source_url, pick,
                                      reasoning, record, odds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (game_id, expert, site, pick) DO NOTHING
            """,
            row["id"], p.get("expert", "unknown"), p.get("site", "unknown"),
            p.get("source_url"), normalized, p.get("reasoning"), p.get("record"), odds,
        )
        if result.endswith("1"):
            saved += 1
    logger.info("[perplexity] saved %d expert picks", saved)
    return saved


async def ask_json(prompt: str, *, max_tokens: int = 900) -> dict | None:
    """[변수 평의회 2026-09-06] 조사 1콜 → JSON dict. 실패하면 None.

    🔴 **요약문을 저장하지 않는다.** 호출부가 JSON 필드만 쓴다.
    ⚠️ 예외를 밖으로 던지지 않는다 — 조사 실패가 판정을 막으면 안 된다.
       크레딧 소진(401 insufficient_quota)도 여기서 조용히 None 이 되고,
       호출부가 무료 사슬로 축소 조사한다.
    """
    import os

    import httpx

    from app.config import get_settings

    s = get_settings()
    key = (s.pplx_api_key or os.environ.get("PPLX_API_KEY") or "").strip()
    if not key:
        logger.info("[pplx] PPLX_API_KEY 없음 — 조사 생략")
        return None
    if "perplexity" in (s.disabled_providers or "").lower():
        logger.info("[pplx] DISABLED_PROVIDERS 로 차단됨 — 조사 생략")
        return None
    url = f"{s.pplx_base_url.rstrip('/')}{s.pplx_chat_path}"
    body = {"model": s.pplx_model or "sonar",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": int(max_tokens), "temperature": 0}
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(url, json=body,
                             headers={"Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json"})
        if r.status_code != 200:
            logger.warning("[pplx] 조사 HTTP %d — %s", r.status_code,
                           r.text[:160])
            return None
        data = normalize_response(r.json())
        txt = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        logger.warning("[pplx] 조사 실패: %s", str(exc)[:160])
        return None
    from app.engine.matchup import parse_json_object

    got = parse_json_object(txt or "")
    return got if isinstance(got, dict) else None
