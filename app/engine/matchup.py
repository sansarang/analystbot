"""매치업 판정 — 라인업 확정 시 경기당 1회. 팀 폼 캐시 히트면 재호출하지 않는다."""
from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.engine.prompts import MATCHUP, fill
from app.engine.team_form import (
    FORM_TTL,
    analysis_game_key,
    complete_json,
    parse_json_object,
)

logger = logging.getLogger(__name__)

CONF_MAP = {"상": "high", "중": "medium", "하": "low"}


def clip_p_home(p, settings=None) -> float:
    """프롬프트가 벗어나도 코드에서 0.32–0.68로 자른다."""
    s = settings or get_settings()
    try:
        val = float(p)
    except (TypeError, ValueError):
        val = 0.5
    lo, hi = s.min_win_prob_mlb, s.max_win_prob_mlb
    return max(lo, min(hi, val))


def _mock_matchup(home: str, away: str) -> dict:
    return {
        "p_home": 0.55,
        "우세": "home",
        "근거": [
            f"홈 평가서 {home} 흐름 유지",
            f"원정 평가서 {away} 표본 3경기",
            "오늘 선발 최근 등판 목 모드",
        ],
        "변수": ["목 모드"],
        "뉴스반영": {"적용": False, "조정폭": "0", "사유": "목 모드"},
        "확신도": "중",
        "model": "mock",
    }


def lineups_payload(jg: dict) -> dict:
    r = jg.get("research") or {}
    return {
        "home": {
            "pitcher": ((r.get("home_pitcher") or {}).get("name")
                        or jg.get("home_pitcher")),
            "order": (r.get("home_lineup") or {}).get("order") or jg.get("lineup_home"),
        },
        "away": {
            "pitcher": ((r.get("away_pitcher") or {}).get("name")
                        or jg.get("away_pitcher")),
            "order": (r.get("away_lineup") or {}).get("order") or jg.get("lineup_away"),
        },
    }


def starters_recent_payload(jg: dict) -> dict:
    r = jg.get("research") or {}
    return {
        "home": r.get("home_starter_recent") or [],
        "away": r.get("away_starter_recent") or [],
    }


def apply_matchup(jg: dict, verdict: dict, settings=None) -> None:
    s = settings or get_settings()
    p = clip_p_home(verdict.get("p_home"), s)
    conf_kr = verdict.get("확신도") or "중"
    model = verdict.get("model") or s.matchup_model
    jg["p_claude"] = p
    jg["matchup"] = {**verdict, "p_home": p, "model": model}
    jg["model"] = model
    jg["judge_confidence"] = CONF_MAP.get(conf_kr, "medium")
    jg["judge_pass"] = conf_kr == "하"
    reasons = verdict.get("근거") or []
    jg["verdict"] = " ".join(str(x) for x in reasons) or "매치업 판정"
    jg["form_unavailable"] = False


async def persist_matchup_record(redis, jg: dict, date: str) -> None:
    """analysis:{league}:{game_id}:{date} 에 사용 모델 ID를 남긴다."""
    if redis is None:
        return
    sport = jg.get("sport") or ""
    gid = jg.get("game_id")
    if not sport or gid is None:
        return
    m = jg.get("matchup") or {}
    blob = {
        "model": jg.get("model") or m.get("model"),
        "p_home": jg.get("p_claude"),
        "우세": m.get("우세"),
    }
    try:
        await redis.set(
            analysis_game_key(sport, gid, date),
            json.dumps(blob, ensure_ascii=False, default=str),
            ex=FORM_TTL)
    except Exception as exc:
        logger.warning("[matchup] analysis 키 기록 실패 game=%s: %s", gid, exc)


async def _form_or_analyze(jg: dict, redis, date: str, side: str, mock: bool | None):
    """캐시 히트면 그대로. 미스면 그 자리에서 팀 분석 후 저장."""
    from app.engine.team_form import analyze_team, load_form, packet_from_usage

    sport = jg.get("sport") or ""
    team = jg.get(side) or ""
    cached = await load_form(redis, sport, team, date)
    if cached is not None:
        return cached
    research = jg.get("research") or {}
    usage = research.get(f"{side}_usage") or {}
    news = research.get(f"{side}_news") or research.get("news") or []
    if isinstance(news, dict):
        news = news.get("headlines") or []
    pkt = packet_from_usage(team, sport, date, usage)
    logger.info("[matchup] %s %s 폼 캐시 미스 — 현장 분석", sport, team)
    return await analyze_team(redis, sport, team, date, pkt, news, mock=mock)


async def judge_matchup(jg: dict, redis, date: str, *,
                        mock: bool | None = None) -> dict | None:
    """form: 히트면 재분석하지 않는다. 미스면 팀 분석을 한 뒤 매치업을 돌린다."""
    from app.engine.scoring import BASEBALL_SPORTS

    sport = jg.get("sport") or ""
    if sport not in BASEBALL_SPORTS:
        return None
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        jg["judgement_void"] = True
        return None
    settings = get_settings()
    is_mock = settings.mock_judge if mock is None else mock
    home, away = jg.get("home") or "", jg.get("away") or ""
    home_form = await _form_or_analyze(jg, redis, date, "home", mock)
    away_form = await _form_or_analyze(jg, redis, date, "away", mock)
    if not home_form or home_form.get("unavailable") or not away_form \
            or away_form.get("unavailable"):
        jg["form_unavailable"] = True
        logger.info("[matchup] %s vs %s 폼 없음·불가 — 추천 탈락", home, away)
        return None
    if is_mock:
        verdict = _mock_matchup(home, away)
        apply_matchup(jg, verdict, settings)
        await persist_matchup_record(redis, jg, date)
        return verdict

    model = settings.matchup_model
    prompt = fill(
        MATCHUP,
        HOME_FORM_JSON=json.dumps(home_form, ensure_ascii=False, default=str),
        AWAY_FORM_JSON=json.dumps(away_form, ensure_ascii=False, default=str),
        LINEUPS_JSON=json.dumps(lineups_payload(jg), ensure_ascii=False, default=str),
        STARTERS_RECENT_JSON=json.dumps(
            starters_recent_payload(jg), ensure_ascii=False, default=str),
    )
    parsed = None
    for attempt in (1, 2):
        try:
            text = await complete_json(
                prompt, model=model, max_tokens=settings.matchup_max_tokens,
                role="matchup", mock=False)
        except Exception as exc:
            logger.warning("[matchup] 호출 실패 %d회 model=%s prompt_chars=%d: %s",
                           attempt, model, len(prompt), exc)
            text = ""
        parsed = parse_json_object(text)
        if parsed and "p_home" in parsed:
            parsed["model"] = model
            break
        parsed = None
        logger.warning("[matchup] JSON 파싱 실패 %d회 model=%s prompt_chars=%d",
                       attempt, model, len(prompt))
    if parsed is None:
        jg["form_unavailable"] = True
        logger.warning("[matchup] %s vs %s 분석 불가 model=%s — 추천 탈락",
                       home, away, model)
        return None
    apply_matchup(jg, parsed, settings)
    await persist_matchup_record(redis, jg, date)
    return parsed
