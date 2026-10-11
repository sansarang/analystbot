"""🔴🔴 **조건부 가설** — 사용자 지시 2026-10-11(측정 불가를 조건으로).

> 데이터만으로 예측 불가능한 영역 … 1번부터 해라
>   = ③ **조건부 시나리오를 더 쓴다** — 측정 불가 요인(동기·피로·결장 다수)을
>     **숫자로 바꾸지 말고** 가설의 **조건**으로 넣는다.

⚠️ 실측 2026-10-11(쇼난): `⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가
   0개다` → 시나리오 일곱 줄이 전부 `🔴 지지된 가설이 없다(무게만 있다)` 였다.
   🔴 그래서 **코드가 조건부 가설을 짓는다** — 변수만 보고(시뮬은 안 본다 · C3)
   각 줄에 **검증 가능한 신호**를 단다.
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


def _var(vid: str, kind: str, key: str, claim: str):
    from app.core.schema import Variable
    return Variable(id=vid, type=kind, subject=key, favors="home",
                    hardness="soft", weight=0.7, usable_as_basis=True,
                    claim=claim, quote=claim, from_rule=vid)


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="m", sport="soccer", competition="J. League 2",
                    competition_short="J2", home="team:000001",
                    away="team:000002", home_name="Shonan Bellmare",
                    away_name="Albirex Niigata",
                    kickoff_utc="2026-10-11T09:00:00Z")


def test_cond_hypo_from_losing_streak() -> None:
    """🔴 연패(간절함)는 **조건**으로 들어간다 — 신호가 붙는다."""
    from app.core import condhypo
    got = condhypo.lines(_ref(), [
        _var("IR12D-home", "stakes", "team:000001",
             "Shonan Bellmare **3연패** — 승리에 더 간절하다")])
    assert got, got
    one = got[0]
    assert one.team in ("home", "away")
    rows = [*one.reasons, *one.breaks]
    assert rows and all(x.signal is not None for x in rows), rows
    assert any("먼저" in x.text for x in rows), [x.text for x in rows]
    assert all(x.var_ids for x in rows), rows


def test_cond_hypo_from_fatigue() -> None:
    """🔴 일정 과부하는 **후반 구간**을 조건으로 본다."""
    from app.core import condhypo
    got = condhypo.lines(_ref(), [
        _var("IR11-home", "fatigue", "team:000001",
             "Shonan Bellmare 일정 과부하 — 8일 안에 3번째")])
    rows = [x for one in got for x in (*one.reasons, *one.breaks)]
    assert rows, got
    assert any(str(x.signal.metric) == "구간득점" for x in rows), rows


def test_cond_hypo_never_reads_the_sim() -> None:
    """🔴🔴 C3 — 조건부 가설은 **시뮬을 보지 않는다**(변수만 본다)."""
    from app.core import condhypo
    src = inspect.getsource(condhypo)
    for bad in ("sim", "시뮬 값", "probs", "our_prob"):
        assert f"{bad}=" not in src and f"{bad})" not in src, bad


def test_cond_hypo_signals_are_in_the_menu() -> None:
    """🔴 신호는 **허용 목록**(`signals.METRICS`) 안에서만 쓴다."""
    from app.core import condhypo, signals
    got = condhypo.lines(_ref(), [
        _var("IR12D-home", "stakes", "team:000001", "3연패"),
        _var("IR11-away", "fatigue", "team:000002", "일정 과부하")])
    for one in got:
        for x in (*one.reasons, *one.breaks):
            assert signals.known(x.signal.metric), x.signal
            assert not signals.bad_signal(x.signal), (x.signal,
                                                      signals.bad_signal(x.signal))


def test_s6_uses_them_when_the_model_gives_none() -> None:
    """🔴🔴 배선 — 모델이 0줄이면 **코드 조건부 가설**로 메운다(빈 칸 금지)."""
    from app.core.stages import s6_hypo
    src = _src(s6_hypo.claims)
    assert "condhypo" in src
    assert "조건부" in src
