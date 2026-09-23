"""[VIS-1] 예측 글이 **내부 용어 그대로** 나온다.

사용자 2026-09-23: "코드로 예측결과를 내면 사용자가 알기 쉽게 표현되어야 한다"

🔴 실측 — 지금 ⑫(`narrate.story_flow`)가 내는 글 그대로:
```
시장은 Hiroshima Toyo Carp 쪽을 근소하게 봅니다.
찾으려 한 것: 우리 픽(home)을 무너뜨릴 근거.
찾은 것: bullpen_3d · starter_recent3.
채점: 미실행 3 · confirmed 2 · unknown 1.
확률을 움직인 것: starter_recent3 +2.1%p · bullpen_3d -2.0%p.
```
읽는 사람이 `bullpen_3d`·`confirmed`·`home` 을 알 수 없다. 바로 앞 대화에서도
사용자가 `엣지 −23.6%p` 가 무슨 뜻인지 물었다 — 같은 문제다.

🔴 **고치는 것은 표현이지 판정이 아니다.** 확률·조정·등급은 코드가 낸 값
   그대로 쓴다. 숫자를 바꾸거나 없는 말을 붙이지 않는다.

⚠️ 변수 이름의 원본은 `config/rules.yaml` 하나다 — 변수 정의 옆에 둔다.
   코드에 표를 만들면 `rules.yaml` 에 변수가 추가될 때 따라가지 않는다.
"""
from __future__ import annotations

import re

import pytest

from app.engine import narrate as NA


class _S:
    league = "KBO"
    home = "두산 베어스"
    away = "KIA 타이거즈"
    pick_side = "home"
    n02_market = {"p": {"home": 0.4512, "away": 0.5488},
                  "odds": {"home": 2.08, "away": 1.71}}
    n03_gate = {"gate": "동의", "gap_pp": -3.39}
    n04_hyp = [{"id": "H_deriv", "text": "승패는 접고 파생만 본다",
                "market": "total",
                "vars": [{"var": "starter_recent3"}, {"var": "bullpen_3d"},
                         {"var": "lineup_out"}]}]
    n05_evidence = [
        {"var": "starter_recent3", "value": ["x"], "status": "",
         "raw_excerpt": "잭로그 · 최근3 방어율 5.17 · 09-18 vs 키움 4.7이닝 2자책 1K"},
        {"var": "bullpen_3d", "value": ["y"], "status": "",
         "raw_excerpt": "09-22 김택연 1.0이닝 · 09-22 이영하 1.0이닝"},
        {"var": "weather", "value": None, "status": "미실행",
         "raw_excerpt": "이 변수는 아직 수집 경로가 없다 — 미실행"},
    ]
    n06_verdict = {"per_var": {"starter_recent3": "confirmed",
                               "bullpen_3d": "confirmed",
                               "lineup_out": "unknown",
                               "weather": "미실행"},
                   "verdict": "확인됨", "unknown_ratio": 0.3333,
                   "unrun": ["weather"], "scored": 3}
    n07_adjust = [{"var": "starter_recent3", "pp": 3.0}]
    n08_pcode = {"p_code_pick": 0.5826, "sum_adj_pp": 3.0}
    n09_conf = {"grade": "A", "reason": "핵심 confirmed=2 · |Σadj|=3.0"}
    n11_value = {"pick_type": "보드", "reject_reason": "총점 방향 미정 — 방향 증거 없음",
                 "structure": None, "ml_edge_pp": -0.56}


def _text() -> str:
    return "\n".join(NA.story_flow(_S()))


# ── 이 단위의 전부: 내부 용어가 글에 없다 ──────────────────────────

def test_변수_코드명이_글에_없다():
    """🔴 `bullpen_3d` 를 사용자가 알 수 없다."""
    t = _text()
    for code in ("starter_recent3", "bullpen_3d", "lineup_out", "weather",
                 "park_factor", "travel_backtoback"):
        assert code not in t, f"코드 이름이 그대로 나온다: {code}\n{t}"


def test_영문_상태값이_글에_없다():
    t = _text()
    for code in ("confirmed", "unknown", "refuted"):
        assert code not in t, f"영문 상태가 그대로 나온다: {code}\n{t}"


def test_home_away_가_글에_없다():
    """🔴 팀 이름으로 부른다."""
    t = _text()
    assert not re.search(r"\b(home|away)\b", t), t
    assert "두산" in t


# ── 읽는 사람이 알아야 할 것이 들어 있다 ───────────────────────────

def test_결론이_맨_앞이다():
    """🔴 무엇을 어느 확률로 보는지가 **첫 줄**이어야 한다."""
    first = NA.story_flow(_S())[0]
    assert "두산" in first and "58" in first, first
    assert "A" in first, "확신 등급이 첫 줄에 없다"


def test_시장과_비교가_숫자로_보인다():
    t = _text()
    assert "45.1" in t or "45%" in t, t


def test_근거가_원문으로_보인다():
    """⚠️ "찾았다"만으로는 알 수 없다 — 무엇을 봤는지 적는다."""
    t = _text()
    assert "잭로그" in t and "5.17" in t, t


def test_못_찾은_것과_잴_수_없는_것을_가른다():
    """🔴 HYC-3 의 구분이 글에도 보여야 한다."""
    t = _text()
    assert "결장" in t, "못 찾은 칸을 안 알려준다"
    assert "날씨" in t, "잴 수 없는 칸을 안 알려준다"


def test_걸_만한가를_말해준다():
    """🔴 사용자가 가장 알고 싶은 것 — 왜 안 걸었는지."""
    t = _text()
    assert "총점" in t or "걸" in t, t


def test_판정_숫자를_바꾸지_않는다():
    """🔴 **표현만 고친다.** 확률·조정은 코드가 낸 값 그대로다."""
    t = _text()
    assert "+3.0" in t, "조정 값이 사라졌다"
    assert "58.3" in t or "58" in t, "코드 확률이 사라졌다"


def test_이름표의_원본이_설정이다():
    """🔴 사본 금지 — 코드에 이름 표를 만들지 않는다."""
    from app.flow import rules as R

    names = R.get("var_names") or {}
    assert names.get("bullpen_3d"), "설정에 이름이 없다"
    import inspect

    src = inspect.getsource(NA)
    assert "var_names" in src or "var_ko" in src


def test_설정의_모든_변수에_이름이_있다():
    """⚠️ 새 변수를 넣고 이름을 빠뜨리면 여기서 걸린다."""
    from app.flow import rules as R

    names = R.get("var_names") or {}
    missing = []
    for sport in ("baseball", "soccer"):
        for var in (R.vars_for(sport) or {}):
            if not names.get(var):
                missing.append(f"{sport}.{var}")
    assert missing == [], f"이름 없는 변수: {missing}"


def test_구경로_글은_그대로다():
    """⚠️ 반대 위험 — `story()` 는 구경로가 쓴다. 건드리지 않았다."""
    jg = {"home": "A", "away": "B", "p_code": 0.6, "winner": "A",
          "order_v3": {}, "lineup_status": "confirmed"}
    assert isinstance(NA.story(jg), str)
