"""🔴🔴 **v5 §5-4 — 에이전트 변수 → 판정층 변수.** 방향은 **코드가 다시 정한다**.

§5-4 원문:

> 에이전트의 `direction_hint` 는 **참고다.** 코드가 `catalog.yaml` 의 방향
> 규칙으로 **다시 정한다.** 결장은 명단 포지션으로 def/att 를 가르고, 양방향
> 유형(`coach_crisis`, `event_match`, `lineup_rotation`)은 **두 항목으로
> 나눈다**. 홈/원정 기록은 오늘 경기의 홈/원정에 맞는 것만 쓴다(원정 기록을
> 홈팀 변수로 쓰면 `side_mismatch`). [#21]

══════════════════════════════════════════════════════════════════
🔴 왜 다리가 필요한가 — 두 경로가 **다른 꼴**을 낸다
══════════════════════════════════════════════════════════════════

    규칙 경로   `classify.Classified`  → 판정층(§6)
    에이전트     `agentschema.AgentVar` → ???

⚠️ §1 은 *"검증층을 통과한 변수만 변수"* 라고 했다 — 그러면 그 변수가 **판정층에
   닿아야** 한다. 🔴 닿지 않으면 에이전트는 토큰만 쓰고 카드를 안 바꾼다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime.now(timezone.utc) + timedelta(hours=2)


def _game():
    from app import classify
    return classify.Game(home="Milwaukee Brewers", away="San Diego Padres",
                         sport="baseball", league="MLB",
                         home_id="team:000338", away_id="team:000325")


def _var(**kw):
    from app import agentschema
    base = {
        "id": "A1", "type": "pitcher_state", "team": "team:000338",
        "claim": "선발이 좋다", "quote": "Henderson will start",
        "url": "https://www.mlb.com/x",
        "published_at": KICK - timedelta(hours=20),
        "direction_hint": "home", "lang": "en",
    }
    base.update(kw)
    return agentschema.AgentVar(**base)


def test_v5_5_4_다리가_있다():
    """🔴 에이전트 변수가 **판정층 꼴**로 바뀌어야 한다(§1)."""
    from app import classify
    got = classify.from_agent_var(_var(), _game())
    assert isinstance(got, classify.Classified), type(got)
    assert got.type == "pitcher_state"
    assert got.source_url == "https://www.mlb.com/x"
    assert got.is_variable is True, got


def test_v5_5_4_방향을_힌트로_정하지_않는다():
    """🔴🔴 *"`direction_hint` 는 **참고다**"* — **팀 열쇠**가 쪽을 정한다.

    ⚠️ 모델이 `away` 라고 적어도 그 변수의 팀이 **홈**이면 홈이다. 🔴 힌트를
       그대로 쓰면 그것이 `side_mismatch` 의 입구다(§5-4 · M36).
    """
    from app import classify
    g = _game()
    got = classify.from_agent_var(_var(direction_hint="away"), g)
    # 🔴 팀 열쇠가 **홈**이다 — 힌트가 `away` 라도 홈이다
    assert got.direction == "home", got
    got2 = classify.from_agent_var(
        _var(team="team:000325", direction_hint="home"), g)
    assert got2.direction == "away", got2


def test_v5_5_4_남의_팀이면_side_mismatch():
    """🔴 *"원정 기록을 홈팀 변수로 쓰면 `side_mismatch`"*(§5-4 · M36).

    ⚠️ 이 경기 팀이 **아닌** 열쇠면 변수가 못 된다 — 그 사실을 `undecided` 가
       말한다(조용히 버리지 않는다 · #3).
    """
    from app import classify
    got = classify.from_agent_var(_var(team="team:999999"), _game())
    assert got.is_variable is False, got
    assert "side_mismatch" in str(got.undecided), got.undecided


@pytest.mark.parametrize("vtype", ["coach_conflict", "event_match",
                                   "squad_rotation"])
def test_v5_5_4_양방향_유형은_둘로_나눈다(vtype):
    """🔴🔴 *"양방향 유형은 **두 항목으로 나눈다**"*(§5-4).

    ⚠️ 지시문은 `coach_crisis`·`event_match`·`lineup_rotation` 이라 적었다 —
       §4 의 우리 이름은 `coach_conflict`·`event_match`·`squad_rotation` 이다
       (`trigger_conditions.yaml` 의 `v5_names` 가 그 대응을 든다).
    🔴 한 쪽에만 붙이면 그것이 **한 방향 근거**가 된다(§6-2 ⑥ 과 같은 까닭).
    """
    from app import classify
    rows = classify.from_agent_vars([_var(type=vtype)], _game())
    assert len(rows) == 2, [r.direction for r in rows]
    assert {r.direction for r in rows} == {"home", "away"}, rows
    # 🔴 **같은 사실**이 두 쪽에 선다(지어낸 것이 아니다)
    assert len({r.text for r in rows}) == 1, rows


def test_v5_5_4_한방향_유형은_하나다():
    """⚠️ 반대 증거 — 양방향이 아닌 유형을 둘로 나누지 않는다."""
    from app import classify
    rows = classify.from_agent_vars([_var(type="pitcher_state")], _game())
    assert len(rows) == 1, rows


def test_v5_5_4_등급이_무게를_준다():
    """🔴 §5-5 — 출처 등급이 `hardness` 를 정한다. ⚠️ 모델이 정하지 않는다."""
    from app import classify
    hard = classify.from_agent_var(_var(url="https://www.mlb.com/x"), _game())
    soft = classify.from_agent_var(
        _var(url="https://www.reddit.com/r/brewers/x"), _game())
    assert hard.hardness == "hard", hard
    assert soft.hardness == "soft", soft
    # 🔴 **재검증 안 한 변수는 한 단계 아래**(M31 · §5-8)
    down = classify.from_agent_var(_var(reverified=False), _game())
    assert down.hardness == "soft", down


def test_v5_5_4_LLM_이_무게에_닿지_않는다():
    """🔴🔴 절대규칙 5 — *"`direction`·`weight`·`strength` 에 LLM 출력이 닿으면
    계약 실패."*

    ⚠️ 다리가 모델 글을 그 칸에 넣으면 그 규칙이 깨진다. 🔴 모델이 주는 것은
       **사실과 인용**이고, 방향·무게는 **코드가** 준다.
    """
    import ast
    import inspect
    import textwrap

    from app import classify
    src = textwrap.dedent(inspect.getsource(classify.from_agent_var))
    tree = ast.parse(src)
    # 🔴 `direction=` 에 `direction_hint` 가 **직접** 들어가지 않는다
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg != "direction":
            continue
        said = ast.dump(node.value)
        assert "direction_hint" not in said, (
            "🔴 §5-4 — `direction` 에 모델 힌트가 그대로 들어간다")


def test_v5_5_4_배선_에이전트_변수가_카드에_닿는다():
    """🔴🔴 **§1** — 검증층을 지난 변수가 **판정층에 닿아야** 한다(#2).

    ⚠️ 안 닿으면 에이전트는 토큰만 쓰고 카드를 안 바꾼다.
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    src = textwrap.dedent(inspect.getsource(analyze))
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") in ("from_agent_vars",
                                                 "from_agent_var")]
    assert calls, (
        "🔴 에이전트 변수를 **판정층 꼴로 바꾸는 곳이 없다** — 그 변수는 "
        "카드에 닿지 않는다(§1 · CLAUDE.md #2)")
