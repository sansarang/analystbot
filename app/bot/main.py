"""aiogram 3.x 텔레그램 봇 — /mlb /soccer /today + 자유 질문(의도 파싱).

- 토큰 없으면 CLI 시뮬레이터로 검증: python -m app.bot --simulate "/mlb"
- 4096자 초과 응답은 분할 전송, 캐시 히트 시 즉시 응답.
"""

import argparse
import asyncio
import json
import logging
import re

import anthropic
import redis.asyncio as aioredis

from app.collectors.base import ApiQuotaError, is_quota_error
from app.config import get_settings
from app.db import close_pool, get_pool
from app.notify import notify_quota
from app.pipeline import run_pipeline, today_kst

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


async def answer_query(sport: str, date: str | None = None) -> str:
    """파이프라인 실행(캐시 우선) → 리포트 텍스트.

    API 크레딧/쿼터 소진 시 크래시 대신 사용자에게 상황을 알리는 메시지를 반환하고,
    관리자 채팅으로도 알림을 보낸다.
    """
    pool = await get_pool()
    redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return await run_pipeline(pool, redis, sport=sport, date=date or today_kst())
    except ApiQuotaError as exc:
        logger.error("[bot] quota exhausted: %s", exc)
        await notify_quota(exc.service, exc.detail)
        return (
            f"⚠️ {exc.service} API 사용량/크레딧이 소진되어 분석을 완료하지 못했습니다.\n"
            f"키를 충전하거나 교체한 뒤 다시 시도해 주세요.\n"
            f"(상세: {exc.detail[:120]})"
        )
    finally:
        await redis.aclose()


# ---------------------------------------------------------------- 텔레그램 연결

def build_dispatcher():
    from aiogram import Dispatcher, Router
    from aiogram.filters import Command, CommandStart
    from aiogram.types import Message

    router = Router()

    async def _reply(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk)

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        await message.answer(
            "AnalystBot입니다. /mlb /soccer /today 또는 자유 질문으로 분석을 요청하세요.\n"
            "※ 분석 정보용 도구이며 베팅 손실 책임은 이용자에게 있습니다."
        )

    @router.message(Command("mlb"))
    async def on_mlb(message: Message) -> None:
        await _reply(message, await answer_query("mlb"))

    @router.message(Command("soccer"))
    async def on_soccer(message: Message) -> None:
        await _reply(message, await answer_query("soccer"))

    @router.message(Command("today"))
    async def on_today(message: Message) -> None:
        await _reply(message, await answer_query("mlb", today_kst()))

    @router.message()
    async def on_free_text(message: Message) -> None:
        intent = await parse_intent(message.text or "")
        await _reply(message, await answer_query(intent["sport"], intent["date"]))

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
        reply = await answer_query("mlb")
    elif text.startswith("/soccer"):
        reply = await answer_query("soccer")
    elif text.startswith("/today"):
        reply = await answer_query("mlb", today_kst())
    else:
        intent = await parse_intent(text)
        reply = await answer_query(intent["sport"], intent["date"])
    return reply


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
        for i, chunk in enumerate(split_message(reply), 1):
            print(f"--- message {i} ({len(chunk)} chars) ---")
            print(chunk)
    else:
        await run_bot()


if __name__ == "__main__":
    asyncio.run(_main())
