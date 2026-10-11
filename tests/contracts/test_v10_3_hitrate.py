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
    """🔴 A — 경기 목록 한 줄이 **xG 합**을 들고 온다(골 줄에 이미 있다)."""
    from app.core.stages import s2e_matchup
    rows = [{"home_name": "A", "away_name": "B", "mine_home": True,
             "utc": "2026-09-01T00:00:00Z", "league": "L", "starters": [],
             "goals": [{"home": True, "xg": 0.8}, {"home": False, "xg": 0.3}],
             "stats": {}}]
    got = s2e_matchup.games_of(rows)[0]
    assert abs(float(got["xgf"]) - 0.8) < 1e-9, got
    assert abs(float(got["xga"]) - 0.3) < 1e-9, got


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
