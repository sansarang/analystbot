"""③ **좁은 질문 추출기** 계약 (사용자 설계 2026-10-02).

> ③ 기사를 읽는다 — *"이 기사가 X 결장을 말하나?"* → 유형별 좁은 질문 →
> **yes/no/unknown + 본문 인용**, 인용이 원문에 실제로 있는지 **코드가 검사**

🔴 **모델을 부르지 않는 계약이다.** 로컬 모델 실측은 커밋 메시지와 `questions/` 에 적는다.
"""
from __future__ import annotations

import inspect

from app import extract, llm, rules, searchcells
from tests._helpers import strip_docs

DESIGNED = ("coach_conflict", "def_absence", "squad_rotation", "event_match",
            "national_duty_return")


def test_모델에게_던지는_질문과_코드의_판정_기준이_다르다():
    """🔴🔴 **실측이 만든 계약이다.**

    처음에 `decides`(*"결장 선수의 자리가 수비(DF·GK)다"*)를 그대로 물었더니 qwen3:8b 가
    **전부 `unknown`** 을 냈다 — 기준은 질문이 아니다. `asks` 를 따로 두니
    *"수비수나 골키퍼가 이 경기에 못 나온다고 적혀 있나?"* → **yes + 원문 인용**이 나왔다.
    """
    types = rules.variable_types()
    for t in DESIGNED:
        v = types[t]
        assert v.get("asks"), f"{t} 에 모델 질문(`asks`)이 없다"
        assert v.get("decides"), f"{t} 에 코드 판정 기준(`decides`)이 없다"
        # 🔴 **둘이 같으면 하나를 잘못 쓴 것이다**
        assert v["asks"] != v["decides"], t
        # ⚠️ 질문은 물음표로 끝난다 — 기준문을 잘못 넣는 것을 막는다
        assert str(v["asks"]).rstrip().endswith("?"), v["asks"]
    # 🔴 추출기가 `asks` 를 읽는다 — `decides` 가 아니다
    src = strip_docs(inspect.getsource(extract._ask_question))
    assert '"asks"' in src and '"decides"' not in src


def test_unknown_이_선택지에_있다():
    """🔴 `unknown` 이 **enum 에 있는 것이 핵심이다.** 없으면 7B 는 모르는 것도 `no` 로
    답하고, 그러면 *"기사에 없다"* 와 *"기사가 아니라고 말한다"* 가 섞인다."""
    enum = llm.ASK_TYPE["properties"]["answer"]["enum"]
    assert set(enum) == {"yes", "no", "unknown"}, enum
    # 🔴 `answer` 만 필수다 — `quote` 를 필수로 두면 `no` 를 낼 수 없다
    assert llm.ASK_TYPE["required"] == ["answer"]
    # 🔴 그리고 프롬프트가 *"없으면 unknown"* 을 못 박는다
    assert "unknown" in extract._ask_prompt("def_absence")


def test_yes_만_사실이_된다():
    """🔴 `no`·`unknown` 은 **사실이 아니고 사유다.** 섞으면 *"기사가 아니라고 했다"* 가
    변수가 된다."""
    assert extract._items("ASK:x", {"answer": "yes", "quote": "a"}) != []
    for bad in ("no", "unknown", "", None):
        assert extract._items("ASK:x", {"answer": bad}) == [], bad




def test_프롬프트가_짧다():
    """🔴🔴 **실측 2026-10-02: 프롬프트가 길면 7B 가 JSON 을 못 끝낸다.**

        qwen3:8b 실패: Unterminated string starting at line 3

    같은 스키마에 짧은 프롬프트를 주면 `{"answer": "yes"}` 가 바로 나왔다 —
    스키마 탓이 아니라 **내 프롬프트 탓**이었다.
    """
    got = extract._ask_prompt("def_absence")
    assert len(got.splitlines()) <= 4, got
    assert len(got) < 240, len(got)
    # 🔴 인용을 **한 문장**으로 못 박는다 — 긴 인용에서 토큰이 끊겼다
    assert "한 문장" in got
    # 🔴 좁은 질문은 **본문도 짧게** 준다
    assert extract.ASK_BODY_CHARS < extract.BODY_CHARS




def test_판정은_코드가_한다():
    """🔴 §17-c — LLM 은 `direction`·`weight`·`strength`·`survival`·`verdict` 에 닿지 않는다.

    ⚠️ 좁은 질문은 *"기사가 이 말을 하나"* 만 묻는다. 그것이 어느 방향인지는 §4 규칙이
       정한다 — 그래서 사실 값에 방향이 없다.
    """
    val = extract._value("ASK:def_absence",
                         {"answer": "yes", "quote": "q", "subject": "x"})
    for bad in ("direction", "weight", "strength", "survival", "verdict"):
        assert bad not in val, bad
    src = strip_docs(inspect.getsource(extract))
    for bad in ("direction", "weight", "strength", "survival", "verdict"):
        assert bad not in src, f"추출기 코드가 {bad} 를 건드린다"
