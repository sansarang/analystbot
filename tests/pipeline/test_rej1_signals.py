"""[REJ-1] ⑩ 재판정 신호가 **주입된 적이 없다.**

🔴 실측: `analysis_runs` 에 `n10_rejudge` 행 **0건**(Phase 0 D-7).
   `n10.run` 은 `ctx.inject["rejudge_signals"]` 를 읽는데
   `bridge` 는 `model_probs` 하나만 주입한다 — 신호는 영원히 빈 dict 였다.

🔴 재료는 판정 캐시에 있다(실측):
     10086 lineup_just_confirmed = True   (= confirmed 이고 확정 1시간 이내)
     lineup_notes 에 "선발 변경: A → B" 줄이 들어온다(`lineups.py`)

⚠️ `pipeline.starter_changed` 는 **이름과 뜻이 다르다** —
     "starter_changed": bool(g.get("lineup_status") == "conflict")
   그건 *소스 불일치*이지 선발 교체가 아니다. n10 머리말은 트리거가
   "`starter_change_notes` 가 낸 줄"이라고 적고 있다 → 그 줄을 쓴다.
   저 칸은 `deep.needs_refresh` 가 쓰고 있어 건드리지 않는다(→ 3-5-b).

⚠️ ⑩은 ⑥ 통과 뒤에 있다. 신호를 이어도 ⑥이 `모름과반`이면 여전히 0건이다 —
   그 사실을 숨기지 않는다.
"""
from __future__ import annotations

import pytest


def test_신호를_캐시에서_뽑는다():
    from app.flow.bridge import rejudge_signals_of

    cg = {"lineup_just_confirmed": True, "lineup_notes": []}
    assert rejudge_signals_of(cg) == {"lineup_confirmed": True,
                                      "starter_changed": False}


def test_선발변경은_메모_줄로_본다():
    """🔴 `lineup_status=='conflict'` 를 선발 교체로 읽지 않는다."""
    from app.flow.bridge import rejudge_signals_of

    cg = {"lineup_status": "conflict", "lineup_notes": []}
    assert rejudge_signals_of(cg)["starter_changed"] is False

    cg2 = {"lineup_notes": ["home 선발 변경: 류현진 → 김광현"]}
    assert rejudge_signals_of(cg2)["starter_changed"] is True


def test_캐시가_없으면_빈_신호다():
    from app.flow.bridge import rejudge_signals_of

    assert rejudge_signals_of(None) == {"lineup_confirmed": False,
                                        "starter_changed": False}


@pytest.mark.asyncio
async def test_창_밖이면_발동하지_않는다():
    """⚠️ 킥오프 −90 ~ −20분만. 그 밖은 신호가 있어도 안 쏜다."""
    from datetime import UTC, datetime, timedelta

    from app.flow.ctx import Ctx
    from app.flow.nodes import n10_rejudge as N
    from app.flow.state import State

    now = datetime(2026, 9, 19, 5, 0, tzinfo=UTC)
    ko_far = (now + timedelta(minutes=200)).isoformat().replace("+00:00", "Z")
    st = State(run_id="r", game_id="1", sport="baseball", league="MLB",
               home="H", away="A", kickoff_utc=ko_far)
    ctx = Ctx(now_kst=now, inject={"rejudge_signals": {"lineup_confirmed": True}})
    out = await N.run(st, ctx)
    assert out.n10_rejudge["triggered"] is False
    assert out.n10_rejudge["in_window"] is False


@pytest.mark.asyncio
async def test_창_안이면_발동한다():
    from datetime import UTC, datetime, timedelta

    from app.flow.ctx import Ctx
    from app.flow.nodes import n10_rejudge as N
    from app.flow.state import State

    now = datetime(2026, 9, 19, 5, 0, tzinfo=UTC)
    ko = (now + timedelta(minutes=45)).isoformat().replace("+00:00", "Z")
    st = State(run_id="r", game_id="1", sport="baseball", league="MLB",
               home="H", away="A", kickoff_utc=ko)
    ctx = Ctx(now_kst=now, inject={"rejudge_signals": {"lineup_confirmed": True}})
    out = await N.run(st, ctx)
    assert out.n10_rejudge["triggered"] is True
    assert out.n10_rejudge["trigger"] == "lineup_confirmed"
