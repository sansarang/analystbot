"""aiogram 3.x 텔레그램 봇 — /mlb /soccer /today + 자유 질문(의도 파싱).

- 토큰 없으면 CLI 시뮬레이터로 검증: python -m app.bot --simulate "/mlb"
- 4096자 초과 응답은 분할 전송, 캐시 히트 시 즉시 응답.
"""

import argparse
import asyncio
import time
import json
import logging
import re

from datetime import datetime, timedelta

import anthropic
import redis.asyncio as aioredis

import html as html_mod

from app.bot.aliases import find_team
from app.collectors.base import (
    ApiAuthError,
    ApiRateLimitError,
    ApiServiceError,
    is_quota_error,
)
from app.config import get_settings
from app.db import close_pool, get_pool
from app.notify import notify_api_error, notify_quota
from app.pipeline import (
    DETAIL_SEP,
    build_analysis,
    default_date,
    ensure_game_fresh,
    mlb_slate_date,
    render_game_easy,
    render_news,
    render_sources,
    run_pipeline,
    today_kst,
)


async def _game_needs_refresh(jg: dict) -> bool:
    """[3] 이 경기 리서치가 신선도 게이트를 위반하는지 (재리서치 필요 여부)."""
    import json as _json
    from datetime import datetime as _dt

    from app.research.deep import (
        DAILY_RESEARCH_CAP, research_calls_today, research_is_fresh,
    )

    if jg.get("status") != "scheduled":
        return False
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await redis.get(f"research:{jg['game_id']}")
        cached_at = None
        if raw:
            try:
                cached_at = _dt.fromisoformat(_json.loads(raw)["at"])
            except (KeyError, ValueError):
                pass
        starts = jg.get("starts_at")
        if isinstance(starts, str):
            starts = _dt.fromisoformat(starts)
        if starts is None:
            return cached_at is None
        quota_out = (await research_calls_today(redis)) >= DAILY_RESEARCH_CAP
        return not research_is_fresh(cached_at, starts, quota_exhausted=quota_out)
    finally:
        await redis.aclose()

ASK_TEAM_TEXT = (
    "어느 팀 경기인지 못 찾았어요. 예: 다저스, 양키스, 맨시티\n"
    "전체 리포트는 /mlb 또는 /soccer 를 입력하세요."
)


def expired_text(sport: str) -> str:
    return f"분석이 만료됐어요. /{sport if sport in ('mlb', 'soccer') else 'soccer'} 로 새로 요청해 주세요."


def collapsed(title: str, body: str) -> str:
    """제목만 보이고 본문은 접힌 인용문 (Telegram expandable blockquote, HTML)."""
    return (
        f"{html_mod.escape(title)}\n"
        f"<blockquote expandable>{html_mod.escape(body)}</blockquote>"
    )


def two_layer_html(text: str) -> str | None:
    """<<DETAIL>> 마커가 있으면 기본층(보임) + 상세(접힌 인용문) HTML로 변환."""
    if DETAIL_SEP not in text:
        return None
    easy, detail = text.split(DETAIL_SEP, 1)
    easy, detail = easy.strip(), detail.strip()
    if detail.startswith("📊 상세 데이터"):
        detail = detail.split("\n", 1)[1] if "\n" in detail else ""
    body = collapsed("📊 상세 데이터 (펼쳐서 보기)", detail or "(내용 없음)")
    html = f"{html_mod.escape(easy)}\n\n{body}"
    if len(html) > TELEGRAM_LIMIT:  # 접힌 상세만 잘라서 4096 안에 맞춘다
        cut = len(html) - TELEGRAM_LIMIT + 40
        detail = detail[:-cut] + "\n…(생략)"
        html = f"{html_mod.escape(easy)}\n\n" + collapsed("📊 상세 데이터 (펼쳐서 보기)", detail)
    return html


async def send_two_layer(message, text: str, reply_markup=None) -> None:
    """2층 텍스트 전송 — HTML 실패 시 마커만 바꿔 플레인으로 폴백."""
    html = two_layer_html(text)
    if html is None:
        await message.answer(text[:TELEGRAM_LIMIT], reply_markup=reply_markup)
        return
    try:
        await message.answer(html[:TELEGRAM_LIMIT], parse_mode="HTML", reply_markup=reply_markup)
    except Exception as exc:
        logger.warning("[bot] two-layer HTML send failed, plain fallback: %s", exc)
        await message.answer(
            text.replace(DETAIL_SEP, "\n\n— 상세 데이터 —\n")[:TELEGRAM_LIMIT],
            reply_markup=reply_markup)


async def load_analysis(sport: str, date: str) -> dict | None:
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        raw = await redis.get(f"analysis:{sport}:{date}")
        return json.loads(raw) if raw else None
    finally:
        await redis.aclose()


async def render_performance(pool) -> str:
    """픽 채점·성적표 집계는 하지 않는다. 목표는 이 경기 적중이다."""
    return "목적은 이 경기 적중이다. 픽 채점·성적표는 두지 않는다."

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096

# ⚠️ `.format()`을 쓰지 않는다 — 스키마의 JSON 중괄호를 치환 필드로 오해해 KeyError가 난다.
#    기준일은 `intent_system()`이 문자열 결합으로 붙인다.
INTENT_SYSTEM = """사용자의 스포츠 분석 요청에서 의도를 추출해 JSON으로만 답하라.
스키마: {"sport": "mlb"|"soccer", "date": "YYYY-MM-DD"|null, "teams": [문자열], "depth": "brief"|"full"}

오늘 날짜: MLB 슬레이트 __MLB_TODAY__ / 축구 __SOCCER_TODAY__ (KST)
**"오늘"·"today"처럼 오늘을 뜻하는 말이거나 날짜 언급이 아예 없으면 date는 반드시 null이다.**
날짜를 추측해 채우지 마라 — 시스템이 기본 날짜를 적용한다.
"내일"·"어제"처럼 상대 날짜만 위 기준일로 계산해 YYYY-MM-DD로 답하라.
팀 언급이 없으면 빈 배열."""

# LLM이 만들어낸 날짜를 그대로 쓰지 않기 위한 허용 범위(기준일 대비 일수).
# 실사고(2026-08-26): 프롬프트에 오늘 날짜가 없어 모델이 **2024-08-26**을 반환했고,
# 검증이 없어 2년 전 종료 경기 12건이 분석돼 사용자에게 나갔다.
INTENT_DATE_WINDOW_DAYS = 7


def intent_system() -> str:
    """오늘 기준일을 박아 넣은 의도 파싱 시스템 프롬프트."""
    return (INTENT_SYSTEM
            .replace("__MLB_TODAY__", mlb_slate_date())
            .replace("__SOCCER_TODAY__", today_kst()))


def sanitize_intent_date(date: str | None, sport: str) -> str | None:
    """LLM이 준 날짜를 기준일 대비 허용 범위로 검증. 벗어나면 None(기본 날짜).

    CLAUDE.md 절대규칙 2번의 적용이다 — LLM 출력은 API 기준값과 대조하고,
    충돌하면 API가 이긴다. 날짜도 예외가 아니다.
    """
    if not date:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        logger.warning("[bot] intent 날짜 형식 이상 — 무시: %r", date)
        return None
    base = mlb_slate_date() if sport == "mlb" else today_kst()
    try:
        delta = (datetime.strptime(date, "%Y-%m-%d")
                 - datetime.strptime(base, "%Y-%m-%d")).days
    except ValueError:
        return None
    if abs(delta) > INTENT_DATE_WINDOW_DAYS:
        logger.warning("[bot] intent 날짜 %s가 기준일 %s에서 %d일 벗어남 — 기본 날짜 사용",
                       date, base, delta)
        return None
    return date


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """4096자 초과 시 줄바꿈 경계 우선으로 분할."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # 한 줄 자체가 초과하는 극단 케이스
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current.rstrip("\n"))
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip("\n"))
    return chunks


def resolve_date_arg(arg: str | None, sport: str) -> str | None:
    """'/mlb tomorrow', '/mlb 2026-08-25' 식 날짜 인자 해석.

    기준일: MLB=미국 동부 오늘, 축구=KST 오늘. 해석 불가·없음 → None(기본 날짜).
    """
    if not arg:
        return None
    a = arg.strip().lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a):
        return a
    base = mlb_slate_date() if sport == "mlb" else today_kst()
    offsets = {"today": 0, "오늘": 0, "tomorrow": 1, "내일": 1, "yesterday": -1, "어제": -1}
    if a in offsets:
        d = datetime.strptime(base, "%Y-%m-%d") + timedelta(days=offsets[a])
        return d.strftime("%Y-%m-%d")
    return None


SCOPE_STOPWORDS = {"오늘", "내일", "어제", "야구", "축구", "mlb", "MLB", "엠엘비", "전체", "모든", "이번"}


def route_query(text: str, llm_teams: list | None = None) -> tuple[str, object]:
    """자유 질문의 3단계 범위 인식.

    team(1경기) | league(리그만) | league_unsupported(미지원 안내) |
    picks(전체 추천 카드) | ask(되묻기) | full(종목 전체)
    """
    from app.leagues import find_league, find_unsupported_league

    team = find_team(text)
    if team:
        return "team", team
    unsupported = find_unsupported_league(text)  # '세리에B' 오매칭 방지 — 리그 매칭보다 먼저
    if unsupported:
        return "league_unsupported", unsupported
    league = find_league(text)
    if league:
        return "league", league
    if re.search(r"픽|추천|언더독|베팅|배당", text):
        return "picks", None
    if llm_teams:  # LLM이 팀을 인식했지만 별칭 사전에 없음 → 전체 리포트 발사 금지
        return "ask", None
    m = re.search(r"([가-힣A-Za-z0-9\.]+)\s*(팀|경기)", text)
    if m and m.group(1) not in SCOPE_STOPWORDS:
        return "ask", None
    return "full", None


def parse_intent_mock(text: str) -> dict:
    """키 없을 때의 규칙 기반 의도 파싱."""
    t = text.lower()
    sport = "soccer" if re.search(r"soccer|축구|epl|프리미어", t) else "mlb"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    date = sanitize_intent_date(m.group(1) if m else None, sport)
    depth = "brief" if re.search(r"짧게|간단|요약|brief", t) else "full"
    return {"sport": sport, "date": date, "teams": [], "depth": depth}


async def parse_intent(text: str) -> dict:
    """자유 질문 → {sport, date, teams, depth}. Haiku 없으면 규칙 기반."""
    settings = get_settings()
    if settings.mock_judge:  # ANTHROPIC_API_KEY 기준
        return parse_intent_mock(text)
    try:
        return await _parse_intent_live(text, settings)
    except anthropic.APIStatusError as exc:
        if is_quota_error(exc.status_code, str(exc)):
            await notify_quota("anthropic(intent)", str(exc))   # 크레딧 소진만 알림
        else:
            logger.warning("[bot] live intent parse failed, using rule-based: %s", exc)
        return parse_intent_mock(text)


async def _parse_intent_live(text: str, settings) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.intent_model,
        max_tokens=300,
        system=intent_system(),
        messages=[{"role": "user", "content": text}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "sport": {"type": "string", "enum": ["mlb", "soccer"]},
                        "date": {"type": ["string", "null"]},
                        "teams": {"type": "array", "items": {"type": "string"}},
                        "depth": {"type": "string", "enum": ["brief", "full"]},
                    },
                    "required": ["sport", "date", "teams", "depth"],
                    "additionalProperties": False,
                },
            }
        },
    )
    out = json.loads(next(b.text for b in response.content if b.type == "text"))
    # 모델이 만들어낸 날짜를 그대로 신뢰하지 않는다
    out["date"] = sanitize_intent_date(out.get("date"), out.get("sport", "mlb"))
    return out


def _quota_reply(exc: ApiServiceError) -> str:
    """[6] 실패 종류에 맞는 사용자 문구 — 429를 '충전 필요'로 안내하지 않는다."""
    if isinstance(exc, ApiRateLimitError):
        return (
            f"⏳ {exc.service} 요청이 몰려 잠시 제한됐습니다(레이트리밋).\n"
            f"크레딧 문제가 아니며, 자동 재시도로 이어집니다. 잠시 후 다시 시도해 주세요."
        )
    if isinstance(exc, ApiAuthError):
        return (
            f"⚠️ {exc.service} API 키 인증에 실패했습니다 (잔액 문제 아님).\n"
            f"키 값을 확인하거나 교체한 뒤 다시 시도해 주세요.\n"
            f"(상세: {exc.detail[:120]})"
        )
    return (
        f"⚠️ {exc.service} API 사용량/크레딧이 소진되어 분석을 완료하지 못했습니다.\n"
        f"키를 충전하거나 교체한 뒤 다시 시도해 주세요.\n"
        f"(상세: {exc.detail[:120]})"
    )


async def answer_query(sport: str, date: str | None = None, progress=None) -> str:
    """파이프라인 실행(캐시 우선) → 리포트 텍스트.

    API 크레딧/쿼터 소진 시 크래시 대신 사용자에게 상황을 알리는 메시지를 반환하고,
    관리자 채팅으로도 알림을 보낸다.
    """
    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        # date=None이면 run_pipeline이 종목별 기본(MLB=미 동부, 축구=KST)을 적용
        return await run_pipeline(pool, redis, sport=sport, date=date, progress=progress)
    except ApiServiceError as exc:
        logger.error("[bot] API 실패(%s): %s", type(exc).__name__, exc)
        await notify_api_error(exc)   # 레이트리밋은 알림 없이 재시도 안내만
        return _quota_reply(exc)
    finally:
        await redis.aclose()


def _format_team_reply(game: dict, news: str, sport: str) -> str:
    easy, detail = render_game_easy(game, news).split(DETAIL_SEP, 1)
    urls = sorted({
        ep["source_url"] for ep in game.get("expert_picks", []) if ep.get("source_url")
    })
    if urls:
        detail += "\n📎 출처\n" + "\n".join(f"  {u}" for u in urls)
    # 🔴 KBO·NPB 질문에 "/soccer"를 안내하고 있었다 — 종목이 셋 이상인데
    #   이분법으로 나눠서다. 없는 명령을 안내하느니 종목별로 정확히 쓴다.
    _SLATE_CMD = {"mlb": "/mlb", "soccer": "/soccer",
                  "kbo": "KBO", "npb": "NPB"}
    _cmd = _SLATE_CMD.get(sport, "/soccer")
    easy += (f"\n\n전체 슬레이트는 {_cmd}"
             if _cmd.startswith("/") else f"\n\n전체 슬레이트는 '{_cmd}'라고 물어보세요")
    return easy + DETAIL_SEP + detail


async def answer_team_query(sport: str, team: str, progress=None) -> str:
    """특정 팀 질문 → 그 경기 1건만 심층 응답.

    전체 슬레이트 분석 캐시가 있으면 즉시 추출, 없으면 그 경기 1건만
    수집·딥서치·판정한다 (전체 15경기 파이프라인 금지 — API 콜 낭비).
    """
    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        date = mlb_slate_date() if sport == "mlb" else today_kst()
        cached = await redis.get(f"analysis:{sport}:{date}")
        if cached:
            data = json.loads(cached)
            from app.collectors.football import similar_team

            game = next(
                (g for g in data.get("games", [])
                 if team in (g["home"], g["away"])
                 or similar_team(g["home"], team) or similar_team(g["away"], team)),
                None,
            )
            if game:
                logger.info("[bot] team query served from slate cache: %s", team)
                if await _game_needs_refresh(game):
                    if progress:
                        await progress(1, 1, "🔍 최신 조사")
                    fresh, refreshed = await ensure_game_fresh(sport, date, game["game_id"])
                    if fresh is not None:
                        game = next((x for x in fresh["games"]
                                     if x["game_id"] == game["game_id"]), game)
                        data = fresh
                return _format_team_reply(game, data.get("news", ""), sport)
        analysis = await build_analysis(pool, sport, date, team=team, progress=progress)
        if not analysis["games"]:
            from app.bot.aliases import kr_team

            return f"오늘({date}) {kr_team(team)} 경기를 찾지 못했습니다."
        return _format_team_reply(analysis["games"][0], analysis["news"], sport)
    except ApiServiceError as exc:
        logger.error("[bot] API 실패(%s): %s", type(exc).__name__, exc)
        await notify_api_error(exc)   # 레이트리밋은 알림 없이 재시도 안내만
        return _quota_reply(exc)
    finally:
        await redis.aclose()


UNSUPPORTED_LEAGUE_TEXT = None  # 아래 함수로 생성


def unsupported_league_text() -> str:
    from app.leagues import supported_league_list

    return f"그 리그는 아직 데이터 소스에 없습니다. 현재 지원: {supported_league_list()}"


async def answer_full_reco() -> str:
    """/픽 · '오늘 추천' — 분석 없이 그날 전체 슬레이트 캐시 기준 추천 카드만."""
    from app.pipeline import render_full_reco

    analyses = []
    for sport in ("mlb", "soccer"):
        a = await load_analysis(sport, default_date(sport))
        if a and a.get("picks") is not None:
            analyses.append(a)
    if not analyses:
        return ("오늘 분석 캐시가 아직 없습니다. /mlb 또는 /soccer 로 먼저 분석을 실행해 주세요.")
    return render_full_reco(analyses)


async def _next_game_message(league_key: str) -> str:
    """오늘 경기 없는 리그 — 다음 경기 안내 (다른 리그 대체 발송 금지)."""
    from datetime import UTC, datetime

    from app.bot.aliases import kr_team
    from app.collectors.odds import OddsClient
    from app.leagues import LEAGUES
    from app.pipeline import KST

    cfg = LEAGUES[league_key]
    try:
        events = await OddsClient().fetch_events(cfg["odds_key"])
    except Exception:
        events = []
    now = datetime.now(UTC)
    future = sorted(
        (e for e in events
         if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) > now),
        key=lambda e: e["commence_time"],
    )
    if not future:
        return f"오늘 {cfg['label']} 경기가 없습니다. 예정된 다음 경기 정보도 아직 없습니다."
    ev0 = future[0]
    kick = datetime.fromisoformat(ev0["commence_time"].replace("Z", "+00:00")).astimezone(KST)
    return (f"오늘 {cfg['label']} 경기가 없습니다. 다음 경기: "
            f"{kick.strftime('%m/%d %H:%M')} {kr_team(ev0['home_team'])} vs {kr_team(ev0['away_team'])}")


async def answer_league_query(league_key: str, progress=None) -> str:
    """리그 지정 분석 — 그 리그만. 전체 캐시가 있으면 추출(재계산 금지)."""
    from app.leagues import LEAGUES
    from app.pipeline import generate_card, rescope_analysis

    label = LEAGUES[league_key]["label"]
    date = today_kst()
    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        full = await load_analysis("soccer", date)
        if full:
            if not any(g.get("league") == label for g in full["games"]):
                return await _next_game_message(league_key)
            scoped = rescope_analysis(full, label)
            await redis.set(f"analysis:soccer:{date}:{league_key}",
                            json.dumps(scoped, ensure_ascii=False, default=str),
                            ex=get_settings().report_cache_ttl)
            return await generate_card(scoped)
        # 전체 캐시 없음 → 그 리그만 수집·딥서치·판정 (전체 슬레이트 재계산 금지)
        analysis = await build_analysis(pool, "soccer", date,
                                        league_key=league_key, progress=progress)
        if not analysis["games"]:
            return await _next_game_message(league_key)
        card = await generate_card(analysis)
        await redis.set(f"analysis:soccer:{date}:{league_key}",
                        json.dumps(analysis, ensure_ascii=False, default=str),
                        ex=get_settings().report_cache_ttl)
        return card
    except ApiServiceError as exc:
        await notify_api_error(exc)
        return _quota_reply(exc)
    finally:
        await redis.aclose()


# ---------------------------------------------------------------- 텔레그램 연결

def card_keyboard(sport: str, date: str, league_key: str | None = None):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    suffix = f":{league_key}" if league_key else ""

    def btn(label: str, section: str):
        return InlineKeyboardButton(
            text=label, callback_data=f"sec:{sport}:{date}:{section}{suffix}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📊 경기별 심층", "deep"), btn("📰 부상·속보", "news")],
        [btn("📎 출처", "src")],
        [InlineKeyboardButton(text="🎯 오늘 전체 추천픽",
                              callback_data=f"sec:{sport}:{date}:reco")],
    ])


def games_keyboard(analysis: dict):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [InlineKeyboardButton(
            text=f"{g['starts_at_kst'][-5:]} {g['home']} vs {g['away']}"[:60],
            callback_data=f"game:{g['game_id']}",
        )]
        for g in analysis["games"] if g["status"] == "scheduled"
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows or [[
        InlineKeyboardButton(text="분석 대상(시작 전) 경기 없음", callback_data="noop")
    ]])


async def _safe_cb_answer(cb) -> None:
    """answer_callback_query — 만료/무효 ID여도 본 응답 흐름을 깨지 않는다."""
    try:
        await cb.answer()
    except Exception as exc:
        logger.debug("[bot] callback answer skipped: %s", exc)


def build_dispatcher():
    from aiogram import Dispatcher, F, Router
    from aiogram.filters import Command, CommandObject, CommandStart
    from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

    router = Router()

    async def _reply(message: Message, text: str) -> None:
        if DETAIL_SEP in text:
            await send_two_layer(message, text)
            return
        for chunk in split_message(text):
            if chunk:
                await message.answer(chunk)

    async def _send_card(message: Message, card: str, sport: str, date: str) -> None:
        await send_two_layer(message, card, reply_markup=card_keyboard(sport, date))

    def _make_progress(message: Message):
        """'⏳ 1/4 ...' 상태 메시지를 만들고 단계마다 edit_message_text로 갱신.

        캐시 히트 등으로 progress가 한 번도 안 불리면 상태 메시지도 안 만든다.
        """
        state: dict = {"msg": None}

        async def progress(step: int, total: int, label: str) -> None:
            text = f"⏳ {step}/{total} {label} 중..."
            try:
                if state["msg"] is None:
                    state["msg"] = await message.answer(text)
                else:
                    await state["msg"].edit_text(text)
            except Exception as exc:  # 진행 표시 실패가 본 흐름을 막으면 안 됨
                logger.warning("[bot] progress update failed: %s", exc)

        return state, progress

    async def _run_with_progress(message: Message, factory) -> None:
        state, progress = _make_progress(message)
        try:
            reply = await factory(progress)
        finally:
            if state["msg"] is not None:
                try:
                    await state["msg"].delete()
                except Exception:
                    pass
        await _reply(message, reply)

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        # 운영 알림용 TELEGRAM_ADMIN_CHAT_ID 설정을 돕기 위해 채팅 ID를 로그로 남긴다
        logger.info("[bot] /start from chat_id=%s (%s)", message.chat.id,
                    message.from_user.username if message.from_user else "?")
        await message.answer(
            "AnalystBot입니다. /mlb /soccer /today 또는 자유 질문으로 분석을 요청하세요.\n"
            "※ 분석 정보용 도구이며 베팅 손실 책임은 이용자에게 있습니다."
        )

    async def _card_flow(message: Message, sport: str, date: str | None) -> None:
        date = date or default_date(sport)
        state, progress = _make_progress(message)
        try:
            card = await answer_query(sport, date, progress=progress)
        finally:
            if state["msg"] is not None:
                try:
                    await state["msg"].delete()
                except Exception:
                    pass
        await _send_card(message, card, sport, date)

    @router.message(Command("mlb"))
    async def on_mlb(message: Message, command: CommandObject) -> None:
        # 기본: 미국 동부 오늘. 인자: tomorrow/내일/어제 또는 YYYY-MM-DD
        await _card_flow(message, "mlb", resolve_date_arg(command.args, "mlb"))

    async def _league_flow(message: Message, league_key: str) -> None:
        state, progress = _make_progress(message)
        try:
            card = await answer_league_query(league_key, progress=progress)
        finally:
            if state["msg"] is not None:
                try:
                    await state["msg"].delete()
                except Exception:
                    pass
        await send_two_layer(
            message, card,
            reply_markup=card_keyboard("soccer", today_kst(), league_key=league_key))

    @router.message(Command("soccer"))
    async def on_soccer(message: Message, command: CommandObject) -> None:
        # '/soccer 분데스리가' — 리그 인자 지원
        if command.args:
            from app.leagues import find_league, find_unsupported_league

            if find_unsupported_league(command.args):
                await message.answer(unsupported_league_text())
                return
            league_key = find_league(command.args)
            if league_key:
                await _league_flow(message, league_key)
                return
        await _card_flow(message, "soccer", None)

    @router.message(Command("health"))
    async def on_health(message: Message) -> None:
        """[7-5] 지금 시스템 상태 — 조회만 한다."""
        from app.health import build_health

        poll_tick()
        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            pool = await get_pool()
            text = await build_health(pool, redis)
        except Exception as exc:
            logger.exception("[bot] /health 실패: %s", exc)
            text = f"🩺 상태 점검 실패\n{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            await redis.aclose()
        for chunk in split_message(text):
            await message.answer(chunk)

    @router.message(Command("checklist"))
    async def on_checklist(message: Message) -> None:
        """KBO·NPB 저녁 발송 계약 + 지금 측정. 조회만 한다."""
        from app.engine.pregame_checklist import build_pregame_checklist

        poll_tick()
        redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            pool = await get_pool()
            text = await build_pregame_checklist(pool, redis)
        except Exception as exc:
            logger.exception("[bot] /checklist 실패: %s", exc)
            text = f"📋 저녁 점검 실패\n{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            await redis.aclose()
        for chunk in split_message(text):
            await message.answer(chunk)

    @router.message(Command("today"))
    async def on_today(message: Message) -> None:
        await _card_flow(message, "mlb", None)

    @router.message(Command("픽"))
    async def on_pick_command(message: Message) -> None:
        await send_two_layer(message, await answer_full_reco())

    # ---------------- 인라인 버튼 콜백 (캐시에서 즉답 — 재계산 금지) ----------------

    @router.callback_query(F.data.startswith("sec:"))
    async def on_section(cb: CallbackQuery) -> None:
        parts = cb.data.split(":")
        sport, date, section = parts[1], parts[2], parts[3]
        league_key = parts[4] if len(parts) > 4 else None
        if section == "reco":
            await send_two_layer(cb.message, await answer_full_reco())
            await _safe_cb_answer(cb)
            return
        cache_key_league = league_key
        analysis = None
        if cache_key_league:
            redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
            try:
                raw = await redis.get(f"analysis:{sport}:{date}:{cache_key_league}")
                analysis = json.loads(raw) if raw else None
            finally:
                await redis.aclose()
        if analysis is None:
            analysis = await load_analysis(sport, date)
        if analysis is None:
            await cb.message.answer(expired_text(sport))
            await _safe_cb_answer(cb)
            return
        if section == "deep":
            await cb.message.answer(
                "📊 경기를 선택하세요 (시작 전 경기만):",
                reply_markup=games_keyboard(analysis),
            )
        elif section == "news":
            await cb.message.answer(
                collapsed("📰 부상·속보", render_news(analysis)), parse_mode="HTML")
        elif section == "src":
            # 접힌 인용문 + 링크 프리뷰 차단. 내용은 escape된 플레인 텍스트라
            # 마크다운 파싱을 타지 않아 URL 병합이 발생하지 않는다.
            await cb.message.answer(
                collapsed("📎 출처 (펼쳐서 보기)", render_sources(analysis)),
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        elif section == "perf":
            pool = await get_pool()
            await cb.message.answer(await render_performance(pool))
        await _safe_cb_answer(cb)  # 로딩 표시 닫기

    @router.callback_query(F.data.startswith("game:"))
    async def on_game(cb: CallbackQuery) -> None:
        game_id = int(cb.data.split(":", 1)[1])
        found = None
        for sport in ("mlb", "soccer"):
            analysis = await load_analysis(sport, default_date(sport))
            if analysis:
                for g in analysis["games"]:
                    if g["game_id"] == game_id:
                        found = (g, analysis)
                        break
            if found:
                break
        if not found:
            await cb.message.answer(expired_text("soccer"))
            await _safe_cb_answer(cb)
            return
        g, analysis = found
        if await _game_needs_refresh(g):
            # [4] 종목 중립 문구 — 야구 경기에 '킥오프'가 나가지 않도록
            status_msg = await cb.message.answer("🔍 최신 조사 중... (경기 임박/캐시 만료 재리서치)")
            sport2 = "mlb" if any(x["game_id"] == g["game_id"] for x in analysis["games"]) and analysis.get("sport") == "mlb" else analysis.get("sport", "soccer")
            fresh, refreshed = await ensure_game_fresh(sport2, analysis.get("date", default_date(sport2)), g["game_id"])
            try:
                await status_msg.delete()
            except Exception:
                pass
            if fresh is not None:
                analysis = fresh
                g = next((x for x in analysis["games"] if x["game_id"] == g["game_id"]), g)
            if not refreshed:
                g = {**g, "research_status": g.get("research_status") or "stale_fallback"}
        await send_two_layer(cb.message, render_game_easy(g, analysis.get("news", "")))
        await _safe_cb_answer(cb)

    @router.callback_query(F.data == "noop")
    async def on_noop(cb: CallbackQuery) -> None:
        await _safe_cb_answer(cb)

    @router.message()
    async def on_free_text(message: Message) -> None:
        text = message.text or ""
        scope, team_info = route_query(text)
        if scope == "team":
            sport, team = team_info
            await _run_with_progress(
                message, lambda p: answer_team_query(sport, team, progress=p))
            return
        if scope == "league":
            await _league_flow(message, team_info)
            return
        if scope == "league_unsupported":
            await message.answer(unsupported_league_text())
            return
        if scope == "picks":
            await send_two_layer(message, await answer_full_reco())
            return
        if scope == "ask":
            await message.answer(ASK_TEAM_TEXT)
            return
        intent = await parse_intent(text)
        if intent.get("teams"):  # LLM이 팀을 봤는데 별칭 사전 매칭 실패 → 전체 발사 금지
            await message.answer(ASK_TEAM_TEXT)
            return
        await _card_flow(message, intent["sport"], intent["date"])

    dp = Dispatcher()
    dp.include_router(router)
    return dp


# [7-3] 폴링 하트비트 — 핸들러가 돌 때마다 갱신하고, 워치독이 정체를 감시한다.
_last_poll_tick: float = 0.0
POLL_STALL_SEC = 180        # 3분 이상 조용하면 "폴링 중단 감지"


def poll_tick() -> None:
    """폴링이 살아 있음을 표시. 업데이트 수신·주기 확인 시 호출."""
    global _last_poll_tick
    _last_poll_tick = time.monotonic()


async def _polling_watchdog() -> None:
    """폴링이 POLL_STALL_SEC 이상 멈추면 알린다.

    aiogram이 조용히 죽는 경우(네트워크·토큰 문제) 사용자는 봇이 죽은 줄도 모른다.
    """
    from app.alerts import _send

    poll_tick()
    notified = False
    while True:
        await asyncio.sleep(30)
        try:
            # getUpdates는 롱폴링이라 조용할 수 있다 → 봇 API 자체가 살아있는지로 판정
            from aiogram import Bot

            bot = Bot(token=get_settings().telegram_bot_token)
            try:
                await bot.get_me()
                poll_tick()
                notified = False
            finally:
                await bot.session.close()
        except Exception as exc:
            idle = time.monotonic() - _last_poll_tick
            if idle >= POLL_STALL_SEC and not notified:
                notified = True
                await _send("poll:stall",
                            f"🔌 폴링 중단 감지 — {int(idle // 60)}분째 응답 없음\n"
                            f"{type(exc).__name__}: {str(exc)[:150]}",
                            bypass_suppression=True)


async def run_bot() -> None:
    from aiogram import Bot

    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN이 없습니다. CLI 시뮬레이터를 사용하세요: "
            'python -m app.bot --simulate "/mlb"'
        )
    bot = Bot(token=settings.telegram_bot_token)
    dp = build_dispatcher()
    # [6] 어떤 코드가 도는지 기동 즉시 남긴다.
    #     실사고(2026-08-25): 26커밋 뒤처진 봇이 하루 넘게 돌았는데 아무도 몰랐다.
    from app.version import boot_line, staleness_line

    logger.info(boot_line("bot"))
    stale = staleness_line()
    if stale:
        logger.warning(stale)
        from app.notify import send_telegram

        await send_telegram(stale)
    logger.info("starting polling")
    # [7-3] 폴링 하트비트 — 3분 이상 멈추면 알린다
    asyncio.create_task(_polling_watchdog())
    await dp.start_polling(bot)


# ---------------------------------------------------------------- CLI 시뮬레이터

async def simulate(text: str) -> str:
    """텔레그램 없이 동일 로직 실행 — 봇이 보낼 응답 텍스트 반환."""
    if text.startswith("/mlb"):
        arg = text[len("/mlb"):].strip() or None
        return await answer_query("mlb", resolve_date_arg(arg, "mlb"))
    if text.startswith("/soccer"):
        return await answer_query("soccer")
    if text.startswith("/today"):
        return await answer_query("mlb")

    scope, team_info = route_query(text)
    if scope == "team":
        sport, team = team_info
        return await answer_team_query(sport, team)
    if scope == "league":
        return await answer_league_query(team_info)
    if scope == "league_unsupported":
        return unsupported_league_text()
    if scope == "picks":
        return await answer_full_reco()
    if scope == "ask":
        return ASK_TEAM_TEXT
    intent = await parse_intent(text)
    if intent.get("teams"):
        return ASK_TEAM_TEXT
    return await answer_query(intent["sport"], intent["date"])


async def _main() -> None:
    parser = argparse.ArgumentParser(description="AnalystBot Telegram bot")
    parser.add_argument("--simulate", metavar="TEXT", help="텔레그램 없이 명령 시뮬레이션")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.simulate:
        try:
            reply = await simulate(args.simulate)
        finally:
            await close_pool()
        for i, chunk in enumerate(split_message(reply.strip()), 1):
            print(f"--- message {i} ({len(chunk)} chars) ---")
            print(chunk)
    else:
        await run_bot()


if __name__ == "__main__":
    asyncio.run(_main())
