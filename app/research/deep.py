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
 "park_factor": 1.03,   // 구장 득점 파크팩터 (1.00=중립)
 "absences": ["핵심 결장자와 중요도(한국어). 반드시 '팀명 + 선수명 + 역할(주전 타자/마무리/셋업/선발) + 팀 내 기여도'를 포함. 예: 'San Diego Padres의 Jason Adam(마무리) 부상 결장 — 9회 담당'"],
 "lineup": {"status": "confirmed|projected|unknown", "home": "홈 선발 라인업/타순(한국어). 미발표면 null", "away": "원정 동일", "source": "출처 매체명"},
 "motivation": "양 팀의 이 경기 동기 — 순위 경쟁·와일드카드·소화 경기·매각 후 리빌딩 여부(한국어). 없으면 null",
 "schedule_load": "일정 부담 — 연전 몇 번째·직전 경기 종료 시각·이동 거리·시차·더블헤더 여부(한국어). 없으면 null",
 "umpire": "주심과 스트라이크존 성향 — 존이 넓은 편인지 좁은 편인지, 삼진율/볼넷율 경향(한국어). 없으면 null",
 "rotation_plan": "감독의 로테이션·불펜 휴식 계획, 오프너 여부(한국어). 없으면 null",
 "park": "구장 특성 — 타자친화/투수친화와 그 근거(한국어). 없으면 null",
 "weather": "경기 시각 날씨 — 기온·풍향·강수 확률(한국어). 없으면 null",
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | <team> +/-1.5 | Over/Under <line>", "reasoning": "한국어", "record": "시즌 전적 예: 61-42"}],
 "predicted_scores": ["4-2"],
 "form_reversal": ["시즌 평균과 최근 폼이 역전된 항목. 예: '홈 선발 시즌 ERA 3.86 vs 최근5 5.40 악화'. 없으면 빈 배열"]
}"""

_SCHEMA_SOCCER = """{
 "home_recent_form": {"form": "WWDLW (최근 5경기, 최신부터)", "last5_detail": "상대·스코어 나열(한국어)", "gf5": 9, "ga5": 4, "rank": 3, "home_split": "홈 성적 요약(한국어)"},
 "away_recent_form": {...동일 (away_split)...},
 "h2h_history": "최근 상대전적 요약(한국어)",
 "absences": ["핵심 결장자와 중요도(한국어). '팀명 + 선수명 + 포지션 + 주전 여부'를 포함"],
 "lineup": {"status": "confirmed|projected|unknown", "home": "홈 선발 라인업/타순(한국어). 미발표면 null", "away": "원정 동일", "source": "출처 매체명"},
 "motivation": "양 팀의 이 경기 동기 — 우승/유럽대항권/강등 경쟁, 이미 확정돼 느슨한지, 다음 경기 대비 로테이션 예고(한국어). 없으면 null",
 "schedule_load": "일정 부담 — 직전 경기 이후 휴식일·미드위크 대항전·이동 거리·시차(한국어). 없으면 null",
 "park": "구장·잔디 상태(한국어). 없으면 null",
 "weather": "경기 시각 날씨(한국어). 없으면 null",
 "expert_picks": [{"expert": "...", "site": "...", "source_url": "...", "pick": "<team> ML | Double Chance <team> | Over/Under <line>", "reasoning": "한국어", "record": "전적"}],
 "predicted_scores": ["2-1", "1-1"],
 "form_reversal": ["시즌 순위와 최근 폼이 역전된 항목(한국어). 없으면 빈 배열"]
}"""

# [§8-14] 리그명을 정확히 박아야 현지 소스(스포츠조선·닛칸스포츠 등)를 찾는다.
#   "baseball"만 주면 MLB 기사를 물어온다 — 실제로 팀명이 겹치는 경우가 있다
#   (Lotte: KBO 롯데 자이언츠 / NPB 지바 롯데 마린스, Tigers: KIA / 한신 / 디트로이트).
_SPORT_LABEL = {
    "mlb": "MLB baseball",
    "kbo": "KBO (Korea Baseball Organization, 한국프로야구) baseball",
    "npb": "NPB (Nippon Professional Baseball, 日本プロ野球) baseball",
    "soccer": "football(soccer)",
}

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
    "soccer": ("last 5 match results and goals for both teams; home/away splits; head-to-head record; "
               "every absence WITH position and whether the player is a regular starter; "
               "pitch and weather conditions; published expert picks WITH records; predicted scorelines"),
    # [§8-14] KBO·NPB — MLB 목록을 그대로 쓰면 **없는 지표를 요구**하게 된다.
    #   SIERA·xFIP·wOBA는 KBO/NPB 공개 매체가 거의 쓰지 않는다(스탯티즈·1.02 등
    #   일부만 제공). 요구했다가 못 찾으면 Perplexity는 200 OK로 "왜 못 찾았는지"를
    #   산문으로 채워 보내고, 그것이 validate에서 전량 폐기돼 **재료 0**이 된다.
    #   → 실제로 공개되는 지표(평균자책점·타율·OPS·최근 등판)만 요구한다.
    #   현지 매체를 명시해 MLB 기사로 새는 것을 막는다(팀명이 겹친다: Lotte·Tigers·Giants).
    # ⚠️ 라인업은 **확정과 예상을 절대 섞지 마라.** 예상을 확정으로 취급하면
    #   '최종 픽' 자격이 잘못 부여된다(라인업 2단계 규율).
    "kbo": ("the starting lineup — say explicitly whether it is 공식 발표(confirmed) "
            "or 예상(projected), and name the source; "
            "each team's last 5 results as a SEQUENCE newest-first in 승/패/무 "
            "(e.g. '승승패승패'), not a tally; "
            "both teams' recent form (last 5~10 games, W/L and runs scored/allowed); "
            "team batting average, OPS and runs per game over the last month; "
            "both probable starting pitchers — season ERA, WHIP, recent 3~5 starts "
            "(innings, earned runs, pitch count), and throwing hand; "
            "bullpen usage over the last 3 days and whether the closer is available; "
            "injuries and absences WITH each player's role — 1군 등록·말소와 부상자 명단을 "
            "함께 보라(KBO는 말소로 결장을 알린다); "
            "the ballpark's run environment (잠실·고척 are pitcher-friendly, 대구·인천 hitter-friendly); "
            "game-time weather; standings position and remaining-games context. "
            "PREFER Korean sources: 네이버 스포츠, KBO 공식(koreabaseball.com), 스포츠조선, "
            "OSEN, 엠스플뉴스, 스탯티즈(statiz.sporki.com), 각 구단 공식 사이트. "
            "This is KOREAN professional baseball — do NOT return MLB information."),
    "npb": ("the starting lineup — say explicitly whether it is 公式発表(confirmed) "
            "or 予想(projected), and name the source; "
            "each team's last 5 results as a SEQUENCE newest-first in 勝/敗/分 "
            "(e.g. '勝勝敗勝敗'), not a tally; "
            "both teams' recent form (last 5~10 games, W/L and runs scored/allowed); "
            "team batting average, OPS and runs per game over the last month; "
            "both probable starting pitchers — season ERA, WHIP, recent 3~5 starts "
            "(innings, earned runs, pitch count), and throwing hand; "
            "bullpen usage over the last 3 days and whether the closer is available; "
            "injuries and absences WITH each player's role — 出場選手登録・抹消も見よ"
            "(NPBは抹消で欠場を知らせる); "
            "the ballpark's run environment (東京ドーム·甲子園 etc.); "
            "game-time weather; standings position (セ・リーグ / パ・リーグ). "
            "PREFER Japanese sources: Yahoo!スポーツ(baseball.yahoo.co.jp), NPB公式(npb.jp), "
            "日刊スポーツ, スポニチ, デイリースポーツ, 各球団公式サイト. "
            "This is JAPANESE professional baseball — do NOT return MLB information."),
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
        sport_kr=_SPORT_LABEL.get(sport, "football(soccer)"),
        now=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        away=game["away"], home=game["home"], league=game.get("league", "?"),
        kickoff=str(kick), targets=TARGETS[sport],
        schema=_SCHEMA_MLB if sport in ("mlb", "kbo", "npb") else _SCHEMA_SOCCER,
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
        # [§8-7] 신규 맥락 필드 — λ 계수로 쓰지 않고 **판정(p_claude)이 본다**.
        #        계수 없이 λ를 건드리면 측정되지 않은 튜닝이 된다(DISCIPLINE 5-1).
        "motivation": bool(d.get("motivation")),
        "schedule_load": bool(d.get("schedule_load")),
        "umpire": bool(d.get("umpire")),
        "lineup": bool((d.get("lineup") or {}).get("status") in ("confirmed", "projected")),
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

def needs_refresh(game: dict) -> str | None:
    """[3] 신선도와 무관하게 **강제 재조사**해야 하는 사유. 없으면 None.

    캐시가 6시간 이내라도 아래가 바뀌면 리서치 내용이 실제로 달라진다:
    - 라인업이 새로 확정됨 → 결장·타순이 확정치로 바뀐다
    - 선발이 변경됨 → 상대 선발 분석이 통째로 무의미해진다

    반대로 "6시간 내 두 번 조사"는 결장·전문가 픽이 거의 바뀌지 않아 콜 낭비다.
    """
    if game.get("lineup_just_confirmed"):
        return "라인업 확정"
    if game.get("starter_changed"):
        return "선발 변경"
    return None


# [§8-22] 빈칸 보충 조사. 크롤링이 채우지 못한 것만 **짧게** 묻는다.
#   실측(2026-08-26): 프롬프트가 길수록 모델이 검색을 포기한다
#   (962→1442자에서 채움률 6/10 → 0/10). 그래서 전체 스키마를 다시 묻지 않고
#   빠진 항목만 한 줄로 묻는다.
GAP_PROMPT = """{sport_kr} 경기 {away} @ {home} ({kickoff} 시작)에 대해 다음만 찾아라.

{gaps}

{locale}
확인된 사실만 한국어로 간단히. 못 찾은 항목은 그냥 빼라 — 왜 못 찾았는지 쓰지 마라."""

GAP_LABEL = {
    "absences": "오늘 결장·부상자와 그 선수의 역할(주전/마무리/선발)",
    "bullpen": "양 팀 불펜 최근 3일 소화 이닝과 마무리 등판 가능 여부",
    "motivation": "양 팀의 이 경기 동기 — 순위 경쟁·소화 경기 여부",
    "rotation_plan": "감독이 밝힌 로테이션·불펜 운용 계획",
    "umpire": "주심과 그 심판의 스트라이크존 성향",
    "home_recent_form.form": "홈팀 최근 5경기 승패 순서(승/패/무로, 최신부터)",
    "away_recent_form.form": "원정팀 최근 5경기 승패 순서(승/패/무로, 최신부터)",
}


async def fill_gaps(game: dict, sport: str, research: dict,
                    gaps: list[str], client: PerplexityClient | None = None) -> dict:
    """[§8-22] 빈칸만 보충 조사해 research에 얹는다. 반환: 채운 필드 목록 포함 요약.

    ⚠️ 이미 있는 값은 **덮어쓰지 않는다.** 크롤링·공식 기록이 딥서치보다 정확하다.
    """
    labels = [GAP_LABEL[g] for g in gaps if g in GAP_LABEL]
    if not labels:
        return {"asked": [], "filled": []}
    client = client or PerplexityClient()
    if client.mock:
        return {"asked": labels, "filled": []}
    prompt = GAP_PROMPT.format(
        sport_kr=_SPORT_LABEL.get(sport, sport),
        away=game.get("away"), home=game.get("home"),
        kickoff=str(game.get("starts_at") or ""),
        gaps="\n".join(f"- {x}" for x in labels),
        locale=("한국어 매체(네이버 스포츠·스포츠조선·OSEN)를 우선하라."
                if sport == "kbo" else
                "日本語メディア(日刊スポーツ·スポニチ)を優先せよ。"
                if sport == "npb" else ""))
    try:
        raw = await client.chat(prompt)
        text = normalize_response(raw)
        text = text if isinstance(text, str) else _extract_text(text)
    except Exception as exc:                       # 보충 실패가 분석을 막지 않는다
        logger.warning("[deep] 빈칸 보충 실패 %s: %s", gaps, exc)
        return {"asked": labels, "filled": [], "error": str(exc)[:120]}
    from app.research.validate import clean_text

    cleaned = clean_text(text, require_number=False, sentencewise=True)
    if not cleaned:
        return {"asked": labels, "filled": []}
    research["gap_fill"] = cleaned[:1200]          # 판정이 읽는 자유서술
    return {"asked": labels, "filled": ["gap_fill"]}


def _extract_text(obj) -> str:
    """normalize_response가 dict를 돌려줄 때 본문만 꺼낸다."""
    try:
        return obj["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""


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
    reason = needs_refresh(game)
    if reason and not quota_out:
        force = True
        logger.info("[deep] 강제 재조사 game=%s — %s", game.get("game_id"), reason)
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
