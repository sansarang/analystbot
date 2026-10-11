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
    assert '"league"' in src and '"score"' in src


def test_card_form_block_reads_the_same_list() -> None:
    """🔴🔴 카드의 폼 블록도 **그 목록**에서 센다 — 두 원천 금지."""
    import ast
    import inspect as _i
    from app.core import render
    src = ast.unparse(ast.parse(_i.getsource(render._b3)))
    assert "games" in src, "폼 블록이 아직 다른 원천을 읽는다"
    assert "matchup" in src, "폼 블록이 상성 재료의 목록을 안 본다"


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
    return MarketProb(probs={"home": home, "draw": draw, "away": away},
                      source="test", used=True)


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
