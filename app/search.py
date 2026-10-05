"""검색 수단 — §19-i (사용자 결정 2026-09-27).

🔴 **"유료 API 0건"의 정의**(§19-i-1): *"카드 미등록·과금 0·무료 플랜 상한
   안에서 도는 키는 유료가 아니다. 카드 등록이 필수인 서비스는 무료 플랜이
   있어도 제외."*

| 순위 | 무엇 | 배정 |
|---|---|---|
| 1 | **SearXNG 자체 호스팅** (맥 로컬·JSON) | 전부. 비용 0·키 없음·상한 없음 |
| 2 | **Google Programmable Search** (무료 100/일·카드 불필요) | **반증 추적**과 **라인업 세포**에만 |
| 3 | 매체별 RSS·사이트맵 | 검색 수요를 줄이는 용도 — **대체가 아니다** |

🔴 제외(§19-i-5): DuckDuckGo HTML 긁기 · 카드 등록을 요구하는 서비스 · SerpAPI류.
🔴 검색 결과는 **항상 §12-c 검증기를 거친다**(§19-i-2) — 그것은 `cells` 가 한다.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app import cassette
from app.cells import Q_COUNTER, Q_LINEUP
from app.net import UA, SearchUnavailable

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

#: SearXNG. 🔴 루프백이 기본이다 — 외부 주소를 기본값으로 두지 않는다(§17-g-8).
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888")

#: 업스트림 엔진 정지를 **몇 초 동안 기억하나.**
#
#  🔴 실측 2026-09-30: `brave: Suspended: too many requests` 가 몇 분 뒤 풀렸고
#     같은 일본어 질의가 0건 → **26건**으로 바뀌었다. 영구히 죽은 것으로 두면
#     일본어 검색(=NPB 라인업)이 그날 통째로 막힌다.
#  ⚠️ robots 거부(`net.dead_hosts`)와 **다른 규칙**이다 — 그쪽은 정책이라 하루,
#     이쪽은 혼잡이라 분 단위다.
ENGINE_DEAD_TTL_SEC = 300.0

#: Google Programmable Search. 🔴 **무료 100쿼리/일**을 코드에 박는다(§19-i-3).
GOOGLE_DAILY_CAP = 100
#: 🔴 **구글 할당량은 태평양 시간 자정에 돌아온다** — KST 로 세면 하루가
#   어긋나고, 그 어긋남이 상한 초과(=요금)로 나타난다(사용자 지시 2026-09-28:
#   "상한 도달 시 다음 날 00:00 PT 까지 호출 0건인지 로그로 증명").
QUOTA_TZ = ZoneInfo("America/Los_Angeles")

#: 🔴 **비용 잠금**(사용자 지시 2026-09-28) — 결제 계정 미연결 또는 할당량
#   100/일 고정을 사용자가 **확인했다는 답을 받기 전엔** 운영 스케줄러에
#   CSE 를 연결하지 않는다. 기본은 꺼짐이고, 켜는 것은 사용자 몫이다.
CSE_OPERATIONAL_ENV = "CSE_OPERATIONAL"


def cse_operational() -> bool:
    return (os.getenv(CSE_OPERATIONAL_ENV) or "").strip().lower() in (
        "1", "true", "yes")
#: 🔴 그 둘에만 배정한다. 다른 질문이 이 예산을 먹으면 반증 추적이 굶는다.
GOOGLE_ALLOWED = (Q_COUNTER, Q_LINEUP)


@dataclass
class Hit:
    """검색 결과 한 줄. 🔴 스니펫만으로 판정하지 않는다 — soft 다(§12-b)."""

    title: str
    url: str
    snippet: str = ""
    publisher: str = ""
    engine: str = ""
    published_at: datetime | None = None


# ══════════════════════════════════════════════════════════════════
# 1순위 — SearXNG
# ══════════════════════════════════════════════════════════════════


class SearxSearch:
    """자체 호스팅 SearXNG. 🔴 **JSON 으로 받는다** — HTML 을 긁지 않는다."""

    name = "SearXNG"
    available = True

    def __init__(self, base_url: str | None = None, *, timeout: float = 20.0,
                 engine_ttl: float = ENGINE_DEAD_TTL_SEC):
        # ⚠️ 여기는 `or` 로 둔다 — 빈 주소는 "없음"이 아니라 **잘못된 설정**이고,
        #    기본값(루프백)으로 가는 것이 맞다.
        self.base = (base_url or SEARXNG_URL).rstrip("/")
        self.timeout = timeout
        #: 업스트림 엔진이 막히면 **그 엔진만** dead 로 둔다(§19-b-4 · §19-i-2).
        #  🔴 **시각과 함께 적는다** — 엔진 정지는 영구가 아니다(아래 참조).
        self._dead: dict[str, tuple[float, str]] = {}
        self.engine_ttl = engine_ttl
        self.alive: bool | None = None       # None = 아직 안 물어봤다

    @property
    def dead_engines(self) -> set[str]:
        """지금 죽어 있는 엔진. 🔴 **TTL 이 지난 것은 살아난 것으로 본다.**

        ⚠️ 실측 2026-09-30: 같은 일본어 질의가 한 번은 0건, 몇 분 뒤 **26건**을
           냈다. 사유는 `brave: Suspended: too many requests` 였고, 그 정지는
           **몇 분이면 풀린다.** 종전 이 값은 `set` 이라 한 번 죽으면 프로세스가
           사는 동안 영구히 죽은 것으로 남았고, 요약 보고가 *"dead ['brave',
           'duckduckgo', 'google cse']"* 라고 **거짓을** 말했다.

        🔴 §19-b-4 의 *"그날 dead"* 는 **robots 거부 도메인** 규칙이다 — 그것은
           정책이라 하루가 맞다. 요청 과다 정지는 정책이 아니라 혼잡이고, 같은
           시간을 주면 소스를 영영 안 쓰게 된다.
        """
        now = time.monotonic()
        return {name for name, (when, _) in self._dead.items()
                if now - when < self.engine_ttl}

    def engine_reasons(self) -> dict[str, str]:
        """🔴 **왜 죽었나를 이름과 함께** 낸다(조용한 0 금지)."""
        now = time.monotonic()
        return {name: why for name, (when, why) in self._dead.items()
                if now - when < self.engine_ttl}

    def mark_engine_dead(self, name: str, reason: str = "") -> None:
        """🔴 **시각을 함께 적는다** — 그래야 살아나는 것을 알 수 있다."""
        self._dead[str(name)] = (time.monotonic(), reason or "사유 미기재")

    async def query(self, text: str, *, lang: str = "ko",
                    engines: list[str] | None = None) -> list[Hit]:
        params = {"q": text, "format": "json", "language": _lang(lang)}
        if engines:
            live = [e for e in engines if e not in self.dead_engines]
            if not live:
                raise SearchUnavailable(
                    f"요청 엔진 전부 dead: {sorted(self.dead_engines)}")
            params["engines"] = ",".join(live)

        # 🔴 카세트(§9 단계 3) — `replay` 면 네트워크에 가지 않는다.
        q = cassette.query_string(params)
        if cassette.mode() == cassette.REPLAY:
            try:
                data = cassette.load("search", f"{self.base}/search", q)
            except cassette.CassetteMiss as exc:
                # ⚠️ `alive` 를 False 로 내리지 않는다 — SearXNG 가 죽은 것이
                #    아니라 **그 질의의 카세트가 없는 것**이다. 내리면 사슬이
                #    이후 모든 질의를 건너뛴다(카오스 테스트가 오염된다).
                raise SearchUnavailable(str(exc)) from exc
            self.alive = True
            return self._hits(data, text)

        try:
            async with httpx.AsyncClient(timeout=self.timeout,
                                         headers={"User-Agent": UA}) as cli:
                r = await cli.get(f"{self.base}/search", params=params)
        except Exception as exc:                    # noqa: BLE001
            self.alive = False
            raise SearchUnavailable(f"SearXNG 에 닿지 못했다: {exc}") from exc
        if r.status_code != 200:
            self.alive = False
            raise SearchUnavailable(f"SearXNG HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as exc:
            self.alive = False
            # 🔴 JSON 이 안 오면 설정에서 `formats: json` 이 빠진 것이다.
            raise SearchUnavailable(
                "SearXNG 가 JSON 을 안 준다 — settings.yml 의 formats 확인") from exc

        self.alive = True
        if cassette.mode() == cassette.RECORD:
            cassette.save("search", f"{self.base}/search", q, data)
        return self._hits(data, text)

    def _hits(self, data: dict, text: str) -> list[Hit]:
        """SearXNG JSON → `Hit`. 🔴 **라이브와 카세트가 같은 길을 탄다** —
        갈라 두면 카세트가 통과하고 라이브가 터지는(또는 반대) 자리가 생긴다.
        """
        # 막힌 엔진을 기억한다. 🔴 우회가 아니라 **대체**다.
        for err in data.get("unresponsive_engines") or []:
            if isinstance(err, (list, tuple)) and err:
                name, why = str(err[0]), (str(err[1]) if len(err) > 1 else "")
            else:
                name, why = str(err), ""
            if name:
                self.mark_engine_dead(name, why)
        out = [Hit(title=str(r_.get("title") or ""),
                   url=str(r_.get("url") or ""),
                   snippet=str(r_.get("content") or ""),
                   publisher=_host(r_.get("url")),
                   engine=str(r_.get("engine") or ""),
                   published_at=_when(r_.get("publishedDate")))
               for r_ in data.get("results") or []]
        logger.info("[searx] %r → %d건 (정지 중인 엔진 %s)", text, len(out),
                    self.engine_reasons() or "없음")
        return out


# ══════════════════════════════════════════════════════════════════
# 2순위 — Google Programmable Search
# ══════════════════════════════════════════════════════════════════


@dataclass
class DailyCap:
    """일일 상한을 **코드가** 센다(§19-i-3). 🔴 상한은 요금 경계다."""

    cap: int = GOOGLE_DAILY_CAP
    day: date | None = None
    used: int = 0

    def take(self, today: date | None = None) -> bool:
        today = today or quota_day()
        if self.day != today:
            self.day, self.used = today, 0
        if self.used >= self.cap:
            return False
        self.used += 1
        return True

    @property
    def left(self) -> int:
        return max(0, self.cap - self.used)


def quota_day(now: datetime | None = None) -> date:
    """구글 할당량이 세는 하루. 🔴 **KST 가 아니라 PT 다.**"""
    return (now or datetime.now(timezone.utc)).astimezone(QUOTA_TZ).date()


class GoogleSearch:
    """Google Programmable Search JSON API.

    🔴 **반증 추적과 라인업 세포에만** 배정한다(§19-i-3). 다른 질문이 쓰면
       그 100건이 금세 마르고, 정작 반증을 못 지운다.
    🔴 키가 없으면 `available=False` 다 — **없는 것을 있는 척하지 않는다.**
    """

    name = "Google CSE"
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str | None = None, cx: str | None = None, *,
                 timeout: float = 20.0, cap: int = GOOGLE_DAILY_CAP):
        # 🔴 `None` 이면 환경에서 읽고, **빈 문자열이면 빈 것이다.**
        #    `api_key or os.getenv(...)` 로 쓰면 "키 없음"을 표현할 수 없고,
        #    환경에 키가 있는 기계에서는 그 경로가 조용히 통과한다
        #    (실측 2026-09-28: `.env` 를 읽게 되자 계약 둘이 그것을 잡았다).
        self.key = (os.getenv("GOOGLE_CSE_KEY") or "") if api_key is None \
            else api_key
        self.cx = (os.getenv("GOOGLE_CSE_CX") or "") if cx is None else cx
        self.timeout = timeout
        self.cap = DailyCap(cap)

    @property
    def available(self) -> bool:
        return bool(self.key and self.cx)

    async def query(self, text: str, *, lang: str = "ko",
                    qtype: str | None = None, today: date | None = None
                    ) -> list[Hit]:
        if not self.available:
            raise SearchUnavailable("GOOGLE_CSE_KEY·GOOGLE_CSE_CX 가 없다")
        if qtype is not None and qtype not in GOOGLE_ALLOWED:
            raise SearchUnavailable(
                f"{qtype} 는 Google 배정 밖이다 — {GOOGLE_ALLOWED} 만(§19-i-3)")
        params = {"key": self.key, "cx": self.cx, "q": text, "num": 10,
                  "hl": _lang(lang)}

        # 🔴 카세트(§9 단계 3). ⚠️ **예산을 먼저 세지 않는다** — `replay` 는
        #    구글에 가지 않으므로 할당량을 쓰지 않는다. 종전 순서대로 두면
        #    카세트 재현 100건이 그날 CSE 예산을 통째로 먹은 것처럼 기록되고,
        #    그 기록을 보고 다음 사람이 "상한을 넘겼다"고 오독한다.
        q = cassette.query_string(params)
        if cassette.mode() == cassette.REPLAY:
            try:
                data = cassette.load("search", self.ENDPOINT, q)
            except cassette.CassetteMiss as exc:
                raise SearchUnavailable(str(exc)) from exc
            return self._hits(data, text)

        if not self.cap.take(today or quota_day()):
            raise SearchUnavailable(
                f"검색 예산 소진 — 무료 상한 {self.cap.cap}/일")
        try:
            async with httpx.AsyncClient(timeout=self.timeout,
                                         headers={"User-Agent": UA}) as cli:
                r = await cli.get(self.ENDPOINT, params=params)
        except Exception as exc:                    # noqa: BLE001
            raise SearchUnavailable(f"Google CSE 에 닿지 못했다: {exc}") from exc
        if r.status_code == 429:
            self.cap.used = self.cap.cap        # 상한을 실제로 만났다
            raise SearchUnavailable("검색 예산 소진 — Google 429")
        if r.status_code != 200:
            # 🔴 **구글이 보낸 말을 그대로 전한다.** "HTTP 403" 만으로는 무엇을
            #    고칠지 모른다(§19-b-6 이 사유를 요구하는 이유다).
            #    실측 2026-09-27: 403 의 본문은 "This project does not have the
            #    access to Custom Search JSON API" 였고, 그것이 **사용자가
            #    Cloud 콘솔에서 API 를 켜야 한다**는 뜻이다.
            # ⚠️ 설정 오류는 **예산을 돌려준다** — 질문을 던진 적이 없다.
            self.cap.used = max(0, self.cap.used - 1)
            raise SearchUnavailable(
                f"Google CSE HTTP {r.status_code} — {_why(r)}")
        data = r.json()
        if cassette.mode() == cassette.RECORD:
            cassette.save("search", self.ENDPOINT, q, data)
        return self._hits(data, text)

    def _hits(self, data: dict, text: str) -> list[Hit]:
        """🔴 라이브와 카세트가 **같은 길**을 탄다(SearXNG 와 같은 이유)."""
        out = [Hit(title=str(i.get("title") or ""),
                   url=str(i.get("link") or ""),
                   snippet=str(i.get("snippet") or ""),
                   publisher=_host(i.get("link")),
                   engine="google_cse")
               for i in data.get("items") or []]
        logger.info("[google] %r → %d건 (남은 예산 %d)", text, len(out),
                    self.cap.left)
        return out


# ══════════════════════════════════════════════════════════════════
# 사슬 — 1순위가 죽으면 2순위 (배정 안에서만)
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 GDELT DOC API — **키 없음 · 65개 언어 · 발행 시각**(사용자 기술 지시 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# > 검색 통로(무료): Bing 뉴스 RSS(이미 씀), **GDELT DOC API**(무료, 65개 언어 뉴스,
# > 발행 시각 포함), ~~Brave Search API 무료 등급~~. 셋을 병렬로 쳐서 합친다.
#
# 🔴 **Brave 는 삭제했다**(사용자 지시 2026-10-03) — 키를 요구하는 통로는 안 쓴다.
#    남은 둘(GDELT · Bing 뉴스 RSS)과 SearXNG, **키 없는 셋**을 병렬로 친다.
#
# 🔴 **지금 못 하는 것을 바로 푼다.** 실측 2026-10-03(콜롬비아 vs 파라과이):
#    감독 발언 ×8 이 전부 미결정이었고 까닭은 *"스페인어 기사를 못 집었다"* 였다.
#    GDELT 는 **언어를 묻지 않는다** — 전 세계 뉴스를 한 색인에서 찾는다.
#
# ✅ **키·카드가 없다**(§19-i-1 의 "유료 API 0건" 정의 안).
# ⚠️ **분당 호출 상한이 있다** — 실측: 연달아 세 번 던지니 `HTTP 429` 였고 6초 쉬니
#    `200` 이었다. `Net` 의 호스트별 간격(`MIN_INTERVAL_SEC = 2초`)보다 길게 둔다.
# 🔴 우회하지 않는다 — 429 면 **그 사실을 사유로 올린다**(§19-b-4 대체로 간다).
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

#: 🔴 GDELT 의 최소 간격. ⚠️ **응답 본문이 직접 말한다**(실측 2026-10-03):
#     `Please limit requests to one every 5 seconds or contact … for larger queries.`
#   그 수보다 길게 둔다 — 경계에 붙으면 반올림 차이로 걸린다.
GDELT_INTERVAL_SEC = 6.0

#: 🔴🔴 **한 번 걸리면 한동안 막힌다**(실측 2026-10-03). 75초를 쉬고 던져도 `429` 였다 —
#   간격만 지키는 것으로는 못 빠져나온다(IP 단위 벌점으로 보인다).
#
#  ⚠️ 그때 계속 두드리는 것은 **예의도 아니고 효과도 없다.** 그래서 429 를 받으면
#     이 시간 동안 **스스로 쉰다**(그 사실을 사유로 올린다).
#  🔴 우회가 아니다 — 우회는 다른 IP·다른 UA 로 가는 것이고, 이것은 **더 세게 지키는
#     것**이다(§14-12 가 금지한 것은 전자다).
GDELT_COOLDOWN_SEC = 900.0

#: 🔴 며칠을 보나. ⚠️ §12-c-1 신선도가 그 뒤를 다시 거른다 — 여기는 **색인 창**이다.
GDELT_TIMESPAN = "7d"


@dataclass
class GdeltSearch:
    """🔴 GDELT 뉴스 색인. **언어를 묻지 않는다** — 현지어 기사가 손에 들어온다.

    ⚠️ `SearxSearch`·`GoogleSearch` 와 **같은 규약**이다(`query(text, lang=…)` →
       `list[Hit]`). 규약이 갈리면 `SearchChain` 에 분기가 생긴다.
    """

    timeout: float = 20.0
    alive: bool | None = None
    _last: float = 0.0
    #: 🔴 `429` 를 받은 뒤 **쉬는 끝 시각**(위 `GDELT_COOLDOWN_SEC`)
    _rest_until: float = 0.0

    async def query(self, text: str, *, lang: str = "ko",
                    qtype: str | None = None) -> list[Hit]:
        del qtype                 # 🔴 GDELT 에는 배정 개념이 없다(무료·상한만)
        del lang                  # 🔴 **언어를 묻지 않는다** — 그것이 이 통로의 값이다
        q = " ".join(str(text or "").split())
        if not q:
            raise SearchUnavailable("GDELT: 질의가 비었다")
        params = {"query": q, "mode": "artlist", "format": "json",
                  "maxrecords": "20", "timespan": GDELT_TIMESPAN,
                  "sort": "datedesc"}
        qs = cassette.query_string(params)
        if cassette.mode() == cassette.REPLAY:
            try:
                data = cassette.load("search", GDELT, qs)
            except cassette.CassetteMiss as exc:
                raise SearchUnavailable(str(exc)) from exc
            self.alive = True
            return self._hits(data, q)
        # 🔴 **벌점 중이면 아예 안 던진다** — 두드려도 안 열리고 예의도 아니다
        left = self._rest_until - time.time()
        if left > 0:
            raise SearchUnavailable(
                f"GDELT: 호출 상한에 걸려 {left:.0f}초 더 쉰다 — 다음 수단으로 간다")
        # 🔴 **상한을 지킨다** — 우회가 아니라 기다린다(본문이 5초라고 말한다)
        wait = GDELT_INTERVAL_SEC - (time.time() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=self.timeout,
                                         headers={"User-Agent": UA}) as cli:
                r = await cli.get(GDELT, params=params)
        except Exception as exc:                    # noqa: BLE001
            self.alive = False
            raise SearchUnavailable(f"GDELT 에 닿지 못했다: {exc}") from exc
        finally:
            self._last = time.time()
        if r.status_code == 429:
            # 🔴 **우회하지 않는다** — 더 세게 지키고 사유를 올린다
            self._rest_until = time.time() + GDELT_COOLDOWN_SEC
            logger.info("[gdelt] 429 — %s", (r.text or "")[:100])
            raise SearchUnavailable(
                f"GDELT: 호출 상한(429) — {GDELT_COOLDOWN_SEC:.0f}초 쉰다. "
                f"다음 수단으로 간다")
        if r.status_code != 200:
            self.alive = False
            raise SearchUnavailable(f"GDELT HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as exc:
            # ⚠️ GDELT 는 오류를 **본문 글자**로 주는 판이 있다(JSON 이 아니다)
            raise SearchUnavailable(
                f"GDELT 가 JSON 을 안 준다: {(r.text or '')[:80]}") from exc
        self.alive = True
        if cassette.mode() == cassette.RECORD:
            cassette.save("search", GDELT, qs, data)
        return self._hits(data, q)

    def _hits(self, data: dict, text: str) -> list[Hit]:
        """🔴 GDELT 항목 → `Hit`. **발행 시각을 그대로 싣는다**(그것이 이 통로의 값이다).

        ⚠️ `seendate` 는 `20260928T161500Z` 꼴이다 — `verify.parse_when` 이 원본이다.
        """
        out: list[Hit] = []
        for a in (data.get("articles") or []):
            if not isinstance(a, dict):
                continue
            url = str(a.get("url") or "").strip()
            if not url:
                continue
            out.append(Hit(
                title=str(a.get("title") or ""), url=url,
                # ⚠️ GDELT 는 스니펫을 주지 않는다 — **빈칸이고 그것이 사실이다**
                #    (본문은 `readtext` 가 연다). 지어낸 요약을 넣지 않는다.
                snippet="",
                publisher=str(a.get("domain") or "") or _host(url),
                engine="gdelt",
                published_at=_when(str(a.get("seendate") or ""))))
        logger.info("[gdelt] %r → %d건", text, len(out))
        return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 Bing 뉴스 RSS — **키 없음 · 현지어 · 발행 시각**(사용자 기술 지시 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ **우리가 끈 `bing` 엔진과 다른 것이다.** 끈 것은 SearXNG 의 bing 웹 엔진이고
#    (질의를 무시해 선거구·쇼핑몰을 냈다 — `config/searxng/settings.yml` 의 실측),
#    이것은 **뉴스 RSS 엔드포인트**다. 실측 2026-10-03:
#
#      `Albirroja Colombia lesión` → "¡La baja de última hora en la Albirroja…"(10/02)
#      `ロッテ 引退試合`            → 角中 은퇴 기사 셋(10/02)
#      `Rudolph Speid`             → "Speid sees fight, faith and a spark…"(09/27)
#
# 🔴 키·카드가 없고 **발행 시각(`pubDate`)이 온다** — §12-c-1 이 요구하는 그 칸이다.
# ⚠️ 링크가 `bing.com/news/apiclick.aspx?...&url=…` **리다이렉트**다. 우리는
#    `follow_redirects=True` 로 열므로 그대로 쓸 수 있다(우회가 아니다).
BING_NEWS = "https://www.bing.com/news/search"

_RSS_ITEM = re.compile(r"<item>(.*?)</item>", re.S)


def _rss_field(block: str, tag: str) -> str:
    """🔴 RSS 칸 하나. ⚠️ **속성이 붙은 태그도 받는다** — `<source url="…">매체</source>`
    가 그 꼴이고, 속성을 못 받으면 매체 이름이 통째로 빈다(실측 2026-10-03)."""
    m = re.search(rf"<{tag}\b[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
                  block, re.S)
    if not m:
        return ""
    import html as _html
    return _html.unescape(" ".join(m.group(1).split()))


def _real_url(link: str) -> str:
    """🔴 Bing 뉴스 링크에서 **실제 기사 주소**를 꺼낸다.

    `http://www.bing.com/news/apiclick.aspx?…&url=https%3A%2F%2F…` 꼴이다.
    ⚠️ 못 꺼내면 원래 주소를 그대로 돌려준다 — 열면 리다이렉트가 데려다준다.
    🔴 **왜 꺼내나**: 안 꺼내면 매체·호스트가 전부 `bing.com` 이 되어 **출처 등급과
       열기 순서가 통째로 무의미해진다**(실측 2026-10-03: `publisher=www.bing.com`).
    """
    s = str(link or "").strip()
    if "bing.com" not in s or "url=" not in s:
        return s
    from urllib.parse import parse_qs, unquote, urlparse
    got = parse_qs(urlparse(s).query).get("url") or []
    return unquote(got[0]) if got else s


@dataclass
class BingNewsSearch:
    """🔴 Bing 뉴스 RSS. **언어를 질의가 정한다** — 현지어 낱말이 현지 기사를 낸다.

    ⚠️ `SearxSearch`·`GdeltSearch` 와 **같은 규약**이다(분기를 만들지 않는다).
    """

    timeout: float = 20.0
    alive: bool | None = None

    async def query(self, text: str, *, lang: str = "ko",
                    qtype: str | None = None) -> list[Hit]:
        del qtype                 # 🔴 배정 개념이 없다(무료·키 없음)
        q = " ".join(str(text or "").split())
        if not q:
            raise SearchUnavailable("Bing 뉴스: 질의가 비었다")
        params = {"q": q, "format": "RSS"}
        # 🔴 **언어를 함께 보낸다** — 그 시장의 뉴스를 먼저 준다
        mkt = _MKT.get(str(lang or "").split("-")[0].lower())
        if mkt:
            params["mkt"] = mkt
        qs = cassette.query_string(params)
        if cassette.mode() == cassette.REPLAY:
            try:
                data = cassette.load("search", BING_NEWS, qs)
            except cassette.CassetteMiss as exc:
                raise SearchUnavailable(str(exc)) from exc
            self.alive = True
            return self._hits(str(data.get("rss") or ""), q)
        try:
            async with httpx.AsyncClient(timeout=self.timeout,
                                         headers={"User-Agent": UA},
                                         follow_redirects=True) as cli:
                r = await cli.get(BING_NEWS, params=params)
        except Exception as exc:                    # noqa: BLE001
            self.alive = False
            raise SearchUnavailable(f"Bing 뉴스에 닿지 못했다: {exc}") from exc
        if r.status_code != 200:
            self.alive = False
            raise SearchUnavailable(f"Bing 뉴스 HTTP {r.status_code}")
        self.alive = True
        if cassette.mode() == cassette.RECORD:
            cassette.save("search", BING_NEWS, qs, {"rss": r.text})
        return self._hits(r.text or "", q)

    def _hits(self, rss: str, text: str) -> list[Hit]:
        """🔴 RSS → `Hit`. **발행 시각을 그대로 싣는다**(그 칸이 이 통로의 값이다)."""
        out: list[Hit] = []
        for block in _RSS_ITEM.findall(rss or ""):
            url = _real_url(_rss_field(block, "link"))
            if not url:
                continue
            out.append(Hit(
                title=_rss_field(block, "title"), url=url,
                snippet=_rss_field(block, "description"),
                publisher=_rss_field(block, "source") or _host(url),
                engine="bing-news",
                published_at=_when(_rss_field(block, "pubDate"))))
        logger.info("[bing-news] %r → %d건", text, len(out))
        return out


#: 🔴 언어 → Bing 시장 코드. ⚠️ **모르는 언어는 안 보낸다**(기본 시장으로 간다) —
#   지어낸 코드를 보내면 조용히 엉뚱한 시장 결과가 온다.
_MKT = {"en": "en-US", "es": "es-ES", "ja": "ja-JP", "ko": "ko-KR",
        "zh": "zh-CN"}


@dataclass
class SearchChain:
    """§19-i 순위대로 시도한다. 🔴 **전부 실패하면 사유를 들고 올라간다.**

    세포는 그 사유를 `unknown` 에 적는다(§19-b-6) — 조용히 0 이 되지 않는다.
    """

    searx: SearxSearch | None = None
    google: GoogleSearch | None = None
    #: 🔴 **GDELT** — 키 없음·65개 언어. `searx` 가 0건일 때 **대체**다(§19-b-4).
    #  ⚠️ *"셋을 병렬로 쳐서 합친다"* 는 사용자 설계이고 **다음 단계**다 — 지금은
    #     순차 대체로 붙인다(한 질의에 통신이 늘면 상한에 먼저 닿는다).
    gdelt: "GdeltSearch | None" = None
    #: 🔴 **Bing 뉴스 RSS** — 키 없음·현지어·발행 시각. GDELT 다음 단이다.
    bing: "BingNewsSearch | None" = None
    tried: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool((self.searx and self.searx.alive is not False)
                    or (self.gdelt and self.gdelt.alive is not False)
                    or (self.bing and self.bing.alive is not False)
                    or (self.google and self.google.available))

    async def query(self, text: str, *, lang: str = "ko",
                    qtype: str | None = None,
                    engines: list[str] | None = None) -> list[Hit]:
        """🔴 `engines` 는 **먼저 물을 엔진**이다. 0건이면 지정 없이 한 번 더 묻는다.

        ══════════════════════════════════════════════════════════════
        🔴 왜 지정하나 — 실측 2026-10-02
        ══════════════════════════════════════════════════════════════

        지정 없이 쏘면 **질의를 무시하는 엔진**의 결과가 섞여 들어오고, 열기 예산
        2건이 그쪽으로 간다. 라이브(소프트뱅크–치바롯데)에서 봇이 연 페이지는
        `viagogo 티켓`·`케이세이 전철 PDF`·`temu`·`monster 이력서`였고 **기사는
        0건**이었다. `engines=["google news"]` 로 지정하니 4개 질의 4/4 로 사람이
        읽은 기사가 그대로 나왔다.

        ⚠️ **되시도는 우회가 아니라 §19-b-4 대체다.** 지정 엔진이 0건이면 그 엔진이
           그 질문에 대해 막힌 것이고, 그때 다른 수단으로 간다. 지정이 좁아서 검색
           경로가 통째로 죽는 일을 막는다.
        """
        self.tried = []
        last: Exception | None = None
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **키 없는 통로 셋을 병렬로 쳐서 합친다**(사용자 기술 지시 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 셋을 **병렬로 쳐서 합친다.** 차단된 곳을 우회하지 않는 원칙은 그대로다.
        #
        #  ⚠️ 종전은 **순차 대체**였다 — SearXNG 가 0건이 아니면 GDELT·Bing 을 아예
        #     안 물었다. 그래서 SearXNG 가 **관련 없는 20건**을 낼 때 현지어 기사가
        #     손에 안 들어왔다(실측 2026-10-03: 열기 예산을 그쪽에 태웠다).
        #  🔴 셋은 **키가 없고 비용이 0** 이라 함께 쳐도 늘어나는 비용이 없다.
        #     ⚠️ GDELT 는 자기 상한을 스스로 지킨다(5초 간격·429 면 쉰다).
        #  🔴 **합치기는 주소로 중복을 지운다** — 같은 기사가 두 통로에서 와도 하나다.
        #  ⚠️ 우회가 아니다 — 막힌 곳을 다른 길로 뚫는 것이 아니라, **열려 있는 길
        #     셋을 함께 쓰는 것**이다(§19-b-4 의 "대체"를 동시에 하는 꼴).
        free = [("SearXNG", self.searx, engines), ("GDELT", self.gdelt, None),
                ("Bing뉴스", self.bing, None)]
        jobs = [(name, ch, eng) for name, ch, eng in free if ch]
        if len(jobs) > 1:
            got, why = await self._gather(jobs, text, lang)
            self.tried += why
            if got:
                return got
        if self.searx:
            # 🔴 ① 지정 엔진 → ② 지정 없이. 지정이 없으면 ②만 돈다.
            plans: list[list[str] | None] = [engines, None] if engines else [None]
            for plan in plans:
                try:
                    got = await self.searx.query(text, lang=lang, engines=plan)
                    if got:
                        return got
                    self.tried.append(
                        f"SearXNG:0건({','.join(plan) if plan else '엔진 지정 없음'})")
                except SearchUnavailable as exc:
                    self.tried.append(
                        f"SearXNG({','.join(plan) if plan else '전체'}):{exc}")
                    last = exc
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **GDELT** — SearXNG 가 0건이면 여기로(사용자 기술 지시 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 **언어를 묻지 않는다** — 실측 2026-10-03 의 *"스페인어 기사를 못 집었다"*
        #     가 그대로 풀리는 자리다. 키·카드가 없다.
        #  ⚠️ 상한이 있다(실측: 연달아 세 번 → 429). 그래서 **대체**로만 쓴다 —
        #     한 질의에 통신이 늘면 상한에 먼저 닿는다.
        if self.gdelt:
            try:
                got = await self.gdelt.query(text, lang=lang)
                if got:
                    return got
                self.tried.append("GDELT:0건")
            except SearchUnavailable as exc:
                self.tried.append(f"GDELT:{exc}")
                last = exc
        # 🔴 **Bing 뉴스 RSS** — 키 없음. 실측에서 현지어 질의가 전부 들었다.
        if self.bing:
            try:
                got = await self.bing.query(text, lang=lang)
                if got:
                    return got
                self.tried.append("Bing뉴스:0건")
            except SearchUnavailable as exc:
                self.tried.append(f"Bing뉴스:{exc}")
                last = exc
        # 🔴 5순위는 **배정된 질문에만.** 배정 밖이면 여기서 끝이다.
        if self.google and (qtype is None or qtype in GOOGLE_ALLOWED):
            try:
                got = await self.google.query(text, lang=lang, qtype=qtype)
                if got:
                    return got
                self.tried.append("Google CSE:0건")
            except SearchUnavailable as exc:
                self.tried.append(f"Google CSE:{exc}")
                last = exc
        elif self.google:
            self.tried.append(f"Google CSE:배정 밖({qtype})")
        if last is not None and not self.tried:
            raise last
        raise SearchUnavailable(" · ".join(self.tried) or "검색 수단 없음")

    async def _gather(self, jobs: list, text: str,
                      lang: str) -> tuple[list[Hit], list[str]]:
        """🔴 통로 여럿을 **함께** 치고 합친다. `(결과, 사유들)`.

        🔴 **주소로 중복을 지운다** — 같은 기사가 두 통로에서 와도 하나다.
        ⚠️ 순서는 **통로 순서**를 지킨다(앞 통로의 결과가 앞이다) — 열기 예산이
           몇 건이라 순서가 결과를 정한다.
        🔴 한 통로가 터져도 **나머지는 돈다**(`_one_channel` 이 사유로 바꿔 준다).
        """
        done = await asyncio.gather(*[
            _one_channel(name, ch, text, lang, eng) for name, ch, eng in jobs])
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **지정 엔진이 0건이면 지정 없이 한 번 더** (§19-b-4 · 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 그 대체는 **코드에 이미 있었다** — 아래 순차 경로에. 🔴 그런데 병렬
        #     합계가 **한 건이라도** 있으면 호출부가 거기서 돌아가므로 영영 안 돌았다.
        #
        #  실측 2026-10-04(북마케도니아 vs 스코틀랜드) 로그 원문:
        #
        #    [searx] 'Северна Македонија lineup Scotland фудбал' → **0건**
        #            (정지 중인 엔진 {'google news': 'Suspended: access denied'})
        #    [bing-news] 같은 질의 → 2건
        #    [search] 병렬 합계 **2건** → 🔴 **여기서 끝났다**
        #
        #  🔴 그래서 마케도니아어 질의가 **기회를 못 받았다.** 같은 질의를 지정
        #     없이 던지면 32건이 오고 그 안에 `sportstation.mk`·`sportmanija.mk`·
        #     `gol.mk`·`tvarenasport.mk` 가 있다(실측 2026-10-04).
        #  ⚠️ 우회가 아니다 — **그 엔진이 스스로 정지**를 알려 왔고, 선언된 대체를
        #     그대로 따르는 것이다. 🔴 SearXNG 가 **자기만** 0건일 때만 다시 던진다
        #     (다른 통로가 채웠다고 이 대체를 건너뛰면 그것이 지금의 병이다).
        retry = [(nm, ch, eng) for (nm, ch, eng), (_n, hits, _r)
                 in zip(jobs, done, strict=False)
                 if nm == "SearXNG" and eng and not hits]
        if retry:
            nm, ch, eng = retry[0]
            again = await _one_channel(nm, ch, text, lang, None)
            done = list(done) + [(f"{nm}(지정 없이 다시)", again[1], again[2])]
            logger.info("[search] 🔴 지정 엔진 %s 가 0건 → **지정 없이 다시** "
                        "던졌다 → %d건 (§19-b-4)", eng, len(again[1]))
        out: list[Hit] = []
        why: list[str] = []
        seen: set[str] = set()
        for name, hits, reason in done:
            if reason:
                why.append(reason)
            for h in hits:
                key = str(getattr(h, "url", "") or "").split("#")[0]
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(h)
            if hits:
                why.append(f"{name}:{len(hits)}건")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **발행 시각이 있는 것을 앞으로**(실측 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  합치고 보니 SearXNG 의 날짜 없는 잡음(`twitter.com`·`fundup.ai`·매체
        #  **홈 화면**)이 앞에 오고, Bing 뉴스가 준 **날짜 있는 기사**가 뒤로 갔다.
        #  🔴 열기 예산이 몇 건이라 그 순서가 결과를 정한다.
        #  ⚠️ 그리고 §12-c-1 은 **날짜 없는 자료를 fail-closed 로 떨어뜨린다** —
        #     즉 날짜 없는 것을 먼저 열면 그 예산이 거의 확실히 버려진다.
        #  🔴 지어낸 선호가 아니다: 날짜 있는 기사는 **쓸 수 있고** 없는 것은 못 쓴다.
        #  ⚠️ **안정 정렬**이다 — 같은 조건이면 통로 순서를 지킨다.
        out.sort(key=lambda h: 0 if getattr(h, "published_at", None) else 1)
        if out:
            dated = sum(1 for h in out if getattr(h, "published_at", None))
            logger.info("[search] 병렬 합계 %d건(날짜 있는 것 %d건) (%s)",
                        len(out), dated, " · ".join(why))
        return out, why


# ══════════════════════════════════════════════════════════════════
#: 🔴 병렬 합치기의 보조 — 클래스 밖에 두면 `SearchChain` 이 길어진다
# ══════════════════════════════════════════════════════════════════


async def _one_channel(name: str, ch, text: str, lang: str, engines):
    """통로 하나. 🔴 **터지지 않는다** — 사유를 함께 돌려준다."""
    try:
        kw = {"lang": lang}
        if engines is not None and "engines" in \
                inspect.signature(ch.query).parameters:
            kw["engines"] = engines
        got = await ch.query(text, **kw)
        return name, list(got or []), (f"{name}:0건" if not got else "")
    except SearchUnavailable as exc:
        return name, [], f"{name}:{exc}"
    except Exception as exc:                        # noqa: BLE001
        return name, [], f"{name}:예외 {exc!r}"


def build_chain(*, operational: bool | None = None) -> SearchChain:
    """환경에서 사슬을 만든다. 🔴 키가 없으면 그 칸을 **비운다** — 지어내지 않는다.

    🔴 **비용 잠금**(사용자 지시 2026-09-28): 운영 경로에서는 `CSE_OPERATIONAL`
       이 켜져 있을 때만 CSE 를 붙인다. 사용자가 콘솔에서 **결제 계정 미연결
       또는 할당량 100/일 고정**을 확인했다고 답한 뒤에 켠다.
       ⚠️ `operational=True` 를 명시하면 그 잠금을 건너뛴다 — **실측·게이트
          전용**이고, 스케줄러는 그렇게 부르지 않는다(계약이 검사한다).
    """
    ok = cse_operational() if operational is None else operational
    g = GoogleSearch()
    return SearchChain(searx=SearxSearch(),
                       # 🔴 **GDELT 는 늘 붙인다** — 키·카드가 없고 비용이 0 이다
                       #    (사용자 기술 지시 2026-10-03). ⚠️ 상한은 자기가 지킨다.
                       gdelt=GdeltSearch(),
                       # 🔴 **Bing 뉴스 RSS 도 늘 붙인다** — 키·카드가 없다
                       bing=BingNewsSearch(),
                       google=g if (ok and g.available) else None)


# ══════════════════════════════════════════════════════════════════
#: 🔴 **`error.errors[0].reason` 이 갈림을 정한다** (사용자 지시 2026-09-28).
#   추측 없이 원문 코드로 갈린다 — `message` 문장으로 판단하면 틀린다.
#   ⚠️ 실사고 2026-09-27: 내가 message 를 읽고 "API 미사용설정"이라 단정했는데
#      reason 은 `forbidden` 이었다. 둘이 가리키는 조치가 다를 수 있다.
REASON_ACTION = {
    "accessNotConfigured":
        "① Cloud 콘솔에서 Custom Search API 를 **사용 설정**하라",
    "dailyLimitExceeded":
        "할당량 소진 — 무료 100/일을 다 썼다. 내일 돌아온다",
    "rateLimitExceeded":
        "순간 호출이 몰렸다 — 간격을 두고 다시",
    "forbidden":
        "**키 제한** 또는 그 키가 속한 프로젝트에 API 미사용설정. "
        "cx 불일치는 400(badRequest)로 오므로 이 코드로는 cx 문제가 아니다",
    "badRequest":
        "키가 무효이거나 cx·인자가 잘못됐다 — 본문 message 를 보라",
    "keyInvalid": "키가 무효다",
    "quotaExceeded": "할당량 소진",
}


def reason_of(r) -> str:
    """🔴 `error.errors[0].reason` **원문 그대로.** 없으면 빈 문자열."""
    try:
        errs = ((r.json() or {}).get("error") or {}).get("errors") or []
    except ValueError:
        return ""
    return str(errs[0].get("reason") or "") if errs else ""


def _why(r) -> str:
    """구글 오류를 사람이 읽을 한 줄로. 🔴 키는 담기지 않는다(본문엔 없다).

    🔴 **reason 코드를 먼저** 적고, 그것이 가리키는 조치를 붙인다. message 는
       뒤에 둔다 — 갈림은 코드가 정하고 문장은 참고다.
    """
    reason = reason_of(r)
    try:
        err = (r.json() or {}).get("error") or {}
    except ValueError:
        return f"HTTP 본문이 JSON 이 아니다: {(r.text or '')[:120]}"
    msg = str(err.get("message") or "").strip()
    bits = []
    if reason:
        bits.append(f"reason={reason}")
        if (act := REASON_ACTION.get(reason)):
            bits.append(f"조치: {act}")
    if msg:
        bits.append(f'message="{msg}"')
    return " · ".join(bits) or "본문 없음"


def _lang(lang: str) -> str:
    """§12-b — **현지어로 검색한다.** 한국어로 NPB 를 검색하면 번역 기사만 나온다."""
    return {"ko": "ko-KR", "ja": "ja-JP", "zh": "zh-TW", "en": "en-US"
            }.get(lang, lang)


def _host(url) -> str:
    from urllib.parse import urlparse
    return (urlparse(str(url or "")).hostname or "").lower()


def _when(v):
    """🔴 발행 시각. **파싱 규칙은 `verify.parse_when` 이 원본이다.**

    ⚠️ 종전에는 여기서 `fromisoformat` 만 썼다 — 그래서 RSS 의 RFC822 꼴
       (`Fri, 02 Oct 2026 09:12:00 Z`)이 통째로 `None` 이 됐다(실측 2026-10-03).
       같은 일을 두 곳에서 하면 한쪽이 늘 늦는다(사본 금지).
    """
    if not v:
        return None
    from app import verify
    return verify.parse_when(v, assume_tz=timezone.utc)
