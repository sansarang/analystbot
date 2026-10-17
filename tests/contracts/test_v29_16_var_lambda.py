"""🔴🔴 **폼·결장·전략 변수가 확률에 닿는다** — 사용자 지시 2026-10-15.

> 폼·결장·전략 변수 **연결해라** → *"변수 넣기전 초기 확률 33.3 프로로 동등하게
> 해라 … 그외에는 아무 의미 없다"*

⚠️ 처음엔 λ 에 걸었다 — **총골이 부풀었다**(합 2.69 → 3.32 · 오버2.5 50.5% →
   64.7%). 변수는 *"누가 유리한가"* 를 말한 것이지 총골이 아니다.
🔴 그래서 변수는 **승무패**(`flat_prob`)로만 간다. λ 규칙에 남은 것은 사용자가
   전에 정한 셋(이동·피로·순위 동기)뿐이다.
"""
from __future__ import annotations

from app.core import probmodel as pm, routing as rt
from app.core.schema import MatchRef, Variable

REF = MatchRef(id="m1", sport="soccer", home="team:100001", away="team:100002",
               home_name="홈팀", away_name="원정팀", competition="ELC",
               competition_short="ELC",
               kickoff_utc="2026-10-15T10:00:00+00:00")


def V(vid: str, kind: str, *, subject: str = "team:100001",
      favors: str = "both", goals: str = "none") -> Variable:
    return Variable(id=vid, type=kind, subject=subject, favors=favors,
                    goals=goals, target=vid, hardness="soft", weight=0.7,
                    claim="x", quote="x", doc_ids=[], from_rule=vid,
                    usable_as_basis=True)


def _by() -> dict:
    return dict(rt.table().get("lambda_rules") or {}).get("by_var") or {}


def test_설정에_칸이_있다() -> None:
    by = _by()
    assert by, "🔴 `lambda_rules.by_var` 가 없다"
    assert float(dict(by["goals"])["up"]) == 1.05
    assert float(dict(by["goals"])["down"]) == 0.95
    assert float(dict(by["favors"])["mul"]) == 1.05


def test_폼이_확률을_움직인다() -> None:
    got, said = pm.flat_prob(rt.place([
        V("S01-home", "recent_pattern", goals="down"),
        V("S01-away", "recent_pattern", subject="team:100002", goals="up")]),
        ref=REF)
    assert got["away"] > got["home"], got
    assert "S01-home" in said, said


def test_결장이_확률을_움직인다() -> None:
    got, said = pm.flat_prob(rt.place([
        V("IR02-home", "def_absence", favors="away")]), ref=REF)
    assert got["away"] > got["home"], got
    assert "favors" in said


def test_전략_변수가_확률을_움직인다() -> None:
    got, _ = pm.flat_prob(rt.place([
        V("SL1", "lineup_intent", favors="home", goals="up")]), ref=REF)
    assert got["home"] > got["away"], got


def test_한_변수를_두_번_세지_않는다() -> None:
    """🔴 `favors` 와 `goals` 를 둘 다 가진 변수를 두 번 세면 이중 계산이다."""
    _got, said = pm.flat_prob(rt.place([
        V("SL1", "lineup_intent", favors="home", goals="up")]), ref=REF)
    assert said.count("[SL1]") == 1, said


def test_표시_전용_집안은_안_센다() -> None:
    got, _ = pm.flat_prob(rt.place([
        V("IR12D-home", "mood", favors="home")]), ref=REF)
    assert abs(got["home"] - 1 / 3) < 1e-9, got


# 🔴 **`test_λ_규칙에는_사용자가_정한_셋만_남았다` 을 지웠다** — `probmodel.lambda_rules`(λ 배율)를 지웠다 — 기대 득점을 지우자 부르는 곳이 없어졌다(사용자 지시 2026-10-17).

# 🔴 **`test_변수가_λ_를_안_부풀린다` 을 지웠다** — 같은 까닭 — λ 가 없으니 부풀릴 것도 없다.

def test_크기를_새로_짓지_않았다() -> None:
    assert float(dict(_by()["goals"])["down"]) == 0.95
