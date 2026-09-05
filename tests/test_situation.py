"""[상황 변수 2026-09-06] 팀의 공기 — 수집·분류·격리.

🔴 이 층의 설계는 "정보는 보이되 확률은 오염되지 않는다"다. 그래서 테스트도
   **두 가지**를 본다: 잡히는가(수집), 그리고 확률로 새지 않는가(격리).
"""
from __future__ import annotations

import pytest

from app.engine import situation
from app.registry import situation_axes, situation_types


# ── 수집 ────────────────────────────────────────────────────────────
def test_ssg_retirement_pregame_article_is_captured():
    """실기사 회귀 — SSG 김성현 은퇴식 (2026-09-06 Google News 실수집분).

    🔴 **경기 전 기사만** 잡는다. 같은 은퇴식이라도 "있던 날 … 1점차 승리" 는
       어제 끝난 경기의 상보라 오늘 경기의 공기가 아니다.
    """
    pre = {"title": "'21년 원클럽맨' SSG 김성현, 은퇴식 특별 엔트리 등록…2루수 선발 출전",
           "url": "https://news.google.com/rss/articles/X",
           "source_url": "https://newsis.com/view/1"}
    post = {"title": "마음을 모아…김성현 은퇴식이 있던 날, SSG 1점차 승리 - 네이트",
            "url": "https://news.google.com/rss/articles/Y",
            "source_url": "https://m.news.nate.com/view/1"}
    tags = situation.classify([pre, post], "kbo")
    assert [t["유형"] for t in tags] == ["retirement"], tags
    assert "엔트리 등록" in tags[0]["제목"], "경기 전 기사가 아니라 상보가 잡혔다"


@pytest.mark.parametrize("title,sport", [
    ("마음을 모아…김성현 은퇴식이 있던 날, SSG 1점차 승리", "kbo"),
    ("[AI상보] 김성현 은퇴식서 김민준 호투 SSG, 두산 3-2 제압", "kbo"),
    ("SSG 전의산, 역전 스리런으로 이틀 연속 홈런…두산 5연패 추락", "kbo"),
    ("[사진]5연패 빠진 두산", "kbo"),
    ("【巨人】大城卓三が途中交代 9回には脇腹に死球", "npb"),
    ("22/7・南伊織が巨人vs中日戦の始球式に登場", "npb"),
    ("Yankees beat Red Sox 5-3", "mlb"),
])
def test_postgame_articles_are_excluded(title, sport):
    """🔴 경기 후 기사는 의미가 없다 (사용자 지시 2026-09-06).

    지나간 사건을 오늘의 공기로 오인하면 판정이 어제를 오늘로 읽는다.
    아래는 전부 **실수집분**이고, 처음 표지 19개로는 그대로 통과했다.
    """
    assert situation.is_recap(title, sport), title


@pytest.mark.parametrize("title,sport", [
    ("SSG 김강민 은퇴식, 25일 문학구장서 열린다", "kbo"),
    ("한화 김경문 감독 경질설 확산", "kbo"),
    ("巨人 監督交代 決定的", "npb"),
    ("Yankees manager fired after collapse", "mlb"),
])
def test_pregame_articles_survive(title, sport):
    """반대 위험 — 예고·공지·논란까지 걸러내면 이 층은 아무것도 못 준다."""
    assert not situation.is_recap(title, sport), title


def test_articles_published_after_start_are_dropped():
    """경기 시작 뒤에 나온 기사는 그 경기의 사전 정보가 아니다."""
    late = {"title": "감독 경질설 확산", "url": "https://x",
            "source_url": "https://yna.co.kr",
            "published": "Sun, 06 Sep 2026 12:00:00 +0000"}
    early = {**late, "published": "Sun, 06 Sep 2026 06:00:00 +0000"}
    start = "2026-09-06T09:00:00+00:00"
    assert situation.classify([early], "kbo", starts_at=start)
    assert situation.classify([late], "kbo", starts_at=start) == []


def test_missing_publish_time_is_kept():
    """시각을 모른다고 버리지 않는다 — 그 매체가 통째로 사라진다."""
    it = {"title": "감독 경질설 확산", "url": "https://x",
          "source_url": "https://yna.co.kr"}
    assert situation.classify([it], "kbo", starts_at="2026-09-06T09:00:00+00:00")


@pytest.mark.parametrize("sport,title", [
    ("kbo", "한화 김경문 감독 경질설 확산"),
    ("npb", "巨人 監督交代 決定的"),
    ("mlb", "Yankees manager fired after collapse"),
    ("soccer", "Arsenal sack head coach after board meeting"),
])
def test_works_across_every_sport(sport, title):
    """종목 분기를 코드에 두지 않는다 — registry 키워드만으로 전 종목 동작."""
    tags = situation.classify(
        [{"title": title, "url": "https://x", "source_url": "https://yna.co.kr"}],
        sport)
    assert any(t["유형"] == "manager" for t in tags), (sport, tags)


def test_recap_filter_costs_recall_and_we_know_it():
    """⚠️ **정밀도를 위해 재현율을 버렸다** — 그 사실을 테스트가 기록한다.

    "sacked after defeat" 처럼 상황 사건과 경기 결과가 한 제목에 섞이면
    상보로 걸러진다. 실측 2026-09-06: 실기사 160건 → 상황태그 4건.
    이 층의 원칙은 "놓치는 쪽이 틀리는 쪽보다 낫다" 이므로 의도한 손실이다.
    잃은 것이 너무 크다고 판단되면 `registry.RECAP_MARKERS` 를 줄인다 —
    코드가 아니라 표를 고친다.
    """
    assert situation.is_recap("Arsenal boss sacked after defeat", "soccer")
    assert situation.classify(
        [{"title": "Arsenal boss sacked after defeat", "url": "https://x",
          "source_url": "https://bbc.com"}], "soccer") == []


def test_unknown_sport_is_silent_but_not_broken():
    """모르는 종목은 빈 목록 — 수집을 멈추지도, 예외를 던지지도 않는다."""
    assert situation.classify([{"title": "감독 경질"}], "handball") == []
    assert situation_axes("handball") == {}


def test_axis_schema_is_shared_across_sports():
    """유형은 전 종목 공통이어야 ledger 가 종목을 가로질러 셀 수 있다."""
    types = set(situation_types())
    for sport in ("kbo", "npb", "mlb", "soccer"):
        assert set(situation_axes(sport)) <= types, sport


def test_ordinary_game_news_is_not_tagged():
    """반대 위험 — 평범한 경기 기사를 상황으로 읽으면 신호가 잡음이 된다."""
    items = [{"title": "두산 선발 곽빈 6이닝 무실점 호투", "url": "https://x",
              "source_url": "https://osen.co.kr"}]
    assert situation.classify(items, "kbo") == []


# ── 출처 신뢰도 ─────────────────────────────────────────────────────
def test_aggregator_link_does_not_decide_trust():
    """🔴 Google News 링크로 판단하면 **전건이 [미확인]** 이 된다(실측)."""
    it = {"title": "은퇴식 개최", "url": "https://news.google.com/rss/articles/X",
          "source_url": "https://sportschosun.com/a/1", "source": "스포츠조선"}
    assert situation.source_of(it) == "sportschosun.com"
    assert situation.classify([it], "kbo")[0]["확인"] == "공식"


def test_blog_source_is_unverified():
    it = {"title": "감독 경질설", "url": "https://news.google.com/rss/articles/X",
          "source_url": "https://blog.naver.com/x"}
    t = situation.classify([it], "kbo")[0]
    assert t["확인"] == "미확인"
    assert situation.UNVERIFIED in t["라벨"]


def test_unknown_source_defaults_to_unverified():
    """모르면 미확인이다 — 모호할 때 안전한 쪽으로 넘어져야 한다."""
    it = {"title": "은퇴식", "url": "https://news.google.com/rss/articles/X"}
    assert situation.classify([it], "kbo")[0]["확인"] == "미확인"


# ── 격리: 확률로 새지 않는가 ────────────────────────────────────────
def test_prompt_binds_situation_to_conservative_reflection():
    """프롬프트가 상한·0 규칙을 실제로 걸고 있는가."""
    from app.engine.prompts import MATCHUP

    assert "[상황]" in MATCHUP
    assert "±1.0%p" in MATCHUP
    assert "%p 0 고정" in MATCHUP        # [미확인] 항목
    assert "%p 0으로 기재만" in MATCHUP   # 방향 불명


def test_situation_tags_reach_material2_with_source():
    """자료2 에 출처가 함께 실려야 판정이 신뢰도를 볼 수 있다."""
    from app.engine.matchup import news_payload

    jg = {"situation_tags": {"home": [
        {"라벨": "[상황]", "유형": "retirement", "제목": "은퇴식",
         "출처": "sportschosun.com", "확인": "공식"}]}}
    out = news_payload({"뉴스태그": []}, {}, jg)
    tag = out["home"][0]
    assert tag["tag"] == "[상황] retirement"
    assert "sportschosun.com" in tag["근거"]
    assert tag["dir"] == "=", "방향은 판정이 정한다 — 수집기가 정하지 않는다"


def test_no_summary_is_stored():
    """요약문을 만들지 않는다 — 요약하면 그 요약이 판정 재료가 된다."""
    it = {"title": "김성현 은퇴식", "url": "https://x", "source_url": "https://yna.co.kr"}
    t = situation.classify([it], "kbo")[0]
    assert t["제목"] == "김성현 은퇴식"          # 원문 그대로
    assert set(t) == {"유형", "라벨", "제목", "url", "출처", "확인"}


# ── 침묵 금지 ───────────────────────────────────────────────────────
def test_attach_logs_even_when_nothing_found(caplog):
    """붙은 게 없어도 로그 한 줄 — '안 붙었다'와 '볼 게 없었다'는 다르다."""
    import logging

    jg = {"sport": "kbo", "game_id": 1, "research": {}}
    with caplog.at_level(logging.INFO):
        assert situation.attach(jg) == 0
    assert any("[situation]" in r.message for r in caplog.records)


def test_situation_query_has_no_hardcoded_site():
    """소스는 registry·쿼리로만 — 특정 사이트를 박지 않는다."""
    from app.collectors.news_rss import situation_query

    q = situation_query("kbo", "SSG Landers")
    assert q and "site:" not in q and "http" not in q
    assert situation_query("handball", "X") == ""


# ── Gemini 검색 그라운딩 ────────────────────────────────────────────
def test_grounding_query_is_sport_driven_and_site_free():
    from app.collectors.grounding import build_query

    q = build_query("kbo", "SSG Landers")
    assert "은퇴식" in q and "검색" in q
    assert "site:" not in q and "http" not in q
    assert build_query("handball", "X") == ""


def test_grounding_drops_non_news_hosts():
    """백과·정적 문서는 오늘의 공기가 아니다."""
    from app.collectors import grounding

    assert any("namu.wiki" in h for h in grounding._NON_NEWS_HOSTS)
    assert any("wikipedia.org" in h for h in grounding._NON_NEWS_HOSTS)


def test_grounding_reads_publish_time_from_page():
    """🔴 그라운딩 결과에는 발행일이 없다 — 페이지에서 직접 읽어야
       지난 시즌 기사가 오늘 태그로 붙지 않는다(실측 2026-09-06)."""
    from app.collectors.grounding import _published_at

    assert _published_at(
        '<meta property="article:published_time" content="2026-09-06T10:00:00+09:00">')
    assert _published_at('{"datePublished":"2026-09-05T22:00:00Z"}')
    assert _published_at("<html>없음</html>") is None


def test_grounding_unescapes_entities():
    """`&quot;` 가 남으면 키워드 매칭이 어긋난다."""
    from app.collectors.grounding import _unescape

    assert _unescape("&quot;세상에&quot;") == '"세상에"'


def test_grounding_needs_redis_to_count_cap():
    """캡 없는 AI 호출을 만들지 않는다 — 셀 수 없으면 부르지 않는다."""
    import asyncio

    from app.collectors.grounding import _cap_ok, _once_ok

    assert asyncio.run(_cap_ok(None, "2026-09-06")) is False
    assert asyncio.run(_once_ok(None, "kbo", 1, "2026-09-06")) is False


def test_grounding_merge_does_not_erase_rss():
    """덧붙이지 덮지 않는다."""
    from app.collectors.grounding import merge_into_research

    research = {"home_news": [{"title": "RSS 기사", "url": "https://a"}]}
    merge_into_research(research, {"home": [{"title": "그라운딩 기사",
                                             "url": "https://b"}]})
    titles = [x["title"] for x in research["home_news"]]
    assert "RSS 기사" in titles and "그라운딩 기사" in titles


def test_prompt_forbids_remembered_team_names():
    """🔴 판정이 기억 속 연고지를 갖다 붙였다 (실측 2026-09-06).

    카드 근거에 "원정 오클랜드" 가 실렸다. statsapi 공식 표기는 `Athletics`,
    연고지 `Sacramento`, 구장 `Sutter Health Park` 다 — 오클랜드가 아니다.
    우리 자료는 전부 맞았고 **모델이 자기 기억을 끌어왔다.**
    """
    from app.engine.prompts import MATCHUP

    assert "자료에 적힌 표기를 그대로" in MATCHUP
    assert "Athletics" in MATCHUP


# ── x_search 발동 조건 ──────────────────────────────────────────────
def test_xsearch_fires_for_situation_on_every_sport():
    """🔴 종전 조건은 라인업 정찰용이라 MLB·KBO 에서 영영 안 걸렸다.

    운영 실측 2026-09-06: 1회 표식이 NPB 4건 · MLB 0 · KBO 0 이었다.
      MLB RSS 21~23 · 라인업 confirmed(3시간 전 공시) → 두 조건 다 미달
      KBO RSS 23~27 · 판별 시점이 T-90분 밖          → 두 조건 다 미달
    X 의 값어치는 라인업이 아니라 **현장 속보**다.
    """
    from app.collectors.xsearch import should_fire
    from app.config import get_settings

    s = get_settings()
    assert s.scout_xsearch_situation is True
    for rss, lu, mins in ((23, "confirmed", -16),   # MLB 실측 형태
                          (24, "none", 519),        # KBO 실측 형태
                          (22, "none", 459)):       # NPB 실측 형태
        fire, why = should_fire(rss, lu, mins, s)
        assert fire, (rss, lu, mins, why)
        assert "상황" in why


def test_xsearch_situation_switch_can_be_turned_off():
    """끄면 종전 조건으로 돌아간다 — 되돌릴 수 있어야 한다."""
    from app.collectors.xsearch import should_fire

    class Off:
        scout_xsearch_situation = False
        scout_xsearch_rss_floor = 5
        scout_xsearch_lineup_min = 90.0

    assert should_fire(23, "confirmed", -16, Off())[0] is False
    assert should_fire(2, "confirmed", -16, Off())[0] is True     # RSS 하한
    assert should_fire(23, "none", 30, Off())[0] is True          # 라인업 창


def test_xsearch_prompt_leads_with_situation_and_excludes_recaps():
    from app.collectors.xsearch import PROMPT

    assert "팀의 공기" in PROMPT
    assert "경기 전 것만" in PROMPT
    assert "결과 회고" in PROMPT


# ── [2026-09-06] x_search 가 가져온 것이 판정에 도달하는가 ──────────
@pytest.mark.parametrize("title,kind", [
    # 전부 운영 x_search 실수집분(2026-09-06 MLB).
    ("Athletics roster moves announced", "roster_move"),
    ("Dodgers notes: Bobby Miller activated, Wrobleski bulk role", "roster_move"),
    ("Dodgers activate Bobby Miller from IL, option Kyle Hurt, DFA Alek Thomas",
     "roster_move"),
])
def test_club_account_roster_wording_is_caught(title, kind):
    """🔴 구단 공식 계정이 쓰는 말을 못 잡았다.

    `@Athletics` 의 "roster moves announced" 가 0건이었고, 같은 유형인 다저스
    건은 "option Kyle Hurt" 의 `option` 이 **우연히** 걸려서 잡혔다.
    운에 기대는 수집은 수집이 아니다.
    """
    tags = situation.classify(
        [{"title": title, "url": "https://x.com/a/1",
          "source_url": "https://x.com"}], "mlb")
    assert any(t["유형"] == kind for t in tags), (title, tags)


def test_game_recap_is_still_not_a_roster_move():
    """반대 위험 — 경기 결과에 'beat' 가 있다고 로스터로 읽으면 안 된다."""
    assert situation.classify(
        [{"title": "Mariners beat Athletics 7-6", "url": "https://x",
          "source_url": "https://espn.com"}], "mlb") == []


@pytest.mark.asyncio
async def test_new_articles_invalidate_the_form_cache():
    """🔴 팀 폼이 캐시라 x_search 가 넣은 새 기사를 읽지 못했다(실측).

    자료2 뉴스태그 경로가 통째로 끊겨 있었다 — `Athletics roster moves
    announced` 가 판정 프롬프트에 없었다. 새 기사가 들어온 팀만 지운다.
    """
    from app.collectors.news_rss import invalidate_form_cache
    from app.engine.team_form import form_key

    deleted = []

    class _R:
        async def delete(self, key):
            deleted.append(key)
            return 1

    jg = {"sport": "mlb", "game_id": 1, "home": "Seattle Mariners",
          "away": "Athletics", "_form_date": "2026-09-05"}
    n = await invalidate_form_cache(_R(), jg, ["away"])
    assert n == 1
    assert deleted == [form_key("mlb", "Athletics", "2026-09-05")]

    # 새 기사가 없으면 아무것도 지우지 않는다 — 매번 지우면 캐시가 없는 것과 같다.
    deleted.clear()
    assert await invalidate_form_cache(_R(), jg, []) == 0
    assert deleted == []
