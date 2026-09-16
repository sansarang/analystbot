"""SCT-4 — 위성이 현지어 검색어·tier 선별을 실제로 쓰는가.

🔴 실측 결함 2026-09-14: `SCT-3` 이 표와 규칙을 만들었는데 **app/ 안에서
   부르는 곳이 0** 이었다. 위성은 고정 영어 꼬리말을 던지고 tier 를 보지 않았다.

⚠️ 주력 채널(다음·야후)에는 걸지 않는다 — 그 도메인은 tier 표에 없어
   `미상` 으로 전량 폐기된다(rank=9 실측). 이 배선은 DDG 경로 한 곳이다.
"""
import ast
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors import satellite as S
from app.collectors import satellite_soccer as SS
from app.engine import scout_config as SC


def test_단계는_킥오프_75분_경계로_갈린다():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    assert SS._tor_stage({"starts_at": now + timedelta(minutes=30)}, now) == "lineup"
    assert SS._tor_stage({"starts_at": now + timedelta(minutes=120)}, now) == "pre"
    # 🔴 모르면 pre 다 — lineup 으로 읽으면 신선도 상한이 3시간으로 좁아져
    #    정상 기사가 폐기된다(반대 위험).
    assert SS._tor_stage({}, now) == "pre"
    assert SS._tor_stage({"starts_at": now - timedelta(minutes=5)}, now) == "pre"


@pytest.mark.asyncio
async def test_league_을_주면_tier_순으로_열고_차단은_버린다(monkeypatch):
    opened: list[str] = []
    hits = [
        {"url": "https://calciolecce.it/a", "title": "Napoli formazioni ufficiali", "snippet": "2026"},
        # ⚠️ [PA-21 2026-09-16] 종전 예시는 v.daum.net 이었다. 실측으로 그곳이
        #    **JS 셸**임이 드러나(본문 대신 사이트 안내문 1,200자) js_only 에
        #    넣었다 — 이제 fetch 대상이 아니다. SCT-9 규칙("미상은 버리지 않고
        #    tier 4 로 통과")은 그대로이고, **예시만** 진짜 미상 도메인으로 바꾼다.
        {"url": "https://sports-earth.net/napoli", "title": "Napoli 선발",
         "snippet": "2026"},
        {"url": "https://tipico.de/wett-tipps/x", "title": "Napoli tips", "snippet": "2026"},
    ]

    async def _search(q):
        return hits

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr("app.collectors.tor_search.search", _search)
    monkeypatch.setattr(S, "_fetch_article_body", _body)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "satellite_tor_enabled", True, raising=False)

    now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    jg = {"home": "Napoli", "away": "Bologna", "starts_at": now + timedelta(minutes=30)}

    out = await S._tor_supplement(jg, [("Napoli", "q")], league="serie_a",
                                  stage="lineup", kickoff=jg["starts_at"], now=now)

    # ⚠️ [SCT-9 2026-09-14 사용자 지시] 미상(v.daum.net)은 **버리지 않고**
    #    tier 4 로 통과한다 — tier1 뒤에 붙는다. 차단(tipico)만 버린다.
    assert opened == ["https://calciolecce.it/a",
                      "https://sports-earth.net/napoli"], opened
    assert len(out) == 2


@pytest.mark.asyncio
async def test_league_이_없으면_종전_경로_그대로다(monkeypatch):
    """야구 호출부는 `league` 를 넘기지 않는다 — 동작이 바뀌면 안 된다."""
    opened: list[str] = []

    async def _search(q):
        return [{"url": "https://v.daum.net/v/1", "title": "Mariners lineup", "snippet": ""}]

    async def _body(u):
        opened.append(u)
        return "본문"

    monkeypatch.setattr("app.collectors.tor_search.search", _search)
    monkeypatch.setattr(S, "_fetch_article_body", _body)
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "satellite_tor_enabled", True, raising=False)

    out = await S._tor_supplement({"home": "Mariners", "away": "A"},
                                  [("Mariners", "q")])
    # tier 표에 없는 도메인이지만 종전 경로는 제목 문만 본다 → 연다.
    assert opened == ["https://v.daum.net/v/1"]
    assert len(out) == 1


def test_축구_위성이_검색어표와_tier_를_부른다():
    """AST — 주석·문자열이 아니라 **실제 호출**을 센다."""
    tree = ast.parse(inspect.getsource(SS))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "gather_soccer")
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    assert any(getattr(c.func, "attr", "") == "queries" for c in calls), \
        "gather_soccer 가 scout_config.queries 를 불러야 한다"
    tor = [c for c in calls if getattr(c.func, "id", "") == "_tor_supplement"]
    assert len(tor) == 1
    assert "league" in {k.arg for k in tor[0].keywords}, \
        "_tor_supplement 에 league 를 넘겨야 tier 선별이 선다"


def test_한국어_리그는_현지어_질의를_토르로_보내지_않는다():
    """🔴 `is_tor_safe_query` 가 한국어를 거부한다 — 조용히 빈손이 되면 안 된다."""
    assert SC.tor_safe("serie_a") is True
    assert SC.tor_safe("kleague1") is False
