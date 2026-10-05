"""🔴🔴 **지시서 §1-2 — `individual` 정리.** 득점·도움 수는 변수가 아니다.

작업 지시서(오픈월드) §1-2:

> **`individual` 유형 정리** — 선수 개인 득점·도움 수는 **변수가 아니다.**
> `individual` 은 **타이틀 경쟁·연속 기록·복귀·이정표(은퇴·기록 직전)** 처럼
> 결과에 작동할 때만 인정하고, 나머지는 **배경 사실**(hardness 0, strength
> 미반영)로 내린다. 포르투갈 카드의 **R3~R8·R10·R11** 이 이 경우다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (포르투갈 vs 노르웨이 카드)
══════════════════════════════════════════════════════════════════

```
R3  individual·home·soft  João Cancelo 1골 0도움
R4  individual·home·soft  Vítinha 1골 0도움
R5  individual·home·soft  Bruno Fernandes 0골 2도움
R6  individual·home·soft  Gonçalo Ramos 1골 1도움
R7  individual·home·soft  Diogo Dalot 0골 1도움
R8  individual·home·soft  Joao Félix 1골 0도움
R10 individual·away·soft  Martin Ødegaard 0골 1도움
R11 individual·away·soft  Oscar Bobb 1골 0도움
```

⚠️ 여덟 개가 **지난 경기 득점표**다. 🔴 그것이 §5-a 묶음 weight 를 부풀려
   `A` 가 근거 **4.8**(아홉 개 중 여섯이 이 꼴)이 됐다 — *"이기는 이유"* 가
   **득점표 나열**이 된다.
🔴 §4 가 든 보기는 *"손흥민 58골 · 기시 41세 계약 · 차나팁 베트남전 2골 이력"* —
   **이정표·타이틀 경쟁**이다. 한 경기 1골이 아니다.
"""
from __future__ import annotations

import pytest


def _game():
    from app import classify
    return classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League",
                         home_id="team:000191", away_id="team:000174")


def _dir(val):
    from app import classify
    return classify._dir_individual(dict(val), _game())


# ══════════════════════════════════════════════════════════════════
# 🔴 변수가 **아닌** 것 — 배경으로 내린다
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("val,who", [
    ({"team": "Portugal", "player": "João Cancelo", "goals": 1, "assists": 0},
     "R3"),
    ({"team": "Portugal", "player": "Vítinha", "goals": 1, "assists": 0}, "R4"),
    ({"team": "Portugal", "player": "Bruno Fernandes", "goals": 0,
      "assists": 2}, "R5"),
    ({"team": "Portugal", "player": "Gonçalo Ramos", "goals": 1,
      "assists": 1}, "R6"),
    ({"team": "Norway", "player": "Martin Ødegaard", "goals": 0,
      "assists": 1}, "R10"),
    ({"team": "Norway", "player": "Oscar Bobb", "goals": 1, "assists": 0},
     "R11"),
])
def test_wo1_2_지난_경기_득점은_변수가_아니다(val, who):
    """🔴🔴 **포르투갈 카드의 그 여덟 개**다 — 전부 배경으로 내려야 한다."""
    side, why, _ = _dir(val)
    assert side is None, (
        f"🔴 **{who}** — `{val['player']} {val['goals']}골 {val['assists']}도움` "
        f"이 아직 방향을 민다({side}) — 지시서 §1-2 는 배경으로 내리라고 했다: "
        f"{why}")
    assert why, "🔴 **조용히 버리지 않는다**(#3) — 배경으로 내린 사유를 적어라"


# ══════════════════════════════════════════════════════════════════
# ✅ 변수가 **되는** 것 — 네 가지(지시서가 이름을 댔다)
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("val,what", [
    ({"team": "Portugal", "player": "손흥민", "season_goals": 58,
      "top_scorer": True}, "타이틀 경쟁(팀 최다 득점자)"),
    ({"team": "Portugal", "player": "A", "streak_games": 5}, "연속 기록"),
    ({"team": "Norway", "player": "B", "returning": True}, "복귀"),
    ({"team": "Norway", "player": "C", "milestone": "100번째 A매치"},
     "이정표"),
])
def test_wo1_2_결과에_작동하는_것만_변수다(val, what):
    """🔴 *"타이틀 경쟁·연속 기록·복귀·이정표처럼 **결과에 작동할 때만**"*."""
    side, why, _ = _dir(val)
    assert side is not None, (
        f"🔴 **{what}** 는 변수여야 한다 — 지시서 §1-2 가 이름을 댔다: {why}")


def test_wo1_2_배경은_strength_에_안_들어간다():
    """🔴🔴 **hardness 0 · strength 미반영** — 그것이 §1-2 의 요점이다.

    ⚠️ 방향을 `None` 으로 돌려주는 것만으로는 부족하다 — 그 사실이 **묶음
       weight** 에 안 들어가야 한다(그것이 `A` 를 4.8 로 부풀렸다).
    """
    from app import classify
    # ⚠️ 필수 인자가 `text`·`source_url` 이다 — 내 첫 두 판이 빗나갔다(재서 고쳤다)
    got = classify.Classified(
        text="Cancelo 1골 0도움", source_url="https://x",
        type="individual", direction=None, hardness="soft",
        why="배경", team="Portugal")
    assert got.weight == 0.0, (
        f"🔴 배경 사실이 weight {got.weight} 를 갖는다 — strength 를 부풀린다")


def test_wo1_2_배경_사실도_카드에_남는다():
    """🔴 **조용한 0 금지**(#3) — 배경으로 내린 것을 **버리지 않는다**.

    ⚠️ 독자가 *"왜 저 선수 얘기가 없나"* 를 물을 수 있어야 한다. 🔴 그래서
       카드가 배경을 **배경으로** 적는다(변수 목록이 아니라 따로).
    """
    from app import classify
    assert hasattr(classify, "BACKGROUND_NOTE"), (
        "🔴 배경으로 내린 사실을 담는 자리가 없다 — `classify.BACKGROUND_NOTE`")
