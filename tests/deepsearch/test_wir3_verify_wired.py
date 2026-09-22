"""[WIR-3] `search.verify` 를 **기사 경로에 잇는다.** 만들고 안 이었다.

🔴 실측 2026-09-22 — `verify`·`drop_wrappers` 를 부르는 곳은
   `tools/search_audition.py`(보고 도구) **하나뿐**이었다. 운영 기사 경로
   (`rss_hits` → `chain_search`)는 지나지 않는다. 그 결과:

     KBO KT Wiz@SSG Landers 12건 중 **5건이 msn.com · 본문 3자**
     (JS 렌더라 정적 HTML 에 값이 없다. 요청 5회를 버렸다.)

🔴 **절제 실험(한 겹씩 얹기) · 오늘 KBO 2경기 18건:**

```
종전 18건 → ①래핑 -6 = 12 → ②리캡 -1 = 11 → ③24h창 -9 = 2
```

   ①②는 얹는다. **③은 얹지 않는다** — 오늘 프리뷰
   (`[프로야구 전망] KT 위즈, SSG 상대로 3연승 정조준`)와 선발 기사
   (`왕옌청 한국전 선발 불발…한화와 차출 조건 합의`)가 버려진다.
   ⚠️ 창이 **두 벌**이다: `scout_config.MAX_AGE_H['pre']`=48h(지금 시각 기준)
      vs `situation.SITUATION_WINDOW_HOURS`=24h(킥오프 기준).
      어느 것이 기사 추출 입력의 정본인지는 **사용자 결정 사항**이다
      → `docs/FORKS.md` F-19. 결정 전에는 `window=False` 로 둔다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 22, 2, 0, tzinfo=timezone.utc)
KICK = NOW + timedelta(hours=8)          # 오늘 경기
PUB_NEW = "Tue, 22 Sep 2026 01:00:00 GMT"   # 1h 전
PUB_OLD = "Sun, 20 Sep 2026 20:00:00 GMT"   # 30h 전 — 48h 안 · 24h 창 밖

RSS = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:News="https://www.bing.com:443/news/search">
<channel><title>SSG 랜더스 - Bing뉴스</title>
<item><title>SSG 랜더스 선발 라인업 발표</title>
<link>https://www.osen.co.kr/article/A1</link>
<description>선발 라인업</description>
<News:Source>OSEN</News:Source><pubDate>{PUB_NEW}</pubDate></item>
<item><title>SSG 랜더스 선발 라인업 발표</title>
<link>https://www.msn.com/ko-kr/news/dup</link>
<description>같은 제목의 래핑</description>
<News:Source>OSEN on MSN</News:Source><pubDate>{PUB_NEW}</pubDate></item>
<item><title>SSG 랜더스 불펜 소식은 여기에만</title>
<link>https://www.msn.com/ko-kr/news/only</link>
<description>원 매체가 같은 응답에 없다</description>
<News:Source>스타뉴스 on MSN</News:Source><pubDate>{PUB_NEW}</pubDate></item>
<item><title>SSG 랜더스, 롯데 완파…4연승 [인천 리뷰]</title>
<link>https://www.osen.co.kr/article/A2</link>
<description>어제 경기 상보</description>
<News:Source>OSEN</News:Source><pubDate>{PUB_NEW}</pubDate></item>
<item><title>SSG 랜더스 이윤성 영입, 청라돔 준비</title>
<link>https://www.edaily.co.kr/article/A3</link>
<description>30시간 전 기사</description>
<News:Source>이데일리</News:Source><pubDate>{PUB_OLD}</pubDate></item>
</channel></rss>"""


class _RT:
    def __init__(self):
        self.sent: list[str] = []

    async def fetch(self, url, **kw):
        from app.deepsearch.runtime import Fetched

        self.sent.append(url)
        return Fetched(url=url, status=200, body=RSS.encode())


@pytest.fixture
def rt(monkeypatch):
    r = _RT()
    monkeypatch.setattr("app.deepsearch.runtime.default_runtime",
                        lambda *a, **k: r)
    return r


async def _hits(rt):
    import app.collectors.satellite as SAT

    return await SAT.rss_hits("SSG 랜더스 라인업", league="kbo", stage="pre",
                              now=NOW, sport="kbo", kickoff=KICK)


@pytest.mark.asyncio
async def test_본문_없는_래핑을_버린다(rt):
    """🔴 원 매체가 같은 응답에 **없으면** 버린다(`wrapper_no_body`).
    ⚠️ 있으면 그것으로 갈아끼운다 — 추가 요청 0."""
    urls = {h["url"] for h in await _hits(rt)}
    assert "https://www.msn.com/ko-kr/news/only" not in urls, "래핑이 남았다"
    assert "https://www.msn.com/ko-kr/news/dup" not in urls, "중복 래핑이 남았다"
    assert "https://www.osen.co.kr/article/A1" in urls, "원 매체가 사라졌다"
    assert not [u for u in urls if "msn.com" in u], urls


@pytest.mark.asyncio
async def test_경기_후_상보를_버린다(rt):
    """🔴 `situation.is_recap` 이 원본이다(사본 금지)."""
    titles = " ".join(h["title"] for h in await _hits(rt))
    assert "인천 리뷰" not in titles, "어제 경기 상보가 추출 입력에 들어갔다"


@pytest.mark.asyncio
async def test_24h_창은_여기서_걸지_않는다(rt):
    """🔴 **반대 위험.** 실측 2026-09-22: 24h 창을 얹으면 18건 → 2건이 되고
    오늘 프리뷰·선발 기사가 버려진다. 신선도는 `scout_config.MAX_AGE_H`
    한 곳이 정한다 — 창을 두 벌 걸지 않는다(F-19 결정 대기)."""
    urls = {h["url"] for h in await _hits(rt)}
    assert "https://www.edaily.co.kr/article/A3" in urls, (
        "30시간 전 기사가 버려졌다 — 24h 창이 걸렸다(F-19 결정 전에는 안 건다)")


@pytest.mark.asyncio
async def test_요청은_늘지_않는다(rt):
    """⚠️ 폐기는 **받은 응답 안에서** 한다 — 원 매체를 다시 찾으러 나가지 않는다."""
    await _hits(rt)
    assert len(rt.sent) == 1, rt.sent


def test_규칙을_다시_짓지_않았다():
    """🔴 `rss_hits` 가 래핑 목록·리캡 표지를 **자기 안에 적지 않는다.**

    ⚠️ **본문만 본다** — 주석·독스트링은 제외한다. 원문 문자열을 grep 하면
       "래핑 도메인을 적지 마라"는 **주석 자체**가 검사에 걸린다. 그 거짓
       실패를 이 저장소는 이미 세 번 겪었다(D46). 그래서 `ast` 로 **실제
       문자열 리터럴과 호출 이름**만 꺼내 본다.
    """
    import ast
    import inspect
    import textwrap

    import app.collectors.satellite as SAT
    from app.registry import RECAP_MARKERS

    tree = ast.parse(textwrap.dedent(inspect.getsource(SAT.rss_hits)))
    fn = tree.body[0]
    called = {n.func.id if isinstance(n.func, ast.Name) else
              getattr(n.func, "attr", "")
              for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert "verify" in called, f"verify 를 부르지 않는다 — 부르는 것: {sorted(called)}"

    # 독스트링을 뺀 **코드의 문자열 리터럴**만 모은다
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)
                           and isinstance(fn.body[0].value.value, str)) else fn.body
    lits = [n.value.lower() for st in body for n in ast.walk(st)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [x for x in lits if "msn" in x], f"래핑 도메인을 손으로 적었다: {lits}"
    marks = {m.lower() for ms in RECAP_MARKERS.values() for m in ms}
    hit = [x for x in lits if x in marks]
    assert not hit, f"리캡 표지를 베꼈다: {hit}"


@pytest.mark.asyncio
async def test_sport_을_모르면_리캡을_안_거른다(rt):
    """⚠️ 모르는 종목에 표지가 없다 — 굶기지 않는다(`recap_markers` 규약)."""
    import app.collectors.satellite as SAT

    out = await SAT.rss_hits("q", league="kbo", stage="pre", now=NOW)
    titles = " ".join(h["title"] for h in out)
    assert "인천 리뷰" in titles, "sport 없이도 리캡이 걸렸다"
    assert not [h for h in out if "msn.com" in h["url"]], "래핑은 항상 버린다"
