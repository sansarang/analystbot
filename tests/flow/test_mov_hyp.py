"""[MOV-H] (다) 배당 이동을 ④가설에 **접목**한다 — MLB 부터.

사용자 2026-09-23: "첫번째 배당분석…왜 이렇게 초기 배당이 설정되었는지…
그후 배당의 흐름분석…왜 이렇게 배당이 이동되었는지…**초기 가설과 접목**" ·
"위에 가,나,다 먼저하고 이거를 해라"

🔴 **접목이지 새 가설이 아니다.** 사용자 표현 그대로 `H_break` 안에 싣는다 —
   ⑤⑥이 `n04_hyp[0]["vars"]` 만 보므로 가설을 하나 더 만들면 채점 분모가
   조용히 달라진다(⑥ `wanted` 가 [0] 만 읽는다).

🔴 **MLB 부터다**(사용자 지시 순서). KBO·NPB 는 ODD-S 게이트가 배포돼
   원자료가 깨끗해진 뒤에 켠다 — 실측:
```
증분 자기상관 ρ₁   mlb +0.0001(진짜) · kbo −0.5849 · npb −0.5751(노이즈)
종가−시가          mlb +0.00169 개선 · npb −0.00896 악화
```

⚠️ **읽는 쪽도 `impossible_set` 을 지난다.** 이미 쌓인 244행(kbo 145 ·
   npb 94 · mlb 5)이 DB 에 남아 있어, 적재 게이트만으로는 옛 행이 개장가로
   뽑힌다. 판정은 한 곳(`odds_math.impossible_set`)이 한다 — 사본 금지.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.flow.nodes import n02_market as N2
from app.flow.nodes import n04_hyp as N4

T0 = dt.datetime(2026, 9, 23, 0, 0, tzinfo=dt.UTC)


def _row(mins, side, odds, market="h2h"):
    return {"market": market, "side": side, "odds": odds, "line": None,
            "snap_tag": None, "provider": "p",
            "captured_at": T0 + dt.timedelta(minutes=mins)}


#: 개장 홈 2.00/원정 2.00(50%) → 현재 홈 1.70/원정 2.30(57.5%)
_ROWS = [_row(0, "HOME", 2.00), _row(0, "AWAY", 2.00),
         _row(60, "HOME", 1.85), _row(60, "AWAY", 2.10),
         _row(120, "HOME", 1.70), _row(120, "AWAY", 2.30)]


# ── ② 가 이동을 낸다 ────────────────────────────────────────────────

def test_개장과_현재를_뽑는다():
    m = N2.move_of(_ROWS, "HOME", "AWAY")
    assert m["n_snaps"] == 3
    assert m["open_home"] == 0.5
    assert abs(m["now_home"] - 0.5748) < 1e-3
    assert abs(m["move_pp"] - 7.48) < 0.02, m


def test_불가능한_개장가는_개장이_아니다():
    """🔴 ODD-S 를 읽는 쪽에서도 쓴다. 이미 쌓인 244행이 DB 에 남아 있다."""
    rows = [_row(-60, "HOME", 2.08), _row(-60, "AWAY", 2.20)] + _ROWS  # 합 0.935
    m = N2.move_of(rows, "HOME", "AWAY")
    assert m["n_snaps"] == 3, "불가능한 벌을 개장으로 삼았다"
    assert m["open_home"] == 0.5


def test_한_벌뿐이면_이동이_없다():
    """⚠️ 0 과 모름은 다르다 — 못 재면 None 이다."""
    m = N2.move_of([_row(0, "HOME", 2.0), _row(0, "AWAY", 2.0)], "HOME", "AWAY")
    assert m["move_pp"] is None and m["n_snaps"] == 1
    assert N2.move_of([], "HOME", "AWAY")["move_pp"] is None


def test_반쪽_벌은_세지_않는다():
    m = N2.move_of([_row(0, "HOME", 2.0)] + _ROWS, "HOME", "AWAY")
    assert m["n_snaps"] == 3


def test_축구는_무승부까지_한_벌이다():
    rows = [_row(0, "HOME", 2.30), _row(0, "DRAW", 3.40), _row(0, "AWAY", 3.10),
            _row(60, "HOME", 2.10), _row(60, "DRAW", 3.40), _row(60, "AWAY", 3.50)]
    m = N2.move_of(rows, "HOME", "AWAY")
    assert m["n_snaps"] == 2 and m["move_pp"] is not None


@pytest.mark.asyncio
async def test_2가_스냅샷에_싣는다():
    class _C:
        inject = {"odds_rows": _ROWS}
        pool = None

    class _S:
        game_id = "1"
        sport = "baseball"
        home = "HOME"
        away = "AWAY"
        n02_market = None

    s = await N2.run(_S(), _C())
    assert s.n02_market["move"]["move_pp"] is not None


# ── ④ 가 접목한다 ──────────────────────────────────────────────────

class _S:
    game_id = "1"
    sport = "baseball"
    league = "MLB"
    home = "HOME"
    away = "AWAY"
    hyp_side = "home"
    pick_side = "home"
    n01_prior = {"p_home": 0.55, "p_away": 0.45}
    n02_market = {"p": {"home": 0.5748, "draw": None, "away": 0.4252},
                  "move": {"move_pp": 7.48, "open_home": 0.5,
                           "now_home": 0.5748, "n_snaps": 3}}
    n03_gate = {"gate": "동의"}
    n04_hyp = None


class _Ctx:
    inject = {}
    pool = None


@pytest.mark.asyncio
async def test_이동을_가설에_싣는다():
    s = await N4.run(_S(), _Ctx())
    h = s.n04_hyp[0]
    assert h["id"] == "H_break", "가설을 하나 더 만들었다 — ⑥ 분모가 달라진다"
    assert h["move"]["move_pp"] == 7.48
    assert "7.5" in h["why"] and "움직" in h["why"], h["why"]


@pytest.mark.asyncio
async def test_이동을_설명할_변수를_앞에_둔다():
    s = await N4.run(_S(), _Ctx())
    names = [v["var"] for v in s.n04_hyp[0]["vars"]]
    from app.flow import rules as R
    first = [x for x in (R.get("move.explains") or []) if x in names]
    assert names[:len(first)] == first, names


@pytest.mark.asyncio
async def test_문턱_미만이면_접목하지_않는다():
    s = _S()
    s.n02_market = dict(s.n02_market, move={"move_pp": 0.4, "n_snaps": 3})
    out = await N4.run(s, _Ctx())
    assert out.n04_hyp[0].get("move") is None


@pytest.mark.asyncio
async def test_못_잰_이동은_지어내지_않는다():
    s = _S()
    s.n02_market = dict(s.n02_market, move={"move_pp": None, "n_snaps": 1})
    assert (await N4.run(s, _Ctx())).n04_hyp[0].get("move") is None
    s2 = _S()
    s2.n02_market = {"p": {"home": 0.5, "draw": None, "away": 0.5}}
    assert (await N4.run(s2, _Ctx())).n04_hyp[0].get("move") is None


@pytest.mark.asyncio
async def test_켜지_않은_종목은_그대로다():
    """🔴 사용자 지시 순서 — MLB 부터. KBO·NPB 는 원자료가 깨끗해진 뒤."""
    s = _S()
    s.league = "KBO"
    assert (await N4.run(s, _Ctx())).n04_hyp[0].get("move") is None


@pytest.mark.asyncio
async def test_보드고정은_종전대로_찾을_것이_없다():
    s = _S()
    s.n03_gate = {"gate": "보드고정"}
    h = (await N4.run(s, _Ctx())).n04_hyp[0]
    assert h["id"] == "H_none" and h.get("move") is None


def test_종목_목록과_문턱이_config_에_있다():
    """⚠️ 이름을 코드에 손으로 적지 않는다 — 사본 금지."""
    import inspect

    from app.flow import rules as R

    assert "mlb" in [str(x).lower() for x in (R.get("move.sports") or [])]
    assert float(R.get("move.min_pp", 0)) > 0
    assert R.get("move.explains")
    # ⚠️ **이 단위가 더한 함수만 본다.** `n04_hyp` 에는 종전부터 손으로 적은
    #    목록이 따로 있다(`("bullpen_3d", "lineup_out")` 등) — 그것은 이
    #    작업의 범위가 아니다. 넘보면 남의 결함으로 내 계약이 깨진다.
    src = inspect.getsource(N4._move_of) + inspect.getsource(N4._move_first)
    for banned in ('"mlb"', "'mlb'", '"lineup_out"', "'lineup_out'"):
        assert banned not in src, f"이름을 손으로 적었다: {banned}"
