"""경기 단위 실시간 심층 리서치 — Perplexity sonar-pro, 전 경기 공통 "재료 조사".

체제 (2026-08-24 실시간 리서치 전환):
- 프리페치(04:00 KST)에서 전 경기 심층 리서치를 세마포어 동시 처리로 캐시.
- 신선도 게이트: 캐시 6시간 이내 & 킥오프 3시간 이상 남음 → 캐시 즉답.
  킥오프 3시간 이내 or 캐시 6시간 초과 → 재리서치. 실패 시 캐시 폴백("새벽 데이터 기준").
- 비용 가드: Perplexity 일 상한 60콜. 초과 시 게이트 보수화(재리서치 억제) + 카드 경고.
"""

import json
import logging
import re
from datetime import UTC, datetime

from app.config import get_settings
from app.research.perplexity import PerplexityClient

logger = logging.getLogger(__name__)

RESEARCH_FRESH_HOURS = 6      # 캐시 신선 기준
KICKOFF_GUARD_HOURS = 3       # 킥오프 임박 기준 — 이내면 무조건 재리서치
DAILY_RESEARCH_CAP = 60       # Perplexity 일 상한 (초과 시 캐시 기준)
RESEARCH_CONCURRENCY = 4      # 프리페치/일괄 재리서치 세마포어
CACHE_TTL = 36 * 3600
EST_COST_PER_CALL_USD = 0.01  # sonar-pro 대략 단가 (주간 비용 추정 로그용)

_SCHEMA_MLB = """{
 "home_recent_form": {"form": "WWLWL (최근 5경기, 최신부터)", "runs_avg": 4.2, "note": "최근 30일 좌/우완 상대 타선 성적 요약(한국어)"},
 "away_recent_form": {...동일...},
 "home_pitcher": {"name": "...", "last5": "최근 5~7경기 ERA·피OPS·이닝 요약(한국어)", "era_recent": 5.40, "era_season": 3.86, "trend": "악화|개선|유지"},
 "away_pitcher": {...동일...},
 "splits": "홈/원정 스플릿 요약(한국어)",
 "bullpen": "양 팀 불펜 최근 3일 소모 상황(한국어)",
 "absences": ["핵심 결장자와 중요도(한국어)"],
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | <team> +/-1.5 | Over/Under <line>", "reasoning": "한국어", "record": "시즌 전적 예: 61-42"}],
 "predicted_scores": ["4-2"],
 "form_reversal": ["시즌 평균과 최근 폼이 역전된 항목. 예: '홈 선발 시즌 ERA 3.86 vs 최근5 5.40 악화'. 없으면 빈 배열"]
}"""

_SCHEMA_SOCCER = """{
 "home_recent_form": {"form": "WWDLW (최근 5경기, 최신부터)", "last5_detail": "상대·스코어 나열(한국어)", "gf5": 9, "ga5": 4, "rank": 3, "home_split": "홈 성적 요약(한국어)"},
 "away_recent_form": {...동일 (away_split)...},
 "h2h_history": "최근 상대전적 요약(한국어)",
 "absences": ["핵심 결장자와 중요도(한국어)"],
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | Double Chance <team> | Over/Under <line>", "reasoning": "한국어", "record": "전적"}],
 "predicted_scores": ["2-1", "1-1"],
 "form_reversal": ["시즌 순위와 최근 폼이 역전된 항목(한국어). 없으면 빈 배열"]
}"""

PROMPT = """Research the {sport_kr} match below as of RIGHT NOW ({now} UTC). Use the most recent data you can find — recent form matters more than season averages.

Match: {away} @ {home} ({league}, kickoff {kickoff} UTC)

Find: {targets}

Output ONLY one JSON object (no prose) with this exact shape:
{schema}

Rules: every free-text value must be KOREAN (team/player names may stay original). If something cannot be found, use null/empty — never invent numbers. "form_reversal" must flag any metric where recent form contradicts the season-long number."""

TARGETS = {
    "mlb": ("both starters' last 5-7 outings (ERA, opponent OPS, innings) vs season averages; "
            "home/away splits; each lineup's last-30-day performance vs LHP/RHP; bullpen usage last 3 days; "
            "published expert picks WITH each expert's season record"),
    "soccer": ("last 5 match results and goals for both teams; home/away splits; head-to-head record; "
               "key absences and their importance; published expert picks WITH records; predicted scorelines"),
}


def _extract_json_object(content: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", content, re.S)
    if not m:
        m = re.search(r"(\{.*\})", content, re.S)
    if not m:
        raise ValueError("no JSON object in response")
    return json.loads(m.group(1))


async def deep_research_game(game: dict, sport: str, client: PerplexityClient | None = None) -> dict:
    """경기 1건 심층 리서치 → 구조화 dict. 파싱 실패 시 1회 재요청."""
    client = client or PerplexityClient()
    if client.mock:
        data = client.load_mock("deep_research.json")
        # 목 모드: 전문가 픽을 해당 경기 팀명으로 치환 (파이프라인 시나리오 재현용)
        data["expert_picks"] = [
            {"expert": "MockExpert", "site": "Covers", "source_url": "https://covers.com/mock",
             "pick": f"{game['home']} ML", "reasoning": "홈 최근 폼 우세 (목)", "record": "10-5"},
            {"expert": "MockTotals", "site": "Dimers", "source_url": "https://dimers.com/mock",
             "pick": "Under 9.5", "reasoning": "양 선발 최근 호조 (목)", "record": None},
        ]
        return data
    kick = game.get("starts_at")
    prompt = PROMPT.format(
        sport_kr="MLB baseball" if sport == "mlb" else "football(soccer)",
        now=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        away=game["away"], home=game["home"], league=game.get("league", "?"),
        kickoff=str(kick), targets=TARGETS[sport],
        schema=_SCHEMA_MLB if sport == "mlb" else _SCHEMA_SOCCER,
    )
    resp = await client.chat(prompt)
    try:
        return _extract_json_object(resp["choices"][0]["message"]["content"])
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("[deep] JSON parse failed (%s) — re-requesting once", exc)
        resp = await client.chat(prompt + "\n\nReturn ONLY the JSON object, nothing else.")
        return _extract_json_object(resp["choices"][0]["message"]["content"])


# ---------------------------------------------------------------- 신선도 게이트

def research_is_fresh(
    cached_at: datetime | None, starts_at: datetime, now: datetime | None = None,
    quota_exhausted: bool = False,
) -> bool:
    """[3] 캐시 6시간 이내 & 킥오프 3시간 이상 → 신선. 쿼터 소진 시 보수화(캐시 사용)."""
    if cached_at is None:
        return False
    if quota_exhausted:
        return True  # 재리서치 억제 — 캐시를 신선한 것으로 취급
    now = now or datetime.now(UTC)
    age_ok = (now - cached_at).total_seconds() <= RESEARCH_FRESH_HOURS * 3600
    kickoff_far = (starts_at - now).total_seconds() >= KICKOFF_GUARD_HOURS * 3600
    return age_ok and kickoff_far


# ---------------------------------------------------------------- 비용 가드

def _quota_key() -> str:
    from app.pipeline import today_kst

    return f"research_calls:{today_kst()}"


async def research_calls_today(redis) -> int:
    v = await redis.get(_quota_key())
    return int(v) if v else 0


async def _record_call(redis) -> int:
    n = await redis.incr(_quota_key())
    await redis.expire(_quota_key(), 86400 * 2)
    if n == DAILY_RESEARCH_CAP:
        logger.warning("[deep] 일 리서치 상한 %d콜 도달 — 이후 재리서치 억제", DAILY_RESEARCH_CAP)
    return n


async def log_cost_summary(redis) -> None:
    """[6] 주간 예상 비용 로그 — 최근 7일 콜 수 합산."""
    from datetime import timedelta

    from app.pipeline import KST

    total = 0
    for d in range(7):
        day = (datetime.now(KST) - timedelta(days=d)).strftime("%Y-%m-%d")
        v = await redis.get(f"research_calls:{day}")
        total += int(v) if v else 0
    logger.info("[deep] 최근 7일 리서치 %d콜 — 주간 예상 비용 ≈ $%.2f (콜당 $%.3f 가정)",
                total, total * EST_COST_PER_CALL_USD, EST_COST_PER_CALL_USD)


# ---------------------------------------------------------------- 캐시 접근

async def get_game_research(
    redis, game: dict, sport: str, force: bool = False,
) -> tuple[dict | None, str]:
    """경기 리서치를 신선도 게이트에 따라 반환.

    반환 status: 'fresh'(캐시 즉답) | 'refreshed'(재리서치 성공) |
                 'stale_fallback'(재리서치 실패 → 구캐시) | 'missing'(캐시·리서치 모두 없음) |
                 'quota'(상한 도달 → 캐시 기준)
    """
    key = f"research:{game['game_id'] if 'game_id' in game else game['id']}"
    raw = await redis.get(key)
    cached_at, cached_data = None, None
    if raw:
        try:
            obj = json.loads(raw)
            cached_at = datetime.fromisoformat(obj["at"])
            cached_data = obj["data"]
        except (KeyError, ValueError):
            pass

    starts_at = game.get("starts_at")
    if isinstance(starts_at, str):
        starts_at = datetime.fromisoformat(starts_at)
    if starts_at is None:  # 구버전 캐시 — 킥오프 미상이면 캐시 연령만으로 판정
        from datetime import timedelta
        starts_at = datetime.now(UTC) + timedelta(days=2)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    calls = await research_calls_today(redis)
    quota_out = calls >= DAILY_RESEARCH_CAP
    if not force and research_is_fresh(cached_at, starts_at, quota_exhausted=quota_out):
        return cached_data, ("quota" if quota_out and cached_data else "fresh")
    if quota_out:
        return cached_data, "quota" if cached_data else "missing"

    try:
        client = PerplexityClient()
        if not client.mock:
            await _record_call(redis)
        data = await deep_research_game({**game, "starts_at": starts_at}, sport, client)
        await redis.set(key, json.dumps(
            {"at": datetime.now(UTC).isoformat(), "data": data}, ensure_ascii=False,
            default=str), ex=CACHE_TTL)
        return data, "refreshed"
    except Exception as exc:
        from app.collectors.base import ApiQuotaError
        from app.notify import notify_quota

        logger.error("[deep] research failed for %s vs %s: %s", game.get("home"), game.get("away"), exc)
        if isinstance(exc, ApiQuotaError):  # 크레딧 소진 → 관리자에게 충전 안내 발송
            await notify_quota(exc.service, exc.detail)
        if cached_data is not None:
            return cached_data, "stale_fallback"
        return None, "missing"
