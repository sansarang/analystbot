"""[DS-10] 종합 판단 — 카드 마지막에 "그래서 누가 이긴다"를 남긴다.

🔴 사용자 지적: "분석은 다 됐어. 그래서 종합평가는? 그래서 이렇게 됐으니 누가
   이길 것이라는 서술이 있어야 해." 그리고 "자료가 사용자가 선택하게 하지 말고
   결정은 AI 가 다 해야 한다."

실측(TB@ATL): 결론(원정 승)과 심의(홈 강화)가 정면 충돌하는데 아무도 정리하지
않아 사용자가 여섯 조각을 들고 스스로 판단해야 했다.

🔴 뼈대는 **규칙**으로 조립한다(지어내기 불가). 마지막 실전 판단 한 줄만 LLM.
"""
from __future__ import annotations

import pytest

from app.engine.synthesis import synthesize


def _jg(**over):
    jg = {
        "sport": "mlb", "home": "Atlanta Braves", "away": "Tampa Bay Rays",
        "p_claude": 0.47, "p_market_send": 0.53,
        "matchup": {"p_home": 0.47, "우세": "away", "확신도": "하",
                    "결론": {"승자": "Tampa Bay Rays"},
                    "전개": {"분기점": "로페즈가 몇 이닝 버티나"}},
        "deepsearch": {"요약": "로페즈 IL 복귀 활성화", "이동_pp": 1.0},
        "situation_check": {"direction": "home", "verdict": "뒷받침"},
    }
    jg.update(over)
    return jg


def test_synthesis_states_a_winner():
    """종합은 반드시 **누가 이기는지**를 말한다."""
    out = synthesize(_jg())
    assert out is not None
    assert "탬파베이" in out or "Tampa" in out, out


def test_synthesis_carries_numbers_from_values_not_invention():
    """확률·이동·시장 괴리는 **값에서** 온다 — 지어내지 않는다."""
    out = synthesize(_jg())
    assert "53" in out                     # 우세팀 확률 53%
    assert "+1.0%p" in out or "1.0%p" in out   # 조사 이동
    assert "6" in out                      # 시장 괴리 6%p대


def test_synthesis_flags_contradiction():
    """결론과 심의가 반대면 **모순을 명시**한다 — 침묵하지 않는다."""
    out = synthesize(_jg())
    assert "반대" in out or "충돌" in out or "엇갈" in out, out


def test_synthesis_notes_what_breaks_the_pick():
    """무엇이 이 픽을 깨는지(갈림길)를 실전 문장으로 남긴다."""
    out = synthesize(_jg())
    assert "로페즈" in out


def test_synthesis_none_without_verdict():
    """판정이 없으면 종합도 없다 — 없는 것을 지어내지 않는다."""
    assert synthesize({"sport": "mlb", "home": "H", "away": "A"}) is None


def test_synthesis_agreement_is_not_called_contradiction():
    """심의가 결론과 같은 방향이면 모순이라 하지 않는다."""
    jg = _jg(situation_check={"direction": "away", "verdict": "뒷받침"})
    out = synthesize(jg)
    assert "반대" not in out


# ── [DS-11 2026-09-10 사용자 지시] 심의 동의도 명시 + LLM 판단 한 줄 ───────

def test_agreement_is_stated_not_silent():
    """🔴 사용자 지시: "심의가 같은 방향일 때도 명시해라."

    실측(CHC@MIL): 심의가 결론과 같은 방향(홈 뒷받침)이라 종합이 **침묵**했다.
    침묵은 고려가 아니다 — 사용자가 "심의를 봤는지" 알 수 없다.
    """
    jg = _jg(situation_check={"direction": "away", "verdict": "뒷받침"})
    out = synthesize(jg)
    assert "현지 상황" in out, out
    assert "뒷받침" in out or "지지" in out or "같은" in out, out


def test_contradiction_still_flagged():
    """반대일 때는 여전히 모순으로 명시한다(DS-10 계약 유지)."""
    out = synthesize(_jg())          # 결론 away · 심의 home
    assert "반대" in out


@pytest.mark.asyncio
async def test_llm_verdict_line_is_appended(monkeypatch):
    """🔴 사용자 지시: "붙여라."

    규칙 뼈대만으로는 값을 옮길 뿐 **견줘본 판단**이 없다(실측: 종합이 갈림길·
    조사 문장을 통째로 재인용했다). 마지막 한 줄만 LLM 이 쓴다.
    ⚠️ 숫자는 여전히 규칙이 만든다 — LLM 은 판단 문장만 덧붙인다.
    """
    from app.engine import synthesis as syn

    async def fake(prompt, **kw):
        assert "갈림길" in prompt and "심의" in prompt, "견줄 재료가 안 들어갔다"
        return "근거가 갈림길의 답을 이미 갖고 있어 확률을 신뢰할 만하다."

    monkeypatch.setattr(syn, "_verdict_line", fake)
    out = await syn.synthesize_async(_jg())
    assert "→ " in out, out
    assert "갈림길의 답" in out


@pytest.mark.asyncio
async def test_llm_failure_keeps_the_rule_skeleton(monkeypatch):
    """LLM 이 죽어도 규칙 뼈대는 그대로 나간다 — 회귀 없음."""
    from app.engine import synthesis as syn

    async def dead(prompt, **kw):
        return None

    monkeypatch.setattr(syn, "_verdict_line", dead)
    out = await syn.synthesize_async(_jg())
    assert out.startswith("🧭 종합 —")
    assert "→ " not in out


def test_verdict_prompt_asks_for_json():
    """🔴 실측 2026-09-10: LLM 이 좋은 문장을 냈는데 **버려졌다.**
        groq: "근거와 조사가 헨더슨의 안정성을 일관되게 지지해 57% 확률은
               신뢰할 만하나, 불펜 피로라는 미확인 변수가 유일한 발목이다."
        [deepsearch] 응답이 JSON 이 아니다 (69자) → 무료 사슬 실패

    `_complete_free` 는 **JSON 파싱까지가 성공 조건**이다(의도된 설계 —
    Nemotron 이 영어 사고문을 돌려주는 회차를 걸러내려고 그렇게 만들었다).
    평문 한 문장을 요구한 내 프롬프트가 그 계약과 어긋났다.
    """
    from app.engine.synthesis import _verdict_prompt

    p = _verdict_prompt(_jg())
    assert "JSON" in p, "JSON 을 요구하지 않으면 무료 사슬이 응답을 버린다"
    assert "판단" in p


@pytest.mark.asyncio
async def test_verdict_line_parses_json(monkeypatch):
    """JSON 으로 와도 문장만 뽑아 쓴다."""
    from app.engine import synthesis as syn
    from app.engine import team_form

    async def fake_complete(routes, prompt, max_tokens, role):
        return '{"판단": "근거와 조사가 서로를 지지해 확률을 믿을 만하다"}'

    from app.llm import judge_route

    monkeypatch.setattr(team_form, "_complete_free", fake_complete)
    monkeypatch.setattr(judge_route, "chain", lambda role: [("groq", "m")])
    line = await syn._verdict_line("prompt")
    assert line == "근거와 조사가 서로를 지지해 확률을 믿을 만하다"


def test_verdict_uses_the_judge_chain_gemini_first():
    """🔴 사용자 지시 2026-09-10: "최종 결론 글도 gemini로 해라."

    종합은 카드의 **마지막 판단**이다. 조사 요약(deepsearch 역할, nvidia 우선)이
    아니라 최종 판정과 같은 사슬(matchup, gemini 우선)을 써야 격이 맞는다.
    실측: deepsearch 사슬은 nvidia → groq → openrouter 이고 gemini 가 없다.
    """
    from app.engine.synthesis import VERDICT_ROLE

    assert VERDICT_ROLE == "matchup"


@pytest.mark.asyncio
async def test_verdict_never_falls_back_to_paid(monkeypatch):
    """⚠️ matchup 은 **유료(anthropic)가 허용되는 유일한 역할**이다.
    종합이 그 문을 타면 카드 한 줄에 유료 호출이 붙는다 — 무료만 남긴다."""
    from app.engine import synthesis as syn
    from app.llm import judge_route

    seen = {}

    async def spy(routes, prompt, max_tokens, role):
        seen["routes"] = routes
        return '{"판단": "ok"}'

    monkeypatch.setattr(judge_route, "chain",
                        lambda role: [("anthropic", "claude"), ("gemini", "g")])
    from app.engine import team_form
    monkeypatch.setattr(team_form, "_complete_free", spy)
    await syn._verdict_line("p")
    assert all(p != "anthropic" for p, _ in seen["routes"]), seen["routes"]
