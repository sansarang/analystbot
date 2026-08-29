"""팀 경기력 분석 — 낮 프리페치 1회, Redis `form:{league}:{team}:{date}` TTL 48h.

라인업과 무관하다. 저녁 재판정에서 재호출하지 않는다.
JSON 파싱 실패 시 1회 재시도, 재실패면 unavailable — 그 팀 경기는 추천 탈락.
"""
from __future__ import annotations

import json
import logging
import re

import anthropic

from app.collectors.base import ApiQuotaError, is_quota_error
from app.config import get_settings
from app.engine.judge import JUDGE_MAX_TOKENS, MODEL_LADDER
from app.engine.prompts import TEAM_FORM, fill

logger = logging.getLogger(__name__)

FORM_TTL = 48 * 3600
_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def form_key(league: str, team: str, date: str) -> str:
    return f"form:{league}:{team}:{date}"


def parse_json_object(text: str) -> dict | None:
    """모델이 백틱을 붙여도 첫 객체만 취한다. 못 읽으면 None."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        m = _JSON_OBJ.search(raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None


async def complete_json(prompt: str, *, mock: bool | None = None) -> str:
    """Judge와 같은 모델·쿼터 처리. 도구 없이 본문 JSON만 받는다."""
    settings = get_settings()
    if settings.mock_judge if mock is None else mock:
        return ""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = settings.judge_model

    async def _create(model_id: str):
        return await client.messages.create(
            model=model_id,
            max_tokens=JUDGE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

    try:
        try:
            resp = await _create(model)
        except anthropic.NotFoundError:
            available = {m.id async for m in client.models.list()}
            model = next((c for c in MODEL_LADDER if c in available), model)
            resp = await _create(model)
    except anthropic.APIStatusError as exc:
        if is_quota_error(exc.status_code, str(exc)):
            raise ApiQuotaError("anthropic(form)", str(exc)) from exc
        raise
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text or "")
    return "\n".join(parts)


def _mock_form(team: str) -> dict:
    return {
        "team": team,
        "타선": {"평가": "중", "설명": "목 모드 3경기 경향"},
        "선발진": {"평가": "중", "설명": "목 모드 선발 경향"},
        "불펜": {"소모도": "보통", "설명": "목 모드 불펜"},
        "흐름": "유지",
        "변수": [],
        "뉴스태그": [],
        "종합": "목 모드 평가서",
        "unavailable": False,
    }


def unavailable_form(team: str) -> dict:
    return {"team": team, "unavailable": True}


async def analyze_team(redis, league: str, team: str, date: str,
                       games_packet, news=None, *, force: bool = False,
                       mock: bool | None = None) -> dict:
    """캐시가 있으면 재호출하지 않는다. force는 테스트·명시 재분석만."""
    key = form_key(league, team, date)
    if not force:
        raw = await redis.get(key)
        if raw:
            try:
                cached = json.loads(raw)
            except json.JSONDecodeError:
                cached = None
            if isinstance(cached, dict):
                return cached
    settings = get_settings()
    is_mock = settings.mock_judge if mock is None else mock
    if is_mock:
        out = _mock_form(team)
        await redis.set(key, json.dumps(out, ensure_ascii=False), ex=FORM_TTL)
        return out

    news = news if news is not None else []
    prompt = fill(
        TEAM_FORM,
        TEAM_NAME=team,
        GAMES_JSON=json.dumps(games_packet, ensure_ascii=False, default=str),
        NEWS_HEADLINES=json.dumps(news, ensure_ascii=False, default=str),
    )
    out = None
    for attempt in (1, 2):
        try:
            text = await complete_json(prompt, mock=False)
        except Exception as exc:
            logger.warning("[form] %s %s 호출 실패 %d회: %s", league, team, attempt, exc)
            text = ""
        parsed = parse_json_object(text)
        if parsed and parsed.get("unavailable") is not True:
            parsed["unavailable"] = False
            parsed.setdefault("team", team)
            out = parsed
            break
        logger.warning("[form] %s %s JSON 파싱 실패 %d회", league, team, attempt)
    if out is None:
        out = unavailable_form(team)
    await redis.set(key, json.dumps(out, ensure_ascii=False), ex=FORM_TTL)
    return out


async def load_form(redis, league: str, team: str, date: str) -> dict | None:
    raw = await redis.get(form_key(league, team, date))
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def packet_from_usage(team: str, league: str, date: str, usage: dict | None) -> dict:
    """수집기가 준 3경기 패킷. 없는 칸을 만들지 않는다."""
    u = usage or {}
    games = u.get("games")
    return {
        "team": team,
        "league": league,
        "as_of": date,
        "results_l3": u.get("results_l3"),
        "score_games": u.get("score_games"),
        "games": games if isinstance(games, list) else [],
    }


async def analyze_games(redis, sport: str, date: str, games: list[dict],
                        *, force: bool = False, mock: bool | None = None) -> dict:
    """당일 슬레이트 팀당 1회. 반환: {team: form_dict}."""
    out: dict[str, dict] = {}
    seen: set[str] = set()
    for g in games:
        for side in ("home", "away"):
            team = g.get(side)
            if not team:
                continue
            if team not in seen:
                seen.add(team)
                research = g.get("research") or {}
                usage = research.get(f"{side}_usage") or {}
                news = research.get(f"{side}_news") or research.get("news") or []
                if isinstance(news, dict):
                    news = news.get("headlines") or []
                pkt = packet_from_usage(team, sport, date, usage)
                form = await analyze_team(
                    redis, sport, team, date, pkt, news, force=force, mock=mock)
                out[team] = form
            else:
                form = out[team]
            g[f"{side}_form"] = form
            if form.get("unavailable"):
                g["form_unavailable"] = True
    return out
