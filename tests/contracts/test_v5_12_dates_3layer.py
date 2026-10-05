"""🔴🔴 **날짜를 세 층으로 푼다** — 사용자 지시 2026-10-05.

> 검색 날짜 문제는 **검색 단계에서 풀지 않는다.** 세 층으로 바꿔라.
>  1. SearXNG 호출에 `time_range=week` 를 **기본**으로 건다. 엔진 표에
>     엔진별 `time_range` 지원 여부를 **실측해** 적는다.
>  2. **fetch 전 거르기**: URL 날짜 패턴과 스니펫 날짜 표현(영·한·일·스페인어)을
>     파싱해 **7일 밖이 확실하면 받지 않는다. 날짜 힌트가 없으면 받는다.**
>  3. **fetch 후**: `htmldate` 로 발행일을 뽑는다(메타·JSON-LD·time 태그).
>     이 값이 `published_at` 의 **원본**이다. 검색 엔진이 준 날짜는 **보조로만**.
>     둘 다 없으면 `date_missing` 으로 변수 근거에서 제외(기존 규칙).
>  4. GDELT `seendate` 와 Bing 뉴스 RSS `pubDate` 는 날짜 있는 통로로 유지.
>     Google News 는 dead.

⚠️ 실측 2026-10-05 (이 지시를 받은 날, SearXNG 127.0.0.1:8888):

```
질의                                     time_range 없음   week    month
ロッテ 西武 スタメン 2026 (ja)                30건            3건      —
Chiba Lotte … lineup October 2026 (en)     45건           10건     12건
France Belgium … preview October 2026      35건           15건     15건
```

🔴 **`week` 는 작동한다**(CLAUDE.md 가 쓰지 말라고 적은 것은 `day` 다 — 그것은
   실측 0건이었다). ⚠️ 그런데 **`publishedDate` 는 모든 조합에서 0건**이다 —
   SearXNG 은 발행 시각을 주지 않는다. 그래서 ③층이 필요하다.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect


# ══════════════════════════════════════════════════════════════════
# ① SearXNG 에 `time_range=week` 를 기본으로
# ══════════════════════════════════════════════════════════════════
def test_d1_searx_가_week_를_기본으로_건다():
    from app import search
    assert hasattr(search, "SEARX_TIME_RANGE"), (
        "🔴 `search.SEARX_TIME_RANGE` 가 없다 — 창을 코드에 박지 말고 이름으로")
    assert search.SEARX_TIME_RANGE == "week", search.SEARX_TIME_RANGE
    src = inspect.getsource(search.SearxSearch.query)
    assert "SEARX_TIME_RANGE" in src, (
        "🔴 `query` 가 그 창을 **안 건다**(#2 배선)")


def test_d1_0건이면_창을_벗기고_다시_던진다():
    """🔴 `week` 로 0건이면 **창 없이** 한 번 더 — 지정 엔진 대체와 같은 결.

    ⚠️ **돌려서** 본다 — D02(퇴로를 죽이기)가 문자열 검사를 빠져나갔다(D46).
    """
    import asyncio

    from app import search
    seen: list = []

    class Fake(search.SearxSearch):
        async def _one(self, text, *, lang="ko", engines=None, time_range=""):
            seen.append(time_range)
            # 🔴 창이 걸린 첫 호출은 **0건**, 벗긴 두 번째는 한 건
            return [] if time_range else [search.Hit(title="t",
                                                     url="https://a.com/1")]

    got = asyncio.run(Fake().query("아무 질의"))
    assert seen == ["week", ""], (
        f"🔴 창을 벗기고 **다시 던지지 않았다**(던진 창: {seen}) — `week` 가 "
        f"0건이면 그 질의가 통째로 죽는다")
    assert len(got) == 1, got


def test_d1_엔진표에_time_range_지원이_적혀_있다():
    """🔴 **실측해 적는다** — 엔진 품질을 코드에 박지 않는다(이 저장소 규율)."""
    import pathlib
    said = pathlib.Path("config/search_routing.yaml").read_text(encoding="utf-8")
    assert "time_range" in said and "실측" in said, (
        "🔴 엔진 표에 `time_range` 지원 여부가 **실측으로** 안 적혀 있다")


# ══════════════════════════════════════════════════════════════════
# ② fetch 전 거르기 — 7일 밖이 **확실하면** 받지 않는다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 지시 원문: *"날짜 힌트가 **없으면 받는다**."* ⚠️ 모르는 것을 버리면
#     당일 기사도 함께 버린다 — fail-open 이 맞다.
_NOW = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.timezone.utc)


def test_d2_url_날짜_패턴을_읽는다():
    from app import datehint
    for url, want in (
            ("https://a.com/2026/10/04/preview", dt.date(2026, 10, 4)),
            ("https://a.com/news/2026-09-01-abc", dt.date(2026, 9, 1)),
            ("https://a.com/20261004/x", dt.date(2026, 10, 4)),
            ("https://a.com/news/preview", None)):
        assert datehint.from_url(url) == want, url


def test_d2_스니펫_날짜를_네_언어로_읽는다():
    from app import datehint
    cases = {
        "Published October 4, 2026 — preview": dt.date(2026, 10, 4),
        "2026년 10월 4일 작성": dt.date(2026, 10, 4),
        "2026年10月4日 掲載": dt.date(2026, 10, 4),
        "4 de octubre de 2026": dt.date(2026, 10, 4),
        "no date at all here": None,
    }
    for text, want in cases.items():
        assert datehint.from_snippet(text) == want, text


def test_d2_7일_밖이_확실하면_안_받는다():
    from app import datehint
    old, why = datehint.too_old("https://a.com/2026/08/01/x", "", now=_NOW)
    assert old and "2026-08-01" in why, why
    fresh, why2 = datehint.too_old("https://a.com/2026/10/04/x", "", now=_NOW)
    assert not fresh, why2
    # 🔴 **힌트가 없으면 받는다**(지시 원문) — 모르는 것을 버리지 않는다
    none, why3 = datehint.too_old("https://a.com/news/x", "", now=_NOW)
    assert not none and why3, why3
    assert "힌트" in why3 or "없" in why3, why3


def test_d2_수집이_그_거름을_쓴다():
    """🔴 **배선**(#2) — 본문을 받기 **전에** 부른다."""
    from app import agentloop
    tree = ast.parse(inspect.getsource(agentloop))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "too_old" in called, (
        "🔴 에이전트가 `datehint.too_old` 를 **안 부른다** — 7일 밖 문서를 "
        "그대로 받는다")


# ══════════════════════════════════════════════════════════════════
# ③ fetch 후 — `htmldate` 가 `published_at` 의 **원본**
# ══════════════════════════════════════════════════════════════════
def test_d3_htmldate_로_발행일을_뽑는다():
    from app import readtext
    html = ('<html><head><meta property="article:published_time" '
            'content="2026-10-04T10:00:00Z"></head><body>'
            '<p>' + "본문 " * 40 + '</p></body></html>')
    said = readtext.published_of(html, url="https://a.com/x")
    assert said == "2026-10-04", said
    # 🔴 `time` 태그도 본다
    html2 = ('<html><body><time datetime="2026-10-03">3일</time>'
             '<p>' + "본문 " * 40 + '</p></body></html>')
    assert readtext.published_of(html2, url="https://a.com/y") == "2026-10-03"
    # 🔴 없으면 **빈 문자열**(지어내지 않는다)
    assert readtext.published_of("<html><body>없다</body></html>") == ""


def test_d3_본문_읽기가_그_값을_원본으로_쓴다():
    """🔴 `read()`·`extract()` 가 `published_of` 를 **먼저** 본다(#2)."""
    from app import readtext
    tree = ast.parse(inspect.getsource(readtext))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "published_of" in called, (
        "🔴 `readtext` 가 `published_of` 를 안 부른다 — trafilatura 의 날짜만 "
        "보면 메타·JSON-LD·time 태그를 놓친다")


def test_d3_검색_엔진_날짜는_보조다():
    """🔴 둘이 다르면 **본문 쪽이 이긴다** — 지시 원문: *"보조로만 쓴다"*."""
    from app import net
    assert hasattr(net, "pick_published"), (
        "🔴 `net.pick_published(본문날짜, 검색날짜)` 가 없다 — 어느 쪽이 원본인지 "
        "코드에 안 적혀 있다")
    got, why = net.pick_published("2026-10-04", "2026-09-01")
    assert got == "2026-10-04" and "본문" in why, (got, why)
    got2, why2 = net.pick_published("", "2026-09-01")
    assert got2 == "2026-09-01" and "보조" in why2, (got2, why2)
    got3, why3 = net.pick_published("", "")
    assert not got3 and why3, why3


# ══════════════════════════════════════════════════════════════════
# ④ 날짜 있는 통로 둘은 유지 · Google News 는 dead
# ══════════════════════════════════════════════════════════════════
def test_d4_날짜_통로_둘이_살아_있다():
    from app import search
    src = inspect.getsource(search)
    assert "seendate" in src, "🔴 GDELT `seendate` 를 안 읽는다"
    assert "pubDate" in src or "published" in src, (
        "🔴 Bing 뉴스 RSS 발행 시각을 안 읽는다")


def test_d2_스니펫_칸이_있고_검색이_채운다():
    """🔴 `getattr` 기본값이 ②층을 **조용히 끄는** 것을 막는다."""
    from app import agentloop
    assert "snippets" in agentloop.Tools.__dataclass_fields__, (
        "🔴 `Tools` 에 `snippets` 칸이 없다 — ②층이 늘 빈 글을 보고 모두 받는다")
    tree = ast.parse(inspect.getsource(agentloop))
    stores = [n for n in ast.walk(tree)
              if isinstance(n, ast.Subscript) and isinstance(n.value,
                                                            ast.Attribute)
              and n.value.attr == "snippets"]
    assert stores, "🔴 아무도 `snippets` 를 **채우지 않는다**(#2 배선)"


def test_d3_세포가_본문_날짜를_먼저_쓴다():
    """🔴 **배선**(#2) — 발행일을 정하는 자리가 `pick_published` 를 부른다.

    ⚠️ 실측 2026-10-05: 그 자리가 **거꾸로**였다 —
       `getattr(got, "published_at", None) or _parsed(when_s)` 로 **검색 날짜를
       먼저** 쓰고 본문을 퇴로로 썼다. 🔴 지시 ③은 *"이 값(htmldate)이
       `published_at` 의 **원본**이다. 검색 엔진이 준 날짜는 **보조로만**"* 이다.
    """
    from app import cells
    tree = ast.parse(inspect.getsource(cells))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "pick_published" in called, (
        "🔴 세포가 `net.pick_published` 를 **안 부른다** — 본문과 검색 중 어느 "
        "쪽이 원본인지 자리마다 달라진다(#1)")
    # 🔴 **인자 순서가 뜻이다** — 첫째가 원본(본문), 둘째가 보조(검색).
    #    ⚠️ D05(둘을 맞바꾸기)가 통과했다: 부르는지만 보면 **거꾸로 불러도**
    #       초록이다(D46 과 같은 결의 함정).
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "pick_published"]
    assert calls, "🔴 호출을 못 찾았다"
    for n in calls:
        first = n.args[0] if n.args else None
        assert isinstance(first, ast.Name) and "when" in first.id, (
            f"🔴 첫 인자가 **본문 날짜가 아니다**({ast.dump(first)[:70]}) — "
            f"검색 날짜를 원본으로 쓰면 지시 ③이 거꾸로 돈다")


def test_d1_카세트_열쇠에_창이_안_들어간다():
    """🔴🔴 **녹음을 깨지 않는다** — CLAUDE.md 가 경고한 자리.

    > 카세트 열쇠에서 `engines` 는 **뺀다** — 넣으면 녹음해 둔 고정물이
    > 한꺼번에 미스가 되고, 그 녹음은 **다시 만들 수 없다.**

    ⚠️ 실사고 2026-10-05: ①층이 `time_range=week` 를 params 에 넣자
       §19-g 게이트 **9건 + 카세트 1건**이 한꺼번에 빨개졌다 — 2026-09-27 의
       웹을 녹음한 것이라 **다시 녹음할 수 없다.**
    🔴 신선도 창도 **라우팅**이다 — 웹이 준 것의 기록이 아니다.
    """
    from app import cassette
    base = {"q": "같은 질의", "format": "json", "language": "ja-JP"}
    assert cassette.query_string(base) == cassette.query_string(
        {**base, "time_range": "week"}), (
        "🔴 창이 카세트 열쇠를 바꾼다 — 녹음이 한꺼번에 미스가 된다")
    assert cassette.query_string(base) == cassette.query_string(
        {**base, "engines": "startpage"}), "🔴 엔진도 열쇠에서 빠져야 한다"
