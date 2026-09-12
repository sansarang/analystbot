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
    arts += await _mlb_velocity_articles(jg, client, now)
    arts += await _mlb_weather_article(jg, client, now)
    arts += await _tor_supplement(jg, [
        (home, f"{home} injury roster move 2026"),
        (away, f"{away} injury roster move 2026")])
    return arts


async def _mlb_velocity_articles(jg: dict, client, now: datetime) -> list[dict]:
    """[SAT-8] 오늘 예고선발의 최근 구속 추세를 발견 기사로. 신호 없으면 빈 리스트.

    🔴 고급정보 — 박스스코어에 없는 투수 건강/폼. 예고선발 id 는 statsapi 에서,
       구속은 Savant 에서 온다(둘 다 무키·AWS 도달).
    """
    from app.collectors import statcast_velo as sv

    date = jg.get("starts_at") or now
    date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(now.date())
    season = int(date_str[:4])
    start = (now - timedelta(days=40)).strftime("%Y-%m-%d")
    try:
        pitchers = await _mlb_probable_pitchers(jg, client, date_str)
    except Exception as exc:
        logger.warning("[satellite] MLB 예고선발 조회 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return []
    out = []
    for team, (pid, name) in pitchers.items():
        try:
            t = await sv.pitcher_trend(pid, name, season=season,
                                       start=start, end=date_str)
        except Exception as exc:
            logger.warning("[satellite] 구속 추세 실패 %s: %s", name, exc)
            continue
        if t:
            out.append(_article(
                title=t["body"],
                url=f"https://baseballsavant.mlb.com/savant-player/{pid}",
                source="Statcast", team=team, body=t["body"], age_h=None))
    if out:
        logger.info("[satellite] MLB %s@%s 구속 추세 발견 %d건",
                    jg.get("away"), jg.get("home"), len(out))
    return out


async def _mlb_weather_article(jg: dict, client, now: datetime) -> list[dict]:
    """[SAT-10] 홈구장 날씨(바람·기온·강수) 발견 기사. 신호 없으면 빈 리스트.

    🔴 풍향→홈런효과는 statsapi venue 의 azimuthAngle(MLB 공식)로 판정한다 —
       좌표·돔 여부는 기존 weather.PARK_COORDS/DOMED 를 재사용한다(사본 금지).
    """
    from app.collectors import weather as wx

    home = jg.get("home")
    if not home or home in wx.DOMED:          # 돔은 날씨 무관
        return []
    coords = wx.PARK_COORDS.get(home)
    if coords is None:
        return []
    starts = jg.get("starts_at") or now
    when_iso = starts.strftime("%Y-%m-%dT%H:%M") if hasattr(starts, "strftime") else str(starts)
    try:
        azimuth = await _mlb_venue_azimuth(jg, client,
                                           when_iso[:10] or now.strftime("%Y-%m-%d"))
        hourly = await wx.hourly_rich(coords[0], coords[1])
    except Exception as exc:
        logger.warning("[satellite] 날씨 조회 실패 %s: %s", home, exc)
        return []
    if not hourly:
        return []
    fc = wx.forecast_at(hourly, when_iso)
    art = wx.weather_article(team=home, forecast=fc or {}, field_azimuth_deg=azimuth)
    if art:
        logger.info("[satellite] MLB %s 날씨 발견", home)
        return [art]
    return []


async def _mlb_venue_azimuth(jg: dict, client, date_str: str) -> float | None:
    """경기 구장의 방위각(홈→중견). statsapi venue(location).azimuthAngle."""
    if client is None:
        from app.collectors.mlb import MLBClient
        client = MLBClient()
    try:
        sched = await client.fetch_schedule(date_str)
    except Exception:
        return None
    home, away = jg.get("home"), jg.get("away")
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            t = g.get("teams", {})
            if (t.get("home", {}).get("team") or {}).get("name") != home:
                continue
            if (t.get("away", {}).get("team") or {}).get("name") != away:
                continue
            loc = (g.get("venue") or {}).get("location") or {}
            az = loc.get("azimuthAngle")
            return float(az) if az is not None else None
    return None


async def _mlb_probable_pitchers(jg: dict, client, date_str: str) -> dict:
    """경기의 홈/원정 예고선발 → {team: (id, name)}. statsapi schedule 재사용."""
    if client is None:
        from app.collectors.mlb import MLBClient
        client = MLBClient()
    sched = await client.fetch_schedule(date_str)
    home, away = jg.get("home"), jg.get("away")
    out: dict = {}
    for d in sched.get("dates", []):
        for g in d.get("games", []):
            t = g.get("teams", {})
            gh = (t.get("home", {}).get("team") or {}).get("name")
            ga = (t.get("away", {}).get("team") or {}).get("name")
            if gh != home or ga != away:
                continue
            for side, team in (("home", home), ("away", away)):
                pp = t.get(side, {}).get("probablePitcher")
                if pp and pp.get("id"):
                    out[team] = (pp["id"], pp.get("fullName") or "선발")
    return out


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


#: KBO 상황 검색어 — 축마다 **짧은 쿼리를 따로** 던진다(타자 전용 아님).
#  🔴 [SAT-12 실측 2026-09-09] 종전에는 "선발 부상 결장 말소 라인업" 을 한 번에
#     붙여 던졌는데, 다음이 그 AND 조합에 맞는 **오래된** 기사까지 긁어와 72h 필터
#     뒤에 1건만 남았다(나이 533~2715h). 축을 나눠 짧게 던지면 같은 필터에서
#     **31건**이 남는다 — 쿼리를 길게 쓴 것이 문제였지 정렬·필터가 아니었다.
_KBO_TERMS_LIST = ("라인업", "부상", "선발", "엔트리")


def _mentions_team(title: str, team: str) -> bool:
    """제목이 그 팀을 말하는가. **팀명이 없으면 그 경기 재료가 아니다.**

    🔴 [SAT-12 실측 2026-09-09] 다음검색은 팀 쿼리에 KBO 일반 기사를 섞어 준다 —
       36건 중 5건(14%)이 딴 팀이었고, 키움@두산 경기에 롯데 결장 기사가 재료로
       들어갔다. ±10%p 상한에서 그런 기사가 판정을 움직이면 그대로 오판이다.

    ⚠️ **반대 위험(정상 폐기)을 함께 막는다.** 기사는 'LG는'·'KT 위즈' 처럼
       축약해 쓰므로 별칭 전체뿐 아니라 **앞토큰**('LG'·'KT'·'삼성')도 인정한다.
       오염률이 14% 뿐이라 전량 폐기가 아니라 그 14%만 걸러내는 것이 목적이다.
    """
    from app.collectors.news_rss import QUERY_ALIAS

    t = title or ""
    if not t or not team:
        return False
    alias = QUERY_ALIAS.get(team, team)
    cands = {alias, alias.split()[0] if alias else "",
             team, team.split()[0] if team else ""} - {""}
    return any(c in t for c in cands)


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
        picked = 0
        for term in _KBO_TERMS_LIST:
            if picked >= _KBO_TOP_N:
                break
            try:
                html = await _daum_fetch(f"{alias} {term}")
            except Exception as exc:
                logger.warning("[satellite] KBO 다음검색 실패 %s/%s: %s",
                               team, term, exc)
                continue
            for it in parse_daum_news(html):
                if picked >= _KBO_TOP_N:
                    break
                u = it["url"]
                if u in seen:
                    continue
                if not _mentions_team(it["title"], team):
                    logger.debug("[satellite] KBO 딴 팀 기사 폐기 (%s): %.50s",
                                 team, it["title"])
                    continue
                age = _daum_age_h(u, now)
                if age is not None and age > MAX_AGE_HOURS:
                    continue
                seen.add(u)
                picked += 1
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
    # 🔴 [ROS-1 2026-09-11] **공시를 맨 앞에 둔다.** 검색 기사보다 공식이 먼저다.
    #    실측 2026-09-11: 위성 재료 76건 중 조사 인용 0건이었고, 모인 것은
    #    굿즈·타팀 FA 전망이었다. KBO 는 **말소로 결장을 알리는데** 우리는
    #    그 사건을 재료로 만들지 않고 있었다.
    if sport == "kbo":
        articles = await _kbo_official(jg, redis) + articles
    await _write_cache(redis, sport, gid, articles)
    return len(articles)


async def _kbo_official(jg: dict, redis) -> list[dict]:
    """KBO 1군 엔트리 **변동**을 재료로. 없으면 빈 목록(사유는 로그).

    ⚠️ 변화 0건이면 기사 0건이다 — "변화 없음"으로 프롬프트를 채우지 않는다.
    ⚠️ 어떤 실패도 위성 전체를 막지 않는다.
    """
    if redis is None:
        return []
    try:
        from app.collectors.kbo_roster import delta_articles, roster_delta
        from app.pipeline import today_kst

        delta = await roster_delta(redis, today_kst())
        if delta.get("사유"):
            logger.info("[satellite] KBO 공시 델타 생략 — %s", delta["사유"])
            return []
        arts = delta_articles(delta, [jg.get("home"), jg.get("away")])
        if arts:
            logger.info("[satellite] KBO 공시 델타 %d건 (기준 %s) game=%s",
                        len(arts), delta.get("기준"), jg.get("game_id"))
        return arts
    except Exception as exc:
        logger.warning("[satellite] KBO 공시 델타 실패 — 검색 재료만 쓴다: %s", exc)
        return []


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
    SELECT id, sport, league, home, away, starts_at
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
        # 🔴 [SOC-5] `league` 를 반드시 싣는다. 축구 어댑터는 리그로 뉴스
        #    소스를 가르므로, 없으면 12경기 전부 "소스 없음"으로 떨어진다
        #    (실측 2026-09-12 22:11, 기사 0건). 야구 어댑터는 읽지 않는다.
        jg = {"sport": r["sport"], "game_id": r["id"], "league": r["league"],
              "home": r["home"], "away": r["away"],
              "starts_at": r["starts_at"]}
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


# ══════════════════ [SAT-S3] 축구 어댑터 등록 ══════════════════
#
# 사용자 지시 2026-09-12: "인공위성 서치기능은 야구와 축구를 분리해라"
#
# 🔴 **파일 맨 끝에서 임포트한다.** 축구 모듈은 위 검색 함수(`_daum_fetch` ·
#    `parse_daum_news` · `_fetch_article_body` · `_article` · `_tor_supplement`)를
#    쓰고, 이 파일은 축구 어댑터를 등록해야 한다 — 위에서 임포트하면 순환이다.
#    ⚠️ 축구 쪽은 그 함수들을 **함수 안에서** 임포트한다(호출 시점 조회).
#       그래서 `monkeypatch.setattr(satellite, "_daum_fetch", …)` 가 그대로 먹는다.
from app.collectors.satellite_soccer import gather_soccer  # noqa: E402

_ADAPTERS["soccer"] = gather_soccer
