"""[위성 Phase1] DB에 없는 경기 정보를 미리 긁어 캐시에 쌓는다.

🔴 **왜 위성인가.** 괴리(우리 vs 시장)의 91.8%가 개장 배당 때부터 이미 있었다
   (실측 2026-09-09). 즉 괴리는 "사건"이 아니라 **며칠~몇 주 유지되는 전력 차이**로,
   우리 DB(최근 3~5경기)가 원칙적으로 담지 못한다. 그 정보가 딥서치의 존재 이유인데,
   지금 재료원(구글 뉴스 RSS)은 본문 0%·팀라벨 76% 오류로 그걸 못 가져온다.

🔴 **수집(느림·차단됨·미리)과 판정(즉시·캐시만)을 가른다.** 이 모듈은 **수집기**다.
   경기가 슬레이트에 뜨는 순간부터 리그별 T-N분까지 백그라운드로 계속 긁어
   `satellite:{sport}:{game_id}` 에 쌓는다. 판정 경로는 이 캐시를 **읽기만** 하고
   외부 검색을 절대 기다리지 않는다.

⚠️ **판정 로직은 건드리지 않는다.** 산출물은 `news_rss` 와 **똑같은 dict 모양**이라
   딥서치 `_free_articles` 가 그대로 삼킨다. 요약·±4%p 상한·우세 뒤집기 금지는 불변.

Phase1 은 **직접 경로만**이다 (AWS IP 로 도달되는 소스). MLB 는 statsapi/transactions
가 부상·등록·말소를 구조화 JSON 으로 준다 — 검색조차 필요 없다. NPB·KBO 어댑터와
토르 경로(Phase2)는 이 프레임워크 위에 뒤이어 붙인다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

#: Redis 캐시 키·수명. 위성이 15분마다 T-N 까지 갱신하므로 캐시는 늘 신선하다.
CACHE_KEY = "satellite:{sport}:{game_id}"
CACHE_TTL = 12 * 3600

#: MLB transactions 조회 창(일). 종전 뉴스 나이 필터(72h)와 다른 축이다 — 트랜잭션은
#  이벤트라 조회 창 자체가 필터다. 장기 IL 은 이 창 밖의 옛 이벤트일 수 있어(류현진
#  89일 이탈처럼) 넉넉히 잡는다. 현재 IL 로스터 스냅샷은 후속 증분에서 보강한다.
TX_WINDOW_DAYS = 14

#: 이 종류는 승부와 무관하거나 소음이라 버린다(상위 팀의 순수 행정 이벤트).
_TX_SKIP_TYPES = {"SFA", "SGN"}   # Selected Free Agent 재계약류 · 소음


def _cache_key(sport: str, game_id) -> str:
    return CACHE_KEY.format(sport=(sport or "").lower(), game_id=game_id)


def _article(*, title: str, url: str, source: str, team: str,
             body: str, age_h: float | None = None) -> dict:
    """news_rss 와 같은 모양. `_inject_articles`(deepsearch.py) 가 읽는 키를 맞춘다.

    ⚠️ 키를 손으로 늘리지 마라 — 원본은 `news_rss.parse_feed` 다. 여기서 빠진 키가
       있으면 `tests/test_satellite.py::test_article_shape_matches_inject_contract`
       가 깨진다.
    """
    return {"title": title, "url": url, "source": source,
            "team": team, "age_h": age_h, "body": body}


def _age_hours(date_str: str | None, now: datetime | None) -> float | None:
    """트랜잭션 date('YYYY-MM-DD') → 지금까지 시간. 파싱 실패면 None."""
    if not date_str:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(date_str)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((now - dt).total_seconds() / 3600, 1)


def transactions_to_articles(txs: list[dict], teams: set[str],
                             *, now: datetime | None = None) -> list[dict]:
    """statsapi transactions → 기사 dict 리스트. **경기의 두 팀 것만** 남긴다.

    🔴 팀 매칭이 핵심이다. 지금 RSS 는 라벨의 76%가 딴 팀 기사였다 — 그 실수를
       반복하지 않도록 `fromTeam/toTeam.name` 이 경기 두 팀에 정확히 들어야 남긴다.
       마이너 팀(ACL Brewers·Buffalo Bisons 등)은 name 이 안 맞아 자동으로 빠진다.
    """
    out: list[dict] = []
    seen: set[str] = set()   # 🔴 statsapi 는 같은 이벤트를 중복 행으로 준다(실측 09-09)
    for t in txs or []:
        if not isinstance(t, dict):
            continue
        if t.get("typeCode") in _TX_SKIP_TYPES:
            continue
        names = {(t.get("fromTeam") or {}).get("name"),
                 (t.get("toTeam") or {}).get("name")} - {None}
        matched = names & teams
        if not matched:
            continue
        desc = (t.get("description") or "").strip()
        if not desc or desc in seen:
            continue
        seen.add(desc)
        pid = (t.get("person") or {}).get("id")
        url = (f"https://www.mlb.com/player/{pid}" if pid
               else "https://www.mlb.com/transactions")
        out.append(_article(
            title=desc, url=url, source="MLB Transactions",
            team=next(iter(matched)), body=desc,
            age_h=_age_hours(t.get("date"), now)))
    return out


async def gather_mlb(jg: dict, *, client=None, now: datetime | None = None) -> list[dict]:
    """MLB 경기 1건의 로스터·부상·트레이드 정보를 transactions 로 긁는다.

    ⚠️ 실패하면 빈 리스트 — 조용한 0 이 아니라 로그를 남긴다. 위성이 못 긁어도
       판정은 news_rss 로 폴백하므로 회귀는 없다.
    """
    home, away = (jg.get("home") or ""), (jg.get("away") or "")
    teams = {home, away} - {""}
    if not teams:
        return []
    if client is None:
        from app.collectors.mlb import MLBClient
        client = MLBClient()
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=TX_WINDOW_DAYS)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    try:
        data = await client.fetch_transactions(start, end)
    except Exception as exc:
        logger.warning("[satellite] MLB transactions 조회 실패 %s@%s: %s",
                       away, home, exc)
        return []
    arts = transactions_to_articles(data.get("transactions") or [], teams, now=now)
    logger.info("[satellite] MLB %s@%s transactions %d건 → 기사 %d건",
                away, home, len(data.get("transactions") or []), len(arts))
    arts += await _tor_supplement(jg, [
        (home, f"{home} injury roster move 2026"),
        (away, f"{away} injury roster move 2026")])
    return arts


# ── KBO 어댑터 (다음 뉴스검색 — AWS IP 로 도달, 토르 불필요) ──────────────
#   🔴 [SAT-5] 검색 애그리게이터(DDG·구글)는 AWS IP 로 막혔지만 다음 뉴스검색은
#      200 을 준다(실측 2026-09-09). v.daum.net URL·제목을 얻고 본문은 직접 수집한다.

_DAUM_URL = "https://search.daum.net/search"
_DAUM_ITEM = re.compile(r'<a[^>]+href="(https?://v\.daum\.net/v/\d+)"[^>]*>(.*?)</a>', re.S)
_DAUM_TS = re.compile(r"/v/(\d{14})")
_KST = ZoneInfo("Asia/Seoul")
_KBO_TOP_N = 6          # 팀당 상위 N건 본문 수집
_HTML_ENT = (("&#39;", "'"), ("&quot;", '"'), ("&amp;", "&"),
             ("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"))


def _strip_html(s: str | None) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    for a, b in _HTML_ENT:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _dedup_titled_links(html: str, pattern: re.Pattern) -> list[dict]:
    """검색결과 HTML → [{url, title}]. **URL 중복 제거**(같은 기사가 썸네일·제목·
    요약으로 여러 번 링크된다). 제목은 가장 긴 앵커텍스트(숫자 배지는 버린다).

    🔴 다음·야후 둘 다 같은 형태라 파서를 하나로 둔다(사본 금지).
    """
    by_url: dict[str, str] = {}
    for m in pattern.finditer(html or ""):
        u, raw = m.group(1), _strip_html(m.group(2))
        if not raw or raw.isdigit():
            continue
        if len(raw) > len(by_url.get(u, "")):
            by_url[u] = raw
    return [{"url": u, "title": t} for u, t in by_url.items()]


def parse_daum_news(html: str) -> list[dict]:
    """다음 뉴스검색 → [{url, title}]."""
    return _dedup_titled_links(html, _DAUM_ITEM)


def _daum_age_h(url: str, now: datetime | None) -> float | None:
    """v.daum.net URL 에 박힌 시각(KST)으로 나이(시간)를 잰다."""
    m = _DAUM_TS.search(url or "")
    if not m:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=_KST)
    except ValueError:
        return None
    return round((now - dt).total_seconds() / 3600, 1)


async def _daum_fetch(query: str) -> str:
    """다음 뉴스검색 HTML(최신순). 실패는 호출부가 처리."""
    import httpx

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": _UA,
                                          "Accept-Language": "ko"}) as c:
        r = await c.get(_DAUM_URL,
                        params={"w": "news", "q": query, "sort": "recency"})
        r.raise_for_status()
        return r.text


async def _fetch_article_body(url: str | None) -> str:
    """기사 본문 앞부분. 무료 HTTP. 실패하면 빈 문자열(제목만 쓴다).

    ⚠️ 딥서치 `_fetch_body` 와 목적이 같지만, 엔진→수집기 순환 의존을 피하려
       여기 둔다. 본문 길이 상한은 딥서치와 같은 1200자.
    """
    if not url:
        return ""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as exc:
        logger.debug("[satellite] 본문 수집 실패 %s: %s", str(url)[:60], exc)
        return ""
    html = re.sub(r"<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ",
                  html, flags=re.S | re.I)
    return _strip_html(html)[:1200]


#: KBO 상황 검색어 — 선발·부상·결장이 승부에 직결되는 축이다(타자 전용 아님).
_KBO_TERMS = "선발 부상 결장 말소 라인업"


async def gather_kbo(jg: dict, *, client=None, now: datetime | None = None) -> list[dict]:
    """KBO 경기 1건 — 다음 뉴스검색으로 팀별 최신 기사·본문을 news_rss 모양으로.

    🔴 팀명은 news_rss.QUERY_ALIAS(한국어)를 재사용한다(사본 금지).
    ⚠️ 실패해도 빈 리스트 — 다른 팀·다른 경기를 막지 않는다.
    """
    from app.collectors.news_rss import MAX_AGE_HOURS, QUERY_ALIAS

    now = now or datetime.now(timezone.utc)
    out: list[dict] = []
    seen: set[str] = set()
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        alias = QUERY_ALIAS.get(team, team)
        try:
            html = await _daum_fetch(f"{alias} {_KBO_TERMS}")
        except Exception as exc:
            logger.warning("[satellite] KBO 다음검색 실패 %s: %s", team, exc)
            continue
        for it in parse_daum_news(html)[:_KBO_TOP_N]:
            u = it["url"]
            if u in seen:
                continue
            seen.add(u)
            age = _daum_age_h(u, now)
            if age is not None and age > MAX_AGE_HOURS:
                continue
            body = await _fetch_article_body(u)
            out.append(_article(title=it["title"], url=u, source="다음뉴스",
                                team=team, body=body or it["title"], age_h=age))
    logger.info("[satellite] KBO %s@%s 다음뉴스 기사 %d건",
                jg.get("away"), jg.get("home"), len(out))
    return out


# ── NPB 어댑터 (야후재팬 뉴스검색 — AWS IP 로 도달, 토르 불필요) ───────────
#   🔴 [SAT-6] 야후재팬 뉴스검색은 AWS IP 로 200 을 준다(실측 2026-09-09,
#      기사 24건·본문 3039자). 다음(KBO)과 같은 형태라 파서를 공유한다.

_YAHOO_URL = "https://news.yahoo.co.jp/search"
_YAHOO_ITEM = re.compile(
    r'<a[^>]+href="(https://news\.yahoo\.co\.jp/articles/[0-9a-f]+)"[^>]*>(.*?)</a>', re.S)
_NPB_TOP_N = 6
#: NPB 상황 검색어 — 선발·부상·말소·등록·스타메가 승부에 직결(타자 전용 아님).
_NPB_TERMS = "先発 故障 抹消 登録 スタメン"


def parse_yahoo_news(html: str) -> list[dict]:
    """야후재팬 뉴스검색 → [{url, title}]."""
    return _dedup_titled_links(html, _YAHOO_ITEM)


async def _yahoo_fetch(query: str) -> str:
    """야후재팬 뉴스검색 HTML. 실패는 호출부가 처리."""
    import httpx

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": _UA,
                                          "Accept-Language": "ja"}) as c:
        r = await c.get(_YAHOO_URL, params={"p": query, "ei": "utf-8"})
        r.raise_for_status()
        return r.text


async def gather_npb(jg: dict, *, client=None, now: datetime | None = None) -> list[dict]:
    """NPB 경기 1건 — 야후재팬 뉴스검색으로 팀별 기사·본문을 news_rss 모양으로.

    🔴 팀명은 news_rss.QUERY_ALIAS(일본어)를 재사용한다(사본 금지).
    ⚠️ 야후 기사 URL 에는 시각이 없어 age_h 는 None 이다(야후 최신순 정렬에 의존).
    ⚠️ 실패해도 빈 리스트 — 다른 팀·경기를 막지 않는다.
    """
    from app.collectors.news_rss import QUERY_ALIAS

    out: list[dict] = []
    seen: set[str] = set()
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        alias = QUERY_ALIAS.get(team, team)
        try:
            html = await _yahoo_fetch(f"{alias} {_NPB_TERMS}")
        except Exception as exc:
            logger.warning("[satellite] NPB 야후검색 실패 %s: %s", team, exc)
            continue
        for it in parse_yahoo_news(html)[:_NPB_TOP_N]:
            u = it["url"]
            if u in seen:
                continue
            seen.add(u)
            body = await _fetch_article_body(u)
            out.append(_article(title=it["title"], url=u, source="Yahoo!ニュース",
                                team=team, body=body or it["title"], age_h=None))
    # 토르 보강 — 일본어 질의(출구노드로 DDG 도달). QUERY_ALIAS 재사용.
    from app.collectors.news_rss import QUERY_ALIAS as _QA
    out += await _tor_supplement(jg, [
        (jg.get(side) or "", f"{_QA.get(jg.get(side) or '', jg.get(side) or '')} 故障 抹消 先発 2026")
        for side in ("home", "away") if jg.get(side)])
    logger.info("[satellite] NPB %s@%s 야후뉴스 기사 %d건",
                jg.get("away"), jg.get("home"), len(out))
    return out


#: 종목별 어댑터. 세 리그 전부 직접 경로(토르 불필요) — 토르는 순수 보강(SAT-7).
_ADAPTERS = {
    "mlb": gather_mlb,
    "kbo": gather_kbo,
    "npb": gather_npb,
}


async def _tor_supplement(jg: dict, queries: list[tuple[str, str]]) -> list[dict]:
    """[SAT-7] 토르 경유 DDG 보강. **satellite_tor_enabled 일 때만.**

    ⚠️ 한국 소스는 부르지 않는다(호출부가 KBO 를 넘기지 않고, tor_search 도
       한국어 질의를 거부한다 — 이중 방어). 실패는 빈 리스트.
    """
    from app.config import get_settings

    if not get_settings().satellite_tor_enabled:
        return []
    from app.collectors import tor_search

    out: list[dict] = []
    seen: set[str] = set()
    for team, q in queries:
        try:
            hits = await tor_search.search(q)
        except Exception as exc:
            logger.warning("[satellite] 토르 보강 실패 %s: %s", team, exc)
            continue
        for h in hits:
            u = h.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            body = await _fetch_article_body(u)
            out.append(_article(
                title=h.get("title") or "", url=u, source="DDG(토르)",
                team=team, body=body or h.get("snippet") or h.get("title") or "",
                age_h=None))
    if out:
        logger.info("[satellite] 토르 보강 %s@%s +%d건",
                    jg.get("away"), jg.get("home"), len(out))
    return out


async def gather(jg: dict, redis, *, client=None, now: datetime | None = None) -> int:
    """경기 1건을 긁어 캐시에 쓴다. 반환: 적재 기사 수.

    ⚠️ 재료 0건이어도 크래시하지 않고 0을 돌려준다(조용한 0 금지). redis 가 없으면
       수집만 하고 캐시는 건너뛴다.
    """
    sport = (jg.get("sport") or "").lower()
    gid = jg.get("game_id") or jg.get("id")
    adapter = _ADAPTERS.get(sport)
    if adapter is None:
        return 0
    articles = await adapter(jg, client=client, now=now)
    await _write_cache(redis, sport, gid, articles)
    return len(articles)


async def _write_cache(redis, sport: str, game_id, articles: list[dict]) -> None:
    if redis is None or game_id is None:
        return
    payload = {"gathered_at": datetime.now(timezone.utc).isoformat(),
               "items": articles}
    try:
        await redis.set(_cache_key(sport, game_id),
                        json.dumps(payload, ensure_ascii=False), ex=CACHE_TTL)
    except Exception as exc:
        logger.warning("[satellite] 캐시 기록 실패 %s:%s — %s", sport, game_id, exc)


#: 대상 경기 — 예정이고 탐색 창 안에 시작. 컷오프는 아래 파이썬에서 건다(원본
#  `minutes_until_start` 를 재사용하려면 행별로 계산해야 하므로 SQL 로 안 자른다).
_DUE_SQL = """
    SELECT id, sport, home, away, starts_at
      FROM games
     WHERE status = 'scheduled'
       AND sport = ANY($1::text[])
       AND starts_at BETWEEN now() AND now() + make_interval(hours => $2)
     ORDER BY starts_at
"""


async def run_satellite(pool, redis, *, sports: list[str], now=None,
                        cutoff_min: int = 10, lookahead_h: int = 24,
                        client=None) -> dict:
    """탐색 창 안 예정 경기를 골라 각각 수집한다. 반환 `{games, gathered}`.

    🔴 **컷오프 = 위성 정지선.** 시작 T-N분 안에 든 경기는 더 긁지 않는다 —
       사용자 표현대로 "T-N분에 정지"한다. 컷오프 판정은 원본
       `minutes_until_start`(pregame_push)를 재사용한다(재정의 금지).

    ⚠️ 어댑터 없는 종목은 `gather` 가 0을 돌려주므로 자연히 건너뛴다.
    ⚠️ 한 경기 실패가 다른 경기를 막지 않는다 — 경기별 try 로 감싼다.
    """
    from app.engine.pregame_push import minutes_until_start

    if not sports:
        return {"games": 0, "gathered": 0}
    try:
        rows = await pool.fetch(_DUE_SQL, list(sports), int(lookahead_h))
    except Exception as exc:
        logger.warning("[satellite] 대상 경기 조회 실패: %s", exc)
        return {"games": 0, "gathered": 0}

    games = gathered = 0
    for r in rows:
        left = minutes_until_start(r["starts_at"], now)
        if left is None or left <= cutoff_min:
            continue                        # 컷오프 안 — 위성 정지
        jg = {"sport": r["sport"], "game_id": r["id"],
              "home": r["home"], "away": r["away"]}
        try:
            n = await gather(jg, redis, client=client, now=now)
        except Exception as exc:
            logger.warning("[satellite] 수집 실패 game=%s: %s", r["id"], exc)
            continue
        games += 1
        gathered += n
    logger.info("[satellite] 수집 사이클 — 대상 %d경기 · 기사 %d건 (%s)",
                games, gathered, ",".join(sports))
    return {"games": games, "gathered": gathered}


async def read_cache(redis, sport: str, game_id) -> list[dict]:
    """캐시된 기사 리스트. 없거나 실패하면 빈 리스트(딥서치는 news_rss 로 폴백)."""
    if redis is None or game_id is None:
        return []
    try:
        raw = await redis.get(_cache_key(sport, game_id))
    except Exception as exc:
        logger.debug("[satellite] 캐시 읽기 실패 %s:%s — %s", sport, game_id, exc)
        return []
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return payload.get("items") or []
