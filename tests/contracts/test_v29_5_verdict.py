"""🔴🔴 **⑯ 종합 평 계약** — 사용자 지시 2026-10-15.

> **16단계가 마지막이다** · llm **solar** 가 종합 평을 낸다 · deepseek…
> **확률 먼저** · 변수가 이래케 저렇게 되서 이렇게 나온다 · **코드 만으로** ·
> solar **지어냈는지 안지어냈는지 결론내다**

지키는 것:
  VD1 공급자가 **solar** 다(앞 단계 deepseek 와 다르다)
  VD2 출력 칸에 **확률·등급이 없다**(모델이 수를 못 바꾼다)
  VD3 입력 묶음은 **코드가 만든다** — `chain_of` 에 LLM 호출이 없다
  VD4 묶음 **첫 줄이 확률**이다(지시: *"확률 먼저"*)
  VD5 🔴🔴 **지어낸 수를 잡는다**
  VD6 🔴🔴 **지어낸 스코어를 잡는다**(전에 이 단계를 지운 그 사고)
  VD7 멀쩡한 평은 **안 지어냈다**로 지난다(거짓 위반이 없다)
  VD8 평이 없으면 **못 쟀다** — `안 지어냈다`로 넘기지 않는다
  VD9 🔴🔴 **지어낸 규칙 번호를 잡는다**(실사고 2026-10-15 `[IR14]`)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s6_verdict.py"


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def _body(name: str) -> str:
    code = _code(MOD)
    i = code.index(f"def {name}(")
    j = code.find("\ndef ", i + 10)
    return code[i:j if j > i else len(code)]


class _P:
    """🔴 `ProbOut` 의 **최소 모양** — 계약이 보는 칸만."""

    home, draw, away = 0.531, 0.258, 0.211
    lam = {"home": 1.537, "away": 0.869}
    over = {"1.5": 0.77, "2.5": 0.53}
    scores = {"1-1": 0.121, "1-0": 0.084}
    share = {"axis1": 0.013}
    share_refs = {}
    why = "축 종합 -0.640 × β 0.25 → λ 이동 홈 -0.207"
    gap = ""


def test_vd1_provider_is_solar() -> None:
    """VD1 — **solar** 다."""
    said = _body("ask")
    assert 'provider="solar"' in said, (
        "VD1 🔴 공급자가 solar 가 아니다 — 지시 2026-10-15(*\"llm solar 가 종합 "
        "평을 낸다\"*). ⚠️ 앞 단계는 deepseek 이고, 작성자와 검열자를 같은 "
        "모델로 두지 않는 규율과 같은 뜻이다")


def test_vd2_output_has_no_numbers() -> None:
    """VD2 — 출력 칸에 **확률·등급이 없다**."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict
    got = set(Verdict.model_fields)
    assert got == {"sentences", "refs"}, (
        f"VD2 🔴🔴 출력 칸이 {sorted(got)} 다 — `sentences`·`refs` 둘이어야 "
        "한다. 확률 칸을 두면 모델이 코드가 정한 수를 덮을 길이 열린다")


def test_vd3_bundle_is_code_only() -> None:
    """VD3 — 묶음을 만드는 함수에 **LLM 호출이 없다**(지시: *"코드 만으로"*)."""
    said = _body("chain_of")
    for bad in ("llm", "ask(", "provider"):
        assert bad not in said, (
            f"VD3 🔴🔴 `chain_of` 가 `{bad}` 를 쓴다 — 묶음에 모델 글자가 섞이면 "
            "*\"코드 만으로\"* 가 깨지고, 지어냄 판정의 기준 자체가 오염된다")


def test_vd4_probability_first() -> None:
    """VD4 — 묶음 **첫 줄이 확률**이다(지시: *"확률 먼저"*)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s6_verdict as vd

    class _R:
        home = away = "t"
        home_name = "A"
        away_name = "B"
        competition = "c"
    box = vd.chain_of(_R(), _P(), None, None)
    assert box, "VD4 🔴 묶음이 비었다"
    assert box[0].startswith("확률"), (
        f"VD4 🔴 첫 줄이 확률이 아니다 — {box[0][:60]!r}")
    assert "53.1%" in box[0], f"VD4 🔴 확률 수가 안 들어갔다 — {box[0]}"


def test_vd5_catches_invented_number() -> None:
    """VD5 🔴🔴 — 묶음에 **없는 수**를 잡는다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    box = ["확률 — 홈 53.1% · 무 25.8% · 원정 21.1%"]
    got = Verdict(sentences=["홈이 53.1% 로 앞선다.",
                             "원정은 **88.8%** 의 확률로 진다.",
                             "그래서 홈이 유리하다."],
                  refs=["확률", "확률", "확률"])
    verdict, bad = judge(got, box)
    assert verdict == "지어냈다", f"VD5 🔴🔴 없는 수(88.8)를 통과시켰다 — {bad}"
    assert any("88.8" in x for x in bad), f"VD5 🔴 그 수를 안 지목했다 — {bad}"


def test_vd6_catches_invented_scoreline() -> None:
    """VD6 🔴🔴 — **스코어 꼴**을 잡는다.

    ⚠️ 이 단계를 전에 지운 까닭이 그것이었다(커밋 `a7448733`): 평이 근거에 없는
       **4-3** 을 적었고 수치 검사는 `4`·`3` 낱개로 쪼개져 **못 잡았다**.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    # 🔴 묶음에 4 와 3 이 **둘 다 있다** — 그래도 `4-3` 은 없다
    box = ["스코어 상위 — 1-1 12.1% · 1-0 8.4%",
           "λ(기대 득점) — 홈 4.000 · 원정 3.000"]
    got = Verdict(sentences=["홈 λ 가 4.000 이다.", "원정 λ 는 3.000 이다.",
                             "**4-3** 으로 끝날 것이다."],
                  refs=["λ", "λ", "스코어"])
    verdict, bad = judge(got, box)
    assert verdict == "지어냈다", (
        f"VD6 🔴🔴 `4-3` 을 통과시켰다 — 묶음에 4 와 3 이 낱개로 있어서 수치 "
        f"검사만으로는 못 잡는다. 그것이 이 단계를 지운 사고다. {bad}")
    assert any("4-3" in x for x in bad), f"VD6 🔴 스코어를 안 지목했다 — {bad}"


def test_vd7_clean_passes() -> None:
    """VD7 — 멀쩡한 평은 지난다(거짓 위반이 없다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    box = ["확률 — 홈 53.1% · 무 25.8% · 원정 21.1%",
           "λ(기대 득점) — 홈 1.537 · 원정 0.869 · 합 2.406",
           "스코어 상위 — 1-1 12.1%"]
    got = Verdict(sentences=["홈이 53.1% 로 앞선다.",
                             "λ 는 홈 1.537 · 원정 0.869 이다.",
                             "1-1 이 12.1% 로 가장 두껍다."],
                  refs=["확률", "λ", "스코어"])
    verdict, bad = judge(got, box)
    assert verdict == "안 지어냈다", (
        f"VD7 🔴 멀쩡한 평에 거짓 위반이 났다 — {bad}")


def test_vd8_no_essay_is_not_pass() -> None:
    """VD8 — 평이 없으면 **못 쟀다**(통과로 넘기지 않는다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import judge
    verdict, bad = judge(None, ["확률 — 홈 50%"])
    assert verdict == "못 쟀다", (
        f"VD8 🔴 평이 없는데 `{verdict}` 로 적었다 — *'안 지어냈다'* 와 "
        "*'쓸 평이 없다'* 는 다른 말이다(#3)")
    assert bad, "VD8 🔴 사유가 없다"


def test_vd9_catches_invented_rule_id() -> None:
    """VD9 🔴🔴 — **없는 규칙 번호**를 잡는다(사용자 지시 2026-10-15 (가)).

    ⚠️ 실사고 2026-10-15(코모): solar 가 *"**[IR14]**로 원정 λ가 0.95배로
       깎여"* 라고 썼다. 🔴 묶음에 `IR14` 글자가 **0건**이었다(그 변수는 자리가
       `['V2','hypo']` 라 묶음에 안 들어갔고 λ 보정도 안 걸렸다). 즉 **없는
       규칙 효과를 지어냈다** — 그런데 (가)(나)(다)는 숫자·스코어·이름만 보므로
       **통과시켰다**.
    🔴 그래서 (라) 번호 검사를 더했다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    # 🔴 묶음에 `T3` 는 있고 `IR14` 는 **없다**
    box = ["확률 — 홈 42.7% · 무 24.4% · 원정 32.8%",
           "λ 유도(코드 글자) — 규칙(축 안에서 셌다) [T3] home λ +5%"]
    got = Verdict(sentences=["홈 42.7% 다.",
                             "[T3] 가 홈 λ 를 밀었다.",
                             "[IR14] 가 원정 λ 를 깎았다."],
                  refs=["확률", "λ", "λ"])
    verdict, bad = judge(got, box)
    assert verdict == "지어냈다", f"VD9 🔴🔴 `[IR14]` 를 통과시켰다 — {bad}"
    assert any("IR14" in x for x in bad), f"VD9 🔴 그 번호를 안 지목했다 — {bad}"
    # 🔴 묶음에 **있는** 번호(`T3`)는 **거짓 위반이 없어야** 한다
    assert not any("T3" in x and "없는" in x for x in bad), (
        f"VD9 🔴 묶음에 있는 `T3` 를 없다고 했다 — {bad}")
