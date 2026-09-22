"""[VEN-1] 파크팩터가 **산출은 되는데 아무도 안 쓴다.**

사용자 2026-09-23: "1,2,3,4 전부다 승인" (③ venue_name·park_factor)

🔴 실측 2026-09-23 운영 — `kbo_park.refresh(redis)` 를 그냥 부르자:
```
refresh → {'stadiums': 9, 'games': 782}
load    → {'잠실': {'pf': 0.878, …}, '사직': {'pf': 1.226, …},
           '대전': 1.153 · '수원': 1.106 · '대구': 1.027 · '문학': 1.005 ·
           '창원': 0.946 · '고척': 0.913 · '광주': 0.909}
```
**모듈은 멀쩡했다.** 종전에 `{'stadiums':0,'games':0}` 이던 것은
`koreabaseball` 게이트 때문이고, 그건 2026-09-23 에 켰다(KBO-ON).

🔴 그런데 배선이 둘 다 없었다:
```
app/scheduler.py   kbo_park 언급 0   (MLB `park` 는 주 1회 잡이 있다)
n05_evidence.py    park_factor 언급 0 · kbo_park 언급 0
```
그래서 `park_factor` 는 야구 전 리그에서 **언제나 미상**이었다.

⚠️ **방향을 붙이지 않는다.** "타자 구장이 우리에게 유리하다"는 팀 성향에
   달렸고 미검증이다. ⑦은 방향이 없으면 행을 만들지 않으므로(`sign == 0`)
   조정은 0 이고, 바뀌는 것은 "쟀다/못 쟀다"뿐이다 — 그것이 정직한 몫이다.
⚠️ NPB 는 파크팩터 모듈이 **없다.** 없는 것을 1.0 으로 채우지 않는다 —
   "측정했는데 중립"과 "못 쟀다"가 구분되지 않는다(`kbo_park` 머리말과 같은 규약).
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n05_evidence as N5


class _R:
    def __init__(self, doc):
        self.doc = doc

    async def get(self, k):
        import json
        return json.dumps(self.doc) if self.doc else None


async def _run(*, league, sport, redis, home="KT Wiz"):
    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": sport, "league": league,
                    "home": home, "away": "SSG Landers",
                    "starts_at": "2026-09-23T09:30:00+00:00"})
    st.sport = sport
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "park_factor"}]}]
    out = await N5.run(st, Ctx(redis=redis))
    return [e for e in (out.n05_evidence or []) if e["var"] == "park_factor"]


@pytest.mark.asyncio
async def test_KBO_는_구장을_읽는다(monkeypatch):
    from app.collectors import kbo_park as KP

    monkeypatch.setattr(KP, "load", lambda r: _ok({"수원": {"pf": 1.106,
                                                          "games": 64}}))
    got = await _run(league="KBO", sport="baseball", redis=_R({}))
    assert got, "파크팩터가 있는데 증거가 비었다"
    assert "1.106" in got[0]["raw_excerpt"], got[0]
    assert "수원" in got[0]["raw_excerpt"]
    assert "kbo_park" in got[0]["source"]


def _ok(v):
    async def _f():
        return v
    return _f()


@pytest.mark.asyncio
async def test_방향을_붙이지_않는다(monkeypatch):
    """🔴 "타자 구장 = 우리에게 유리"는 미검증이다."""
    from app.collectors import kbo_park as KP

    monkeypatch.setattr(KP, "load", lambda r: _ok({"수원": {"pf": 1.106}}))
    got = await _run(league="KBO", sport="baseball", redis=_R({}))
    assert not got[0].get("direction"), got[0]


@pytest.mark.asyncio
async def test_모르는_구장은_지어내지_않는다(monkeypatch):
    from app.collectors import kbo_park as KP

    monkeypatch.setattr(KP, "load", lambda r: _ok({}))
    assert await _run(league="KBO", sport="baseball", redis=_R({})) == []


@pytest.mark.asyncio
async def test_NPB_는_미상이다(monkeypatch):
    """🔴 모듈이 없다 — 1.0 으로 채우면 "쟀는데 중립"으로 읽힌다."""
    got = await _run(league="NPB", sport="baseball", redis=_R({}),
                     home="Hanshin Tigers")
    assert got == []


@pytest.mark.asyncio
async def test_MLB_도_읽는다(monkeypatch):
    from app.collectors import park as P

    monkeypatch.setattr(P, "load", lambda r: _ok({"New York Yankees": 1.08}))
    got = await _run(league="MLB", sport="baseball", redis=_R({}),
                     home="New York Yankees")
    assert got and "1.08" in got[0]["raw_excerpt"], got


def test_주간_잡이_KBO_도_갱신한다():
    """🔴 산출이 안 돌면 표가 비고, 표가 비면 ⑤가 읽을 게 없다.

    ⚠️ 새 잡을 만들지 않았다 — MLB 파크팩터를 돌리는 **그 잡**에 붙였다.
       주기가 두 벌이 되면 한쪽만 도는 날이 생긴다.
    """
    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S.park_refresh_job).splitlines())
    assert "kbo_park" in src, "주간 잡이 KBO 를 갱신하지 않는다"
    assert "from app.collectors.park import refresh" in src, "MLB 갱신이 사라졌다"


def test_한_잡이다():
    """⚠️ 잡 이름을 늘리지 않았다 — 등록표에 park 잡은 하나다."""
    import app.scheduler as S

    src = inspect.getsource(S)
    assert src.count("park_refresh_job") == 2, "잡이 갈렸다(정의 1 + 등록 1)"
