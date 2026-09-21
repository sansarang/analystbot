"""[T-ADD] deepsearch_addendum_0921 짝 테스트.

⚠️ 지시문 번호를 그대로 쓴다. 아직 만들지 않은 단위의 항목은 **그 단위를
   만들 때 여기에 더한다** — 미리 xfail 로 적어 두면 "있는데 안 도는" 것과
   "아직 없는" 것을 구분할 수 없다(오늘 거짓 통과를 세 번 잡았다).

지금 있는 것: DS-2a(변경 감지) · T-ADD 12·13·14(수집·브라우저).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

KST = timezone(timedelta(hours=9))

# ── 픽스처: 09-21 실제로 일어난 일 ────────────────────────────────
#: 🔴 이날 우리가 늦게 안 셋 — 중지 08:30 · 등록 공시 11:06 · 우천 12:40.
_PAGE = """<html><body>
<div class="ad">광고 {ad}</div>
<span class="views">조회 {views}</span>
<time class="updated">{ts}</time>
<div id="main">
  <p>楽天 - ソフトバンク 18:00 楽天モバイルパーク</p>
  {extra}
</div>
</body></html>"""


def page(*, ad="A", views=100, ts="2026-09-21 08:00", extra=""):
    return _PAGE.format(ad=ad, views=views, ts=ts, extra=extra)


IGNORE = [".ad", ".views", "time.updated"]
CANCELLED = '<p class="notice">試合中止 降雨のため</p>'


# ── T-ADD 1 ───────────────────────────────────────────────────────
def test_watch_detects_change_only():
    """본문이 같고 타임스탬프·광고·조회수만 다르면 **변화가 아니다.**"""
    from app.deepsearch.watch import content_hash

    a = content_hash(page(ad="A", views=100, ts="08:00"), IGNORE)
    b = content_hash(page(ad="Z", views=999, ts="12:40"), IGNORE)
    assert a == b, "잡음 때문에 바뀐 것으로 봤다 — 매 주기가 오탐이 된다"

    c = content_hash(page(extra=CANCELLED), IGNORE)
    assert c != a, "중지 문구가 생겼는데 변화로 안 봤다"


@pytest.mark.asyncio
async def test_watch_파서는_바뀐_때만_돈다():
    from app.deepsearch.watch import Watcher

    parsed = []
    bodies = [page(ad="A"), page(ad="Z", views=7), page(extra=CANCELLED)]
    rt = _FakeRT(bodies)
    w = Watcher(runtime=rt, store=_Store(),
                parse=lambda html, row: parsed.append(html) or {"ok": True})
    row = {"url": "https://x.example/g", "ignore_selectors": IGNORE}
    outs = [await w.check(row) for _ in bodies]
    assert [o["changed"] for o in outs] == [True, False, True]
    assert len(parsed) == 2, f"파서가 {len(parsed)}회 돌았다 (기대 2)"


# ── T-ADD 2 ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_watch_uses_conditional_request():
    from app.deepsearch.watch import Watcher

    parsed = []
    rt = _FakeRT([page()], etag='W/"v1"', then_304=True)
    w = Watcher(runtime=rt, store=_Store(),
                parse=lambda html, row: parsed.append(html))
    row = {"url": "https://x.example/g", "ignore_selectors": IGNORE}
    await w.check(row)
    await w.check(row)
    assert rt.seen_etag == 'W/"v1"', f"If-None-Match 를 안 보냈다: {rt.calls}"
    assert len(parsed) == 1, "304 인데 파서가 돌았다"


# ── T-ADD 3 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("mins_to_ko,expect", [
    (400, 30), (180, 10), (120, 10), (65, 5), (30, 5), (20, 3), (5, 3)])
def test_watch_interval_by_phase(mins_to_ko, expect):
    """가짜 시계로 T-180 / T-65 / T-20 경계에서 주기가 바뀐다."""
    from app.deepsearch.watch import interval_min

    ko = datetime(2026, 9, 21, 18, 0, tzinfo=KST)
    now = ko - timedelta(minutes=mins_to_ko)
    assert interval_min(now=now, kickoff=ko, kind="game") == expect


def test_공지는_경기시각과_무관하게_10분():
    from app.deepsearch.watch import interval_min

    now = datetime(2026, 9, 21, 9, 0, tzinfo=KST)
    assert interval_min(now=now, kickoff=None, kind="notice") == 10


# ── T-ADD 4 ───────────────────────────────────────────────────────
def test_status_fact_has_as_of_and_goes_stale():
    """🔴 09-21 에 내가 실제로 저지른 오독을 막는 계약.

    11:50 기사("예정대로 개장")를 보고 "개최"라고 보고했는데, 그 뒤
    스포츠나비가 `試合中止 降雨のため` 를 띄웠다. **최신이 이긴다.**
    """
    from app.deepsearch.watch import StatusFact

    with pytest.raises(ValueError):
        StatusFact(value="scheduled", as_of=None)      # as_of 없으면 사실이 아니다

    t1 = datetime(2026, 9, 21, 11, 50, tzinfo=KST)
    t2 = datetime(2026, 9, 21, 12, 40, tzinfo=KST)
    a = StatusFact(value="scheduled", as_of=t1)
    b = StatusFact(value="cancelled", as_of=t2)
    assert b.beats(a) and not a.beats(b)

    assert not a.is_stale(now=t1 + timedelta(minutes=29))
    assert a.is_stale(now=t1 + timedelta(minutes=31))


# ── T-ADD 5 ───────────────────────────────────────────────────────
def test_notice_lag_metric():
    """"공지 게시 → 봇 인지" 지연(분)."""
    from app.deepsearch.watch import lag_minutes

    ev = [{"url": "u1", "published_at": datetime(2026, 9, 21, 8, 30, tzinfo=KST),
           "changed_at": datetime(2026, 9, 21, 8, 38, tzinfo=KST)},
          {"url": "u2", "published_at": datetime(2026, 9, 21, 11, 6, tzinfo=KST),
           "changed_at": datetime(2026, 9, 21, 11, 16, tzinfo=KST)},
          {"url": "u3", "published_at": None,           # 게시 시각을 모르는 건 빠진다
           "changed_at": datetime(2026, 9, 21, 12, 0, tzinfo=KST)}]
    out = lag_minutes(ev)
    assert out["n"] == 2 and out["median"] == 9.0 and out["max"] == 10.0
    assert out["unknown"] == 1, "게시 시각 모르는 것을 0분으로 세면 지연이 작아 보인다"


# ── T-ADD 6 ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_noisy_page_excluded():
    """ignore_selectors 로도 매번 바뀌면 watch 에서 빼고 **사유를 남긴다.**"""
    from app.deepsearch.watch import Watcher

    rt = _FakeRT([page(extra=f"<p>{i}</p>") for i in range(6)])
    st = _Store()
    w = Watcher(runtime=rt, store=st, parse=lambda html, row: None)
    row = {"url": "https://noisy.example/g", "ignore_selectors": IGNORE}
    for _ in range(6):
        await w.check(row)
    assert not w.is_watched(row["url"])
    why = w.excluded_reason(row["url"])
    assert why and "매번" in why, why


# ── T-ADD 12·13·14 (수집·브라우저) ────────────────────────────────
def test_third_party_crawler_goes_through_runtime():
    """DS-4a 1 — 제3자 크롤러는 **어댑터를 거친다.** 아직 하나도 없다."""
    import subprocess

    out = subprocess.run(
        ["rg", "-l", "crawl4ai|Crawl4AI|AsyncWebCrawler", "app/", "crawler/"],
        capture_output=True, text=True).stdout.strip()
    assert out == "", f"어댑터 없이 들어온 제3자 크롤러가 있다: {out}"


def test_browser_automation_scripted_only():
    """DS-4a 2 — LLM 이 브라우저를 조종하는 경로가 없다. 로그인·캡차 처리 없다."""
    import subprocess

    for pat in (r"browser_use|BrowserUse", r"solve_captcha|captcha_solver",
                r"page\.fill\(.*password", r"login\(.*passwd"):
        out = subprocess.run(["rg", "-l", pat, "app/", "crawler/", "tools/"],
                             capture_output=True, text=True).stdout.strip()
        assert out == "", f"{pat} → {out}"


def test_no_bypass_artifacts_in_deepsearch_path():
    """T-ADD 14 — **딥서치 경로**에 우회 장치가 없다.

    🔴 범위를 여기로 좁힌 것은 사용자 결정이다(2026-09-21 "위장 거부 끄지
       마라"). 기존 수집기에는 `Mozilla/5.0` 위장 22파일(D34)과
       `tor_search.py` 가 **그대로 있고, 그대로 두기로 했다.**
       지시문 원문은 저장소 전체를 대상으로 했으나 그 갈림길에서 사용자가
       "끄지 마라"를 골랐으므로, 잠그는 것은 **새로 만드는 경로**다.
    ⚠️ 이 좁힘을 숨기지 않는다 — 문서에도 적었다(docs/maps/DS-2a.md).
    """
    import subprocess

    for pat in (r"socks5|SOCKS|:9050", r"Mozilla/5\.0", r"proxies\s*=",
                r"cookies\s*="):
        out = subprocess.run(["rg", "-l", pat, "app/deepsearch/"],
                             capture_output=True, text=True).stdout.strip()
        assert out == "", f"딥서치 경로에 {pat} → {out}"


def test_모든_외부_요청이_런타임을_지난다():
    """🔴 `app/deepsearch/` 안에서 httpx 를 직접 부르는 곳은 런타임 하나뿐."""
    import subprocess

    out = subprocess.run(["rg", "-l", r"httpx|aiohttp|requests\.", "app/deepsearch/"],
                         capture_output=True, text=True).stdout.strip().splitlines()
    assert out == ["app/deepsearch/runtime.py"], f"런타임 밖 요청 경로: {out}"


# ── 시험용 대역 ───────────────────────────────────────────────────
class _FakeRT:
    def __init__(self, bodies, *, etag=None, then_304=False):
        self.bodies, self.i = bodies, 0
        self.etag, self.then_304 = etag, then_304
        self.calls, self.seen_etag = [], None

    async def fetch(self, url, *, etag=None, last_modified=None):
        from app.deepsearch.runtime import Fetched

        self.calls.append({"url": url, "etag": etag})
        if etag:
            self.seen_etag = etag
        if self.then_304 and etag:
            return Fetched(url=url, status=304, body=b"", etag=etag,
                           not_modified=True)
        body = self.bodies[min(self.i, len(self.bodies) - 1)]
        self.i += 1
        return Fetched(url=url, status=200, body=body.encode(), etag=self.etag)


class _Store:
    """Redis 대역 — 🔴 진짜 Redis 를 켜지 않고도 계약이 돈다."""

    def __init__(self):
        self.d = {}

    async def get(self, k):
        return self.d.get(k)

    async def set(self, k, v, ex=None):
        self.d[k] = v
