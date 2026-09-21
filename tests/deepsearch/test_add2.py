"""[ADD-2] MSN 래핑 버리기 · Bing RSS 를 `access_basis=feed` 로 등록.

사용자 지시 2026-09-21:
  "MSN 으로 감싸인 기사(본문 3자)는 **버린다**(`reason=wrapper_no_body`).
   같은 제목의 원 매체 URL 이 **같은 검색 결과 안에** 있으면 그것만 쓴다.
   **추가 검색 금지.**"
  "Bing 뉴스 RSS 는 `access_basis=feed` 로 등록(근거 URL·간격·일일 상한)."

🔴 **실측 근거(D43):** 기사 URL 24건 중 **6건이 msn.com** 이었고 본문이
   **3자**였다. MSN 은 JS 렌더라 정적 HTML 에 값이 없다. 제목만 남는다.

⚠️ **추가 검색을 하지 않는다.** 원 매체를 다시 찾으러 나가면 요청이 늘고,
   그건 지시가 금지한 것이다. **같은 응답 안에 있을 때만** 바꿔 쓴다.
"""
from __future__ import annotations

import pytest

from app.deepsearch.search import Hit


def _h(url, title, source=""):
    return Hit(url=url, title=title, source=source, provider="bing_news_rss")


def test_MSN_래핑을_버린다():
    from app.deepsearch.search import drop_wrappers

    hits = [_h("https://www.msn.com/ko-kr/news/x", "한화 선발 발표", "노컷뉴스 on MSN"),
            _h("https://www.osen.co.kr/a/1", "다른 기사", "OSEN")]
    ok, dropped = drop_wrappers(hits)
    assert [h.url for h in ok] == ["https://www.osen.co.kr/a/1"]
    assert dropped[0]["reason"] == "wrapper_no_body"
    assert "msn.com" in dropped[0]["url"]


def test_같은_결과_안에_원문이_있으면_그것만_쓴다():
    """🔴 같은 제목의 원 매체가 **같은 응답 안에** 있으면 바꿔 쓴다."""
    from app.deepsearch.search import drop_wrappers

    t = "한화 왕옌청, 한국전 선발 무산 왜?"
    hits = [_h("https://www.msn.com/ko-kr/news/x", t, "노컷뉴스 on MSN"),
            _h("https://www.osen.co.kr/article/G1", t, "OSEN")]
    ok, dropped = drop_wrappers(hits)
    assert len(ok) == 1 and "osen" in ok[0].url
    assert dropped[0]["reason"] == "wrapper_replaced"


def test_추가_검색을_하지_않는다():
    """⚠️ 지시: "추가 검색 금지." 순수 함수여야 한다."""
    import inspect

    from app.deepsearch import search as S

    # ⚠️ **docstring 은 세지 않는다.** "추가 검색을 하지 않는다"라는 **설명
    #    문구**가 금지어에 걸린다 — DEC-3 에서 같은 실수를 했다.
    #    잠글 것은 **코드가 요청을 보내는 것**이다.
    body = inspect.getsource(S.drop_wrappers).split('"""')[-1]
    for banned in ("await", "async ", "fetch(", "chain_search", "httpx"):
        assert banned not in body, f"추가 요청 경로가 있다: {banned}"


def test_제목이_다르면_바꾸지_않는다():
    """⚠️ 아무 기사나 갖다 붙이면 안 된다 — **제목이 같아야** 같은 기사다."""
    from app.deepsearch.search import drop_wrappers

    hits = [_h("https://www.msn.com/ko-kr/news/x", "한화 선발 발표", "노컷뉴스 on MSN"),
            _h("https://www.osen.co.kr/a/1", "전혀 다른 제목", "OSEN")]
    ok, dropped = drop_wrappers(hits)
    assert [h.url for h in ok] == ["https://www.osen.co.kr/a/1"]
    assert dropped[0]["reason"] == "wrapper_no_body"     # 대체가 아니라 폐기


def test_래핑_도메인_목록이_config_에_있다():
    """🔴 코드에 도메인을 박지 않는다(사본 금지)."""
    import inspect

    from app.deepsearch import search as S
    from app.deepsearch.runtime import load_config

    body = inspect.getsource(S.drop_wrappers).split('"""')[-1]
    assert "msn.com" not in body, "도메인을 코드에 적었다"
    assert "msn.com" in ((load_config().get("search") or {}).get("wrappers") or [])


def test_bing_이_access_basis_feed_로_등록됐다():
    from app.deepsearch.runtime import load_config

    row = ((load_config().get("access_basis") or {}).get("www.bing.com") or {})
    assert row.get("basis") == "feed", row
    assert str(row.get("evidence_url") or "").startswith("https://"), row
    assert row.get("daily_cap"), row
    assert row.get("min_interval_sec"), row


def test_feed_도_robots_를_지난다():
    """🔴 `feed` 는 **robots 를 덮지 않는다.** bing 은 `/news/…` 가 애초에
    허용이라 등록이 필요 없었지만, 간격·상한을 명시하려고 적었다.
    ⚠️ 덮는 것은 `api_terms` 뿐이다 — 그 차이를 계약으로 잠근다."""
    from app.deepsearch.runtime import access_basis, overrides_robots

    assert access_basis("www.bing.com") == "feed"
    assert overrides_robots("www.bing.com") is False
    assert overrides_robots("api.open-meteo.com") is True
