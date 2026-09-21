"""[DS-1] 딥서치 런타임 — **모든 외부 요청이 지나는 한 곳.**

🔴 **왜 있나.** 이 저장소에는 robots 를 검사하는 코드가 한 줄도 없었다
   (실측 2026-09-21: `grep -rl robotparser|can_fetch app/ tools/` → 0건).
   수집기 20여 개가 각자 요청을 보내고, 누가 무엇을 얼마나 치는지 아무도
   모른다. 예절(간격·동시성·상한)도 서킷 브레이커도 없다.

🔴 **stdlib `urllib.robotparser` 를 쓰지 않는다.** 그것은 `*`·`$` 를 해석하지
   않아 `Disallow: /api/*` 를 문자 그대로 읽고 `/api/data/…` 를 **허용**이라
   답한다. 이 버그로 FotMob 을 "robots 명시 허용 — 유일하다"고 **오보했다**
   (DS-0 → [3] 에서 정정). 구글 규격으로 맞춘다:
     `*` = 임의 문자열 · `$` = 끝 · **최장일치 우선** · 동률이면 Allow ·
     **우리 UA 를 지목한 블록이 있으면 `*` 는 보지 않는다**
     (news.google.com 이 `ClaudeBot`·`anthropic-ai` 를 이름으로 거부한다).

⚠️ 값은 전부 `config/deepsearch.yaml` 에서 온다(사본 금지).
⚠️ 이것은 `source_gate` 와 **역할이 다르다** — 그쪽은 사람이 끈 스위치(정책),
   이쪽은 robots 가 말하는 사실(기계). 합치지 않는다.
⚠️ DS-1 은 **자리를 만들 뿐** 기존 수집기를 옮기지 않는다. 옮기는 것은 DS-4a
   어댑터 작업이다 — 한 번에 하면 되돌릴 수 없다.
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import time
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

#: 🔴 **작업 디렉토리에 기대지 않는다.** 상대 경로로 두면 cwd 가 다른 곳에서
#   조용히 빈 설정이 되고, 그러면 간격·상한·서킷이 전부 사라진 채 돈다.
#   `app/engine/rules.py` 와 **같은 방식**이다(사본이 아니라 같은 관용구).
_CFG_PATH = (pathlib.Path(__file__).resolve().parents[2]
             / "config" / "deepsearch.yaml")
_CFG_CACHE: dict | None = None


def load_config(force: bool = False) -> dict:
    """🔴 값의 원본은 `config/deepsearch.yaml` **하나**다."""
    global _CFG_CACHE
    if _CFG_CACHE is not None and not force:
        return _CFG_CACHE
    try:
        import yaml

        _CFG_CACHE = yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        # ⚠️ 조용히 넘어가지 않는다. 설정이 없으면 간격·상한·서킷이 전부
        #    사라진 채 도는 것이고, 그건 남의 서버에 대한 결례다.
        logger.error("[ds1] %s 를 못 읽었다 — 예절값 없이 돈다: %s",
                     _CFG_PATH, exc)
        _CFG_CACHE = {}
    return _CFG_CACHE


def access_basis(host: str) -> str | None:
    """이 호스트에 **robots 밖의 접근 근거**가 있나. 없으면 None.

    🔴 robots 가 거부해도 그 API 자신의 약관이 프로그램 접근을 정하고 있으면
       그 약관이 governing 이다(DEC-2 사용자 결정). 원본은
       `config/deepsearch.yaml` 의 `access_basis:` 하나다.
    🔴 **근거 URL 이 없으면 근거가 아니다** — 그런 항목은 무시한다.
    ⚠️ 전역 스위치가 아니다. **호스트 하나씩**이다.
    """
    row = ((load_config().get("access_basis") or {}).get(str(host or "")) or {})
    if not str(row.get("evidence_url") or "").startswith("http"):
        return None
    return str(row.get("basis") or "") or None


#: robots 를 **덮는** 근거. 🔴 `feed` 는 덮지 않는다 — 피드가 제공된다는 것과
#  robots 가 허락한다는 것은 다른 말이다.
_OVERRIDING = ("api_terms",)


def overrides_robots(host: str) -> bool:
    """이 호스트의 근거가 robots 를 **덮나**.

    🔴 `api_terms` 만 덮는다. `feed` 는 간격·상한을 적으려고 등록할 뿐이고
       robots 검사를 면제하지 않는다.
    """
    return access_basis(host) in _OVERRIDING


class Blocked(RuntimeError):
    """요청을 **보내지 않았다.** 🔴 조용히 빈손을 주지 않는다 — 부른 쪽이
    "자료가 없다"와 "막혀서 안 보냈다"를 구분할 수 있어야 한다."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason, self.detail = reason, detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# ── robots 해석 (순수 함수) ────────────────────────────────────────
def _norm_path(path: str) -> str:
    p = path or "/"
    if not p.startswith("/"):
        p = "/" + p
    return p


def _pattern_match(pattern: str, path: str) -> int | None:
    """구글 규격 일치. 맞으면 **패턴 길이**(최장일치 비교용), 아니면 None.

    `*` = 임의 문자열(0자 이상) · `$` = 문자열 끝.
    ⚠️ 정규식으로 바꾸지 않고 직접 훑는다 — `?`·`+`·`(` 같은 문자가 경로에
       그대로 들어오는데, 정규식으로 만들면 그것들이 메타문자가 된다.
    """
    if pattern == "":
        return None
    anchored = pattern.endswith("$")
    pat = pattern[:-1] if anchored else pattern
    parts = pat.split("*")

    pos = 0
    # 첫 조각은 반드시 맨 앞에서 맞아야 한다
    if not path.startswith(parts[0]):
        return None
    pos = len(parts[0])
    for seg in parts[1:-1]:
        if seg == "":
            continue
        i = path.find(seg, pos)
        if i < 0:
            return None
        pos = i + len(seg)
    if len(parts) > 1:
        last = parts[-1]
        if anchored:
            if not path.endswith(last) or len(path) - len(last) < pos:
                return None
        elif last:
            i = path.find(last, pos)
            if i < 0:
                return None
    elif anchored and path != pat:
        return None
    return len(pattern)


def _groups(text: str) -> list[tuple[list[str], list[tuple[bool, str]]]]:
    """robots.txt → [(user-agent 목록, [(허용여부, 패턴), …]), …]"""
    out: list = []
    agents: list[str] = []
    rules: list = []
    fresh = True
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if not fresh:
                out.append((agents, rules))
                agents, rules = [], []
            agents.append(val.lower())
            fresh = True
        elif key in ("allow", "disallow"):
            fresh = False
            rules.append((key == "allow", val))
    if agents:
        out.append((agents, rules))
    return out


def robots_allows(text: str, path: str, ua: str | None = None) -> bool:
    """이 UA 가 이 경로를 받아도 되나.

    🔴 **이름으로 지목된 블록이 있으면 `*` 는 보지 않는다.** 구글 규격이고,
       실제로 news.google.com 이 `ClaudeBot`·`anthropic-ai` 를 그렇게 막는다.
    ⚠️ 규칙이 하나도 없으면 허용이다(빈 robots.txt 는 전면 허용).
    """
    agent = (ua or (load_config().get("runtime") or {}).get("user_agent") or "")
    token = agent.split("/")[0].strip().lower()
    groups = _groups(text)

    named = [r for ags, r in groups
             if any(a and a != "*" and (a in token or token in a) for a in ags)]
    rules = named[0] if named else next(
        (r for ags, r in groups if "*" in ags), [])
    if not rules:
        return True

    p = _norm_path(unquote(path))
    best_allow, best_deny = -1, -1
    for allow, pattern in rules:
        n = _pattern_match(pattern, p)
        if n is None:
            continue
        if allow:
            best_allow = max(best_allow, n)
        else:
            best_deny = max(best_deny, n)
    if best_deny < 0:
        return True
    return best_allow >= best_deny      # 동률이면 Allow 가 이긴다


# ── 런타임 ────────────────────────────────────────────────────────
@dataclass
class Fetched:
    url: str
    status: int
    body: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


@dataclass
class _Domain:
    lock: asyncio.Semaphore
    last_at: float = 0.0
    sent_today: int = 0
    day: str = ""
    fails: int = 0
    open_until: float = 0.0
    robots_text: str | None = None
    robots_at: float = 0.0
    robots_state: str = "unset"          # ok | unknown | unset
    gate: asyncio.Lock = field(default_factory=asyncio.Lock)


#: 🔴 **이벤트 루프별로 하나.** 호출마다 새로 만들면 도메인 상태(마지막 요청
#  시각·일일 카운터·서킷·robots 캐시)가 매번 초기화되고, 그러면 이 모듈을
#  만든 이유가 통째로 사라진다.
#  실측 2026-09-21(같은 도메인 3회): 새 인스턴스마다 → 대기 **0회** ·
#  robots 재조회 **6회** / 공유 → 대기 2회 · robots 재조회 4회.
#  **요청이 2배가 된다** — robots 를 지키겠다고 만든 것이 남의 서버에 요청을
#  늘리면 안 된다.
#  ⚠️ 싱글턴 하나로 두지 않는 이유: `asyncio.Semaphore` 는 처음 쓸 때 실행
#     중인 루프에 묶인다. 루프가 바뀌는 자리에서 터진다.
_DEFAULTS: dict = {}


def default_runtime() -> "Runtime":
    """공유 런타임. 같은 루프에서는 **같은 것**을 돌려준다."""
    try:
        key = id(asyncio.get_running_loop())
    except RuntimeError:
        key = 0
    rt = _DEFAULTS.get(key)
    if rt is None:
        rt = _DEFAULTS[key] = Runtime()
        if len(_DEFAULTS) > 8:            # 테스트가 루프를 많이 갈아도 안 샌다
            for k in list(_DEFAULTS)[:-4]:
                _DEFAULTS.pop(k, None)
    return rt


class _Httpx:
    """기본 전송. 🔴 테스트는 이걸 갈아끼운다 — 진짜 요청을 내지 않기 위해."""

    async def get(self, url, *, headers=None, timeout=None):
        import httpx

        async with httpx.AsyncClient(timeout=timeout,
                                     follow_redirects=True) as c:
            r = await c.get(url, headers=headers)
        return r.status_code, r.content, dict(r.headers)


class Runtime:
    """🔴 외부 요청은 **전부 여기를 지난다.** 지나지 않는 경로가 생기면
    예절도 robots 도 집계도 그 경로에는 없는 것이다."""

    def __init__(self, *, config=None, transport=None, clock=None, sleep=None):
        self._cfg = config if config is not None else load_config()
        self._t = transport or _Httpx()
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._dom: dict[str, _Domain] = {}

    # -- 설정 읽기: 코드에 값을 박지 않는다 -------------------------
    def _r(self, key, default=None):
        return ((self._cfg.get("runtime") or {}).get(key, default))

    def _circuit(self, key, default):
        return ((self._r("circuit") or {}).get(key, default))

    def _robots_cfg(self, key, default):
        return ((self._r("robots") or {}).get(key, default))

    def _d(self, host: str) -> _Domain:
        d = self._dom.get(host)
        if d is None:
            n = int(self._r("per_domain_concurrency") or 1)
            d = self._dom[host] = _Domain(lock=asyncio.Semaphore(max(1, n)))
        return d

    def robots_state(self, host: str) -> str:
        return self._d(host).robots_state

    def stats(self) -> dict:
        """무엇을 얼마나 쳤나. ⚠️ 표시·관측 전용이다."""
        return {h: {"sent": d.sent_today, "fails": d.fails,
                    "robots": d.robots_state} for h, d in self._dom.items()}

    async def _robots(self, scheme: str, host: str, d: _Domain) -> None:
        ttl = float(self._robots_cfg("cache_ttl_sec", 86400) or 86400)
        if d.robots_text is not None and (self._clock() - d.robots_at) < ttl:
            return
        try:
            status, body, _ = await self._t.get(
                f"{scheme}://{host}/robots.txt",
                headers={"User-Agent": self._r("user_agent") or "AnalystBot/1.0"},
                timeout=float(self._r("timeout_sec") or 20.0))
        except Exception as exc:
            # ⚠️ robots 를 못 받은 것과 "파일이 없다"는 다르다. 둘 다 막지는
            #    않지만 **상태를 구분해 남긴다**.
            logger.debug("[ds1] robots 조회 실패 %s: %s", host, exc)
            d.robots_text, d.robots_state = "", "unknown"
            d.robots_at = self._clock()
            return
        if status == 200:
            d.robots_text = body.decode("utf-8", "replace")
            d.robots_state = "ok"
        else:
            # 🔴 "파일 없음(404)"은 **허용과 다르다.** 막지 않되 그렇게 적는다.
            d.robots_text, d.robots_state = "", "unknown"
        d.robots_at = self._clock()

    async def fetch(self, url: str, *, etag: str | None = None,
                    last_modified: str | None = None) -> Fetched:
        """한 번 받는다. 🔴 막히면 **`Blocked`** 를 올린다 — 빈손을 주지 않는다."""
        u = urlsplit(url)
        host = u.netloc
        d = self._d(host)
        now = self._clock()

        # 서킷 — 열려 있으면 요청을 만들지 않는다
        if d.open_until and now < d.open_until:
            raise Blocked("circuit_open",
                          f"{host} · {int(d.open_until - now)}초 남음")

        # 일일 상한 (⚠️ 날짜가 바뀌면 리셋 — 실시간 날짜로 본다)
        today = time.strftime("%Y-%m-%d")
        if d.day != today:
            d.day, d.sent_today = today, 0
        cap = self._r("daily_cap_per_domain")
        if cap is not None and d.sent_today >= int(cap):
            raise Blocked("daily_cap", f"{host} · {d.sent_today}/{cap}")

        async with d.gate:
            # 🔴 [DEC-2] 약관이 governing 인 호스트는 robots 검사를 지난다.
            #    ⚠️ 그 호스트 **하나만**이다. 전역 스위치가 아니다.
            if overrides_robots(host):
                d.robots_state = "overridden"
            else:
                await self._robots(u.scheme or "https", host, d)
            if d.robots_state == "ok" and not robots_allows(
                    d.robots_text or "", u.path or "/",
                    ua=self._r("user_agent")):
                # 🔴 **요청을 보내지 않는다.** 차단을 우회하지 않는다(지시문 규율).
                raise Blocked("robots", f"{host}{u.path}")

            gap = float(self._r("min_interval_sec") or 0.0)
            if gap > 0 and d.last_at:
                wait = gap - (self._clock() - d.last_at)
                if wait > 0:
                    await self._sleep(wait)

            headers = {"User-Agent": self._r("user_agent") or "AnalystBot/1.0"}
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

            async with d.lock:
                try:
                    status, body, resp = await self._t.get(
                        url, headers=headers,
                        timeout=float(self._r("timeout_sec") or 20.0))
                except Exception:
                    d.fails += 1
                    if d.fails >= int(self._circuit("fail_threshold", 5)):
                        d.open_until = self._clock() + float(
                            self._circuit("open_sec", 300))
                        logger.warning("[ds1] 서킷 열림 %s — 연속 실패 %d",
                                       host, d.fails)
                    raise
            d.fails = 0
            d.last_at = self._clock()
            d.sent_today += 1

        low = {str(k).lower(): v for k, v in (resp or {}).items()}
        return Fetched(url=url, status=status,
                       body=b"" if status == 304 else body,
                       etag=low.get("etag"),
                       last_modified=low.get("last-modified"),
                       not_modified=(status == 304))
