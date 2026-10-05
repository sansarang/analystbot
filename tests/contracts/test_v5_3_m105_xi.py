"""🔴🔴 **M105~M108 — XI 변수·평균 보정·경기 형식**.

지시서 `docs/fable/inbox/2026-10-05_workorder_idn_tha_fixes.md` §3.

> **3-1 확정 XI 를 변수로**(`lineup_intent` 유형, **코드가 생성**)
>  · **수비 숫자**: 포메이션 첫 숫자(`5-3-2`·`3-4-3`), 없으면 XI 포지션 집계.
>    5백 → `favors: goals_down`, 주장 문장 `"{팀} 5백 선발 — 내려앉는 운영"`.
>  · **주전 이탈**: 직전 경기 XI 중 선발에서 빠진 선수 → `absence_att`(공격수·
>    공격형 MF) 또는 `absence_def`. 벤치면 "벤치", 명단에 없으면 "결장".
>  · **복귀**: 직전 경기 징계·부상으로 빠졌다 돌아온 선수 → 그 팀 쪽.
>  🔴 이 셋은 리드·에이전트가 아니라 **코드가 XI 사실에서 만든다**(재현 가능).
>
> **3-2 평균 득점 보정** — 최근 N경기 중 한 경기 득점이 나머지 평균의 **2배
> 이상**이면 그 경기를 뺀 평균을 함께 계산한다. 주장 문장:
> `"평균 3.6골(9-2 방글라데시전 제외 시 2.0)"`. 🔴 시나리오 strength·필수형
> 판정에는 **보정 평균**을 쓴다. 보정이 원 평균보다 **1.0 이상 낮으면 회귀형
> (저득점) 시나리오 필수**.
>
> **3-3 경기 형식** — `match_format`: `league|group|knockout_single|
> knockout_two_leg_1st|knockout_two_leg_2nd|final_single|friendly` +
> `extra_time: bool`·`penalties: bool`. 모르면 `unknown`(지어내지 않는다).
> 🔴 `final_single`·`knockout_single`·`knockout_two_leg_1st` 이면 **90분
> 무승부(0-0·1-1) 시나리오 필수**.
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# M105 — 5백 XI → `goals_down` 변수(확정 XI 면 hard)
# ══════════════════════════════════════════════════════════════════
def test_M105_수비_숫자를_포메이션에서_읽는다():
    from app import classify
    assert hasattr(classify, "back_line"), (
        "🔴 `classify.back_line(포메이션, 선수들)` 이 없다")
    assert classify.back_line("5-3-2", []) == 5
    assert classify.back_line("3-4-3", []) == 3
    assert classify.back_line("4-4-2", []) == 4
    # 🔴 **없으면 `None`** — 지어내지 않는다(#4)
    assert classify.back_line("", []) is None
    assert classify.back_line("알 수 없음", []) is None


def test_M105_5백이면_goals_down_변수가_선다():
    from app import classify
    assert hasattr(classify, "xi_variables"), (
        "🔴 `classify.xi_variables(...)` 가 없다 — XI 를 변수로 바꿀 곳")
    got = classify.xi_variables(
        team="team:000111", formation="5-3-2",
        players=["GK", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        url="https://a.com/xi", confirmed=True)
    low = [v for v in got if v.get("type") == "lineup_intent"]
    assert low, f"🔴 5백인데 `lineup_intent` 변수가 없다: {got}"
    v = low[0]
    assert v.get("favors") == "goals_down", v
    assert "5백" in str(v.get("claim")), v
    assert v.get("hardness") == "hard", (
        "🔴 **확정 XI** 면 `hard` 다(지시서 §3-1)")
    # 🔴 예상 XI 면 `soft`
    soft = classify.xi_variables(
        team="team:000111", formation="5-3-2", players=["GK"] * 11,
        url="https://a.com/xi", confirmed=False)
    assert soft and soft[0].get("hardness") == "soft", soft


def test_M105_4백은_그_변수를_안_만든다():
    from app import classify
    got = classify.xi_variables(
        team="team:000111", formation="4-4-2", players=["GK"] * 11,
        url="https://a.com/xi", confirmed=True)
    assert not [v for v in got if v.get("favors") == "goals_down"], got


# ══════════════════════════════════════════════════════════════════
# M106 — 직전 XI 주전이 벤치면 `absence` 변수(그 팀 **반대쪽** favors)
# ══════════════════════════════════════════════════════════════════
def test_M106_주전_이탈이_변수로_선다():
    from app import classify
    got = classify.xi_variables(
        team="team:000111", formation="4-4-2",
        players=["Kampol", "Waris", "Kritsada", "Peerawat", "Chaiyaphon",
                 "Teerapat", "Peeradol", "Anan", "Iklas", "X", "Y"],
        url="https://a.com/xi", confirmed=True,
        # 🔴 직전 경기 XI — 거기 있었는데 지금 없으면 이탈이다
        last_xi=["Kampol", "Waris", "Kritsada", "Peerawat", "Chaiyaphon",
                 "Teerapat", "Peeradol", "Supachok", "Soonsup-Bell", "X", "Y"],
        bench=["Supachok"])
    out = [v for v in got if str(v.get("type")).startswith("absence")]
    assert out, f"🔴 Supachok·Soonsup-Bell 이탈이 변수로 안 섰다: {got}"
    said = " ".join(str(v.get("claim")) for v in out)
    assert "Supachok" in said and "벤치" in said, said
    assert "Soonsup-Bell" in said and "결장" in said, (
        f"🔴 명단에 없는 선수를 **결장**으로 안 적었다: {said}")
    # 🔴 그 팀의 **반대쪽**에 유리하다
    assert all(v.get("favors") == "opponent" for v in out), out


def test_M106_복귀는_그_팀_쪽이다():
    from app import classify
    got = classify.xi_variables(
        team="team:000108", formation="3-4-3", players=["Haye"] + ["X"] * 10,
        url="https://a.com/xi", confirmed=True,
        last_xi=["X"] * 11, out_last=["Haye"])
    back = [v for v in got if "복귀" in str(v.get("claim"))]
    assert back, f"🔴 복귀가 변수로 안 섰다: {got}"
    assert back[0].get("favors") == "subject", back


# ══════════════════════════════════════════════════════════════════
# M107 — 이상치 경기를 뺀 보정 평균 · 1.0 이상 낮으면 회귀 필수
# ══════════════════════════════════════════════════════════════════
def test_M107_이상치를_뺀_보정_평균():
    from app.collect import fotmob
    assert hasattr(fotmob, "trimmed_avg"), (
        "🔴 `fotmob.trimmed_avg(득점들)` 이 없다")
    # 🔴 인도네시아 실측: 9-2 한 경기(9골)가 평균을 끌어올렸다
    got, why = fotmob.trimmed_avg([9, 1, 2, 1, 3])
    assert abs(got - 1.75) < 0.01, (got, why)
    assert "9" in why, why
    # 🔴 이상치가 없으면 **원 평균 그대로**이고 사유는 빈 글
    same, why2 = fotmob.trimmed_avg([2, 2, 3, 1, 2])
    assert abs(same - 2.0) < 0.01 and not why2, (same, why2)
    # ⚠️ 표본이 2개 미만이면 **안 깎는다**
    one, _w = fotmob.trimmed_avg([5])
    assert abs(one - 5.0) < 0.01


def test_M107_보정이_낮으면_회귀가_필수다():
    from app import scenarios
    assert hasattr(scenarios, "regression_needed"), (
        "🔴 `scenarios.regression_needed(원평균, 보정평균)` 이 없다")
    need, why = scenarios.regression_needed(3.6, 2.0)
    assert need, why
    # 🔴 **수를 글자로 보지 않는다** — `1.0` 이 `%g` 로 `1` 로 찍힌다.
    #    사유에 **차이**가 들어 있으면 된다(독자가 왜인지 안다).
    assert "1.60" in why or "1.6" in why, why
    assert str(scenarios.REGRESSION_GAP).rstrip("0").rstrip(".") in why, why
    no, why2 = scenarios.regression_needed(2.4, 2.0)
    assert not no, why2


# ══════════════════════════════════════════════════════════════════
# M108 — `final_single` 등이면 90분 무승부 시나리오 필수
# ══════════════════════════════════════════════════════════════════
def test_M108_형식이_필수형을_정한다():
    from app import scenarios
    assert hasattr(scenarios, "FORMATS"), "🔴 `scenarios.FORMATS` 가 없다"
    for want in ("league", "group", "knockout_single",
                 "knockout_two_leg_1st", "knockout_two_leg_2nd",
                 "final_single", "friendly", "unknown"):
        assert want in scenarios.FORMATS, f"🔴 `{want}` 가 없다"
    assert hasattr(scenarios, "draw_needed")
    for fmt in ("final_single", "knockout_single", "knockout_two_leg_1st"):
        need, why = scenarios.draw_needed(fmt)
        assert need, f"🔴 `{fmt}` 인데 90분 무승부가 필수가 아니다: {why}"
        assert "연장" in why or "승부차기" in why, why
    for fmt in ("league", "group", "friendly", "unknown"):
        assert not scenarios.draw_needed(fmt)[0], fmt


def test_M108_무승부_시나리오가_없으면_incomplete():
    from app import classify, scenarios
    game = classify.Game(home="Indonesia", away="Thailand", sport="soccer",
                         league="FIFA ASEAN Cup")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["3-1"], strength=2.0,
                                  template_id="t", why="w")]
    ok = scenarios.require_draw(res, game, fmt="final_single")
    assert not ok, "🔴 90분 무승부가 없는데 통과했다"
    assert res.incomplete and res.incomplete_why
    res.drafts.append(scenarios.Draft(id="B", scores=["1-1"], strength=1.0,
                                      template_id="t", why="w"))
    assert scenarios.require_draw(res, game, fmt="final_single"), (
        f"🔴 `1-1` 을 넣었는데 아직 막는다: {res.incomplete_why}")
    assert not res.incomplete_why, res.incomplete_why
