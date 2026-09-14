"""D1-6 — ESPN 축구 호출부 + gap_vs_median (사용자 지시).

🔴 오즈포털 북은 전부 소프트북 대역이었다(실측 2026-09-14: 최고 환급률
   94.8~95.9%). 그래서 비교 기준을 바꾸고 **라벨에 그 사실을 박는다** —
   값만 보고 샤프 대비로 읽는 것을 막는다.
"""
import ast
import inspect

import pytest

from app import scheduler
from app.engine import book_gap as BG
from app.engine import gate as G


def _has(fn, name):
    t = ast.parse(inspect.getsource(fn).lstrip())
    return any(isinstance(n, ast.Call)
               and (getattr(n.func, "attr", "") == name
                    or getattr(n.func, "id", "") == name)
               for n in ast.walk(t))


def test_스냅샷_잡이_게이트_대상만_친다():
    assert _has(scheduler._free_odds_snapshot, "_espn_soccer_snapshot")
    assert _has(scheduler._espn_soccer_snapshot, "fetch_soccer")
    src = inspect.getsource(scheduler._espn_soccer_snapshot)
    # 🔴 게이트 라벨 문자열을 베끼지 않는다 — gate 상수를 읽는다.
    assert "시장 과대" not in src and "가치 의심" not in src
    assert scheduler._gate_target_labels() == (G.OVER, G.DOUBT)


def test_DK_와_오즈포털_중앙값_차이를_낸다():
    got = BG.gap_vs_median(
        {"home": 1.25, "draw": 6.0, "away": 11.0},
        [{"home": 1.20, "draw": 6.2, "away": 12.0},
         {"home": 1.22, "draw": 6.0, "away": 11.5},
         {"home": 1.30, "draw": 5.8, "away": 10.0}])

    assert got["side"] == "home" and got["n_books"] == 3
    assert isinstance(got["gap_pp"], float)
    # 🔴 라벨이 "샤프 비교 아님"을 말해야 한다.
    assert got["label"].startswith("샤프 비교 아님 · ")
    assert got["sharp_absent"] is True


def test_한쪽이_없으면_NULL_이다():
    assert BG.gap_vs_median(None, [{"home": 1.2, "away": 5.0}]) is None
    assert BG.gap_vs_median({"home": 1.2, "away": 5.0}, []) is None


@pytest.mark.asyncio
async def test_대상이_0이면_요청도_0이다(monkeypatch):
    class _Pool:
        async def fetch(self, sql, *a):
            return []

    called = []

    async def _fetch(*a, **k):
        called.append(1)
        return {}

    monkeypatch.setattr("app.collectors.espn_odds.fetch_soccer", _fetch)

    n = await scheduler._espn_soccer_snapshot(_Pool(), None)

    assert n == 0 and not called


@pytest.mark.asyncio
async def test_예산_카운터에_espn_soccer_를_센다(monkeypatch):
    from app.collectors import espn_odds as E

    hits = {}

    class _R:
        async def hincrby(self, key, field, n):
            hits[(key.split(":")[0], field)] = n

        async def expire(self, *a):
            return True

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, **k):
            class _Resp:
                @staticmethod
                def json():
                    return {"items": []}
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", _C)

    await E.fetch_soccer("serie_a", "20260914", only_names={"Torino FC"},
                         redis=_R())

    assert hits.get(("api_calls", "espn_soccer")) == 1
