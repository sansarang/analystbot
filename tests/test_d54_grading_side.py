"""[D54] **채점이 카드와 다른 쪽을 채점한다.**

🔴 실측 2026-09-22 · 운영 원장 (채점 완료 · `p_code` 있는 251행):

```
채점이 쓴 side 와 p_code 방향이 **다른 행 26건 (10.4%)**

g1741 NC Dinos@Doosan Bears   favored=away  p_code=0.5579(→home)  winner=home  hit=False
g1742 LG Twins@Samsung Lions  favored=home  p_code=0.4814(→away)  winner=away  hit=False
g6517 Chunichi@Hanshin        favored=박빙  p_code=0.6156(→home)  winner=away  hit=True   ← 우연히 맞았다
```

`predicted_side()` 의 우선순위가 뒤집혀 있다:

```
favored  →  stored(predicted_side 칸)  →  p_home
   ↑                  ↑
레거시 라벨        카드가 실제로 낸 승자
```

`_row_from_game` 을 보면 어느 칸이 정본인지 나온다:
```
"predicted_side": _side_of(jg, matchup.get("승자") or jg.get("winner"))   ← 코드가 정한 승자
"favored":        matchup.get("우세") or _side_of(...)                    ← 레거시 라벨('박빙' 포함)
"p_home":         jg.get("p_claude")                                      ← **은퇴한 옛 Judge**
```
CLAUDE.md 가 "승자·확률·확신은 코드가 정한다(`matchup.apply_code_verdict`)"고
적은 그 승자가 `predicted_side` 다. `favored` 는 그것과 어긋날 수 있다.

🔴 **대가가 측정된다** (같은 251행):
```
채점이 쓴 side (favored 우선)   적중 56.2%  σ+1.96
p_code 방향                     적중 57.8%  σ+2.46
```
**1.6%p** 를 잘못된 칸을 우선해서 잃었다.

⚠️ **기존 행을 다시 채점하지 않는다.** `grade_pending` 은 `graded_at IS NULL`
   만 집으므로 이 수정은 **앞으로만** 적용된다. 소급 재채점은 "어느 규칙으로
   채점된 행인지" 구분을 없애므로 하지 않는다(같은 파일의 `final_score` 순서
   정정에서 이미 같은 판단을 했다).
"""
from __future__ import annotations

import pytest


def test_카드의_승자가_레거시_라벨을_이긴다():
    """🔴 이것이 HEAD 에서 실패한다 — `favored` 가 먼저였다."""
    from app.engine.pick_ledger import predicted_side

    # 실측 g1741: favored=away 인데 카드는 home 을 냈다
    assert predicted_side("away", 0.48, "home") == "home"
    # 실측 g1742: favored=home 인데 카드는 away 를 냈다
    assert predicted_side("home", 0.54, "away") == "away"


def test_카드가_없으면_레거시를_쓴다():
    """⚠️ **반대 위험.** 옛 경기에는 `predicted_side` 칸이 없다(1,404행 중 242행만
    있다). 그 행이 채점 분모에서 빠지면 원장이 통째로 얇아진다."""
    from app.engine.pick_ledger import predicted_side

    assert predicted_side("away", 0.48, None) == "away"
    assert predicted_side("home", None, None) == "home"


def test_박빙은_확률로_환산한다():
    """⚠️ `favored='박빙'` 은 방향 선언이 아니다 — 종전 규약 그대로."""
    from app.engine.pick_ledger import predicted_side

    assert predicted_side("박빙", 0.61, None) == "home"
    assert predicted_side("박빙", 0.42, None) == "away"
    assert predicted_side("박빙", None, None) is None


def test_방향이_없으면_None_이다():
    """🔴 모르는 것을 찍지 않는다 — `hit=None` 으로 분모에서 빠져야 한다."""
    from app.engine.pick_ledger import predicted_side

    assert predicted_side(None, None, None) is None


def test_우선순위를_코드에_적어_두었다():
    """🔴 왜 이 순서인지가 코드에 없으면 다음 사람이 되돌린다."""
    import inspect

    from app.engine.pick_ledger import predicted_side

    src = inspect.getsource(predicted_side)
    assert "D54" in src, "정정 근거가 코드에 없다"
    i_stored, i_fav = src.index("stored in"), src.index('favored in')
    assert i_stored < i_fav, "stored 를 favored 보다 먼저 보지 않는다"


@pytest.mark.parametrize("fav,stored,p_home,want", [
    ("away", "home", 0.48, "home"),   # 실측 g1741
    ("home", "away", 0.54, "away"),   # 실측 g1742
    ("박빙", None, 0.47, "away"),      # 실측 g6517 — 카드 칸이 비었다
    ("away", None, 0.48, "away"),     # 옛 행
])
def test_실측_행들(fav, stored, p_home, want):
    from app.engine.pick_ledger import predicted_side

    assert predicted_side(fav, p_home, stored) == want
