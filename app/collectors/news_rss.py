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
        out.append({"title": title, "url": link, "source": source,
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


async def fetch_team(sport: str, team: str, *, limit: int = 20) -> list[dict]:
    """팀 1개의 최근 기사. 실패하면 빈 목록 — 딥서치가 폴백을 결정한다."""
    import httpx

    loc = LOCALE.get(sport)
    if not loc or not team:
        return []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": UA}) as c:
            r = await c.get(BASE, params={"q": QUERY_ALIAS.get(team, team), **loc})
            r.raise_for_status()
            items = parse_feed(r.text)
    except Exception as exc:
        logger.warning("[news_rss] %s %s 조회 실패: %s", sport, team, exc)
        return []
    logger.info("[news_rss] %s %s — 72시간 내 기사 %d건 (쿼리=%r)",
                sport, team, len(items), QUERY_ALIAS.get(team, team))
    return items[:limit]


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
