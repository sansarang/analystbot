"""🔴🔴 **v5 §9-1 — R1~R12 를 코드가 집행하나.** 남은 R 들을 여기서 본다.

§9-1 원문(v4 §7 그대로):

> R1 생존 1.0 미만 이름 금지 · **R2 보드 줄만** · **R3 난타전 자동 생성** ·
> **R4 전제 재검증** · R5 자료 부족 카드 · R6 2골 차 패 시나리오 ·
> R7 표본 3경기 미만 0.4 · **R8 배당 숫자 0건** ·
> **R9 금칙어**(§11-3 기본값으로 "방향 판정" 섹션은 허용) · R10 명단 재실행 1회 ·
> **R11 명단 전 주전 출장 hard 금지** · **R12 새 hard 변수 없이 등급 상향 금지**.

⚠️ R1·R5·R6·R7·R10 은 다른 파일이 든다(이름에 번호가 있다). 🔴 여기는 **나머지**다.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_v5_9_1_열두_규칙이_문서에_있다_R2_M8_M19():
    """🔴 **베끼지 않는다** — 문서에서 `R1`~`R12` 를 세어 대조한다.

    ⚠️ 그리고 **R2(보드 줄만)** 가 그 목록에 있는지 본다 — 목록이 줄면 여기가
       먼저 빨개진다.
    """
    import re
    text = (ROOT / "docs" / "fable" / "archive"
            / "2026-10-04_v5_solar.md").read_text(encoding="utf-8")
    i = text.index("9-1 R1~R12")
    seg = text[i:text.index("9-2 M1~M25", i)]
    got = {int(m) for m in re.findall(r"\bR(\d{1,2})\b", seg)}
    assert got >= set(range(1, 13)), sorted(got)
    assert "보드  줄만" in seg or "보드 줄만" in seg, seg[:200]


def test_v5_9_1_보드가_오면_우리_기준선은_무효다_R2():
    """🔴 R2 — *"보드 줄만"*. ⚠️ 보드 없는 경기의 기준선은 **꼬리표**를 단다.

    §6-3: *"보드가 없으면 종목별 기준선 후보에 복수 대입하고 전부 **'보드 오면
    무효'** 꼬리표."*
    """
    import inspect

    from app import survive
    src = inspect.getsource(survive)
    assert "보드 오면 무효" in src, (
        "🔴 R2 — 보드 없는 기준선에 *'보드 오면 무효'* 꼬리표가 없다")


def test_v5_9_1_난타전은_규칙이_만든다_R3_M6():
    """🔴 R3 — *"난타전 자동 생성"*. §5-c-1 이 그 규칙이고 `sec7_rule: R3` 다."""
    from app import rules
    got = rules.cross_rule("5c-1")
    assert str(got.get("sec7_rule")) == "R3", got
    # 🔴 그 규칙을 **부르는 함수**가 있다
    import inspect

    from app import scenarios
    assert "_c1_open" in inspect.getsource(scenarios._cross)


def test_v5_9_1_전제는_재검증한다_R4_M7():
    """🔴 R4 — *"전제 재검증"*. §4 전제 유형이 있고 그것이 변수와 갈린다."""
    from app import rules
    prem = rules.premise_types()
    assert prem, "🔴 §4 전제 유형 선언이 없다"
    # 🔴 `Variable` 이 그것을 **칸으로** 든다(섞이면 재검증할 것을 모른다).
    #    ⚠️ `Classified` 에는 그 칸이 없다 — `to_variable` 이 배정한다.
    from app import classify
    c = classify.Classified(
        text="x", source_url="u", hardness="hard", type=sorted(prem)[0],
        direction="home", why="w")
    v, why = c.to_variable("V1")
    assert v is not None, why
    assert v.is_premise is True, v
    # 🔴 전제가 **아닌** 유형은 거짓이다(반대 증거)
    other = next(t for t in rules.variable_types() if t not in prem)
    v2, _ = classify.Classified(
        text="x", source_url="u", hardness="hard", type=other,
        direction="home", why="w").to_variable("V2")
    assert v2 is None or v2.is_premise is False, v2


def test_v5_9_1_배당_숫자가_판정에_없다_R8():
    """🔴🔴 R8 — *"배당 숫자 0건"*. ⚠️ 배당은 `research` 스키마에만(절대규칙 6).

    🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다.
    """
    import re

    from tests._helpers import strip_docs
    # ══════════════════════════════════════════════════════════════════
    # 🔴 D46 — **금지하는 것**과 **쓰는 것**은 다르다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `app/card.py` 는 `"odds"` 를 **금칙어 목록**에 적는다(R9 가 그것을
    #     요구한다). 🔴 그 줄을 결함으로 보면 계약이 **규칙을 지키는 코드**를
    #     때린다 — 같은 병을 이 저장소가 여러 번 겪었다.
    #  🔴 그래서 **수로 쓰는 꼴**을 본다: `float(odds)`·`odds *`·`/ odds`·
    #     `odds =` 처럼 값으로 다루는 자리다.
    use = re.compile(
        r"(?:float|int|Decimal)\s*\(\s*\w*odds|"
        r"\bodds\s*[*/+\-]|[*/+\-]\s*odds\b|\bodds\s*=\s*[^=]")
    for path in ("app/survive.py", "app/scenarios.py", "app/triggers.py",
                 "app/card.py"):
        body = strip_docs((ROOT / path).read_text(encoding="utf-8"))
        hit = use.search(body)
        assert not hit, (
            f"🔴 R8 — {path} 가 배당을 **수로 쓴다**: {hit.group(0)!r}. "
            f"배당은 `research` 스키마에만이다(절대규칙 6)")
    # ✅ 그리고 **금칙어 목록에는 있어야** 한다(R9) — 없으면 안 막는다
    card = strip_docs((ROOT / "app" / "card.py").read_text(encoding="utf-8"))
    assert "odds" in card, "🔴 R9 — 금칙어 목록에 `odds` 가 없다"


def test_v5_9_1_금칙어를_발송이_막는다_R9():
    """🔴 R9 — 금칙어. ⚠️ §11-3 기본값으로 **"방향 판정" 섹션은 허용**이다."""
    from app import tg
    import inspect
    src = inspect.getsource(tg)
    assert "금칙" in src or "금지" in src, "🔴 R9 — 발송이 금칙어를 안 본다"
    # 🔴 그리고 카드에 **"방향 판정"** 블록이 있다(허용된 것이다)
    spec = (ROOT / "docs" / "fable" / "output_spec.md").read_text(
        encoding="utf-8")
    assert "방향 판정" in spec, "🔴 §11-3 이 허용한 블록이 규격에 없다"


def test_v5_9_1_명단_전_주전_출장은_hard_가_아니다_R11_M11():
    """🔴 R11 — *"명단 전 주전 출장 hard 금지"*.

    ⚠️ 확정 XI 전에는 *"그 선수가 나온다"* 가 **추측**이다. 🔴 그것을 hard 로
       쓰면 상한이 풀린 것처럼 보인다.
    """
    from app import rules
    # 🔴 그 규칙이 §4 유형 선언에 **글자로** 있어야 한다(코드가 짐작하지 않게)
    types = rules.variable_types()
    said = " ".join(str(v) for v in types.values())
    assert "명단" in said, "🔴 R11 — §4 선언이 명단 조건을 말하지 않는다"


def test_v5_9_1_새_hard_없이_등급_상향_금지_R12_M4():
    """🔴 R12 — *"새 hard 변수 없이 등급 상향 금지"*.

    ⚠️ 라이브(§7-3)가 그것을 **승격 금지**로 못 박았다(M29). 🔴 그 둘이 같은 말이다.
    """
    from app import live, rules
    assert rules.live_rules().get("promote") is False
    assert live.cap_verdict(before="small", after="name") == "small"
    # 🔴 그리고 `survive._r6_missing` 처럼 **§7 번호로** 규칙을 찾는 길이 있다
    assert callable(getattr(rules, "by_sec7_rule", None))
