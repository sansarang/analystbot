"""🔴🔴 **v5 §6-2 — 시나리오 세트 자동 보강**(필수형 · 최소 4개 · 무효 조건).

지시문 §6-2 원문:

> 에이전트 초안(§3-5)을 받아 **코드가 다음을 강제한다.** 하나라도 못 만들면 그
> 경기는 `scenario_incomplete` 로 **카드 금지.** 시나리오는 **최소 4개**, 각각
> `driver_vars`·`mechanism`·`outcomes` 가 비면 무효. 한 시나리오의 스코어가
> 여럿이면 **하나라도 죽으면 그 시나리오는 죽음**(수정 1-4).

| 필수형 | 조건 | 없으면 |
|---|---|---|
| 우세팀 실점 동반형 (X-1) | 우세팀 승 시나리오가 있을 때 | 항상 코드가 템플릿으로 추가, `added_by:code` |
| 대량득점형 (축구 4골+, 야구 10점+) | 약팀 수비 결장 2명+ 또는 랭킹 차 50+ 또는 직전 대패(0-3 이상) 또는 양 팀 연속 득점 폼 | 추가 |
| 회귀 반전형 | `regression` 변수가 있을 때 | **지속형·반전형 둘 다** 추가 |
| 핸디 ±N.5 대응형 | 후보 핸디가 ±N.5 면 상대가 N+1 차로 이기는 시나리오 | 추가 |
| 반대 방향 | 전부 같은 방향이면 | **실패** |
| 양방향 변수 | `coach_crisis`·`event_match`·`lineup_rotation` 은 두 시나리오에 모두 부착 | **실패** |

══════════════════════════════════════════════════════════════════
🔴 왜 이것이 필요한가 — **거짓 1.0** 의 뿌리다
══════════════════════════════════════════════════════════════════

§6-7: *"생존 1.0 은 **시나리오를 다 만든 뒤**에만 성립한다."*
⚠️ 시나리오를 적게 만들면 생존이 **공짜로** 1.0 이 된다 — 죽을 자리가 없으니까.
🔴 그래서 §6-2 는 **반대 시나리오를 코드가 강제로 넣는다.**

⚠️ 표를 **코드에 박지 않는다** — `config/scenario_required.yaml` 이 원본이고
   `rules.required_forms()` 가 읽는다(#1 사본 금지).

🔴 **§10-4 M34** — 변수 3개·같은 결론(10-04) — 거짓 1.0 계약(§6-7) · 변수 5개 미만 카드 금지
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

import pytest

from app import classify


def _var(vtype="recent_pattern", direction="home", *, team="A", why="§4"):
    """🔴 `Classified` 의 **실제 칸**으로 만든다 — `vtype`·`name` 칸은 **없다**.

    ⚠️ 유형 이름 칸은 `type` 이고, `Draft.variables` 에 들어가는 열쇠도 그것이다
       (`_base` 가 `variables=[c.type …]` 로 적는다).
    """
    return classify.Classified(
        text=f"{vtype} 사실", source_url="https://x/y", hardness="hard",
        type=vtype, direction=direction, team=team, why=why)


def _game(sport="soccer"):
    return classify.Game(home="A", away="B", sport=sport, league="L")


def test_v5_6_2_표가_yaml_에_있다_M26():
    """🔴 **여섯 줄 전부.** ⚠️ 코드에 박으면 지시문이 바뀔 때 한 발 늦는다."""
    from app import rules
    forms = rules.required_forms()
    want = {"우세팀_실점_동반형", "대량득점형", "회귀_반전형", "핸디_대응형",
            "반대_방향", "양방향_변수"}
    assert want <= set(forms), f"🔴 §6-2 표에서 빠진 줄: {want - set(forms)}"
    for name, row in forms.items():
        assert str(row.get("when") or "").strip(), f"🔴 `{name}` 에 조건이 없다"
        assert row.get("on_missing") in ("추가", "실패"), (
            f"🔴 `{name}` 의 '없으면' 이 §6-2 의 두 값이 아니다: {row}")


def test_v5_6_2_최소_넷이_선언돼_있다():
    """🔴 *"시나리오는 최소 4개"* — ⚠️ 그 수를 코드에 박지 않는다."""
    from app import scenarios
    assert scenarios.MIN_SCENARIOS == 4


@pytest.mark.parametrize("hole", ["variables", "why", "scores"])
def test_v5_6_2_빈_칸이_있으면_무효(hole):
    """🔴 *"각각 driver_vars·mechanism·outcomes 가 비면 무효."*

    우리 `Draft` 의 칸이 그 셋이다 — `variables`·`why`·`scores`.
    ⚠️ 이름이 다르다고 검사를 빼지 않는다(§8-3 이 그 대응을 적어 둔다).
    """
    from app import scenarios
    d = scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                        template_id="t", why="까닭", variables=["V1"])
    setattr(d, hole, [] if hole != "why" else "")
    ok, reason = scenarios.draft_valid(d)
    assert ok is False
    assert hole in str(reason) or reason, reason
    # 🔴 **채워져 있으면** 통과한다(반대 증거)
    full = scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                           template_id="t", why="까닭", variables=["V1"])
    assert scenarios.draft_valid(full)[0] is True


def test_v5_6_2_넷_미만이면_불완전이다_M34():
    """🔴🔴 *"하나라도 못 만들면 scenario_incomplete 로 **카드 금지**."*"""
    from app import scenarios
    res = scenarios.Result()
    # ⚠️ 스코어를 **무승부**로 둔다 — 이긴 쪽이 없으면 X-1 보강이 안 들어가고,
    #    그래야 *"최소 개수"* 하나만 시험한다(둘을 섞으면 무엇이 걸렸는지 모른다).
    res.drafts = [scenarios.Draft(id=x, scores=["1-1"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"])
                  for x in "ABC"]
    # 🔴 방향은 **둘** 준다 — ⑤(반대 방향)가 아니라 개수로 걸리게
    scenarios.require_set(
        res, _game(), [_var(direction="home"), _var("x", "away")])
    assert res.incomplete is True
    assert any(str(scenarios.MIN_SCENARIOS) in w for w in res.incomplete_why), (
        res.incomplete_why)
    # 🔴 사유가 **어느 필수형이 없어서인지** 말해야 한다(#3)
    assert res.incomplete_why, res.incomplete_why
    assert any("카드 금지" in n for n in res.notes), res.notes


def test_v5_6_2_우세팀_실점_동반형을_코드가_넣는다_M21():
    """🔴 *"우세팀 승 시나리오가 있을 때 **항상** 코드가 템플릿으로 추가."*

    ⚠️ 이것이 §6-7 의 거짓 1.0 을 막는 핵심이다 — `2-0` 만 있으면 `언더 2.5` 가
       공짜로 1.0 을 받는다. `2-1` 이 있으면 그 마켓이 **죽는다**.
    """
    from app import scenarios
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["2-0"], strength=2.0,
                                  template_id="soccer_home_dominant",
                                  why="홈 우세", variables=["V1"])]
    scenarios.require_set(res, _game(), [_var()])
    added = [d for d in res.drafts if d.added_by == "required"]
    assert added, [d.id for d in res.drafts]
    # 🔴 §1 — id 는 **글자**다(`types.ScenarioId`). 설명은 `why` 에 들어간다.
    #    ⚠️ 실측 2026-10-04: 설명을 id 에 넣었더니 `MarketSurvival` 이 터졌다
    #       (`Input should be 'A', 'B', 'C', 'D' or 'E'`).
    import typing

    from app import types as _t
    allowed = set(typing.get_args(_t.ScenarioId))
    assert all(d.id in allowed for d in res.drafts), [d.id for d in res.drafts]
    assert any("실점 동반" in d.why for d in added), [d.why for d in added]
    # 🔴 **실점을 동반한 스코어**여야 한다 — 우세팀이 이기면서 1점을 준다
    got = [s for d in added for s in d.scores]
    assert any(s.split("-")[1] != "0" for s in got), got


def test_v5_6_2_코드가_넣은_것을_added_by_로_적는다():
    """🔴 *"`added_by:code`"* — ⚠️ 에이전트가 낸 것과 **섞으면 안 된다.**

    그 구분이 사라지면 *"에이전트가 반대 시나리오를 생각했나"* 를 못 센다.
    """
    from app import scenarios
    d = scenarios.Draft(id="X", scores=["1-0"], strength=1.0, template_id="t",
                        why="w", variables=["V1"])
    assert d.added_by == "", "🔴 기본값은 **빈 문자열**이다(누가 넣었나 모른다)"
    assert "added_by" in {f.name for f in
                          __import__("dataclasses").fields(scenarios.Draft)}


def test_v5_6_2_회귀_변수는_둘_다_넣는다_M22():
    """🔴 *"regression 변수가 있을 때 **지속형·반전형 둘 다** 추가."*

    ⚠️ 하나만 넣으면 그 방향이 **공짜로** 살아남는다.
    """
    from app import scenarios
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["2-0"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"])]
    scenarios.require_set(
        res, _game(), [_var("regression"), _var("x", "away")])
    # 🔴 id 는 글자이므로 **`why` 로** 가린다
    whys = [d.why for d in res.drafts]
    assert any("지속형" in w for w in whys), whys
    assert any("반전형" in w for w in whys), whys


def test_v5_6_2_핸디_대응형은_이미_5c_5_가_한다_R6_M10():
    """🔴🔴 **§6-2 ④ 는 §5-c-5 다** — 두 번 만들지 않는다(#1 사본 금지).

    §6-2 ④: *"후보 핸디가 ±N.5 면 **상대가 N+1 차로 이기는** 시나리오."*
    §5-c-5: *"핸디 +1.5 가 후보 마켓이면 **상대가 2골 차로 이기는** 시나리오를
             반드시 하나 만든다."*

    ⚠️ 같은 규칙이다(`N = 1` → `N+1 = 2`). 🔴 `require_set` 이 또 만들면 글자가
       두 개 먹히고 같은 시나리오가 두 번 선다.
    """
    from app import rules, scenarios
    cfg = rules.cross_rule("5c-5")
    assert cfg.get("two_goal_scores"), cfg
    # 🔴 `require_set` 은 ④ 를 **만들지 않고 어디서 되는지 적는다**
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id=x, scores=["2-0"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"])
                  for x in "AB"]
    before = len(res.drafts)
    scenarios.require_set(res, _game(), [_var(), _var("x", "away")],
                          handicaps=[1.5])
    assert any("5-c-5" in n and "핸디" in n for n in res.notes), res.notes
    added = [d for d in res.drafts[before:] if "핸디" in d.why]
    assert not added, [d.why for d in added]
    # 🔴 그리고 **2골 차 스코어**가 §5-c-5 표에 실제로 있다
    sides = cfg["two_goal_scores"]
    for side in ("home", "away"):
        want = [str(x) for x in (sides.get(side) or [])]
        assert want, side
        for sc in want:
            h, a = (int(x) for x in sc.split("-"))
            assert abs(h - a) >= 2, (side, sc)


def test_v5_6_2_전부_같은_방향이면_실패다_M1():
    """🔴 *"반대 방향 — 전부 같은 방향이면 **실패**."*(추가가 아니다)"""
    from app import scenarios
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id=x, scores=["2-0"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"])
                  for x in "ABCD"]
    scenarios.require_set(res, _game(), [_var(direction="home")])
    assert res.incomplete is True
    assert any("방향" in n for n in res.notes), res.notes


def test_v5_6_2_양방향_변수가_두_시나리오에_붙는다():
    """🔴 *"`coach_crisis`·`event_match`·`lineup_rotation` 은 **두 시나리오에
    모두 부착**"* — 안 붙으면 **실패**다.

    ⚠️ 한 쪽에만 붙으면 그 변수가 **한 방향 근거**가 된다. 양방향 변수는 어느
       쪽으로 갈지 모르는 변수이고, 그래서 양쪽 시나리오를 다 흔들어야 한다.
    """
    from app import rules, scenarios
    both = rules.required_forms()["양방향_변수"]
    types = [str(x) for x in (both.get("types") or [])]
    assert {"coach_conflict", "event_match", "squad_rotation"} <= set(types), (
        f"🔴 §6-2 ⑥ 이 가리키는 유형이 §4 이름이 아니다: {types}")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id=x, scores=["2-0"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"])
                  for x in "AB"] + [
        scenarios.Draft(id=x, scores=["0-2"], strength=1.0, template_id="t",
                        why="w", variables=["V2"]) for x in "CD"]
    # ⚠️ 글자가 다 찼다 — 보강이 더 들어갈 자리가 없다(그 사유가 남는다)
    v = _var("coach_conflict", "home")
    scenarios.require_set(res, _game(), [_var(), _var("x", "away"), v])
    # 🔴 그 변수가 **두 시나리오 이상**에 붙어야 한다
    where = [d.id for d in res.drafts if "coach_conflict" in d.variables]
    assert len(where) >= 2 or res.incomplete, (where, res.notes)


def test_v5_6_2_배선_generate_가_부른다():
    """🔴🔴 **안 이어진 보강은 없는 보강이다**(CLAUDE.md #2)."""
    import ast
    import inspect
    import textwrap

    from app import scenarios
    tree = ast.parse(textwrap.dedent(inspect.getsource(scenarios.generate)))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "require_set"]
    assert calls, (
        "🔴 `require_set` 을 만들어 두고 `generate` 가 **안 부른다** — 시나리오는 "
        "그대로 적게 나오고 생존은 공짜로 1.0 이 된다(§6-7)")


def test_v5_6_2_불완전이면_카드가_금지된다():
    """🔴🔴 *"`scenario_incomplete` 로 **카드 금지**"* — 끝까지 이어졌나.

    ⚠️ 깃발만 세우고 카드가 그대로 나오면 그 깃발은 장식이다.
    """
    import pathlib

    from tests._helpers import strip_docs
    body = strip_docs(pathlib.Path("app/analyze.py").read_text())
    assert "incomplete" in body, (
        "🔴 `analyze` 가 `incomplete` 를 **보지 않는다** — 불완전한 세트로 카드가 "
        "나가고 생존 1.0 이 공짜로 적힌다(§6-7)")

def test_v5_6_2_무효_시나리오를_실제로_떨어뜨린다():
    """🔴🔴 **돌연변이 B 가 통과했다**(2026-10-04).

    `ok, why = draft_valid(d)` 를 `True, ""` 로 바꿔도 **초록이었다** — 내 계약이
    `draft_valid` 를 **직접** 부르기만 하고 *"그 결과로 떨어지나"* 를 안 봤다.
    🔴 판정 함수가 맞는 것과 **그 판정이 쓰이는 것**은 다르다(#2 배선).
    """
    from app import scenarios
    res = scenarios.Result()
    # 🔴 `added_by=""`(출처 미상)이라 `driver_vars` 를 **요구받는다** — fail-closed
    bad = scenarios.Draft(id="A", scores=["2-0"], strength=1.0, template_id="t",
                          why="w", variables=[])
    good = [scenarios.Draft(id=x, scores=["2-1"], strength=1.0,
                            template_id="t", why="w", variables=["V1"],
                            added_by="template") for x in "BCDE"]
    res.drafts = [bad, *good]
    scenarios.require_set(res, _game(), [_var(), _var("x", "away")])
    assert bad not in res.drafts, "🔴 무효 시나리오가 **안 떨어졌다**"
    assert any("무효" in n for n in res.notes), res.notes
    # ⚠️ 바닥 출처(`template`)는 **변수 없이도** 남는다(§5-c-5 floor)
    res2 = scenarios.Result()
    floor = scenarios.Draft(id="A", scores=["0-2"], strength=0.3,
                            template_id="5c-5", why="w", variables=[],
                            added_by="rule:5c-5")
    res2.drafts = [floor, *good]
    scenarios.require_set(res2, _game(), [_var(), _var("x", "away")])
    assert floor in res2.drafts, (
        "🔴 §5-c-5 가 일부러 세운 **바닥 시나리오**가 지워졌다 — 그것이 핸디 "
        "±1.5 를 죽이는 자리다(지우면 거짓 1.0 이 **생긴다**)")


def test_v5_6_2_1점차_승리에는_실점_동반이_없다():
    """🔴🔴 **돌연변이 E 가 통과했다**(2026-10-04).

    `h >= 2` 를 지워도 초록이었다. `0-1` → `1-1` 은 **무승부**이고 *"우세팀이
    이기면서 한 점을 준다"* 가 아니다 — **이기지 못하는** 스코어다.
    🔴 그 산수를 **직접** 시험한다(세트 전체를 돌려 잡기를 기다리지 않는다).
    """
    from app import scenarios
    assert scenarios._conceding_scores(["0-1"]) == []
    assert scenarios._conceding_scores(["1-0"]) == []
    assert scenarios._conceding_scores(["2-0"]) == ["2-1"]
    assert scenarios._conceding_scores(["0-3"]) == ["1-3"]
    # 🔴 이미 실점이 있으면 보강할 것이 없다
    assert scenarios._conceding_scores(["2-1"]) == []


def test_v5_6_2_양방향_변수는_반드시_둘에_붙는다():
    """🔴🔴 **돌연변이 G 가 통과했다**(2026-10-04).

    `picked[:2]` 를 `[:1]` 로 바꿔도 초록이었다 — 내 계약이 `len(where) >= 2 or
    res.incomplete` 였고, **`or` 가 빠져나갈 문을 열어 뒀다.**
    🔴 방향이 다른 시나리오가 **있을 때**는 `incomplete` 가 변명이 될 수 없다.
    """
    from app import scenarios
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["2-0"], strength=1.0,
                                  template_id="t", why="w", variables=["V1"],
                                  added_by="template"),
                  scenarios.Draft(id="B", scores=["0-2"], strength=1.0,
                                  template_id="t", why="w", variables=["V2"],
                                  added_by="template"),
                  scenarios.Draft(id="C", scores=["2-1"], strength=1.0,
                                  template_id="t", why="w", variables=["V3"],
                                  added_by="template"),
                  scenarios.Draft(id="D", scores=["1-2"], strength=1.0,
                                  template_id="t", why="w", variables=["V4"],
                                  added_by="template")]
    scenarios.require_set(
        res, _game(), [_var(direction="home"), _var("x", "away"),
                       _var("coach_conflict", "home")])
    where = [d.id for d in res.drafts if "coach_conflict" in d.variables]
    assert len(where) >= 2, (
        f"🔴 양방향 변수가 {where} 하나에만 붙었다 — 그러면 그것이 **한 방향 "
        f"근거**가 된다(§6-2 ⑥). notes={res.notes}")


def test_v5_6_2_불완전이면_등급이_한_줄도_안_선다():
    """🔴🔴 **불완전한 세트로는 등급이 없다** — 그런데 **대입은 낸다.**

    ══════════════════════════════════════════════════════════════════
    ⚠️ 종전 계약은 *"`survive.run` 을 `incomplete` 로 **감싸라**"* 였다 — 걷혔다
    ══════════════════════════════════════════════════════════════════

    > 사용자 규칙 2026-10-06: 시나리오·**대입**·방향 판정은 **항상** 낸다.

    🔴 그리고 §6-2 의 주석이 스스로 이렇게 적어 뒀다: *"시나리오는 지우지
       않는다 — 만든 것은 카드에 그대로 적고 **등급만** 막는다."* 그런데 코드는
       `survive` 를 통째로 막아 **대입까지** 없앴다.
    🔴 실측 2026-10-06(북아일랜드–조지아 재실행): 시나리오 **7개**가 섰는데
       블록 7~8 이 *"못 셌다"* 이고 블록 9 가 *"시나리오가 없어 확률이 서지
       않았다"* 라고 적었다 — **거짓 사유**다(§8-6).

    ⚠️ 종전 계약의 **걱정은 맞다**: 불완전한 세트로 등급을 매기면 공짜 1.0 이
       원장에 쌓인다(§6-7). 🔴 그래서 **그 걱정을 직접 센다** — 돌려서 등급이
       한 줄도 없는지 본다(글자·구조가 아니라 **결과**다).
    """
    from app import classify, scenarios, survive
    game = _game()
    # 🔴 세트가 불완전해지도록 **한 방향만** 준다(§5-c-6)
    one = classify.Classified(
        text="홈 우위", source_url="https://x.test/t", hardness="hard",
        type="home_field", direction="home", why="§4 home_field")
    sc = scenarios.generate([one, one, one], game)
    assert sc.drafts, sc.notes
    # ── ① 사유를 **안 넘기면** 등급이 선다(그래야 아래 비교가 뜻을 갖는다)
    graded = survive.run(sc.drafts, game, board=None)
    named = [r for r in graded.rows
             if r.get("verdict") in ("name", "small", "low")]
    assert named, f"전제가 깨졌다 — 등급이 애초에 0줄이다: {graded.rows[:2]}"
    # ── ② `§6-2` 사유를 넘기면 **등급이 한 줄도 없다**
    blocked = survive.run(sc.drafts, game, board=None,
                          thin_why="§6-2 `scenario_incomplete` — 반대 방향 없음")
    left = [r for r in blocked.rows
            if r.get("verdict") in ("name", "small", "low")]
    assert not left, f"🔴 불완전한데 등급이 남았다(§6-7 공짜 1.0): {left[:2]}"
    # ── ③ 🔴 그런데 **대입 줄은 그대로 있다**(그것이 이번에 바뀐 것이다)
    assert len(blocked.rows) == len(graded.rows), (
        len(blocked.rows), len(graded.rows))


def test_v5_6_2_카드가_불완전을_생존에_넘긴다():
    """🔴 #2 배선 — 넘기지 않으면 ②의 보호가 **운영에서** 안 돈다."""
    import ast
    import inspect
    import textwrap

    from app import analyze
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.build)))
    found = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and getattr(node.func.value, "id", "") == "survive"):
            continue
        kw = {k.arg for k in node.keywords}
        assert "thin_why" in kw, (
            f"🔴 `survive.run` 에 `thin_why` 를 **안 넘긴다** — 얇거나 "
            f"불완전한 세트에서 등급이 공짜로 선다: {sorted(kw)}")
        found = True
    assert found, "🔴 `survive.run` 호출을 못 찾았다 — 이 계약을 고쳐라"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **그 값이 `incomplete` 를 담는가** — 글자 검사로는 안 잡힌다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전 이 줄은 `"sc.incomplete" in src` 였다. 🔴 돌연변이 M125(사유에서
    #     `incomplete` 를 빼기)가 **통과했다** — 그 낱말이 `build` 의 다른 자리
    #     (`if sc.incomplete: fun.drop(…)`)에 남아 있기 때문이다.
    #  🔴 그래서 **`thin_why` 로 흘러드는 이름을 따라간다**: 그 키워드 값이 어느
    #     변수에서 오고, 그 변수를 만든 식이 `incomplete` 를 읽는지.
    src = textwrap.dedent(inspect.getsource(analyze.build))
    tree2 = ast.parse(src)
    feeds: set[str] = set()
    for node in ast.walk(tree2):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and getattr(node.func.value, "id", "") == "survive"):
            for k in node.keywords:
                if k.arg == "thin_why":
                    feeds |= {n.id for n in ast.walk(k.value)
                              if isinstance(n, ast.Name)}
                    feeds |= {ast.unparse(k.value)}
    said = " ".join(sorted(feeds))
    if "incomplete" not in said:
        # 🔴 이름을 거쳐 왔다 — 그 이름을 **만든 식**을 본다
        srcs = [ast.unparse(n.value) for n in ast.walk(tree2)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in feeds
                        for t in n.targets)]
        said += " " + " ".join(srcs)
    assert "incomplete" in said, (
        f"🔴 §6-2 `incomplete` 가 **등급 금지 사유로 안 들어간다** — 불완전한 "
        f"세트에서 생존 1.0 이 공짜로 등급이 된다(§6-7): {said[:200]}")


def test_v5_6_2_보강은_무승부를_다시_넣지_못한다():
    """🔴🔴 **돌연변이 L 이 통과했다 — 그 방어는 아무것도 막지 않았다.**

    처음에 `require_set` **뒤에** `drop_impossible_draws` 를 한 번 더 불렀다.
    ⚠️ 그 호출을 지워도 **초록이었다** — 그때 이미 `_conceding_scores` 가 고쳐져
       무승부를 만들지 않았기 때문이다. 🔴 **쓰임이 증명되지 않은 방어**다
       (§9-5: 돌연변이가 안 물리면 그 계약은 없는 것이다).

    🔴 그래서 관문을 **모든 보강이 지나는 자리**(`_add`)로 옮겼다. 보강은 네
       가지이고 앞으로 더 생긴다 — 한 곳에서 막는다.
    """
    from app import rules, scenarios
    nhl = classify.Game(home="A", away="B", sport="hockey", league="NHL")
    assert rules.draw_possible("NHL")[0] is False
    res = scenarios.Result()
    claim = scenarios._claimer(res)
    # 🔴 **무승부를 섞어** 넣어 본다 — 관문이 그것만 걷어야 한다
    ok = scenarios._add(res, claim=claim, hint="시험", scores=["2-1", "1-1"],
                        why="w", variables=["V1"], game=nhl)
    assert ok is True
    assert res.drafts[-1].scores == ["2-1"], res.drafts[-1].scores
    assert any("걷었다" in n for n in res.notes), res.notes
    # 🔴 **전부** 무승부면 넣지 않는다
    res2 = scenarios.Result()
    ok2 = scenarios._add(res2, claim=scenarios._claimer(res2), hint="시험2",
                         scores=["1-1", "2-2"], why="w", variables=["V1"],
                         game=nhl)
    assert ok2 is False and not res2.drafts
    # ⚠️ 무승부가 **있는** 리그에서는 걷지 않는다(반대 증거)
    soc = classify.Game(home="A", away="B", sport="soccer", league="L")
    res3 = scenarios.Result()
    scenarios._add(res3, claim=scenarios._claimer(res3), hint="시험3",
                   scores=["2-1", "1-1"], why="w", variables=["V1"], game=soc)
    assert res3.drafts[-1].scores == ["2-1", "1-1"], res3.drafts[-1].scores

