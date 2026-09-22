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
import pathlib
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
    velo: dict = {}
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
            # 🔴 [PA-18 · D2] **숫자를 버리지 않는다.** 종전에는 문장만
            #    기사로 남고 delta_mph 가 사라져서, 판정이 구속 하락을
            #    가감으로 쓸 길이 없었다(D2: −1.0mph 이상이면 −2%p).
            velo[team] = t.get("delta_mph")
    if velo:
        await _write_velo(redis_of(jg), jg, velo)
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
    # 🔴 [DEC-2 2026-09-21] robots 거부 소스 — **요청을 보내지 않는다.**
    #    판단은 `source_gate` 한 곳이 한다(사본 금지). Bing 이 대체한다(DS-3).
    from app.collectors.source_gate import require

    require("daum_search")
    return await _daum_fetch_inner(query)


async def _daum_fetch_inner(query: str) -> str:
    """다음 뉴스검색 HTML(최신순). 실패는 호출부가 처리."""
    import httpx

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers={"User-Agent": _UA,
                                          "Accept-Language": "ko"}) as c:
        r = await c.get(_DAUM_URL,
                        params={"w": "news", "q": query, "sort": "recency"})
        r.raise_for_status()
        return r.text


#: 동의 배너·안내문 표식. 이런 문구가 든 후보는 본문이 아니다.
#  실측 2026-09-12: Standard 기사의 `<p>` 는 **전부** Exco Player 동의 배너였다.
_BOILER = ("allow and continue", "cookies or similar technologies",
           "ad-supported tier", "skip to main content", "enable javascript",
           "이 콘텐츠를 보려면")
_BODY_CLEAN = re.compile(
    r"<(script|style|nav|header|footer|aside|form|svg|button)[^>]*>.*?</\1>",
    re.S | re.I)
_BODY_P = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
_BODY_BLOCK = re.compile(r"</(?:div|section|article|li|td|p|h[1-6])>", re.I)


def extract_body(html: str, limit: int = 1200) -> str:
    """기사 본문. 🔴 **페이지 앞부분을 그냥 자르면 메뉴가 온다.**

    실측 2026-09-12 23:00 (위성 캐시의 실제 라인업 기사 5개 URL, 같은 HTML):

        앞 1200자 자르기   0/5   전부 내비게이션·광고·쿠키 배너
        `<p>` 모음         3/5   SI 는 `<p>` 0개 · Standard 는 전부 동의 배너
        최장 블록          4/5   Standard 에서 "Pedro Neto ... will celebrate
                                 his new contract with a start at left
                                 wing-back" 을 건졌다 — 선발 정보다
        둘 중 나은 쪽      5/5

    ⚠️ 후보가 하나도 없으면 **종전대로** 통째로 긁는다 — 빈손을 주지 않는다.
    """
    h = _BODY_CLEAN.sub(" ", html or "")

    def _ok(t: str, n: int) -> bool:
        # 🔴 배너는 **덩어리 단위로** 버린다. 합친 뒤에 거르면 배너가 본문을
        #    끌고 들어가 둘 다 잃는다(실측: Standard 기사).
        return len(t) > n and not any(b in t.lower() for b in _BOILER)

    cands: list[str] = []
    paras = [_strip_html(m).strip() for m in _BODY_P.findall(h)]
    paras = [t for t in paras if _ok(t, 60)]
    if paras:
        cands.append(" ".join(paras))
    blocks = [_strip_html(x).strip() for x in _BODY_BLOCK.split(h)]
    blocks = [t for t in blocks if _ok(t, 80)]
    if blocks:
        cands.append(max(blocks, key=len))
    best = max(cands, key=len, default="")
    return (best or _strip_html(h))[:limit]


async def _fetch_article_body(url: str | None) -> str:
    """기사 본문 앞부분. 실패하면 빈 문자열(제목만 쓴다).

    🔴 [DS-1W 2026-09-21] **DS-1 런타임을 지난다.** 이 함수는 검색 결과에서 온
       **임의 도메인**을 연다 — 우리가 도메인을 미리 모르는 유일한 자리다.
       종전에는 robots 검사가 **0건**이었고 예절(도메인당 동시 1 · 간격 2초 ·
       일일 상한)도 서킷 브레이커도 없었다.
       DS-3 이 소스를 Bing 으로 바꾼 뒤 여기 들어오는 도메인이 늘었다:
       osen.co.kr · yna.co.kr · mt.co.kr · fnnews.com · msn.com …(실측).

    ⚠️ robots 가 거부하면 **빈 문자열**이다 — 차단을 우회하지 않는다.
       호출부에게는 "본문 없음"이고, **사유는 로그에 남는다**(조용한 0 이 아니다).
    ⚠️ 본문 길이 상한은 `extract_body` 가 원본이다 — 여기서 다시 자르지 않는다.
    """
    if not url:
        return ""
    from app.deepsearch.runtime import Blocked, default_runtime

    try:
        # 🔴 **공유 런타임**이다. 호출마다 새로 만들면 간격·상한·서킷이 사라지고
        #    robots.txt 를 매 요청마다 다시 받는다(요청 2배) — 실측으로 확인했다.
        got = await default_runtime().fetch(url)
        html = (got.body or b"").decode("utf-8", "replace")
    except Blocked as b:
        # 🔴 "막혀서 안 보냈다"와 "받았는데 비었다"는 다르다. 사유를 남긴다.
        logger.info("[satellite] 본문 미수집(%s) %s", b.reason, str(url)[:60])
        return ""
    except Exception as exc:
        logger.debug("[satellite] 본문 수집 실패 %s: %s", str(url)[:60], exc)
        return ""
    return extract_body(html)


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
    """KBO 경기 1건 — 팀별 최신 기사·본문을 news_rss 모양으로.

    🔴 [D52 2026-09-22] **Bing RSS(`rss_hits`) 가 1순위다.** 어제(DEC-2)
       `search.daum.net` 을 robots 거부로 끄면서 "대체가 이미 있다"고 적었지만
       **KBO 에는 미연결이었다** — `rss_hits` 를 부르는 곳은 축구뿐이었다.
       실측 2026-09-22 10:29 KST(KT Wiz@SSG Landers): `gather_kbo` 기사 **0건**
       (다음 검색 8회 전부 SourceDisabled) · `gather_npb` 9건.
       정정: "대체가 이미 있다" → **"대체 함수는 있었으나 미연결. 09-22 연결."**

    🔴 팀명은 news_rss.QUERY_ALIAS(한국어)를 재사용한다(사본 금지).
    🔴 선별은 **`_mentions_team`(별칭표)** 이다 — `rss_supplement` 를 쓰지 않는
       이유가 이것이다. 그쪽은 `scout_config.screen` → `_tokens(team)` 로
       **DB 표기(영문)** 를 제목에서 찾는데 한국 매체 제목은 한국어다:
       `_tokens("Doosan Bears")` → `["Doosan","Bears"]` vs 제목 "두산 베어스 …"
       → 10팀 중 6팀이 전량 폐기된다. `screen` 을 한국어로 고치는 것은
       축구·NPB 전부에 닿으므로 범위 밖이다(SAT-12 가 같은 이유로 있다).
    ⚠️ 다음 검색은 **RSS 가 그 팀에서 0건일 때만** 부른다. 지금은 게이트가
       막으므로 요청이 나가지 않는다 — 정식 접근이 허락되면 설정 한 줄로 살아난다.
    ⚠️ 실패해도 빈 리스트 — 다른 팀·다른 경기를 막지 않는다.
    """
    from app.collectors.news_rss import MAX_AGE_HOURS, QUERY_ALIAS
    from app.engine.pregame_push import minutes_until_start

    now = now or datetime.now(timezone.utc)
    # ⚠️ 신선도 단계는 **원본**(`minutes_until_start`)으로 잰다 — 여기서 다시
    #    계산하면 시점 정의가 두 벌이 된다(축구 `_tor_stage` 와 같은 규약).
    _left = minutes_until_start(jg.get("starts_at"), now)
    stage = "lineup" if (_left is not None and 0 < _left <= 75) else "pre"
    out: list[dict] = []
    seen: set[str] = set()
    n_rss = 0
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        alias = QUERY_ALIAS.get(team, team)
        picked = 0
        # ── 1순위: Bing RSS(DS-3 체인). robots 허용 경로다.
        for term in _KBO_TERMS_LIST:
            if picked >= _KBO_TOP_N:
                break
            for h in await rss_hits(f"{alias} {term}", league="kbo",
                                    stage=stage, now=now, sport="kbo",
                                    kickoff=jg.get("starts_at")):
                if picked >= _KBO_TOP_N:
                    break
                u = h.get("url") or ""
                if not u or u in seen:
                    continue
                if not _mentions_team(h.get("title") or "", team):
                    logger.debug("[satellite] KBO 딴 팀 기사 폐기 (%s): %.50s",
                                 team, h.get("title") or "")
                    continue
                # ⚠️ 신선도는 `rss_hits` 가 이미 걸었다(scout_config.MAX_AGE_H).
                #    여기서 다시 자르지 않는다 — 사본이 되고 두 벌이 어긋난다.
                pub = h.get("published")
                age = (round((now - pub).total_seconds() / 3600, 1)
                       if isinstance(pub, datetime) else None)
                seen.add(u)
                picked += 1
                n_rss += 1
                body = await _fetch_article_body(u)
                out.append(_article(title=h.get("title") or "", url=u,
                                    source=h.get("source") or "Bing뉴스",
                                    team=team,
                                    body=body or h.get("title") or "",
                                    age_h=age))
        if picked:
            continue
        # ── 2순위: 다음 뉴스검색. **RSS 가 0건일 때만.**
        #    ⚠️ 지금은 `source_gate` 가 막는다(robots 거부·D40). 코드는 남긴다.
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
    logger.info("[satellite] KBO %s@%s 기사 %d건 (RSS %d · 다음 %d)",
                jg.get("away"), jg.get("home"), len(out), n_rss,
                len(out) - n_rss)
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



def _title_hits(title: str, team: str) -> bool:
    """[URL-1] 제목이 그 팀을 말하는가. **본문을 열기 전에** 본다.

    🔴 실측 2026-09-13(몬차@레체): 위성 26건 중 24건이 "레체 데 티그레 & 김치",
       "둘세 데 레체 1400kg", "몬차 서킷 F1 그랑프리"였는데 **전부 본문까지
       열었다.** 경기당 12회 × 12경기 = 144회.

    ⚠️ **반대 위험(정상 폐기)을 막는다** — 제목이 비면 통과시키고, 팀명의
       **토큰 하나라도** 맞으면 인정한다(`Mariners`처럼 줄여 쓴다).
       오염만 걷어내는 것이 목적이지 전량 폐기가 아니다.
    ⚠️ KBO 는 별칭표를 쓰는 `_mentions_team` 을 그대로 쓴다(SAT-12).
    """
    t, n = (title or "").lower(), (team or "").lower()
    if not t or not n:
        return True
    toks = [w for w in re.split(r"[^\w가-힣]+", n) if len(w) > 2]
    return not toks or any(w in t for w in toks)


async def rss_hits(query: str, *, league: str, stage: str = "pre",
                   now=None, sport: str | None = None,
                   kickoff=None) -> list[dict]:
    """[SCT-7 → DS-3] 현지어 질의 1순위 통로. **2026-09-21 에 공급자를 갈았다.**

    🔴 종전은 Google News RSS 였고 그것은 **robots 거부**다 — `*` 에
       `Disallow: /` 이고 `/rss/` 를 여는 Allow 줄이 없으며, `ClaudeBot`·
       `anthropic-ai` 를 **이름으로 지목**해 막는다(원문 직접 수신 2026-09-21).
       실측: 운영 캐시의 기사 URL **174건이 전부** 그 도메인이었다.
    🔴 지금은 `deepsearch.search.chain_search` 를 쓴다 — 공급자·순서의 원본은
       `config/deepsearch.yaml` 의 `search.chain` 하나다(사용자 결정: bing).
       요청은 DS-1 런타임을 지나 robots·간격·상한·서킷이 걸린다.

    반환 모양은 **그대로**다(바꾸면 `_tor_supplement`·`screen` 이 깨진다):
    `{url, title, snippet, source, source_url, published(datetime)}`.

    🔴 `source_url` 은 **매체 도메인**이다. 검색엔진 리다이렉트로 등급을 보면
       전건이 '미상'이 된다(SCT-9 에서 겪은 실패). Bing 은 apiclick 링크의
       `url=` 에 원문을 그대로 담아 주므로 **추가 요청 0** 으로 푼다.
    ⚠️ `published` 를 **datetime 으로** 넘긴다 — `scout_config.screen` 이 그
       타입으로 "pubDate 를 아는 소스"(RSS)를 가른다(SCT-6).
    ⚠️ 되돌릴 스위치를 두지 않았다 — 되돌릴 자리가 **robots 거부 경로**다.
    """
    from app.deepsearch.search import chain_search, verify
    from app.engine.scout_config import MAX_AGE_H, locale

    loc = locale(league)
    if not loc or not query:
        return []
    # 🔴 [DS-3 2026-09-21] **구글 RSS 를 끊었다.** `news.google.com` 은 robots
    #    거부다 — `*` 에 `Disallow: /` 이고 `/rss/` 를 여는 Allow 줄이 없으며
    #    `ClaudeBot`·`anthropic-ai` 를 **이름으로 지목**해 막는다(원문 수신).
    #    실측: 운영 캐시의 기사 URL 174건이 **전부** 그 도메인이었다.
    #    ⚠️ 되돌릴 스위치를 두지 않았다 — 되돌릴 자리가 거부 경로라서다.
    mkt = f"{loc.get('hl') or 'ko'}-{loc.get('gl') or 'KR'}"
    try:
        hits = await chain_search(query, market=mkt)
    except Exception as exc:
        logger.warning("[rss] %s 조회 실패 %s: %s", league, query[:40], exc)
        return []
    # 🔴 [WIR-3 2026-09-22] **검증을 여기서 건다.** `verify` 는 ADD-2·D38 에서
    #    만들어졌는데 부르는 곳이 오디션 도구 하나였다 — 운영 기사 경로는
    #    지나지 않았다. 실측: KBO 12건 중 5건이 msn.com · 본문 3자(요청 5회 낭비).
    #    ⚠️ **창(`window`)은 걸지 않는다** — `MAX_AGE_H` 와 두 벌이 되고, 실측
    #       2026-09-22 에 24h 를 얹으면 18건 → 2건이 됐다(FORKS F-19 결정 대기).
    #    ⚠️ `sport` 가 없으면 `recap_markers` 규약대로 리캡을 안 거른다.
    hits, _bad = verify(hits, sport=sport or "", starts_at=kickoff, window=False)
    if _bad:
        _why: dict = {}
        for d in _bad:
            _why[d.get("reason")] = _why.get(d.get("reason"), 0) + 1
        logger.info("[rss] %s 검증 폐기 %d건 %s", league, len(_bad), _why)
    # ⚠️ 신선도 상한은 **종전 그대로** `scout_config.MAX_AGE_H` 다(사본 금지).
    cur = now or datetime.now(timezone.utc)
    cap = MAX_AGE_H.get(stage, 48)
    out: list[dict] = []
    for h in hits:
        pub = h.published_at
        if pub is not None and pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub is not None and (cur - pub).total_seconds() > cap * 3600:
            continue
        out.append({"url": h.url, "title": h.title,
                    "snippet": h.snippet or h.source,
                    "source": h.source,
                    # 🔴 등급·차단은 **매체 도메인**으로 본다. 검색엔진 주소로
                    #    보면 전건이 '미상'이 된다(SCT-9 에서 겪은 실패).
                    "source_url": h.url,
                    "published": pub})
    logger.info("[rss] %s %s — %d건", league, query[:40], len(out))
    return out


async def rss_supplement(jg: dict, queries: list[tuple[str, str]], *,
                         league: str, stage: str = "pre", kickoff=None,
                         now=None, stats: dict | None = None,
                         sport: str | None = None) -> list[dict]:
    """[SCT-7] RSS 결과를 **같은 문**(rank_and_pick)에 태워 상위만 연다.

    🔴 선별 규칙을 여기 복사하지 않는다 — 토르 경로와 **같은 함수**를 쓴다.
    ⚠️ [SCT-8] `team` 이 `None` 인 항목은 **대진 질의**다. 제목에 두 팀이 다
       나오므로 홈으로 문을 지나게 하고, 결과는 **양 팀에 모두** 붙인다
       (추출이 팀별로 기사를 고르기 때문이다). 본문은 한 번만 연다.
    ⚠️ `stats` 를 주면 `{"hits": n}` 을 채운다 — 호출부가 "대진 질의가
       충분한가"를 판단할 근거다.
    """
    from app.engine.scout_config import rank_and_pick

    out: list[dict] = []
    seen: set[str] = set()
    dropped = 0
    hits_total = 0
    for team, q in queries:
        hits = await rss_hits(q, league=league, stage=stage, now=now,
                              sport=sport, kickoff=kickoff)
        hits_total += len(hits)
        if not hits:
            continue
        pair = team is None
        screen_team = jg.get("home") if pair else team
        picked, disc = rank_and_pick(hits, league=league, stage=stage,
                                     team=screen_team, kickoff=kickoff, now=now,
                                     with_discard=True)
        if pair and not picked:
            # 제목이 원정 팀만 말하는 경우도 있다 — 한 번 더 본다.
            picked, disc = rank_and_pick(hits, league=league, stage=stage,
                                         team=jg.get("away"), kickoff=kickoff,
                                         now=now, with_discard=True)
        dropped += sum(disc.values())
        for h in picked:
            u = h.get("url") or ""
            if not u or u in seen:
                continue
            seen.add(u)
            body = await _fetch_article_body(u)
            if h.get("undated") and body:
                from app.engine.scout_config import body_date_ok

                ok, why = body_date_ok(body, kickoff=kickoff, now=now)
                if not ok:
                    dropped += 1
                    logger.info("[rss] 본문 재검사 폐기 %s — %s", u, why)
                    continue
            # 🔴 대진 기사는 **양 팀 모두**의 재료다. 본문은 한 번만 열고
            #    행만 둘로 만든다(추출이 팀으로 기사를 고른다).
            for t in ([jg.get("home"), jg.get("away")] if pair else [team]):
                if not t:
                    continue
                out.append(_article(
                    title=h.get("title") or "", url=u,
                    source=h.get("source") or "Google News",
                    team=t, body=body or h.get("title") or "",
                    age_h=None))
    if stats is not None:
        stats["hits"] = hits_total
    if out or dropped:
        logger.info("[rss] %s@%s 검색결과 %d건 → 기사 %d건 · 폐기 %d건",
                    jg.get("away"), jg.get("home"), hits_total, len(out), dropped)
    return out


async def _tor_supplement(jg: dict, queries: list[tuple[str, str]], *,
                          league: str | None = None, stage: str = "pre",
                          kickoff=None, now=None, pool=None) -> list[dict]:
    """[SAT-7] 토르 경유 DDG 보강. **satellite_tor_enabled 일 때만.**

    ⚠️ 한국 소스는 부르지 않는다(호출부가 KBO 를 넘기지 않고, tor_search 도
       한국어 질의를 거부한다 — 이중 방어). 실패는 빈 리스트.

    🔴 [SCT-4 2026-09-14] `league` 를 주면 **선별을 `scout_config` 에 맡긴다**
       (지시문 Part 2 / 4-3: 제목·날짜·신선도 문 → tier 정렬 → 상위 3개).
       안 주면 종전 그대로 제목 문만 본다 — 야구 호출부의 동작은 바뀌지 않는다.
       ⚠️ 규칙을 여기에 베끼지 않는다. `rank_and_pick` 이 원본이다.
    """
    from app.config import get_settings

    if not get_settings().satellite_tor_enabled:
        return []
    from app.collectors import tor_search

    out: list[dict] = []
    seen: set[str] = set()
    dropped = 0
    # 🔴 [TOR-1] 이번 호출에서 403 을 봤는지. "검색했는데 0건"과 "막혀서 못
    #    했다"는 다른 말이고, 뒤엣것은 원장에 남아야 다음에 다시 재지 않는다.
    _rl_before = tor_search.RATE_LIMITED_AT
    for team, q in queries:
        try:
            hits = await tor_search.search(q)
        except Exception as exc:
            logger.warning("[satellite] 토르 보강 실패 %s: %s", team, exc)
            continue
        if league:
            from app.engine import scout_config as SC

            picked, disc = SC.rank_and_pick(hits, league=league, stage=stage,
                                            team=team, kickoff=kickoff, now=now,
                                            with_discard=True)
            dropped += sum(disc.values())
            hits = picked
        for h in hits:
            u = h.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            # 🔴 [URL-1] **열기 전에 제목을 본다.** 팀을 말하지 않는 기사는
            #    본문을 열지 않는다 — 실측 2026-09-13: 위성 26건 중 24건이
            #    음식·F1 기사였는데 전부 본문까지 열었다.
            #    ⚠️ `league` 를 준 경로는 `rank_and_pick` 이 이미 같은 문을
            #       지났다 — 두 번 걸러도 결과는 같고, 건수만 이중으로 세지
            #       않게 여기서는 건너뛴다.
            if not league and not _title_hits(h.get("title") or "", team):
                dropped += 1
                continue
            body = await _fetch_article_body(u)
            # 🔴 [SCT-6] 날짜를 **모르고** 연 기사는 본문으로 다시 본다.
            #    증거(article:published_time·본문 날짜·지난 연도)가 있을 때만
            #    버린다 — 본문에도 날짜가 없으면 통과다.
            if h.get("undated") and body:
                from app.engine.scout_config import body_date_ok

                ok, why = body_date_ok(body, kickoff=kickoff, now=now)
                if not ok:
                    dropped += 1
                    logger.info("[scout] 본문 재검사 폐기 %s — %s", u, why)
                    continue
            out.append(_article(
                title=h.get("title") or "", url=u, source="DDG(토르)",
                team=team, body=body or h.get("snippet") or h.get("title") or "",
                age_h=None))
    if tor_search.RATE_LIMITED_AT != _rl_before:
        # 🔴 [TOR-1 사용자 지시] 속도 제한을 **원장에** 남긴다.
        #    ⚠️ 새 stage 를 만들지 않는다 — `game_trace.STAGES` 가 원본이고,
        #       사건 이름은 `ref.event` 로 남긴다.
        from app.engine import game_trace as GT

        await GT.note(pool, game_id=jg.get("game_id"),
                      sport=(jg.get("sport") or "soccer"),
                      date=(now or datetime.now(timezone.utc)).date().isoformat(),
                      stage=GT.COLLECT,
                      summary=f"tor_rate_limited — DDG 403/429 (질의 {len(queries)}건)",
                      ref={"event": "tor_rate_limited",
                           "queries": [q for _, q in queries][:4],
                           "min_gap_sec": tor_search.MIN_GAP_SEC})
        logger.info("[tor] 속도 제한 — 원장에 tor_rate_limited 로 남겼다 (game=%s)",
                    jg.get("game_id"))
    if out or dropped:
        # ⚠️ 조용히 줄이지 않는다 — 반대 위험(정상 폐기)을 재려면 건수가 남아야 한다
        logger.info("[satellite] 토르 보강 %s@%s +%d건 · 제목 불일치 폐기 %d건",
                    jg.get("away"), jg.get("home"), len(out), dropped)
    return out


def _need_of(jg: dict) -> list | None:
    """[HYP-1] 원장 가설 → `["home.out", …]`. 없으면 **None**(종전대로 전부).

    🔴 키 모양은 `hypothesis.Need.key` 가 원본이다 — 여기서 손으로 짓지 않는다.
    ⚠️ 빈 목록("찾을 것 없음" = 보드 고정)과 **None**(가설 없음)은 다르다.
    """
    raw = (jg or {}).get("hypothesis")
    if not raw:
        return None
    try:
        import json as _j

        from app.engine import hypothesis as HY

        hyp = _j.loads(raw) if isinstance(raw, str) else raw
        need = [HY.Need(n["field"], n["side"], n.get("why", ""))
                for n in (hyp.get("need") or [])]
        return [n.key for n in need]
    except Exception as exc:
        logger.info("[scout] game=%s 가설을 못 읽었다: %s", jg.get("game_id"), exc)
        return None


async def gather(jg: dict, redis, *, client=None, now: datetime | None = None,
                 pool=None) -> int:
    """경기 1건을 긁어 캐시에 쓴다. 반환: 적재 기사 수.

    ⚠️ 재료 0건이어도 크래시하지 않고 0을 돌려준다(조용한 0 금지). redis 가 없으면
       수집만 하고 캐시는 건너뛴다.
    """
    sport = (jg.get("sport") or "").lower()
    gid = jg.get("game_id") or jg.get("id")
    # [PA-18] SAT-8 이 구속 숫자를 남길 수 있게 핸들을 실어 둔다.
    jg["_redis"] = redis
    adapter = _ADAPTERS.get(sport)
    if adapter is None:
        return 0
    # 🔴 [SOC-9] 축구만 pool 을 받는다 — 라인업을 `lineups` 에 남긴다.
    #    야구 어댑터 시그니처는 건드리지 않는다.
    if sport == "soccer":
        # 🔴 [FOT-2 사용자 지시] **구조 JSON 이 먼저다.** 층1(부상표·피드)보다
        #    앞에서 붙여야 어댑터가 그 값을 보고, 기사 추출이 보조로 내려간다.
        #    ⚠️ 실패는 결측이다 — 수집을 막지 않는다.
        try:
            from app.collectors import fotmob

            await fotmob.attach(jg, redis=redis)
        except Exception as exc:
            logger.warning("[fotmob] 부착 실패 game=%s: %s", gid, exc)
        articles = await adapter(jg, client=client, now=now, pool=pool)
    else:
        articles = await adapter(jg, client=client, now=now)
    # 🔴 [ROS-1 2026-09-11] **공시를 맨 앞에 둔다.** 검색 기사보다 공식이 먼저다.
    #    실측 2026-09-11: 위성 재료 76건 중 조사 인용 0건이었고, 모인 것은
    #    굿즈·타팀 FA 전망이었다. KBO 는 **말소로 결장을 알리는데** 우리는
    #    그 사건을 재료로 만들지 않고 있었다.
    if sport == "kbo":
        articles = await _kbo_official(jg, redis) + articles
    await _write_cache(redis, sport, gid, articles)
    # 🔴 [PA-12 2026-09-16 사용자 지시 "위성수집으로 하면 되잖아"]
    #    **종목을 가르지 않는다.** 종전 SCT-5 는 "추출은 축구만"이었고, 이유는
    #    "야구 스키마(타순·등판)는 4-4 에 없고 없는 칸을 억지로 채우면 그게 곧
    #    거짓 재료가 된다" 였다.
    #    그런데 **야구 가설이 요구하는 칸은 타순·등판이 아니다** — `out`·
    #    `doubt`·`last3` 셋이고 전부 공용 스키마에 있다. 그리고 추출 스키마에
    #    타순·등판 칸이 **아예 없어서** LLM 이 그 칸을 만들 자리가 없다.
    #    SCT-5 의 걱정은 스키마로 이미 막혀 있다.
    # 🔴 실측 2026-09-16: 야구가 기사 **35건을 모으고 추출 0회** 였고, 그래서
    #    원장 g8773 의 need 5개가 **전부 '미상'** 이었다. 가설을 세우고
    #    아무것도 확인하지 못한 채 판정하고 있었다.
    # ⚠️ 콜이 순증한다 — 경기당 1콜 × (MLB 15 + KBO 5 + NPB 6) ≈ 하루 26콜.
    #    위성은 15분 잡이라 분산되고, 같은 URL 묶음이면 다시 묻지 않는다.
    # ⚠️ 추출이 실패해도 기사 수집 결과(반환값)는 그대로다.
    if articles:
        from app.leagues import league_labels

        lkey = league_labels().get(jg.get("league") or "") or ""
        # 🔴 [EXT-1] **경기당 1콜.** 종전 팀별 3건(=6콜)이 groq 무료 한도를
        #    매 사이클 태웠다(실측 2026-09-14: 429 백오프 340~467초).
        # 🔴 [HYP-1 2026-09-17] **가설을 수집으로 내려보낸다.**
        #    `hypothesis.py` 가 "페이블 순서의 핵심"이라고 적은 자리인데
        #    호출부가 없어서 need 가 한 번도 수집에 닿은 적이 없었다.
        #    ⚠️ 가설이 없으면(판정 전·보드 고정·옛 행) **None** 이고 그때는
        #       종전 그대로다 — 굶기지 않는다.
        facts = await extract_game_facts(articles, home=jg.get("home") or "",
                                         away=jg.get("away") or "",
                                         league=lkey, redis=redis, jg=jg,
                                         need=_need_of(jg))
        await _write_extract(redis, sport, gid, facts)
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


#: [SCT-5] 추출 캐시 키. 기사 캐시와 **다른 키**다 — 원문(기사)과 해석(추출)을
#  한 칸에 섞으면 어느 쪽이 실패했는지 못 가른다.
EXTRACT_KEY = "scout:{sport}:{game_id}"


def _extract_key(sport: str, game_id) -> str:
    return EXTRACT_KEY.format(sport=(sport or "").lower(), game_id=game_id)


#: [EXT-1] 관련 문단 창 반폭(자). 지시문 후속 지시 — 기사 전문 대신 이만큼만.
WINDOW_SPAN = 300
#: 한 경기에서 LLM 에 넣는 창의 총 상한(자). 로컬 3B 의 문맥·속도를 고려한 값.
WINDOW_BUDGET = 6000
#: 창을 잡을 단서. 🔴 리그별 현지어는 `search_terms` 가 원본이라 여기서는
#  **팀 이름**과 만국 공통 표기만 쓴다 — 낱말 목록을 새로 만들지 않는다.
_WINDOW_HINTS = ("out", "injur", "infortun", "formazion", "alineac", "aufstellung",
                 "opstelling", "compos", "lineup", "XI", "결장", "선발", "부상")


def _windows(body: str, terms, *, span: int = WINDOW_SPAN) -> str:
    """[EXT-1] 단서 주변 ±`span` 자만 남긴다. 겹치면 합친다.

    🔴 기사 전문을 넣지 않는다 — 경기당 1콜로 줄이려면 입력이 작아야 하고,
       결장·라인업은 **문단 하나**에 모여 있다(실측: 프리뷰 기사 구조).
    ⚠️ 단서가 하나도 없으면 **머리 `span`×2 자**를 준다. 빈손으로 부르면
       "기사를 읽었는데 아무것도 없다"와 "안 읽었다"가 같아진다.
    """
    text = " ".join(str(body or "").split())
    if not text:
        return ""
    low = text.lower()
    hits: list[tuple[int, int]] = []
    for t in list(terms or []) + list(_WINDOW_HINTS):
        t = str(t or "").strip().lower()
        if len(t) < 2:
            continue
        i = low.find(t)
        while i >= 0:
            hits.append((max(0, i - span), min(len(text), i + len(t) + span)))
            i = low.find(t, i + len(t))
    if not hits:
        return text[:span * 2]
    hits.sort()
    merged = [list(hits[0])]
    for a, b in hits[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return " … ".join(text[a:b] for a, b in merged)


def _extract_prompt(home: str, away: str, blocks: list[tuple[str, str]],
                   need: list | None = None) -> str:
    """[EXT-1] **경기 하나에 프롬프트 하나.** 두 팀을 한 번에 묻는다.

    🔴 스키마를 손으로 적지 않는다 — `EXTRACT_SCHEMA` 에서 만든다.
    🔴 [HYP-1 2026-09-17] `need` 를 주면 **무엇을 찾는지 말한다.**
       `hypothesis.py` 가 "이것이 페이블 순서의 핵심"이라고 적은 자리다 —
       게이트가 방향을 정하고 방향이 need 를 정하는데, 수집이 그 need 를
       **본 적이 없었다**(호출부 미배선).
    ⚠️ **지휘는 "무엇을 찾을지 말해 주는 것"이지 "찾은 것을 버리는 것"이
       아니다.** 스키마 8칸은 그대로 다 돌려받는다 — need 밖 칸을 비우면
       분석 입력이 도로 좁아진다(ANL-5 로 넣은 notes 가 사라진다).
    ⚠️ `need` 가 없으면 프롬프트는 **종전과 글자 하나 안 다르다.**
    """
    from app.engine.scout_config import EXTRACT_SCHEMA

    keys = ", ".join(f'"{k}"' for k in EXTRACT_SCHEMA)
    want = ""
    if need:
        # 🔴 키 모양(`home.out`)은 `hypothesis.Need.key` 가 원본이다.
        want = ("7. 이 경기에서 **우선 찾는 것**: " + " · ".join(need)
                + ". 다른 칸도 발췌에 있으면 채운다.\n")
    src = "\n\n".join(f"[기사 {i + 1} · {u}]\n{w}"
                        for i, (u, w) in enumerate(blocks))
    return (
        "다음 기사 발췌에서 **두 팀 각각**의 경기 전 정보를 뽑아 JSON 하나로 답한다.\n"
        '형식: {"teams": [{...홈...}, {...원정...}]}\n'
        f"각 팀 객체에 허용된 칸은 이것뿐이다: {keys}\n"
        "규칙\n"
        "1. 발췌에 없는 것은 만들지 않는다. 모르면 빈 목록·빈 문자열.\n"
        "2. 전적·감독 예상 스코어·팬 반응·베팅 팁은 뽑지 않는다.\n"
        "3. xi_status 는 'predicted' 또는 'official' 둘 중 하나다.\n"
        "4. notes 는 한 줄이다.\n"
        "5. team 칸에는 아래 주어진 팀 이름을 그대로 쓴다.\n"
        "6. JSON 만 출력한다.\n"
        + want
        + f"[홈] {home}\n[원정] {away}\n\n{src}"
    )


def _extract_cache_key(urls, home: str, away: str) -> str:
    """[EXT-1] URL 해시 캐시 키. **같은 기사 묶음이면 다시 묻지 않는다.**"""
    import hashlib

    raw = "|".join(sorted(str(u or "") for u in urls)) + f"|{home}|{away}"
    return "scout:x:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


#: 🔴 [EXT-2] 키워드 사전 — `config/evidence_lexicon.yaml` 이 **원본**이다.
#   v2 STEP 7-4 가 쓸 그 파일이고 여기서 낱말을 새로 짓지 않는다.
_LEX: list | None = None


def _lexicon() -> list:
    global _LEX
    if _LEX is None:
        try:
            import yaml

            f = (pathlib.Path(__file__).resolve().parents[2]
                 / "config" / "evidence_lexicon.yaml")
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            lex = doc.get("lexicon") or {}
            _LEX = [w for words in lex.values() for w in (words or [])]
        except Exception as exc:
            logger.warning("[scout] 키워드 사전 로드 실패: %s", exc)
            _LEX = []
    return _LEX


def _lexicon_hit(text: str) -> bool:
    """제목·본문에 라인업/결장 계열 낱말이 있나. ⚠️ 부분 문자열이다."""
    t = str(text or "")
    return any(w in t for w in _lexicon())


async def get_depth(redis, *, game_id) -> str:
    """이 경기의 수집 깊이. 🔴 정하는 것은 v2 STEP 6 `app/flow/select.py` 다.

    지금은 흐름 state 에 depth 칸이 없으므로 **폴백**(`flow.depth_fallback`)을
    돌려준다. STEP 6 이 오면 **이 함수만** 실제 값을 돌려주게 바꾼다.
    ⚠️ 폴백 값을 코드에 박지 않는다 — `config/rules.yaml` 이 원본이다.
    """
    from app.flow import rules as R

    return str(R.get("depth_fallback", "normal") or "normal")


async def _article_cap(redis, game_id) -> int:
    """depth → 경기당 추출 기사 수. 🔴 숫자는 `rules.yaml` 이 원본이다."""
    from app.flow import rules as R

    depth = await get_depth(redis, game_id=game_id)
    caps = R.get("depth_articles", {}) or {}
    try:
        return int(caps.get(depth, caps.get("normal", 2)))
    except (TypeError, ValueError):
        return 2


#: LLM 일일 호출 계수기. 🔴 형식은 `espn_odds` 의 예산 기록과 같다
#  (`api_calls:{날짜}` 해시). 새 방식을 만들지 않는다.
_LLM_CALL_KEY = "api_calls:{date}"


async def _llm_budget_ok(redis) -> bool:
    """오늘 LLM 추출 호출이 상한 안인가. 🔴 넘으면 **건너뛴다**(예외 금지).

    🔴 [D27 2026-09-22] **`app.engine.rules` 다.** 종전에는 `app.flow.rules` 를
       썼는데 그 모듈은 경로에 `flow.` 접두사를 붙이므로
       `flow.llm.daily_call_cap` 을 찾았고 그런 블록은 없다 — 값은 언제나
       코드 폴백 200 이었다(실측 2026-09-22: flow→None · engine→200).
       폴백이 config 값과 우연히 같아서 증상이 없었을 뿐, **설정을 고쳐도
       반영되지 않았다.**
    ⚠️ 바로 위 `get_depth`·`_article_cap` 은 `app.flow.rules` 가 **맞다** —
       `depth_fallback`·`depth_articles` 는 실제로 `flow:` 블록 안에 있다.
       같이 옮기면 그쪽이 None 이 되어 조용히 폴백으로 돈다. 계약이 잠근다.
    ⚠️ redis 가 없으면 셀 수 없다 — 그때는 막지 않는다(관측만).
    """
    from app.engine import rules as R

    cap = int(R.get("llm.daily_call_cap", 200) or 200)
    if redis is None or cap <= 0:
        return True
    try:
        from datetime import UTC, datetime

        key = _LLM_CALL_KEY.format(date=datetime.now(UTC).date().isoformat())
        used = int(await redis.hget(key, "scout_extract") or 0)
        return used < cap
    except Exception as exc:
        logger.debug("[scout] LLM 예산 조회 실패 — 막지 않는다: %s", exc)
        return True


async def _llm_budget_spend(redis, n: int = 1) -> None:
    """실제로 부른 만큼 센다. ⚠️ 실패해도 추출을 되돌리지 않는다."""
    if redis is None or n <= 0:
        return
    try:
        from datetime import UTC, datetime

        key = _LLM_CALL_KEY.format(date=datetime.now(UTC).date().isoformat())
        await redis.hincrby(key, "scout_extract", int(n))
        await redis.expire(key, 7 * 24 * 3600)
    except Exception as exc:
        logger.debug("[scout] LLM 예산 기록 실패: %s", exc)


def _extract_names(home: str, away: str, league: str) -> tuple:
    """[DS-5] 재순위에 넘길 **팀 이름들** — 영문 DB 이름 + 현지 표기.

    🔴 **현지 표기가 없으면 NPB 가 통째로 죽는다.** DB 는
       `Chiba Lotte Marines` 인데 기사는 `千葉ロッテマリーンズ` 로 쓴다.
       실측 2026-09-21: 별칭을 넣자 증거 0자 경기가 **4 → 2** 로 줄었다.
    ⚠️ 표를 여기서 만들지 않는다 — `news_rss.QUERY_ALIAS`(한/일) 와
       `scout_config.local_name`(축구) 이 원본이다(사본 금지).
       AUD-1 에서 **똑같은 실수를 했다**: DB 영문명으로 검색어를 만들어
       `Hanwha Eagles 내일의 선발투수` 가 나갔고 회수가 0 이었다.
    """
    from app.collectors.news_rss import QUERY_ALIAS
    from app.engine.scout_config import local_name

    lg = (league or "").lower()
    out: list[str] = []
    for n in (home, away):
        if not n:
            continue
        for v in (n, QUERY_ALIAS.get(n), local_name(lg, n)):
            if v and v not in out:
                out.append(v)
    return tuple(out)


def _rerank_blocks(picked: list, *, home: str, away: str, league: str):
    """[DS-5] 기사 → **질문과 관련된 문단만**. 없으면 빈 목록.

    🔴 빈 목록은 "증거가 없다"는 뜻이고, 그때는 **LLM 을 부르지 않는다**
       (절대 규칙 6). 실측 2026-09-21: 롯데vs세이부·니혼햄vs오릭스의 기사
       6건에 그 경기 이야기가 아예 없었다(아시안게임 식사 문제 · 한신 투수).
       지금은 그 3,600자가 통째로 들어간다.
    """
    from app.deepsearch import rerank as R

    paras = R.split(picked)
    top = R.top_k(paras, names=_extract_names(home, away, league))
    return [(p.url or "", p.text) for p in top]


async def extract_game_facts(articles: list[dict], *, home: str, away: str,
                             league: str, redis=None, jg: dict | None = None,
                             need: list | None = None) -> dict:
    """[EXT-1] 경기 하나 → `{"home": {...}, "away": {...}}`. **LLM 1콜.**

    🔴 종전에는 팀별 3건 = **경기당 6콜**이었고 기사 전문을 넣었다. groq 무료
       한도가 그 때문에 매 사이클 429 였다(실측 2026-09-14: 백오프 340~467초).
    🔴 같은 URL 묶음이면 **다시 묻지 않는다**(URL 해시 캐시).
    🔴 [U6 2026-09-15] `need` 를 주면 **그 칸만** 판정 입력으로 남긴다
       (`hypothesis.need_keys` 모양: `["home.out", "away.midweek", …]`).
       나머지는 버리지 않고 `collected_extra` 로 세기만 한다 — 왜 안 썼는지를
       나중에 답할 수 있어야 한다.
    ⚠️ **`need` 를 못 받으면 종전대로 전부 쓴다.** need 가 빈 목록인 것(보드
       고정)과 안 받은 것(호출부 미배선)은 다르다 — 굶기지 않는다.
    ⚠️ 실패해도 예외를 올리지 않는다 — 추출 실패가 기사 수집을 되돌리면 안 된다.
    """
    from app.engine.scout_config import (FETCH_PER_STAGE, RANK_UNLISTED, merge,
                                         rank, validate)
    from app.engine.team_form import _complete_free, parse_json_object
    from app.llm.judge_route import chain

    # 🔴 [PA-21] **반복 본문을 먼저 버린다.** 길이 검사는 1,200자짜리
    #    사이트 안내문을 못 잡는다(실측 g8360: 17건 중 15건).
    from app.engine.scout_config import drop_boilerplate

    have = [a for a in drop_boilerplate(articles) if (a.get("body") or "").strip()]
    if not have:
        logger.info("[scout] %s@%s — 본문 있는 기사가 없다", away, home)
        return {}
    # 🔴 [EXT-2 / STEP 1-g 2026-09-20 사용자 결정 `two_gates_0920`]
    #    **게이트 라벨로 가르지 않는다.** 종전 조건(`gate_target or tag.big`)은
    #    위성이 **구경로 게이트**(`pick_ledger.gate_of`, tier+form)를 보고
    #    추출 여부를 정하게 했다. 흐름은 다른 사전값(team_elo)을 쓰므로 같은
    #    경기에 게이트가 둘이었고, 흐름의 가설이 수집에 닿지 못했다.
    #    실측 2026-09-20: KBO 5경기가 기사를 6~14건씩 모으고도 `out` 이 찬
    #    것은 한 경기뿐. 두산@KT 는 기사 12건을 쥐고 여섯 변수 전건 미상.
    #      [scout] Doosan Bears@KT Wiz — 게이트 동의 · 빅매치 아님 · LLM 추출 생략
    #    → **기사가 1건 이상 모인 전 경기**가 대상이다.
    # ⚠️ 그 대신 **두 겹으로 묶는다**: 경기당 기사 상한(depth)과 일일 LLM 상한.
    #    종전에는 §3 예산이 최대 8경기로 묶고 있었다.
    cap = await _article_cap(redis, (jg or {}).get("game_id"))
    if cap <= 0:
        logger.info("[scout] %s@%s — depth=shallow · 기사 추출 0건", away, home)
        return {}
    if not await _llm_budget_ok(redis):
        logger.info("[scout] %s@%s — llm_cap 도달 · 추출 건너뜀", away, home)
        return {}
    # 🔴 고르는 순서: **키워드 적중 우선**, 같으면 등급, 그다음 최신순.
    #    키워드는 `config/evidence_lexicon.yaml` 이 원본이다(코드에 박지 않는다).
    def _score(i_a):
        i, a = i_a
        text = f"{a.get('title') or ''} {a.get('body') or ''}"
        hit = 0 if _lexicon_hit(text) else 1
        return (hit, min(rank(a.get("url") or "", league), RANK_UNLISTED), i)

    ranked = sorted(enumerate(have), key=_score)
    picked, seen_url = [], set()
    for _, a in ranked:
        u = a.get("url") or ""
        if u in seen_url:
            continue
        seen_url.add(u)
        picked.append(a)
        if len(picked) >= min(cap, FETCH_PER_STAGE):
            break

    key = _extract_cache_key([a.get("url") for a in picked], home, away)
    if redis is not None:
        try:
            hit = await redis.get(key)
        except Exception:
            hit = None
        if hit:
            logger.info("[scout] %s@%s — 캐시 적중(%s), 묻지 않는다", away, home, key)
            try:
                return json.loads(hit) or {}
            except Exception:
                pass

    # 🔴 [DS-5 2026-09-21] **재순위로 줄인다.** 실측(운영 11경기): 창 6,000자가
    #    400~2,130자가 된다. 그 6,000자에 피카츄 기사·이강인 악플이 40%를
    #    차지하고 있었다(game=Valencia CF).
    #    ⚠️ 끄면 종전 `_windows` 경로다 — config 한 줄, 배포 없이 되돌린다.
    from app.deepsearch.runtime import load_config as _ds_cfg

    # 🔴 [DEC-3 2026-09-21] `used` 를 **여기서** 초기화한다. 재순위 경로로 가면
    #    아래 폴백 블록이 안 돌아 `used` 가 정의되지 않는데, 맨 끝 로그가 그것을
    #    쓴다 — `UnboundLocalError` 다. 지금까지는 **항상 폴백을 거쳐서** 가려져
    #    있었고(DS-5 의 폴백 설계), 규칙 개정으로 그 경로가 사라지자 드러났다.
    blocks, used = [], 0
    if ((_ds_cfg().get("rerank") or {}).get("wire_extract")) is not False:
        blocks = _rerank_blocks(picked, home=home, away=away, league=league)
        used = sum(len(t) for _, t in blocks)
        if not blocks:
            # 🔴 [DEC-3 2026-09-21 **사용자 결정 · 규칙 개정**]
            #    "관련 문단 ≥1 일 때만 추출한다. 0 이면 미상이다."
            #    ⚠️ DS-5 때 나는 같은 변경을 만들었다가 **되돌렸다** — 기존 계약
            #       17건이 깨졌고 "내 변경을 통과시키려고 계약을 고치는 것은
            #       회귀를 숨기는 수"라고 적었다. **지금은 사용자가 규칙을 바꿨다.**
            #    실측 2026-09-21: 운영 11경기 중 2건이 이 자리다(롯데vs세이부 ·
            #    니혼햄vs오릭스). 둘 다 기사 6건에 **그 경기 이야기가 없었다**
            #    (아시안게임 식사 문제 · 다른 팀 투수). LLM 호출 11 → 9.
            #    ⚠️ 되돌리려면 `rerank.require_relevant: false` 한 줄이다.
            if ((_ds_cfg().get("rerank") or {}).get("require_relevant")) is not False:
                logger.info("[scout] %s@%s — 증거 문단 0 · 추출 안 함 "
                            "(기사 %d건 · reason=no_relevant_paragraph)",
                            away, home, len(picked))
                return {"reason": "no_relevant_paragraph",
                        "articles": len(picked)}
            logger.info("[scout] %s@%s — 증거 문단 0 · 종전 창 경로로 내려간다 "
                        "(기사 %d건)", away, home, len(picked))
    if not blocks:
        for a in picked:
            w = _windows(a.get("body") or "", (home, away))
            if not w:
                continue
            w = w[:max(0, WINDOW_BUDGET - used)]
            if not w:
                break
            used += len(w)
            blocks.append((a.get("url") or "", w))
    if not blocks:
        return {}

    try:
        # 🔴 [HYP-1] **가설이 수집을 지휘한다.** need 를 프롬프트에 실어
        #    "무엇을 찾는지"를 말한다. 못 받으면 종전과 같은 프롬프트다.
        if need:
            logger.info("[scout] %s@%s 가설 지휘 — 우선 찾을 것 %s",
                        away, home, need)
        # 🔴 [EXT-2] **부른 만큼 센다.** 상한 검사는 위에서 이미 했고, 여기서는
        #    실제 호출을 기록한다 — 검사만 하고 안 세면 상한이 영영 안 찬다.
        await _llm_budget_spend(redis, 1)
        raw = await _complete_free(chain("form"),
                                   _extract_prompt(home, away, blocks, need),
                                   1536, "form")
    except Exception as exc:
        logger.warning("[scout] 추출 호출 실패 %s@%s: %s", away, home, exc)
        return {}
    parsed = parse_json_object(raw) or {}
    rows = [validate(x) for x in (parsed.get("teams") or []) if isinstance(x, dict)]
    rows = [r for r in rows if r]
    if not rows:
        logger.info("[scout] %s@%s — 추출 0건(JSON 불량 또는 팀 칸 없음)", away, home)
        return {}
    # 🔴 [HYC-1 2026-09-20 사용자 결정] **출처는 코드가 아는 것만 쓴다.**
    #    `blocks` 는 이 호출의 프롬프트에 **실제로 들어간** 기사다 — 모델이
    #    뭐라고 답하든 이 목록은 우리가 안다. ⑤의 신뢰 검사가 이것을 본다.
    #    ⚠️ 종전 `got.setdefault("source", picked[0]...)` 를 **뺐다.** 두 가지
    #       이유다: (a) `validate()` 가 이미 `source: ""` 키를 만들어 두므로
    #       `setdefault` 는 **한 번도 동작한 적이 없다**(실측: 운영 상자 42쪽 중
    #       30쪽이 빈 칸). (b) 설령 동작해도 "첫 기사에서 나왔다"는 것은
    #       **우리가 모르는 사실**이다 — 항목별 출처는 HYC-1b 의 `article_idx` 다.
    fed = [u for u, _w in blocks if u]
    # 🔴 [W2 2026-09-21] **한 행이 양쪽에 들어가지 않는다.** 종전에는 쪽마다
    #    `_same_team` 으로 훑어서, 두 팀이 토큰을 공유하면(`madrid`) 같은 행이
    #    양쪽에 뽑혔다 — 실측 `scout:soccer:11330` 이 그 모양이다.
    #    ⚠️ 못 정한 행은 버리지 않고 `unknown` 으로 모은다(로그로 남긴다).
    by_side = split_rows_by_side(rows, home=home, away=away)
    if by_side.get("unknown"):
        logger.info("[scout] %s@%s — 귀속 미상 %d행 (팀: %s)", away, home,
                    len(by_side["unknown"]),
                    " · ".join(str(r.get("team")) for r in by_side["unknown"]))
    out: dict = {}
    for side, name in (("home", home), ("away", away)):
        mine = [r for r in [by_side.get(side)] if r]
        # ⚠️ 개명은 `merge` **뒤**다 — merge 는 `source` 로 순위를 매긴다.
        got = merge(mine, league=league)
        if got:
            # 🔴 LLM 이 쓴 출처·시각은 **버리지 않고 이름만 바꾼다.** 판정·검사에
            #    쓰지 않되, 나중에 "지어낸 출처 비율"을 잴 자료로 남긴다.
            got["llm_source"] = got.pop("source", "") or ""
            got["llm_fetched_at"] = got.pop("fetched_at", "") or ""
            got["sources_fed"] = list(fed)
            out[side] = _json_wins(got, (jg or {}).get("fotmob"), side)
    # 🔴 [W2 2026-09-21] 귀속이 **맞았는지**를 한 번 더 본다. 쪽은 갈렸는데
    #    명단이 글자까지 같으면 LLM 이 한쪽 것을 양쪽에 적은 것이다
    #    (실측 `scout:soccer:11334` — SonderjyskE / Randers FC).
    out = resolve_attribution(out)
    for a in picked:
        u = a.get("url") or ""
        if rank(u, league) >= RANK_UNLISTED:
            logger.info("[scout] 승격후보 %s (%s@%s)", _domain_of(u), away, home)
    logger.info("[scout] %s@%s 추출 1콜 — 기사 %d건 · 창 %d자 · 홈 out %d · 원정 out %d",
                away, home, len(blocks), used,
                len((out.get("home") or {}).get("out") or []),
                len((out.get("away") or {}).get("out") or []))
    if redis is not None and out:
        try:
            await redis.set(key, json.dumps(out, ensure_ascii=False), ex=CACHE_TTL)
        except Exception as exc:
            logger.debug("[scout] 캐시 기록 실패 %s: %s", key, exc)
    return out


#: 🔴 [U6 2026-09-15] 추출 스키마 **8칸**. 원본은 `hypothesis.FIELDS` 다 —
#   여기 목록을 손으로 적지 않는다(두 이름표를 만들면 U7 이 못 맞춘다).
def _schema_fields() -> tuple:
    from app.engine.hypothesis import FIELDS

    return tuple(FIELDS)


def fill_schema(box: dict) -> dict:
    """8칸을 **전부** 채운다. 없는 칸은 `None`(모른다)이지 빈 값이 아니다.

    🔴 종전에는 doubt·last3·midweek·notes 가 프롬프트에만 있고 저장되지 않아
       U7(확인 판정)이 맞출 대상이 없었다(실측 2026-09-15: 8칸 중 4칸 유실).
    ⚠️ **0 이나 빈 목록으로 채우지 않는다.** "모른다"와 "없다"는 다르다 —
       `out=[]` 는 결장 0명이고 `out=None` 은 안 봤다는 뜻이다.
    """
    out = dict(box or {})
    for f in _schema_fields():
        out.setdefault(f, None)
    return out


def snippet_level(source_tier: int | None, box: dict) -> bool:
    """[U6] 이 자료가 **조각**인가 — tier 3 이상인데 수치가 하나도 없다.

    🔴 조각이면 확신 상한이 내려간다(U10 이 쓴다). 여기서는 표시만 한다.
    """
    if source_tier is None or int(source_tier) < 3:
        return False
    for f in ("out", "xi", "bench_notable", "last3"):
        v = (box or {}).get(f)
        if v:
            return False
    return True


def _json_wins(llm: dict, fm: dict | None, side: str) -> dict:
    """[FOT-4 사용자 지시] **out·xi 는 구조 JSON 이 정본.** LLM 은 보조 칸만.

    🔴 LLM 이 `out` 을 돌려줘도 JSON 과 다르면 **JSON 채택 + conflict 플래그**다.
       LLM 값을 버리지 않고 비교만 한다 — 버리면 왜 달랐는지 영영 모른다.
    ⚠️ JSON 이 없으면(축구가 아니거나 FotMob 결측) 종전 동작 그대로다.
    """
    if not fm:
        llm.setdefault("out_src", "llm")
        return llm
    box = (fm.get(side) or {})
    out = dict(llm)
    un = box.get("unavailable")
    if un is not None:
        names = [str(x.get("name") or "").strip() for x in un if x.get("name")]
        if set(names) != {str(x).strip() for x in (llm.get("out") or [])}:
            out["conflict"] = True
            out["out_llm"] = list(llm.get("out") or [])
        out["out"] = names
        out["out_src"] = "fotmob"
    else:
        out["out_src"] = "llm"
    starters = [p.get("name") for p in (box.get("starters") or []) if p.get("name")]
    if starters:
        out["xi"] = starters
        out["xi_status"] = fm.get("lineup_type") or out.get("xi_status")
        out["xi_src"] = "fotmob"
    # bench_notable 은 코드가 채운다(FotMob diff). LLM 값은 그때 덮인다.
    d = (fm.get("diff") or {}).get(side) or {}
    if d.get("bench_notable"):
        out["bench_notable"] = d["bench_notable"]
        out["surprise_in"] = d.get("surprise_in") or []
    if out.get("conflict"):
        logger.info("[scout] %s 결장 충돌 — JSON %s vs LLM %s",
                    llm.get("team"), out.get("out"), out.get("out_llm"))
    # 🔴 [U6] 8칸을 전부 채워 내보낸다. 없는 칸은 None 이다.
    out = fill_schema(out)
    out["snippet_level"] = snippet_level(out.get("source_tier"), out)
    return out


def apply_need(box: dict, side: str, need_keys: list | None) -> dict:
    """[U6] need 밖 칸을 **판정 입력에서 뺀다.** 지우지 않고 옮긴다.

    🔴 `need_keys` 가 `None` 이면 **종전대로 전부**다(호출부 미배선).
       빈 목록은 "찾을 것이 없다"(보드 고정)라 전부 뺀다 — 둘을 구분한다.
    🔴 뺀 칸은 `collected_extra` 에 이름만 남긴다. 버리면 "왜 안 썼나"를
       영영 모른다.
    """
    if need_keys is None:
        return dict(box or {})
    want = {k.split(".", 1)[1] for k in need_keys
            if k.startswith(f"{side}.")}
    out, extra = {}, []
    for f in _schema_fields():
        v = (box or {}).get(f)
        if f in want:
            out[f] = v
        else:
            out[f] = None
            if v:
                extra.append(f)
    for k, v in (box or {}).items():
        if k not in out:
            out[k] = v
    out["collected_extra"] = extra
    return out


def _same_team(a, b) -> bool:
    """LLM 이 `team` 을 살짝 달리 쓸 수 있다. 토큰 하나만 겹쳐도 같은 팀이다.

    ⚠️ [W2 2026-09-21] **귀속에는 더 쓰지 않는다.** 이 함수는 "두 이름이
       비슷한가"만 답하고, 한 경기의 **어느 쪽인가**는 `assign_side` 가 정한다.
       종전에는 이것으로 쪽을 정했고, 그래서 공통 토큰 `madrid` 하나로
       AT마드리드 카드가 레알에도 들어갔다(실측 `scout:soccer:11330`).
    """
    return bool(_tokens(a) & _tokens(b))


def _tokens(name) -> set:
    """이름 → 토큰 집합. 🔴 정규식을 두 곳에 적지 않는다."""
    import re as _re

    return {t for t in _re.split(r"[^\w가-힣]+", str(name or "").lower())
            if len(t) > 2}


def _generic_tokens() -> set:
    """팀을 가리지 못하는 흔한 말. 🔴 원본은 `pipeline._GENERIC_TEAM_TOKENS`
    다 — 여기서 목록을 손으로 적지 않는다(사본 금지).

    ⚠️ 못 읽어도 죽지 않는다. 그때는 아래 "그 경기 두 팀의 공유 토큰" 규칙만
       남고, `madrid` 류는 그것만으로도 걸러진다.
    """
    try:
        from app.pipeline import _GENERIC_TEAM_TOKENS

        return set(_GENERIC_TEAM_TOKENS)
    except Exception:
        return set()


def assign_side(row_team, home: str, away: str) -> str | None:
    """이 카드가 **어느 쪽인가.** 못 정하면 `None` — 찍지 않는다.

    🔴 [W2 2026-09-21] 실측이 만든 규칙이다.

        scout:soccer:11330 — 양쪽 카드의 `team` 이 **둘 다**
        `Club Atlético de Madrid` 였다. 원인은 한 줄이다:
            _same_team('Club Atlético de Madrid', 'Real Madrid CF') → True
        공통 토큰 `madrid` 하나로 AT마드리드 명단이 레알에도 들어갔고,
        ⑤의 방향이 양쪽 악재로 잡혀 **상쇄**됐다.

    🔴 **두 팀이 공유하는 토큰은 식별자가 아니다.** 같은 규율이 이미 저장소에
       있다 — `pipeline._shared_team_tokens` 의 머리말: "Boston Red Sox 속보가
       Chicago White Sox 카드에 붙었다. 공유 토큰은 식별자가 될 수 없다."
       여기서는 **그 경기 두 팀 사이**의 공유 토큰을 뺀다(별칭표가 없는
       리그에서도 통한다).

    ⚠️ 겹치는 토큰 수가 **같으면 못 정한 것**이다(`football.match_team_name`
       과 같은 규약 — 동점이면 None). 한쪽으로 찍으면 그때부터 거짓 자료가 된다.
    """
    gen = _generic_tokens()
    t = _tokens(row_team) - gen
    th, ta = _tokens(home), _tokens(away)
    shared = th & ta                       # 🔴 그 경기 두 팀의 공통 토큰
    th, ta = (th - shared) - gen, (ta - shared) - gen
    nh, na = len(t & th), len(t & ta)
    if nh == na:
        return None
    return "home" if nh > na else "away"


def split_rows_by_side(rows: list, *, home: str, away: str) -> dict:
    """추출 행들 → `{side: 행}`. 🔴 **한 행이 양쪽에 들어가지 않는다.**

    ⚠️ 어느 쪽인지 못 정한 행은 **버리지 않고** `unknown` 으로 모은다 —
       버리면 "그런 자료가 없었다"와 구분되지 않는다.
    """
    out: dict = {"home": None, "away": None, "unknown": []}
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        side = assign_side(r.get("team"), home, away)
        if side is None or out.get(side) is not None:
            out["unknown"].append(r)
            continue
        out[side] = r
    return out


def resolve_attribution(box: dict) -> dict:
    """양쪽 카드의 **명단이 같으면 둘 다 미상**으로 둔다.

    🔴 실측 `scout:soccer:11334` — `team` 은 `SonderjyskE` / `Randers FC` 로
       다른데 `out` 목록이 글자까지 같았다. 덴마크 부상표 한쪽을 LLM 이 양쪽에
       적은 것이고, 어느 쪽이 진짜인지 **자료로는 알 수 없다.**
    🔴 사용자 결정 2026-09-20: *"추출이 어느 팀인지 못 정하면 양쪽에 복사하지
       말고 side=unknown 으로 두고 어느 쪽에도 세지 않는다."*
    ⚠️ 지우기만 하지 않는다 — `out_unknown` 에 남긴다. 나중에 사람이 보고
       판정할 수 있어야 하고, 지우면 그 사실조차 사라진다.
    """
    b = {k: dict(v) for k, v in (box or {}).items() if isinstance(v, dict)}
    h, a = b.get("home") or {}, b.get("away") or {}
    ho, ao = list(h.get("out") or []), list(a.get("out") or [])
    if ho and ao and ho == ao:
        for side, card in (("home", h), ("away", a)):
            card["out_unknown"] = list(card.get("out") or [])
            card["out"] = []
            card["attribution"] = "unknown"
            b[side] = card
        logger.info("[scout] 결장 명단이 양쪽에 동일 %d명 — 어느 쪽에도 세지 "
                    "않는다(귀속 미상)", len(ho))
    return b


def _domain_of(url: str) -> str:
    from app.engine.scout_config import _domain

    return _domain(url)


async def _write_extract(redis, sport: str, game_id, payload: dict) -> None:
    """추출 결과를 **기사와 다른 키**에 남긴다. 없으면 쓰지 않는다."""
    if redis is None or game_id is None or not payload:
        return
    try:
        await redis.set(_extract_key(sport, game_id),
                        json.dumps({"gathered_at": datetime.now(timezone.utc).isoformat(),
                                    "teams": payload}, ensure_ascii=False),
                        ex=CACHE_TTL)
    except Exception as exc:
        logger.warning("[scout] 추출 기록 실패 %s:%s — %s", sport, game_id, exc)


#: 🔴 [PA-18 · 통로 A] 구속은 **하루 지나면 무의미**하다 — TTL 로 사는
#   값이라 원장·스키마를 늘리지 않고 redis 에 둔다(사용자 결정 2026-09-16).
def _velo_key(sport: str, game_id) -> str:
    return f"scout:velo:{sport}:{game_id}"


def redis_of(jg: dict):
    """SAT-8 이 쓸 redis 핸들. `gather` 가 jg 에 실어 둔 것을 쓴다."""
    return (jg or {}).get("_redis")


async def _write_velo(redis, jg: dict, velo: dict) -> None:
    """팀별 구속 변화(mph)를 남긴다. 없으면 쓰지 않는다."""
    gid = jg.get("game_id") or jg.get("id")
    if redis is None or gid is None or not velo:
        return
    try:
        await redis.set(_velo_key((jg.get("sport") or "").lower(), gid),
                        json.dumps(velo, ensure_ascii=False), ex=CACHE_TTL)
        logger.info("[scout] 구속 기록 game=%s %s", gid, velo)
    except Exception as exc:
        logger.warning("[scout] 구속 기록 실패 %s: %s", gid, exc)


async def read_velo(redis, sport: str, game_id) -> dict:
    """저장된 팀별 구속 변화. 없으면 빈 dict — 0 으로 읽지 않는다."""
    if redis is None or game_id is None:
        return {}
    try:
        raw = await redis.get(_velo_key((sport or "").lower(), game_id))
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


async def read_extract(redis, sport: str, game_id) -> dict:
    """저장된 추출 JSON. 없으면 빈 dict — 0 으로 읽지 않는다."""
    if redis is None or game_id is None:
        return {}
    try:
        raw = await redis.get(_extract_key(sport, game_id))
    except Exception as exc:
        logger.debug("[scout] 추출 읽기 실패 %s:%s — %s", sport, game_id, exc)
        return {}
    if not raw:
        return {}
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


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
#: 🔴 [PA-13] 게이트 라벨을 함께 싣는다 — 지시문 §3 "입력: 게이트 결과".
#   읽는 것은 **선별 신호**다. 확률·승자는 읽지 않는다(레저는 측정 전용).
#   ⚠️ LEFT JOIN 이다 — 아직 판정 전인 경기는 라벨이 NULL 이고, 그때는
#      종전대로 빅매치만 본다.
# 🔴 [SWAP-2 2026-09-22 사용자 지시] **구경로 원장을 안 읽는다.**
#    종전에는 `LEFT JOIN pick_ledger` 로 `gate_label`·`hypothesis` 를 받았다.
#    그것이 CLAUDE.md 가 "순서가 끊겨 있다"고 적은 자리다 — 흐름이 세운 가설이
#    수집에 닿지 못하고, 수집은 **다른 사전값으로 계산된 다른 게이트**를 봤다.
#    지금은 `flow.adapt.latest_for` 가 흐름의 `n03_gate`·`n04_hyp` 를 읽어 온다.
_DUE_SQL = """
    SELECT g.id, g.sport, g.league, g.home, g.away, g.starts_at,
           NULL::text AS gate_label, NULL::numeric AS gate_gap_pp,
           NULL::jsonb AS hypothesis
      FROM games g
     WHERE g.status = 'scheduled'
       AND g.sport = ANY($1::text[])
       AND g.starts_at BETWEEN now() AND now() + make_interval(hours => $2)
     ORDER BY g.starts_at
"""


def select_search_targets(rows: list) -> list:
    """[PA-15 · 지시문 §3] 검색 대상 고르기. **상한 슬레이트 30% · 최소 2 · 최대 8.**

    🔴 예산 규칙은 `gate.select` 가 원본이다 — 30%·2·8 을 여기 적지 않는다.
       그 함수는 §3 을 글자 그대로 구현해 놓고 **호출이 0건**이었다.
    🔴 PA-13 이 "게이트 대상이면 추출"을 열었는데 **몇 건까지인지는 안 걸었다.**
       게이트 대상이 많은 날이면 무료 한도(groq 분당 8,000 토큰)가 그대로 터진다.
    ⚠️ 라벨이 없는 경기(판정 전)는 여기서 뽑히지 않는다 — 그 경기는 종전대로
       빅매치 판정으로 간다(PA-13). 예산은 **게이트 대상에만** 건다.
    """
    from app.engine import gate as _G

    cand = [{"id": r["id"],
             "label": (r.get("gate_label") if hasattr(r, "get") else None),
             "gap_pp": (r.get("gate_gap_pp") if hasattr(r, "get") else None)}
            for r in (rows or [])]
    picked = _G.select(cand)
    ids = {c["id"] for c in picked}
    logger.info("[satellite] §3 대상 선별 — 슬레이트 %d · 게이트 대상 %d · 선별 %d %s",
                len(cand),
                sum(1 for c in cand if c["label"] in (_G.OVER, _G.DOUBT)),
                len(picked), sorted(ids))
    return [r for r in (rows or []) if r["id"] in ids]


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

    # 🔴 [GAT-1 2026-09-18] **라벨이 없으면 그 자리에서 계산한다.**
    #    원장 행은 판정이 끝나야 생기고 라벨은 그 행에 붙는다 — 그래서 첫 판정
    #    전에는 라벨이 없었고, 라벨이 없으면 아래 `gather` 가 추출을 생략했다
    #    ("게이트 미판정 · 빅매치 아님 · LLM 추출 생략"). 가설을 세워 놓고도
    #    수집이 그것을 본 적이 없다는 뜻이다.
    #    실측 2026-09-17: `§3 대상 선별 — 슬레이트 19 · 게이트 대상 0 · 선별 0`.
    #    ⚠️ **계산은 `pick_ledger.gate_of` 한 곳이다**(사본 금지). 원장에 적히는
    #       라벨도 같은 함수에서 나온다 — 여기서 규칙을 다시 쓰지 않는다.
    #    ⚠️ **읽기 전용이다.** 원장에 쓰지 않는다. 채운 값은 이 사이클의
    #       메모리에만 산다.
    #    ⚠️ LLM 콜은 늘지 않는다 — 같은 추출 1회를 **더 일찍** 할 뿐이고,
    #       §3 예산 상한(최대 8)도 그대로다.
    computed = 0
    if pool is not None:
        # 🔴 [SWAP-2] **흐름의 게이트·가설을 읽는다.** 구경로 `gate_of` 를
        #    부르지 않는다 — 두 게이트가 사전값이 달라 결론도 달랐다
        #    (실측 g1766: 구경로 "동의"(tier+form) vs 흐름 "시장과대"(team_elo)).
        #    ⚠️ 못 읽은 경기는 라벨 없음 → 종전대로 빅매치 판정으로 간다.
        #       구경로로 **되돌아가지 않는다**(사용자 지시).
        from app.flow.adapt import latest_for

        try:
            flow_rows = await latest_for(pool, [r["id"] for r in rows])
        except Exception as exc:
            logger.warning("[satellite] 흐름 산출 조회 실패 — 라벨 없이 간다: %s",
                           exc)
            flow_rows = {}
        _fixed = []
        for r in rows:
            row = dict(r)
            got = flow_rows.get(row["id"])
            if got and got.get("gate_label"):
                row["gate_label"] = got["gate_label"]
                row["gate_gap_pp"] = got["gate_gap_pp"]
                row["hypothesis"] = got["hypothesis"]
                computed += 1
            _fixed.append(row)
        rows = _fixed
        # 🔴 조용한 0 금지 — "원장에서 왔다"와 "우리가 계산했다"를 구분하지
        #    못하면 다음 사람이 §3 로그를 잘못 읽는다.
        logger.info("[satellite] 흐름 게이트 적용 %d건 / 슬레이트 %d "
                    "(라벨 없는 %d건은 빅매치 판정으로)",
                    computed, len(rows), len(rows) - computed)

    # 🔴 [PA-15 · §3] 예산을 **여기서** 건다. 선별된 경기만 게이트 대상으로
    #    표시하고, 나머지는 라벨을 지워 빅매치 판정으로 보낸다.
    #    ⚠️ 수집(기사 긁기) 자체는 막지 않는다 — §3 의 상한은 **검색·추출**
    #       예산이고, 층1 수집은 전 경기가 그대로 받는다.
    selected = {r["id"] for r in select_search_targets(rows)}

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
              "starts_at": r["starts_at"],
              # 🔴 [PA-13] 지시문 §3 의 선별 입력. 없으면 None 이고
              #    그때는 종전대로 빅매치만 본다.
              # ⚠️ `.get` 으로 읽는다 — 스키마가 아직 안 붙은 컨테이너나
              #    옛 가짜 행에서 KeyError 로 수집 사이클이 통째로 죽지 않게.
              # 🔴 [PA-15] 예산 밖이면 라벨을 싣지 않는다 — 그 경기는
              #    빅매치일 때만 추출된다(§3 상한).
              "gate_label": ((r.get("gate_label")
                              if hasattr(r, "get") else None)
                             if r["id"] in selected else None),
              # 🔴 [HYP-1] 가설을 수집에 내려보낸다. `.get` 으로 읽는 이유는
              #    gate_label 과 같다 — 옛 행·스키마 미적용에서 KeyError 로
              #    수집 사이클이 통째로 죽지 않게.
              "hypothesis": (r.get("hypothesis")
                             if hasattr(r, "get") else None)}
        try:
            n = await gather(jg, redis, client=client, now=now, pool=pool)
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
