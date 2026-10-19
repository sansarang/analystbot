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



def _seq(*results: str) -> dict:
    """🔴 폼 묶음 대역 — **운영 모양**(`sequence` · 최신이 앞 · 날짜·득실 포함).

    ⚠️ 2026-10-17 부터 `IR12` 는 **직전 경기 하나**로 방향을 정한다
       (*"연승은 표현하지 않는다"* · *"직전 경기에 패했으면 경기력은 더
       안좋아지는거나"*). 그래서 대역도 **경기 줄**을 준다 — 종전처럼
       `{"streak_winless": 4}` 만 주면 운영에 없는 꼴이다(#5).
    """
    rows = []
    for i, r in enumerate(results):
        rows.append({"date": f"2026-10-{20 - i * 3:02d}", "result": r,
                     "goals_for": 2 if r == "W" else (1 if r == "D" else 0),
                     "goals_against": 0 if r == "W" else (1 if r == "D" else 2)})
    #  🔴 **연패 간절함**(`IR12D`)이 보는 칸 — 운영은 같은 수열에서 센다
    n_lose = 0
    for r in results:
        if r != "L":
            break
        n_lose += 1
    return {"sequence": rows, "last5": list(results), "streak_losing": n_lose}


def test_직전_패는_그_팀을_깎는다() -> None:
    #  🔴 홈은 **직전 패**, 원정은 **직전 승**
    got = _vars(_seq("L", "W", "W"), _seq("W", "L", "L"))
    one = got["IR12-home"]
    assert one.favors == "away", (one.favors, one.claim)
    assert "불리" in one.claim and "직전 경기 **패**" in one.claim, one.claim
    #  🔴 **경기마다 한 줄**이 글에 있다(통합하지 않는다)
    assert "최신순" in one.claim and one.claim.count("·") >= 3, one.claim
    #  🔴 **연승이라는 말을 쓰지 않는다**(사용자 지시 2026-10-17)
    assert "연승" not in one.claim and "무패" not in one.claim, one.claim


def test_직전_승은_그_팀을_올린다() -> None:
    got = _vars(_seq("L", "W", "W"), _seq("W", "L", "L"))
    one = got["IR12-away"]
    assert one.favors == "away", (one.favors, one.claim)
    assert "유리" in one.claim and "직전 경기 **승**" in one.claim, one.claim


def test_확률에서도_방향이_맞다() -> None:
    """🔴 직전에 진 팀의 승 확률이 **내려가야** 한다(그게 삭감이다).

    🔴🔴 **집안 하나로 바뀌었다**(사용자 지시 2026-10-18 — *"집안마다 부등호
       하나"*). 양 팀 직전 결과가 다 방향을 가지면 **더 좋았던 쪽**(여기서는
       원정 `W`)만 확률에 닿고, 홈 `L` 변수는 **맥락 전용**으로 내려간다.
    ⚠️ 그래서 이 시험은 **집안을 함께** 넣어 방향을 본다 — 한 줄만 넣고 보면
       대표가 아닌 쪽이라 안 민다(그것이 의도한 동작이다).
    🔴 지키는 뜻은 그대로다 — **직전에 진 팀 쪽으로는 확률이 안 간다**.
    🔴🔴 **뒤집혔다 — 과거 폼은 확률에서 뺐다**(사용자 지시 2026-10-18
       *"과거 경기력 폼 제외...오로지 변수로만"*). `recent_pattern`·
       `form_streak`·`squad_rotation` 은 자리가 `hypo` 고 λ 보정표에도 없다.
    ⚠️ 까닭은 실측이다 — 즈볼러 4-1(우리 원정 40.8%) · 우디네세 0-3(우리 홈 41.8%)
       에서 과거 층이 **결과와 정반대**였다.
    """
    got = _vars(_seq("L", "W", "W"), _seq("W", "L", "L"))
    rows = [got["IR12-home"], got["IR12-away"]]
    p, said = pm.flat_prob(rt.place(rows), ref=REF)
    # 🔴 **확률은 안 움직인다** — 균등 그대로다
    assert abs(p["home"] - 1 / 3) < 1e-9 and abs(p["away"] - 1 / 3) < 1e-9, p
    assert "맥락 전용" in said, said
    # 🔴 그래도 **글자(부호)는 사실대로** 선다 — 카드·⑯ 이 읽는다
    assert got["IR12-home"].favors == "away", got["IR12-home"].claim
    assert "집안 하나" in got["IR12-home"].claim, got["IR12-home"].claim


def test_둘이_같이_있어도_확률은_안_움직인다() -> None:
    """🔴 위 머리말과 같다 — 과거 폼은 2026-10-18 에 확률에서 뺐다."""
    got = _vars(_seq("L", "W", "W"), _seq("W", "L", "L"))
    rows = [got["IR12-home"], got["IR12-away"]]
    p, _ = pm.flat_prob(rt.place(rows), ref=REF)
    assert abs(p["away"] - 1 / 3) < 1e-9, p


def test_표는_그대로다() -> None:
    """🔴 표의 `favors: subject` 는 **직전 승 기준**이다 — 그 줄에서만 바꿔 넘긴다."""
    assert str(_row().get("favors")) == "subject"


def test_연패_간절함은_여전히_표시_전용이다() -> None:
    """⚠️ 같은 사실의 다른 해석 — 그것은 확률에 닿지 않는다(`mood`)."""
    #  🔴 홈이 **4연패** — 대역도 운영 모양(경기 줄)으로 준다(#5)
    got = _vars(_seq("L", "L", "L", "L"), _seq("W", "L", "L"))
    one = got["IR12D-home"]
    assert one.type == "mood", one.type
    p, _ = pm.flat_prob(rt.place([one]), ref=REF)
    assert abs(p["home"] - 1 / 3) < 1e-9, p
