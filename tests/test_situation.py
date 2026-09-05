"""[상황 변수 2026-09-06] 팀의 공기 — 수집·분류·격리.

🔴 이 층의 설계는 "정보는 보이되 확률은 오염되지 않는다"다. 그래서 테스트도
   **두 가지**를 본다: 잡히는가(수집), 그리고 확률로 새지 않는가(격리).
"""
from __future__ import annotations

import pytest

from app.engine import situation
from app.registry import situation_axes, situation_types


# ── 수집 ────────────────────────────────────────────────────────────
def test_ssg_retirement_is_captured():
    """실기사 회귀 — SSG 김성현 은퇴식 (2026-09-06 Google News 실수집분)."""
    items = [
        {"title": "마음을 모아…김성현 은퇴식이 있던 날, SSG 1점차 승리 - 네이트",
         "url": "https://news.google.com/rss/articles/X",
         "source_url": "https://m.news.nate.com/view/1"},
        {"title": "SSG 선발 김민준 6이닝 무실점",
         "url": "https://news.google.com/rss/articles/Y",
         "source_url": "https://sportschosun.com/a/2"},
    ]
    tags = situation.classify(items, "kbo")
    assert [t["유형"] for t in tags] == ["retirement"], tags
    assert "은퇴식" in tags[0]["제목"]


@pytest.mark.parametrize("sport,title", [
    ("kbo", "한화 김경문 감독 경질설 확산"),
    ("npb", "巨人 監督交代 決定的"),
    ("mlb", "Yankees manager fired after collapse"),
    ("soccer", "Arsenal boss sacked after defeat"),
])
def test_works_across_every_sport(sport, title):
    """종목 분기를 코드에 두지 않는다 — registry 키워드만으로 전 종목 동작."""
    tags = situation.classify(
        [{"title": title, "url": "https://x", "source_url": "https://yna.co.kr"}],
        sport)
    assert any(t["유형"] == "manager" for t in tags), (sport, tags)


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
