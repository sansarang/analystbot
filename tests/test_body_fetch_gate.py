"""URL-1 — 열기 전에 제목을 본다. 본문 fetch 낭비를 막는다.

사용자 지시 2026-09-13: "1번만 해라" (검색 결과에서 **어느 URL을 열지** 고르기)

🔴 **실측 2026-09-13 (운영, 몬차@레체).** 위성 26건 중 채택 2건. 버려진 24건:
     "도미 당근 레체 데 티그레 & 김치"       (프랑스 요리)
     "아르헨티나 초코파이 둘세 데 레체 1400kg"
     "몬차 서킷 F1 그랑프리 키미 안토넬리 우승"
   `레체`·`몬차`가 한국어로 음식·F1 서킷과 같은 말이라 검색이 물어왔고,
   우리는 **24건 전부 본문까지 열었다**. 경기당 12회 × 12경기 = 144회.

🔴 문은 이미 있다 — `_mentions_team` (SAT-12, KBO 전용). **KBO 에만 걸려 있다.**
   NPB·축구·토르 보강은 제목을 보지 않고 전부 연다. 그 문을 나머지에도 건다.

⚠️ **반대 위험(정상 폐기)** 을 함께 잰다. 버린 건수를 로그로 남긴다 —
   SAT-12 가 "오염률 14%만 걸러내는 것이 목적"이라고 적어 둔 그대로다.
"""
import inspect

import pytest

from app.collectors import satellite as SAT


def test_제목에_팀이_없으면_본문을_열지_않는다():
    """🔴 토르 보강이 제목을 안 보고 전부 열었다."""
    src = inspect.getsource(SAT._tor_supplement)
    i = src.index("_fetch_article_body")
    assert "_title_hits" in src[:i], "본문 fetch 앞에 제목 문이 없다"


@pytest.mark.asyncio
async def test_토르_보강이_무관_기사를_버린다(monkeypatch, caplog):
    import logging

    async def _search(q):
        return [{"title": "Seattle Mariners injury update", "url": "http://a/1"},
                {"title": "Louis Vuitton Dolomites Classic Run", "url": "http://a/2"}]

    opened = []

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr("app.collectors.tor_search.search", _search)
    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    from app.config import get_settings
    monkeypatch.setattr(SAT, "get_settings", get_settings, raising=False)

    jg = {"home": "Seattle Mariners", "away": "Arizona Diamondbacks"}
    with caplog.at_level(logging.INFO):
        out = await SAT._tor_supplement(jg, [("Seattle Mariners", "q")])
    assert opened == ["http://a/1"], opened
    assert len(out) == 1, out
    # 🔴 조용히 버리지 않는다 — 반대 위험을 재려면 건수가 남아야 한다
    assert "제목" in caplog.text or "폐기" in caplog.text, caplog.text


def test_팀_이름_일부만_같아도_인정한다():
    """⚠️ 반대 위험 — 기사는 'Mariners', '매리너스' 처럼 줄여 쓴다."""
    assert SAT._title_hits("Mariners bullpen news", "Seattle Mariners")
    assert SAT._title_hits("Diamondbacks lineup", "Arizona Diamondbacks")
    assert not SAT._title_hits("Louis Vuitton Dolomites Run", "Seattle Mariners")


def test_제목이_없으면_버리지_않는다():
    """⚠️ 제목이 비었다고 폐기하면 정상 자료를 잃는다."""
    assert SAT._title_hits("", "Seattle Mariners")
    assert SAT._title_hits("무엇이든", "")
