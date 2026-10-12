"""🔴🔴 **적중률 다섯**(D·A·B·C·E) — 사용자 지시 2026-10-11.

> 데이터 축적 말고 **지금 봇이 든 재료**로. 순서 D > A > B > C > E.

D. 결장을 λ 에 닿게 — **공격 기여 비중**을 축0 에 넣는다(결장이 확률을 움직인다)
A. xG 를 축1 에 — 골 줄에 이미 있는 `xg` 를 폼에 쓴다
B. 축2 상쇄를 고친다 — **6축 차**를 직접 쓴다(양 팀 동시 발동이 서로 지우지 않게)
C. 홈/원정 분리 폼 — `games` 의 `side` 로 가른 뒤 전체 폼과 섞는다(수축)
E. 팀별 홈 이점 — `games` 의 홈/원정 득실로, 표본 적으면 리그 값으로 수축

🔴 계수를 **새로 짓지 않는다** — 쓰임만 바꾼다(비중·β·ELO_SLOPE 는 그대로 임시값).
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
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
# D — 결장이 λ 를 움직인다(축0 에 공격 기여 비중)
# ══════════════════════════════════════════════════════════════════

def test_axis0_counts_the_missing_share() -> None:
    """🔴🔴 D — **빠진 주전의 공격 기여 비중**이 축0 에 들어간다.

    ⚠️ 실측 2026-10-11: 카드가 *"라인업 보정 평소 대비 -0.3% — 확률은 **안
       움직였다**(환산 계수 없음)"* 라고 적었다. 핵심 공격수가 빠져도 λ 가 거의
       그대로였다 — 결장이 닿는 길이 선수 가치 로그합 하나뿐이었다.
    🔴 `att_share` 는 이미 센다(`뮐러 17.6%`) — 그 수를 축0 이 쓴다.
    """
    from app.core import matchup
    src = _src(matchup.axis0)
    assert "miss_share" in src, "빠진 선수 비중을 안 쓴다"
    #: 🔴 비중이 클수록 그 팀 축0 이 **내려간다**
    a = matchup.miss_move(0.0)
    b = matchup.miss_move(0.25)
    assert a == 0.0 and b < 0.0, (a, b)
    #: ⚠️ 상한이 있다(한 선수로 팀을 지우지 않는다)
    assert matchup.miss_move(1.0) >= matchup.MISS_CAP * -1 - 1e-9


def test_axis0_needs_the_player_to_be_key() -> None:
    """🔴🔴 D(사용자 지시 2026-10-11) — **핵심 선수인지 확인하고** 닿게 한다.

    > 결장선수가 핵심선수인지 확인하고 닿게 해라.

    🔴 "핵심"의 뜻 둘(둘 중 하나면 핵심이다):
       ① 공격 기여 비중이 문턱 이상(`KEY_SHARE`) — 그 팀 득점+도움의 몫
       ② 리그 페이지가 꼽은 **핵심 선수**(`strategy.key_state`)
    ⚠️ 비중을 못 쟀으면(기여표 0명) **닿지 않는다** — 0 으로 보지 않는다(#3).
    """
    from app.core import matchup
    #: ① 비중이 문턱 이상이면 핵심이다
    got, why = matchup.key_miss(shares={"p:a": 0.25}, keys=set(), table=20)
    assert got > 0 and "비중" in why, (got, why)
    #: ② 비중이 작아도 **리그가 꼽은 핵심**이면 센다
    got2, why2 = matchup.key_miss(shares={"p:b": 0.04}, keys={"p:b"}, table=20)
    assert got2 > 0 and "핵심" in why2, (got2, why2)
    #: 🔴 둘 다 아니면 **닿지 않는다**(로테이션을 결장으로 바꾸지 않는다)
    got3, why3 = matchup.key_miss(shares={"p:c": 0.04}, keys=set(), table=20)
    assert got3 == 0.0, (got3, why3)
    #: ⚠️ 기여표가 비면 **못 쟀다**고 적고 0 이다
    got4, why4 = matchup.key_miss(shares={"p:d": 0.4}, keys=set(), table=0)
    assert got4 == 0.0 and "못 쟀다" in why4, (got4, why4)


def test_axis0_why_says_the_share() -> None:
    """🔴 #3 — 그 수를 사유에 적는다(조용히 깎지 않는다)."""
    from app.core import matchup
    src = _src(matchup.axis0)
    assert "빠진 주전" in src or "결장 비중" in src


# ══════════════════════════════════════════════════════════════════
# A — xG 를 축1 에
# ══════════════════════════════════════════════════════════════════

def test_games_carry_xg() -> None:
    """🔴🔴 경기 줄의 **xG 두 종류를 가른다**(지시서 2026-10-12 ①).

    ⚠️ 종전 이 계약은 `xgf` 를 **득점한 골의 xG**(`goals[].xg`)로 고정했다 —
       🔴 그것은 *운 요소* 재료(T12)이고 **팀 xG 가 아니다**. 팀 xG 는 경기 통계
       `expected_goals` 다(실측 2026-10-12 · 12리그 36경기 전부에 있다).
    🔴 그래서 골의 xG 는 `luck_xg*` 로, 팀 xG 는 `xgf/xga` 로 갈라 싣는다.
    """
    from app.core.stages import s2e_matchup
    rows = [{"home_name": "A", "away_name": "B", "mine_home": True,
             "utc": "2026-09-01T00:00:00Z", "league": "L", "starters": [],
             "goals": [{"home": True, "xg": 0.8}, {"home": False, "xg": 0.3}],
             "stats": {"expected_goals": ({"n": 1.7}, {"n": 0.9})}}]
    got = s2e_matchup.games_of(rows)[0]
    # 🔴 운 요소 재료 — 골의 xG
    assert abs(float(got["luck_xgf"]) - 0.8) < 1e-9, got
    assert abs(float(got["luck_xga"]) - 0.3) < 1e-9, got
    # 🔴 폼이 보는 수 — 팀 xG
    assert abs(float(got["xgf"]) - 1.7) < 1e-9, got
    assert abs(float(got["xga"]) - 0.9) < 1e-9, got
    assert got["xg_n"] == 1, got


def test_team_xg_missing_is_named() -> None:
    """🔴 #3 — 팀 xG 가 없는 리그는 **0 이 아니라 사유**다."""
    from app.core.stages import s2e_matchup
    rows = [{"home_name": "A", "away_name": "B", "mine_home": True,
             "utc": "2026-09-01T00:00:00Z", "league": "L", "starters": [],
             "goals": [], "stats": {}}]
    got = s2e_matchup.games_of(rows)[0]
    assert got["xgf"] is None and got["xg_n"] == 0, got
    assert "팀 xG 없음" in got["adv_why"], got["adv_why"]


def test_xg_only_form_is_pure_xg() -> None:
    """🔴🔴 **xG 판은 100% xG**(사용자 결정 2026-10-12 1번) · 운 할인은 끈다."""
    from app.core import form
    rows = [{"gf": 3, "ga": 0, "opp": "X"}] * 5
    games = [{"gf": 3, "ga": 0, "xgf": 1.0, "xga": 1.0, "xg_n": 1}] * 5
    got = form.form_of("xG판", rows, elo={}, games=games, luck_goals=2.0,
                       xg_only=True)
    assert got.xg_only is True and got.xg_n == 5
    # 🔴 xG 가 같으면 지수는 0 이다 — 득실(3-0)도, 운 할인(2골)도 안 본다
    assert abs(float(got.index())) < 1e-9, (got.index(), got.why)


def test_form_blends_xg() -> None:
    """🔴🔴 A — 폼이 **xG 폼**을 섞는다(운 좋게 이긴 팀을 가른다)."""
    from app.core import form
    rows = [{"gf": 1, "ga": 0, "opp": "X"}] * 10
    games = [{"gf": 1, "ga": 0, "xgf": 0.2, "xga": 1.5, "xg_n": 2}] * 10
    lucky = form.form_of("운", rows, elo={}, games=games)
    solid = form.form_of("실속", rows, elo={},
                         games=[{"gf": 1, "ga": 0, "xgf": 1.8, "xga": 0.3,
                                 "xg_n": 2}] * 10)
    assert lucky.index() is not None and solid.index() is not None
    assert lucky.index() < solid.index(), (lucky.index(), solid.index())
    assert "xG" in lucky.why
    #: ⚠️ xG 를 센 골이 모자라면 **안 섞는다**(그 사실을 적는다)
    thin = form.form_of("얇다", rows, elo={},
                        games=[{"gf": 1, "ga": 0, "xgf": 0.1, "xga": 2.0,
                                "xg_n": 0}] * 10)
    assert thin.index() == 1.0 and "안 섞음" in thin.why


# ══════════════════════════════════════════════════════════════════
# B — 축2 상쇄를 고친다(6축 차를 직접)
# ══════════════════════════════════════════════════════════════════

def test_axis2_uses_the_six_axis_gap() -> None:
    """🔴🔴 B — 양 팀이 **같은 규칙에 걸려도** 축2 가 0 이 되지 않는다.

    ⚠️ 실측 2026-10-11(가와사키): `T1 home`·`T1 away`·`T3 home`·`T3 away` 가 다
       터져 **차 0.0** 이었다. 쇼난은 `발동 0건`으로 축2 가 ⬜ 였다. 즉 비중 0.2
       짜리 축이 **거의 늘 죽어 있었다**.
    🔴 스타일 6축의 raw 값은 이미 있다 — 그 **차**를 직접 쓴다.
    """
    from app.core import matchup

    class _S:
        def __init__(self, box):
            self.axis = dict(box)

    #: 🔴 축 이름은 **`style.axes()` 표**가 든다(여섯째는 `setpiece` 다 —
    #   내가 `wide` 로 적어 축2 가 계속 ⬜ 였던 실사고 2026-10-11)
    box = {"style": {"home": _S({"forward": 0.47, "box_entry": 1.64,
                                 "direct": 0.10, "press": 0.04,
                                 "low_block": 0.06, "setpiece": 0.20}),
                     "away": _S({"forward": 0.44, "box_entry": 2.50,
                                 "direct": 0.12, "press": 0.05,
                                 "low_block": 0.07, "setpiece": 0.18})},
           "fired2": [], "fired": [], "off": {}, "late": {}}
    got = matchup.axis2(box, None)
    assert got.gap is not None, got.why
    assert abs(float(got.gap)) > 0.0, (got.gap, got.why)
    assert "6축" in got.why


def test_six_axis_names_come_from_the_table() -> None:
    """🔴 B — 축 이름을 **베껴 적지 않는다**(`style.axes()` 가 원본)."""
    from app.core import matchup, style
    src = _src(matchup._six_gap)
    assert "axes()" in src, "표에서 이름을 안 받는다"
    assert set(matchup.SIX_DEF) <= set(style.axes()), (
        matchup.SIX_DEF, list(style.axes()))


def test_axis2_says_when_style_is_missing() -> None:
    """🔴 #3 — 6축 자료가 없으면 **그 사실을 적는다**(0 으로 메우지 않는다)."""
    from app.core import matchup
    got = matchup.axis2({"style": {}, "fired2": [], "fired": []}, None)
    assert got.gap is None or got.gap == 0.0
    assert "자료" in got.why or "안 센다" in got.why or "6축" in got.why


# ══════════════════════════════════════════════════════════════════
# C — 홈/원정 분리 폼(수축해서 섞는다)
# ══════════════════════════════════════════════════════════════════

def test_side_form_splits_home_and_away() -> None:
    """🔴🔴 C — 홈팀은 **홈 경기**, 원정팀은 **원정 경기** 폼으로 본다."""
    from app.core import form
    games = ([{"gf": 3, "ga": 0, "side": "home"}] * 5
             + [{"gf": 0, "ga": 2, "side": "away"}] * 5)
    at_home = form.side_sums(games, "home")
    at_away = form.side_sums(games, "away")
    assert at_home["n"] == 5 and at_home["gf"] == 15, at_home
    assert at_away["n"] == 5 and at_away["ga"] == 10, at_away


def test_side_form_shrinks_on_small_sample() -> None:
    """🔴 C — 표본이 적으면 **전체 폼으로 수축**한다(그 비율을 적는다)."""
    from app.core import form
    whole, side = 1.0, -1.0
    a = form.shrink(whole=whole, side=side, n=0)
    b = form.shrink(whole=whole, side=side, n=form.SIDE_FULL)
    assert a == whole, a
    assert abs(b - side) < 1e-9, b
    mid = form.shrink(whole=whole, side=side, n=form.SIDE_FULL // 2)
    assert side < mid < whole, mid


def test_form_of_uses_the_side() -> None:
    """🔴 C 배선 — `form_of(side_at=…)` 가 그 쪽 폼을 섞는다."""
    from app.core import form
    rows = [{"gf": 1, "ga": 1, "opp": "X"}] * 10
    games = ([{"gf": 3, "ga": 0, "side": "home"}] * 5
             + [{"gf": 0, "ga": 3, "side": "away"}] * 5)
    at_home = form.form_of("홈", rows, elo={}, games=games, side_at="home")
    at_away = form.form_of("원정", rows, elo={}, games=games, side_at="away")
    assert at_home.index() > at_away.index(), (at_home.index(),
                                               at_away.index())
    assert "홈 경기 폼" in at_home.why or "쪽 폼" in at_home.why


# ══════════════════════════════════════════════════════════════════
# E — 팀별 홈 이점(수축)
# ══════════════════════════════════════════════════════════════════

def test_team_home_edge_from_games() -> None:
    """🔴🔴 E — 그 팀의 **홈/원정 득실**로 홈 효과를 센다(표본 적으면 수축)."""
    from app.core import probmodel
    games = ([{"gf": 3, "ga": 0, "side": "home"}] * 8
             + [{"gf": 1, "ga": 2, "side": "away"}] * 8)
    got, why = probmodel.team_home_mul(games, league=1.1)
    assert got is not None and got > 1.1, (got, why)
    assert "표본" in why
    #: ⚠️ 표본이 없으면 **리그 값을 그대로** 쓴다(지어내지 않는다)
    none, why2 = probmodel.team_home_mul([], league=1.1)
    assert none == 1.1 and "리그" in why2
