"""aiogram 3.x 텔레그램 봇 — /mlb /soccer /today + 자유 질문(의도 파싱).

- 토큰 없으면 CLI 시뮬레이터로 검증: python -m app.bot --simulate "/mlb"
- 4096자 초과 응답은 분할 전송, 캐시 히트 시 즉시 응답.
"""

import argparse
import asyncio
import json
import logging
import re

from datetime import datetime, timedelta

import anthropic
import redis.asyncio as aioredis

from app.bot.aliases import find_team
from app.collectors.base import ApiQuotaError, is_quota_error
from app.config import get_settings
from app.db import close_pool, get_pool
from app.notify import notify_quota
from app.pipeline import (
    SECTION_SEP,
    build_analysis,
    mlb_slate_date,
    render_game_section,
    run_pipeline,
    today_kst,
)

ASK_TEAM_TEXT = (
    "어느 팀 경기인지 못 찾았어요. 예: 다저스, 양키스, 맨시티\n"
    "전체 리포트는 /mlb 또는 /soccer 를 입력하세요."
)

logger = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096

INTENT_SYSTEM = """사용자의 스포츠 분석 요청에서 의도를 추출해 JSON으로만 답하라.
스키마: {"sport": "mlb"|"soccer", "date": "YYYY-MM-DD"|null, "teams": [문자열], "depth": "brief"|"full"}
날짜 언급이 없으면 null. 팀 언급이 없으면 빈 배열."""


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


def route_query(text: str, llm_teams: list | None = None) -> tuple[str, tuple[str, str] | None]:
    """자유 질문의 범위 인식: team(1경기) | picks(EV 픽만) | ask(되묻기) | full(전체)."""
    team = find_team(text)
    if team:
        return "team", team
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
    date = m.group(1) if m else None
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
            await notify_quota("anthropic(intent)", str(exc))
        else:
            logger.warning("[bot] live intent parse failed, using rule-based: %s", exc)
        return parse_intent_mock(text)


async def _parse_intent_live(text: str, settings) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.intent_model,
        max_tokens=300,
        system=INTENT_SYSTEM,
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
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def _quota_reply(exc: ApiQuotaError) -> str:
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
    except ApiQuotaError as exc:
        logger.error("[bot] quota exhausted: %s", exc)
        await notify_quota(exc.service, exc.detail)
        return _quota_reply(exc)
    finally:
        await redis.aclose()


def _format_team_reply(game: dict, news: str, sport: str) -> str:
    text = render_game_section(game, news)
    urls = sorted({
        ep["source_url"] for ep in game.get("expert_picks", []) if ep.get("source_url")
    })
    if urls:
        text += "\n📎 출처\n" + "\n".join(f"  {u}" for u in urls)
    text += f"\n\n전체 슬레이트는 /{'mlb' if sport == 'mlb' else 'soccer'}"
    return text


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
            game = next(
                (g for g in data.get("games", []) if team in (g["home"], g["away"])), None
            )
            if game:
                logger.info("[bot] team query served from slate cache: %s", team)
                return _format_team_reply(game, data.get("news", ""), sport)
        analysis = await build_analysis(pool, sport, date, team=team, progress=progress)
        if not analysis["games"]:
            return f"오늘({date}) {team} 경기를 찾지 못했습니다."
        return _format_team_reply(analysis["games"][0], analysis["news"], sport)
    except ApiQuotaError as exc:
        logger.error("[bot] quota exhausted: %s", exc)
        await notify_quota(exc.service, exc.detail)
        return _quota_reply(exc)
    finally:
        await redis.aclose()


async def answer_picks_only(sport: str = "mlb", progress=None) -> str:
    """'오늘 픽/언더독' 류 질문 → 일정+EV픽+조합 파트만."""
    report = await answer_query(sport, progress=progress)
    part1 = report.split(SECTION_SEP)[0]
    return part1 + "\n\n(경기별 심층 분석과 출처는 /mlb 전체 리포트에서)"


# ---------------------------------------------------------------- 텔레그램 연결

def build_dispatcher():
    from aiogram import Dispatcher, Router
    from aiogram.filters import Command, CommandObject, CommandStart
    from aiogram.types import Message

    router = Router()

    async def _reply(message: Message, text: str) -> None:
        # 3분할(<<<PART>>>) 우선, 각 파트가 4096자를 넘으면 추가 분할
        for part in text.split(SECTION_SEP):
            for chunk in split_message(part.strip()):
                if chunk:
                    await message.answer(chunk)

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

    @router.message(Command("mlb"))
    async def on_mlb(message: Message, command: CommandObject) -> None:
        # 기본: 미국 동부 오늘. 인자: tomorrow/내일/어제 또는 YYYY-MM-DD
        date = resolve_date_arg(command.args, "mlb")
        await _run_with_progress(message, lambda p: answer_query("mlb", date, progress=p))

    @router.message(Command("soccer"))
    async def on_soccer(message: Message) -> None:
        await _run_with_progress(message, lambda p: answer_query("soccer", progress=p))

    @router.message(Command("today"))
    async def on_today(message: Message) -> None:
        await _run_with_progress(message, lambda p: answer_query("mlb", progress=p))

    @router.message()
    async def on_free_text(message: Message) -> None:
        text = message.text or ""
        scope, team_info = route_query(text)
        if scope == "team":
            sport, team = team_info
            await _run_with_progress(
                message, lambda p: answer_team_query(sport, team, progress=p))
            return
        if scope == "picks":
            await _run_with_progress(message, lambda p: answer_picks_only("mlb", progress=p))
            return
        if scope == "ask":
            await message.answer(ASK_TEAM_TEXT)
            return
        intent = await parse_intent(text)
        if intent.get("teams"):  # LLM이 팀을 봤는데 별칭 사전 매칭 실패 → 전체 발사 금지
            await message.answer(ASK_TEAM_TEXT)
            return
        await _run_with_progress(
            message, lambda p: answer_query(intent["sport"], intent["date"], progress=p))

    dp = Dispatcher()
    dp.include_router(router)
    return dp


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
    logger.info("starting polling")
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
    if scope == "picks":
        return await answer_picks_only("mlb")
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
        i = 0
        for part in reply.split(SECTION_SEP):
            for chunk in split_message(part.strip()):
                if not chunk:
                    continue
                i += 1
                print(f"--- message {i} ({len(chunk)} chars) ---")
                print(chunk)
    else:
        await run_bot()


if __name__ == "__main__":
    asyncio.run(_main())
