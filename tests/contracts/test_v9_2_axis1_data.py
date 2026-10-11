"""🔴🔴 **축1 데이터 일치 외 넷** — 사용자 지시 2026-10-11(마지막 넷).

> 7개는 됐다. 남은 넷 — 확률을 끄는 축1이 틀린 데이터에 서 있다.
> 1. 축1 데이터 일치 … 한 원천(같은 경기 목록)에서 두 창을 자른다.
>    계약: 최근 n경기 합 ≤ 최근 m경기 합(n<m, 득·실 각각). 어기면 축1 미계산 + 운영자 알림.
> 2. 운 할인 … T12 "운 요소 득점 k/n"이면 빼는 골은 최대 k. ×0.5 일괄 할인 삭제.
>    계약: 할인 골 수 ≤ 운 요소로 분류된 골 수.
> 3. 무기 꺼짐 기준 … "평소 XI(최근 폼 계산 기간)에 있었는데 오늘 빠진 선수"만 무기를 끈다.
>    고정물: 밴쿠버 꺼진 무기 ≥1(뮐러 비중이 15% 이상이면).
> 4. "우리 판단 유지" 근거 검열 … 같은 방향 근거가 없으면 "근거 부족 — 시장과 갈림".
>    Elo가 우리와 같은 방향이면 "시장이 다르게 보는 까닭"에 Elo를 쓰지 않는다.

🔴 실사고가 무엇이었나: 카드의 **폼 블록은 밴쿠버 실점 2.0×5=10**, 축1 은 **실점 9
   (10경기)** 였다. 5경기 합이 10경기 합보다 크다 — **불가능하다.** 두 블록이
   *다른 원천*(fotmob 폼 블록 vs 경기 페이지 목록)을 읽고 있었다.
"""
from __future__ import annotations

import inspect

from app.core import compare, form, matchup, style
from app.core.schema import (AdjProb, BaseProb, MarketProb, MatchRef,
                             ProbTriple, Variable)


def _code(mod) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
    import ast
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════
# 1. 축1 데이터 일치 — 한 원천, 두 창
# ══════════════════════════════════════════════════════════════════

GAMES = [
    {"date": "2026-08-01", "league": "MLS", "opp": "A", "side": "home",
     "score": "2-1", "gf": 2, "ga": 1},
    {"date": "2026-08-08", "league": "MLS", "opp": "B", "side": "away",
     "score": "0-3", "gf": 0, "ga": 3},
    {"date": "2026-08-15", "league": "MLS", "opp": "C", "side": "home",
     "score": "1-1", "gf": 1, "ga": 1},
    {"date": "2026-08-22", "league": "MLS", "opp": "D", "side": "away",
     "score": "1-0", "gf": 1, "ga": 0},
    {"date": "2026-08-29", "league": "MLS", "opp": "E", "side": "home",
     "score": "3-2", "gf": 3, "ga": 2},
    {"date": "2026-09-05", "league": "MLS", "opp": "F", "side": "away",
     "score": "0-1", "gf": 0, "ga": 1},
    {"date": "2026-09-12", "league": "MLS", "opp": "G", "side": "home",
     "score": "2-0", "gf": 2, "ga": 0},
    {"date": "2026-09-19", "league": "MLS", "opp": "H", "side": "away",
     "score": "1-2", "gf": 1, "ga": 2},
    {"date": "2026-09-26", "league": "MLS", "opp": "I", "side": "home",
     "score": "1-1", "gf": 1, "ga": 1},
    {"date": "2026-10-03", "league": "MLS", "opp": "J", "side": "away",
     "score": "2-2", "gf": 2, "ga": 2},
]


def test_window_sums_one_source() -> None:
    """🔴 두 창은 **같은 목록**에서 잘린다 — 5창 합 ≤ 10창 합."""
    five = form.window_sums(GAMES, 5)
    ten = form.window_sums(GAMES, 10)
    assert five["n"] == 5 and ten["n"] == 10
    #: 🔴 뒤에서 자른다(최근 n경기) — 목록의 **마지막** 5경기다
    assert five["gf"] == sum(g["gf"] for g in GAMES[-5:])
    assert five["ga"] == sum(g["ga"] for g in GAMES[-5:])
    assert five["gf"] <= ten["gf"] and five["ga"] <= ten["ga"]


def test_window_violation_is_caught_and_named() -> None:
    """🔴 어기면 **빈 글자가 아니라 사유**를 낸다(운영자 알림의 재료)."""
    assert form.windows_bad(GAMES) == ""
    bad = form.sums_bad({"n": 5, "gf": 7, "ga": 10},
                        {"n": 10, "gf": 10, "ga": 9})
    assert bad and "실" in bad and "5" in bad and "10" in bad


def test_axis1_not_measured_when_windows_disagree() -> None:
    """🔴 창이 어긋나면 **축1 을 안 센다**(틀린 수를 확률로 보내지 않는다)."""
    one = form.form_of("홈", [{"gf": 2, "ga": 1, "opp": "A"}] * 10, elo={})
    two = form.form_of("원정", [{"gf": 1, "ga": 1, "opp": "B"}] * 10, elo={})
    box = {"form": {"home": one, "away": two},
           "window_bad": {"away": "🔴 최근 5경기 실점 10 > 최근 10경기 실점 9"}}
    got = matchup.axis1(box, None, r={})
    assert got.gap is None, "창이 어긋났는데 축1 을 셌다"
    assert "창" in got.why or "경기 목록" in got.why


def test_axis1_prints_both_windows() -> None:
    """🔴 축1 사유에 **두 창**(5·10)이 다 적힌다 — 카드가 그 수를 보여야 한다."""
    one = form.form_of("홈", [{"gf": 2, "ga": 1, "opp": "A"}] * 10, elo={})
    two = form.form_of("원정", [{"gf": 1, "ga": 1, "opp": "B"}] * 10, elo={})
    box = {"form": {"home": one, "away": two},
           "games": {"home": GAMES, "away": GAMES}}
    why = matchup.axis1(box, None, r={}).why
    assert "최근 5경기" in why and "최근 10경기" in why


def test_s2e_builds_one_game_list() -> None:
    """🔴 배선 — `s2e_matchup` 이 **한 경기 목록**(`games`)을 내고 창 검사를 돈다."""
    from app.core.stages import s2e_matchup
    src = _code(s2e_matchup)
    assert "games" in src, "경기 목록을 안 낸다"
    assert "windows_bad" in src, "창 검사를 안 돈다"
    #: 🔴 날짜·대회·스코어를 들고 다닌다(사용자가 나란히 보는 표의 재료)
    assert "league" in src and "score" in src


def test_card_form_block_reads_the_same_list() -> None:
    """🔴🔴 카드의 폼 블록도 **그 목록**에서 센다 — 두 원천 금지."""
    import ast
    import inspect as _i
    from app.core import render
    src = ast.unparse(ast.parse(_i.getsource(render._b3)))
    assert "_b3_games" in src, "폼 블록이 아직 다른 원천만 읽는다"
    made = ast.unparse(ast.parse(_i.getsource(render._b3_games)))
    assert "matchup" in made and "games" in made, "상성 재료의 목록을 안 본다"
    assert "window_sums" in made, "창 합을 제 손으로 세고 있다(사본 금지)"


# ══════════════════════════════════════════════════════════════════
# 2. 운 할인 — 빼는 골은 최대 k
# ══════════════════════════════════════════════════════════════════

def test_luck_cut_is_goals_not_a_ratio() -> None:
    """🔴 10골 중 운 3골이면 **7** 이다(×0.5 일괄 할인 금지)."""
    rows = [{"gf": 1, "ga": 1, "opp": "A"}] * 10
    got = form.form_of("팀", rows, elo={}, luck_goals=3)
    assert got.gf == 10
    assert got.luck_cut_goals == 3
    assert abs(float(got.gf_after_luck) - 7.0) < 1e-6, got.gf_after_luck


def test_luck_cut_never_exceeds_lucky_goals() -> None:
    """🔴 계약 — **할인 골 수 ≤ 운 요소로 분류된 골 수**."""
    rows = [{"gf": 1, "ga": 1, "opp": "A"}] * 10
    for k in (0, 1, 3, 9, 10, 14):
        got = form.form_of("팀", rows, elo={}, luck_goals=k)
        assert got.luck_cut_goals <= k
        assert got.luck_cut_goals <= got.gf
        assert float(got.gf_after_luck) >= 0.0


def test_blanket_ratio_discount_is_gone() -> None:
    """🔴 `form_attack_discount` 비율을 폼에 곱하는 길이 **없다**."""
    src = _code(form)
    assert "luck_discount" not in src, "비율 할인 인자가 남아 있다"
    from app.core.stages import s2e_matchup
    assert "luck_discount" not in _code(s2e_matchup)


def test_t12_carries_the_goal_count() -> None:
    """🔴 T12 가 **운 요소 골 수**를 들고 온다 — 비율만으로는 골을 못 뺀다."""
    from app.core import goals as _goals
    assert "luck_goals" in _code(_goals)


# ══════════════════════════════════════════════════════════════════
# 3. 무기 꺼짐 — 평소 XI 에 있었던 선수만
# ══════════════════════════════════════════════════════════════════

def _read(key_state: dict, att: dict):
    from app.core.strategy import TeamRead
    return TeamRead(team="밴쿠버", key_state=dict(key_state),
                    att_table=dict(att))


def test_long_absentee_does_not_turn_weapons_off() -> None:
    """🔴🔴 그 기간 내내 빠져 있던 선수는 **폼에 이미 들어 있다**(이중 계산 금지)."""
    read = _read({"Ebobisse": "명단 제외"}, {"Ebobisse": 9, "Müller": 6,
                                             "Others": 15})
    got = style.off_weapons(read, None, usual={"Müller", "Berhalter"})
    assert got == [], f"장기 결장으로 무기를 껐다: {got}"


def test_newly_out_player_turns_weapons_off() -> None:
    """🔴 고정물 — 평소 XI 에 있던 선수가 오늘 빠지고 비중 ≥15% 면 **≥1 꺼진다**."""
    read = _read({"Müller": "명단 제외", "Ebobisse": "명단 제외"},
                 {"Müller": 6, "Ebobisse": 9, "Others": 15})
    got = style.off_weapons(read, None, usual={"Müller", "Berhalter"})
    assert len(got) >= 1, "새로 빠진 주 기여자인데 무기가 안 꺼졌다"


def test_usual_xi_comes_from_the_form_window() -> None:
    """🔴 배선 — 평소 XI 는 **폼 창의 선발 명단**에서 온다(`_history`)."""
    from app.core.stages import s2e_matchup
    src = _code(s2e_matchup)
    assert "starters" in src, "과거 선발을 안 받아 온다"
    assert "usual" in src, "평소 XI 를 무기 꺼짐에 안 넘긴다"


# ══════════════════════════════════════════════════════════════════
# 4. "우리 판단 유지" 근거 검열
# ══════════════════════════════════════════════════════════════════

def _ref() -> MatchRef:
    return MatchRef(id="m1", sport="soccer", competition="MLS",
                    competition_short="MLS", home="team:000001",
                    away="team:000002", home_name="LAFC",
                    away_name="밴쿠버", kickoff_utc="2026-10-12T02:30:00Z")


def _market(home: float, draw: float, away: float) -> MarketProb:
    return MarketProb(probs={"win:home": home, "win:draw": draw,
                             "win:away": away}, source="test", used=True)


def test_evidence_against_us_cannot_support_us() -> None:
    """🔴🔴 우리 결론이 **원정**인데 근거가 홈을 밀면 "유지"를 못 낸다."""
    vars_ = [Variable(id="IR02-home", type="absence", subject="team:000001",
                      favors="home", hardness="hard", weight=1.0,
                      usable_as_basis=True, claim="x", quote="q")]
    out = compare.market_reasons(
        BaseProb(probs=ProbTriple(home=0.3, draw=0.25, away=0.45),
                 home_elo=1540, away_elo=1574, dr=-34),
        AdjProb(strength_pct={"home": -2.0}),
        _market(0.52, 0.24, 0.24), vars_, _ref(),
        ours=ProbTriple(home=0.33, draw=0.24, away=0.43))
    said = "\n".join(out)
    assert "근거 부족" in said and "시장과 갈림" in said, said
    assert "우리 판단 유지" not in said, said


def test_same_direction_evidence_keeps_our_call() -> None:
    """🔴 방향이 같으면 그대로 "유지" 다(검열이 전부를 막지 않는다)."""
    vars_ = [Variable(id="IR02-home", type="absence", subject="team:000001",
                      favors="away", hardness="hard", weight=1.0,
                      usable_as_basis=True, claim="x", quote="q")]
    out = compare.market_reasons(
        BaseProb(probs=ProbTriple(home=0.3, draw=0.25, away=0.45),
                 home_elo=1540, away_elo=1574, dr=-34),
        AdjProb(strength_pct={"home": -2.0}),
        _market(0.52, 0.24, 0.24), vars_, _ref(),
        ours=ProbTriple(home=0.33, draw=0.24, away=0.43))
    said = "\n".join(out)
    assert "우리 판단 유지" in said, said


def test_elo_on_our_side_is_not_a_market_reason() -> None:
    """🔴 Elo 가 **우리와 같은 방향**이면 "시장이 다르게 보는 까닭"이 아니다."""
    out = compare.market_reasons(
        BaseProb(probs=ProbTriple(home=0.3, draw=0.25, away=0.45),
                 home_elo=1540, away_elo=1574, dr=-34),
        AdjProb(), _market(0.52, 0.24, 0.24), [], _ref(),
        ours=ProbTriple(home=0.33, draw=0.24, away=0.43))
    said = "\n".join(out)
    tail = said.split("시장이 다르게 보는 까닭")
    assert len(tail) == 1 or "Elo" not in tail[1].split(")")[0], said


# ══════════════════════════════════════════════════════════════════
# 1-b. `facts.recent`(폼 블록·S01)도 **그 목록**에서 센다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-11(재현 1회차): 카드 블록 3 은 밴쿠버 **최근5 실 8**(1.60)을
#     적었는데 같은 카드의 `S01-away` 는 **실점 평균 2.0** 이었다 — `facts.recent`
#     가 *또 다른 파서*(fotmob 폼 블록·`team_recent`)에서 왔기 때문이다.

def test_facts_recent_comes_from_the_same_list() -> None:
    """🔴🔴 ① — `facts.recent` 의 수가 **같은 경기 목록**에서 나온다."""
    from app.core.stages import s2_facts
    got = s2_facts._recent_from_games(GAMES, kickoff=None)
    five = form.window_sums(GAMES, 5)
    assert got["matches"] == 5
    assert abs(got["recent_scored_avg"] - five["gf"] / 5) < 1e-6
    assert abs(got["recent_conceded_avg"] - five["ga"] / 5) < 1e-6
    #: 🔴 목록 자체도 들고 있다(카드·축1 이 같은 줄을 본다)
    assert len(got["games"]) == len(GAMES)
    #: 🔴 **최신이 앞**이다(`team_recent`·`parse_form` 과 같은 순서)
    assert got["last5"] == ["D", "D", "L", "W", "L"]
    assert got["sequence"][0]["date"] == GAMES[-1]["date"]
    #: 🔴 `s5_verify._form_goal_dirs` 가 읽는 칸이 **있어야** 실점 방향이 남는다
    assert "goals_against" in got["sequence"][0]


def test_s2_facts_is_wired_to_that_list() -> None:
    """🔴 배선 — `s2_facts` 가 상성의 그 목록 함수를 부른다(사본 금지)."""
    from app.core.stages import s2_facts
    src = _code(s2_facts)
    assert "games_of" in src and "_recent_from_games" in src


# ══════════════════════════════════════════════════════════════════
# 3-b. 평소 XI 는 **자주 선발로 뛴 선수**다 — 창에 한 번 낀 선수가 아니다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 실측 2026-10-11(밴쿠버 8경기 · LAFC 10경기):
#     뮐러 **6/8** · 바드왈 2/8 · 아데쿠그베 1/8 · 에보비세 **3/10** · 틸먼 3/10.
#  ⚠️ 그래서 *"창 안에 한 번이라도 선발"* 로 평소 XI 를 만들면 밴쿠버가 **32명**,
#     LAFC 가 22명이다 — 로테이션 선수까지 다 들어와 "오늘 빠졌다"가 무의미해진다.
#  🔴 사용자 지시 ③ 의 *"평소 XI"* 는 **그 창에서 주로 뛴 선수**로 읽는다.

def _rows(starters: list[list[str]]) -> list[dict]:
    """🔴 `_history` 꼴 줄들 — 선발 명단만 다르게."""
    return [{"home_name": "A", "away_name": "B", "mine_home": True,
             "utc": f"2026-09-0{i + 1}T00:00:00Z", "league": "MLS",
             "starters": list(xs), "goals": [], "stats": {}}
            for i, xs in enumerate(starters)]


def test_usual_xi_needs_most_of_the_window() -> None:
    """🔴 절반 이상 선발이면 평소 XI, 한두 번이면 아니다."""
    from app.core.stages import s2e_matchup
    rows = _rows([["Müller", "White"], ["Müller", "White"],
                  ["Müller", "Badwal"], ["White", "Diaby"]])
    got = s2e_matchup.usual_xi(rows)
    assert "Müller" in got and "White" in got
    assert "Badwal" not in got and "Diaby" not in got


def test_usual_xi_skips_games_without_lineups() -> None:
    """🔴 선발 명단이 없는 경기는 **분모에서 뺀다**(없는 것을 0 으로 세지 않는다)."""
    from app.core.stages import s2e_matchup
    rows = _rows([["Müller"], [], [], ["Müller"]])
    assert "Müller" in s2e_matchup.usual_xi(rows)


def test_weapons_off_counts_absences_outside_the_top_two() -> None:
    """🔴🔴 ③ 고정물 — 평소 XI 의 **결장**이면 무기가 꺼진다.

    ⚠️ 실측 2026-10-11: `key_state` 는 리그 페이지의 **팀당 상위 2명**만 든다 —
       그래서 뮐러(6/8 선발 · 오늘 결장)가 **어디에도 안 세어져** 밴쿠버의 꺼진
       무기가 0 이었다(양 팀 중 한쪽만 끄는 그 상태가 축2 를 끌었다).
    """
    read = _read({}, {"Thomas Müller": 8, "Brian White": 7, "Others": 20})
    got = style.off_weapons(read, None, usual={"Thomas Müller", "Brian White"},
                            out_today={"Thomas Müller"})
    assert len(got) >= 1, "평소 XI 의 결장인데 무기가 안 꺼졌다"


def test_fringe_absence_still_turns_nothing_off() -> None:
    """🔴 평소 XI 가 아닌 선수의 결장은 **끄지 않는다**(폼에 이미 들어 있다)."""
    read = _read({}, {"Jeremy Ebobisse": 9, "Others": 20})
    got = style.off_weapons(read, None, usual={"Denis Bouanga"},
                            out_today={"Jeremy Ebobisse"})
    assert got == [], got


def test_s2e_passes_todays_absences() -> None:
    """🔴 배선 — 오늘 **결장·벤치**를 무기 꺼짐에 넘긴다(`facts.missing`)."""
    from app.core.stages import s2e_matchup
    src = _code(s2e_matchup)
    assert "out_today" in src and "missing" in src


def test_out_today_reads_the_real_absence_field() -> None:
    """🔴 `facts.missing` 의 **그 칸 이름**으로 읽는다 — 빈 집합을 조용히 돌리지 않게.

    ⚠️ 실사고 2026-10-11: 내가 `player` 로 적었다(실제 칸은 `name` · `schema.
       Missing`). 계약이 없으면 *"꺼진 무기 0"* 으로 조용히 통과했을 자리다.
    """
    from app.core.schema import Facts, Missing
    from app.core.stages import s2e_matchup
    facts = Facts(missing={"team:000002": [
        Missing(name="Thomas Müller", pos="AM", reason="injury")]})
    assert s2e_matchup._out_today(facts, "team:000002") == {"Thomas Müller"}


def test_variable_path_obeys_the_same_gate() -> None:
    """🔴🔴 ③ — **변수 경로**(`off_from_vars`)도 평소 XI 문을 지난다.

    ⚠️ 실측 2026-10-11(재현 3회차): 꺼진 무기가 여전히 `home 3 · away 0` 이었다.
       까닭은 `off_weapons` 가 아니라 **`off_from_vars`** 다 — `IR02-home`
       (*"직전 선발 Jeremy Ebobisse 가 오늘 명단에 없다"*)이 공격 축 셋을
       통째로 껐다. 🔴 에보비세는 **3/10 선발**로 평소 XI 가 아니다.
    """
    from app.core.stages import s2e_matchup
    src = _code(s2e_matchup)
    assert "off_from_vars" in src
    #: 🔴 문은 `usual ∩ out_today` 다 — 그 교집합이 비면 끌 무기가 없다
    assert "_gate_off" in src, "변수 경로에 문이 없다"
    assert s2e_matchup._gate_off(["forward"], usual={"A"},
                                 out_today={"B"}) == []
    assert s2e_matchup._gate_off(["forward"], usual={"A"},
                                 out_today={"A"}) == ["forward"]
    #: ⚠️ 평소 XI 를 못 만들었으면(선발 자료 0) **막지 않는다** — 없는 자료로
    #    있는 사실을 지우지 않는다(#3)
    assert s2e_matchup._gate_off(["forward"], usual=set(),
                                 out_today=set()) == ["forward"]


# ══════════════════════════════════════════════════════════════════
# 3-c. 공격 기여 **비중**은 그 팀 안에서 센다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 실측 2026-10-11(fotmob 선수단 페이지):
#     밴쿠버 25명 득점+도움 합 **85** — 뮐러 **15(17.6%)** · 바드왈 3(3.5%)
#     LAFC   30명 합 **62** — 부앙가 19(30.6%) · 손흥민 16(25.8%) · 에보비세 0
#  ⚠️ `s2_facts` 가 두 팀 선수단을 **한 표로 합쳐**(`out.update`) 담았다. 그래서
#     뮐러의 비중이 15/(85+62)=**10.2%** 로 읽혀 문턱(15%)을 못 넘었고, 밴쿠버
#     꺼진 무기가 **0** 이었다(사용자 고정물 위반).

def test_att_table_is_one_team() -> None:
    """🔴 `read.att_table` 은 **그 팀**의 표다 — 두 팀을 섞으면 비중이 반이 된다."""
    from app.core import strategy
    from app.core.schema import Facts
    facts = Facts(
        player_stats={"Thomas Müller": {"goals": 10, "assists": 5},
                      "Denis Bouanga": {"goals": 14, "assists": 5}},
        player_stats_team={
            "team:000002": {"Thomas Müller": {"goals": 10, "assists": 5},
                            "Brian White": {"goals": 12, "assists": 7}}})
    one = strategy._att_table(facts, key="team:000002")
    assert set(one) == {"Thomas Müller", "Brian White"}
    assert abs(one["Thomas Müller"] / sum(one.values()) - 15 / 34) < 1e-6
    #: ⚠️ 팀별 표가 없으면 **합친 표**를 쓴다(있는 수를 버리지 않는다)
    both = strategy._att_table(facts, key="team:000099")
    assert "Denis Bouanga" in both


def test_s2_facts_keeps_the_table_per_team() -> None:
    """🔴 배선 — 선수단 기록을 **팀별로도** 담는다."""
    from app.core.stages import s2_facts
    assert "player_stats_team" in _code(s2_facts)


def test_weapons_off_says_why_it_is_zero() -> None:
    """🔴🔴 #3 조용한 0 금지 — 꺼진 무기가 0 이면 **까닭**이 사유에 남는다.

    ⚠️ 실사고 2026-10-11(재현 4·5회차): `꺼진 무기 away 0` 만 적혀 있어
       *평소 XI 를 못 만든 것인지 · 빠진 선수가 없는 것인지 · 비중이 모자란
       것인지* 를 가릴 수 없었다 — 그래서 고치는 데 두 번을 더 돌렸다.
    """
    from app.core.stages import s2e_matchup
    src = _code(s2e_matchup)
    assert "off_why" in src, "꺼진 무기의 까닭을 안 적는다"
    got = s2e_matchup._off_why(usual={"Thomas Müller", "Brian White"},
                               out_today={"Thomas Müller"},
                               share=0.176, table=25)
    assert "평소 XI 2명" in got and "Thomas Müller" in got
    assert "17.6%" in got or "18%" in got
    none = s2e_matchup._off_why(usual=set(), out_today={"X"}, share=0.0,
                                table=0)
    assert "평소 XI 를 못 만들었다" in none


def test_card_prints_the_weapons_reason() -> None:
    """🔴 #3 — 카드가 **꺼짐 판정**을 적는다(0 이어도)."""
    import ast
    import inspect as _i
    from app.core import matchup, render
    src = ast.unparse(ast.parse(_i.getsource(render.matchup_report_long)))
    assert "off_why" in src and "꺼짐 판정" in src
    assert "off_why" in [f.name for f in
                         __import__("dataclasses").fields(
                             matchup.MatchupReport)]


def test_att_table_ignores_the_other_teams_key_players() -> None:
    """🔴🔴 ③ — `standings["key_players"]` 도 **그 팀 칸만** 더한다.

    ⚠️ 실사고 2026-10-11(재현 7회차): 모든 팀의 상위 2명을 더해 밴쿠버 기여표가
       27명(합 120)이 되어 뮐러가 **12.5%** 로 읽혔다(실제 15/85=17.6%) — 문턱
       15% 를 못 넘어 꺼진 무기 0 이었다.
    """
    from app.core import strategy
    from app.core.schema import Facts
    facts = Facts(
        player_stats_team={"team:000002": {
            "Thomas Müller": {"goals": 10, "assists": 5},
            "Brian White": {"goals": 12, "assists": 7}}},
        standings={"key_players": {
            "team:000002": [{"name": "Brian White", "value": 19}],
            "team:000001": [{"name": "Denis Bouanga", "value": 19},
                            {"name": "Heung-Min Son", "value": 16}]}})
    one = strategy._att_table(facts, key="team:000002")
    assert "Denis Bouanga" not in one and "Heung-Min Son" not in one
    assert abs(one["Thomas Müller"] / sum(one.values()) - 15 / 34) < 1e-6
