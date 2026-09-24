"""[PIPE-4 2026-09-25] `play_load` 는 **차이가 문턱을 넘을 때만** 방향이 선다.

사용자 감사 2026-09-25 모순 4:
```
n05_evidence  d[sd] = -1 if score >= thr and score >= hi else 0
              direction={"dev": _DEV_FULL()}   ← 강도가 언제나 1.0
→ 부하 47.3 vs 52.9 처럼 근소해도 ±1.0 만점.
  17경기 중 12경기에 들어갔고 부호가 양방향이다.
```

🔴 잠그는 것 둘:
  (a) `|차| < thr` 이면 양 쪽 0 — ⑦이 행을 만들지 않는다.
  (b) `dev` 는 **실제 차이**다 — 기준값을 그대로 싣지 않는다.
⚠️ 문턱 `load.heavy_score`(3.0)·`max_abs`(1.0) 는 **바꾸지 않았다.**
"""
from __future__ import annotations

import ast
import inspect

from app.flow import direction as DIR
from app.flow.nodes import n05_evidence as N5
from app.flow.nodes import n07_adjust as N7


def test_pipe4_play_load_needs_gap():
    """🔴 근소한 차이는 방향이 서지 않는다."""
    d = DIR.load_direction(score_home=47.287, score_away=48.9, thr=3.0)
    assert d["home"] == 0 and d["away"] == 0, d
    assert "문턱" in d["basis"], d


def test_pipe4_문턱을_넘으면_많이_뛴_쪽이_악재():
    d = DIR.load_direction(score_home=54.538, score_away=48.938, thr=3.0)
    assert d["home"] == -1 and d["away"] == 0, d
    d2 = DIR.load_direction(score_home=48.938, score_away=54.538, thr=3.0)
    assert d2["away"] == -1 and d2["home"] == 0, d2


def test_pipe4_dev_는_실제_차이다():
    """종전에는 `dev` 가 기준값이라 강도가 항상 1.0 이었다."""
    small = DIR.load_direction(score_home=3.4, score_away=0.0, thr=3.0)
    big = DIR.load_direction(score_home=30.0, score_away=0.0, thr=3.0)
    assert small["dev"] < big["dev"], (small, big)
    # ⑦의 강도 계산과 실제로 이어지는지 — 함수를 그대로 태운다(사본 금지)
    assert N7._strength_of(small["dev"], 0.5) == 1.0
    assert N7._strength_of(0.05, 0.5) == 0.1


def test_pipe4_한쪽이라도_모르면_방향_없음():
    d = DIR.load_direction(score_home=None, score_away=50.0, thr=3.0)
    assert d["home"] == 0 and d["away"] == 0 and d["dev"] is None, d


def test_pipe4_n05_가_direction_을_부른다():
    """🔴 배선 — 판정 규칙이 두 곳에 생기면 어긋난다(사본 금지)."""
    src = inspect.getsource(N5)
    assert "DIR.load_direction(" in src, "⑤가 판정을 여전히 자기 안에서 한다"
    tree = ast.parse(src)
    # 종전의 손계산(`score >= thr and score >= hi`)이 남아 있으면 안 된다
    assert "score\", 0.0) >= thr" not in src, "옛 판정식이 남아 있다"
