"""페이지 열기 — robots 를 먼저 읽고, 거부면 **dead 처리뿐이다**(§19-f).

🔴 우회 없음(§14-12): 프록시·헤더 위장 금지. 실사고 D34: 운영 수집 경로가
   브라우저 UA 로 위장하고 있었다. UA 는 봇이라고 밝힌다.
🔴 유료 검색 API 0건(§19-f). 이 파일은 **검색을 하지 않는다** — URL 을 연다.
   검색 수단은 `app/search.py` 다(§19-i, 사용자 결정 2026-09-27).

🔴 **카세트**(v4 §9 단계 3): `CASSETTE_MODE=replay` 면 네트워크에 가지 않고
   저장된 응답을 쓴다. 없으면 **없다고 적는다** — 몰래 라이브로 넘어가지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx

from app import cassette

logger = logging.getLogger(__name__)

#: 🔴 봇이라고 밝힌다. 위장하지 않는다(D34).
UA = "AnalystBot/3.0 (sports analysis; contact via telegram)"

#: 같은 호스트에 이 간격보다 자주 가지 않는다.
MIN_INTERVAL_SEC = 2.0
TIMEOUT_SEC = 20.0


@dataclass
class Fetched:
    """열어 본 결과. 🔴 `fetched_at` 은 **코드가** 기록한다(§12-e)."""

    url: str
    ok: bool
    status: int = 0
    text: str = ""
    reason: str = ""
    fetched_at: float = field(default_factory=time.time)
    elapsed_ms: int = 0
    #: 🔴 **페이지가 스스로 적은 발행 시각.** 못 읽으면 `None`.
    #
    #  실측 2026-09-30: SearXNG 결과 20건 중 발행 시각이 있는 것이 **0건**이었다
    #  (`brave`·`duckduckgo` 는 날짜를 안 준다). §12-c-1 은 날짜를 못 읽으면
    #  **거부**(fail-closed)이므로, 스니펫만 보면 검색 경로의 기사 근거가
    #  **구조적으로 전부 떨어진다.** §19-b-2 가 *"숫자·인용은 본문을 연다"* 고 한
    #  이유가 이것이다 — 날짜도 본문에 있다.
    published_at: datetime | None = None
    #: 🔴🔴 **응답 머리말 몇 칸**(네 층 지시서 §2-2) — 배당 피드가 *"남은 요청"* 을
    #  머리말로 준다(실측: `x-requests-remaining`·`x-requests-used`). ⚠️ 그걸 못 읽으면
    #  월 한도를 **우리가 센 수**로만 알고, 그 수는 다른 기계의 호출을 모른다.
    #  🔴 담는 것은 **소문자 이름의 몇 칸뿐**이다 — 쿠키·인증 머리말은 담지 않는다.
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def dead(self) -> bool:
        """그날 이 소스를 버릴지. §19-b-4 — 막히면 우회가 아니라 **대체**다."""
        return not self.ok


class Net:
    """호스트별 robots·간격을 지키는 열기. 인스턴스 하나가 하루를 산다."""

    def __init__(self, *, ua: str = UA, min_interval: float = MIN_INTERVAL_SEC,
                 timeout: float = TIMEOUT_SEC, cache: bool = False):
        self.ua = ua
        self.min_interval = min_interval
        self.timeout = timeout
        # ══════════════════════════════════════════════════════════════
        # 🔴 **한 분석 안에서 같은 주소를 두 번 받지 않는다**(2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  같은 페이지에 **다른 질문**이 걸리는 자리가 생겼다: npb.jp 월간 일정이
        #  ① 장소별 득점(여러 달) ② 이 경기 예고선발·날씨 를 함께 들고 있다.
        #  소스를 둘로 둔 것은 질문이 둘이기 때문이고(파서가 다르다), 통신이 두 번일
        #  이유는 없다.
        #  ⚠️ **기본은 꺼짐이다.** 라이브 스코어처럼 *같은 주소를 반복해서 새로 받아야*
        #     하는 주기가 있고, 거기서 캐시가 켜지면 점수가 영원히 멈춘다.
        #     🔴 그래서 켜는 쪽(`analyze.gather`)이 **한 분석 동안만** 켠다.
        self._cache: dict[tuple, "Fetched"] | None = {} if cache else None
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}
        #: 🔴 `{호스트: 사유}` — **사유 없이 죽이지 않는다.** `source_state` 표의
        #  `reason` 이 NOT NULL 이고, 사유가 없으면 "왜 대체 소스로 갔나"를
        #  되짚을 수 없다(§19-b-6 · CLAUDE.md §조용한 0 금지).
        self.dead_hosts: dict[str, str] = {}

    # ── dead 처리 ─────────────────────────────────────────────────
    def mark_dead(self, host: str, reason: str) -> None:
        """이 호스트를 그날 버린다. 🔴 **사유가 비면 거부한다** — 이름만 남는
        dead 는 "왜"를 잃고, 그러면 다음 사람이 그 소스를 다시 시도한다.

        §19-g 카오스 테스트가 *"1차 소스를 강제로 dead 처리"* 할 때 부르는 문도
        여기다 — robots 거부와 **같은 칸에 다른 사유로** 들어간다.
        """
        host = (host or "").strip().lower()
        if not host:
            raise ValueError("호스트가 비었다")
        if not (reason or "").strip():
            raise ValueError(f"{host} 를 사유 없이 dead 로 두지 않는다")
        self.dead_hosts.setdefault(host, reason)

    # ── robots ────────────────────────────────────────────────────
    async def allowed(self, url: str) -> tuple[bool, str]:
        """robots 가 허용하나. **읽을 수 없으면 허용**(robots 없음 = 제한 없음).

        ⚠️ 거부는 기억한다 — 같은 호스트를 다시 두드리지 않는다.
        """
        host = _host(url)
        if host in self.dead_hosts:
            return False, f"{self.dead_hosts[host]} (기억)"
        if host not in self._robots:
            self._robots[host] = await self._load_robots(host)
        rp = self._robots[host]
        if rp is None:
            return True, ""
        if rp.can_fetch(self.ua, url):
            return True, ""
        self.mark_dead(host, "robots 거부")
        return False, "robots 거부"

    async def _load_robots(self, host: str):
        url = f"https://{host}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10,
                                         headers={"User-Agent": self.ua},
                                         follow_redirects=True) as cli:
                r = await cli.get(url)
        except Exception as exc:                   # noqa: BLE001
            logger.info("[net] robots 못 읽었다 %s: %s — 허용으로 본다", host, exc)
            return None
        body = r.text or ""
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **v5 §4-7 — 판정을 한 표에서 본다**(2026-10-04) [#9]
        # ══════════════════════════════════════════════════════════════
        #
        #  > robots **404 는 허용**으로 본다(npb.jp 와 kleague.com 을 **같은
        #  > 규칙으로**). **301 은 끝까지 따라가 최종 호스트의 robots** 를 읽는다.
        #
        #  ⚠️ 실측 2026-10-04: `npb.jp`(404 → 허용)와 `kleague.com`(301)에
        #     **다른 규칙**을 썼다 — 사용자가 *"못 읽었다가 아니라 따라가지
        #     않았다"* 고 지적했다. 🔴 지금 `follow_redirects=True` 로 따라가고,
        #     판정은 `app/robots.py` 한 표가 말한다.
        #  ⚠️ **5xx 는 허용이 아니다**(`unknown`) — 서버가 흔들릴 때 긁으면 더 흔든다.
        from app import robots as _RB
        said = _RB.verdict_for_status(r.status_code)
        logger.info("[net] %s", _RB.same_rule_note(host, r.status_code))
        if said == "deny":
            self.mark_dead(host, f"robots {r.status_code} — 읽기를 막는다(§4-7)")
            return None
        if said == "unknown":
            # 🔴 모르면 **이번만 건너뛴다** — 기억하지 않는다(서버가 돌아올 수 있다)
            logger.info("[net] robots %s 가 %d — 모른다(fail-closed · 이번만)",
                        host, r.status_code)
            return None
        # ⚠️ robots.txt 자리에 HTML 을 주는 사이트가 있다(npb.jp 실측 2026-09-27).
        #    그것은 robots 파일이 아니다 — 제한 없음으로 본다.
        if said == "allow" or "<html" in body[:400].lower():
            return None
        rp = robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        return rp

    # ── 열기 ──────────────────────────────────────────────────────
    async def get(self, url: str, *, params: dict | None = None,
                  headers: dict | None = None) -> Fetched:
        # 🔴 **카세트 재생은 robots 보다 먼저다.** 저장된 응답을 쓰는 것은
        #    그 사이트에 가는 것이 아니므로 robots 를 다시 물을 대상이 아니고,
        #    물으면 `replay` 가 robots.txt 때문에 네트워크를 때린다(그 순간
        #    "네트워크 없이 재현"이 거짓이 된다 — §19-g 가 요구하는 바로 그것).
        q = cassette.query_string(params)
        if cassette.mode() == cassette.REPLAY:
            got = self._from_cassette(url, q)
            # 🔴🔴 **`--replay-fallthrough` 면 없는 요청만 라이브로**(M134 · 카세트
            #    머리말). ⚠️ 기본은 **안 나간다** — 그 기본이 "네트워크 없이 재현"을
            #    지킨다. 🔴 나간 요청은 **저장한다**(다음 재생에 붙는다).
            if got.ok or cassette.REPLAY_MISS not in str(got.reason or ""):
                return got
            if not cassette.fallthrough():
                return got
            logger.info("[net] 재생 미스 → **라이브로 한 번** %s", url)
        # 🔴 분석 1회 캐시(위 주석). ⚠️ 카세트 **뒤에** 둔다 — 재생 경로를 가리면
        #    "네트워크 없이 재현"이 캐시 상태에 따라 달라진다.
        ckey = (url, q, tuple(sorted((headers or {}).items())))
        if self._cache is not None and ckey in self._cache:
            logger.info("[net] 캐시 적중 %s", url)
            return self._cache[ckey]

        ok, why = await self.allowed(url)
        if not ok:
            logger.info("[net] 건너뛴다 %s — %s", url, why)
            return Fetched(url, False, reason=why)

        host = _host(url)
        wait = self.min_interval - (time.time() - self._last.get(host, 0.0))
        if wait > 0:
            await asyncio.sleep(wait)
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout,
                                         # 🔴 UA 는 **봇이라고 밝힌다**(§14-12).
                                         #    소스별 헤더는 아래에서 얹되 UA 를
                                         #    덮지 않는다 — 위장이 아니다.
                                         headers={"User-Agent": self.ua},
                                         follow_redirects=True) as cli:
                r = await cli.get(url, params=params, headers=headers or None)
        except Exception as exc:                   # noqa: BLE001
            self._last[host] = time.time()
            return Fetched(url, False, reason=f"{type(exc).__name__}: {exc}",
                           elapsed_ms=int((time.time() - t0) * 1000))
        self._last[host] = time.time()
        ms = int((time.time() - t0) * 1000)
        if r.status_code >= 400:
            out = Fetched(url, False, r.status_code,
                          reason=f"HTTP {r.status_code}", elapsed_ms=ms,
                          headers=_kept_headers(r))
        else:
            out = Fetched(url, True, r.status_code, r.text, elapsed_ms=ms,
                          published_at=published_at_of(r.text, url),
                          headers=_kept_headers(r))
        if cassette.mode() in (cassette.RECORD, cassette.REPLAY):
            # ⚠️ **실패도 저장한다.** 404·robots 거부가 재현되지 않으면 §19-b-4
            #    ("막히면 대체")를 카세트로 시험할 수 없다.
            cassette.save("fetch", url, q,
                          {"headers": out.headers,
                           "ok": out.ok, "status": out.status,
                           "text": out.text, "reason": out.reason})
        # 🔴 **성공만 담는다.** 실패를 담으면 한 번의 일시 오류가 그 분석 내내
        #    같은 주소를 죽은 것으로 만든다(§19-b-4 는 그날 dead 지, 영구가 아니다).
        if self._cache is not None and out.ok:
            self._cache[ckey] = out
        return out

    def _from_cassette(self, url: str, q: str) -> Fetched:
        """🔴 `replay` — 저장된 응답뿐이다. 없으면 **없다고 적는다.**"""
        try:
            got = cassette.load("fetch", url, q)
        except cassette.CassetteMiss as exc:
            logger.info("[net] %s", exc)
            return Fetched(url, False, reason=str(exc))
        text = str(got.get("text") or "")
        return Fetched(url, bool(got.get("ok")), int(got.get("status") or 0),
                       text, reason=str(got.get("reason") or ""),
                       published_at=published_at_of(text, url),
                       headers={str(k): str(v) for k, v in
                                (got.get("headers") or {}).items()})

    # ── §19-e 영속 — 죽은 호스트를 하루 넘겨 기억한다 ──────────────
    async def load_state(self, pool, *, when: date | None = None) -> int:
        """`source_state` 에서 **오늘 죽은** 호스트를 되살린다.

        🔴 §19-b-4 는 *"그날 `dead` 로 표시"* 다 — 어제 robots 가 거부했다고
           오늘도 안 두드리면, 사이트가 robots 를 고쳐도 영영 못 본다. 그래서
           **날짜로 가른다.**
        """
        rows = await pool.fetch(
            "SELECT host, reason, dead_since FROM source_state "
            " WHERE dead_since IS NOT NULL AND dead_since::date = $1::date",
            when or datetime.now(timezone.utc).date())
        for r in rows:
            # 🔴 **멱등이어야 한다.** 실측 2026-09-30: 사이클마다 표시를 덧붙여
            #    `robots 거부 (오늘 기록됨) (오늘 기록됨)` 로 자랐다 — 사유가 길어질
            #    뿐 정보는 늘지 않고, 하루 72사이클이면 읽을 수 없게 된다.
            #    ⚠️ 표시가 필요한 이유는 "지금 막은 것"과 "이미 막혀 있던 것"을
            #       구분하기 위해서다. 그래서 **한 번만** 붙인다.
            why = str(r["reason"])
            self.mark_dead(r["host"],
                           why if _LOADED in why else f"{why} {_LOADED}")
        logger.info("[net] 오늘 죽은 호스트 %d개 되살렸다", len(rows))
        return len(rows)

    async def flush_state(self, pool) -> int:
        """죽은 호스트를 `source_state` 에 남긴다. 🔴 **사유째로** 남긴다.

        ⚠️ 살아난 호스트를 여기서 되살리지 않는다 — `dead_since` 는 "그날 언제
           죽었나"이고, 다음 날 `load_state` 가 날짜로 걸러 낸다. 지우는 것은
           사람 몫이다(§19-e: 점수표는 데이터이며 사람 승인 없이 문서를 바꾸지
           않는다).
        """
        for host, reason in self.dead_hosts.items():
            await pool.execute(
                "INSERT INTO source_state (host, dead_since, reason) "
                "VALUES ($1, now(), $2) ON CONFLICT (host) DO UPDATE "
                "SET dead_since = COALESCE(source_state.dead_since, now()), "
                "    reason = EXCLUDED.reason, updated_at = now()",
                host, reason)
        logger.info("[net] source_state 에 %d개 남겼다", len(self.dead_hosts))
        return len(self.dead_hosts)


#: 🔴 DB 에서 되살린 dead 표시. **한 번만** 붙는다(위 `load_state` 참조).
_LOADED = "(DB 기록)"


#: 🔴 담아 두는 머리말 — **이 넷뿐이다**(§2-2 할당량). ⚠️ 목록을 늘리지 않는다
KEPT_HEADERS = ("x-requests-remaining", "x-requests-used", "x-requests-last",
                "retry-after")


def _kept_headers(resp) -> dict[str, str]:
    """🔴 응답 머리말에서 **할당량 칸만** 꺼낸다(쿠키·인증은 담지 않는다).

    ⚠️ 머리말이 **없는 응답 객체**도 온다(테스트의 대역·일부 전송 계층) — 그때는
       빈 표다(실측 2026-10-06: `'_R' object has no attribute 'headers'`).
    """
    box = getattr(resp, "headers", None)
    if box is None:
        return {}
    out: dict[str, str] = {}
    for name in KEPT_HEADERS:
        try:
            got = box.get(name)
        except Exception:                                   # noqa: BLE001
            got = None
        if got is not None:
            out[name] = str(got)
    return out


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


# ══════════════════════════════════════════════════════════════════
# 검색 포트 — 구현은 `app/search.py` 다
# ══════════════════════════════════════════════════════════════════


class Search:
    """검색 수단의 **바닥 구현** — 아무것도 못 찾는 것.

    ⚠️ 종전 이 독스트링은 *"구현이 아직 없다 — 갈림길이다"* 라고 적혀 있었다.
       그 갈림길은 **2026-09-27 에 닫혔다**(§19-i, 사용자 결정): 1순위 SearXNG ·
       2순위 Google CSE · 3순위 RSS. 구현은 `app/search.py` 의 `SearxSearch`·
       `GoogleSearch`·`SearchChain` 이다. 🔴 낡은 사본이 여기 남아 있었다.

    🔴 **이 클래스가 남는 이유**: 수단을 **주지 않은** 호출부를 위해서다. 그때
       세포는 `unknown` 을 내고 사유에 "검색 수단 미정"을 적는다(§19-b-6) —
       조용히 0건이 되지 않는 것이 이것의 값어치다.
    """

    available = False
    name = "없음"

    async def query(self, text: str, *, lang: str = "ko",
                    qtype: str | None = None) -> list[dict]:
        raise SearchUnavailable("검색 수단이 주어지지 않았다 (§19-i 구현은 app/search.py)")


class SearchUnavailable(RuntimeError):
    pass


# ══════════════════════════════════════════════════════════════════
# 페이지가 스스로 적은 발행 시각
# ══════════════════════════════════════════════════════════════════

#: 🔴 **표준 표기만 읽는다.** 매체별 HTML 을 손으로 뒤지면 규칙이 매체마다 자라고,
#  그 목록은 언제나 한 발 늦는다(CLAUDE.md §사본 금지). 아래 넷은 스키마·OG·HTML
#  표준이라 매체와 무관하다.
_PUB_KEYS = ("article:published_time", "article:published", "og:published_time",
             "pubdate", "publishdate", "date", "dc.date.issued")
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""(\w[\w.:-]*)\s*=\s*("([^"]*)"|'([^']*)')""")
_JSON_LD = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I)
_TIME_TAG = re.compile(r"<time\b[^>]*\bdatetime\s*=\s*[\"']([^\"']+)", re.I)


#: 🔴 주소 경로의 발행 날짜 — `/news/2025/01/09/...`.
#
#  ⚠️ **실측 2026-10-01**: `lasvegaslightsfc.com/news/2025/01/09/...head-coach/` 가
#     **9개월 지난 기사**인데 오늘 경기의 "감독 의도" 사실로 통과했다. 그 페이지에
#     메타 발행 시각이 없어서 `dateless_ok` 경로로 soft 로 들어왔다.
#  🔴 날짜가 **주소에 적혀 있었다.** 매체가 경로에 박아 둔 날짜는 본문에 인용된
#     과거 날짜와 다르다 — **발행자가 붙인 구조**다. 그래서 읽는다.
#  ⚠️ 그래도 좁게 읽는다: `/연/월/일/` 꼴만. `/2026_..._season` 같은 연도 하나는
#     발행 날짜가 아니다(M13 재발 경로를 열지 않는다).
_URL_DATE = re.compile(r"/((?:19|20)\d\d)/(\d{1,2})/(\d{1,2})(?:/|$)")


def pick_published(body_date: object, search_date: object) -> tuple[str, str]:
    """🔴🔴 **본문 날짜가 원본이고 검색 날짜는 보조다**(지시 2026-10-05).

    > 이 값이 `published_at` 의 **원본**이다. 검색 엔진이 준 날짜는 **보조로만**
    > 쓴다. 둘 다 없으면 `date_missing` 으로 변수 근거에서 제외(기존 규칙).

    ⚠️ 둘이 **다를 때 어느 쪽이 이기나**를 코드에 적어 둔다 — 그 선택이
       안 적혀 있으면 호출부마다 달라진다(#1).
    """
    body = " ".join(str(body_date or "").split())
    said = " ".join(str(search_date or "").split())
    if body:
        extra = f" (검색 날짜 {said} 는 보조)" if said and said != body else ""
        return body, f"**본문**에서 왔다{extra}"
    if said:
        return said, "⚠️ 본문에 발행일이 없어 **검색 엔진 날짜를 보조로** 쓴다"
    return "", "🔴 **발행일이 없다** — `date_missing` 으로 근거에서 뺀다"


def published_at_from_url(url: str):
    """주소 경로에서 발행 날짜. 🔴 없으면 `None` — 지어내지 않는다."""
    m = _URL_DATE.search(url or "")
    if not m:
        return None
    from app.verify import parse_when
    y, mo, d = m.groups()
    return parse_when(f"{y}-{int(mo):02d}-{int(d):02d}")


def published_at_of(html: str, url: str = ""):
    """페이지의 발행 시각. 🔴 **못 읽으면 `None`** — 지어내지 않는다(fail-closed).

    ⚠️ 본문 어디에 있는 날짜든 잡으면 안 된다 — 기사 안에 인용된 과거 날짜를
       발행 시각으로 읽으면 지난주 기사가 오늘 것이 된다(M13 의 재발 경로).
       그래서 **발행 시각이라고 표시된 자리**(메타 태그·JSON-LD·`<time>`)만 본다.

    ⚠️ 메타 태그는 속성 순서가 매체마다 다르다(`content` 가 먼저 오는 곳이 있다).
       정규식으로 순서를 박으면 절반을 놓친다 — **속성을 뽑아 dict 로** 본다.
    """
    if not html:
        # 🔴 본문이 없어도 **주소는 있다** — 거기 날짜가 있으면 그것이 답이다
        return published_at_from_url(url)
    from app.verify import parse_when      # 지연 import — verify 는 순수 함수다
    head = html[:200_000]                  # 머리만 본다 — 메타는 앞에 있다
    for tag in _META.findall(head):
        attrs = {}
        for m in _ATTR.finditer(tag):
            attrs[m.group(1).lower()] = m.group(3) if m.group(3) is not None \
                else m.group(4)
        key = attrs.get("property") or attrs.get("name") or ""
        if key.strip().lower() not in _PUB_KEYS:
            continue
        when = parse_when(attrs.get("content") or "")
        if when is not None:
            return when
    for pat in (_JSON_LD, _TIME_TAG):
        m = pat.search(head)
        if m and (when := parse_when(m.group(1))) is not None:
            return when
    # 🔴 **마지막으로 주소를 본다.** 페이지가 발행 시각을 안 적는 매체가 많고
    #    (실측: SearXNG 결과의 발행 시각 적재율이 0% 였다), 그때 주소가 유일한
    #    구조적 신호다. ⚠️ 메타가 있으면 메타가 이긴다 — 이것은 대체다.
    return published_at_from_url(url)
