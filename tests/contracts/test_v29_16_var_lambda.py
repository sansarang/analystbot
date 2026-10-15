"""🔴🔴 **폼·결장·전략 변수를 λ 에 잇는다** — 사용자 지시 2026-10-15.

> 폼·결장·전략 변수 **연결해라**

⚠️ 상성을 삭제해 축 통로가 사라졌다 — 변수가 확률에 닿는 길은 **여기뿐**이다.
🔴 크기는 **새 수가 아니다** — 이동·피로·순위 동기에 사용자가 정한 ±5% 다.
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


def _box() -> dict:
    return dict(rt.table().get("lambda_rules") or {}).get("by_var") or {}


def test_설정에_칸이_있다() -> None:
    by = _box()
    assert by, "🔴 `lambda_rules.by_var` 가 없다"
    assert float(dict(by["goals"])["up"]) == 1.05
    assert float(dict(by["goals"])["down"]) == 0.95
    assert float(dict(by["favors"])["mul"]) == 1.05


def test_폼이_λ_를_움직인다() -> None:
    """② 흐름 — `S01` 의 `goals` 칸(득점 많다/적다)."""
    got, said = pm.lambda_rules(rt.place([
        V("S01-home", "recent_pattern", goals="down"),
        V("S01-away", "recent_pattern", subject="team:100002", goals="up")]),
        ref=REF)
    assert got["home"] == 0.95 and got["away"] == 1.05, got
    assert "S01-home" in said and "goals down" in said, said


def test_결장이_λ_를_움직인다() -> None:
    """① 전력 — 결장은 `favors`(유리한 쪽)로 건다."""
    got, said = pm.lambda_rules(rt.place([
        V("IR02-home", "def_absence", favors="away")]), ref=REF)
    assert got["away"] == 1.05 and got["home"] == 1.0, got
    assert "favors" in said


def test_전략_변수가_λ_를_움직인다() -> None:
    """③ 전술 — 부등호가 만든 `goals`·`favors` 둘 다 통로가 있다."""
    got, _ = pm.lambda_rules(rt.place([
        V("SL1", "lineup_intent", favors="home", goals="up")]), ref=REF)
    assert got["home"] == 1.05, got


def test_한_변수를_두_번_세지_않는다() -> None:
    """🔴 `goals` 가 말한 변수를 `favors` 로 **또** 세면 이중 계산이다."""
    got, said = pm.lambda_rules(rt.place([
        V("SL1", "lineup_intent", favors="home", goals="up")]), ref=REF)
    assert got["home"] == 1.05, (got, said)
    assert said.count("SL1") == 1, said


def test_방향_없는_변수는_안_센다() -> None:
    got, said = pm.lambda_rules(rt.place([
        V("SL9", "lineup_intent", favors="both", goals="none")]), ref=REF)
    assert got == {"home": 1.0, "away": 1.0} and said == "", (got, said)


def test_표시_전용_집안은_안_센다() -> None:
    """🔴 ⑥ 표시 전용(`mood`·`stakes`)은 확률에 닿지 않는다."""
    got, _ = pm.lambda_rules(rt.place([
        V("IR12D-home", "mood", favors="home")]), ref=REF)
    assert got == {"home": 1.0, "away": 1.0}, got


def test_겹치면_상한이_막는다() -> None:
    """⚠️ 변수가 많으면 곱이 폭주한다 — `cap_mul`·`floor_mul` 이 막는다."""
    box = dict(rt.table().get("lambda_rules") or {})
    cap, floor = float(box.get("cap_mul") or 0), float(box.get("floor_mul") or 0)
    assert cap > 1 and 0 < floor < 1, (cap, floor)
    many = [V(f"S0{i}", "recent_pattern", goals="up") for i in range(1, 9)]
    got, said = pm.lambda_rules(rt.place(many), ref=REF)
    assert got["home"] == cap, (got, said)
    assert "상한에 걸렸다" in said, said


def test_크기를_새로_짓지_않았다() -> None:
    """🔴 ±5% 는 이동·피로·순위 동기에 사용자가 정한 **그 수**다."""
    box = dict(rt.table().get("lambda_rules") or {})
    assert float(dict(box["travel_away"])["mul"]) == 0.95
    assert float(dict(_box()["goals"])["down"]) == 0.95
