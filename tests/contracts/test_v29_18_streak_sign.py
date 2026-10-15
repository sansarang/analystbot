"""🔴🔴 **+ − 가 제대로** — 사용자 지적 2026-10-15.

> **무승 4경기인데 왜 이게 삭감이 안 되냐** · + − 가 제대로 되어야 한다

⚠️ 실사고: `IR12` 가 무패·무승을 **한 규칙**으로 묶고 표의 `favors: subject`
   하나를 써서, *"노리치 무승 4경기"* 가 **홈에 유리**(×1.05)로 들어갔다.
🔴 무패·연승 → 그 팀 **유리** · 무승·연패 → 그 팀 **불리**(상대가 유리).
"""
from __future__ import annotations

import yaml

from app.core import probmodel as pm, routing as rt
from app.core.schema import Facts, MatchRef
from app.core.stages import s5_verify as s5
from app.core.state import RunState

REF = MatchRef(id="m1", sport="soccer", home="team:100001", away="team:100002",
               home_name="노리치", away_name="사우샘프턴", competition="ELC",
               competition_short="ELC",
               kickoff_utc="2026-10-15T10:00:00+00:00")


def _row() -> dict:
    box = yaml.safe_load(open("config/interpret_rules.yaml", encoding="utf-8"))
    return next(r for r in box["ir_table"] if r.get("id") == "IR12")


def _vars(home: dict, away: dict) -> dict:
    # ⚠️ 이 규칙은 **양 팀 재료가 다 있을 때** 돈다(`needs` 문) — 한쪽만 주면
    #    목록이 빈다(실측 2026-10-15). 그래서 시험도 둘 다 준다.
    facts = Facts(recent={"team:100001": home, "team:100002": away})
    got = s5._ir_soccer("IR12", _row(), REF, facts, state=RunState())
    return {v.id: v for v in got}


def test_무승은_그_팀을_깎는다() -> None:
    got = _vars({"streak_winless": 4}, {"streak_unbeaten": 5})
    one = got["IR12-home"]
    assert one.favors == "away", (one.favors, one.claim)
    assert "불리" in one.claim, one.claim


def test_무패는_그_팀을_올린다() -> None:
    got = _vars({"streak_winless": 4}, {"streak_unbeaten": 5})
    one = got["IR12-away"]
    assert one.favors == "away", (one.favors, one.claim)
    assert "유리" in one.claim, one.claim


def test_확률에서도_방향이_맞다() -> None:
    """🔴 무승인 팀의 승 확률이 **내려가야** 한다(그게 삭감이다)."""
    got = _vars({"streak_winless": 4}, {"streak_unbeaten": 5})
    one = got["IR12-home"]
    p, said = pm.flat_prob(rt.place([one]), ref=REF)
    assert p["home"] < 1 / 3 < p["away"], (p, said)


def test_둘이_같이_있으면_한쪽으로_몰린다() -> None:
    got = _vars({"streak_winless": 4}, {"streak_unbeaten": 5})
    rows = [got["IR12-home"], got["IR12-away"]]
    p, _ = pm.flat_prob(rt.place(rows), ref=REF)
    assert p["away"] > p["home"], p


def test_표는_그대로다() -> None:
    """🔴 표의 `favors: subject` 는 **무패 기준**이다 — 그 줄에서만 바꿔 넘긴다."""
    assert str(_row().get("favors")) == "subject"


def test_연패_간절함은_여전히_표시_전용이다() -> None:
    """⚠️ 같은 사실의 다른 해석 — 그것은 확률에 닿지 않는다(`mood`)."""
    got = _vars({"streak_winless": 4, "streak_losing": 4},
                {"streak_unbeaten": 5})
    one = got["IR12D-home"]
    assert one.type == "mood", one.type
    p, _ = pm.flat_prob(rt.place([one]), ref=REF)
    assert abs(p["home"] - 1 / 3) < 1e-9, p
