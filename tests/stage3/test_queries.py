"""단계 3 계약 — §13-b 소스 표(**사본 금지**)와 §19-b-5 변형 검색.

§19-b-5 원문: *"같은 검색어 반복 금지. 언어(한→일→영), 표기(9月27日→27日, 팀
정식명→약칭), 매체명 추가(`西スポ`), 시점(오늘→전날 예고 기사) 순으로 변형.
변형 생성은 L5(LLM)이 하되 §12-b 규칙 정규식으로 걸러서 쓴다."*
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app import llm, queries

ROOT = Path(__file__).resolve().parents[2]
#: 🔴 **정본은 부록의 §13-b 표다.** yaml 은 그 구현이고, 이 파일이 둘을 대조한다.
APPENDIX = (ROOT / "docs" / "fable" / "v4_appendix_from_v3.md").read_text(
    encoding="utf-8")
DAY = date(2026, 9, 27)


#: 🔴 `_rows` 의 **독립** 정규식. 줄 필터와 **다른 방법**이어야 대조가 뜻을 가진다.
#:
#: ⚠️ 줄 필터는 *"머리글 낱말·구분줄을 뺀다"* 로 가르고, 이쪽은 **데이터 행의
#:    구조적 성질**로 가른다: §13-b 의 `검색어` 칸은 **자리표를 반드시 담는다**
#:    (`{月日}`·`{date}`·`{날짜}`). 머리글의 그 칸은 `검색어`(자리표 없음)이고
#:    구분줄은 `---` 다 — 그래서 둘이 저절로 떨어진다.
#: 🔴 그러니 정본에 자리표 없는 행이 생기면 **수가 안 맞아 터진다** — 그때는
#:    "표의 규약이 바뀌었다"는 뜻이고, 그것이 이 대조의 값어치다.
_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*`?([^|`]*\{[^|`]*)`?\s*\|",
                  re.M)


def _section(start: str, end: str) -> str:
    return APPENDIX.split(start)[1].split(end)[0]


def _rows() -> list[tuple[str, str, str]]:
    """§13-b 표의 데이터 행 `(팀, 1차 소스, 검색어)`.

    🔴 **정규식이 행을 빠뜨리면 터진다.** 데이터 행을 따로 세어 대조한다 —
       "원본에서 자란다"는 파싱이 **완전할 때만** 참이다(단계 2 의 `_rows` 와 같은
       규약. 손으로 쓴 `[a-z_]+` 가 `h2h_pattern` 을 놓쳐 13유형을 12로 센 적이 있다).
    """
    sec = _section("**13-b 확정 라인업 1차 소스", "**13-c 라인업 검증 규칙")
    data = [ln for ln in sec.splitlines()
            if ln.startswith("|") and not re.match(r"^\|\s*-", ln)
            and not re.match(r"^\|\s*팀\s*\|", ln)]
    # 🔴 **두 방법으로 뽑아 대조한다.** 리뷰 2026-09-30: 종전 판은 `got` 을 `data`
    #    에서 만들어 `len(got) == len(data)` 가 **늘 참**이었다(공회전). 단계 2 의
    #    본보기(`tests/stage2/test_rules.py`)는 줄 필터와 **독립 정규식**을 대조
    #    했는데, 그 규약이 베껴지며 사라졌다.
    got = [tuple(c.strip() for c in m.groups())
           for m in _ROW.finditer(sec)]
    assert len(got) == len(data), (
        f"표 데이터 행 {len(data)}개 중 {len(got)}개만 뽑았다 — 정규식이 행을 "
        f"빠뜨린다. 뽑은 것: {[g[0] for g in got]}")
    return got


# ══════════════════════════════════════════════════════════════════
# §13-b — 🔴 사본 금지
# ══════════════════════════════════════════════════════════════════

def test_yaml이_13b_표를_전부_담았다():
    """🔴 팀 이름을 여기 적지 않는다. **정본 표에서 읽는다.**

    ⚠️ 정본에 팀이 생기면 이 계약이 빨개져 *"따라가라"* 고 말한다. 손으로 유지하는
       목록은 언제나 한 발 늦는다(CLAUDE.md §사본 금지).
    """
    want = {team for team, _, _ in _rows()}
    have = set(queries.lineup_teams())
    assert have == want, (f"yaml 이 빠뜨린 행 {sorted(want - have)} · "
                          f"정본에 없는 행 {sorted(have - want)}")


def test_검색어가_정본과_같다():
    """🔴 검색어 틀을 **바꿔 적지 않는다** — `{月日}`·`{球場}` 를 그대로 쓴다."""
    want = {team: q.strip("`") for team, _, q in _rows()}
    for team, row in queries.lineup_teams().items():
        assert row["query"] == want[team], (
            f"{team}: yaml={row['query']!r} 정본={want[team]!r}")


def test_매체_토큰이_정본_칸_안에_있다():
    """🔴 **매체명을 지어내지 않는다.** yaml 의 `media_token` 은 정본 `1차 소스`
    칸에 실제로 있는 낱말이어야 한다.

    ⚠️ 이 칸은 산문이라(`구단 공식 X 인용 팀 블로그, 닛칸`) 첫 토큰을 기계로 뽑으면
       `구단` 같은 쓸모없는 낱말이 나온다(실측 2026-09-30). 그래서 사람이 골라
       적고 — **기계가 정본과 대조한다.**
    """
    primary = {team: p for team, p, _ in _rows()}
    for team, row in queries.lineup_teams().items():
        tok = (row.get("media_token") or "").strip()
        if not tok:
            continue        # 🔴 정본이 구체 매체를 안 대는 행 — 비우는 것이 맞다
        assert tok in primary[team], (
            f"{team}: `{tok}` 이 정본 칸 `{primary[team]}` 에 없다 — 지어낸 매체명")


def test_리그_표기가_정본_첫_칸에_있다():
    """🔴 리그 단위 행의 `league:` 는 정본 첫 칸이 **이름으로 댄** 리그다."""
    for team, row in queries.lineup_teams().items():
        name = (row.get("league") or "").strip()
        if name:
            assert name in team, f"{team} 행의 league={name!r} 이 정본 칸에 없다"


def test_공개_시각이_정본_머리글과_같다():
    """§13-b 머리글: *"경기 1시간 전 공개 → 이후 5분 간격 재시도."*"""
    head = _section("**13-b 확정 라인업 1차 소스", "| 팀 |")
    assert "1시간 전" in head
    assert queries.lineup_opens_before_min() == 60


def test_금지된_라인업_소스가_표에_없다():
    """🔴 §13-a: *"스포츠나비 경기 페이지(JS)·baseball-data 스타멘 표(하루 지연)·
    야후 뉴스 본문(robots 거부)은 라인업 소스로 쓰지 않는다."*

    ⚠️ 그 셋이 검색 결과에 **나오는 것**은 막을 수 없지만(실측 2026-09-27:
       baseball-data 가 1위로 나왔다), 우리가 **소스로 지목**하면 안 된다.
    """
    blob = str(queries.lineup_teams())
    for bad in ("baseball-data", "スポーツナビ", "스포츠나비", "news.yahoo"):
        assert bad not in blob, f"§13-a 가 금지한 라인업 소스가 표에 있다: {bad}"


# ══════════════════════════════════════════════════════════════════
# 표 조회
# ══════════════════════════════════════════════════════════════════

def test_금지_라인업_소스가_정본_문장에서_왔다():
    """🔴 **금지 목록을 지어내지 않는다.** §13-a 가 이름으로 댄 것만이다.

    §13-a 원문: *"스포츠나비 경기 페이지(JS)·baseball-data 스타멘 표(하루 지연)·
    야후 뉴스 본문(robots 거부)은 라인업 소스로 쓰지 않는다."*
    """
    head = APPENDIX.split("## 13. 리그별 소스 지도")[1].split("**13-b")[0]
    rows = queries.banned_for_lineup()
    assert rows, "금지 목록이 비었다"
    for row in rows:
        origin = row["origin"]
        assert origin in head, (
            f"`{origin}` 이 §13-a 문장에 없다 — 지어낸 금지 목록이다")
        assert row.get("hosts"), f"{origin} 의 실제 도메인이 없다"
    # 🔴 정본이 셋을 댔다 — 수를 대조한다(하나를 빠뜨리면 조용히 통과한다)
    assert len(rows) == 3, f"§13-a 는 셋을 금지한다 (yaml 에 {len(rows)}건)"
    # 🔴 도메인이 실제로 막히는지는 아래 계약이 URL 로 확인한다




# ══════════════════════════════════════════════════════════════════
# 🔴🔴 검색 언어는 **리그가 아니라 팀**에 맞춘다 (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════


def test_검색어가_팀_언어로_만들어진다():
    """🔴 고른 언어가 **실제 검색어에 쓰이나** — 고르고 안 쓰면 아무 일도 안 한다."""
    from datetime import date

    from app import queries as Q

    got = Q.variants(team="South Korea", league="Asian Games",
                     day=date(2026, 10, 2), what="라인업")
    langs = {v.lang for v in got}
    assert "ko" in langs, sorted(langs)
    # 🔴 미국 팀에는 한국어가 안 붙는다
    us = Q.variants(team="Las Vegas Lights FC", league="USL Championship",
                    day=date(2026, 10, 2), what="lineup")
    assert "ko" not in {v.lang for v in us}


