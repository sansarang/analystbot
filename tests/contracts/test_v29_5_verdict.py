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
    """VD1 — 기본 공급자가 **solar** 다. ⚠️ 바꿀 수 있지만 **기본값**은 solar.

    🔴 지시 2026-10-15 — *"llm solar 가 종합 평을 낸다"*(기본) 그리고
       *"solar 서술형 카드와 deepseek 서술형 카드 **동시에** 보여주라"*(비교).
       그래서 `provider` 를 **인자로** 받되 기본값은 solar 여야 한다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    import inspect
    from app.core.stages import s6_verdict as vd
    sig = inspect.signature(vd.ask)
    said = sig.parameters.get("provider")
    assert said is not None, "VD1 🔴 `provider` 인자가 없다 — 두 모델 비교 불가"
    assert said.default == "solar", (
        f"VD1 🔴 기본 공급자가 `{said.default}` 다 — solar 여야 한다"
        "(지시 2026-10-15)")
    # 🔴 같은 묶음을 **그대로** 넘길 길이 있어야 비교가 뜻을 갖는다
    assert "box" in sig.parameters, (
        "VD1 🔴 `box` 인자가 없다 — 두 모델이 **같은 입력**을 못 받는다")


def test_vd2_output_has_no_numbers() -> None:
    """VD2 — 출력 칸에 **확률·등급이 없다**."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict
    got = set(Verdict.model_fields)
    # 🔴🔴 **예측 칸 둘을 더했다**(사용자 지시 2026-10-15) — *"변수 경기 관련으로
    #    예측을 각각 하라"*. ⚠️ 그래도 **수 칸은 없다**: `pick` 은 셋 중 한 글자,
    #    `score` 는 **묶음의 스코어 상위에 있는 것**이고 코드가 대조한다.
    #    확률·등급 칸을 두면 모델이 코드가 정한 수를 덮을 길이 열린다 — 그건 여전히 없다.
    # ⚠️ 2026-10-15: 점수 예측 칸을 **되살렸다** — 사용자 지시 *"기대득점은
    #    삭제했어도 마지막에는 두 모델이 점수까지 예상하게 해야 한다"*.
    #    🔴 격자가 없으니 그 점수는 **묶음에 없어도 된다**(사실이 아니라 예측).
    assert got == {"sentences", "refs", "pick", "score"}, (
        f"VD2 🔴🔴 출력 칸이 {sorted(got)} 다 — `sentences`·`refs` 둘이어야 "
        "한다. 확률 칸을 두면 모델이 코드가 정한 수를 덮을 길이 열린다")


def test_vd3_bundle_is_code_only() -> None:
    """VD3 — 묶음을 만드는 함수에 **LLM 호출이 없다**(지시: *"코드 만으로"*)."""
    said = _body("chain_of")
    for bad in ("llm", "ask(", "provider"):
        assert bad not in said, (
            f"VD3 🔴🔴 `chain_of` 가 `{bad}` 를 쓴다 — 묶음에 모델 글자가 섞이면 "
            "*\"코드 만으로\"* 가 깨지고, 지어냄 판정의 기준 자체가 오염된다")


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
    # 🔴 **문장 아홉**이다(`MIN_SENT` 9) — 가설 다섯 + 가름·예측·조심·감시.
    #    ⚠️ 종전 대역은 세 문장이었고, 그것은 이제 운영이 안 만드는 모양이다
    #    (사용자 지시 2026-10-17: 가설 최소 다섯 · 규율 #5 대역은 운영 모양).
    # 🔴 **문장 3~6**(사용자 지시 2026-10-18 — 가설 전부 삭제) · 묶음은 변수만
    got = Verdict(sentences=["홈이 폼에서 앞선다.",
                             "원정은 결장이 있다.",
                             "그래서 홈을 고른다."],
                  refs=["변수"] * 3,
                  # 🔴 예측 둘도 **있어야** 멀쩡한 평이다(지시 2026-10-15) —
                  #    `score` 는 묶음의 `스코어 상위` 에 있는 것만 쓴다.
                  pick="home", score="2-1")
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


def test_vd8_예측_점수는_묶음에_없어도_된다() -> None:
    """🔴🔴 사용자 지시 2026-10-15 — *"기대득점은 삭제했어도 마지막에는 솔라와
    딥시크가 **점수까지 예상**하게 해야 한다"*.

    격자(λ·스코어)를 지웠으니 그 점수는 묶음에 있을 수 없다. 🔴 **예측**이지
    사실이 아니므로 (나) 스코어 검열이 잡으면 안 된다. ⚠️ 빈 칸은 위반이다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    box = ["확률 — 홈 35.5% · 무 32.2% · 원정 32.2%"]
    got = Verdict(sentences=["홈이 폼에서 앞선다.",
                             "변수가 홈 쪽으로 밀었다.",
                             "그래서 2-1 을 본다."],
                  refs=["변수"] * 3, pick="home", score="2-1")
    verdict, bad = judge(got, box)
    assert verdict == "안 지어냈다", f"🔴 예측 점수에 거짓 위반이 났다 — {bad}"
    # 🔴 빈 칸은 위반이다
    _v2, bad2 = judge(got.model_copy(update={"score": ""}), box)
    assert any("점수 예측이 없다" in x for x in bad2), bad2


def test_vd12_예측과_점수가_어긋나면_위반이다() -> None:
    """🔴🔴 사용자 지시 2026-10-15 — 점수는 **홈-원정 순서**다.

    ⚠️ 실측(Svay Rieng vs Shanghai Shenhua): solar 가 `pick=away` 인데 점수를
       **`1-0`**(홈 승 스코어)으로 적었다. 검열은 `pick` 이 셋 중 하나인지와
       빈 칸만 보고 **둘의 일치는 안 봤다** — 평 자체가 모순이었다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, judge
    box = ["확률 — 홈 31.1% · 무 31.1% · 원정 37.8%"]
    # 🔴 **문장 아홉**이다(`MIN_SENT` 9 · 가설 다섯이 앞에 선다) — 종전 세
    #    문장 대역은 이제 운영이 안 만드는 모양이다(규율 #5)
    rows = ("홈이 폼에서 앞선다.", "원정은 결장이 있다.",
            "그래서 한쪽을 고른다.")

    def _v(pick: str, score: str) -> tuple:
        return judge(Verdict(sentences=list(rows),
                             refs=["확률"] * len(rows),
                             pick=pick, score=score), box)

    # 🔴 그 사고 그대로 — 원정 승인데 홈 승 점수
    verdict, bad = _v("away", "1-0")
    assert verdict == "지어냈다", bad
    assert any("예측과 점수가 어긋난다" in x for x in bad), bad
    # 🔴 무 예측이면 **동점**이어야 한다
    assert any("어긋난다" in x for x in _v("draw", "2-1")[1])
    # ✅ 맞는 짝은 통과한다
    for pick, score in (("away", "1-2"), ("home", "2-1"), ("draw", "1-1")):
        got_v, got_bad = _v(pick, score)
        assert got_v == "안 지어냈다", (pick, score, got_bad)


def test_vd13_프롬프트가_점수_순서를_못_박는다() -> None:
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import ask
    src = inspect.getsource(ask)
    # 🔴 글자가 바뀌었다(지시 2026-10-18 — 프롬프트를 변수만으로 줄였다)
    assert "홈-원정 순서" in src, src[-700:]
    assert "`pick` 과 어긋나면 버려진다" in src, src[-700:]


def test_vd22_점수는_홈_원정_순서다() -> None:
    """🔴🔴 VD22 — 사용자 지시 2026-10-16: *"순서를 거꾸로 썼다 — 수정해라"*.

    ⚠️ 실사고 2026-10-16(PSIM · City Club 둘 다): `pick=away` 인데
       `score="2-1"`(또는 문장에 `1-0`)을 냈다. 뜻은 *"원정이 이기고 홈이 한
       골"* 인데 **표기만 뒤집혔다**.
    🔴 프롬프트에만 적어 둔 규칙이 **두 번 안 지켜졌다** → 모델이 출력 직전에
       보는 **스키마 칸 설명**에도 박고, 문장 속 **뒤집힌 표기**도 잡는다.
    """
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import Verdict, ask, judge

    # ① 스키마 칸 설명이 순서를 말한다
    said = str(Verdict.model_fields["score"].description or "")
    assert "홈-원정" in said and "1-2" in said, said
    assert "앞이 홈 득점" in said, said
    assert "away" in str(Verdict.model_fields["pick"].description or "")
    # ② 프롬프트가 **순서를 못 박는다** — ⚠️ 종전엔 *"원정이 이기고 홈이 한
    #    골"* 보기까지 넣었다. 지시 2026-10-18 로 프롬프트를 **변수만**으로
    #    줄였고(가설·검증·보기 전부 걷었다) 못만 남겼다.
    src = inspect.getsource(ask)
    assert "홈-원정 순서" in src, src[-900:]
    assert "버려진다" in src, src[-900:]

    # ③ 문장에 **거꾸로** 적으면 잡는다
    box = ["확률 — 홈 31.1% · 무 31.1% · 원정 37.8%"]
    one = "점수는 원정 1골, 홈 0골로 원정 1-0을 예상한다."
    _v, bad = judge(Verdict(sentences=[one] * 3, refs=["확률"] * 3,
                            pick="away", score="0-1"), box)
    assert any("거꾸로 적었다" in x for x in bad), bad
    # ④ **대안 점수**(1-1 로 접힐 여지)는 잡지 않는다 — 그것까지 막으면 평이 얕아진다
    alt = "원정 수비가 버티면 1-1 쪽으로 기울 여지도 있다."
    _v2, bad2 = judge(Verdict(sentences=[alt] * 3, refs=["확률"] * 3,
                              pick="away", score="1-2"), box)
    assert not [x for x in bad2 if "(마)" in x], bad2


def test_vd24_맥락_전용도_묶음에_싣는다() -> None:
    """🔴🔴 VD24 — 사용자 지시 2026-10-16.

    ⚠️ 실사고(PSIM 확정 XI): `S01-away`(원정 최근 4경기 · 득점 1.5 · 실점
       2.75)가 표본 문턱으로 **맥락 전용**이 되자 묶음이 **아예 안 실었다** →
       평이 *"득실 평균이 **홈 쪽만** 있다"* 고 썼다. **수치는 있었는데 못 본
       것**이다. 🔴 ⑩ 은 맥락 전용을 *"**표시**·검증·가설"* 이라 부른다 —
       표시는 **평에게 보여 준다**는 뜻이다.
    """
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.routing import VarRow, VariableSet
    from app.core.stages import s6_verdict as vd

    rows = [VarRow(id="S01-home", type="recent_pattern",
                   places=["axis1", "hypo"], claim="홈 폼"),
            VarRow(id="S01-away", type="recent_pattern", places=["hypo"],
                   claim="원정 최근 4경기 · 득점 1.5 · 실점 2.75(많다)"),
            VarRow(id="R1", type="event_match", places=["hypo"], claim="기사",
                   from_doc=True)]
    box = vd.chain_of(None, _P(), None, VariableSet(rows=rows))
    said = "\n".join(box)
    # 🔴 **둘이다**(지시 2026-10-18) — 기사 칸을 걷었으므로 기사 변수(`R1`)도
    #    맥락 묶음에 든다. ⚠️ 종전엔 기사 칸이 따로 있어 하나였다.
    assert "맥락 전용 변수 2개" in said, said
    assert "`S01-away`" in said and "2.75" in said, said
    assert "`R1`" in said, said
    # 🔴 프롬프트는 **변수 목록만 보라**고 말한다(지시 2026-10-18) —
    #    ⚠️ 종전엔 *"`맥락 전용 변수` 칸도 **읽고** 분석에 쓴다"* 라는 줄이
    #    따로 있었다. 묶음이 **변수뿐**이므로 그 줄이 필요 없어졌다.
    src = inspect.getsource(vd.ask)
    assert "변수 목록만" in src, src[-900:]
    assert "변수 밖의 것" in src, src[-900:]
