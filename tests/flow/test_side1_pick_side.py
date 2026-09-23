"""[SIDE-1] 방향의 원본은 ①의 `pick_side` 다 — 확률에서 되짚지 않는다.

사용자 2026-09-23: "그러면 수정해야 하지 않냐? 예측할때마다 버그가 생기는
원인은 뭐냐?"

🔴 같은 값에 두 모듈이 **반대 뜻**을 붙이고 있었다:
```
생산자 n08_pcode.run:72   side = state.pick_side
                          p_code_pick = 시장[side] + 조정      ← 픽 기준
소비자 record.pick_of     "⚠️ p_code_pick 은 홈 기준이다"
                          side = "home" if p >= 0.5 else "away"  ← 홈 기준
```
실측 2026-09-23 (최근 30일, ⑧까지 간 58경기):
```
원장 팀이 뒤집힌 행   13건 (22.4%)
decision_ledger flow_v14   home 525 : away 221   ← 쏠림이 그 서명이다
  예) Seattle @ Colorado  픽확률 57.2%  진짜픽 Seattle → 원장 Colorado
```

🔴 **왜 계약이 못 잡았나.** 이 자리를 지키던 `test_swap1_record.py` 의 상태
   대역 `_S` 에는 `pick_side` 가 **아예 없다**(실측: 그 파일의 `pick_side`
   언급 0건). 진실을 담은 칸이 대역에 없으니 두 해석이 구분되지 않았다.
   같은 파일이 이미 LED-1(`p_market` 은 ②가 만들지 않는 모양) · LED-2
   (`_Pool` 에 `fetchrow` 없음)를 겪었다 — **세 번째다.**
"""
from __future__ import annotations

import inspect

import pytest

from app.flow import record as R


class _S:
    """🔴 대역에 `pick_side` 를 **반드시** 둔다 — 이것이 없어서 못 잡았다."""

    run_id = "r1"
    game_id = "7"
    sport = "baseball"
    league = "KBO"
    stop_reason = None
    pick_side = "home"
    n02_market = {"p": {"home": 0.4424, "draw": None, "away": 0.5576},
                  "odds": {"home": 2.13, "away": 1.69}}
    n03_gate = {"label": "가치의심"}
    n07_adjust = [{"pp": -3.0}]
    n08_pcode = {"p_code_pick": 0.4124}
    n09_conf = {"grade": "A"}


# ── 오늘 실제로 틀린 경기 ───────────────────────────────────────────

def test_픽이_50퍼센트_미만이어도_픽을_바꾸지_않는다():
    """🔴 KIA@두산 실측. ①이 두산을 골랐고 ⑧이 41.2% 를 냈다.
    확률이 낮다고 상대 팀을 픽으로 적으면 **다른 경기를 채점**하게 된다."""
    side, ours, mkt = R.pick_of(_S())
    assert side == "home", "픽 확률이 50% 미만이라고 방향을 뒤집었다"
    assert ours == 0.4124, "픽 기준 확률을 또 변환했다"
    assert mkt == 0.4424


def test_원정_픽은_원정으로_적는다():
    """🔴 **22.4% 의 본체.** 원정 픽이 50% 이상이면 종전 코드는 home 으로 적었다."""
    s = _S()
    s.pick_side = "away"
    s.n08_pcode = {"p_code_pick": 0.5876}
    side, ours, mkt = R.pick_of(s)
    assert side == "away", "원정 픽을 홈으로 적었다 — 22.4% 가 이것이다"
    assert ours == 0.5876
    assert mkt == round(1 - 0.4424, 4), "시장만 픽 기준으로 돌린다"


@pytest.mark.parametrize("side,pc", [("home", 0.6522), ("home", 0.4124),
                                     ("away", 0.5876), ("away", 0.3300)])
def test_방향은_언제나_pick_side_다(side, pc):
    """⚠️ 네 조합 전부. 종전 코드는 이 중 **둘**에서만 우연히 맞았다."""
    s = _S()
    s.pick_side = side
    s.n08_pcode = {"p_code_pick": pc}
    assert R.pick_of(s)[0] == side


def test_확률에서_방향을_되짚지_않는다():
    """🔴 사본 금지의 방향판 — 원본이 `pick_side` 하나여야 한다.

    ⚠️ **독스트링까지 뗀다.** 위 설명이 `>= 0.5` 를 그대로 담고 있어 원문
       grep 은 거짓으로 실패한다 — 이 저장소가 겪은 D46 의 12번째다.
       주석만 떼는 `split("#")` 으로는 부족해서 AST 로 판다.
    """
    import ast

    tree = ast.parse(inspect.getsource(R.pick_of).strip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not (body and isinstance(body, list)):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    src = ast.unparse(tree)
    assert "pick_side" in src
    assert ">= 0.5" not in src and "> 0.5" not in src, "확률로 방향을 되짚는다"


def test_pick_side_가_없으면_적지_않는다():
    """🔴 추정하면 22.4% 가 그대로 돌아온다. 지어내느니 안 적는다."""
    for bad in (None, "", "HOME", "홈", 1):
        s = _S()
        s.pick_side = bad
        assert R.pick_of(s) == (None, None, None), bad


def test_확률이_없으면_종전대로_안_적는다():
    s = _S()
    s.n08_pcode = {"p_code_pick": None}
    assert R.pick_of(s) == (None, None, None)


def test_시장이_없어도_판정은_남긴다():
    """⚠️ 시장 확률이 없다고 흐름 판정을 버리지 않는다 — CLV 만 못 잰다."""
    s = _S()
    s.n02_market = {"p": None, "market_missing": True}
    side, ours, mkt = R.pick_of(s)
    assert side == "home" and ours == 0.4124 and mkt is None


# ── 가격도 같은 방향을 본다 ─────────────────────────────────────────

def test_가격이_픽_쪽_배당이다():
    """🔴 `price_of` 가 `pick_of` 의 방향을 쓴다 — 뒤집히면 **상대 배당**으로
    ROI 를 잰다."""
    assert R.price_of(_S()) == 2.13
    s = _S()
    s.pick_side = "away"
    s.n08_pcode = {"p_code_pick": 0.5876}
    assert R.price_of(s) == 1.69


# ── 생산자·소비자 대조 ──────────────────────────────────────────────

def test_생산자가_픽_기준으로_쓴다():
    """🔴 **이 계약이 이번 사고의 핵심이다.** 두 모듈의 뜻을 여기서 대조한다.

    🔴 [SIDE-2 2026-09-23 개정] ⑧은 이제 `pick_side` 를 **읽지 않고 쓴다.**
       확률을 홈 기준으로 내고 50% 를 넘는 쪽을 고른다. 그래서 대조할 것은
       "⑧이 픽 기준으로 읽는가"가 아니라 **"⑧이 정한 방향과 `p_code_pick` 이
       같은 쪽인가"** 다 — 그 둘이 어긋난 것이 이 사고였다.
    """
    import asyncio

    from app.flow.nodes import n08_pcode as N8

    class _C:
        inject = {}

    for mkt_home, adj, want in [(0.48, 0.0, "away"), (0.48, 4.0, "home"),
                                (0.64, 0.0, "home"), (0.64, -20.0, "away")]:
        s = _S()
        s.hyp_side = "home"
        s.n02_market = {"p": {"home": mkt_home, "draw": None,
                              "away": round(1 - mkt_home, 4)},
                        "odds": {"home": 2.0, "away": 2.0}}
        s.n07_adjust = [{"pp": adj}] if adj else []
        asyncio.run(N8.run(s, _C()))
        assert s.pick_side == want, (mkt_home, adj, s.n08_pcode)
        side, ours, _m = R.pick_of(s)
        assert side == want and ours >= 0.5, (side, ours)


def test_대역이_운영_모양을_따른다():
    """⚠️ LED-1·LED-2 와 같은 부류를 막는다 — 대역에 진실 칸이 있어야 한다."""
    s = _S()
    assert s.pick_side in ("home", "away")
    assert set(s.n02_market["p"]) == {"home", "draw", "away"}
    assert set(s.n02_market["odds"]) >= {"home", "away"}
