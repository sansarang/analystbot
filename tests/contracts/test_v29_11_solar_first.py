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


def test_차례는_solar_가_먼저다() -> None:
    from app.core import llm
    assert llm.ORDER[0] == "solar", llm.ORDER
    assert "deepseek" in llm.ORDER, "🔴 퇴로를 지웠다 — solar 가 죽으면 멈춘다"


def test_deepseek_고정_호출이_app_에_없다() -> None:
    """🔴 한 공급자에 못을 박으면 그쪽이 죽을 때 그 단계가 통째로 멈춘다."""
    import pathlib
    bad = [str(f) for f in pathlib.Path("app").rglob("*.py")
           if 'provider="deepseek"' in f.read_text()]
    assert not bad, f"🔴 deepseek 고정 호출 — {bad}"


def test_차례를_도는_곳은_하나다() -> None:
    """🔴 사본 금지(#1) — 같은 고리를 단계마다 베끼지 않는다."""
    import pathlib
    from app.core import llm
    assert hasattr(llm, "ask_first"), "🔴 `llm.ask_first` 가 없다"
    users = [str(f) for f in pathlib.Path("app").rglob("*.py")
             if "ask_first(" in f.read_text() and f.name != "llm.py"]
    # 🔴 **채택자가 하나 줄었다** — `querywriter.ask`(딥서치 질의 쓰기)를
    #    지웠다(사용자 지시 2026-10-17 *"딥서치 삭제"*). 규칙은 그대로다:
    #    차례를 **베끼지 말고** `llm.ask_first` 를 쓴다.
    assert len(users) >= 2, f"🔴 배선이 덜 됐다 — {users}"
