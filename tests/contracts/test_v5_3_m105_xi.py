"""🔴🔴 **M105~M108 — XI 변수·평균 보정·경기 형식**.

지시서 `docs/fable/archive/2026-10-05_workorder_idn_tha_fixes.md` §3.

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
from datetime import datetime, timezone


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


def test_M108_무승부가_없으면_코드가_보강한다():
    """🔴🔴 §3-3 은 **자동 보강**이다(`on_missing: 추가`) — 막기만 하지 않는다.

    ⚠️ 종전 계약이 *"없으면 `incomplete`"* 를 못 박고 있었다. 그러면 단판
       결승마다 카드가 막힌다 — `from_deepseek` 가 `added_by="template"` 인 C
       초안을 **버리기** 때문이다(실측으로 확인한 경로다).
    🔴 보강된 초안은 `added_by="required"` 여야 한다 — 그래야 교체를 **살아
       남는다**. 그 칸을 안 보면 이 계약은 아무것도 막지 않는다.
    """
    from app import classify, scenarios
    game = classify.Game(home="Indonesia", away="Thailand", sport="soccer",
                         league="FIFA ASEAN Cup")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["3-1"], strength=2.0,
                                  template_id="t", why="w")]
    ok = scenarios.require_draw(res, game, fmt="final_single")
    assert ok, f"🔴 보강했어야 한다: {res.incomplete_why} · {res.notes}"
    added = [d for d in res.drafts
             if any(sc in scenarios.draw_scores() for sc in d.scores)]
    assert added, (f"🔴 90분 무승부 초안이 **안 들어갔다**: "
                   f"{[d.scores for d in res.drafts]}")
    assert added[0].added_by == "required", (
        f"🔴 `added_by={added[0].added_by!r}` — `required` 가 아니면 DeepSeek "
        f"교체가 이 초안을 **버린다**(그러면 보강이 헛일이다)")
    assert not res.incomplete_why, res.incomplete_why
    # 🔴 스코어는 **표가 든다** — 코드에 박힌 것이 아님을 확인한다(#1)
    assert set(added[0].scores) <= set(scenarios.draw_scores()), added[0].scores
    # 🔴 **두 번 불러도 하나다** — `generate` 와 DeepSeek 교체 뒤 두 번 돈다
    before = len(res.drafts)
    assert scenarios.require_draw(res, game, fmt="final_single")
    assert len(res.drafts) == before, (
        f"🔴 다시 세면서 **또 넣었다**({before} → {len(res.drafts)})")


def test_M108_보강이_불가능하면_막는다():
    """🔴 무승부가 **일어날 수 없는 리그**면 보강이 아니라 `incomplete` 다.

    ⚠️ 이 반대 증거가 없으면 위 계약이 *"언제나 통과"* 를 허락한다.
    """
    from app import classify, rules, scenarios
    assert rules.draw_possible("NHL")[0] is False, "🔴 전제가 바뀌었다"
    game = classify.Game(home="A", away="B", sport="hockey", league="NHL")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["3-1"], strength=2.0,
                                  template_id="t", why="w")]
    ok = scenarios.require_draw(res, game, fmt="final_single")
    assert not ok, f"🔴 무승부가 없는 리그인데 보강했다: {res.drafts}"
    assert res.incomplete and res.incomplete_why
    assert not [d for d in res.drafts
                if any(sc in scenarios.draw_scores() for sc in d.scores)], (
        "🔴 NHL 초안에 무승부 스코어가 들어갔다")


def test_M108_형식을_경기_페이지에서_읽는다():
    """🔴🔴 **①-1 실사고** — 재료가 있는데 안 읽었다(실측 2026-10-05).

    fotmob `6232991`(인도네시아–태국 결승) 페이지가 `"roundName":"final"` 을
    **명시**하는데 `games.round_note` 가 `None` 이었다. 🔴 그래서 형식이
    `unknown` 이고 90분 무승부 필수형이 **한 번도 발동하지 못했다.**
    """
    from app import scenarios
    from app.collect import fotmob
    # ① 수집기가 그 칸을 읽는가 — **페이지 꼴 그대로** 돌려서 본다
    page = {"props": {"pageProps": {"content": {"matchFacts": {"infoBox": {
        "Tournament": {"leagueName": "FIFA ASEAN Cup Premier Division",
                       "roundName": "final", "round": "final"}}}}}}}
    assert fotmob.round_note(page) == "final", fotmob.round_note(page)
    assert fotmob.round_note({}) == "", "🔴 못 읽으면 빈 문자열이어야 한다"
    # ② 그 글자가 형식이 되는가
    got, why = scenarios.match_format(
        round_note="final", competition="FIFA ASEAN Cup Premier Division")
    assert got == "final_single", (got, why)
    assert scenarios.draw_needed(got)[0], "🔴 그 형식이 필수형을 안 켠다"
    # ③ **지어내지 않는다** — 리그 라운드 번호는 형식이 아니다
    num, why2 = scenarios.match_format(round_note="1",
                                       competition="USL Championship")
    assert num == "unknown", (num, why2)
    assert "모른다" in why2, why2
    # ④ `semi-final` 이 `final` 로 새지 않는다(글자 포함 함정)
    semi, _ = scenarios.match_format(round_note="Semi-final", competition="x")
    assert semi == "knockout_single", semi


def test_배선_round_note_가_형식까지_이어진다():
    """🔴 #2 배선 — **끊긴 한 칸**이 이 결함의 전부였다. 사슬을 다 센다."""
    from app import analyze, classify, matchref
    row = {"id": 1, "ext_id": "fotmob:6232991", "home": "Indonesia",
           "away": "Thailand", "league": "FIFA ASEAN Cup Premier Division",
           "sport": "soccer", "round_note": "final",
           "starts_kst": datetime(2026, 10, 5, 13, tzinfo=timezone.utc)}
    ref = matchref.ref_from_row(row)
    assert ref.round_note == "final", "🔴 `MatchRef` 가 그 칸을 안 싣는다"
    game = classify.Game(home=ref.home, away=ref.away, sport=ref.sport,
                         league=ref.competition, round_note=ref.round_note)
    assert analyze._of(game, "round_note") == "final"
    # 🔴 dict 로 와도 읽는다(`scheduler._rerun_card` 가 dict 를 넘긴다)
    assert analyze._of(row, "round_note") == "final"
    # 🔴 카드가 그 칸을 **구조 사실로** 올리는가
    src = inspect.getsource(analyze.build)
    assert "match_format" in src, (
        "🔴 `build` 가 `match_format` 을 구조 사실에 안 넣는다 — 형식이 영영 "
        "`unknown` 이다")
    # 🔴 조건부 필수형이 DeepSeek 입력에서 **형식으로 갈리는가**(§3-3)
    assert "90분_무승부형" in analyze._required_forms_for(
        {"match_format": "final_single"})
    assert "90분_무승부형" not in analyze._required_forms_for(
        {"match_format": "league"})


# ══════════════════════════════════════════════════════════════════
# 🔴 **배선**(#2) — 안 이은 코드는 없는 코드보다 나쁘다
# ══════════════════════════════════════════════════════════════════
def test_배선_카드가_XI_변수를_만든다():
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "xi_variables" in called, (
        "🔴 카드가 `classify.xi_variables` 를 **안 부른다** — XI 가 이름 목록으로 "
        "남고 5백·주전이탈이 변수로 서지 않는다(지시서 §3-1)")


def test_배선_폼이_보정_평균을_싣는다():
    from app.collect import fotmob
    src = inspect.getsource(fotmob)
    assert '"recent_trimmed_avg"' in src, (
        "🔴 폼 사실에 `recent_trimmed_avg` 칸이 없다 — 보정 평균이 판정에 "
        "닿을 길이 없다(지시서 §3-2)")
    assert "trimmed_why" in src, (
        "🔴 보정 **사유**를 안 싣는다 — 카드가 *'9-2 제외 시'* 를 못 적는다(#3)")


def test_배선_형식과_회귀가_필수형에_걸린다():
    from app import scenarios
    tree = ast.parse(inspect.getsource(scenarios))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "draw_needed" in called or "require_draw" in called, (
        "🔴 `generate` 가 형식 필수형을 **안 부른다**(M108)")
    from app import analyze
    tree2 = ast.parse(inspect.getsource(analyze))
    called2 = {n.func.attr for n in ast.walk(tree2)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "require_draw" in called2, (
        "🔴 카드가 `require_draw` 를 안 부른다 — DeepSeek 교체 뒤 다시 세야 한다")
    assert "regression_needed" in called2, (
        "🔴 카드가 `regression_needed` 를 안 부른다 — 회귀형이 안 걸린다")
