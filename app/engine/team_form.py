"""팀 경기력 분석 — 낮 프리페치 1회, Redis `form:{league}:{team}:{date}`.

성공 TTL 48h. unavailable 은 30분 + cause(credit_400/timeout/parse_fail).
로드 시 unavailable 은 캐시 히트가 아니다 — 48시간 추천 탈락을 막는다.
크레딧 400은 재시도하지 않고 프로세스를 중단한다.

모델: `MODEL_TEAM_FORM`(기본 Haiku). Judge(--old) 모델은 여기 쓰지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

import anthropic

from app.collectors.base import ApiQuotaError, is_quota_error
from app.config import get_settings
from app.engine.prompts import TEAM_FORM, fill

logger = logging.getLogger(__name__)

FORM_TTL = 48 * 3600
# 일시 장애가 48시간 추천 탈락으로 번지지 않게. 성공 캐시(48h)와 분리.
FORM_UNAVAILABLE_TTL = 30 * 60
CAUSE_CREDIT = "credit_400"
CAUSE_TIMEOUT = "timeout"
CAUSE_PARSE = "parse_fail"
# API 실패(타임아웃·5xx) 초기 대기. 최대 2회 재시도 → 1s 후, 2s 후.
_RETRY_BACKOFF = (1.0, 2.0)
LAST_USAGE: dict = {}


def _loads_dict(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None


def parse_json_object(text: str) -> dict | None:
    """thinking·산문이 섞여도 첫 `{`부터 마지막 `}`까지 JSON 객체를 회수한다.

    잘린 JSON은 회수하지 않는다 — 그때는 max_tokens를 늘린다 (매치업 4000).
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    obj = _loads_dict(raw)
    if obj is not None:
        return obj
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    return _loads_dict(raw[start:end + 1])


def form_key(league: str, team: str, date: str) -> str:
    return f"form:{league}:{team}:{date}"


def analysis_game_key(league: str, game_id, date: str) -> str:
    return f"analysis:{league}:{game_id}:{date}"


def _sampling_allowed(model: str) -> bool:
    """실측 2026-08-29: claude-sonnet-5 는 extra_body temperature=0 이 400.

    '`temperature` is deprecated for this model.'
    문서: non-default sampling → 400. 생략만 허용. Haiku 4.5는 0이 통과했다.
    """
    m = (model or "").lower()
    return "claude-sonnet-5" not in m


def message_kwargs(model: str, max_tokens: int, prompt: str) -> dict:
    """Anthropic SDK 1.0은 temperature 인자를 제거했다.

    샘플링이 되는 모델은 extra_body로 0을 고정한다. 재판정 dedupe 전제.
    모델이 거절하면 보내지 않는다 — 임의로 온도를 올리는 것이 아니다.
    """
    kw = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if _sampling_allowed(model):
        kw["extra_body"] = {"temperature": 0}
    return kw


def _retryable_api(exc: BaseException) -> bool:
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        code = getattr(exc, "status_code", None)
        if code is None:
            resp = getattr(exc, "response", None)
            code = getattr(resp, "status_code", None)
        try:
            n = int(code)
        except (TypeError, ValueError):
            return False
        return n == 429 or 500 <= n < 600
    return False


def fail_cause(exc: BaseException | None) -> str:
    """unavailable.cause. 세 값만: credit_400 / timeout / parse_fail."""
    if exc is None:
        return CAUSE_PARSE
    if isinstance(exc, ApiQuotaError):
        return CAUSE_CREDIT
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError,
                        TimeoutError, asyncio.TimeoutError)):
        return CAUSE_TIMEOUT
    if isinstance(exc, anthropic.APIStatusError):
        code = getattr(exc, "status_code", None)
        if code is None:
            resp = getattr(exc, "response", None)
            code = getattr(resp, "status_code", None)
        body = str(exc)
        if is_quota_error(int(code or 0), body):
            return CAUSE_CREDIT
        try:
            n = int(code)
        except (TypeError, ValueError):
            return CAUSE_PARSE
        if 500 <= n < 600:
            return CAUSE_TIMEOUT
    return CAUSE_PARSE


def form_cache_usable(obj) -> bool:
    """unavailable 캐시는 히트가 아니다. 재시도 대상."""
    return isinstance(obj, dict) and not obj.get("unavailable")


async def _redis():
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception:
        return None


async def _paid_ok(role: str) -> bool:
    """Anthropic 호출 전 캡 확인 + 사용 기록. 캡을 넘으면 False."""
    from app.llm.judge_route import note_paid_call, paid_allowed

    r = await _redis()
    try:
        if not await paid_allowed(r):
            return False
        await note_paid_call(r, role)
        return True
    finally:
        if r is not None:
            try:
                await r.aclose()
            except Exception:
                pass


async def _complete_free(routes, prompt: str, max_tokens: int,
                         role: str) -> str | None:
    """무료 사슬을 순서대로. 전부 실패하면 None (호출부가 유료로 내려간다)."""
    from app.llm.openai_compat import complete

    for provider, model in routes:
        if provider == "anthropic":
            break
        r = await complete(provider, model, prompt, max_tokens=max_tokens)
        logger.info("[%s] free provider=%s model=%s ok=%s %.1fs%s",
                    role, provider, model, r["ok"], r["elapsed"],
                    f" err={str(r['error'])[:120]}" if r["error"] else "")
        if r["ok"]:
            u = r.get("usage") or {}
            LAST_USAGE.clear()
            LAST_USAGE.update({"role": role, "model": f"{provider}/{model}",
                               "input_tokens": u.get("prompt_tokens"),
                               "output_tokens": u.get("completion_tokens"),
                               "stop_reason": "free"})
            return r["text"]
    logger.warning("[%s] 무료 provider 전부 실패 — 유료 폴백 검토", role)
    return None


async def complete_json(prompt: str, *, model: str, max_tokens: int,
                        role: str = "form", mock: bool | None = None) -> str:
    """폼·매치업 전용. Judge 모델·토큰을 쓰지 않는다. 도구 없이 본문 JSON만."""
    from app.engine.credit_guard import abort_if_credit_gone, trip_credit

    settings = get_settings()
    if settings.mock_judge if mock is None else mock:
        return ""
    # [무료 전환 2026-09-04] provider 라우팅. `JUDGE_PROVIDER=anthropic` 이면
    #   아래 종전 경로가 그대로 돈다 — **경로를 지우지 않았다.**
    from app.llm.judge_route import chain

    routes = chain(role)
    if routes and routes[0][0] != "anthropic":
        out = await _complete_free(routes, prompt, max_tokens, role)
        if out is not None:
            return out
        # 무료가 전부 실패했다 — 캡 안에서만 유료로 내려간다.
    abort_if_credit_gone(role)
    if not await _paid_ok(role):
        raise ApiQuotaError(f"anthropic({role})", "일일 캡 도달 — 호출 차단")
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    n_chars = len(prompt or "")
    kwargs = message_kwargs(model, max_tokens, prompt)
    last_exc: BaseException | None = None
    # 최초 1회 + 재시도 최대 2회
    for attempt in range(3):
        try:
            resp = await client.messages.create(**kwargs)
            last_exc = None
            break
        except anthropic.APIStatusError as exc:
            if is_quota_error(exc.status_code, str(exc)):
                err = ApiQuotaError(f"anthropic({role})", str(exc))
                trip_credit(role, err)
                raise err from exc
            last_exc = exc
            if not _retryable_api(exc) or attempt == 2:
                logger.warning("[%s] API 실패 model=%s prompt_chars=%d: %s",
                               role, model, n_chars, exc)
                raise
        except Exception as exc:
            last_exc = exc
            if not _retryable_api(exc) or attempt == 2:
                logger.warning("[%s] API 실패 model=%s prompt_chars=%d: %s",
                               role, model, n_chars, exc)
                raise
        wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
        logger.warning("[%s] API 재시도 %d/2 model=%s prompt_chars=%d wait=%.1fs: %s",
                       role, attempt + 1, model, n_chars, wait, last_exc)
        await asyncio.sleep(wait)
    else:
        raise last_exc or RuntimeError(f"{role} API 실패")
    parts = []
    thoughts = []
    for block in resp.content:
        kind = getattr(block, "type", None)
        if kind == "text":
            parts.append(block.text or "")
        elif kind == "thinking":
            thoughts.append(getattr(block, "thinking", None) or "")
    usage = getattr(resp, "usage", None)
    in_t = getattr(usage, "input_tokens", None) if usage else None
    out_t = getattr(usage, "output_tokens", None) if usage else None
    stop = getattr(resp, "stop_reason", None)
    logger.info("[%s] tokens input=%s output=%s stop=%s model=%s prompt_chars=%d",
                role, in_t, out_t, stop, model, n_chars)
    LAST_USAGE.clear()
    LAST_USAGE.update({"role": role, "model": model, "input_tokens": in_t,
                       "output_tokens": out_t, "stop_reason": stop})
    body = "\n".join(parts)
    if body.strip():
        return body
    # 본문 텍스트가 비면 thinking 안에서 JSON을 회수한다.
    return "\n".join(thoughts)


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
        "model": "mock",
    }


def unavailable_form(team: str, model: str | None = None,
                     cause: str | None = None) -> dict:
    out = {"team": team, "unavailable": True}
    if model:
        out["model"] = model
    if cause:
        out["cause"] = cause
    return out


#: 폼 프롬프트에 실을 원문 상한. 넘기면 프롬프트가 커져 max_tokens 여유를 먹는다.
NEWS_BODY_MAX = 6           # 인용 개수
NEWS_BODY_CHARS = 220       # 인용 1건 길이


def with_news_bodies(headlines, research: dict):
    """헤드라인 + 수집된 원문. 원문이 없으면 헤드라인 그대로 돌려준다.

    ⚠️ **가공하지 않는다.** 문장·URL을 그대로 넘긴다 — 요약하면 판정이
       우리의 요약을 사실로 읽는다(kbo_news.merge_into_research와 같은 태도).
    ⚠️ 개수·길이를 자른다. 원문을 통째로 실으면 프롬프트가 부풀어 정작
       박스스코어가 밀린다.
    """
    quotes = (research or {}).get("news_quotes") or []
    bodies = []
    for q in quotes[:NEWS_BODY_MAX]:
        if not isinstance(q, dict):
            continue
        txt = str(q.get("text") or "").strip()
        if not txt:
            continue
        bodies.append({"원문": txt[:NEWS_BODY_CHARS], "출처": q.get("url")})
    if not bodies:
        return headlines
    return {"헤드라인": headlines, "원문": bodies}


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
            if form_cache_usable(cached):
                return cached
    settings = get_settings()
    is_mock = settings.mock_judge if mock is None else mock
    if is_mock:
        out = _mock_form(team)
        await redis.set(key, json.dumps(out, ensure_ascii=False), ex=FORM_TTL)
        return out

    from app.engine.credit_guard import abort_if_credit_gone, trip_credit

    abort_if_credit_gone(f"form:{league}:{team}")
    news = news if news is not None else []
    model = settings.team_form_model
    prompt = fill(
        TEAM_FORM,
        TEAM_NAME=team,
        GAMES_JSON=json.dumps(games_packet, ensure_ascii=False, default=str),
        NEWS_HEADLINES=json.dumps(news, ensure_ascii=False, default=str),
    )
    out = None
    last_cause = CAUSE_PARSE
    for attempt in (1, 2):
        try:
            text = await complete_json(
                prompt, model=model, max_tokens=settings.team_form_max_tokens,
                role="form", mock=False)
        except ApiQuotaError as exc:
            logger.warning("[form] %s %s 크레딧 소진 model=%s prompt_chars=%d: %s",
                           league, team, model, len(prompt), exc)
            trip_credit(f"form:{league}:{team}", exc)
            out = unavailable_form(team, model, CAUSE_CREDIT)
            await redis.set(key, json.dumps(out, ensure_ascii=False),
                            ex=FORM_UNAVAILABLE_TTL)
            raise
        except Exception as exc:
            last_cause = fail_cause(exc)
            logger.warning("[form] %s %s 호출 실패 %d회 model=%s prompt_chars=%d cause=%s: %s",
                           league, team, attempt, model, len(prompt), last_cause, exc)
            if attempt < 2:
                continue
            break
        parsed = parse_json_object(text)
        if parsed and parsed.get("unavailable") is not True:
            parsed["unavailable"] = False
            parsed.setdefault("team", team)
            parsed["model"] = model
            out = parsed
            break
        last_cause = CAUSE_PARSE
        # 🔴 [계측 2026-09-04] **원문을 남긴다.** 15:04 프리페치에서 폼이
        #    7/10 파싱 실패했는데, 절단 가설을 실측으로 반증했고(1500토큰에서도
        #    정상 파싱) 무엇이 왔는지 알 방법이 없었다.
        #    ENGINEERING §3: 재현 없는 수정 금지 — 재현이 안 되면 계측을 먼저.
        logger.warning("[form] %s %s JSON 파싱 실패 %d회 model=%s "
                       "prompt_chars=%d resp_chars=%d 앞=%r 뒤=%r",
                       league, team, attempt, model, len(prompt),
                       len(text or ""), (text or "")[:200], (text or "")[-200:])
    if out is None:
        out = unavailable_form(team, model, last_cause)
    ttl = FORM_TTL if not out.get("unavailable") else FORM_UNAVAILABLE_TTL
    await redis.set(key, json.dumps(out, ensure_ascii=False), ex=ttl)
    return out


async def load_form(redis, league: str, team: str, date: str) -> dict | None:
    raw = await redis.get(form_key(league, team, date))
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not form_cache_usable(obj):
        return None
    return obj


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
                # [v1.1 3단계] 헤드라인만 넘기면 태그 압축 과정에서 "왜"가 죽는다.
                #   수집된 원문(news_quotes)을 함께 넘겨 판정이 근거를 읽게 한다.
                #   (실측 사례: "동료들이 바즈를 옹호" 같은 정성 정보가 판정을 갈랐다)
                news = with_news_bodies(news, research)
                pkt = packet_from_usage(team, sport, date, usage)
                try:
                    form = await analyze_team(
                        redis, sport, team, date, pkt, news, force=force, mock=mock)
                except ApiQuotaError:
                    logger.error("[form] 크레딧 소진 — 슬레이트 중단 sport=%s done=%s remaining_at=%s",
                                 sport, list(out), team)
                    raise
                out[team] = form
            else:
                form = out[team]
            g[f"{side}_form"] = form
            if form.get("unavailable"):
                g["form_unavailable"] = True
    return out
