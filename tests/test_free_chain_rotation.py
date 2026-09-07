"""무료 사슬 회전 — 판정만 한 모델, 나머지는 사슬 끝까지 (2026-09-07 실측).

🔴 "한 판정은 한 모델이 낸다"는 2026-09-05 안정성 규칙이다. 그 규칙이
   평의회·딥서치처럼 **판정이 아닌** 역할까지 묶고 있었다.

실측 2026-09-06 MLB #3725 평의회 심의:
  nemotron 이 JSON 대신 영어 사고문(2362자·2416자)을 두 번 냈고,
  뒤에 있던 groq×2·openrouter 후보를 **한 번도 안 가고** 포기했다.
  → 심의는 구조적으로 늘 빈 dict 였고 퍼플렉시티 조사비만 나갔다.
"""
from __future__ import annotations

import asyncio

import pytest

import app.engine.team_form as tf
from app.llm.judge_route import MATCHUP_ROLE, PRELIM_ROLE

CHAIN = [("nvidia", "nemotron"), ("groq", "qwen"), ("groq", "oss"),
         ("openrouter", "gemma")]
GOOD = '{"기전": "x", "방향": "home", "확실성": "중", "사유": "y"}'


def _fake(seq):
    """provider 별 응답을 정해 두고, 실제로 어떤 순서로 불렸는지 기록한다."""
    seen = []

    async def complete(provider, model, prompt, **kw):
        seen.append(f"{provider}/{model}")
        return {"ok": True, "text": seq.get(provider, "not json"),
                "error": None, "elapsed": 0.1, "usage": {}}

    return complete, seen


def _run(role, seq, monkeypatch):
    complete, seen = _fake(seq)
    import app.llm.openai_compat as oc

    monkeypatch.setattr(oc, "complete", complete)
    out = asyncio.run(tf._complete_free(CHAIN, "p", 500, role))
    return out, seen


def test_non_judgement_roles_rotate_to_the_end(monkeypatch):
    """평의회는 nemotron 이 막혀도 groq 까지 간다."""
    out, seen = _run("council", {"groq": GOOD}, monkeypatch)
    assert out == GOOD, "사슬 끝까지 안 갔다 — 심의가 또 빈 dict 가 된다"
    assert seen[0].startswith("nvidia") and any(x.startswith("groq") for x in seen)


def test_deepsearch_rotates_too(monkeypatch):
    out, _ = _run("deepsearch", {"openrouter": GOOD}, monkeypatch)
    assert out == GOOD


def test_form_rotates_too(monkeypatch):
    out, _ = _run("form", {"groq": GOOD}, monkeypatch)
    assert out == GOOD


@pytest.mark.parametrize("role", [MATCHUP_ROLE, PRELIM_ROLE])
def test_judgement_still_does_not_rotate(role, monkeypatch):
    """🔴 판정은 그대로다 — 같은 재료로 모델을 갈아타면 답이 회차마다 달라진다.

    실측 2026-09-05 KBO game=1713: 기아 0.440 → 0.590 → KT 0.450,
    50% 선을 두 번 넘었다. 그래서 회전을 없앤 것이다.
    """
    out, seen = _run(role, {"groq": GOOD}, monkeypatch)
    assert out is None, "판정이 provider 를 회전했다"
    assert all(x.startswith("nvidia") for x in seen), seen


def test_rotation_stops_at_the_first_usable_answer(monkeypatch):
    out, seen = _run("council", {"nvidia": GOOD, "groq": GOOD}, monkeypatch)
    assert out == GOOD and len(seen) == 1, "쓸 수 있는 답이 왔는데 더 불렀다"


def test_all_candidates_failing_returns_none(monkeypatch):
    out, seen = _run("council", {}, monkeypatch)
    assert out is None
    assert len({x.split("/")[0] for x in seen}) == 3, seen
