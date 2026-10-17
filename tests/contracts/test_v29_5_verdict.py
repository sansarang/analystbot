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
    # 🔴 **문장 아홉**이다(`MIN_SENT` 9) — 가설 다섯 + 가름·예측·조심·감시.
    #    ⚠️ 종전 대역은 세 문장이었고, 그것은 이제 운영이 안 만드는 모양이다
    #    (사용자 지시 2026-10-17: 가설 최소 다섯 · 규율 #5 대역은 운영 모양).
    got = Verdict(sentences=["홈이 53.1% 로 앞선다.",
                             "λ 는 홈 1.537 · 원정 0.869 이다.",
                             "1-1 이 12.1% 로 가장 두껍다.",
                             "가설 넷 — 원정이 뒤를 연다.",
                             "가설 다섯 — 홈이 측면을 잡는다.",
                             "선 가설은 다섯이다.",
                             "그래서 홈을 고른다.",
                             "조심할 것은 세트피스다.",
                             "재료는 확률과 λ 가 들어왔다."],
                  refs=["확률", "λ", "스코어", "변수", "변수",
                        "변수", "확률", "변수", "확률"],
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
                             "가설 셋 — 원정이 지친다.",
                             "가설 넷 — 홈이 중원을 잡는다.",
                             "가설 다섯 — 세트피스가 갈린다.",
                             "선 가설은 넷이다.",
                             "그래서 2-1 을 본다.",
                             "조심할 것은 결장이다.",
                             "재료는 확률만 들어왔다."],
                  refs=["확률"] * 9, pick="home", score="2-1")
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
    # 🔴 **문장 아홉**이다(`MIN_SENT` 9 · 가설 다섯이 앞에 선다) — 종전 세
    #    문장 대역은 이제 운영이 안 만드는 모양이다(규율 #5)
    rows = ("홈 31.1% 다.", "원정 37.8% 다.", "무 31.1% 다.",
            "가설 넷 — 원정이 지친다.", "가설 다섯 — 홈이 측면을 잡는다.",
            "선 가설은 둘이다.", "그래서 한쪽을 고른다.",
            "조심할 것은 결장이다.", "재료는 확률만 들어왔다.")

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
    assert "홈-원정 순서" in src and "pick` 과 어긋나면 안 된다" in src


def test_vd19_예측은_변수로_한다() -> None:
    """🔴🔴 VD19 — 사용자 지시 2026-10-15:

    > llm 평은 **확률에 근거하여 예측하지 말고 변수를 기반으로** 예측하라 …
    > 확률은 변수를 기반하지만 … **포메이션 전략 등을 동반하여** 예측글을 쓰라

    ⚠️ 실측 2026-10-15: 확률이 33.3 균등인 경기에서 두 평이 *"균등하니까 무"* ·
       *"균등하지만 홈"* 처럼 **그 수를 출발점**으로 삼았다. 🔴 확률은 변수에서
       나온 **결과**라 예측 근거로 쓰면 같은 재료를 두 번 세는 것이다.
    """
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s6_verdict import ask

    src = inspect.getsource(ask)
    # 🔴🔴 **못 박혔다** — 사용자 지시 2026-10-17: *"프론프트에 못박아라 ..
    #    확률과 별개다 … 확률은 별개다"*. 종전 글자(*"예측은 변수로 한다"*)는
    #    *"적어도 되지만 근거로 쓰지 마라"* 라 반쯤 열려 있었고, 실측에서
    #    deepseek 이 **확률표를 앵커**라고 답했다.
    assert "확률은 절대 쓰지 마라" in src, "VD19 🔴 그 규칙이 프롬프트에 없다"
    assert "한 글자도 적지 " in src, "VD19 🔴 *절대* 가 프롬프트에 없다"
    assert "앵커로 **절대** 삼지 않는다" in src, src[-900:]
    assert "확률 수를 " in src and "따라가지 마라" in src, src[-700:]
    assert "포메이션과 전략을 반드시 동반" in src, "VD19 🔴 전략 동반 규칙이 없다"
    # 🔴🔴 **보는 것은 세 가지뿐** — 사용자 지시 2026-10-17:
    #    *"변수, 지난경기 데이타, 기사만 보고 예측하라고 해라"*
    assert "네가 보는 것은 세 가지뿐이다" in src, "VD19 🔴 세 가지 규칙이 없다"
    for one in ("**변수**", "**지난 경기 데이터**", "**기사**"):
        assert one in src, f"VD19 🔴 재료 {one} 가 프롬프트에 없다"
    # 🔴🔴 **예측불허 가설** — 사용자 지시 2026-10-17:
    #    *"예측불허가설를 세워서 예측하라고 프론프트 못박아라"*
    # ⚠️ 글자가 **줄에 걸쳐** 끊긴다(프롬프트는 여러 토막을 이어 붙인다) —
    #    그래서 토막 그대로 본다(사본 금지 · 글자를 손으로 이어 적지 않는다)
    # 🔴🔴 **가설이 먼저 · 다섯 이상** — 사용자 지시 2026-10-17
    assert "가설을 먼저 세우고 그 다음 예측한다" in src, "VD19 🔴 순서가 안 박혔다"
    assert "가설은 다섯 개 이상" in src, "VD19 🔴 다섯 개가 안 박혔다"
    assert "다섯 미만" in src, "VD19 🔴 다섯 미만을 버린다는 못이 없다"
    # 🔴 가설은 **따로 한 문장**이다 — 예측과 섞이면 못이 풀린다
    assert "가설만 쓰는 자리" in src, "VD19 🔴 가설이 따로 한 문장이 아니다"
    # 🔴 다섯이 **서로 다른 자리**에서 나와야 한다(같은 말 바꿔 쓰기 금지)
    assert "서로 다른 자리" in src, "VD19 🔴 가설이 겹쳐도 통과한다"
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **경기력 패턴 · 줄 다음 칸** — 사용자 지시 2026-10-17
    # ══════════════════════════════════════════════════════════════
    #
    #  > 최근 경기력을 봤을때 **나폴리는 연속승이 없다**는것도 가설에 붙여야
    #  > 한다 .. **바로 전경기는 졌다** .. **패턴분석**도 해야 한다
    #  > **lwdwl 이런식으로 갔단말이다** .. 그러면 **이후에 어떤 결과가
    #  > 나올지를 예측하는 것**과 같잖아
    assert "경기력 패턴을 읽어 가설에 붙인다" in src, "VD19 🔴 패턴 분석이 없다"
    assert "연속 승이 있나" in src, "VD19 🔴 연속 승을 안 묻는다"
    assert "바로 전 경기 결과" in src, "VD19 🔴 직전 경기를 안 묻는다"
    # 🔴 줄은 **세는 것이 아니라 순서**다 — 다음 칸을 예측하게 해야 한다
    assert "그 줄은 순서다 — 다음 칸을 예측해라" in src, "VD19 🔴 줄을 센다"
    assert "L W D W L" in src, "VD19 🔴 줄 보기가 없다"
    # 🔴 가설 다섯 중 **하나 이상**은 그 패턴에서 나와야 한다
    assert "하나 이상은 이 패턴에서" in src, "VD19 🔴 패턴 가설이 안 걸렸다"
    # 🔴🔴 **줄은 되돌아온다** — 사용자 지시 2026-10-17:
    #    *"진팀은 계속지지 않는다 .. 이기는 팀은 영원히 이길수 없다"*
    #    ⚠️ 줄을 그대로 이어 붙이는 예측은 가설이 아니다(예측불허의 뼈)
    assert "줄은 되돌아온다" in src, "VD19 🔴 되돌아옴이 안 박혔다"
    assert "그대로 이어 붙이지 마라" in src, "VD19 🔴 줄 연장을 막지 않는다"
    assert "가설 하나로 반드시 세워라" in src, "VD19 🔴 그 가설이 선택이 된다"
    # 🔴 **옛 규칙은 걷혔다** — 확률이 왜 그렇게 나왔나를 쓰라고 시키지 않는다
    assert "그 수가 **왜 그렇게 " not in src
    # 🔴 **반쯤 여는 글자가 남아 있으면 빨개진다** — *"적어도 되지만"* 이 그것이다
    assert "적어도 되지만" not in src, "VD19 🔴 확률을 적어도 된다고 아직 말한다"


def test_vd20_묶음에_포메이션_전략_칸이_있다() -> None:
    """🔴 VD20 — 프롬프트가 읽을 **재료**가 묶음에 있어야 한다(없으면 빈 말이다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s6_verdict as vd

    class _R:
        home = away = "t"
        home_name, away_name, competition = "A", "B", "c"

    class _Line:
        side, strategy, why = "home", "고압박", "최근 5경기 전진 수비"

    class _Plan:
        shape, audit, lines = "평소 그대로 vs 바뀜", "🟡 예상 XI 판정", [_Line()]

    class _Row:
        id, type = "SL1", "lineup_intent"
        claim = "홈 수비 라인 > 원정 수비 라인 · 총골 down"

    box = "\n".join(vd.chain_of(_R(), _P(), None, None,
                                plan=_Plan(), strat=[_Row()]))
    assert "포메이션·전략 — 양상 평소 그대로 vs 바뀜" in box, box
    assert "home 전략 `고압박`" in box, box
    assert "전략 `SL1`" in box and "수비 라인 >" in box, box
    # 🔴 비면 ⬜ 로 남긴다(#3) — 다만 평은 그 없음을 글로 쓰지 않는다
    box0 = "\n".join(vd.chain_of(_R(), _P(), None, None))
    assert "포메이션·전략 — ⬜ **없다**" in box0, box0


def test_vd21_러너가_그_칸을_넘긴다() -> None:
    """🔴 VD21 배선 — 안 넘기면 묶음에 ⬜ 만 남는다(없는 코드와 같다)."""
    said = (ROOT / "tools/run_collect.py").read_text(encoding="utf-8")
    assert "plan=plan, strat=var_sl" in said, (
        "VD21 🔴 러너가 ⑤-b 판정·⑤-b2 전략 변수를 ⑯ 묶음에 안 넘긴다")


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
    # ② 프롬프트에 **보기**가 있다
    src = inspect.getsource(ask)
    assert "원정이 이기고 홈이 한 골" in src, src[-900:]

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


def test_vd23_llm_감시() -> None:
    """🔴🔴 VD23 — 사용자 지시 2026-10-16:

    > llm 이 **변수가 잘 들어왔는지 · 딥서치가 잘됐는지 · 파이프라인이 제대로
    > 돌았는지** 평문에 적게 하고 프롬프트 주입해라 — **llm 감시를 추가한다**

    🔴 수는 **코드가 센 것**을 묶음(`🔎 파이프라인` 줄)으로 준다 — 모델이 다시
       세면 그 수가 또 거짓이 된다.
    """
    import inspect
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.routing import VarRow, VariableSet
    from app.core.stages import s6_verdict as vd

    rows = [VarRow(id="S01-home", type="recent_pattern", places=["axis1"],
                   claim="최근 5경기"),
            VarRow(id="R1", type="event_match", places=["hypo"], claim="기사",
                   from_doc=True)]
    box = vd.chain_of(None, _P(), None, VariableSet(rows=rows))
    one = next((x for x in box if "🔎 파이프라인" in x), "")
    assert one, "VD23 🔴 묶음에 감시 줄이 없다"
    for w in ("변수 2개", "확률에 닿는 것", "기사 변수 1개", "딥서치 문서",
              "전략 변수", "포메이션"):
        assert w in one, (w, one)
    # 🔴 프롬프트가 그 줄을 읽고 **마지막 문장**으로 적으라고 말한다
    src = inspect.getsource(vd.ask)
    assert "마지막 문장은 감시다" in src, src[-900:]
    assert "네가 세지 마라" in src
    # 🔴 감시 한 문장이 더 붙으니 상한이 6 이다
    # 🔴🔴 **가설이 먼저 · 다섯 이상**(사용자 지시 2026-10-17: *"가설을 먼저
    #    세우고 경기를 예측하는 방식으로 가야한다 .. 최소 5개이상"*) —
    #    가설 5+ · 가름 1~2 · 예측 1 · 조심 1 · 감시 1 → 최소 9 · 상한 13
    assert (vd.MIN_SENT, vd.MAX_SENT) == (9, 13), (vd.MIN_SENT, vd.MAX_SENT)
    assert vd.MIN_SENT >= 9, "VD24 🔴 가설 다섯이 들어갈 자리가 없다"


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
    assert "맥락 전용 변수 1개" in said, said
    assert "맥락 `S01-away`" in said and "2.75" in said, said
    # 🔴 기사 변수는 **그 칸으로 가지 않는다**(기사 칸이 따로 있다)
    assert "맥락 `R1`" not in said
    # 🔴 감시 줄의 수가 맞다(확률에 닿는 것 1 · 맥락 1)
    one = next(x for x in box if "🔎 파이프라인" in x)
    assert "확률에 닿는 것 1개 · 맥락 전용 1개" in one, one
    # 🔴 프롬프트가 **읽되 얇다고 적으라**고 말한다
    src = inspect.getsource(vd.ask)
    assert "맥락 전용 변수` 칸도 **읽고" in src, src[-900:]
