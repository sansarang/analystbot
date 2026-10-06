"""🔴🔴 **블록 9 방향 줄은 까닭을 지어내지 않는다** — §8-6.

⚠️ 실측 2026-10-06(북아일랜드–조지아 재실행): 시나리오 **7개**가 선 카드에서
   블록 9 가 *"시나리오가 없어 승패 확률이 서지 않았다"* 라고 적었다.

🔴 `direction_line` 은 **확률 셋만** 받는다 — 시나리오가 몇 개인지 **모른다.**
   모르는 것을 까닭으로 적으면 그것이 거짓 사유다(§8-6). 그 수는 카드가
   옆줄에 적는다(`_dir_block`).
"""
from __future__ import annotations

import inspect

from app import survive


def test_방향_줄이_모르는_까닭을_적지_않는다():
    said = survive.direction_line(0.0, 0.0, 0.0, home="A", away="B")
    assert "못 쟀다" in said, said
    assert "반반이 아니다" in said, said
    # 🔴 **시나리오 수를 모르면서** 그것을 까닭으로 적지 않는다
    assert "시나리오" not in said, (
        "🔴 `direction_line` 이 *'시나리오가 없어'* 라고 적는다 — 이 함수는 "
        f"시나리오 수를 **받지 않는다**(§8-6 거짓 사유): {said}")
    # 🔴 **인자가 셋뿐인지** 확인한다 — 받지도 않는 것을 말하지 못하게
    sig = inspect.signature(survive.direction_line)
    pos = [n for n, pr in sig.parameters.items()
           if pr.kind is not pr.KEYWORD_ONLY]
    assert len(pos) == 3, (
        f"🔴 인자가 늘었다 — 시나리오 수를 받게 됐다면 까닭을 적어도 된다: {pos}")


