"""SOC-1 — 수집 채널을 종목 표로 뺀다. 축구는 **새 행**이지 새 분기가 아니다.

사용자 지시 2026-09-12: "코드 꼬이지 않게 분류해서 작업을 할거다"

🔴 왜. `gather.collect` 의 `jobs` 가 **야구 전용으로 하드코딩**돼 있다:

     jobs = {"satellite": …, "라인업": …(크롤러 선발·타순), "크롤러": …(불펜)}

   축구에는 선발투수도 불펜도 없다. 그대로 두고 축구를 끼우면
   `if sport == "soccer"` 가 엔진 전체에 번지고, 그때부터 야구를 고칠 때마다
   축구가 깨진다(그 반대도).

⚠️ **반대 위험이 더 크다.** 야구 세 종목은 지금 운영에서 돈다 —
   채널이 하나라도 빠지면 재료가 줄고 판정이 굶는다. 그 계약이 이 파일의 절반이다.
"""

import pytest

from app.engine import gather as G
from app import registry as R


def _jg(sport="kbo"):
    return {"game_id": 1, "sport": sport, "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


# ═══════════════ ① 표가 원본이다

def test_채널_표가_레지스트리에_있다():
    assert hasattr(R, "COLLECT_CHANNELS")
    assert isinstance(R.COLLECT_CHANNELS, dict)


def test_collect_가_표를_읽는다():
    """🔴 하드코딩을 남기면 표가 사본이 된다."""
    import inspect

    src = inspect.getsource(G.collect)
    assert "COLLECT_CHANNELS" in src or "collect_channels" in src


def test_표에_네_종목이_있다():
    for s in ("kbo", "npb", "mlb", "soccer"):
        assert s in R.COLLECT_CHANNELS, s


# ═══════════════ ② 야구 회귀 0 — 가장 큰 반대 위험

@pytest.mark.parametrize("sport", ["kbo", "npb", "mlb"])
def test_야구는_세_채널_그대로다(sport):
    """🔴 운영이 이 채널로 돈다. 하나라도 빠지면 판정이 굶는다."""
    assert R.COLLECT_CHANNELS[sport] == ("satellite", "라인업", "크롤러")


@pytest.mark.parametrize("sport", ["kbo", "npb", "mlb"])
@pytest.mark.asyncio
async def test_야구는_세_채널을_실제로_부른다(sport, monkeypatch):
    called = []
    _patch_all(monkeypatch, called)
    await G.collect(_jg(sport), None, "2026-09-12")
    assert set(called) == {"enrich", "satellite", "라인업", "크롤러"}, called


# ═══════════════ ③ 축구는 위성만

def test_축구는_위성만이다():
    """축구에는 선발투수도 불펜도 없다 — 야구 채널을 부르면 빈손 호출만 는다."""
    assert R.COLLECT_CHANNELS["soccer"] == ("satellite",)


@pytest.mark.asyncio
async def test_축구는_야구_채널을_부르지_않는다(monkeypatch):
    called = []
    _patch_all(monkeypatch, called)
    await G.collect(_jg("soccer"), None, "2026-09-12")
    assert "크롤러" not in called, "불펜(pitcher_appearances)을 축구에서 불렀다"
    assert "라인업" not in called, "야구 크롤러 라인업을 축구에서 불렀다"
    assert "satellite" in called


# ═══════════════ ④ 모르는 종목 — 조용히 0 이 되지 않는다

@pytest.mark.asyncio
async def test_표에_없는_종목은_위성만_쓰고_로그를_남긴다(monkeypatch, caplog):
    """🔴 표를 안 채우고 종목을 늘리면 그 종목은 영영 재료가 0 이다."""
    import logging

    called = []
    _patch_all(monkeypatch, called)
    with caplog.at_level(logging.INFO):
        await G.collect(_jg("hockey"), None, "2026-09-12")
    assert called.count("satellite") == 1
    assert any("hockey" in r.getMessage() for r in caplog.records), caplog.text


# ═══════════════ ⑤ 종전 계약은 그대로다

@pytest.mark.asyncio
async def test_수집이_메우기를_먼저_한다(monkeypatch):
    """🔴 [ORD-16] `enrich` → `game_brief` 순서가 계약이다."""
    called = []
    _patch_all(monkeypatch, called)
    await G.collect(_jg(), None, "2026-09-12")
    assert called[0] == "enrich"


@pytest.mark.asyncio
async def test_한_채널이_터져도_나머지가_산다(monkeypatch):
    called = []
    _patch_all(monkeypatch, called)

    async def _boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(G, "_satellite", _boom)
    out = await G.collect(_jg(), None, "2026-09-12")
    assert "크롤러" in called


@pytest.mark.asyncio
async def test_수집에서_유료_호출이_나가지_않는다(monkeypatch):
    """🔴 요청받았을 때만 검색한다 — 표에 pplx 를 넣으면 안 된다."""
    for ch in R.COLLECT_CHANNELS.values():
        assert "pplx" not in ch and "퍼플렉시티" not in ch


# ═══════════════ 보조

def _patch_all(monkeypatch, called):
    def mk(tag, ret=None):
        async def _f(*a, **k):
            called.append(tag)
            return ret if ret is not None else []
        return _f

    monkeypatch.setattr(G, "enrich", mk("enrich"))
    monkeypatch.setattr(G, "_satellite", mk("satellite"))
    monkeypatch.setattr(G, "_lineup", mk("라인업"))
    monkeypatch.setattr(G, "_bullpen", mk("크롤러"))
    monkeypatch.setattr(G, "_preview", mk("pplx"))
