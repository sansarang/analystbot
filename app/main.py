"""FastAPI 앱 — 헬스체크 + 리포트 조회 (uvicorn app.main:app --reload)."""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.db import close_pool, get_pool
from app.pipeline import run_pipeline, today_kst


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().log_mock_status()
    app.state.redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await close_pool()


app = FastAPI(title="AnalystBot", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/report/{sport}")
async def report(sport: str, date: str | None = None) -> dict:
    if sport not in ("mlb", "soccer"):
        raise HTTPException(404, "sport must be 'mlb' or 'soccer'")
    pool = await get_pool()
    text = await run_pipeline(pool, app.state.redis, sport=sport, date=date or today_kst())
    return {"sport": sport, "date": date or today_kst(), "report": text}
