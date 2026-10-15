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
                  refs=["확률", "λ", "스코어"],
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
    got = Verdict(sentences=["홈이 35.5% 로 앞선다.",
                             "변수가 홈 쪽으로 조금 더 밀었다.",
                             "그래서 2-1 을 본다."],
                  refs=["확률", "확률", "확률"], pick="home", score="2-1")
    verdict, bad = judge(got, box)
    assert verdict == "안 지어냈다", f"🔴 예측 점수에 거짓 위반이 났다 — {bad}"
    # 🔴 빈 칸은 위반이다
    _v2, bad2 = judge(got.model_copy(update={"score": ""}), box)
    assert any("점수 예측이 없다" in x for x in bad2), bad2


def test_vd9_묶음에_기사와_출처가_든다() -> None:
    """🔴🔴 사용자 지시 2026-10-15 — *"딥서치, llm 서치 자료들을 파악해서 ⑯
    평이 **그 자료를 쓰게**"*.

    ⚠️ 그때까지 묶음에는 확률·축·확률에 닿는 변수뿐이었다 — 기사 변수는 확률에서
       안 세니(개수 금지) **묶음에도 없었고**, 검열이 *"묶음에 없는 글자"* 로
       잡아 모델은 기사 내용을 **쓰고 싶어도 못 썼다**.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import chain_of

    class _V:
        def __init__(self, vid: str, doc: bool) -> None:
            self.id, self.type, self.claim = vid, "team_stats", f"{vid} 글"
            self.favors, self.goals, self.places = "home", "none", ["axis1"]
            self.from_doc = doc

    class _Set:
        rows = [_V("R1", True), _V("S01-home", False)]

        def of(self, place: str) -> list:
            return [x for x in self.rows if place in x.places]

    class _Doc:
        doc_id, title = "A-D1", "노리치 결장 소식"
        url, published_at = "https://news.example.com/a", "2026-10-15T09:00"

    class _Prob:
        home, draw, away = 0.35, 0.32, 0.33
        lam, over, scores = {}, {}, {}

    box = chain_of(None, _Prob(), None, _Set(), docs=[_Doc()])
    said = "\n".join(box)
    assert "기사에서 나온 사실" in said and "R1" in said, said
    assert "확률에는 안 셌다" in said, "🔴 그 칸이 확률에 닿는다고 읽힌다"
    assert "문서 출처" in said and "news.example.com" in said, said


def test_vd10_기사_유무를_평문에_안_쓴다() -> None:
    """🔴🔴 **바뀐 규칙** — 사용자 지시 2026-10-15:

    > 평을 낼 때 **기사에서 나온 사실이 없다는 표기하지 않아도 된다** …
    > 기사에서 나온 내용은 **평문으로 안 써도 된다**

    🔴 묶음 칸은 그대로 **⬜ 로 남긴다**(#3 · 코드가 아는 상태다). 바뀐 것은
       **프롬프트**다 — 그 칸이 비면 *"기사에서 나온 것이 없다"* 를 **쓰지
       말라**고 말해야 한다(종전엔 **쓰라고** 말했다).
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import ask, chain_of

    class _Set:
        rows: list = []

        def of(self, place: str) -> list:
            return []

    class _Prob:
        home, draw, away = 0.33, 0.33, 0.34
        lam, over, scores = {}, {}, {}

    said = "\n".join(chain_of(None, _Prob(), None, _Set(), docs=None))
    assert "기사에서 나온 사실 — ⬜ **없다**" in said, said
    assert "문서 출처 — ⬜ **없다**" in said, said
    # 🔴 프롬프트가 **쓰지 말라**고 말한다(강제 조항은 걷혔다)
    import inspect
    src = inspect.getsource(ask)
    assert "기사에서 나온 사실을 반드시 한 번은 쓴다" not in src
    # ⚠️ 그 글은 **여러 줄로 쪼개져** 있다 — 이어 붙인 글자로 세면 안 된다
    assert "그 사실을 적지 마라" in src, src[-500:]
    assert "자료 살림" in src and "경기 분석" in src, src[-500:]


def test_vd11_문서_id_가_찍힌다() -> None:
    """⚠️ 실측 2026-10-15: `doc_id` 로 읽어 **`?` 로 찍혔다** — `Doc` 의 칸은
    **`id`** 다(만드는 함수 인자 이름이 `doc_id` 라 헷갈린다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import chain_of

    class _Doc:
        id, title = "A-D3", "예상 라인업"
        url, published_at = "https://x.example/a", "2026-10-15T09:00"

    class _Set:
        rows: list = []

        def of(self, place: str) -> list:
            return []

    class _Prob:
        home, draw, away = 0.4, 0.3, 0.3
        lam, over, scores = {}, {}, {}

    said = "\n".join(chain_of(None, _Prob(), None, _Set(), docs=[_Doc()]))
    assert "문서 `A-D3`" in said, said
    assert "문서 `?`" not in said, said


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
    rows = [("홈 31.1% 다.", "원정 37.8% 다.", "무 31.1% 다.")][0]

    def _v(pick: str, score: str) -> tuple:
        return judge(Verdict(sentences=list(rows),
                             refs=["확률", "확률", "확률"],
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
    assert "홈-원정 순서" in src and "pick` 과 어긋나면 안 된다" in src
