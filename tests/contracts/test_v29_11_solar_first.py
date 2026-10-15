"""🔴🔴 **① 이름 풀이와 딥서치 질의는 solar 가 먼저다** — 지시 2026-10-15.

> 1을 솔라로 바꿔라 / 딥서치도 솔라가 우선되게 바꿔라

⚠️ 실측 2026-10-15: deepseek 가 `"Say OK"` 3토막 요청에도 **59.3초 읽기
   타임아웃**이었다(solar 는 **0.5초**). 그 멈춤이 카드 예산을 태워 ③·④·⑯ 가
   **빈손 8개**가 됐고, ① 에서는 13분을 버렸다.
"""
from __future__ import annotations

import inspect


def test_일단_이름_풀이는_solar_다() -> None:
    from app.core import findwriter
    src = inspect.getsource(findwriter.ask)
    assert 'provider="solar"' in src, "🔴 ① 이 solar 가 아니다"
    assert 'provider="deepseek"' not in src, "🔴 deepseek 가 남아 있다"


def test_딥서치_질의는_solar_가_먼저다() -> None:
    from app.core import querywriter
    src = inspect.getsource(querywriter)
    at_s = src.find('"solar"')
    at_d = src.find('"deepseek"')
    assert at_s >= 0 and at_d >= 0, "🔴 공급자 둘이 다 있어야 한다(퇴로)"
    assert at_s < at_d, "🔴 solar 가 먼저가 아니다"
    assert 'for pv in ("solar", "deepseek")' in src, "🔴 퇴로가 고리로 안 돈다"


def test_퇴로를_지운_것이_아니다() -> None:
    """🔴 solar 가 죽으면 deepseek 로 간다 — 한쪽만 남기면 또 멈춘다."""
    from app.core import querywriter
    src = inspect.getsource(querywriter)
    assert src.count('llm.ask(provider=pv') == 1, "🔴 공급자를 고리로 안 돈다"
