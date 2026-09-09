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
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

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
        if not desc:
            continue
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
    return arts


#: 종목별 어댑터. NPB·KBO 는 후속 증분에서 채운다(직접 경로).
_ADAPTERS = {
    "mlb": gather_mlb,
}


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
