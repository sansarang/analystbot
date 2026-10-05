"""🔴🔴 **M102~M104 — 다중 스코어 대입·죽는 목록·방향 판정**.

지시서 `docs/fable/inbox/2026-10-05_workorder_idn_tha_fixes.md` §2.

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


def test_M103_카드가_그_목록을_쓴다():
    """🔴 **배선**(#2) — 결론 줄이 `dead_marks` 를 부른다."""
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "dead_marks" in called, (
        "🔴 카드가 `FAIL` 만 세어 `△` 를 빠뜨린다 — 실측 it4: "
        "`오버 1.5 (생존 0.8462) — 죽는 시나리오 없다` 인데 `△` 가 둘이었다")


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
    # 🔴 차이가 0.15 미만이면 **반반** + 기울기
    near = survive.direction_line(0.40, 0.33, 0.27, home="Indonesia",
                                  away="Thailand")
    assert "반반" in near, near
    assert "Indonesia" in near or "인도네시아" in near, (
        f"🔴 반반인데 **기울기**를 안 적었다: {near}")


def test_M104_방향_없음_이_블록9_에_없다():
    """🔴 *"'방향 없음' 문자열은 코드에서 제거한다"* — **블록 9 의 것**이다.

    ⚠️ `classify` 의 *"방향 없음"* 은 **뜻이 다르다** — 그 변수가 승패 방향을
       안 가리킨다는 §4 규칙 사유다(`event_match`·`national_duty_return`).
       🔴 지시서가 제거를 요구한 것은 **블록 9 가 찍는 글**이다.
    """
    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze))
    at = src.find("■ 9 방향 판정")
    assert at > 0, "🔴 블록 9 를 못 찾았다 — 이 계약을 고쳐라"
    seg = src[at:at + 1200]
    assert "방향 없음" not in seg, (
        "🔴 블록 9 가 아직 그 글을 찍는다 — 등급이 없어도 방향은 낸다(§2-2)")



def test_M104_시작한_경기도_방향_줄을_낸다():
    """🔴 *"시작한 경기(M97)도 방향 줄은 낸다 — 등급만 거둔다"*."""
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "direction_line" in called, (
        "🔴 카드가 `direction_line` 을 안 부른다 — 방향이 등급에 묶인다")
