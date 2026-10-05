"""🔴🔴 **v5 §7-2 — 방아쇠는 *기계 조건*이어야 한다.**

지시문 §7-2 원문:

> 카드마다 명단에서 확인할 항목을 **1개 이상 기계 조건**으로 적는다
> (`"player:… in XI"`, `"changes_from_last >= 5"`, `"formation == 5-back"`).
> T-60 재실행이 조건을 **평가**해 걸리면 등급을 그 자리에서 바꾸고, **평가
> 불가면** 결론을 `trigger_unresolved` 로 표시해 **베팅 등급이 아님**을
> 명시한다(M28). 재실행에서 **시나리오 수가 줄면 실패**(M2).

══════════════════════════════════════════════════════════════════
🔴 왜 — 사람이 읽는 글은 **기계가 평가할 수 없다**
══════════════════════════════════════════════════════════════════

종전 방아쇠의 `watch` 는 사람 글이었다:

    `lineup` 세포가 깨는 T-70분 · *"로테이션이 보이면"*

⚠️ T-60 재실행이 그 글을 보고 **무엇을 참으로 볼지** 정할 수 없다. 🔴 그러면
   재실행이 등급을 바꿀 수 없고, 바꾸지 못한 것과 *"조건이 안 걸렸다"* 가
   **한 글자**가 된다(§8-6 이 막는 섞임이다).
"""
from __future__ import annotations

import pytest


def test_v5_7_2_세_꼴이_선언돼_있다():
    """🔴 지시문이 **보기로 든 세 꼴** 전부. ⚠️ 코드에 박지 않는다."""
    from app import trigcond
    kinds = set(trigcond.KINDS)
    assert {"in_xi", "changes_from_last", "formation"} <= kinds, kinds


@pytest.mark.parametrize(("expr", "kind"), [
    ("player:Alex McLeish in XI", "in_xi"),
    ("changes_from_last >= 5", "changes_from_last"),
    ("formation == 5-back", "formation"),
])
def test_v5_7_2_지시문_보기를_읽는다(expr, kind):
    """🔴 지시문에 **적힌 그대로**가 파싱돼야 한다."""
    from app import trigcond
    got = trigcond.parse(expr)
    assert got is not None, expr
    assert got.kind == kind, got


def test_v5_7_2_모르는_꼴은_지어내지_않는다():
    """🔴 못 읽으면 `None` — **대충 참으로 보지 않는다**(#4 추측 금지)."""
    from app import trigcond
    assert trigcond.parse("로테이션이 보이면") is None
    assert trigcond.parse("") is None


def test_v5_7_2_명단이_있으면_평가한다():
    """🔴 **참·거짓을 수로 답한다.** ⚠️ 그것이 §7-2 의 요점이다."""
    from app import trigcond
    xi = {"players": ["Alex McLeish", "Scott McTominay"],
          "formation": "5-back", "changes_from_last": 6}
    assert trigcond.evaluate("player:Alex McLeish in XI", xi)[0] is True
    assert trigcond.evaluate("player:Nobody in XI", xi)[0] is False
    assert trigcond.evaluate("changes_from_last >= 5", xi)[0] is True
    assert trigcond.evaluate("changes_from_last >= 7", xi)[0] is False
    assert trigcond.evaluate("formation == 5-back", xi)[0] is True
    assert trigcond.evaluate("formation == 4-4-2", xi)[0] is False


def test_v5_7_2_명단이_없으면_평가_불가다():
    """🔴🔴 **`None` 이다 — `False` 가 아니다**(M28).

    ⚠️ *"명단에 그 선수가 없다"* 와 *"명단을 못 받았다"* 는 **다른 말**이고
       고칠 곳이 다르다(§8-6). 🔴 `False` 로 때우면 방아쇠가 **안 걸린 것**으로
       읽히고 등급이 그대로 남는다 — 그것이 돈을 잃는 자리다.
    """
    from app import trigcond
    ok, why = trigcond.evaluate("player:X in XI", {})
    assert ok is None
    assert "못" in why or "없다" in why, why
    # 🔴 칸마다 따로다 — 포메이션만 없는 명단
    xi = {"players": ["A"]}
    assert trigcond.evaluate("player:A in XI", xi)[0] is True
    assert trigcond.evaluate("formation == 5-back", xi)[0] is None
    assert trigcond.evaluate("changes_from_last >= 5", xi)[0] is None


def test_v5_7_2_평가_불가는_베팅_등급이_아니다_M28():
    """🔴 M28 — *"평가 불가면 결론을 `trigger_unresolved` 로 표시"*."""
    from app import trigcond
    from app.reasons import Reason
    got = trigcond.resolve(["player:X in XI"], {})
    assert got.unresolved == ["player:X in XI"]
    assert got.reason is Reason.TRIGGER_UNRESOLVED
    assert got.betting_grade is False
    assert "베팅 등급이 아니다" in got.line(), got.line()
    # ⚠️ 평가되면 베팅 등급이다
    ok = trigcond.resolve(["player:A in XI"], {"players": ["A"]})
    assert ok.unresolved == [] and ok.betting_grade is True
    assert ok.reason is Reason.OK


def test_v5_7_2_카드마다_조건이_하나_이상이다():
    """🔴🔴 *"카드마다 … **1개 이상** 기계 조건"* — 0 개면 실패다."""
    from app import trigcond
    from app.reasons import Reason
    none_ = trigcond.resolve([], {"players": ["A"]})
    assert none_.betting_grade is False
    assert none_.reason is Reason.TRIGGER_UNRESOLVED
    assert "1개 이상" in none_.line(), none_.line()


def test_v5_7_2_방아쇠가_기계_조건을_들고_있다():
    """🔴 `Trigger` 에 그 칸이 있어야 한다 — 글만 있으면 평가할 수 없다."""
    import dataclasses

    from app import triggers
    names = {f.name for f in dataclasses.fields(triggers.Trigger)}
    assert "check" in names, (
        f"🔴 §7-2 — `Trigger` 에 기계 조건 칸이 없다: {sorted(names)}")


def test_v5_7_2_유형마다_조건을_yaml_이_정한다():
    """🔴 조건 **꼴**을 코드에 박지 않는다 — 유형이 가리킨다(#1 사본 금지)."""
    from app import rules
    got = rules.trigger_checks()
    assert got, "🔴 `config/trigger_conditions.yaml` 의 `checks` 가 비었다"
    # 🔴 §4 유형 이름이어야 한다 — 없는 유형을 가리키면 그 줄은 죽은 줄이다
    types = set(rules.variable_types())
    unknown = [k for k in got if k not in types]
    assert not unknown, f"🔴 §4 에 없는 유형을 가리킨다: {unknown}"
    # ⚠️ 꼴은 **파싱되는 것**이어야 한다(장식 글자를 두지 않는다)
    from app import trigcond
    bad = [(k, v) for k, v in got.items() if trigcond.template_kind(v) is None]
    assert not bad, f"🔴 읽을 수 없는 조건 꼴: {bad}"


def test_v5_7_2_배선_방아쇠가_조건을_붙인다():
    """🔴🔴 **안 붙은 조건은 없는 조건이다**(CLAUDE.md #2)."""
    import ast
    import inspect
    import textwrap

    from app import triggers
    src = textwrap.dedent(inspect.getsource(triggers))
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") in ("check_for", "template_kind")]
    assert calls, (
        "🔴 `triggers` 가 기계 조건을 **안 붙인다** — T-60 재실행이 평가할 것이 "
        "없고, 카드는 사람 글만 들고 나간다(§7-2)")


def test_v5_7_2_M2_재실행에서_시나리오가_줄면_실패():
    """🔴 *"재실행에서 **시나리오 수가 줄면 실패**(M2)."*

    ⚠️ 재실행은 **더 아는 상태**다 — 아는 것이 늘었는데 그릴 수 있는 시나리오가
       줄면 그것은 우리 규칙이 **좁아진** 것이다(자료 탓이 아니다).
    """
    from app import trigcond
    ok, why = trigcond.rerun_ok(before=4, after=4)
    assert ok is True
    ok2, why2 = trigcond.rerun_ok(before=4, after=3)
    assert ok2 is False
    assert "M2" in why2 and "4" in why2 and "3" in why2, why2
    # 🔴 늘어나는 것은 **괜찮다**
    assert trigcond.rerun_ok(before=4, after=5)[0] is True


def test_v5_7_2_못_읽는_글은_평가_불가다():
    """🔴🔴 **돌연변이 B 가 통과했다**(2026-10-04).

    `evaluate` 의 *"조건을 못 읽었다"* 가지를 `True` 로 바꿔도 **초록이었다** —
    내 계약이 `parse()` 만 직접 시험하고 **`evaluate` 에 사람 글을 넣어 보지
    않았다.** 🔴 그러면 *"로테이션이 보이면"* 같은 글이 **늘 걸린 것**이 되고
    등급이 그 자리에서 바뀐다 — 돈을 잃는 자리다.
    """
    from app import trigcond
    xi = {"players": ["A"], "formation": "4-4-2", "changes_from_last": 3}
    for junk in ("로테이션이 보이면", "player X in XI", "changes_from_last ~ 5",
                 "formation = 5-back", ""):
        ok, why = trigcond.evaluate(junk, xi)
        assert ok is None, (junk, ok, why)
        assert "읽을 수 없다" in why or "평가 불가" in why, (junk, why)
    # 🔴 그리고 그런 글만 있는 카드는 **베팅 등급이 아니다**
    got = trigcond.resolve(["로테이션이 보이면"], xi)
    assert got.betting_grade is False
    assert got.unresolved == ["로테이션이 보이면"]


def test_v5_7_2_빈_자리를_빈_채로_적지_않는다():
    """🔴🔴 **돌연변이 F 가 통과했다**(2026-10-04).

    `check_for` 의 *"빈 자리를 채울 값이 없다"* 검사를 끄면 `player: in XI` 라는
    **평가할 수 없는 글자**가 조건으로 나간다. ⚠️ 그것이 §7-2 의 *"1개 이상"* 을
    **거짓으로 채운다** — 조건은 있는데 평가가 영원히 불가다.
    🔴 내 계약이 `check_for` 를 **직접 시험하지 않았다.**
    """
    from app import trigcond
    # ⚠️ `{star}` 를 채울 값이 없다
    got, why = trigcond.check_for("absence")
    assert got == "", (got, why)
    assert "채울 값이 없다" in why, why
    # 🔴 **채울 값이 있으면** 만든다(반대 증거)
    got2, why2 = trigcond.check_for("absence", star="Yelich")
    assert got2 == "player:Yelich in XI", (got2, why2)
    # 🔴 그리고 만든 것은 **반드시 읽힌다**
    assert trigcond.parse(got2) is not None
    # ⚠️ 빈 자리가 없는 꼴은 값 없이도 만들어진다
    got3, _ = trigcond.check_for("squad_rotation")
    assert got3 == "changes_from_last >= 5", got3


def test_v5_7_2_선언_오타와_채운_값을_가려_적는다():
    """🔴 §8-6 — *"선언이 틀렸다"* 와 *"채운 값이 틀렸다"* 는 고칠 곳이 다르다."""
    from app import trigcond
    # 🔴 §4 에 **없는 유형** — 그 사실을 말한다
    _, why = trigcond.check_for("regression")
    assert "§4 에 없는 유형" in why, why
    # ⚠️ 조건 선언이 **아예 없는** 유형
    _, why2 = trigcond.check_for("h2h_pattern")
    assert "선언된 기계 조건이 없다" in why2, why2
    assert why != why2

