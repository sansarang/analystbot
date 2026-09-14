"""SCT-5 — 위성이 긁은 본문을 4-4 스키마로 추출한다.

🔴 실측 결함 2026-09-14: `SCT-3` 이 스키마·검증·병합을 만들었는데 **부르는
   곳이 0** 이었다. 본문은 긁어 캐시에 쌓였지만 결장·XI·최근3 이 칸으로
   서지 않아, 분석 LLM 이 "결장 없음"을 사실로 읽게 되는 자리였다.

⚠️ 실제 호출로 단언한다 — 소스 grep 이 아니다.
"""
import json

import pytest

from app.collectors import satellite as SAT
from app.engine import scout_config as SC


def _art(team, url, body="본문"):
    return {"team": team, "url": url, "body": body}


def _fake(payload):
    async def _f(routes, prompt, max_tokens, role):
        assert role == "form", "구조화 출력은 추론을 끄고 부른다"
        return json.dumps(payload, ensure_ascii=False)
    return _f


@pytest.mark.asyncio
async def test_스키마_밖은_버리고_칸만_남는다(monkeypatch):
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake({"team": "Como 1907", "out": ["Hilgers"],
                               "xi_status": "official", "notes": "중원 결장",
                               "전적": "버려야 한다", "베팅팁": "홈 승"}))

    got = await SAT.extract_facts([_art("Como 1907", "https://calciolecce.it/a")],
                                  team="Como 1907", league="serie_a")

    assert got["out"] == ["Hilgers"] and got["xi_status"] == "official"
    assert "전적" not in got and "베팅팁" not in got
    assert set(got) <= set(SC.EXTRACT_SCHEMA) | {"source", "conflict"}


@pytest.mark.asyncio
async def test_팀_칸이_없으면_버린다(monkeypatch):
    """🔴 팀을 모르는 추출은 어느 쪽 사실인지 모르는 것이다."""
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake({"out": ["X"], "xi_status": "predicted"}))

    assert await SAT.extract_facts([_art("Como 1907", "https://calciolecce.it/a")],
                                   team="Como 1907", league="serie_a") is None


@pytest.mark.asyncio
async def test_본문이_없으면_부르지_않는다(monkeypatch):
    called = []

    async def _f(*a, **k):
        called.append(1)
        return "{}"

    monkeypatch.setattr("app.engine.team_form._complete_free", _f)

    assert await SAT.extract_facts([_art("T", "https://x.it/a", body="")],
                                   team="T", league="serie_a") is None
    assert not called, "본문 없는 기사에 LLM 을 태우지 않는다"


@pytest.mark.asyncio
async def test_추출은_기사와_다른_키에_남는다():
    class _R:
        def __init__(self):
            self.kv = {}

        async def set(self, k, v, ex=None):
            self.kv[k] = v

        async def get(self, k):
            return self.kv.get(k)

    r = _R()
    await SAT._write_extract(r, "soccer", 7432, {"home": {"team": "A"}})

    assert list(r.kv) == ["scout:soccer:7432"]
    assert SAT._cache_key("soccer", 7432) not in r.kv, "기사 캐시를 덮으면 안 된다"
    back = await SAT.read_extract(r, "soccer", 7432)
    assert back["teams"]["home"]["team"] == "A"
    assert await SAT.read_extract(r, "soccer", 9999) == {}


@pytest.mark.asyncio
async def test_야구는_추출하지_않는다(monkeypatch):
    """🔴 4-4 스키마는 축구 칸이다. 야구에 억지로 채우면 거짓 재료가 된다."""
    called = []

    async def _ex(*a, **k):
        called.append(1)
        return {"team": "x"}

    async def _adapter(jg, client=None, now=None):
        return [{"team": "Mariners", "body": "b", "url": "u"}]

    monkeypatch.setattr(SAT, "extract_facts", _ex)
    monkeypatch.setitem(SAT._ADAPTERS, "mlb", _adapter)

    n = await SAT.gather({"sport": "mlb", "game_id": 1, "home": "Mariners",
                          "away": "A", "league": "MLB"}, None)

    assert n == 1 and not called


# ── SCT-10: 추출은 **등급 순**으로 읽는다

@pytest.mark.asyncio
async def test_추출은_tier_순으로_읽는다(monkeypatch):
    """🔴 실측 2026-09-14: 수집 순서가 층1(트랜스퍼마크트)→다음→RSS 라
    목록 앞 3건을 자르면 **tier1/2 현지 기사가 항상 잘린다.** 로마 추출
    출처가 v.daum.net 이었고, Dybala 선발이 든 teleradiostereo.it 는
    열어 놓고 읽지 않았다."""
    seen: list[str] = []

    async def _fake(routes, prompt, max_tokens, role):
        return json.dumps({"team": "Torino FC", "out": ["X"]}, ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form._complete_free", _fake)

    arts = [_art("Torino FC", "https://www.transfermarkt.com/x"),
            _art("Torino FC", "http://v.daum.net/v/1"),
            _art("Torino FC", "http://v.daum.net/v/2"),
            _art("Torino FC", "https://www.teleradiostereo.it/a"),   # tier1
            _art("Torino FC", "https://www.fantacalcio.it/b")]       # tier2

    got = await SAT.extract_facts(arts, team="Torino FC", league="serie_a")

    # tier1 이 먼저 채택된다(merge 가 tier 높은 쪽을 고른다).
    assert "teleradiostereo" in got["source"], got["source"]
    _ = seen
