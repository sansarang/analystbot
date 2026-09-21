"""[DS-1] 딥서치 런타임 — **모든 외부 요청이 지나는 한 곳.**

🔴 **왜 필요한가.** 지금 이 저장소에는 robots 를 검사하는 코드가 **한 줄도
   없다**(실측 2026-09-21: `grep -rl robotparser|can_fetch app/ tools/` → 0건).
   [3] 감사는 임시 스크립트로 했다. 그래서 수집기 20여 개가 각자 요청을 보내고,
   누가 무엇을 얼마나 치는지 아무도 모른다.

🔴 **stdlib `urllib.robotparser` 를 쓰지 않는다.** 그것은 `*`·`$` 와일드카드를
   해석하지 않아 `Disallow: /api/*` 를 문자 그대로 읽고 `/api/data/…` 를
   "허용"으로 답한다. 이 버그로 내가 FotMob 을 "robots 명시 허용"이라고
   **잘못 보고했다**(DS-0 → [3] 에서 정정). 구글 규격으로 직접 맞춘다:
   `*`=임의 문자열 · `$`=끝 · **최장일치 우선** · 동률이면 Allow.

⚠️ 값은 전부 `config/deepsearch.yaml` 에서 온다(사본 금지).
⚠️ 기존 수집기의 UA 는 **건드리지 않는다**(사용자 지시 2026-09-21 "위장 거부
   끄지 마라"). 이 런타임이 **자기 요청에** 쓰는 UA 만 식별 가능한 것으로 한다.

⚠️ 짝 지시문 `deepsearch_tests_0921` 의 T-RT 원문이 이 세션에 없다. 아래 계약은
   `deepsearch_addendum_0921` 이 **명시한 요구**에서만 뽑았다(도메인당 동시 1 ·
   최소 간격 2초 · 도메인 일일 상한 · 서킷 브레이커 · robots 검사 ·
   ETag/If-Modified-Since · 값은 config). 지어낸 항목은 없다.
"""
from __future__ import annotations

import pytest

# ── robots 해석 (순수 함수) ────────────────────────────────────────
#: 🔴 [3] 감사에서 **실제로 받은** 원문이다. 손으로 지어내지 않았다.
GOOGLE_NEWS = """
User-agent: *
Disallow: /
Allow: /$
Allow: /?
Allow: /home$
Allow: /topics/
Allow: /stories/
"""
FOTMOB = """
User-agent: *
Allow: /
Disallow: /api/*
Disallow: /auth/*
Disallow: /info
"""


def test_와일드카드를_해석한다():
    """🔴 stdlib 이 못 하는 바로 그것. 이 한 줄이 없어서 내가 오보했다."""
    from app.deepsearch.runtime import robots_allows

    assert robots_allows(FOTMOB, "/api/data/matches") is False
    assert robots_allows(FOTMOB, "/api/matchDetails") is False
    assert robots_allows(FOTMOB, "/matches") is True


def test_끝_앵커를_해석한다():
    from app.deepsearch.runtime import robots_allows

    assert robots_allows(GOOGLE_NEWS, "/") is True          # Allow: /$
    assert robots_allows(GOOGLE_NEWS, "/rss/search") is False
    assert robots_allows(GOOGLE_NEWS, "/topics/abc") is True


def test_최장일치가_이긴다():
    from app.deepsearch.runtime import robots_allows

    txt = "User-agent: *\nDisallow: /a/\nAllow: /a/b/\n"
    assert robots_allows(txt, "/a/x") is False
    assert robots_allows(txt, "/a/b/x") is True             # 더 긴 Allow


def test_동률이면_허용이_이긴다():
    from app.deepsearch.runtime import robots_allows

    txt = "User-agent: *\nDisallow: /x\nAllow: /x\n"
    assert robots_allows(txt, "/x") is True


def test_우리_UA_블록이_별표를_이긴다():
    """🔴 news.google.com 은 `ClaudeBot`·`anthropic-ai` 를 이름으로 지목해
    전면 거부한다(실측 2026-09-21). 이름 블록이 있으면 그것만 본다."""
    from app.deepsearch.runtime import robots_allows

    txt = ("User-agent: *\nAllow: /\n\n"
           "User-agent: AnalystBot\nDisallow: /\n")
    assert robots_allows(txt, "/any", ua="AnalystBot/1.0") is False
    assert robots_allows(txt, "/any", ua="OtherBot/1.0") is True


# ── 런타임 ────────────────────────────────────────────────────────
class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class FakeTransport:
    """httpx 대신. 🔴 **요청이 실제로 나갔는지**를 센다."""

    def __init__(self, *, robots="User-agent: *\nAllow: /\n", status=200,
                 body=b"ok", headers=None, fail=0):
        self.robots, self.status, self.body = robots, status, body
        self.headers = headers or {}
        self.fail, self.calls = fail, []

    async def get(self, url, *, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {})})
        if url.endswith("/robots.txt"):
            return 200, self.robots.encode(), {}
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("전송 실패")
        return self.status, self.body, dict(self.headers)


def _rt(**kw):
    from app.deepsearch.runtime import Runtime

    return Runtime(**kw)


@pytest.mark.asyncio
async def test_robots_가_거부하면_요청을_안_보낸다():
    from app.deepsearch.runtime import Blocked

    t = FakeTransport(robots=GOOGLE_NEWS)
    rt = _rt(transport=t, clock=FakeClock())
    with pytest.raises(Blocked) as e:
        await rt.fetch("https://news.google.com/rss/search?q=x")
    assert e.value.reason == "robots"
    # 🔴 robots.txt 1회 말고는 **아무것도 안 나갔다**
    assert [c["url"] for c in t.calls] == ["https://news.google.com/robots.txt"]


@pytest.mark.asyncio
async def test_robots_404_는_판단불가지만_허용하고_기록한다():
    """⚠️ "파일 없음"은 허용과 다르다 — 그래도 막지는 않고 **사실을 남긴다**."""
    class NoRobots(FakeTransport):
        async def get(self, url, *, headers=None, timeout=None):
            self.calls.append({"url": url, "headers": dict(headers or {})})
            if url.endswith("/robots.txt"):
                return 404, b"", {}
            return 200, b"ok", {}

    t = NoRobots()
    rt = _rt(transport=t, clock=FakeClock())
    r = await rt.fetch("https://api.example.com/v1/x")
    assert r.status == 200
    assert rt.robots_state("api.example.com") == "unknown"


@pytest.mark.asyncio
async def test_같은_도메인_최소_간격을_지킨다():
    clock = FakeClock()
    waited = []

    async def fake_sleep(s):
        waited.append(s)
        clock.advance(s)

    t = FakeTransport()
    rt = _rt(transport=t, clock=clock, sleep=fake_sleep)
    await rt.fetch("https://a.example.com/1")
    await rt.fetch("https://a.example.com/2")
    assert waited and waited[-1] >= 2.0, f"간격을 안 기다렸다: {waited}"


@pytest.mark.asyncio
async def test_다른_도메인은_안_기다린다():
    clock = FakeClock()
    waited = []

    async def fake_sleep(s):
        waited.append(s)
        clock.advance(s)

    rt = _rt(transport=FakeTransport(), clock=clock, sleep=fake_sleep)
    await rt.fetch("https://a.example.com/1")
    await rt.fetch("https://b.example.com/1")
    assert not [w for w in waited if w >= 2.0], f"남의 도메인 때문에 기다렸다: {waited}"


@pytest.mark.asyncio
async def test_도메인_일일_상한에_걸리면_안_보낸다():
    from app.deepsearch.runtime import Blocked

    t = FakeTransport()
    rt = _rt(transport=t, clock=FakeClock(), sleep=_nosleep,
             config={"runtime": {"daily_cap_per_domain": 2, "min_interval_sec": 0}})
    await rt.fetch("https://a.example.com/1")
    await rt.fetch("https://a.example.com/2")
    before = len(t.calls)
    with pytest.raises(Blocked) as e:
        await rt.fetch("https://a.example.com/3")
    assert e.value.reason == "daily_cap"
    assert len(t.calls) == before, "상한을 넘고도 요청이 나갔다"


@pytest.mark.asyncio
async def test_서킷이_열리면_그_도메인은_멈춘다():
    from app.deepsearch.runtime import Blocked

    t = FakeTransport(fail=3)
    rt = _rt(transport=t, clock=FakeClock(), sleep=_nosleep,
             config={"runtime": {"min_interval_sec": 0,
                                 "circuit": {"fail_threshold": 3, "open_sec": 300}}})
    for _ in range(3):
        with pytest.raises(Exception):
            await rt.fetch("https://a.example.com/x")
    before = len(t.calls)
    with pytest.raises(Blocked) as e:
        await rt.fetch("https://a.example.com/y")
    assert e.value.reason == "circuit_open"
    assert len(t.calls) == before, "서킷이 열렸는데 요청이 나갔다"


@pytest.mark.asyncio
async def test_ETag_를_받으면_다음에_되돌려준다():
    t = FakeTransport(headers={"etag": 'W/"abc"'})
    rt = _rt(transport=t, clock=FakeClock(), sleep=_nosleep,
             config={"runtime": {"min_interval_sec": 0}})
    r1 = await rt.fetch("https://a.example.com/p")
    assert r1.etag == 'W/"abc"'
    await rt.fetch("https://a.example.com/p", etag=r1.etag)
    assert t.calls[-1]["headers"].get("If-None-Match") == 'W/"abc"'


@pytest.mark.asyncio
async def test_304_는_본문이_없다고_말한다():
    class C304(FakeTransport):
        async def get(self, url, *, headers=None, timeout=None):
            self.calls.append({"url": url, "headers": dict(headers or {})})
            if url.endswith("/robots.txt"):
                return 200, self.robots.encode(), {}
            return 304, b"", {}

    rt = _rt(transport=C304(), clock=FakeClock(), sleep=_nosleep,
             config={"runtime": {"min_interval_sec": 0}})
    r = await rt.fetch("https://a.example.com/p", etag='W/"x"')
    assert r.not_modified is True and r.body == b""


@pytest.mark.asyncio
async def test_UA_가_식별_가능하다():
    """⚠️ 기존 수집기는 건드리지 않는다 — **이 런타임의 요청**만 본다."""
    t = FakeTransport()
    rt = _rt(transport=t, clock=FakeClock(), sleep=_nosleep,
             config={"runtime": {"min_interval_sec": 0}})
    await rt.fetch("https://a.example.com/p")
    ua = t.calls[-1]["headers"].get("User-Agent", "")
    assert "AnalystBot" in ua and "Mozilla" not in ua


def test_값은_config_에서_온다():
    """🔴 사본 금지 — 코드에 숫자를 박지 않는다."""
    import inspect

    from app.deepsearch import runtime as R

    src = inspect.getsource(R)
    assert "deepsearch.yaml" in src or "_CFG" in src
    for lit in ("= 2.0", "= 500", "fail_threshold = ", "= 300"):
        assert lit not in src, f"코드에 값을 박았다: {lit}"


def test_설정_파일이_실제로_있다():
    """⚠️ 경로는 **작업 디렉토리에 기대지 않는다** — 런타임이 쓰는 그 경로를
    그대로 본다. 상대 경로였다면 cwd 가 다른 곳에서 조용히 빈 설정이 된다."""
    import yaml

    from app.deepsearch.runtime import _CFG_PATH as p
    assert p.exists(), "값의 원본이 없다"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    r = d.get("runtime") or {}
    for k in ("per_domain_concurrency", "min_interval_sec",
              "daily_cap_per_domain", "user_agent", "circuit", "robots"):
        assert k in r, f"config 에 {k} 가 없다"


async def _nosleep(s):
    return None
