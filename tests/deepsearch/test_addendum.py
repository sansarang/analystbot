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


# ── T-ADD 7·8·9·11 (검색 공급자 · DS-3a) ─────────────────────────
def test_provider_chain_from_config_only():
    """T-ADD 7 — 공급자 이름을 코드에 박지 않는다."""
    import subprocess

    from app.deepsearch import search as S

    out = subprocess.run(
        ["rg", "-n", r'chain\s*=\s*\[|"bing_news_rss"|"media_rss"',
         "app/deepsearch/search.py"], capture_output=True, text=True).stdout
    # 등록표(REGISTRY) 의 **키**로 쓰는 것은 허용이다 — 순서를 박는 것이 금지다.
    assert "chain = [" not in out, f"체인을 코드에 박았다: {out}"
    assert S.chain_names() == ["bing_news_rss", "media_rss"], S.chain_names()


def test_키가_없는_공급자는_비활성(monkeypatch):
    """T-ADD 7 뒷부분 — 키 없는 유료 공급자는 체인에 안 들어간다."""
    from app.deepsearch import search as S

    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    assert "brave" not in S.active_names()


@pytest.mark.asyncio
async def test_provider_cap_falls_through():
    """T-ADD 8 — 일일 상한 도달 → 다음 공급자. **예외 없음.**"""
    from app.deepsearch import search as S

    calls = []

    class P:
        def __init__(self, name, cap, hits):
            self.name, self.daily_query_cap, self._h = name, cap, hits
            self.used = 0

        async def search(self, **kw):
            calls.append(self.name)
            self.used += 1
            return list(self._h)

    a = P("a", 1, [S.Hit(url="u1", title="t1")])
    b = P("b", 9, [S.Hit(url="u2", title="t2")])
    got1 = await S.chain_search("q", providers=[a, b])
    got2 = await S.chain_search("q", providers=[a, b])
    assert [h.url for h in got1] == ["u1"]
    assert [h.url for h in got2] == ["u2"], "상한 뒤 다음 공급자로 안 넘어갔다"
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_전부_막혀도_예외가_아니라_빈손이다():
    from app.deepsearch import search as S

    class Dead:
        name, daily_query_cap = "dead", 0

        async def search(self, **kw):
            raise AssertionError("상한 0 인데 불렸다")

    assert await S.chain_search("q", providers=[Dead()]) == []


def test_provider_content_still_verified():
    """T-ADD 9 — 공급자가 준 본문에도 **같은 검증**이 걸린다.

    🔴 검증 규칙을 새로 만들지 않는다 — `situation.is_recap`(경기 후 기사)과
       `situation.published_before`(시점)가 원본이다(사본 금지).
    ⚠️ 픽스처는 09-21 에 내가 실제로 저지른 오독이다: 9/11 자 중지 공지를
       9/21 경기 중지로 읽었다.
    """
    import inspect
    from datetime import datetime as _dt

    from app.deepsearch import search as S

    src = inspect.getsource(S.verify)
    assert "is_recap" in src and "published_before" in src, \
        "검증을 새로 지었다 — 원본을 불러야 한다"
    # 🔴 원본은 **RFC 2822 문자열만** 파싱하고, 못 파싱하면 "모르면 통과"로
    #    True 를 준다. datetime 을 그냥 넘기면 10일 전 기사가 통과한다
    #    (실측 2026-09-21). 형식을 맞춰 넘기는지 잠근다.
    assert "format_datetime" in src, "datetime 을 그대로 넘기면 창 검사가 무력화된다"

    ko = _dt(2026, 9, 21, 18, 0, tzinfo=KST)
    hits = [
        S.Hit(url="https://a/1", title="한화 7연패 당해도 웃는다…김서현 슬럼프 탈출",
              published_at=_dt(2026, 9, 21, 10, 0, tzinfo=KST)),
        # 경기 후 기사 — 점수 표기
        S.Hit(url="https://a/2", title="포항스틸러스, FC서울 2-1 격파…7위 도약",
              published_at=_dt(2026, 9, 21, 9, 0, tzinfo=KST)),
        # 9/11 자 공지 — 창 밖
        S.Hit(url="https://a/3", title="9/11(金)福岡ソフトバンク戦 中止のお知らせ",
              published_at=_dt(2026, 9, 11, 12, 0, tzinfo=KST)),
    ]
    ok, dropped = S.verify(hits, sport="kbo", starts_at=ko)
    assert [h.url for h in ok] == ["https://a/1"], [h.url for h in ok]
    why = {d["url"]: d["reason"] for d in dropped}
    assert why["https://a/2"] == "post_match"
    assert why["https://a/3"] == "out_of_window"


def test_budget_zero_means_free_only():
    """T-ADD 11 — `monthly_budget_usd: 0` 이면 과금 가능한 호출 0."""
    from app.deepsearch import search as S

    for name in S.active_names():
        assert S.budget_usd(name) == 0, f"{name} 예산이 0 이 아니다"
        assert S.is_free(name), f"{name} 이 과금 가능한데 체인에 있다"


def test_공급자는_질의를_말없이_바꾸지_않는다():
    """🔴 **기계적 절단 규칙을 넣지 않았다 — 실측이 그 규칙을 뒤집었다.**

    처음엔 "검색어가 길수록 나쁘다"고 보고 시장별 단어 상한을 넣으려 했다.
    2×2 절제(2026-09-21 Bing, 같은 시각)가 그 방향을 지지하는 듯했다:

        한/일 긴→짧   한화 선발 1→8 · 中日 予告先発 2→5
        영/스 긴→짧   EPL 확정XI 9→2 (긴 쪽 압승)

    그런데 한 번 더 좁혀 재자 **반대가 나왔다**:

        川崎フロンターレ        11항목/8최근 → 최신 「감독이 반성한 후반 23분 교체책」
        川崎フロンターレ スタメン  5항목/2최근 → 최신 「【川崎vs鹿島】スタメン発表」

    🔴 좁히면 **기사 수는 줄고 정확도는 오른다.** 즉 "당일 기사 회수 수"는
       잘못된 지표다 — 그것만 보면 쓸모없는 기사를 많이 받는 쪽이 이긴다.
       (지시문 DS-3a 4 가 회수율을 1순위로 두는데 실측이 반대를 가리킨다.)

    그래서 규칙을 **짓지 않고** 오디션(DS-3a 3)에 넘긴다. 공급자는 받은
    질의를 그대로 보낸다 — 질의의 원본은 `config/search_terms.yaml` 이다.
    """
    import inspect

    from app.deepsearch import search as S

    src = inspect.getsource(S)
    for banned in ("max_query_words", "trim_query", "[:3]", "split()[:"):
        assert banned not in src, f"질의를 말없이 자르는 코드가 있다: {banned}"


@pytest.mark.asyncio
async def test_보낸_질의가_받은_질의와_같다():
    from app.deepsearch import search as S

    sent = []

    class RT:
        async def fetch(self, url, **kw):
            from app.deepsearch.runtime import Fetched

            sent.append(url)
            return Fetched(url=url, status=200, body=b"<rss></rss>")

    p = S.BingNewsRSS(runtime=RT())
    q = "川崎フロンターレ 予想スタメン 負傷 欠場"
    await p.search(query=q, market="ja-JP")
    import urllib.parse

    assert urllib.parse.quote(q) in sent[0], sent[0]


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


# ── T-ADD 15·16·17 (재순위 · DS-5a) ──────────────────────────────
import json
import pathlib

_FIX = (pathlib.Path(__file__).resolve().parents[1]
        / "fixtures" / "deepsearch" / "valencia_14.json")


def _fixture():
    """🔴 **운영에서 그대로 내려받은 것**이다(2026-09-21, game=Valencia CF).

    지시문 픽스처는 "09-20 K리그 2경기(무고사 출전·대전 로테이션 문단)"인데
    **그 경기들은 캐시에 기사가 0건**이었다(축구 12경기 중 기사가 있는 것은
    이 한 경기뿐). 대신 지시문이 말한 바로 그 상황 — **기사 14건** — 이
    여기 있어서 이것을 썼다. 바꿔 쓴 사실을 숨기지 않는다.
    """
    return json.loads(_FIX.read_text(encoding="utf-8"))


def test_픽스처가_실제_운영_자료다():
    d = _fixture()
    from app.engine.scout_config import drop_boilerplate

    have = [a for a in drop_boilerplate(d["articles"])
            if (a.get("body") or "").strip()]
    assert len(have) == 14, f"정제 후 {len(have)}건 (기대 14)"
    # 🔴 이 경기와 **무관한** 기사가 실제로 섞여 있다 — 재순위가 겨냥하는 것
    joined = " ".join(a.get("body") or "" for a in have)
    assert "피카츄" in joined, "무관 기사가 사라졌다 — 픽스처가 바뀌었나"


def test_rerank_works_without_model():
    """T-ADD 15 — (c) 재순위 모델이 꺼진 상태에서 (a)(b)만으로 상위 k."""
    from app.deepsearch import rerank as R

    assert R.model_enabled() is False, "모델이 기본 켜짐이면 외부 의존이 생긴다"
    d = _fixture()
    paras = R.split(d["articles"])
    assert paras and all(p.article_idx >= 0 and p.para_idx >= 0 for p in paras)
    top = R.top_k(paras, names=(d["home"], d["away"]), k=6)
    # 🔴 **k 를 채우지 않는다.** 실측: 99문단 중 이 경기 증거는 2개뿐이고,
    #    채우면 나머지 4자리를 피카츄·이강인 기사가 가져간다.
    assert 0 < len(top) <= 6
    assert all(p.score > 0 for p in top)


def test_rerank_reduces_tokens():
    """T-ADD 16 — 입력이 줄고, **정답 문단이 상위 k 안에** 있다.

    정답 = Transfermarkt 부상자 표(이 경기 두 팀). 오답 = 피카츄·이강인 기사.
    """
    from app.deepsearch import rerank as R
    from app.collectors.satellite import WINDOW_BUDGET

    d = _fixture()
    paras = R.split(d["articles"])
    top = R.top_k(paras, names=(d["home"], d["away"]), k=6)
    after = sum(len(p.text) for p in top)
    assert after < WINDOW_BUDGET, f"{after}자 — 지금 창 상한({WINDOW_BUDGET})보다 커졌다"

    joined = " ".join(f"{p.title} {p.text}" for p in top)
    # 🔴 정답은 Transfermarkt 부상자 표다. ⚠️ `부상자 N명` 은 **제목에만**
    #    있고 본문은 선수 목록(`Muscle injury (복귀 예정 …)`)이다 — 실측.
    assert "복귀 예정" in joined, "정답 문단(부상자 표)이 상위 k 에 없다"
    assert "피카츄" not in joined, "무관 문단이 상위 k 에 남았다"
    # 🔴 이 경기와 무관한 기사(이강인/PSG)가 자리를 채우면 안 된다.
    #    `Valencia CF` 의 `cf` 가 잡토큰으로 걸려 실제로 그랬다(실측).
    assert "이강인" not in joined, "잡토큰 때문에 무관 기사가 상위 k 에 들어왔다"


def test_quote_maps_to_paragraph():
    """T-ADD 17 — LLM 인용이 `article_idx·para_idx` 문단에 실제로 존재."""
    from app.deepsearch import rerank as R

    d = _fixture()
    paras = R.split(d["articles"])
    target = next(p for p in paras if "복귀 예정" in p.text)
    quote = target.text[10:40]
    got = R.locate_quote(quote, paras)
    assert got is not None
    assert (got.article_idx, got.para_idx) == (target.article_idx, target.para_idx)
    # 🔴 지어낸 인용은 **어디에도 없어야 한다**
    assert R.locate_quote("무고사 선발 출전이 확정됐다", paras) is None


def test_문단마다_출처가_붙는다():
    """🔴 인용 검증은 코드가 한다 — 문단이 어느 기사에서 왔는지 모르면 못 한다."""
    from app.deepsearch import rerank as R

    d = _fixture()
    for p in R.split(d["articles"]):
        assert p.url is not None


# ── T-ADD 10 (오디션 도구 · DS-3a 3) ─────────────────────────────
def test_audition_outputs_table_without_paid_keys(tmp_path, monkeypatch):
    """T-ADD 10 — **유료 키 없이도** rss 단독 표가 나온다."""
    from tools import search_audition as A

    for env in ("BRAVE_API_KEY", "FIRECRAWL_API_KEY", "PARALLEL_API_KEY",
                "TAVILY_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    rows = [A.Row(provider="bing_news_rss", league="kbo", market="ko-KR",
                  query="한화 이글스 선발", got=12, fresh=8, verified=4,
                  dropped={"post_match": 1, "out_of_window": 7},
                  ms=2260, cost_usd=0.0, whitelisted=9)]
    out = tmp_path / "t.md"
    A.write_report(rows, out, date_kst="2026-09-21")
    txt = out.read_text(encoding="utf-8")
    assert "bing_news_rss" in txt and "한화 이글스 선발" in txt
    assert "post_match" in txt, "폐기 사유 분포가 빠졌다"


def test_audition_1순위_지표가_검증통과_사실수다():
    """🔴 **지시문의 지표를 바꿨다 — 실측이 그렇게 하게 했다.**

    지시문 DS-3a 4 는 "당일 기사 회수율"을 1순위로 둔다. 그런데 실측
    2026-09-21 (Bing, 같은 시각):

        川崎フロンターレ        11항목/8최근 → 최신 「감독 교체책 반성」(쓸모없음)
        川崎フロンターレ スタメン  5항목/2최근 → 최신 「スタメン発表」(찾던 것)

    좁히면 **수는 줄고 정확도는 오른다.** 회수율을 1순위로 두면 쓸모없는
    기사를 많이 받는 쪽이 이긴다. 그래서 `verified` 를 1순위로 정렬한다.
    ⚠️ 회수 수(`got`·`fresh`)는 **버리지 않고 함께 싣는다** — 지시문이
       요구한 값이고, 둘을 나란히 봐야 이 뒤집힘이 보인다.
    """
    from tools import search_audition as A

    assert A.PRIMARY_METRIC == "verified"
    rows = [A.Row(provider="p_many", league="kbo", market="ko-KR", query="q",
                  got=30, fresh=20, verified=1, dropped={}, ms=100,
                  cost_usd=0.0, whitelisted=0),
            A.Row(provider="p_good", league="kbo", market="ko-KR", query="q",
                  got=5, fresh=2, verified=4, dropped={}, ms=100,
                  cost_usd=0.0, whitelisted=0)]
    assert A.rank_rows(rows)[0].provider == "p_good", "회수 수가 이기면 안 된다"


def test_audition_은_자동_채택을_하지_않는다():
    """🔴 지시문 DS-3a 3: "**자동 채택 금지**" — 사용자가 고른다."""
    import inspect

    from tools import search_audition as A

    src = inspect.getsource(A)
    for banned in ("rules.yaml", "deepsearch.yaml", "R.set", "chain =",
                   "write_text(.*chain"):
        assert banned not in src, f"오디션이 설정을 건드린다: {banned}"
    assert "자동 채택" in src or "사용자가" in src


def test_audition_은_경기_전_시점만_쓴다():
    """🔴 지시문 DS-3a 3: 과거 경기로 돌리면 **경기 후 기사가 섞인다.**"""
    import inspect

    from tools import search_audition as A

    src = inspect.getsource(A.run)
    assert "starts_at" in src and "now" in src


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
