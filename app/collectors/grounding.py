"""[상황 변수 2026-09-06] Gemini 검색 그라운딩 — 구글 검색 전체를 눈으로 쓴다.

RSS 는 Google News 색인 안에서만 본다. 그라운딩은 **웹 검색 결과 전체**를
훑으므로 지역지·구단 공지·커뮤니티까지 닿는다.

🔴 **요약을 쓰지 않는다. URL 만 취한다.**
   모델이 만든 문장은 판정 재료가 될 수 없다 — 그것이 이 저장소가 자료1·2에서
   이미 겪은 실패다("수치는 있는 그대로, 분석만 AI"). 여기서는 모델을
   **검색 엔진으로만** 쓰고, 제목은 **실제 페이지에서 직접 읽는다.**

🔴 **fetch 200 을 통과한 것만 적재한다.** 모델이 URL 을 지어내도 그 주소는
   열리지 않는다 — 환각 방어의 마지막 관문이 이것이다.

⚠️ 비용: **경기당 1회 고정** + 일일 캡. 캡을 넘으면 조용히 0건이 아니라
   로그 한 줄을 남기고 멈춘다.
"""
from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

#: 하루 호출 카운터 · 경기당 1회 표식. 둘 다 KST 날짜로 끊는다.
CAP_KEY = "grounding:calls:{date}"
ONCE_KEY = "grounding:done:{sport}:{game_id}:{date}"
TTL = 26 * 3600

#: 그라운딩이 주는 URL 은 `vertexaisearch.cloud.google.com/...` 리다이렉트다.
#  실제 주소는 따라가야 나온다(실측 2026-09-06).
_REDIRECT_HOST = "vertexaisearch.cloud.google.com"

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

#: 🔴 [2026-09-06] 그라운딩 결과에는 **발행일이 없다.** 그래서 경기 전 필터가
#   못 걸리고 지난 시즌 기사("25시즌 김강민 은퇴식")가 오늘 태그로 붙었다.
#   페이지에서 직접 읽는다 — 대부분의 언론사가 이 메타를 준다.
_PUB_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|'
    r'og:pubdate|pubdate|date|datePublished)["\'][^>]*content=["\']([^"\']+)',
    re.I)
_PUB_JSONLD = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I)

#: 백과·정적 문서 — 뉴스가 아니다. 오늘의 공기를 말해주지 않는다.
#  ⚠️ 사이트를 **막기 위한** 목록이 아니라 **뉴스가 아닌 것을 거르는** 목록이다.
_NON_NEWS_HOSTS = ("namu.wiki", "wikipedia.org", "wikiwand.com", "fandom.com",
                   "dbpedia.org", "youtube.com", "instagram.com")

#: 그라운딩 결과가 이보다 오래되면 버린다. RSS 와 같은 창을 쓴다.
MAX_AGE_HOURS = 72

TIMEOUT = 20.0
FETCH_TIMEOUT = 12.0
MAX_URLS = 8


def _unescape(s: str) -> str:
    """HTML 엔티티를 푼다. `&quot;` 가 제목에 그대로 남으면 키워드가 어긋난다."""
    import html as _html

    return _html.unescape(s or "")


def _published_at(html: str):
    """페이지의 발행 시각. 못 읽으면 None — 모르는 것을 지어내지 않는다."""
    from datetime import datetime

    m = _PUB_RE.search(html) or _PUB_JSONLD.search(html)
    if not m:
        return None
    raw = m.group(1).strip()
    for cand in (raw, raw.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return None


def _age_hours(dt) -> float:
    from datetime import datetime, timezone

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def _cfg():
    from app.config import get_settings

    return get_settings()


def build_query(sport: str, team: str) -> str:
    """상황 축 전용 검색 지시. 종목별 키워드는 registry 가 원본이다.

    ⚠️ **명시적으로 "검색하라"고 말한다.** 실측 2026-09-06: 일반 서술형
       질문은 도구를 발동시키지 않아 `groundingChunks` 가 0 이었다.
    """
    from app.collectors.news_rss import qualified
    from app.registry import situation_axes

    axes = situation_axes(sport)
    if not axes:
        return ""
    terms = [w[0] for w in axes.values() if w][:8]
    # 리그 한정어를 함께 — 팀명만 주면 다른 종목이 딸려온다(실측 2026-09-06).
    name = qualified(sport, team)
    return (f"{name} 구단의 최근 뉴스를 검색해서 알려줘. "
            f"특히 다음과 관련된 것: {', '.join(terms)}. "
            f"경기 결과·스코어 기사는 제외하고, 아직 열리지 않은 일정·발표·"
            f"논란만 찾아라.")


async def _cap_ok(redis, date: str) -> bool:
    """일일 캡. Redis 가 없으면 **막는다** — 셀 수 없으면 쓰지 않는다."""
    cap = int(_cfg().grounding_daily_cap)
    if redis is None:
        logger.info("[grounding] Redis 없음 — 캡을 셀 수 없어 생략한다")
        return False
    try:
        n = int(await redis.get(CAP_KEY.format(date=date)) or 0)
    except Exception as exc:
        logger.warning("[grounding] 캡 조회 실패 — 생략: %s", exc)
        return False
    if n >= cap:
        logger.warning("[grounding] 일일 캡 도달 %d/%d — 오늘은 더 부르지 않는다",
                       n, cap)
        return False
    return True


async def _note_call(redis, date: str) -> None:
    if redis is None:
        return
    try:
        k = CAP_KEY.format(date=date)
        await redis.incr(k)
        await redis.expire(k, TTL)
    except Exception as exc:
        logger.debug("[grounding] 카운터 기록 실패: %s", exc)


async def _once_ok(redis, sport: str, game_id, date: str) -> bool:
    """경기당 1회. 표식을 못 남기면 **부르지 않는다** (중복 과금 방지)."""
    if redis is None:
        return False
    key = ONCE_KEY.format(sport=sport, game_id=game_id, date=date)
    try:
        first = await redis.set(key, "1", ex=TTL, nx=True)
    except Exception as exc:
        logger.warning("[grounding] 1회 표식 실패 — 생략: %s", exc)
        return False
    if not first:
        logger.info("[grounding] game=%s 이미 호출함 — 생략", game_id)
    return bool(first)


async def search_uris(query: str) -> list[tuple[str, str]]:
    """검색 그라운딩 1회 → `[(리다이렉트 URL, 도메인)]`. 실패하면 빈 목록.

    ⚠️ 본문(모델이 쓴 문장)은 **읽지도 않는다.**
    """
    import httpx

    from app.llm import gemini

    if not gemini.is_available():
        logger.info("[grounding] GEMINI_API_KEY 없음 — 생략")
        return []
    s = _cfg()
    url = f"{BASE}/{s.gemini_model}:generateContent"
    body = {"contents": [{"parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 800}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(url, json=body,
                             headers={"x-goog-api-key": s.gemini_api_key})
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("[grounding] 호출 실패 — RSS 만으로 진행: %s", exc)
        return []
    cand = (data.get("candidates") or [{}])[0]
    chunks = ((cand.get("groundingMetadata") or {}).get("groundingChunks") or [])
    out: list[tuple[str, str]] = []
    for ch in chunks[:MAX_URLS]:
        w = (ch or {}).get("web") or {}
        uri, dom = str(w.get("uri") or ""), str(w.get("title") or "")
        if uri:
            out.append((uri, dom))
    logger.info("[grounding] 검색 결과 %d건 (질의 %d자)", len(out), len(query))
    return out


async def resolve(uri: str, hint_domain: str = "") -> dict | None:
    """리다이렉트를 따라가 **200 을 확인**하고 실제 제목·도메인을 읽는다.

    🔴 여기가 환각 방어의 마지막 관문이다. 모델이 주소를 지어내도 열리지 않는다.
    ⚠️ 제목은 **페이지에서 직접** 읽는다 — 모델 요약을 쓰지 않는다.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT,
                                     follow_redirects=True) as c:
            r = await c.get(uri, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/128.0.0.0 Safari/537.36"})
    except Exception as exc:
        logger.debug("[grounding] fetch 실패 %s: %s", uri[:60], exc)
        return None
    if r.status_code != 200:
        logger.debug("[grounding] HTTP %d — 버린다 %s", r.status_code, uri[:60])
        return None
    final = str(r.url)
    if any(h in final.lower() for h in _NON_NEWS_HOSTS):
        logger.debug("[grounding] 뉴스 아님 — 버린다 %s", final[:60])
        return None
    html = r.text or ""
    m = _TITLE_RE.search(html)
    title = _TAG_RE.sub("", m.group(1)).strip() if m else ""
    title = _unescape(re.sub(r"\s+", " ", title))[:160]
    if not title:
        return None
    pub = _published_at(html)
    if pub is not None and _age_hours(pub) > MAX_AGE_HOURS:
        logger.debug("[grounding] %.0f시간 전 기사 — 버린다 %s",
                     _age_hours(pub), title[:40])
        return None
    return {"title": title, "url": final, "source_url": final,
            "published": pub.strftime("%a, %d %b %Y %H:%M:%S %z") if pub else None}


async def fetch_for_team(sport: str, team: str, date: str,
                         redis=None) -> list[dict]:
    """팀 1개의 상황 검색 결과. RSS 항목과 **같은 모양**으로 돌려준다.

    실패·캡 도달은 빈 목록이고, 그 사실이 로그에 남는다.

    🔴 [LLM0 2026-09-22 사용자 지시] 스위치가 꺼져 있으면 **부르지 않는다.**
    """
    from app.api_guard import llm_enabled

    if not llm_enabled() or not _cfg().grounding_enabled:
        return []
    q = build_query(sport, team)
    if not q:
        return []
    if not await _cap_ok(redis, date):
        return []
    uris = await search_uris(q)
    await _note_call(redis, date)
    if not uris:
        return []
    got = await asyncio.gather(*(resolve(u, d) for u, d in uris),
                               return_exceptions=True)
    items = [g for g in got if isinstance(g, dict)]
    logger.info("[grounding] %s %s — 검색 %d · 200 검증 통과 %d",
                sport, team, len(uris), len(items))
    return items


async def fetch_for_game(jg: dict, date: str, redis=None) -> dict[str, list[dict]]:
    """경기 1건 — **경기당 1회**. `{home:[…], away:[…]}`.

    🔴 [LLM0 2026-09-22 사용자 지시] 스위치가 꺼져 있으면 **부르지 않는다.**
    """
    from app.api_guard import llm_enabled

    if not llm_enabled() or not _cfg().grounding_enabled:
        return {}
    sport = (jg.get("sport") or "").lower()
    gid = jg.get("game_id")
    if not await _once_ok(redis, sport, gid, date):
        return {}
    out: dict[str, list[dict]] = {}
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        rows = await fetch_for_team(sport, team, date, redis)
        if rows:
            out[side] = rows
    return out


def merge_into_research(research: dict, table: dict) -> int:
    """`{side}_news` 에 **덧붙인다.** RSS 결과를 지우지 않는다."""
    from app.collectors.news_rss import dedupe_by_title

    n = 0
    for side in ("home", "away"):
        rows = (table or {}).get(side) or []
        if not rows:
            continue
        cur = list(research.get(f"{side}_news") or [])
        merged = dedupe_by_title(cur + rows)
        n += len(merged) - len(cur)
        research[f"{side}_news"] = merged
    return n
