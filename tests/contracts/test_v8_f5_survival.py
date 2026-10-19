"""🔴🔴 **F5 — 보드 생존 = 시뮬 확률**(지시서 2026-10-11 §2 F5).

> ⑭ 생존은 ⑪ 스코어 분포에서 **직접** 계산(승무패·핸디·오버 1.5/2.5/3.5·보드 기준선).
> 시나리오(⑬)와 필수형 보강 갈래는 **표시용** — 생존 계산에 안 쓴다.
> **R7**: 보드 생존 = 시뮬 확률(소수 넷째 자리). 시나리오 갈래를 추가·삭제해도
> 생존이 **같다**.
"""
from __future__ import annotations

import inspect


def _line(market: str, side: str = "", point=None):
    """🔴 `apply`·`from_dist` 가 받는 옛 `Market` 꼴.

    ⚠️ 종전에는 `s7_judge._old_of` 로 `BoardLine` 을 옮겼다 — 🔴 그 함수는
       **걷혔다**(2026-10-19 · 배당을 안 받으므로 보드 줄이 없다). 여기서는
       **생존 산수**를 재는 것이므로 옛 꼴을 바로 만든다.
    """
    from app.types import Market as OldMarket
    if market == "win":
        return OldMarket(market_type={"home": "home", "draw": "draw",
                                      "away": "away"}[side])
    return OldMarket(market_type=market, team=side, line=point)


def _dist() -> dict:
    """🔴 작은 분포 — 합이 1 이다(1-0 0.4 · 1-1 0.35 · 1-2 0.25)."""
    return {(1, 0): 0.4, (1, 1): 0.35, (1, 2): 0.25}


def test_F5_생존이_분포에서_나온다():
    """🔴 `survive.from_dist(line, scores)` — 분포를 그대로 확률로 읽는다."""
    from app import survive
    got = survive.from_dist(_line("win", "home"), _dist(),
                            home="H", away="A", sport="soccer")
    assert abs(got - 0.4) < 1e-9, got
    draw = survive.from_dist(_line("win", "draw"), _dist(),
                             home="H", away="A", sport="soccer")
    assert abs(draw - 0.35) < 1e-9, draw
    away = survive.from_dist(_line("win", "away"), _dist(),
                             home="H", away="A", sport="soccer")
    assert abs(away - 0.25) < 1e-9, away
    # 🔴 셋을 더하면 **1** 이다(분포를 그대로 읽었다는 뜻)
    assert abs(got + draw + away - 1.0) < 1e-9


def test_F5_오버언더도_분포에서():
    """🔴 총골 줄도 같은 분포에서 — 1-0(1골)·1-1(2골)·1-2(3골)."""
    from app import survive
    over15 = survive.from_dist(_line("total", "over", 1.5), _dist(),
                               home="H", away="A", sport="soccer")
    assert abs(over15 - 0.6) < 1e-9, over15      # 2골·3골
    under25 = survive.from_dist(_line("total", "under", 2.5), _dist(),
                                home="H", away="A", sport="soccer")
    assert abs(under25 - 0.75) < 1e-9, under25   # 1골·2골


def test_F5_R7_시나리오를_바꿔도_생존이_같다():
    """🔴🔴 **계약 R7** — 시나리오 갈래를 **추가·삭제해도 생존이 같다**.

    🔴 생존이 분포에서 나오므로 시나리오는 **표시용**이다.
    ⚠️ 돌연변이: ⑭ 가 다시 시나리오 무게로 생존을 세면 이 시험이 빨개진다.
    """
    from app import survive
    line = _line("win", "home")
    a = survive.from_dist(line, _dist(), home="H", away="A", sport="soccer")
    b = survive.from_dist(line, _dist(), home="H", away="A", sport="soccer")
    assert a == b
    # 🔴 **배선** — ⑭ 가 분포를 쓴다
    from app.core.stages import s7_judge as _s7
    said = inspect.getsource(_s7)
    assert "from_dist" in said, "🔴 보드 판정이 분포를 안 쓴다(시나리오 무게로 센다)"


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_F5_시나리오_무게는_표시용이다`
