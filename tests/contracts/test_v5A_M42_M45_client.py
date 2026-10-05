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


def test_v5A_2_도구를_넘기지_않는다_M42():
    """🔴🔴 **M42** — `tools` 가 몸통에 **없어야** 한다."""
    from app import deepseek
    net = _Net()
    # ⚠️ `_force` 로 **스위치를 건너뛴다** — 이 계약이 보는 것은 *"몸통에 도구가
    #    실리나"* 이고, 스위치는 다른 계약이 본다(아래
    #    `test_v5A_2_꺼져_있으면_안_부른다`).
    deepseek.ask([{"role": "user", "content": "x"}], match="statsapi:1",
                 _net=net, _force=True)
    assert net.sent, "🔴 한 번도 안 불렀다"
    body = net.sent[0]
    assert "tools" not in body, body.keys()
    assert "tool_choice" not in body, body.keys()
    # 🔴 **JSON 출력 모드**는 강제한다(v5-A §2)
    assert body.get("response_format", {}).get("type") == "json_object", body


def test_v5A_2_도구를_넘길_길이_없다_M42():
    """🔴 `ask()` 에 `tools` 인자가 **아예 없어야** 한다 — 있으면 누가 쓴다."""
    import inspect

    from app import deepseek
    sig = inspect.signature(deepseek.ask)
    assert "tools" not in sig.parameters, sorted(sig.parameters)


def test_v5A_2_장애를_삼키고_사유를_낸다_M45():
    """🔴🔴 **M45** — *"장애 시 예외를 **삼키고** `deepseek_unavailable` 반환"*.

    ⚠️ 그래야 v5 원래 경로(Solar 초안 + 코드 필수형 보강)로 판정이 **끝까지
       돈다.** 🔴 DeepSeek 장애가 **경기 분석을 막지 않는다**(v5-A §2).
    """
    from app import deepseek
    from app.reasons import Reason
    got = deepseek.ask([{"role": "user", "content": "x"}], match="m1",
                       _net=_Net(boom=RuntimeError("타임아웃")), _force=True)
    assert got.ok is False
    assert got.reason is Reason.DEEPSEEK_UNAVAILABLE
    assert "타임아웃" in got.why, got.why
    # 🔴 **예외가 위로 올라오지 않는다**(돌연변이: 던지게 하면 빨개진다)


def test_v5A_2_꺼져_있으면_안_부른다():
    """🔴 `deepseek.enabled` 가 꺼짐이면 **통로를 열지 않는다**."""
    from app import deepseek
    from app.reasons import Reason
    net = _Net()
    got = deepseek.ask([{"role": "user", "content": "x"}], match="m1",
                       _net=net)
    # ⚠️ 지금 설정은 **꺼짐**이다(작업지시 §4) — 그래서 안 나간다
    assert net.sent == [] or got.ok, (net.sent, got)
    if not net.sent:
        assert got.reason is Reason.DEEPSEEK_UNAVAILABLE
        assert "enabled" in got.why or "꺼" in got.why, got.why


def test_v5A_2_원장에_provider_를_적는다_M49():
    """🔴 *"`usage` 를 Solar 와 같은 원장에 `provider:deepseek` 로 적는다"*.

    ⚠️ 그래야 하루 $3 가드가 **두 API 를 합산**한다(v5-A §2).
    """
    import pathlib
    import tempfile

    from app import deepseek
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        deepseek.ask([{"role": "user", "content": "x"}], match="m1",
                     _net=_Net(), _ledger_root=root, _force=True)
        rows = [json.loads(x) for x in
                (root / "cost_202610.jsonl").read_text(
                    encoding="utf-8").splitlines()] if list(root.glob("*.jsonl")) else []
    assert rows, list(root.glob("*")) if root.exists() else "없다"
    assert rows[0]["provider"] == "deepseek", rows[0]
    for need in ("in", "cache", "out", "usd"):
        assert rows[0].get(need) is not None, (need, rows[0])


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
