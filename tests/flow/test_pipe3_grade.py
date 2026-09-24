"""[PIPE-3 2026-09-25] ⑨ 등급은 **방향이 판정된 핵심 변수**로만 선다.

사용자 감사 2026-09-25 모순 3:
```
TB@NYY  lineup_out 이 양 팀 −1(상쇄) → ⑦ 행 없음
        그런데 ⑥은 "값이 있으면 confirmed" 라 핵심 3/3 으로 세어졌다
        Σadj = 선발 3.0 + play_load 1.0 = 4.0  → **A**
그날 MLB A등급 4건이 전부 "선발 3.0 + 잡변수 1.0" 구조였다
```

🔴 두 가지를 잠근다:
  (a) ⑦에 행이 없는 핵심 변수는 `n_core_conf` 에 세지 않는다.
  (b) `Σadj` 는 **핵심 변수의 조정만** 합산한다 — 비핵심 잡변수가 A 문턱을
      채우지 못하게.
⚠️ 문턱 숫자(`A_MIN_ADJ_PP` 3.0 · `A_MIN_CORE` 2)는 **바꾸지 않았다.**
   배선만 고쳤다.
"""
from __future__ import annotations

import asyncio

from app.flow.labels import CONFIRMED, GRADE_A, GRADE_B
from app.flow.nodes import n09_conf as N9


class _Ctx:
    pool = None
    redis = None
    inject: dict = {}


def _run(state):
    return asyncio.run(N9.run(state, _Ctx()))


class _S:
    """야구 상태 대역. 🔴 **운영이 실제로 만드는 모양**으로 짠다.

    ⑥ `per_var` 는 변수→판정, ⑦ `n07_adjust` 는 **방향이 선 행만** 남는다.
    """

    game_id = "1"
    sport = "baseball"

    def __init__(self, per_var, adjust):
        self.n06_verdict = {"per_var": per_var}
        self.n07_adjust = adjust
        self.n09_conf = None


def test_pipe3_grade_A_needs_two_directional_core():
    """🔴 TB@NYY 실물 모양 — 핵심 3 confirmed 인데 ⑦ 행은 선발 하나뿐."""
    s = _S(per_var={"starter_recent3": CONFIRMED, "bullpen_3d": CONFIRMED,
                    "lineup_out": CONFIRMED, "play_load": CONFIRMED,
                    "news_injury": "unknown"},
           # lineup_out·bullpen_3d 는 상쇄라 ⑦이 행을 만들지 않았다
           adjust=[{"var": "starter_recent3", "pp": 3.0},
                   {"var": "play_load", "pp": 1.0}])
    out = _run(s).n09_conf
    assert out["core_confirmed"] == 1, \
        f"방향 없는 핵심을 셌다: {out}"
    assert out["grade"] == GRADE_B, f"A 가 남았다: {out}"


def test_pipe3_핵심_둘이_방향까지_서면_A():
    s = _S(per_var={"starter_recent3": CONFIRMED, "bullpen_3d": CONFIRMED,
                    "lineup_out": CONFIRMED},
           adjust=[{"var": "starter_recent3", "pp": 3.0},
                   {"var": "bullpen_3d", "pp": 1.5}])
    out = _run(s).n09_conf
    assert out["core_confirmed"] == 2
    assert out["grade"] == GRADE_A, out


def test_pipe3_비핵심_조정은_A_문턱을_채우지_못한다():
    """🔴 핵심 둘이 서도 **핵심 조정 합**이 문턱 미만이면 A 가 아니다."""
    s = _S(per_var={"starter_recent3": CONFIRMED, "bullpen_3d": CONFIRMED},
           adjust=[{"var": "starter_recent3", "pp": 1.0},
                   {"var": "bullpen_3d", "pp": 1.0},
                   # 비핵심이 5.0 을 보태도 A 가 되면 안 된다
                   {"var": "play_load", "pp": 5.0}])
    out = _run(s).n09_conf
    assert out["core_confirmed"] == 2
    assert out["grade"] == GRADE_B, f"비핵심이 A 를 만들었다: {out}"
    assert "2.0" in out["reason"] or "|Σadj|" not in out["reason"], out["reason"]


def test_pipe3_문턱_숫자를_바꾸지_않았다():
    """⚠️ 이 패치는 **배선만** 고친다. 숫자가 움직이면 다른 얘기다."""
    assert N9.A_MIN_ADJ_PP == 3.0
    assert N9.A_MIN_CORE == 2
