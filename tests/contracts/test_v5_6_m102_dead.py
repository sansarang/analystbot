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


# ⚠️ **걷은 시험** — `survive.direction_line`·`dead_marks` 가 §1 처분
#    (2026-10-12 셋째)으로 지워졌다: 방향은 `pipeline._direction` 이 확률로
#    적고, *죽는 목록*(시나리오 기호)은 격자에 없는 개념이다.
#    걷은 시험: `test_M103_죽는_목록에_부분도_들어간다`

# ⚠️ **걷은 시험** — `survive.direction_line`·`dead_marks` 가 §1 처분
#    (2026-10-12 셋째)으로 지워졌다: 방향은 `pipeline._direction` 이 확률로
#    적고, *죽는 목록*(시나리오 기호)은 격자에 없는 개념이다.
#    걷은 시험: `test_M104_방향은_항상_한_줄이다`
