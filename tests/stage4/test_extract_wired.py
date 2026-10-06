"""§17-b 추출기 **배선** 계약 (사용자 지시 2026-10-02).

> 핵심은 "검색"이 아니라 "읽기"다 … 웹에 변수가 4개 다 있었는데 0건을 가져왔다 …
> 봇이 이걸 못 읽는 한 어떤 리그 규칙을 더해도 같은 벽에 부딪힌다

🔴 **LLM 을 부르지 않는 계약이다.** 로컬 모델이 없거나 느린 곳에서도 돌아야 하므로,
   여기서는 ① 배선이 붙어 있나 ② 코드 쪽 집행(사유 낱말·본문 대조)이 도나 를 본다.
   실측(모델을 실제로 돌린 결과)은 커밋 메시지와 `questions/` 에 적는다.
"""
from __future__ import annotations

import inspect

from app import cells, extract, searchcells
from tests._helpers import strip_docs


def test_규칙_파서가_0건이면_추출기를_부른다():
    """🔴 §19-b-5 — L1~L3 은 *"규칙 파서가 못 읽는 형식의 **대체**"* 다.

    그 자리가 `_open_hits` 의 *"열었는데 사실 0건"* 줄이다 — **그 전이 아니다.**
    ⚠️ 먼저 부르면 규칙 파서가 읽을 수 있는 것도 LLM 에 맡기게 된다(비싸고 틀린다).
    """
    src = strip_docs(inspect.getsource(cells.Cell._open_hits))
    # ⚠️ 라이브 2026-10-02 로 이 줄이 바뀌었다 — 규칙 파서가 **없는** 소스(카탈로그)는
    #    그것을 건너뛰고 바로 추출기로 간다. 묻는 것은 그대로다: **규칙 파서 뒤인가.**
    at_rule = src.index("src.parse_body or (None if src.extract_tasks")
    at_llm = src.index("_extracted(")
    at_fail = src.index("열었는데 사실 0건")
    assert at_rule < at_llm < at_fail, (at_rule, at_llm, at_fail)
    # 🔴 규칙 파서가 성공하면 **부르지 않는다**
    assert src.index("return self._verified(src, facts)") < at_llm


def test_추출_과제가_없으면_부르지_않는다():
    """🔴 과제를 선언한 소스만 읽는다 — 아무 페이지나 LLM 에 넣지 않는다."""
    src = strip_docs(inspect.getsource(cells.Cell._extracted))
    assert "if not src.extract_tasks" in src
    # 🔴 **짧은 본문은 부르지 않는다** — 두 문장을 주면 없는 것을 만들어 낸다
    assert "EXTRACT_MIN_CHARS" in src and cells.EXTRACT_MIN_CHARS >= 200








def test_LLM_이_판정_칸에_닿지_않는다():
    """🔴 §17-c — `direction`·`weight`·`strength`·`survival`·`verdict` 금지.

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다.
    """
    src = strip_docs(inspect.getsource(extract))
    for bad in ("direction", "weight", "strength", "survival", "verdict"):
        assert bad not in src, f"추출기 코드가 {bad} 를 건드린다"


def test_규칙_파서가_없어도_본문을_연다():
    """🔴🔴 **라이브가 찾은 결함이다**(2026-10-02 소프트뱅크–치바롯데).

    카탈로그 세포가 **열기 0/2** 로 끝났다. 검색은 25건을 찾았는데 본문을 **한 번도
    안 열어서** ③ 좁은 질문이 **아예 돌지 않았다.** 조건이 `parse_body is not None`
    이라 규칙 파서가 없는 소스는 그 문을 통과할 수 없었다.

    🔴 카탈로그 소스는 **규칙 파서가 없는 것이 정상이다** — 산문을 겨냥하므로 읽는
       것은 `extract_tasks` 다.
    """
    src = strip_docs(inspect.getsource(cells.Cell._try))
    # ⚠️ `open_body` 는 두 군데 나온다 — ① 스니펫이 사실을 냈는데 **더 센 것**을
    #    찾으려 여는 길 ② 스니펫이 0건이라 여는 길. 🔴 카탈로그가 쓰는 것은 ②다.
    at = src.index("hits and src.open_body and")
    cond = src[at:at + 220]
    assert "extract_tasks" in cond, cond
    # 🔴 `parse_body` 가 있는 소스는 전처럼 돈다 — 둘 다 문을 연다
    assert "parse_body is not None" in cond, cond
    # 🔴 그리고 사유에 **왜 열었나**가 남는다(규칙 파서 없음 · 추출기 이름)
    assert "규칙 파서 없음" in inspect.getsource(cells.Cell._try)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **본문 추출 + 관련 문단** (사용자 기술 지시 2026-10-03 · 기술 3)
# ══════════════════════════════════════════════════════════════════
#
# > 나는 검색 요약이 아니라 **본문을 읽는다** … 팀·선수 이름이 나오는 문단만 골라
# > LLM 에 넘긴다. **입력이 짧아야 8B 모델도 정확하다.**
#
# 종전: `_strip_tags`(태그만) → `body[:4000]`(**앞을 자른다**). 실측 로그가
# *"본문 3329자 중 2500자만 넘겼다"* 를 네 번 적었고 그 네 번이 전부 `unknown` 이었다.

_HTML = """<html><head><title>T</title></head><body>
<nav>메뉴 홈 뉴스 로그인 구독신청 광고문의 이용약관 개인정보처리방침</nav>
<article><p>""" + ("리그 소식 일반 문장입니다. " * 6) + """</p>
<p>""" + ("앙굴로가 발목 부상으로 이번 경기에 결장한다고 구단이 밝혔다. " * 2) + """</p>
<p>""" + ("날씨 이야기와 무관한 잡설이 이어진다. " * 6) + """</p></article>
<footer>저작권 안내 전재 금지 구독 문의</footer></body></html>"""


def test_광고와_메뉴를_걷고_본문만_남긴다():
    """🔴 `trafilatura` 가 메뉴·푸터를 걷는다 — 정규식은 태그만 걷었다."""
    from app import readtext
    text, _when = readtext.extract(_HTML, url="https://x.example/a")
    assert text, "본문을 못 뽑았다"
    assert "결장" in text
    # 🔴 메뉴·푸터가 **없다**
    for junk in ("로그인", "이용약관", "전재 금지"):
        assert junk not in text, junk


def test_질의와_가까운_문단만_넘긴다():
    """🔴🔴 사용자 지시의 핵심이다 — **입력이 짧아야 8B 가 정확하다.**"""
    from app import readtext
    text, _ = readtext.extract(_HTML, url="https://x.example/a")
    got = readtext.top_paragraphs(text, "앙굴로 결장 부상", n=1)
    assert len(got) == 1 and "앙굴로" in got[0], got
    # 🔴 **본문 순서로** 돌려준다 — 점수 순이면 문맥이 끊기고 모델이 인용을 만든다
    many = readtext.top_paragraphs(text, "앙굴로 결장", n=2)
    assert many == [p for p in readtext.paragraphs(text) if p in many], many


def test_못_뽑으면_사유를_남기고_종전_경로로_간다():
    """🔴 조용히 태그만 걷어 돌려주면 *"본문을 뽑았다"* 가 거짓이 된다."""
    from app import readtext
    body, when, why, full = readtext.read("<html></html>", url="x", query="q")
    assert body == "" and when == "" and "못 뽑았다" in why, (body, why)
    # 🔴 **본문 전체 길이를 함께 돌려준다** — 호출부가 *"페이지가 얄팍한가"* 를 그
    #    수로 판단한다. ⚠️ 좁힌 글로 재면 깨끗하고 충분한 글이 거부된다
    #    (실측 2026-10-03: 271자로 좁힌 글이 최소 400자 문턱에 걸렸다).
    assert full == 0
    got, _w, _y, full2 = readtext.read(_HTML, url="u", query="앙굴로 결장", n=1)
    assert full2 > len(got), (full2, len(got))


def test_추출기_경로가_본문_추출을_쓴다():
    """🔴 **규칙 파서는 종전 경로를 그대로 쓴다** — `trafilatura` 는 표를 지우고
    타순은 표에 있다. 이 문은 **LLM 추출기 전용**이다."""
    import inspect

    from app import cells
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(cells.Cell._extracted))
    assert "readtext.read(" in src, "추출기가 본문 추출을 안 쓴다"
    # 🔴 못 뽑았을 때의 대체 경로가 남아 있다
    assert "_strip_tags" in src
    # 🔴 발행일을 채운다(§12-c-1 fail-closed 를 살리는 자리다)
    assert "_parsed(" in src
    # ⚠️ 규칙 파서 쪽은 **안 바뀌었다**
    body_src = strip_docs(inspect.getsource(cells.Cell._open_hits))
    assert "readtext" not in body_src
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **v5 §3-2 가 이 계약을 시험했다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  §3-2 가 *"받은 본문을 모아 에이전트에게 준다"* 를 요구했고, 내가 그 네
    #  줄을 `_open_hits` 안에 **직접** 넣었다 — 🔴 이 계약이 빨개졌다. **맞았다**:
    #  그 함수 안에 이름이 있으면 다음 사람이 규칙 파서를 그 경로로 돌려도
    #  계약이 안 막는다.
    #  ✅ 그래서 **옆 함수**(`_remember_body`)로 뺐다. 🔴 그 함수가 있고
    #     `_open_hits` 가 **그것을 부른다**는 것을 함께 본다(배선 · #2).
    assert callable(getattr(cells.Cell, "_remember_body", None)), (
        "🔴 §3-2 본문 수집 함수가 없다 — 에이전트가 빈손이다")
    assert "_remember_body" in body_src, (
        "🔴 `_open_hits` 가 `_remember_body` 를 **안 부른다** — 본문이 안 모인다")
    keep = strip_docs(inspect.getsource(cells.Cell._remember_body))
    assert "readtext" in keep, "🔴 수집이 본문 추출을 안 쓴다(광고·메뉴가 섞인다)"
