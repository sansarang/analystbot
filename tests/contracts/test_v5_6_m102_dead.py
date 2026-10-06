"""🔴🔴 **M102~M104 — 다중 스코어 대입·죽는 목록·방향 판정**.

지시서 `docs/fable/archive/2026-10-05_workorder_idn_tha_fixes.md` §2.

> **2-1 다중 스코어 대입** — 시나리오의 `outcomes` 가 둘 이상이면 **모든
> 마켓**에서 스코어 전부를 대입한다. 판정: 전부 승 `○` · 전부 패 `✗` ·
> 섞임 `△`. 🔴 *"죽는 시나리오"* 목록에는 **`✗` 와 `△` 를 둘 다** 적는다 —
> **`△` 가 있는데 "죽는 시나리오 없다"는 표기 금지.**
>
> **2-2 방향 판정은 등급과 분리, 항상 문장** — 블록 9 는 등급 유무와 무관하게
> 매 경기 한 줄. 홈승·원정승 중 큰 쪽이 **0.15 이상** 크면
> `방향: {팀 이름} — 홈승 x · 원정승 y · 무 z`, 미만이면
> `방향: 반반 — … 기울기는 {팀}`. 🔴 **"방향 없음" 문자열은 코드에서 제거.**

⚠️ 재서 확인한 것(2026-10-05): `survive.apply` 와 `passes` 는 **정확했다** —
   `E(2-1·1-0)` 가 `△ 0.5` 고 생존 `0.8462 = 11/13` 도 △ 를 반영했다. 블록 7
   표도 `○ ○ ○ ○ △ △` 로 바르게 찍었다.
🔴 **결함은 결론 줄의 `dead` 목록**이다 — `FAIL` 만 세어 `△` 둘을 빼고
   *"죽는 시나리오 없다"* 라고 적었다. 그것이 "소액"을 안전해 보이게 만든다.
"""
from __future__ import annotations

import ast
import inspect


def test_M102_다중_스코어가_전부_대입된다():
    """🔴 `1-0`·`0-1` 이 섞이면 오버 1.5 는 **`△`** 다(생존 1.0 아님)."""
    from app import survive
    from app.types import Market
    over15 = Market(market_type="total", line=1.5, team="over")
    sym, ratio, bad = survive.apply(over15, ["2-1", "1-0"],
                                    home="Indonesia", away="Thailand",
                                    sport="soccer")
    assert sym == survive.PART, f"🔴 E(2-1·1-0)가 `{sym}` 이다 — `△` 여야 한다"
    assert 0 < ratio < 1, ratio
    sym2, _r, _b = survive.apply(over15, ["1-1", "0-1"], home="Indonesia",
                                 away="Thailand", sport="soccer")
    assert sym2 == survive.PART, f"🔴 F(1-1·0-1)가 `{sym2}` 이다"
    # 🔴 **전부 지면 `✗`** — 섞임과 가른다
    sym3, _r, _b = survive.apply(over15, ["1-0", "0-1"], home="Indonesia",
                                 away="Thailand", sport="soccer")
    assert sym3 == survive.FAIL, sym3


def test_M103_죽는_목록에_부분도_들어간다():
    """🔴 *"`✗` 와 `△` 를 둘 다 적는다 — △ 가 있는데 '없다'는 금지"*."""
    from app import survive
    assert hasattr(survive, "dead_marks"), (
        "🔴 `survive.dead_marks(기호들)` 이 없다 — 죽는 목록을 세는 자리가 "
        "호출부마다 흩어진다(#1)")
    marks = {"A": survive.PASS, "B": survive.PASS, "C": survive.PASS,
             "D": survive.PASS, "E": survive.PART, "F": survive.PART}
    got = survive.dead_marks(marks, ["A", "B", "C", "D", "E", "F"])
    assert got == ["E(△)", "F(△)"], (
        f"🔴 `△` 를 죽는 목록에서 빼면 *'죽는 시나리오 없다'* 가 된다: {got}")
    marks2 = dict(marks, F=survive.FAIL)
    got2 = survive.dead_marks(marks2, ["A", "B", "C", "D", "E", "F"])
    assert got2 == ["E(△)", "F(✗)"], got2
    # 🔴 전부 통과면 **빈 목록**(그때만 "없다"다)
    allok = dict.fromkeys("ABCDEF", survive.PASS)
    assert survive.dead_marks(allok, list("ABCDEF")) == []




def test_M104_방향은_항상_한_줄이다():
    """🔴 등급과 **분리** — `"방향 없음"` 문자열은 코드에서 제거."""
    from app import survive
    assert hasattr(survive, "direction_line"), (
        "🔴 `survive.direction_line(홈승, 원정승, 무)` 이 없다")
    assert hasattr(survive, "DIR_GAP") and survive.DIR_GAP == 0.15, (
        "🔴 `survive.DIR_GAP = 0.15` 가 이름으로 없다(지시서 §2-2)")
    said = survive.direction_line(0.62, 0.23, 0.15, home="Indonesia",
                                  away="Thailand")
    assert "인도네시아" in said or "Indonesia" in said, said
    assert "0.62" in said and "0.23" in said, said
    # 🔴 **차이가 크면 "반반"이 아니다** — M104 가 그 길로 빠져나갔다:
    #    `gap >= DIR_GAP` 을 죽여도 반반 경로가 팀 이름을 내서 초록이었다.
    assert "반반" not in said, (
        f"🔴 홈승 0.62 vs 원정승 0.23(차이 0.39)인데 **반반**이라고 한다 — "
        f"문턱 {survive.DIR_GAP} 이 안 걸린다: {said}")
    # 🔴 차이가 0.15 미만이면 **반반** + 기울기
    near = survive.direction_line(0.40, 0.33, 0.27, home="Indonesia",
                                  away="Thailand")
    assert "반반" in near, near
    assert "Indonesia" in near or "인도네시아" in near, (
        f"🔴 반반인데 **기울기**를 안 적었다: {near}")







