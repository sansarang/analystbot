"""[PIPE-1 2026-09-25] **픽은 게이트가 아니라 edge 가 가른다.**

사용자 감사 2026-09-25 모순 1:
```
n04_hyp.py:181   hyp["market"] = "total" if gate == AGREE else None
n11_value.py     if gate == AGREE and ml_edge >= edge_min:
→ 동의        p_code≈p_market 이라 edge < 2%p → 승패 불가
  시장과대·가치의심  마켓 미지정 → 구조 불가
  **어느 게이트에서도 픽이 나올 수 없다.** 실측 야구 17경기 전건 보드.
```
이 조건은 R1(시장 역행 금지) 시절 것이고 09-20 사용자 결정으로 폐지됐다.

🔴 잠그는 것 넷:
  (a) `동의` 밖에서도 승패 픽이 난다 — 단 `stance` 로 자세를 적는다.
  (b) `보드고정` 은 그대로 막는다.
  (c) `사전값단독`(시장 없음)은 파생 가격이 없으므로 마켓을 지정하지 않는다(F-17).
  (d) **문턱과 방향 검사는 그대로다** — 열린 것은 게이트뿐이다.
"""
from __future__ import annotations

import asyncio

from app.flow.ctx import Ctx
from app.flow.labels import (AGREE, BOARD, DOUBT, OVER, PICK_BOARD, PICK_ML,
                             PRIOR_ONLY)
from app.flow.nodes import n04_hyp, n11_value
from app.flow.state import State

KBO = {"game_id": "1", "sport": "baseball", "league": "KBO",
       "home": "한화", "away": "삼성", "starts_at": "2026-09-18T09:30:00Z"}


def _s(**kw):
    st = State.new(KBO)
    for k, v in kw.items():
        setattr(st, k, v)
    if "hyp_side" not in kw and "pick_side" in kw:
        st.hyp_side = kw["pick_side"]
    return st


def _value(gate, p_code, odds=1.35, side="away"):
    st = _s(pick_side=side, n03_gate={"gate": gate},
            n02_market={"odds": {side: odds}, "derivatives": {}},
            n08_pcode={"p_code_pick": p_code})
    return asyncio.run(n11_value.run(st, Ctx())).n11_value


# ── (a) 동의 밖에서도 픽이 난다 ─────────────────────────────────────

def test_pipe1_pick_allowed_outside_agree():
    """필요확률 1/1.35 = 0.7407. p_code 0.95 면 edge +20.9%p."""
    for gate, want in ((OVER, "contrarian"), (DOUBT, "contrarian"),
                       (AGREE, "agree"), (PRIOR_ONLY, "agree")):
        v = _value(gate, 0.95)
        assert v["pick_type"] == PICK_ML, (gate, v)
        assert v["stance"] == want, (gate, v)


# ── (b) 보드고정은 그대로 막힌다 ───────────────────────────────────

def test_pipe1_보드고정은_여전히_막힌다():
    v = _value(BOARD, 0.95)
    assert v["pick_type"] == PICK_BOARD, v
    assert "stance" not in v, v


# ── (c) F-17 — 시장이 없으면 걸 대상도 없다 ────────────────────────

def test_pipe1_사전값단독은_마켓을_지정하지_않는다():
    for gate, want in ((OVER, "total"), (DOUBT, "total"), (AGREE, "total"),
                       (PRIOR_ONLY, None), (BOARD, None)):
        st = _s(pick_side="away", n03_gate={"gate": gate})
        h = asyncio.run(n04_hyp.run(st, Ctx())).n04_hyp[0]
        assert h["market"] == want, (gate, h)


# ── (d) 문턱·방향 검사는 그대로다 ──────────────────────────────────

def test_pipe1_문턱_미달은_여전히_보드다():
    """1/1.35 = 0.7407 · p_code 0.75 → edge +0.93%p < 2.0 → 보드."""
    v = _value(OVER, 0.75)
    assert v["pick_type"] == PICK_BOARD, v
    assert v["ml_edge_pp"] is not None and v["ml_edge_pp"] < 2.0, v


def test_pipe1_픽_반대_방향_증거는_여전히_철회한다():
    """🔴 게이트를 열었다고 방향 검사까지 푼 것은 아니다."""
    st = _s(pick_side="away", n03_gate={"gate": OVER},
            n02_market={"odds": {"away": 1.35}, "derivatives": {}},
            n08_pcode={"p_code_pick": 0.95},
            n05_evidence=[{"var": "starter_recent3",
                           "direction": {"home": 1, "away": -1}}])
    v = asyncio.run(n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_BOARD, v
    assert "방향 증거" in (v.get("reject_reason") or ""), v


def test_pipe1_문턱_숫자를_바꾸지_않았다():
    from app.flow import rules as R

    assert R.get("edge_min_pp") == 2.0
    assert R.get("gate_pp.agree") == 4.0
    assert R.get("gate_pp.freeze") == 12.0
