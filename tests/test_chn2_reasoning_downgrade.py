"""CHN-2 — 400 강등은 **우리가 무엇을 보냈는지**로 판단한다. 응답 글자가 아니라.

운영 실측 2026-09-15 (gemini-3.5-flash-lite · OpenAI 호환 엔드포인트):
    reasoning_effort=none      400 "Request contains an invalid argument."
    reasoning_effort=low/minimal/필드없음   200
groq 는 400 본문에 필드명을 적어주고 gemini 는 안 적는다. 종전 조건
`"reasoning_effort" in r.text` 는 그 차이에 걸려 gemini 에서 강등을 못 했다.
`reasoning = role != "form"` 이므로 피해 범위는 **팀 폼 전건**이었다.
"""
from __future__ import annotations

import pytest

from app.llm import openai_compat as OC

GEMINI_400 = ('[{ "error": { "code": 400, '
              '"message": "Request contains an invalid argument.", '
              '"status": "INVALID_ARGUMENT" } }]')
GROQ_400 = ('{"error":{"message":"`reasoning_effort` must be one of '
            '`low`, `medium`, or `high`"}}')


class _R:
    def __init__(self, code, text, js=None):
        self.status_code, self.text, self._js = code, text, js
        self.headers = {}

    def json(self):
        return self._js


def _ok():
    return _R(200, "", {"choices": [{"message": {"content": '{"승자":"A"}'}}],
                        "usage": {"prompt_tokens": 9, "completion_tokens": 5}})


def _wire(monkeypatch, reject_when, body_text):
    """`reject_when(effort)` 이 참이면 400, 아니면 200. 보낸 body 를 모은다."""
    import httpx

    sent = []

    async def fake_post(self, url, json=None, headers=None, **kw):
        sent.append(dict(json or {}))
        eff = (json or {}).get("reasoning_effort")
        return _R(400, body_text) if reject_when(eff) else _ok()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    return sent


@pytest.mark.asyncio
async def test_400이_필드명을_말하지_않아도_강등한다(monkeypatch):
    sent = _wire(monkeypatch, lambda e: e == "none", GEMINI_400)
    r = await OC.complete("gemini", "gemini-3.5-flash-lite", "p",
                          max_tokens=1500, reasoning=False)
    assert r["ok"] is True, "gemini 400 에서 강등하지 않았다"
    assert [s.get("reasoning_effort") for s in sent] == ["none", "low"]


@pytest.mark.asyncio
async def test_필드명을_말해주는_400도_그대로_강등한다(monkeypatch):
    """⚠️ groq 경로가 바뀌지 않았다는 확인."""
    sent = _wire(monkeypatch, lambda e: e == "none", GROQ_400)
    r = await OC.complete("groq", "openai/gpt-oss-120b", "p",
                          max_tokens=1500, reasoning=False)
    assert r["ok"] is True
    assert [s.get("reasoning_effort") for s in sent] == ["none", "low"]


@pytest.mark.asyncio
async def test_보내지_않은_필드로는_강등하지_않는다(monkeypatch):
    """🔴 반대 위험 — 400 을 전부 강등으로 읽으면 모델명 오타를 세 번 더 때린다."""
    sent = _wire(monkeypatch, lambda e: True, '{"error":"model not found"}')
    r = await OC.complete("gemini", "없는모델", "p", max_tokens=1500,
                          reasoning=True)          # reasoning_effort 를 안 보낸다
    assert r["ok"] is False
    assert all("reasoning_effort" not in s for s in sent)
    assert len(sent) == 1, f"400 인데 재시도했다: {len(sent)}회"


def test_강등_사다리_순서는_그대로다():
    """사다리를 새로 만들지 않았다 — 마지막은 **필드 제거**다."""
    seen, cur = [], "none"
    while (nxt := OC._next_reasoning(cur)) is not None:
        seen.append(nxt)
        cur = nxt
    # 원본은 `_REASONING_OFF` 다 — 여기 값을 손으로 옮겨 적지 않는다.
    assert seen == list(OC._REASONING_OFF[1:]), seen
    assert OC._next_reasoning(seen[-1]) is None, "마지막 뒤에는 필드 제거다"
