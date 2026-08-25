"""경기 단위 실시간 심층 리서치 — Perplexity sonar-pro, 전 경기 공통 "재료 조사".

체제 (2026-08-24 실시간 리서치 전환):
- 프리페치(04:00 KST)에서 전 경기 심층 리서치를 세마포어 동시 처리로 캐시.
- 신선도 게이트: 캐시 6시간 이내 & 킥오프 3시간 이상 남음 → 캐시 즉답.
  킥오프 3시간 이내 or 캐시 6시간 초과 → 재리서치. 실패 시 캐시 폴백("새벽 데이터 기준").
- 비용 가드: Perplexity 일 상한 60콜. 초과 시 게이트 보수화(재리서치 억제) + 카드 경고.
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.research.perplexity import PerplexityClient
from app.research.validate import has_material, sanitize_research

logger = logging.getLogger(__name__)

RESEARCH_FRESH_HOURS = 6      # 캐시 신선 기준
KICKOFF_GUARD_HOURS = 3       # 킥오프 임박 기준 — 이내면 무조건 재리서치
DAILY_RESEARCH_CAP = 60       # Perplexity 일 상한 (초과 시 캐시 기준)
RESEARCH_CONCURRENCY = 2      # 일괄 재리서치 세마포어 (레이트리밋 방어로 축소)
CACHE_TTL = 36 * 3600
RETRY_QUEUE_KEY = "research_retry_queue"   # 레이트리밋 최종 실패분 — 다음 사이클 재시도
EST_COST_PER_CALL_USD = 0.01  # sonar-pro 대략 단가 (주간 비용 추정 로그용)

_SCHEMA_MLB = """{
 "home_recent_form": {"form": "WWLWL (최근 5경기, 최신부터)", "runs_avg": 4.2, "note": "최근 30일 좌/우완 상대 타선 성적 요약(한국어)"},
 "away_recent_form": {...동일...},
 // ↓ 확률 계산(포아송 λ)에 직접 쓰이는 수치. 반드시 **숫자**로 채운다.
 "home_offense": {"woba_30d": 0.318, "obp_30d": 0.322, "iso_30d": 0.155, "k_pct": 22.4, "bb_pct": 8.1, "vs_lhp_woba": 0.330, "vs_rhp_woba": 0.312},
 "away_offense": {...동일...},
 "home_pitcher": {"name": "...", "throws": "L|R", "last5": "최근 5~7경기 ERA·피OPS·이닝 요약(한국어)", "siera": 3.95, "xfip": 4.02, "fip": 4.10, "era_recent": 5.40, "era_season": 3.86, "ip_avg_recent": 5.2, "home_away_split": "홈/원정 스플릿(한국어)", "trend": "악화|개선|유지"},
 // era_recent와 ip_avg_recent는 **반드시 숫자**로 채운다. 서술에 "최근 ERA 2점대 중후반"처럼
 // 쓸 수 있으면 그 수치를 계산해 era_recent에 숫자로 넣어라. 정말 모를 때만 null.
 "away_pitcher": {...동일...},
 "splits": "홈/원정 스플릿 요약(한국어)",
 "bullpen": "양 팀 불펜 최근 3일 소모 상황 — 소화 이닝과 연투 여부를 숫자로(한국어)",
 "bullpen_overused": "홈|원정|양팀|없음 (최근 3일 소모가 리그 평균 대비 과다한 쪽)",
 "home_bullpen": {"era": 3.85, "fip": 4.02, "ip_last3d": 8.2, "closer_available": true},
 "away_bullpen": {...동일...},
 "park_factor": 1.03,   // 구장 득점 파크팩터 (1.00=중립). 홈런 파크팩터는 park_hr
 "park_hr": 1.08,
 "absences": ["핵심 결장자와 중요도(한국어). 반드시 '팀명 + 선수명 + 역할(주전 타자/마무리/셋업/선발) + 팀 내 기여도'를 포함. 예: 'San Diego Padres의 Jason Adam(마무리) 부상 결장 — 9회 담당'"],
 "rotation_plan": "감독의 로테이션·불펜 휴식 계획, 오프너 여부(한국어). 없으면 null",
 "park": "구장 특성 — 타자친화/투수친화와 그 근거(한국어). 없으면 null",
 "weather": "경기 시각 날씨 — 기온·풍향·강수 확률(한국어). 없으면 null",
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | <team> +/-1.5 | Over/Under <line>", "reasoning": "한국어", "record": "시즌 전적 예: 61-42"}],
 "predicted_scores": ["4-2"],
 "form_reversal": ["시즌 평균과 최근 폼이 역전된 항목. 예: '홈 선발 시즌 ERA 3.86 vs 최근5 5.40 악화'. 없으면 빈 배열"]
}"""

_SCHEMA_SOCCER = """{
 "home_recent_form": {"form": "WWDLW (최근 5경기, 최신부터)", "last5_detail": "상대·스코어 나열(한국어)", "gf5": 9, "ga5": 4, "rank": 3, "xg6": 1.62, "xga6": 1.10, "home_split": "홈 성적 요약(한국어)"},
 // xg6/xga6 = 최근 6경기 경기당 기대득점(xG)·기대실점(xGA). 확률 계산에 직접 쓰인다.
 "away_recent_form": {...동일 (away_split)...},
 "h2h_history": "최근 상대전적 요약(한국어)",
 "absences": ["핵심 결장자와 중요도(한국어). '팀명 + 선수명 + 포지션 + 주전 여부'를 포함"],
 "park": "구장·잔디 상태(한국어). 없으면 null",
 "weather": "경기 시각 날씨(한국어). 없으면 null",
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | Double Chance <team> | Over/Under <line>", "reasoning": "한국어", "record": "전적"}],
 "predicted_scores": ["2-1", "1-1"],
 "form_reversal": ["시즌 순위와 최근 폼이 역전된 항목(한국어). 없으면 빈 배열"]
}"""

PROMPT = """Research the {sport_kr} match below as of RIGHT NOW ({now} UTC). Use the most recent data you can find — recent form matters more than season averages.

Match: {away} @ {home} ({league}, kickoff {kickoff} UTC)

Find: {targets}

Output ONLY one JSON object (no prose) with this exact shape:
{schema}

CRITICAL — these NUMERIC fields drive the win-probability model. Fill them with numbers:
- Batting (last 30 days, NOT season): wOBA, OBP, ISO, K%, BB%, and split wOBA vs LHP / vs RHP.
  Research shows batting metrics predict outcomes better than pitching metrics — do not skip them.
- Starters: SIERA, xFIP, FIP if published (these are luck-adjusted; plain ERA is the last resort),
  the hand they throw with (L/R), and average innings per start over the last 5.
- Bullpen: ERA/FIP and innings pitched in the last 3 days, whether the closer is available.
- Park run factor (1.00 = neutral) and home-run factor.
- Game-time temperature in Celsius and wind direction (맞바람/뒷바람).
For soccer: xG and xGA per match over the last 6 matches (xg6 / xga6).

"era_recent" (last-5-start ERA) and "ip_avg_recent" (average innings per start over
those outings) must be NUMBERS, not prose. If you can describe the recent form in words, you can
compute the number — do it. Leave them null ONLY if you truly found no game logs. These two fields
drive the win-probability calculation; prose in "last5" alone is not usable.

Rules: every free-text value must be KOREAN (team/player names may stay original). If something cannot be found, use null/empty — never invent numbers. Do NOT restate the question or explain what you could not find — use null for anything you cannot verify with a real number. "form_reversal" must flag any metric where recent form contradicts the season-long number."""

# [4-1] 승률 조정 계수(performance.py)에 직접 매핑되는 항목을 명시적으로 요구한다.
#       수집은 됐는데 확률에 못 쓰이는 정보가 생기지 않도록 필드를 계수에 맞춰 잡았다.
TARGETS = {
    "mlb": ("each team's LAST-30-DAY batting line — wOBA, OBP, ISO, K%, BB% — and their "
            "wOBA split against left-handed and right-handed starters; "
            "both starters' SIERA / xFIP / FIP (luck-adjusted metrics beat raw ERA) and throwing hand; "
            "both bullpens' ERA and innings pitched in the last 3 days, closer availability; "
            "the ballpark's run and home-run park factors; game-time temperature and wind; "
            "both starters' LAST 5 STARTS in detail — game-by-game ERA, innings pitched, "
            "opponent OPS — and their AVERAGE innings per start (this drives bullpen exposure); "
            "home/away splits; each lineup's last-30-day performance vs LHP/RHP; "
            "bullpen innings used in the LAST 3 DAYS and whether either bullpen is overworked; "
            "every absence WITH the player's role (everyday hitter / closer / setup / starter) and "
            "how much of the team's offense or leverage innings they account for; "
            "the manager's stated rotation and bullpen rest plan; ballpark run environment; "
            "game-time weather (temperature, wind direction, precipitation); "
            "published expert picks WITH each expert's season record"),
    "soccer": ("each team's xG and xGA per match over the LAST 6 MATCHES (xg6/xga6) — these drive "
               "the probability model, so give numbers; "
               "last 5 match results and goals for both teams; home/away splits; head-to-head record; "
               "every absence WITH position and whether the player is a regular starter; "
               "pitch and weather conditions; published expert picks WITH records; predicted scorelines"),
}


class ResearchUnusableError(RuntimeError):
    """응답은 왔지만 데이터가 아니다 — 프롬프트 반향/미확보 산문뿐인 경우."""


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
             "pick": "Under 9.5", "reasoning": "양 팀 최근 득점력 저하 (목)", "record": None},
        ]
        clean, _ = sanitize_research(data, sport)
        return clean
    kick = game.get("starts_at")
    prompt = PROMPT.format(
        sport_kr="MLB baseball" if sport == "mlb" else "football(soccer)",
        now=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        away=game["away"], home=game["home"], league=game.get("league", "?"),
        kickoff=str(kick), targets=TARGETS[sport],
        schema=_SCHEMA_MLB if sport == "mlb" else _SCHEMA_SOCCER,
    )
    try:
        return await _ask_and_validate(client, prompt, sport)
    except (ValueError, json.JSONDecodeError, KeyError, ResearchUnusableError) as exc:
        logger.warning("[deep] 응답 무효 (%s) — 1회 재요청", exc)
        return await _ask_and_validate(
            client,
            prompt + "\n\nYour previous answer contained explanations instead of data. "
                     "Return ONLY the JSON object, nothing else. Every field you cannot "
                     "verify with a real number must be null — do not describe why.",
            sport,
        )


async def _ask_and_validate(client: PerplexityClient, prompt: str, sport: str) -> dict:
    """1콜 → JSON 파싱 → 무효 값 제거 → 재료가 하나도 없으면 실패로 취급.

    [1] 프롬프트 문구·"확인 불가" 산문이 recent_form 자리에 실리는 경로를 여기서 끊는다.
    """
    resp = await client.chat(prompt)
    data = _extract_json_object(resp["choices"][0]["message"]["content"])
    clean, dropped = sanitize_research(data, sport)
    if not has_material(clean):
        raise ResearchUnusableError(
            f"재료 없음 — 무효 필드 {len(dropped)}개 제거 후 recent_form·전문가 픽·결장 정보 전무")
    return clean


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


async def _record_call(redis, n_calls: int = 1) -> int:
    """실제 발생한 HTTP 콜 수만큼 일 사용량을 올린다 (재요청 1콜도 비용이다)."""
    n = await redis.incrby(_quota_key(), n_calls)
    await redis.expire(_quota_key(), 86400 * 2)
    if n >= DAILY_RESEARCH_CAP > n - n_calls:
        logger.warning("[deep] 일 리서치 상한 %d콜 도달 — 이후 재리서치 억제", DAILY_RESEARCH_CAP)
    return n


# ---------------------------------------------------------------- 실패 계측·재시도 큐

FAIL_REASONS = ("rate_limit", "timeout", "parse", "credit", "auth", "other")


def classify_research_failure(exc: BaseException) -> str:
    """리서치 실패 원인 분류 — 레이트리밋/타임아웃/파싱/크레딧/인증/기타."""
    from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError

    if isinstance(exc, ApiRateLimitError):
        return "rate_limit"
    if isinstance(exc, ApiQuotaError):
        return "credit"
    if isinstance(exc, ApiAuthError):
        return "auth"
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return "timeout"
    if isinstance(exc, (ResearchUnusableError, ValueError, json.JSONDecodeError, KeyError)):
        return "parse"
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return "rate_limit"
    return "other"


def _fail_key(date: str, reason: str) -> str:
    return f"research_fail:{date}:{reason}"


async def record_research_failure(redis, reason: str, date: str | None = None) -> None:
    """원인별 실패 카운터 — 일일 실패 리포트(레이트리밋/타임아웃/파싱)의 소스."""
    from app.pipeline import today_kst

    date = date or today_kst()
    key = _fail_key(date, reason)
    await redis.incr(key)
    await redis.expire(key, 86400 * 14)


async def research_failure_report(redis, date: str) -> dict[str, int]:
    """해당 날짜의 원인별 리서치 실패 건수."""
    out: dict[str, int] = {}
    for reason in FAIL_REASONS:
        v = await redis.get(_fail_key(date, reason))
        if v:
            out[reason] = int(v)
    return out


# ---------------------------------------------------------------- 채움률 계측

FILL_FIELDS = ("form", "absences", "splits", "bullpen", "form_reversal")


def _fill_key(date: str) -> str:
    return f"research_fill:{date}"


def _filled_fields(data: dict | None) -> dict[str, bool]:
    """정제본에서 필드별 실제 채움 여부. 지어내기 감시의 기준선이 된다.

    프롬프트 금지문("못 찾은 이유를 설명하지 말고 null을 써라")이 과하면 채움률이
    급락하고, 반대로 모델이 빈칸을 지어내기 시작하면 채움률만 치솟는다.
    """
    d = data or {}
    return {
        "form": any((d.get(s) or {}).get("form") for s in
                    ("home_recent_form", "away_recent_form")),
        "absences": bool(d.get("absences")),
        "splits": bool(d.get("splits") or (d.get("home_recent_form") or {}).get("home_split")
                       or (d.get("away_recent_form") or {}).get("away_split")),
        "bullpen": bool(d.get("bullpen")),
        "form_reversal": bool(d.get("form_reversal")),
    }


async def record_fill_stats(redis, data: dict | None, *, invalid: bool = False,
                            date: str | None = None) -> None:
    """경기 1건의 필드 채움 여부를 일자별 해시에 누적."""
    from app.pipeline import today_kst

    key = _fill_key(date or today_kst())
    await redis.hincrby(key, "games_total", 1)
    if invalid:
        await redis.hincrby(key, "games_invalid", 1)
    else:
        for field, filled in _filled_fields(data).items():
            if filled:
                await redis.hincrby(key, f"{field}_filled", 1)
    await redis.expire(key, 86400 * 30)


async def fill_report(redis, date: str) -> dict:
    """해당 날짜의 필드별 채움률 + 무효율. 프리페치 로그·튜닝 판단 근거."""
    raw = await redis.hgetall(_fill_key(date)) or {}
    total = int(raw.get("games_total", 0) or 0)
    invalid = int(raw.get("games_invalid", 0) or 0)
    out = {
        "games": total,
        "invalid": invalid,
        "invalid_rate": round(invalid / total, 3) if total else None,
    }
    usable = total - invalid
    for field in FILL_FIELDS:
        n = int(raw.get(f"{field}_filled", 0) or 0)
        out[f"{field}_rate"] = round(n / usable, 3) if usable else None
    return out


async def queue_for_retry(redis, game: dict, sport: str) -> None:
    """레이트리밋 최종 실패 경기를 큐에 적재 — 다음 사이클에서 재시도."""
    item = json.dumps({
        "game_id": game.get("game_id") or game.get("id"),
        "home": game.get("home"), "away": game.get("away"),
        "league": game.get("league"), "sport": sport,
        # 킥오프 미상이면 None을 유지한다 — "None" 문자열이 되면 재시도 시 파싱이 깨진다
        "starts_at": (str(game["starts_at"]) if game.get("starts_at") is not None else None),
    }, ensure_ascii=False)
    await redis.rpush(RETRY_QUEUE_KEY, item)
    await redis.expire(RETRY_QUEUE_KEY, 86400)
    logger.info("[deep] 레이트리밋 실패 → 재시도 큐 적재: %s vs %s",
                game.get("home"), game.get("away"))


async def drain_retry_queue(redis, limit: int = 20) -> int:
    """큐에 쌓인 경기를 **순차** 재리서치. 성공 건수 반환.

    레이트리밋으로 실패한 건이므로 동시 실행하지 않는다 (다시 429를 부른다).
    """
    done = 0
    for _ in range(limit):
        raw = await redis.lpop(RETRY_QUEUE_KEY)
        if not raw:
            break
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        data, status = await get_game_research(
            redis, item, item.get("sport", "mlb"), force=True)
        if status == "refreshed" and data is not None:
            done += 1
        elif status in ("missing", "invalid"):
            logger.info("[deep] 큐 재시도 실패 유지: %s vs %s", item.get("home"), item.get("away"))
    if done:
        logger.info("[deep] 재시도 큐 처리 — %d경기 복구", done)
    return done


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
                 'invalid'(응답은 왔으나 데이터가 아님 — 리서치 실패) | 'quota'(상한 도달)

    캐시된 구데이터도 반환 전에 sanitize_research를 통과시킨다 — 이전 버전이 저장한
    프롬프트 반향/미확보 산문이 그대로 화면에 나가지 않도록.
    """
    key = f"research:{game['game_id'] if 'game_id' in game else game['id']}"
    raw = await redis.get(key)
    cached_at, cached_data = None, None
    cached_empty = False   # 조사는 했으나 재료가 없던 캐시
    if raw:
        try:
            obj = json.loads(raw)
            cached_at = datetime.fromisoformat(obj["at"])
            clean, _ = sanitize_research(obj["data"], sport)
            if has_material(clean):
                cached_data = clean
            else:
                cached_empty = True   # 재료 없는 캐시는 폴백 가치가 없다
        except (KeyError, ValueError):
            pass

    starts_at = game.get("starts_at")
    if isinstance(starts_at, str):
        try:
            starts_at = datetime.fromisoformat(starts_at)
        except ValueError:   # 깨진 값은 킥오프 미상으로 취급 (캐시 연령만으로 판정)
            logger.warning("[deep] starts_at 파싱 실패(%r) — 킥오프 미상 처리", starts_at)
            starts_at = None
    if starts_at is None:  # 구버전 캐시 — 킥오프 미상이면 캐시 연령만으로 판정
        from datetime import timedelta
        starts_at = datetime.now(UTC) + timedelta(days=2)
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)

    calls = await research_calls_today(redis)
    quota_out = calls >= DAILY_RESEARCH_CAP
    if not force and research_is_fresh(cached_at, starts_at, quota_exhausted=quota_out):
        if cached_data is not None:
            return cached_data, ("quota" if quota_out else "fresh")
        if cached_empty:
            # 6시간 내 조사했는데 재료가 없었다 — 곧바로 재조사해도 같은 결과다(콜 낭비 방지)
            return None, "invalid"  # 계측은 최초 조사 시점에 이미 반영됐다
    if quota_out:
        return cached_data, "quota" if cached_data else "missing"

    try:
        client = PerplexityClient()
        try:
            data = await deep_research_game({**game, "starts_at": starts_at}, sport, client)
        finally:
            # 재요청까지 포함한 실제 콜 수를 반영 (실패해도 비용은 발생했다)
            if not client.mock and client.calls:
                await _record_call(redis, client.calls)
        data, _ = sanitize_research(data, sport)
        await redis.set(key, json.dumps(
            {"at": datetime.now(UTC).isoformat(), "data": data}, ensure_ascii=False,
            default=str), ex=CACHE_TTL)
        await record_fill_stats(redis, data)
        return data, "refreshed"
    except Exception as exc:
        from app.notify import notify_api_error

        reason = classify_research_failure(exc)
        logger.error("[deep] research failed for %s vs %s (%s): %s",
                     game.get("home"), game.get("away"), reason, exc)
        await record_research_failure(redis, reason)
        # 크레딧 소진/키 오류만 알림 — 레이트리밋은 내부 재시도·큐 재처리로 흡수한다
        await notify_api_error(exc)
        if reason == "rate_limit":
            await queue_for_retry(redis, game, sport)
        if reason == "parse":
            await record_fill_stats(redis, None, invalid=True)
        if cached_data is not None:
            return cached_data, "stale_fallback"
        return None, "invalid" if reason == "parse" else "missing"
