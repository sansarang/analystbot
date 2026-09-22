"""[NAR-2] ⑫가 **없는 함수**를 부르고 있었다 — 서술이 언제나 실패한다.

🔴 실측 2026-09-19 (운영 컨테이너에서 ⑫ 직접 실행):
     [flow:n12] 서술 실패: cannot import name 'complete_text'
                from 'app.llm.provider'
     [flow:n12] game=10098 규격 미달 (문장 0 · 지어낸 숫자 [])
     시도 2 · 환각 True · 문장 0
   두 번 다 같은 ImportError 로 죽고 `hallucination=True` 가 된다.
   **⑫가 카드를 만들 수 있었던 적이 없다.**
🔴 드러나지 않은 이유: 흐름이 ⑥(`n06_unknown`)에서 멈춰 ⑫까지 간 적이 없다.
   "배포했고 테스트가 통과한다"가 동작의 증거가 아니라는 예다.

⚠️ 진짜 API 는 `provider.complete(role, messages, ...) -> LLMResult` 다.
   `narrator` 는 이미 등록된 역할이다(`provider.ROLES`).
"""
from __future__ import annotations

import inspect

import pytest


# ── [SWAP-3T 2026-09-22] 이 파일은 **LLM 서술 경로**를 시험한다 ────────────
#
# 🔴 사용자 지시로 서술이 **템플릿**이 됐다("서술도 템플릿으로 바꿔라").
#    `judge.llm_verdict` 가 꺼져 있으면 ⑫가 LLM 을 아예 안 부르므로
#    이 파일의 시험 대상 경로가 돌지 않는다.
# 🔴 **그 경로를 지우지 않았다** — 스위치 한 줄로 되돌릴 수 있어야 하고,
#    되돌렸을 때 종전대로 도는지는 **계약이 지켜야 한다.**
# ⚠️ 템플릿 동작은 `tests/test_nollm.py` 가 따로 잠근다.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _llm_verdict_on(monkeypatch):
    monkeypatch.setattr("app.engine.matchup._llm_verdict_on", lambda: True)


def _body(fn) -> str:
    """주석을 뺀 본문. 🔴 설명문에 적힌 이름이 계약을 통과/실패시키면 안 된다 —
    이 세션에서 같은 실수를 네 번 했다."""
    out = []
    for line in inspect.getsource(fn).splitlines():
        t = line.split("#", 1)[0]
        if t.strip():
            out.append(t)
    return "\n".join(out)


def test_있는_함수를_부른다():
    from app.flow.nodes import n12_text as N
    from app.llm import provider as P

    src = _body(N._ask)
    assert "complete_text" not in src, "없는 함수를 부른다"
    assert "import complete" in src
    assert hasattr(P, "complete"), "provider 에 complete 가 없다"
    assert not hasattr(P, "complete_text"), "provider 가 complete_text 를 내놓는다"


def test_narrator_역할을_쓴다():
    """🔴 판정 역할(judge_*)을 쓰면 서술이 판정 예산을 먹는다."""
    from app.flow.nodes import n12_text as N
    from app.llm.provider import ROLES

    assert '"narrator"' in _body(N._ask)
    assert "narrator" in ROLES


@pytest.mark.asyncio
async def test_호출이_실패해도_예외를_올리지_않는다():
    """⚠️ 사슬이 죽어도 흐름이 죽으면 안 된다 — 서술 실패 태그로 끝난다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n12_text as N
    from app.flow.state import State

    s = State(run_id="r", game_id="1", sport="baseball", league="MLB",
              home="H", away="A", kickoff_utc="2026-09-19T01:40:00Z")
    s.n08_pcode = {"p_code_pick": 0.6}
    s.n09_conf = {"grade": "B"}
    s.n11_value = {"pick_type": "보드"}
    out = await N.run(s, Ctx(inject={"narration": ""}))
    assert out.n12_text["hallucination"] is True
    assert out.n12_text["sentences"] == []


# ── [NAR-2b] 추론 모델 토큰 여유 · 빈손 폴백

def test_토큰_여유가_추론_모델_몫을_포함한다():
    """🔴 실측: `openai/gpt-oss-120b` 는 추론 모델이다.
         max_tokens=600  → reasoning 598 · content **0자**
         max_tokens=2000 → 4문장 정상
       줄이면 서술이 **조용히 0건**이 된다."""
    from app.flow.nodes.n12_text import NARRATE_MAX_TOKENS

    assert NARRATE_MAX_TOKENS >= 1500, NARRATE_MAX_TOKENS


def test_빈손이면_객체표현을_서술로_쓰지_않는다():
    """🔴 `str(res)` 를 돌려주면
       "LLMResult(text='', data=None, provider='groq', ...)" 가 서술로 둔갑한다.
       빈손은 빈손이어야 ⑫가 `hallucination` 으로 정직하게 끝난다."""
    from dataclasses import dataclass

    from app.flow.nodes.n12_text import _text_of

    @dataclass
    class _R:
        text: str = ""
        provider: str = "groq"

    assert _text_of(_R()) == ""
    assert _text_of(None) == ""
    assert _text_of(_R(text="네 문장.")) == "네 문장."
