"""🔴🔴 **v5-A §7 — 판정 순서가 바뀐다.** `보강 → 1차 대입 → 반증 → 재대입 → …`

작업지시 §4-7:

> 판정 순서 변경 — v5 §6 을 **"보강 → 1차 대입 → 반증 → 재대입 → 상한 → pick"**
> 으로(v5-A §7 표). **`enabled=false` 면 반증 단계를 건너뛰고 로그에
> `redteam:off` 한 줄.**

══════════════════════════════════════════════════════════════════
🔴 왜 순서가 바뀌나 — **반증은 등급 후보를 보고 묻는다**
══════════════════════════════════════════════════════════════════

v5-A §4: *"단계 3 시나리오 세트로 코드가 **1차 생존 계산**을 한 뒤, 생존 0.8
이상인 마켓이 하나라도 있을 때만."* 🔴 그래서 **대입이 먼저**여야 한다 —
등급 후보가 없으면 반증할 결론도 없다.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_v5A_7_순서가_선언돼_있다():
    """🔴 그 순서를 **한 곳**에 적는다 — 코드 흐름이 그것을 따른다."""
    from app import judgeorder
    assert judgeorder.ORDER == (
        "보강", "1차 대입", "반증", "재대입", "상한", "pick")


def test_v5A_7_꺼짐이면_반증을_건너뛴다():
    """🔴 *"`enabled=false` 면 반증 단계를 건너뛰고 로그에 `redteam:off` 한 줄"*."""
    # ══════════════════════════════════════════════════════════════
    # 🔴 **끄고 잰다** — 켜진 상태가 기본이 됐다(지시 2026-10-05)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 계약은 `enabled: false` 를 **전제**했다. 🔴 사용자가 켜라고 해서
    #     그 전제가 깨졌다 — 그런데 **묻는 것은 그대로다**: *"꺼져 있으면 안
    #     부른다."* 그래서 **끄고** 잰다.
    #  🔴 끄는 자리는 한 곳이다(`rules.deepseek_cfg`) — 설정 파일을 건드리지
    #     않는다(시험이 저장소 상태를 바꾸면 그 다음 시험이 거짓이 된다).
    from app import judgeorder, rules
    old = rules.deepseek_cfg
    try:
        rules.deepseek_cfg = lambda: dict(old(), enabled=False)
        got = judgeorder.steps()
    finally:
        rules.deepseek_cfg = old
    assert "반증" not in got, got
    assert judgeorder.OFF_NOTE, judgeorder.OFF_NOTE

def test_v5A_7_켜지면_반증이_들어온다():
    """⚠️ 반대 증거 — 켜지면 순서에 **들어온다**(수를 바꾸지 않고 확인한다)."""
    from app import judgeorder
    got = judgeorder.steps(on=True)
    assert list(got) == list(judgeorder.ORDER), got
    # 🔴 **반증은 1차 대입 뒤·재대입 앞**이다
    assert got.index("반증") == got.index("1차 대입") + 1
    assert got.index("재대입") == got.index("반증") + 1


def test_v5A_7_판정이_그_순서를_쓴다():
    """🔴🔴 **안 이어진 순서는 없는 순서다**(#2).

    ⚠️ `analyze` 가 그 순서를 **읽어야** 한다 — 안 읽으면 `judgeorder` 는 글이다.
    """
    from tests._helpers import strip_docs
    body = strip_docs((ROOT / "app" / "analyze.py").read_text(encoding="utf-8"))
    assert "judgeorder" in body, (
        "🔴 `analyze` 가 §4-7 순서를 **안 읽는다** — 반증이 언제 도는지 아무도 "
        "모른다(CLAUDE.md #2)")


def test_v5A_7_반증_결과가_카드에_닿는다():
    """🔴 v5-A §4 출력 예 — 카드 하단에 **`■ 반증`** 블록이 있다."""
    from tests._helpers import strip_docs
    body = strip_docs((ROOT / "app" / "analyze.py").read_text(encoding="utf-8"))
    assert "반증" in body, "🔴 카드가 반증 블록을 안 낸다"


def test_v5A_7_M44_가_카드를_막는다():
    """🔴🔴 **M44** — 생존율이 올라가면 **카드 금지**. 그 길이 이어져 있어야 한다."""
    import ast
    import inspect
    import textwrap

    from app import judgeorder
    src = textwrap.dedent(inspect.getsource(judgeorder))
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "check_survival"]
    assert calls, "🔴 재대입 뒤 M44 검사를 **안 부른다**"


def test_v5A_7_M44_가_카드를_실제로_막는다():
    """🔴🔴 **돌연변이가 통과했다**(2026-10-04).

    `if card.redteam and card.redteam.blocked:` 를 `if False:` 로 바꿔도
    **초록이었다** — 내 계약이 `judgeorder` 안의 `check_survival` 호출만 보고
    **`analyze` 가 그 결과로 막는지**는 안 봤다.
    🔴 §9-5: 돌연변이가 안 물리면 그 계약은 **없는 것**이다.
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.build)))
    # 🔴 `redteam.blocked` 를 **보는 `if`** 가 있어야 한다
    guards = [n for n in ast.walk(tree)
              if isinstance(n, ast.If) and "blocked" in ast.dump(n.test)]
    assert guards, (
        "🔴 `analyze` 가 M44 의 `blocked` 를 **안 본다** — 생존율이 올라가도 "
        "카드가 그대로 나간다(v5-A M44: 카드 금지)")
    # 🔴 그리고 그 안에서 **깔때기에 떨어뜨린다**(수로 남는다)
    said = ast.dump(guards[0])
    assert "drop" in said or "markets_graded" in said, (
        "🔴 막기만 하고 **세지 않는다** — 왜 등급이 0 인지 카드가 못 말한다(#3)")
