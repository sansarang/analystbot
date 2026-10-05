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
from app.collect import npb

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

def test_NPB_12팀이_전부_행을_찾는다():
    """🔴 수집기의 팀명은 **일본어 정식명**이고 §13-b 키는 **한국어**다.

    ⚠️ 실측 2026-09-30: 종전 `lineup_for` 는 팀 이름만 봐서 12팀 중 **6팀이
       §13-b 행을 하나도 못 찾았다**(ヤクルト·日本ハム·オリックス·楽天·西武·ロッテ).
       그러면 그 팀들은 §13-b 검색어를 영영 못 받는다.
    🔴 대응표를 만들지 않는다 — `npb.TEAMS`(약칭↔정식명)가 이미 원본이고,
       호출부가 그것으로 `local` 을 넘긴다.
    """
    short = {full: s for s, full in npb.TEAMS.items()}
    miss = [full for full in npb.TEAMS.values()
            if queries.lineup_for(full, "NPB", short[full]) is None]
    assert miss == [], f"§13-b 행을 못 찾는 NPB 팀: {miss}"


def test_팀_전용_행이_리그_행을_이긴다():
    """🔴 소프트뱅크는 넓은 행이 아니라 **자기 행**(西スポ)을 써야 한다."""
    row = queries.lineup_for("福岡ソフトバンクホークス", "NPB", "ソフトバンク")
    assert row and row.get("media_token") == "西スポ"


def test_리그_단위_행이_잡힌다():
    """§19-g 5·6번이 쓰는 행이다 — MLB·K리그는 팀별 행이 없다."""
    assert queries.lineup_for("Houston Astros", "MLB") is not None
    assert queries.lineup_for("인천", "K리그1") is not None
    # 🔴 모르는 리그는 `None` — 아무 행이나 돌려주면 남의 검색어로 던진다(M14)
    assert queries.lineup_for("아무팀", "없는리그") is None


# ══════════════════════════════════════════════════════════════════
# §19-b-5 네 축
# ══════════════════════════════════════════════════════════════════

def test_같은_검색어를_두_번_넣지_않는다():
    """🔴 §19-b-5 — *"같은 검색어 반복 금지."*"""
    vs = queries.variants(team="福岡ソフトバンクホークス", league="NPB", day=DAY,
                          what="スタメン", local="ソフトバンク")
    texts = [v.text for v in vs]
    assert len(texts) == len(set(texts)), texts


def test_네_축이_전부_나온다():
    """🔴 축 하나가 빠지면 §19-b-5 의 *"바꿔서 다시"* 가 반쪽이 된다."""
    vs = queries.variants(team="福岡ソフトバンクホークス", league="NPB", day=DAY,
                          what="スタメン", local="ソフトバンク")
    axes = {v.axis for v in vs}
    assert "§13-b" in axes, "표의 검색어가 1번이 아니다"
    assert any(a.startswith("표기") for a in axes), "표기 변형이 없다"
    assert "매체명" in axes, "매체명 변형이 없다"
    assert "시점:전날" in axes, "시점 변형이 없다"


def test_현지어_변형이_팀명까지_바꾼다():
    """🔴 실측 2026-09-30: 언어 변형이 `소프트뱅크 スタメン 9月27日` 를 냈다 —
    핵심어만 일본어로 바꾸고 **팀명은 한국어로 남았다.**

    ⚠️ 일본 매체는 그 표기로 안 쓰므로 그 검색은 **구조적으로 0건**이다.
       §19-b-5 의 "언어" 축은 질문 **전체**를 현지어로 바꾸는 것이다.

    🔴 **`in` 으로 보면 안 된다.** 절제 2026-09-30: `who = team` 으로 되돌렸더니
       현지어 변형이 `広島東洋カープ スタメン …` 가 됐고 `"広島" in t` 는 **참**이라
       계약이 통과했다. 정식명이 현지 약칭을 **부분문자열로 품기** 때문이다 —
       이 저장소가 반복해 만든 병(문자열 검사)의 또 다른 얼굴이다.
       → **낱말 단위로 정확히** 대조한다.
    """
    vs = queries.variants(team="広島東洋カープ", league="NPB", day=DAY,
                          what="スタメン", local="広島")
    ja = [v for v in vs if v.lang == "ja"]
    assert ja, "일본어 변형이 없다"
    for v in ja:
        head = v.text.split()[0]
        assert head == "広島", (
            f"현지어 변형의 팀명이 현지 표기가 아니다: {head!r} (전체 {v.text!r})")


def test_현지어_변형이_모든_리그에서_현지명을_쓴다():
    """🔴 축 하나를 리그 하나로만 검사하면 다른 리그에서 조용히 깨진다."""
    for team, league, local, what in (
            ("福岡ソフトバンクホークス", "NPB", "ソフトバンク", "スタメン"),
            ("広島東洋カープ", "NPB", "広島", "スタメン"),
            ("千葉ロッテマリーンズ", "NPB", "ロッテ", "スタメン")):
        vs = queries.variants(team=team, league=league, day=DAY, what=what,
                              local=local)
        native = [v for v in vs if v.lang == "ja"]
        assert native, (team, "일본어 변형이 없다")
        for v in native:
            assert v.text.split()[0] == local, (team, v.text)


def test_연도를_붙이지_않는다():
    """🔴 §12-b — 연도를 붙이면 **지난 시즌 기사**가 섞인다.

    🔴 **모든 언어 표기를 검사한다.** 절제 2026-09-30: `zh` 갈래에만 연도를
       넣었더니 계약이 통과했다 — CPBL 을 안 넣어 둬서다. 갈래가 다섯이면 다섯을
       다 본다(손으로 셋만 적으면 넷째가 조용히 깨진다).
    """
    # 🔴 `month_day`·`day_only` 의 **모든 언어**를 원본에서 가져온다
    langs = sorted({lg for v in queries.LANGS.values() for lg in v}
                   | set(queries.DEFAULT_LANGS))
    assert {"ko", "ja", "en", "zh"} <= set(langs), langs
    for lang in langs:
        for fn in (queries.month_day, queries.day_only):
            got = fn(DAY, lang)
            assert str(DAY.year) not in got, (lang, fn.__name__, got)

    for league, what in (("NPB", "スタメン"), ("MLB", "lineup"),
                         ("K리그1", "선발 명단"), ("KBO", "선발 라인업"),
                         ("CPBL", "先發打序")):
        vs = queries.variants(team="팀", league=league, day=DAY, what=what)
        assert vs, (league, "변형이 0건이다")
        for v in vs:
            for year in ("2024", "2025", "2026", "2027"):
                assert year not in v.text, (league, v.text)


def test_규칙_변형도_12b로_걸러진다():
    """🔴 L5 출력만 거르면 안 된다 — 긴 팀명·표 검색어가 6낱말을 넘길 수 있다.

    ⚠️ 0건은 "없음"이 아니라 unknown 이고(§7-5e), 그 사유가 남아야 한다.
    """
    long_team = "아주 아주 아주 아주 긴 팀 이름"
    vs = queries.variants(team=long_team, league="KBO", day=DAY,
                          what="선발 라인업")
    kept, dropped = queries.admissible(vs)
    assert dropped, "6낱말을 넘는 검색어가 그대로 통과했다"
    assert all("§12-b" in d for d in dropped)
    for v in kept:
        assert llm.query_ok(v.text)


def test_못_채운_자리표를_그대로_던지지_않는다():
    """⚠️ `{球場}` 를 그대로 던지면 중괄호가 검색어에 들어가 0건이 된다."""
    vs = queries.variants(team="広島東洋カープ", league="NPB", day=DAY,
                          what="スタメン", local="広島")
    for v in vs:
        assert "{" not in v.text and "}" not in v.text, v.text


def test_L5_변형은_query_ok를_통과한_것만_쓴다():
    """🔴 §19-b-5 — *"변형 생성은 L5(LLM)이 하되 §12-b 규칙 정규식으로 걸러서."*

    ⚠️ 실측 2026-09-30: qwen3:8b 가 `ohito runners`·`阪神タイガース ランナップ`
       같은 **엉망 검색어**를 냈다. §12-b 는 문법만 보므로 이런 것은 통과한다 —
       그래서 0건이 나고, 그 0건이 사유와 함께 남는 것이 지금 할 수 있는 최선이다.
       🔴 문법 위반(연도·따옴표·site:)은 **반드시** 걸러져야 한다.
    """
    import asyncio

    calls: list[dict] = []

    async def _fake_call(prompt, schema, **k):
        return {"queries": [
            {"lang": "en", "text": "astros starting pitcher"},   # 통과
            {"lang": "en", "text": "astros 2026 pitcher"},       # 연도 → 버림
            {"lang": "en", "text": 'site:mlb.com astros'},       # site: → 버림
            {"lang": "en", "text": '"astros" pitcher'},          # 따옴표 → 버림
            {"lang": "en", "text": "a b c d e f g"},             # 7낱말 → 버림
        ]}

    class _Pool:
        async def execute(self, *a, **k):
            calls.append({"sql": a[0], "args": a[1:]})

    import app.queries as Q
    orig = Q.llm.call
    Q.llm.call = _fake_call
    try:
        kept, dropped = asyncio.run(
            Q.from_llm("휴스턴 선발 확정?", league="MLB", pool=_Pool()))
    finally:
        Q.llm.call = orig

    assert [v.text for v in kept] == ["astros starting pitcher"]
    assert len(dropped) == 4, dropped
    # 🔴 §17-g-4 — 버린 것을 `extraction_rejected` 에 남긴다
    assert len(calls) == 4, "버린 L5 출력이 기록되지 않았다"
    assert all("extraction_rejected" in c["sql"] for c in calls)


def test_L5가_없어도_수집이_멈추지_않는다():
    """🔴 Ollama 가 없으면 `unknown` + 사유다 — 예외로 사이클을 죽이지 않는다."""
    import asyncio

    async def _boom(*a, **k):
        raise llm.LLMUnavailable("Ollama 에 닿지 못했다")

    import app.queries as Q
    orig = Q.llm.call
    Q.llm.call = _boom
    try:
        kept, dropped = asyncio.run(Q.from_llm("x", league="MLB"))
    finally:
        Q.llm.call = orig
    assert kept == []
    assert dropped and "L5 호출 실패" in dropped[0]


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


def test_금지_소스_URL을_거부한다():
    """🔴 **표에 안 넣는 것만으로는 부족하다** — 그 셋은 검색 1순위로 나온다.

    ⚠️ 실측 2026-09-30(단계 4): 세이부 라인업 세포가
       `baseball-data.com/lineup/l.html` 을 **실제로 열었고**, 그 표는 하루 지연이라
       겐다가 선발로 들어 있었다 — §19-g-5 의 사실(겐다 **벤치**)과 반대다.
    """
    from app import searchcells
    for bad in ("https://baseball-data.com/lineup/l.html",
                "https://news.yahoo.co.jp/articles/abc",
                "https://baseball.yahoo.co.jp/npb/game/x"):
        why = searchcells.deny_lineup_source(bad)
        assert why and "§13-a" in why, (bad, why)
    # 🔴 허용되는 곳은 통과시킨다 — 전부 막으면 라인업 세포가 무력해진다
    for ok in ("https://lions-matome.com/archives/x.html",
               "https://www.nishispo.jp/x", "https://www.carp.co.jp/"):
        assert searchcells.deny_lineup_source(ok) is None, ok


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 검색 언어는 **리그가 아니라 팀**에 맞춘다 (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════


def test_언어를_팀으로_고른다():
    """🔴🔴 **라이브가 내 결정을 깨뜨렸다.**

    실측 2026-10-01(USL): 기본이 한국어라 미국 팀을 한국어로 찾았다 → zhihu 홍수.
      그래서 기본을 **영어**로 바꿨다.
    🔴 실측 2026-10-02(아시안게임 한국 vs 중국): 그 영어 기본이 **한국 대표팀을
      깨뜨렸다** — 사실 0건인데 맞대결·휴식·감독 발언이 **한국어 매체에 다 있었다.**

    ⚠️ 리그로는 못 담는다 — 대표팀 경기는 **상대에 따라** 언어가 달라진다.
    """
    from app import queries as Q

    ko, why = Q.langs_for("Asian Games", "South Korea")
    # 🔴🔴 **영어가 맨 앞이다**(사용자 지시 2026-10-02):
    #    *"공통으로 영어 그다음은 그나라 현지어"* — 영어가 공통이라 예산을 먼저 쓴다
    assert ko[0] == "en", ko
    assert "ko" in ko, (ko, why)
    assert "현지어" in why
    zh, _ = Q.langs_for("Asian Games", "China")
    assert zh[0] == "en" and "zh" in zh, zh
    # 🔴 **같은 리그인데 팀마다 다르다** — 리그 칸 하나로는 못 담는다는 증거다
    assert ko != zh

    # 🔴 팀 선언이 없으면 **리그**로 간다(기존 표가 원본이다) — 그래도 영어가 먼저다
    ja, why2 = Q.langs_for("NPB", "없는팀")
    assert ja[0] == "en" and set(ja) == set(Q.LANGS["NPB"]), (ja, Q.LANGS["NPB"])
    assert "리그" in why2
    # 🔴 yaml 에 `en` 을 적지 않는다 — 적으면 순서가 갈린다
    from app import rules
    table = rules._load(Q.SEARCH_LANGS)["teams"]
    assert not [k for k, v in table.items() if "en" in v], \
        f"현지어 표에 en 이 적혀 있다: {[k for k, v in table.items() if 'en' in v]}"

    # 🔴 둘 다 없으면 기본이고 **그 위험을 사유에 적는다**
    bare, why3 = Q.langs_for("", "없는팀")
    assert bare == Q.DEFAULT_LANGS
    assert "못 찾는다" in why3, why3

    # ⚠️ 미국 팀은 **여전히 영어다** — 전 결함을 되돌리지 않았다
    us, _ = Q.langs_for("USL Championship", "Las Vegas Lights FC")
    assert us == ("en",), us


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


def test_현지_약칭은_현지어_질의에_붙는다():
    """🔴🔴 **순서를 바꾸자 드러난 결함이다**(사용자 지시 2026-10-02).

    전 판 코드는 `lang == langs[0]`(첫 언어)일 때 현지 약칭을 썼다. 그때는 첫 언어가
    곧 현지어였으니 **우연히** 맞았다. *"공통으로 영어 그다음 현지어"* 로 바꾸자
    영어 변형에 `広島`, 일본어 변형에 `広島東洋カープ` 가 붙었다 — **거꾸로다.**

    🔴 현지 약칭은 **그 나라 매체가 쓰는 표기**다. 그 나라 언어 질의에 붙어야 한다.
    """
    vs = queries.variants(team="広島東洋カープ", league="NPB", day=DAY,
                          what="スタメン", local="広島")
    # 🔴 일본어 변형은 **약칭**을 쓴다
    for v in [x for x in vs if x.lang == "ja"]:
        assert v.text.split()[0] == "広島", v.text
    # 🔴 영어 변형은 **정식명**을 쓴다 — 영어 매체는 약칭을 안 쓴다
    en = [x for x in vs if x.lang == "en" and x.axis.startswith("lang:")]
    assert en and en[0].text.split()[0] == "広島東洋カープ", en[0].text if en else None
    # 🔴 그리고 **영어가 먼저 나온다**(§13-b 표 축은 예외 — 실측이 정한 1번이다)
    order = [v.lang for v in vs if v.axis.startswith("lang:")]
    assert order[0] == "en", order
