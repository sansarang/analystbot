"""[A-3단계] 경기 전 기사에서 **원문 문장을 발췌**한다. LLM 0회.

⚠️ **요약하지 않는다.** 딥서치는 "찾아서 요약"을 했지만 우리 설계에서는 요약이
   필요 없다. 사실 칸에는 원문 문장이 그대로 들어가고, 해석(▲▼)은 2단이 한다.
   발췌 단계에서 부호를 매기면 3단이 판단을 사실로 읽는다.

**직접 인용문만 뽑는다.** 이것이 이 모듈의 핵심 안전장치다:
  · 기자의 전망·평가("반등이 기대된다", "유리해 보인다")는 사실이 아니라 의견이고,
    우리 2단이 할 일을 미리 해버린다.
  · 인용문은 정의상 **"누가 무슨 말을 했다"**는 사실이다. 인용만 뽑으면
    의견/사실 분류라는 어려운 문제를 통째로 우회한다.
  · "5선발을 당겨쓴다"가 로테이션 붕괴인지 승부수인지는 **판정하지 않는다.**
    감독이 무슨 말을 했는지만 기록한다.

뉴스는 정형 데이터가 아니라 기존 물리 검사(게이트 ①)가 통하지 않는다.
뉴스 전용 게이트 셋을 건다:
  ① **시각** — 기사 게시 시각이 경기 시작 **이전**이어야 한다.
     경기 후 기사는 결과를 담고 있어 **누출**이다. 이것이 가장 위험한 구멍이다.
  ② **팀** — 문장에 그 경기 팀명(또는 선발 이름)이 있어야 한다.
     실사고 유형: 화이트삭스-텍사스 경기에 보스턴 라인업이 들어갔다.
  ③ **중복** — 같은 문장이 여러 경기에 붙지 않게 한다.
"""

import hashlib
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

INDEX = "https://sports.chosun.com/baseball/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
CACHE_TTL = 3 * 3600
MAX_ARTICLES = 25          # 하루 야구 기사 상한 — 전부 받으면 느리고 대부분 무관하다
MAX_QUOTES_PER_GAME = 4

# 기사 URL에 날짜가 박혀 있다 — 다른 날 기사를 거르는 1차 관문
_ART = re.compile(r'href="(https://www\.sportschosun\.com/baseball/(\d{4}-\d{2}-\d{2})/\d+)"')
_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_TITLE = re.compile(r'<meta[^>]+og:title[^>]+content="([^"]*)"')
_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S)

# 직접 인용 + 발화 동사. 이 둘이 함께 있어야 "누가 말했다"는 사실이 된다.
_QUOTE = re.compile(r'[“"]([^”"]{10,200})[”"]')
_SAID = ("말했다", "밝혔다", "전했다", "설명했다", "강조했다", "덧붙였다",
         "말한다", "얘기했다", "이야기했다", "언급했다")

# 팀 한국어 표기 → Odds 팀명
TEAM_KR = {"LG": "LG Twins", "두산": "Doosan Bears", "KT": "KT Wiz",
           "SSG": "SSG Landers", "NC": "NC Dinos", "키움": "Kiwoom Heroes",
           "한화": "Hanwha Eagles", "삼성": "Samsung Lions",
           "롯데": "Lotte Giants", "KIA": "Kia Tigers", "기아": "Kia Tigers"}


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", _SCRIPT.sub("", html))).strip()


def _sentences(text: str) -> list[str]:
    """마침표 기준 문장 분리. 인용부호 안의 마침표는 자르지 않는다."""
    out, buf, depth = [], [], 0
    for ch in text:
        if ch in '“"':
            depth = 1 - depth
        buf.append(ch)
        if ch in ".!?" and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    if buf:
        out.append("".join(buf).strip())
    return out


def extract_quotes(html: str, names: set[str]) -> list[str]:
    """[A-3] 직접 인용이 있고 **그 경기와 관련된** 문장만 원문 그대로.

    ⚠️ `names`가 비면 **빈 목록**이다. 관련성을 확인할 수 없는데 넣으면
       다른 경기 이야기가 이 경기 칸에 들어간다(게이트 ②).
    """
    if not names:
        return []
    out = []
    for s in _sentences(_plain(html)):
        if len(s) > 400 or not _QUOTE.search(s):
            continue
        if not any(v in s for v in _SAID):
            continue                       # 인용은 있는데 발화 동사가 없다 → 제목·광고
        if not any(n and n in s for n in names):
            continue                       # 게이트 ② — 이 경기와 무관
        out.append(re.sub(r"\s+", " ", s).strip())
    return out


def quote_key(sentence: str) -> str:
    """중복 판정 키 (게이트 ③). 공백·문장부호 차이를 무시한다."""
    norm = re.sub(r"[\s\"“”'’.,!?]+", "", sentence)
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


class ChosunClient:
    timeout = 20.0

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def _get(self, url: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout,
                                     follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
        r.raise_for_status()
        return r.text

    async def index(self, date: str) -> list[str]:
        """그 날짜 기사 URL 목록. **URL의 날짜로 1차로 거른다.**"""
        html = await self._get(INDEX)
        urls = [u for u, d in dict.fromkeys(_ART.findall(html)) if d == date]
        return urls[:MAX_ARTICLES]

    async def article(self, url: str) -> tuple[str, datetime | None, str]:
        """(HTML, 게시 시각, 제목)."""
        html = await self._get(url)
        m = _PUBLISHED.search(html)
        at = None
        if m:
            try:
                at = datetime.fromisoformat(m.group(1))
            except ValueError:
                at = None
        t = _TITLE.search(html)
        return html, at, (t.group(1) if t else "")


async def fetch_for_games(games: list[dict], date: str,
                          client: ChosunClient | None = None) -> dict[str, list[dict]]:
    """{"원정@홈": [{"text","url","at"}]}. 게이트 ①②③를 전부 통과한 것만.

    ⚠️ 게이트 ① — 기사 게시 시각이 **경기 시작 이전**이어야 한다.
       경기 후 기사는 결과를 담고 있어 누출이다. 이 프로젝트에서 누출은
       한 번 새면 그 뒤 모든 측정을 못 믿게 만든다.
    """
    client = client or ChosunClient()
    try:
        urls = await client.index(date)
    except Exception as exc:
        logger.warning("[kbo_news] 기사 목록 조회 실패: %s", exc)
        return {}

    articles = []
    for u in urls:
        try:
            html, at, title = await client.article(u)
        except Exception as exc:
            logger.debug("[kbo_news] 기사 조회 실패 %s: %s", u, exc)
            continue
        articles.append((u, at, title, html))

    seen: set[str] = set()          # 게이트 ③ — 경기 간 중복 발췌 방지
    out: dict[str, list[dict]] = {}
    for g in games:
        key = f"{g.get('away')}@{g.get('home')}"
        starts = g.get("starts_at")
        if isinstance(starts, str):
            try:
                starts = datetime.fromisoformat(starts)
            except ValueError:
                starts = None
        names = _game_names(g)
        picked: list[dict] = []
        for url, at, _title, html in articles:
            if starts is not None and at is not None and at >= starts:
                continue            # 게이트 ① — 경기 시작 후 기사는 누출이다
            for s in extract_quotes(html, names):
                k = quote_key(s)
                if k in seen:
                    continue
                seen.add(k)
                picked.append({"text": s, "url": url,
                               "at": at.isoformat() if at else None})
                if len(picked) >= MAX_QUOTES_PER_GAME:
                    break
            if len(picked) >= MAX_QUOTES_PER_GAME:
                break
        if picked:
            out[key] = picked
    logger.info("[kbo_news] %s — %d경기에 인용 발췌 (기사 %d건 조회)",
                date, len(out), len(articles))
    return out


def _game_names(g: dict) -> set[str]:
    """게이트 ②용 — 이 경기를 특정하는 이름들 (팀 한국어 표기 + 선발)."""
    odds_to_kr = {}
    for kr, odds in TEAM_KR.items():
        odds_to_kr.setdefault(odds, set()).add(kr)
    names: set[str] = set()
    for side in ("home", "away"):
        names |= odds_to_kr.get(g.get(side) or "", set())
        p = (g.get("research") or {}).get(f"{side}_pitcher") or {}
        if p.get("name"):
            names.add(p["name"])
    return {n for n in names if n}


def merge_into_research(research: dict, jg: dict, table: dict) -> list[str]:
    """발췌 문장을 research에 얹는다.

    ⚠️ **가공하지 않는다.** 문장·URL·시각을 그대로 넣는다. 요약하거나 부호를
       매기면 2단 해석봇의 일을 미리 해버리는 것이고, 그 순간 3단은 우리의
       판단을 사실로 읽는다.
    """
    from app.research.crosscheck_sources import mark_collected

    rows = (table or {}).get(f"{jg.get('away')}@{jg.get('home')}")
    mark_collected(research, "rotation_plan")   # 조사했다 — 인용이 없어도
    if not rows:
        return []
    research["news_quotes"] = rows
    # 감독 발언이 로테이션·불펜 운용을 다루면 그 자리에도 원문을 남긴다.
    # ⚠️ `마무리`·`셋업`·`클로저`를 빠뜨리면 **불펜 순서 변경 발언이 통째로
    #    누락된다.** 실측(2026-08-26): 롯데 감독의 "오늘부터 이이무라가 마무리다"가
    #    이 목록에 안 걸려 rotation_plan이 비었다 — 카드 ①칸의 핵심 사실이다.
    _PLAN_WORDS = ("선발", "로테이션", "불펜", "등판", "마무리", "셋업",
                   "클로저", "휴식", "엔트리")
    plan = [r["text"] for r in rows
            if any(w in r["text"] for w in _PLAN_WORDS)]
    filled = ["news_quotes"]
    if plan and not research.get("rotation_plan"):
        research["rotation_plan"] = " / ".join(plan[:2])
        filled.append("rotation_plan")
    return filled
