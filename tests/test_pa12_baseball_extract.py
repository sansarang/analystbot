"""PA-12 계약 — 위성 추출은 종목을 가르지 않는다.

🔴 실측 2026-09-16: 야구가 기사 35건을 모으고 **추출 0회** 였다. 그래서 원장
   g8773 의 need 5개가 전부 '미상'이었다 — 가설을 세우고 아무것도 확인하지
   못한 채 판정하고 있었다.
⚠️ 종전 SCT-5("추출은 축구만")의 이유는 "야구 스키마(타순·등판)가 없다"였다.
   그 걱정은 **스키마에 그 칸이 없다는 사실**로 이미 막혀 있다 — 계약이 그것을 잰다.
"""
import pathlib

import pytest

from app.collectors import satellite as S


class _Redis:
    def __init__(self):
        self.keys = []

    async def get(self, k):
        return None

    async def set(self, k, v, **kw):
        self.keys.append(k)
        return True

    async def sismember(self, *a):
        return False

    async def sadd(self, *a):
        return 1


def _jg(sport):
    return {"game_id": 991, "sport": sport,
            "league": "MLB" if sport != "soccer" else "세리에A",
            "home": "Los Angeles Angels", "away": "Seattle Mariners",
            "starts_at": "2026-09-17T01:38:00+00:00"}


@pytest.fixture
def spy(monkeypatch):
    calls = []

    async def _extract(articles, **kw):
        calls.append({"n": len(articles or []), "need": kw.get("need")})
        return {"home": {"out": ["A"]}, "away": {"out": []}}

    monkeypatch.setattr(S, "extract_game_facts", _extract)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("sport", ["mlb", "kbo", "npb", "soccer"])
async def test_종목별로_스키마를_가르지_않는다(spy, sport):
    """🔴 야구도 추출한다. 그리고 축구는 종전대로다(회귀 방지)."""
    n = await S.gather(_jg(sport), _Redis())
    if n:                                   # 기사를 모았으면 반드시 뽑는다
        assert spy, f"{sport}: 기사 {n}건을 모으고 추출을 안 했다"


@pytest.mark.asyncio
async def test_기사가_0건이면_추출하지_않는다(spy, monkeypatch):
    """🔴 반대 위험 — 빈 기사로 LLM 을 부르면 한도만 태운다."""
    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(S, "_ADAPTERS", {"mlb": _empty})
    await S.gather(_jg("mlb"), _Redis())
    assert not spy, "기사 0건인데 추출을 불렀다"


def test_추출_스키마에_타순_등판이_없다():
    """🔴 SCT-5 의 걱정은 **스키마**가 막는다 — LLM 이 만들 칸 자체가 없다."""
    from app.engine.scout_config import EXTRACT_SCHEMA

    banned = ("batting_order", "타순", "pitcher", "등판", "starter", "rotation")
    bad = [k for k in EXTRACT_SCHEMA for b in banned if b in k.lower()]
    assert not bad, f"야구 전용 칸이 생겼다: {bad}"
    for f in ("out", "doubt", "last3"):     # 야구 가설이 요구하는 셋
        assert f in EXTRACT_SCHEMA, f


def test_야구_가설이_요구하는_칸이_스키마에_있다():
    """이게 깨지면 야구 확인은 영영 '미상'이다."""
    from app.engine import gate as G
    from app.engine import hypothesis as HY
    from app.engine.scout_config import EXTRACT_SCHEMA

    h = HY.build(G.OVER, sport="mlb", side="home", gap_pp=-8.0)
    assert h.need, "야구 가설이 비어 있다"
    for n in h.need:
        assert n.field in EXTRACT_SCHEMA, \
            f"{n.field} 를 추출이 만들 수 없다 — 영영 '미상'이 된다"


def test_종목_분기가_남아_있지_않다():
    """종전 `if sport == "soccer":` 가 남으면 야구는 또 막힌다."""
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    blk = src.split("extract_game_facts(articles")[0][-1400:]
    assert 'if sport == "soccer":' not in blk
