"""[v1.1 3단계] 뉴스 근거 원문 동봉 — 태그 압축에서 죽는 "왜"를 살린다.

실측 사례: "동료들이 바즈를 옹호" 같은 정성 정보가 판정 품질을 갈랐다.
헤드라인만 넘기면 그 문장이 태그 한 글자로 압축돼 사라진다.
"""

import json

import pytest

from app.engine.prompts import MATCHUP, TEAM_FORM
from app.engine.team_form import (
    NEWS_BODY_CHARS, NEWS_BODY_MAX, with_news_bodies,
)


def test_prompt_asks_for_lead_text_not_just_title():
    assert "제목 + 리드 문단" in TEAM_FORM
    assert "수집된 원문 그대로" in TEAM_FORM
    assert "요약·의역하지 않는다" in TEAM_FORM


def test_news_cap_is_unchanged():
    """뉴스 상한 ±3%p·방향 뒤집기 금지는 이 단계에서 바뀌지 않는다."""
    assert "±3%p" in MATCHUP
    assert "뉴스만으로 뒤집을 수 없다" in MATCHUP


def test_bodies_are_attached_verbatim():
    """가공하지 않는다 — 요약하면 판정이 우리의 요약을 사실로 읽는다."""
    quotes = [{"text": "감독은 '오늘부터 이이무라가 마무리다'라고 말했다.",
               "url": "https://x/1"}]
    out = with_news_bodies(["헤드라인"], {"news_quotes": quotes})
    assert out["헤드라인"] == ["헤드라인"]
    assert out["원문"][0]["원문"] == quotes[0]["text"]
    assert out["원문"][0]["출처"] == "https://x/1"


def test_no_quotes_returns_headlines_unchanged():
    """원문이 없으면 구조를 바꾸지 않는다 — 빈 껍데기를 만들지 않는다."""
    assert with_news_bodies(["a", "b"], {}) == ["a", "b"]
    assert with_news_bodies(["a"], {"news_quotes": []}) == ["a"]


def test_bodies_are_capped_in_count_and_length():
    """원문을 통째로 실으면 프롬프트가 부풀어 정작 박스스코어가 밀린다."""
    quotes = [{"text": "가" * 500, "url": f"u{i}"} for i in range(20)]
    out = with_news_bodies(["h"], {"news_quotes": quotes})
    assert len(out["원문"]) == NEWS_BODY_MAX
    assert all(len(b["원문"]) <= NEWS_BODY_CHARS for b in out["원문"])


def test_malformed_quotes_do_not_break_the_packet():
    quotes = ["문자열", {"url": "본문없음"}, {"text": "  "}, {"text": "정상"}]
    out = with_news_bodies(["h"], {"news_quotes": quotes})
    assert [b["원문"] for b in out["원문"]] == ["정상"]


def test_news_tags_flow_whole_into_matchup():
    """뉴스 태그는 **원문 근거까지 통째로** 판정에 간다.

    [E 2026-09-02] 평가서 전체를 넘기던 것을 뉴스태그만 넘기도록 바꿨다 —
    등급('상/중/하')은 다른 모델의 해석이라 판정 입력에서 뺐다. 그래도
    뉴스는 3경기 숫자에 없는 새 정보이므로 **압축하지 않고** 넘겨야 한다.
    """
    from app.engine.matchup import news_payload

    tag = {"tag": "주축부상", "dir": "▼",
           "근거": "제목 + 리드 원문 두 문장이 그대로 들어 있다."}
    out = news_payload({"뉴스태그": [tag], "타선": {"평가": "상"}, "흐름": "상승"},
                       {"뉴스태그": []})
    assert out == {"home": [tag]}, "태그는 원문째로, 없는 쪽은 넣지 않는다"
    assert "평가" not in json.dumps(out, ensure_ascii=False)
    assert "흐름" not in json.dumps(out, ensure_ascii=False)


def test_prompt_size_increase_is_bounded():
    """증가량이 상한 안에 있어야 한다 — 측정 없이 '괜찮다'고 하지 않는다."""
    quotes = [{"text": "가" * 500, "url": "u"} for _ in range(20)]
    base = json.dumps(["h"] * 8, ensure_ascii=False)
    grown = json.dumps(with_news_bodies(["h"] * 8, {"news_quotes": quotes}),
                       ensure_ascii=False)
    added = len(grown) - len(base)
    # 인용 상한(6×220=1320자) + JSON 구조 오버헤드. 2000자를 넘으면 설계 이탈이다.
    assert added <= 2000, f"프롬프트 증가량이 상한을 넘었다: +{added}자"
