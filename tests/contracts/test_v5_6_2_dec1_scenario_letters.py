"""🔴🔴 **결정 ① — 시나리오 글자를 A~H 로 늘린다(상한 8)**.

사용자 결정 2026-10-04:

> 시나리오 글자 → **A(늘린다), 단 상한 8**. ID를 A~E 고정이 아니라 **A~H**로
> 바꾸고, 필수형은 빈자리가 없으면 넣지 못하는 게 아니라 **항상 들어간다** —
> 일반 시나리오가 8개를 넘을 때만 **strength 최저인 일반 시나리오**를 뺀다.
> **B**(필수형이 일반을 밀어냄)는 **반대 방향 시나리오가 빠질 위험**이 있고,
> **C**(한 글자에 여러 스코어)는 *"하나라도 죽으면 사망"* 규칙과 섞여
> **생존이 왜곡된다.**

⚠️ 왜 필요했나 — v5-A §5 정답지 재현 계약이 셋 중 **둘**에서 빨갰다:
   남아공 5-0(대량득점형) · 크로아티아 2-2(난타전) → `A~E 가 다 찼다`.
"""
from __future__ import annotations

import pytest


def test_dec1_글자가_여덟이다():
    """🔴 `A`~`H`. ⚠️ 아홉째는 없다 — **상한 8**이다."""
    import typing

    from app import types as T
    got = list(typing.get_args(T.ScenarioId))
    assert got == ["A", "B", "C", "D", "E", "F", "G", "H"], got


def test_dec1_상한이_한_곳에서_온다():
    """🔴 `8` 을 여러 곳에 적지 않는다(사본 금지) — 글자 수가 원본이다."""
    from app import scenarios
    assert scenarios.MAX_SCENARIOS == 8
    import typing

    from app import types as T
    assert scenarios.MAX_SCENARIOS == len(typing.get_args(T.ScenarioId)), (
        "🔴 상한을 **손으로** 적었다 — `ScenarioId` 글자 수에서 자라게 하라")


def test_dec1_필수형은_자리를_묻지_않는다():
    """🔴🔴 *"필수형은 **항상 들어간다**"* — 빈자리가 없어도 들어간다."""
    from app import scenarios
    import inspect

    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(scenarios))
    # 🔴 *"글자가 없다"* 로 **거부하는 길이 남아 있지 않아야** 한다
    assert "글자가 없다" not in body, (
        "🔴 아직 *'시나리오 글자가 없다'* 로 필수형을 **거부한다** — 결정 ①은 "
        "필수형이 **항상 들어간다**고 했다")
    assert hasattr(scenarios, "place_required"), (
        "🔴 필수형을 넣는 자리가 없다 — `scenarios.place_required` 를 만들어라")


def test_dec1_넘치면_일반_중_최저_strength_를_뺀다():
    """🔴🔴 **필수형은 절대 안 뺀다** — 일반 중 `strength` 최저만 뺀다.

    ⚠️ 사용자가 **B 를 거부한 까닭**이 여기다 — *"반대 방향 시나리오가 빠질
       위험"*. 🔴 그래서 빼는 것은 **일반**이고, 방향 묶음(A·B)이 일반이라도
       `strength` 가 낮지 않으면 안 빠진다.
    """
    from app import scenarios
    gen = [{"id": chr(65 + i), "strength": 10 - i, "added_by": "template"}
           for i in range(8)]          # 🔴 일반 8개(strength 10..3)
    need = [{"id": "X", "strength": 1, "added_by": "required"}]
    got = scenarios.place_required(gen, need, cap=8)
    ids = [x["added_by"] for x in got]
    assert len(got) == 8, got
    assert "required" in ids, "🔴 **필수형이 안 들어갔다**"
    # 🔴 빠진 것은 **일반 중 strength 최저**(3) 다
    kept = sorted(x["strength"] for x in got if x["added_by"] != "required")
    assert 3 not in kept, f"🔴 최저 strength 가 아닌 것을 뺐다: {kept}"
    assert 10 in kept, f"🔴 가장 센 일반을 뺐다: {kept}"


def test_dec1_필수형이_여럿이면_필수형은_안_뺀다():
    """🔴 필수형이 상한을 넘겨도 **필수형을 빼지 않는다**(일반을 다 뺀다)."""
    from app import scenarios
    gen = [{"id": "A", "strength": 9, "added_by": "template"}]
    need = [{"id": f"N{i}", "strength": 1, "added_by": "required"}
            for i in range(8)]
    got = scenarios.place_required(gen, need, cap=8)
    assert all(x["added_by"] == "required" for x in got), got
    assert len(got) == 8, got


def test_dec1_글자를_다시_매긴다():
    """🔴 남은 것들이 `A`부터 **빈틈없이** 글자를 받아야 한다(출력 규격)."""
    import typing

    from app import scenarios
    from app import types as T
    ok = list(typing.get_args(T.ScenarioId))
    gen = [{"id": "?", "strength": 5 - i, "added_by": "template"}
           for i in range(3)]
    got = scenarios.place_required(gen, [], cap=8)
    assert [x["id"] for x in got] == ok[:3], got


def test_dec1_규격_문구도_같이_고쳤다():
    """⚠️ *"시나리오 A~E"* 라 적힌 문서·규격이 남아 있으면 카드가 거짓말한다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    bad = []
    for p in list((root / "app").rglob("*.py")) + \
            list((root / "config").rglob("*.yaml")):
        try:
            said = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "시나리오 A~E" in said or "시나리오 A∼E" in said:
            bad.append(str(p.relative_to(root)))
    assert not bad, (
        f"🔴 *'시나리오 A~E'* 가 아직 적혀 있다 — 글자는 여덟이다: {bad}")


def test_dec1_상한이_실제_경로에서_걸린다():
    """🔴🔴 **배선**(#2) — `place_required` 를 만들고 **안 부르면** 없는 코드다.

    ⚠️ 이 저장소가 반복해 다친 자리다(돌연변이 22건이 그 병으로 통과했다).
       🔴 그래서 **빌드 경로**에서 그 함수를 부르나를 본다.
    """
    import inspect

    from app import scenarios
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(scenarios))
    # 🔴 `def` 말고 **호출**이 있어야 한다
    calls = [ln for ln in body.splitlines()
             if "place_required(" in ln and "def place_required" not in ln]
    assert calls, (
        "🔴 `place_required` 를 **아무 데서도 안 부른다** — 안 이어진 코드는 "
        "없는 코드보다 나쁘다(#2)")
    assert "MAX_SCENARIOS" in body


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **돌연변이가 뚫은 자리를 메운다** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  M78 `sid = _evict_for_required(res, hint)` → `sid = None`      ⚠️ **통과했다**
#  M79 `gens = [일반만]` → `gens = list(res.drafts)`               ⚠️ **통과했다**
#  M83 `baseball_templates(res, game, varis)` → `pass`            ⚠️ **통과했다**
#
# 🔴 까닭은 같다 — 나는 `place_required` 를 **직접 불러** 시험했고, **실제
#    보강 경로**(`require_set`)에서 같은 일이 되는지 묻지 않았다. §9-5 가
#    무효로 보는 바로 그 꼴이다(판정 함수는 보고 쓰는 곳은 안 본다).


def _full(n_general: int):
    """🔴 일반 시나리오로 **상한을 꽉 채운** `Result` — 보강이 들어올 자리가 없다."""
    from app import scenarios
    res = scenarios.Result()
    res.drafts = [
        scenarios.Draft(id=chr(65 + i), scores=[f"{i}-{i + 1}"],
                        strength=float(10 - i), template_id="t",
                        why="일반", variables=["V"], added_by="template")
        for i in range(n_general)]
    return res


def test_dec1_M78_자리가_없어도_필수형이_들어간다():
    """🔴🔴 **M78** — `_evict_for_required` 를 꺼도 빨개져야 한다.

    ⚠️ `_add` 는 `claim` 이 `None` 을 줄 때 **자리를 비워서라도** 넣어야 한다.
    """
    from app import scenarios
    res = _full(scenarios.MAX_SCENARIOS)
    before = len(res.drafts)
    ok = scenarios._add(
        res, claim=scenarios._claimer(res), hint="대량득점형",
        scores=["5-0"], game=_game(), why="시험", variables=["V"])
    assert ok is True, (
        f"🔴 자리가 꽉 찼을 때 필수형을 **포기했다** — 결정 ①은 *'항상 들어간다'* "
        f"다. 사유: {res.incomplete_why}")
    assert len(res.drafts) == before, [d.id for d in res.drafts]
    assert any(d.added_by == "required" for d in res.drafts)
    assert "5-0" in {sc for d in res.drafts for sc in d.scores}


def test_dec1_M79_필수형은_절대_안_빠진다():
    """🔴🔴 **M79** — 뺄 대상에서 필수형을 빼지 않으면 빨개져야 한다."""
    from app import scenarios
    res = _full(scenarios.MAX_SCENARIOS - 1)
    # 🔴 **가장 약한 것을 필수형으로** 둔다 — 잘못 짜면 이것이 먼저 빠진다
    res.drafts.append(scenarios.Draft(
        id=chr(65 + scenarios.MAX_SCENARIOS - 1), scores=["9-9"],
        strength=0.0, template_id="t", why="필수", variables=["V"],
        added_by="required"))
    scenarios._add(res, claim=scenarios._claimer(res), hint="또_필수형",
                   scores=["5-0"], game=_game(), why="시험", variables=["V"])
    kept = {sc for d in res.drafts for sc in d.scores}
    assert "9-9" in kept, (
        "🔴 **필수형이 빠졌다**(strength 0 이라서) — 결정 ①은 일반 중 최저를 "
        "빼라고 했다")


def _game():
    from app import classify
    return classify.Game(home="H", away="A", sport="soccer",
                         league="해외축구", home_id="team:1", away_id="team:2")
