"""🔴🔴 **v5 §6-8 — 등급·결론 어휘 다섯 개와 그 경계값.**

지시문 §6-8 원문:

> 등급은 **1.0 낸다 / 0.85·0.9 소액 / 0.8 소액 하단 / 그 아래 없음 / 자료 부족.**
> 등급 경계값(0.85·0.8 의 무게 기준)은 **원장 30건 뒤 재보정**하고 그 전엔
> 초기값을 `config/thresholds.yaml` 에 **근거와 함께** 적는다. 카드에 "방향
> 판정" 섹션을 둔다(R9 완화, §11-3 기본값).

§11-3 기본값 표: `결론 등급명 = 낸다 / 소액 / 소액 하단 / 없음 / 자료 부족`

══════════════════════════════════════════════════════════════════
🔴 종전은 **세 어휘**였다 — `낸다` · `소액` · (이름 없음)
══════════════════════════════════════════════════════════════════

`analyze.py` 가 이렇게 적고 있었다:

```python
word = "낸다" if r["verdict"] == "name" else "소액"
```

⚠️ 그 한 줄에 **두 결함**이 있다:
   ① `0.8`(소액 **하단**)과 `0.9`(소액)가 **같은 글자**를 받는다 — 상한에 걸려
      내려온 마켓과 바닥에서 간신히 선 마켓이 카드에서 구별되지 않는다.
   ② 어휘가 **코드에 박혀 있다** — §6-8 은 경계값을 yaml 에 두라고 했다.

🔴 그리고 **`자료 부족` 은 수가 아니다** — 변수가 모자라 애초에 등급을 매길 수
   없는 상태다(§7 R5). 그것을 `없음`(= 재 봤는데 안 섰다)과 섞으면 *"우리가
   안 했다"* 와 *"해 봤는데 없다"* 가 한 글자가 된다(§8-6 이 막는 섞임이다).
"""
from __future__ import annotations

import pytest


def test_v5_6_8_다섯_어휘가_선언돼_있다():
    """🔴 §11-3 표가 **이름으로 댄** 다섯. ⚠️ 코드에 박지 않는다."""
    from app import survive
    got = list(survive.verdict_words())
    assert got == ["낸다", "소액", "소액 하단", "없음", "자료 부족"], got


@pytest.mark.parametrize(("sv", "want"), [
    (1.0, "낸다"),
    (0.95, "소액"),          # ⚠️ 1.0 미만은 낸다가 아니다
    (0.9, "소액"),
    (0.85, "소액"),
    (0.84, "소액 하단"),
    (0.8, "소액 하단"),
    (0.79, "없음"),
    (0.0, "없음"),
])
def test_v5_6_8_수가_어휘를_정한다_R1_M5(sv, want):
    """🔴 §6-b — **수가 정한다.** 고르는 사람도 LLM 도 없다."""
    from app import survive
    assert survive.verdict_word(sv) == want, sv


def test_v5_6_8_자료_부족은_수와_무관하다():
    """🔴🔴 *"해 봤는데 없다"* 와 *"애초에 못 쟀다"* 는 **다른 말**이다.

    ⚠️ 섞으면 고칠 곳이 사라진다 — `없음` 은 규칙이 답한 것이고, `자료 부족` 은
       수집·검증이 모자란 것이다(§8-6 의 `fix_where` 가 다르다).
    """
    from app import survive
    assert survive.verdict_word(1.0, enough=False) == "자료 부족"
    assert survive.verdict_word(0.0, enough=False) == "자료 부족"


def test_v5_6_8_경계값이_yaml_에_근거와_함께_있다():
    """🔴 §6-8 — *"초기값을 `config/thresholds.yaml` 에 근거와 함께 적는다."*"""
    from app import thresholds
    rows = thresholds.all_rows()
    for name in ("verdict_name_at", "verdict_small_at", "verdict_small_low_at"):
        assert name in rows, f"🔴 §6-8 경계값 `{name}` 이 yaml 에 없다"
        row = rows[name]
        assert str(row.get("basis") or "").strip(), (
            f"🔴 `{name}` 에 근거가 없다 — §5-6 은 근거 없는 상수를 금지한다")
    assert thresholds.value("verdict_name_at") == 1.0
    assert thresholds.value("verdict_small_at") == 0.85
    assert thresholds.value("verdict_small_low_at") == 0.8


def test_v5_6_8_원장_재보정_약속이_글자로_남아_있다():
    """🔴 *"원장 30건 뒤 재보정"* — ⚠️ 그런데 **원장으로 규칙을 고치지 않는다.**

    사용자 지시 2026-10-02: *"쌓이는거는 우리 로직이 맞냐 틀렸냐만 **검증하는
    방법으로만** 사용한다."* 🔴 그 충돌을 **글자로 남긴다** — 다음 세션이 원장을
    보고 문턱을 만지려 들면 그 줄이 막는다.
    """
    from app import thresholds
    rows = thresholds.all_rows()
    basis = " ".join(str(rows[n].get("basis") or "") for n in
                     ("verdict_small_at", "verdict_small_low_at"))
    assert "30" in basis, "🔴 §6-8 의 '원장 30건' 약속이 근거에 없다"
    assert "검증" in basis, (
        "🔴 사용자 지시 2026-10-02 와의 충돌이 안 적혀 있다 — 원장은 **검증에만** "
        "쓴다(계수를 맞추지 않는다)")


def test_v5_6_8_어휘를_코드에_박지_않는다():
    """🔴🔴 **사본 금지** — `analyze` 가 어휘를 다시 적으면 한 발 늦는다.

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다(이 파일이 그 글자를 *설명*하는
       것과 코드가 그것을 *짓는* 것은 다르다).
    """
    import pathlib

    from tests._helpers import strip_docs
    for path in ("app/analyze.py", "app/card.py"):
        body = strip_docs(pathlib.Path(path).read_text())
        assert '"소액"' not in body and "'소액'" not in body, (
            f"🔴 {path} 가 등급 어휘를 **글자로** 적는다 — "
            f"`survive.verdict_word` 가 한 표다(§6-8)")


def test_v5_6_8_결론_줄이_하단을_가린다():
    """🔴 **끝까지 잇는다** — 어휘가 실제로 카드 글에 다르게 나오나.

    ⚠️ 함수만 맞고 부르는 곳이 옛 삼항식이면 카드는 그대로다(#2 배선).
    """
    from app import survive
    rows = [{"verdict": "small", "survival": 0.8, "market": None},
            {"verdict": "small", "survival": 0.9, "market": None}]
    words = [survive.verdict_word(float(r["survival"])) for r in rows]
    assert words == ["소액 하단", "소액"], words
    # 🔴 `analyze` 의 결론 줄이 그 함수를 **부르는가**
    import ast
    import inspect
    import textwrap

    from app import analyze
    src = textwrap.dedent(inspect.getsource(analyze))
    # ══════════════════════════════════════════════════════════════
    # 🔴 **`word_of` 도 그 자리다** — 지시 ② (2026-10-05)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 결론 줄이 `verdict_word(survival)` 로 **다시 계산**했고, 그래서
    #     상한이 내린 등급이 **되올라갔다**(pn8 모순: *"낸다 … 죽는 시나리오 G"*).
    #  🔴 이제 결론 줄은 `word_of(verdict)` 를 쓴다 — **판정은 한 번만** 한다.
    #     ⚠️ 묻는 것은 그대로다: *"어휘를 카드가 **한 곳에서** 받나."*
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr in ("verdict_word", "word_of")]
    assert calls, (
        "🔴 어휘 함수를 만들어 두고 **카드가 안 부른다** — 안 이어진 코드는 "
        "없는 코드보다 나쁘다(CLAUDE.md #2)")
