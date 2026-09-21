"""SCT-3 — 위성 검색 개편 (Part 2). SCT-2 를 **대체**한다.

오늘 페이블이 실제로 정보를 가져온 방식을 이식한다:
**리그별 현지어 검색어 → 제목·날짜·신선도로 걸러 → 구단·지역 매체 우선 →
결장·XI·직전 3경기만 추출.**

🔴 층1 위성(다음 뉴스검색)의 `_SOCCER_TERMS = ""` 는 건드리지 않는다.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import scout_config as SC

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def _h(title, url, published=None):
    d = {"title": title, "url": url}
    if published is not None:
        d["published"] = published
    return d


# ── 2단계 검색어

def test_단계가_둘이다():
    for lg, stages in SC.SEARCH_TERMS.items():
        assert set(stages) == {"pre", "lineup"}, (lg, stages)


def test_지시문_현지어_그대로다():
    """⚠️ [SCT-8 2026-09-14 사용자 지시] 유럽 리그는 **두 벌**이 됐다 —
    대진 질의(`{home} {away}`)가 기사 매칭용, 팀 질의(`{team} … 오늘`)가
    결장 뉴스용이다. 실측이 바꿨다: 팀 질의만 쓰면 구글이 과거 전체를
    매칭해 80건 중 48시간 안이 **0건**이었다.
    ⚠️ 야구·아시아 리그는 **팀 질의 그대로**다(현지 매체가 팀 단위로 쓴다).
    """
    assert SC.queries("la_liga", None, "pre", home="Celta Vigo", away="Málaga") == [
        "Celta Vigo Málaga alineaciones probables"]
    assert SC.queries("la_liga", "Celta Vigo", "pre") == ["Celta Vigo bajas hoy"]
    assert SC.queries("la_liga", None, "lineup", home="Celta Vigo",
                      away="Málaga") == ["Celta Vigo Málaga alineación oficial"]
    assert SC.queries("serie_a", None, "pre", home="Lecce", away="Monza") == [
        "Lecce Monza probabili formazioni"]
    assert SC.queries("kbo", "KT Wiz", "pre") == [
        "KT Wiz 내일의 선발투수", "KT Wiz 엔트리 말소"]


def test_팀_질의에는_신선도_토큰이_붙는다():
    """🔴 사용자 지시 — 토큰이 없으면 구글이 과거 전체를 매칭한다(실측)."""
    tokens = set(SC.TODAY_WORDS) | {"aujourd'hui", "heute", "vandaag"}
    for lg in ("epl", "la_liga", "serie_a", "bundesliga", "ligue1", "eredivisie"):
        team_q = SC.queries(lg, "X", "pre")
        assert team_q, lg
        assert any(t in q.lower() for q in team_q for t in tokens), (lg, team_q)


def test_채울_수_없는_자리표시자는_그_줄을_뺀다():
    """🔴 빈 문자열로 채우면 반쪽 질의가 나가고, 그게 다시 과거 전체를 긁는다."""
    assert SC.queries("serie_a", None, "pre") == []          # home·away 없음
    assert SC.queries("serie_a", "Lecce", "lineup") == []     # lineup 은 대진 전용


def test_우리_리그가_전부_있다():
    """⚠️ [W3-4b 2026-09-21] **위성을 켠 리그**만이다. 기사를 긁지 않는
    리그(결과만 켠 리그)에 검색어를 둘 이유가 없다 — LGA-1 과 같은 판단."""
    from app.leagues import leagues_with

    want = set(leagues_with("satellite")) | {"mlb", "kbo", "npb"}
    assert want <= set(SC.SEARCH_TERMS), want - set(SC.SEARCH_TERMS)


def test_예산은_지시문_그대로다():
    assert SC.PER_GAME_SEARCH == 3
    assert SC.PER_GAME_FETCH == 5
    assert SC.FETCH_PER_STAGE == 3


# ── 선별 ① 제목 문

def test_팀명_토큰이_없으면_버린다():
    r = SC.screen(_h("리그 순위 총정리", "https://calciolecce.it/a"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is False and r.reason == "제목"


def test_팀명이_있으면_제목_문을_통과한다():
    r = SC.screen(_h("Lecce, out Banda e Pierotti oggi", "https://calciolecce.it/a"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is True


# ── 선별 ② 날짜 문

def test_지난_시즌_페이지는_날짜_문에서_걸린다():
    """🔴 실측: 2021·2023·2025 프리뷰가 섞여 나왔다."""
    r = SC.screen(_h("Lecce probabili formazioni 2023/24", "https://fantacalcio.it/x"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is False and r.reason == "날짜"


@pytest.mark.parametrize("word", ["oggi", "today", "오늘", "heute"])
def test_오늘_말이_있으면_통과한다(word):
    r = SC.screen(_h(f"Lecce formazioni {word}", "https://calciolecce.it/x"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is True


def test_경기_날짜가_있으면_통과한다():
    r = SC.screen(_h("Lecce vs Monza 2026-09-13 preview", "https://calciolecce.it/x"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is True


# ── 선별 ③ 신선도

def test_pre는_48시간_lineup은_3시간이다():
    assert SC.MAX_AGE_H == {"pre": 48, "lineup": 3}


def test_오래된_결과는_버린다():
    old = _h("Lecce formazioni oggi", "https://calciolecce.it/x",
             NOW - timedelta(hours=60))
    assert SC.screen(old, team="Lecce", kickoff=NOW, stage="pre",
                     now=NOW).reason == "신선도"
    fresh = _h("Lecce formazioni oggi", "https://calciolecce.it/x",
               NOW - timedelta(hours=5))
    assert SC.screen(fresh, team="Lecce", kickoff=NOW, stage="pre",
                     now=NOW).keep is True
    assert SC.screen(fresh, team="Lecce", kickoff=NOW, stage="lineup",
                     now=NOW).reason == "신선도"


def test_발행시각을_모르면_버리지_않는다():
    """⚠️ 모르는 것과 오래된 것은 다르다. 날짜 문이 이미 한 겹 막는다."""
    r = SC.screen(_h("Lecce formazioni oggi", "https://calciolecce.it/x"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is True


# ── 선별 ④ 차단·JS

@pytest.mark.parametrize("u", ["https://oddschecker.com/x",
                               "https://best-bet-tips.com/x",
                               "https://reddit.com/r/x"])
def test_차단_도메인과_조각(u):
    r = SC.screen(_h("Lecce oggi", u), team="Lecce", kickoff=NOW,
                  stage="pre", now=NOW)
    assert r.keep is False and r.reason == "차단", u


def test_js_전용은_열지_않는다():
    r = SC.screen(_h("Lecce oggi", "https://flashscore.com/x"),
                  team="Lecce", kickoff=NOW, stage="pre", now=NOW)
    assert r.keep is False and r.reason == "js_only"


# ── 정렬·확정 키워드 가중

def test_tier_순으로_정렬하고_셋만_남긴다():
    hits = [_h("Lecce oggi", "https://goal.com/1"),
            _h("Lecce oggi", "https://calciolecce.it/2"),
            _h("Lecce oggi", "https://ansa.it/3"),
            _h("Lecce oggi", "https://fantacalcio.it/4"),
            _h("Lecce oggi", "https://unknown.com/5")]
    got = SC.rank_and_pick(hits, league="serie_a", stage="pre")
    assert [h["url"].split("/")[2] for h in got] == [
        "calciolecce.it", "goal.com", "fantacalcio.it"]


def test_확정_키워드는_tier를_이긴다():
    hits = [_h("Lecce oggi", "https://calciolecce.it/1"),
            _h("Lecce formazioni ufficiali", "https://goal.com/2")]
    got = SC.rank_and_pick(hits, league="serie_a", stage="lineup")
    assert got[0]["url"].endswith("/2")


def test_확정_가중은_lineup_단계에서만_먹는다():
    hits = [_h("Lecce oggi", "https://calciolecce.it/1"),
            _h("Lecce formazioni ufficiali", "https://goal.com/2")]
    got = SC.rank_and_pick(hits, league="serie_a", stage="pre")
    assert got[0]["url"].endswith("/1")


def test_폐기_사유를_센다():
    hits = [_h("순위표", "https://goal.com/1"),
            _h("Lecce oggi", "https://oddschecker.com/2"),
            _h("Lecce 2023/24", "https://goal.com/3"),
            _h("Lecce oggi", "https://calciolecce.it/4")]
    got, discard = SC.rank_and_pick(hits, league="serie_a", stage="pre",
                                    team="Lecce", kickoff=NOW, now=NOW,
                                    with_discard=True)
    assert len(got) == 1
    assert discard == {"제목": 1, "차단": 1, "날짜": 1}


# ── 확장 추출 스키마

def test_스키마가_지시문_4_4_그대로다():
    """🔴 [HYC-1 2026-09-20 사용자 결정] `fetched_at` 을 **뺐다.**

    채우는 코드가 0건인 칸이었다 — LLM 에게 기사에서 뽑으라고 맡겼는데 기사
    본문에 "우리가 언제 수집했는지"가 있을 리 없다(실측: 운영 상자 42쪽 중
    **42쪽 빈 칸**). 수집 시각의 원본은 상자 최상위 `gathered_at` 이다.
    """
    assert set(SC.EXTRACT_SCHEMA) == {
        "team", "out", "doubt", "xi_status", "xi", "bench_notable",
        "last3", "midweek", "notes", "source", "published"}
    assert "fetched_at" not in SC.EXTRACT_SCHEMA


def test_xi_status는_둘_중_하나거나_없음이다():
    assert SC.validate({"team": "X", "xi_status": "official"})["xi_status"] == "official"
    assert SC.validate({"team": "X", "xi_status": "predicted"})["xi_status"] == "predicted"
    assert SC.validate({"team": "X", "xi_status": "아무거나"})["xi_status"] is None


def test_스키마_밖은_버린다():
    got = SC.validate({"team": "X", "전적": "5승", "감독코멘트": "이긴다",
                       "팬반응": "분노", "베팅팁": "under"})
    assert set(got) == set(SC.EXTRACT_SCHEMA)


def test_팀이_없으면_버린다():
    assert SC.validate({"out": ["A"]}) is None


def test_bench_notable은_코드가_채운다():
    """🔴 LLM 자기보고가 아니다 — 예상 XI 대비 공식 XI 에서 빠진 주전이다."""
    got = SC.bench_notable(predicted=["A", "B", "C"], official=["A", "C", "D"],
                           regulars={"A", "B", "C"})
    assert got == ["B"]


def test_주전이_아니면_bench_notable이_아니다():
    assert SC.bench_notable(predicted=["A", "B"], official=["A"],
                            regulars={"A"}) == []


# ── 충돌 처리 (4-6)

def test_충돌하면_tier_높은_쪽을_쓰고_표시한다():
    a = {"team": "X", "out": ["A", "B"], "source": "calciolecce.it"}
    b = {"team": "X", "out": ["A"], "source": "goal.com"}
    got = SC.merge([b, a], league="serie_a")
    assert got["out"] == ["A", "B"] and got["conflict"] is True


def test_같으면_충돌이_아니다():
    a = {"team": "X", "out": ["A"], "source": "calciolecce.it"}
    b = {"team": "X", "out": ["A"], "source": "goal.com"}
    assert SC.merge([a, b], league="serie_a")["conflict"] is False


def test_하나뿐이면_그대로다():
    a = {"team": "X", "out": ["A"], "source": "calciolecce.it"}
    got = SC.merge([a], league="serie_a")
    assert got["out"] == ["A"] and got["conflict"] is False
    assert SC.merge([], league="serie_a") is None
