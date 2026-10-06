"""🔴🔴 **v5-A §2 클라이언트 — M42(웹 차단) · M45(장애 시 원래 경로).**

v5-A §5 표:

| 번호 | 계약 | 돌연변이 |
|---|---|---|
| **M42** | DeepSeek 호출에 `tools` 를 **넘기지 않는다**(웹 차단) | `tools` 에 `search` 하나 넣기 |
| **M45** | DeepSeek 장애 시 v5 원래 경로로 판정이 **끝까지 돈다**(`deepseek_unavailable`) | 장애 시 예외를 위로 던지기 |

══════════════════════════════════════════════════════════════════
🔴 왜 웹을 막나 — **검색은 Solar 자리다**(v5-A §1)
══════════════════════════════════════════════════════════════════

> 검색·본문 읽기·변수 추가 — **Solar 자리**다. DeepSeek 가 새 사실을 말하면
> 그 시나리오는 폐기(§5 M41).

⚠️ DeepSeek 에 `Tool Calls ✓` 가 있다(공식 문서). 🔴 **있어도 쓰지 않는다** —
   쓰면 그 출력이 검증층을 안 지난 사실을 들고 온다.
"""
from __future__ import annotations

import json

import pytest


class _Net:
    """🔴 대역 — 보낸 몸통을 적는다."""

    def __init__(self, reply=None, boom: Exception | None = None):
        self.sent: list[dict] = []
        self.reply = reply or {"choices": [{"message": {"content": "{}"}}],
                               "usage": {"prompt_tokens": 10,
                                         "completion_tokens": 5}}
        self.boom = boom

    def __call__(self, base_url, key, body, timeout, retries):
        self.sent.append(body)
        if self.boom is not None:
            raise self.boom
        return self.reply






    # 🔴 **예외가 위로 올라오지 않는다**(돌연변이: 던지게 하면 빨개진다)






def test_v5A_8_6_사유_여섯이_있다():
    """🔴 작업지시 §4-6 — 사유 **여섯 종**을 §8-6 enum 에."""
    from app.reasons import SAY, Reason
    want = ("UNKNOWN_VAR", "NEW_FACT", "REDTEAM_SKIPPED", "REDTEAM_OVERRULED",
            "DEEPSEEK_UNAVAILABLE", "DEEPSEEK_MISSED_REQUIRED")
    for name in want:
        assert hasattr(Reason, name), [r.name for r in Reason]
        r = getattr(Reason, name)
        assert r.fix_where and r.kind in ("ask", "bug", "verdict", "none")
        assert str(SAY.get(r) or "").strip(), name


@pytest.mark.parametrize("name", ["UNKNOWN_VAR", "NEW_FACT"])
def test_v5A_8_6_폐기_사유는_우리_것이_아니다(name):
    """⚠️ `unknown_var`·`new_fact` 는 **모델이 규격을 벗어난 것**이다.

    🔴 `fix_where` 는 `에이전트` 다 — 우리 코드도 자료도 아니다(§8-6).
    """
    from app.reasons import Reason
    r = getattr(Reason, name)
    assert r.fix_where == "에이전트", (name, r.fix_where)
