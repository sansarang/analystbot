"""[CNF-2 2026-09-20] ⑥의 **반증이 구조적으로 불가능**했다.

🔴 실측 2026-09-20: 운영 최근 2시간 변수 채점 `{'unknown': 496, 'confirmed': 137}`
   — `refuted` **0건**. ⑤가 값이 없는 변수는 행 자체를 만들지 않으므로
   ⑥의 `_judge` 가 빈 값을 볼 일이 없었다.

🔴 그리고 반증의 **뜻이 가설마다 다르다**(딥서치 2026-09-20 → FORKS F-19):
   "absence of evidence is evidence of absence **to the degree that evidence
   would have been expected had the claim been true**" — 탐지 가능성이 관건이다.

     H_fade (시장과대)  "시장 반대편을 세울 근거"   → 없으면 **픽 철회**
     H_break(가치의심)  "우리 픽을 무너뜨릴 근거"   → 없으면 **픽 강화**

   종전 ⑥은 게이트와 무관하게 앞쪽 하나만 적용했다. 그대로 반증을 켜면
   결장 0명인 건강한 라인업이 **전부 철회**된다.
"""
from __future__ import annotations

import pytest

from app.flow.labels import REFUTED, V_OK, V_REFUTED


def _state(*, hyp_id, vars_, evidence):
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "KBO",
                    "home": "한화", "away": "삼성"})
    st.pick_side = "away"
    st.n04_hyp = [{"id": hyp_id, "vars": vars_}]
    st.n05_evidence = evidence
    return st


@pytest.mark.asyncio
async def test_가설이_무너뜨릴_근거면_반증은_철회가_아니다():
    """🔴 H_break — 무너뜨릴 근거가 없다는 것은 **픽이 단단하다**는 뜻이다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n06_verdict

    st = _state(hyp_id="H_break",
                vars_=[{"var": "lineup_out", "is_core": True}],
                evidence=[{"var": "lineup_out", "value": [],
                           "raw_excerpt": "확정 타순 · 평소 주전 제외 0명"}])
    st = await n06_verdict.run(st, Ctx())
    assert st.n06_verdict["per_var"]["lineup_out"] == REFUTED, st.n06_verdict
    assert st.n06_verdict["verdict"] == V_OK, st.n06_verdict
    assert st.n06_verdict.get("refuted_means") == "강화", st.n06_verdict


@pytest.mark.asyncio
async def test_가설이_반대편을_세울_근거면_반증은_철회다():
    """🔴 H_fade — 반대편을 세울 근거가 없으면 시장이 맞다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n06_verdict

    st = _state(hyp_id="H_fade",
                vars_=[{"var": "lineup_out", "is_core": True}],
                evidence=[{"var": "lineup_out", "value": [],
                           "raw_excerpt": "확정 타순 · 평소 주전 제외 0명"}])
    st = await n06_verdict.run(st, Ctx())
    assert st.n06_verdict["verdict"] == V_REFUTED, st.n06_verdict
    assert st.n06_verdict.get("refuted_means") == "철회", st.n06_verdict


@pytest.mark.asyncio
async def test_결장_수집이_돌았는데_0명이면_빈_값_행을_남긴다():
    """🔴 ⑤가 "찾아봤는데 없다"를 남겨야 ⑥이 반증을 낼 수 있다.

    ⚠️ 결장 수집이 **아예 안 돌았으면** 남기지 않는다 — 그건 모름이다.
    """
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence

    st = _state(hyp_id="H_break",
                vars_=[{"var": "lineup_out", "is_core": True}],
                evidence=[])
    # 결장 수집은 돌았다(문장 2건) — 그런데 이 경기 두 팀 몫은 0명이다.
    ctx = Ctx(inject={"extract": {}, "absences": ["엉뚱한팀 A 오늘 라인업에서 빠짐"]})
    st = await n05_evidence.run(st, ctx)
    row = next((e for e in st.n05_evidence if e["var"] == "lineup_out"), None)
    assert row is not None, st.n05_evidence
    assert row["value"] == [], row
    assert "0명" in str(row.get("raw_excerpt")), row


@pytest.mark.asyncio
async def test_수집이_안_돌았으면_행을_남기지_않는다():
    """⚠️ 반대 위험 — 모름을 반증으로 둔갑시키지 않는다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence

    st = _state(hyp_id="H_break",
                vars_=[{"var": "lineup_out", "is_core": True}],
                evidence=[])
    ctx = Ctx(inject={"extract": {}, "absences": []})
    st = await n05_evidence.run(st, ctx)
    assert not [e for e in st.n05_evidence if e["var"] == "lineup_out"], st.n05_evidence
