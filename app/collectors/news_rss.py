"""[무과금 전환 2a] 무료 뉴스 선수집 — Google News RSS.

🔴 왜 바꾸나: 딥서치가 Anthropic `web_search` 도구를 쓴다. 검색 1회당 과금이고
   경기당 최대 5회다. **"검색"을 우리가 무료로 대신하고 LLM 은 읽기만 하면**
   그 수수료가 0원이 된다. 판정 프롬프트와 조정 상한(±4%p)은 그대로다.

무인증·무제한. 실측 2026-09-02:
  Cincinnati Reds  106건 · LG 트윈스 98건 · 阪神タイガース 100건 (전부 200)

⚠️ **RSS 는 제목·시각·링크만 준다.** 본문은 `web_fetch`(무료)가 따로 가져온다.
   제목만으로 판정을 흔들지 않는다 — 딥서치 프롬프트가 원문을 요구한다.
⚠️ 리그마다 언어가 다르다. 한국어 기사에 영어 쿼리를 던지면 0건이 된다.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

BASE = "https://news.google.com/rss/search"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

#: 종목 → RSS 로케일. 원문이 그 언어로 쓰여 있다.
LOCALE = {
    "mlb": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "kbo": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    "npb": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
}

#: 검색 쿼리 별칭 — 우리 팀명(영문) → 그 리그 언어의 실제 표기.
#  🔴 실측 2026-09-02 16:22: 영문명으로 던지면 기사는 오는데(49건) **72시간
#     필터가 전부 걸러낸다** — 영문 기사는 오래된 것뿐이다. 모국어로 던지면
#     같은 팀이 100건, 그것도 최신이다.
#       Hanwha Eagles 0건 → 한화 이글스 100건
#       Lotte Giants  0건 → 롯데 자이언츠 102건
#     리그 로케일만 맞추고 쿼리는 영문으로 둔 것이 구멍이었다.
#  ⚠️ 없는 팀은 팀명 그대로 던진다 — 별칭이 없다고 수집을 멈추지 않는다.
QUERY_ALIAS = {
    # KBO
    "LG Twins": "LG 트윈스", "Doosan Bears": "두산 베어스",
    "KT Wiz": "KT 위즈", "Hanwha Eagles": "한화 이글스",
    "NC Dinos": "NC 다이노스", "Kia Tigers": "KIA 타이거즈",
    "Kiwoom Heroes": "키움 히어로즈", "SSG Landers": "SSG 랜더스",
    "Samsung Lions": "삼성 라이온즈", "Lotte Giants": "롯데 자이언츠",
    # NPB
    "Yomiuri Giants": "読売ジャイアンツ", "Hanshin Tigers": "阪神タイガース",
    "Yokohama DeNA BayStars": "横浜DeNAベイスターズ",
    "Hiroshima Toyo Carp": "広島東洋カープ",
    "Tokyo Yakult Swallows": "東京ヤクルトスワローズ",
    "Chunichi Dragons": "中日ドラゴンズ",
    "Fukuoka SoftBank Hawks": "福岡ソフトバンクホークス",
    "Hokkaido Nippon-Ham Fighters": "日本ハムファイターズ",
    "Chiba Lotte Marines": "千葉ロッテマリーンズ",
    "Tohoku Rakuten Golden Eagles": "東北楽天ゴールデンイーグルス",
    "Saitama Seibu Lions": "埼玉西武ライオンズ",
    "Orix Buffaloes": "オリックス・バファローズ",
}

KEY = "news_rss:{sport}:{team}"
TTL = 3 * 3600            # 크롤러 평시 주기와 맞춘다
#: 이보다 오래된 기사는 버린다. 딥서치는 "지금 무엇이 달라졌나"를 묻는다.
MAX_AGE_HOURS = 72
TIMEOUT = 20.0


def _text(raw: str) -> str:
    """CDATA·엔티티·태그를 벗긴다."""
    raw = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw or "", flags=re.S)
    raw = re.sub(r"<[^>]+>", "", raw)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        raw = raw.replace(a, b)
    return re.sub(r"\s+", " ", raw).strip()


def parse_feed(xml: str, *, now=None, max_age_hours: int = MAX_AGE_HOURS) -> list[dict]:
    """RSS → [{title, url, source, published, age_h}]. 오래된 것은 버린다."""
    now = now or datetime.now(UTC)
    out = []
    for block in re.findall(r"<item>(.*?)</item>", xml or "", re.S):
        def grab(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _text(m.group(1)) if m else ""

        title, link, pub = grab("title"), grab("link"), grab("pubDate")
        if not title or not link:
            continue
        age = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                age = (now - dt).total_seconds() / 3600
            except (TypeError, ValueError):
                age = None
        if age is not None and age > max_age_hours:
            continue
        # 구글 RSS 제목은 "제목 - 매체" 형식이다. 매체를 따로 떼 신뢰도 판단에 쓴다.
        source = grab("source") or (title.rsplit(" - ", 1)[-1]
                                    if " - " in title else "")
        # 🔴 [2026-09-06] `<source url="…">` 의 **속성**이 실제 언론사 도메인이다.
        #    `link` 는 news.google.com 리다이렉트라 그것으로 신뢰도를 보면
        #    **모든 기사가 `[미확인]`** 이 된다(실측: 상황 태그 전건 미확인).
        m_su = re.search(r"<source[^>]*\burl=[\"']([^\"']+)[\"']", block, re.S)
        source_url = _text(m_su.group(1)) if m_su else ""
        out.append({"title": title, "url": link, "source": source,
                    "source_url": source_url,
                    "published": pub, "age_h": round(age, 1) if age else None})
    return out


#: 제목 끝의 " - 매체명" 꼬리. Google News RSS 가 모든 제목에 붙인다.
_OUTLET_TAIL = re.compile(r"\s*[-–—]\s*[^-–—]{1,30}$")
#: 정규화에서 지울 것 — 공백·따옴표·괄호·구두점. 의미는 안 건드린다.
_NOISE_CHARS = re.compile(r"[\s'\"“”‘’\[\]()（）【】…·・,\.!?~]+")


def title_key(title: str) -> str:
    """중복 판정용 제목 지문.

    🔴 [2026-09-06] 같은 기사가 여러 매체 URL 로 들어온다. 실측 2026-09-05
       KIA 뉴스태그 2개가 **같은 기사**였다:
         "'4G ERA 15.00' KIA 이대로 괜찮나… - v.daum.net"
         "'4G ERA 15.00' KIA 이대로 괜찮나… - xportsnews.com"
       판정은 그것을 두 개의 신호로 읽는다 — 없는 반복을 근거로 삼는 것이다.

    ⚠️ **제목만 정규화한다.** 본문·URL 로 비교하지 않는다 — 같은 기사를
       매체가 조금씩 고쳐 싣기 때문에 본문 비교는 오히려 갈린다.
    ⚠️ 지우는 것은 매체 꼬리와 구두점·공백뿐이다. 단어를 건드리면 다른
       기사가 같은 것으로 뭉친다.
    """
    t = html.unescape(str(title or ""))
    t = _OUTLET_TAIL.sub("", t)
    return _NOISE_CHARS.sub("", t).lower()


def dedupe_by_title(items: list[dict]) -> list[dict]:
    """제목 지문 기준 중복 제거. **먼저 온 것을 남긴다**(최신순 정렬 유지)."""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items or []:
        k = title_key(it.get("title"))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


#: 상황 축 쿼리에 쓸 유형 수 상한. 전 축을 한 쿼리에 넣으면 URL 이 길어지고
#  Google News 가 조용히 잘라낸다 — 대표 키워드만 OR 로 묶는다.
_SIT_QUERY_TERMS = 8


def qualified(sport: str, team: str) -> str:
    """팀명 + 리그 한정어. 한정어가 없으면 팀명 그대로.

    🔴 [2026-09-06] 팀명만으로 검색하면 다른 종목·학교가 딸려온다.
       실측: MLB `Athletics` 기사 102건 중 **60건(59%)** 이 스페인 축구
       (Athletic Bilbao)·대학 스포츠(Penn/Elon Athletics)였다. 그것들이
       `roster_move` 상황 태그로 잡혀 판정 재료에 들어갔다.
       `MLB` 를 붙이니 47건 중 6건(13%)으로 떨어졌다.

    ⚠️ 한정어는 재현율을 깎는다(비모호 팀은 85→43건). 그래도 붙이는 이유는
       **우리가 실제로 쓰는 양이 팀당 12~20건**이라 43건이면 넘치기 때문이다.
       KBO·NPB 는 오히려 늘었다(85→100 · 71→76).
    """
    from app.registry import league_query_term

    name = QUERY_ALIAS.get(team, team)
    term = league_query_term(sport)
    return f"{name} {term}".strip() if term else name


def situation_query(sport: str, team: str) -> str:
    """`팀명 (키워드 OR 키워드 …)`. 종목 분기는 registry 가 갖는다.

    ⚠️ 사이트를 지정하지 않는다. Google News RSS 는 그 자체가 **전 웹 집계**라
       특정 사이트를 박으면 오히려 좁아진다.
    """
    from app.registry import situation_axes

    axes = situation_axes(sport)
    if not axes:
        return ""
    terms: list[str] = []
    for words in axes.values():          # 유형마다 대표 1개씩
        if words:
            terms.append(words[0])
    if not terms:
        return ""
    picked = terms[:_SIT_QUERY_TERMS]
    return f'{qualified(sport, team)} ({" OR ".join(picked)})'


async def fetch_team_situation(sport: str, team: str, *,
                               limit: int = 20) -> list[dict]:
    """상황 축 전용 쿼리 1회. **실패해도 기존 수집에 영향이 없다.**

    ⚠️ 조용히 실패하지 않는다 — 실패도 로그 한 줄을 남긴다.
    """
    import httpx

    loc = LOCALE.get(sport)
    q = situation_query(sport, team)
    if not loc or not q:
        logger.info("[news_rss] %s %s 상황 쿼리 생략 (로케일=%s 쿼리=%s)",
                    sport, team, bool(loc), bool(q))
        return []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": UA}) as c:
            r = await c.get(BASE, params={"q": q, **loc})
            r.raise_for_status()
            items = parse_feed(r.text)
    except Exception as exc:
        logger.warning("[news_rss] %s %s 상황 쿼리 실패 — 기존 수집은 계속: %s",
                       sport, team, exc)
        return []
    logger.info("[news_rss] %s %s 상황 쿼리 %d건 (q=%r)",
                sport, team, len(items), q[:80])
    return items[:limit]


async def fetch_team(sport: str, team: str, *, limit: int = 20) -> list[dict]:
    """팀 1개의 최근 기사. 실패하면 빈 목록 — 딥서치가 폴백을 결정한다.

    🔴 [상황 변수 2026-09-06] 일반 쿼리와 **상황 축 쿼리를 함께** 던진다.
       한 곳에서 합치므로 호출부(`for_game`·`by_side`)는 손댈 것이 없다.
       ⚠️ 상황 쿼리가 실패해도 일반 결과는 그대로 돌려준다 — 새 수집이
          기존 수집을 깨뜨리면 안 된다. 실패는 로그 한 줄로 남는다.
       ⚠️ RSS 는 무료다. 늘어난 것은 **쿼리 수**뿐이고 그것을 로그에 적는다.
    """
    import asyncio

    import httpx

    loc = LOCALE.get(sport)
    if not loc or not team:
        return []
    q_main = qualified(sport, team)

    async def _one(q: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": UA}) as c:
            r = await c.get(BASE, params={"q": q, **loc})
            r.raise_for_status()
            return parse_feed(r.text)

    try:
        items = await _one(q_main)
    except Exception as exc:
        logger.warning("[news_rss] %s %s 조회 실패: %s", sport, team, exc)
        items = []
    n_main = len(items)

    sit: list[dict] = []
    q_sit = situation_query(sport, team)
    if q_sit:
        try:
            sit = await _one(q_sit)
        except Exception as exc:
            logger.warning("[news_rss] %s %s 상황 쿼리 실패 — 일반 결과는 유지: %s",
                           sport, team, exc)
    merged = dedupe_by_title(items + sit)
    logger.info("[news_rss] %s %s — 72시간 내 기사 %d건 "
                "(일반 %d + 상황 %d, 중복 제거 후 %d · 쿼리 2회)",
                sport, team, len(merged), n_main, len(sit), len(merged))
    return merged[:limit]


async def for_game(jg: dict, redis=None, *, limit: int = 12) -> list[dict]:
    """양 팀 기사를 합쳐 최신순. 캐시 우선.

    ⚠️ 팀마다 따로 캐시한다 — 같은 팀이 여러 경기에 나오지 않지만, 슬레이트
       안에서 재판정이 여러 번 돌면 같은 쿼리를 반복하게 된다.
    """
    import json as _json

    sport = (jg.get("sport") or "").lower()
    if sport not in LOCALE:
        return []
    merged: list[dict] = []
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        key = KEY.format(sport=sport, team=team)
        items = None
        if redis is not None:
            try:
                raw = await redis.get(key)
                if raw:
                    items = _json.loads(raw)
            except Exception as exc:
                logger.debug("[news_rss] 캐시 읽기 실패 %s: %s", team, exc)
        if items is None:
            items = await fetch_team(sport, team)
            if items and redis is not None:
                try:
                    await redis.set(key, _json.dumps(items, ensure_ascii=False),
                                    ex=TTL)
                except Exception as exc:
                    logger.debug("[news_rss] 캐시 기록 실패 %s: %s", team, exc)
        for it in items or []:
            merged.append({**it, "team": team})
    merged.sort(key=lambda x: (x.get("age_h") is None, x.get("age_h") or 0))
    return merged[:limit]


async def by_side(jg: dict, redis=None, *, limit: int = 12) -> dict[str, list[dict]]:
    """`{"home": [기사…], "away": [기사…]}`. **팀 매칭은 쿼리 팀명으로 한다.**

    🔴 [1단계 2026-09-05] 팀 폼이 읽는 `research[f"{side}_news"]` 를 **아무도
       채우지 않고 있었다**(전수 grep 0건). 그래서 RSS 로 팀당 99~100건을
       받아 놓고도 판정에는 한 건도 도달하지 않았다 — 그 기사들은
       `deepsearch._free_articles` 전용이고, KBO·NPB 는 딥서치가 꺼져 있어
       통째로 버려졌다.

    ⚠️ **새로 긁지 않는다.** `for_game` 과 같은 캐시(`KEY`)를 타므로 같은
       슬레이트에서 두 번 요청하지 않는다.
    ⚠️ 72시간 창은 `parse_feed` 가 강제한다 — 여기서 다시 자르지 않는다.
       두 곳에서 자르면 어느 쪽이 실제 창인지 알 수 없게 된다.
    ⚠️ 팀 매칭은 `for_game` 이 붙여 준 `team`(= 우리 팀명)으로 한다.
       기사 본문에서 팀을 다시 추정하지 않는다 — 추정은 다음 사고다.
    """
    items = await for_game(jg, redis, limit=limit * 2)
    out: dict[str, list[dict]] = {}
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        rows = [{k: v for k, v in it.items() if k != "team"}
                for it in items if it.get("team") == team]
        # 🔴 [2026-09-06] **태그를 만들기 전에** 중복을 없앤다. 팀 폼이
        #    같은 기사를 두 번 보면 태그도 두 번 나오고, 판정은 그것을
        #    두 신호로 읽는다(실측 2026-09-05 KIA 태그 2개 = 같은 기사).
        before = len(rows)
        rows = dedupe_by_title(rows)
        if before != len(rows):
            logger.info("[news_rss] %s 중복 제거 %d → %d건", team, before, len(rows))
        if rows:
            out[side] = rows[:limit]
    return out


async def invalidate_form_cache(redis, jg: dict, sides: list[str]) -> int:
    """새 기사가 들어온 팀의 **팀 폼 캐시를 지운다.** 반환 지운 수.

    🔴 [2026-09-06] 팀 폼은 `form:{sport}:{team}:{date}` 로 캐시된다. 그래서
       재실행에서 x_search·그라운딩이 새 기사를 넣어도 **폼은 옛 캐시를 그대로
       쓰고 새 헤드라인을 읽지 않았다** — 자료2 뉴스태그 경로가 통째로 끊겨
       있었다(실측 2026-09-06: x_search 가 가져온 `Athletics roster moves
       announced`·`Lazaro Montes 부상`이 판정 프롬프트에 없었다).

    ⚠️ **새 기사가 실제로 들어온 팀만** 지운다. 매번 지우면 슬레이트마다 폼을
       다시 계산하게 되고, 그건 캐시를 없앤 것과 같다.
    """
    from app.engine.team_form import form_key

    if redis is None or not sides:
        return 0
    sport = (jg.get("sport") or "").lower()
    date = jg.get("_form_date") or jg.get("date") or ""
    n = 0
    for side in sides:
        team = jg.get(side) or ""
        if not team or not date:
            continue
        try:
            n += int(await redis.delete(form_key(sport, team, date)) or 0)
        except Exception as exc:
            logger.debug("[news_rss] 폼 캐시 무효화 실패 %s: %s", team, exc)
    if n:
        logger.info("[news_rss] %s game=%s 새 기사로 팀 폼 캐시 %d건 무효화 "
                    "— 폼이 새 헤드라인을 다시 읽는다",
                    sport, jg.get("game_id"), n)
    return n


def merge_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """`{side}_news` 를 채운다. 반환은 채운 키 목록.

    ⚠️ **가공하지 않는다.** 제목·URL·시각을 그대로 넣는다 — 팀 폼이
       그것을 읽고 태그를 만든다(자료2). 여기서 요약하면 그 요약이
       판정 재료가 된다.
    """
    filled: list[str] = []
    for side in ("home", "away"):
        rows = (table or {}).get(side)
        if not rows:
            continue
        research[f"{side}_news"] = rows
        filled.append(f"{side}_news")
    return filled
