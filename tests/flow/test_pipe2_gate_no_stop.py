"""[PIPE-2 2026-09-25] ③은 **사전값 품질 문제로 흐름을 죽이지 않는다.**

사용자 감사 2026-09-25 모순 2:
```
n03_gate.py:40  사전값 없음 → BOARD, stop=True  → 축구 10/23 즉사
n03_gate.py:58  |gap|≥12    → BOARD, stop=True  → 야구 5/17 즉사
사전값 team_elo 에는 **선발이 없다**. 에이스 등판일마다 |gap|≥12 가 난다:
  HOU@ATH +16.1 · 한신 −18.2 · SSG +21.4 · 맨시티 −15.9 · 리즈 +18.4
```

🔴 잠그는 것 넷:
  (a) 사전값만 없으면 `사전값없음`(시장 단독)으로 **진행**한다.
  (b) 괴리가 커도 멈추지 않고 부호대로 라벨을 주며 `prior_suspect` 로 표시한다.
  (c) **둘 다 없을 때만** 보드 고정으로 멈춘다.
  (d) `사전값없음` 에서는 ⑪이 승패 픽을 만들지 않는다.
⚠️ 문턱 `gate_pp.freeze`(12.0)·`gate_pp.agree`(4.0)는 **바꾸지 않았다.**
"""
from __future__ import annotations

import asyncio

from app.flow.ctx import Ctx
from app.flow.labels import (AGREE, BOARD, DOUBT, NO_PRIOR, OVER, PICK_BOARD,
                             PICK_ML, PRIOR_ONLY)
from app.flow.nodes import n03_gate, n11_value
from app.flow.state import State

KBO = {"game_id": "1", "sport": "baseball", "league": "KBO",
       "home": "한화", "away": "삼성", "starts_at": "2026-09-18T09:30:00Z"}


def _s(**kw):
    st = State.new(KBO)
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def _gate(gap_pp=None, *, prior=True, market=True, side="home"):
    p_mkt = 0.55
    pri = {f"p_{side}": (round(p_mkt + gap_pp / 100.0, 4) if prior else None),
           "missing": [] if prior else ["한화", "삼성"]}
    mkt = ({"p": {side: p_mkt}, "market_missing": False} if market
           else {"p": None, "market_missing": True})
    st = _s(hyp_side=side, pick_side=side, n01_prior=pri, n02_market=mkt)
    return asyncio.run(n03_gate.run(st, Ctx())).n03_gate


# ── (a) 사전값만 없음 → 진행 ───────────────────────────────────────

def test_pipe2_no_prior_flows_to_n11():
    g = _gate(prior=False)
    assert g["gate"] == NO_PRIOR and g["stop"] is False, g
    assert g["missing"] == ["한화", "삼성"], g


# ── (b) 큰 괴리 → 멈추지 않고 표시만 ───────────────────────────────

def test_pipe2_big_gap_does_not_stop():
    for gap, want in ((+16.1, DOUBT), (-18.2, OVER), (+21.4, DOUBT)):
        g = _gate(gap)
        assert g["stop"] is False, (gap, g)
        assert g["gate"] == want, (gap, g)
        assert g["prior_suspect"] is True, (gap, g)


def test_pipe2_문턱_아래는_의심표지가_붙지_않는다():
    assert _gate(+0.3)["gate"] == AGREE
    assert _gate(-9.3)["gate"] == OVER
    for gap in (+0.3, -9.3, +4.4):
        assert _gate(gap)["prior_suspect"] is False, gap


def test_pipe2_표지는_스냅샷에_남는다():
    """🔴 `state` 에 새 속성을 달면 `asdict()` 에서 조용히 빠진다.

    `State` 는 dataclass 이고 `to_json` 이 `asdict` 를 쓴다 — 선언되지 않은
    속성은 `analysis_runs` 에 **남지 않는다.** 그래서 ③의 자기 칸에 넣었다.
    """
    st = _s(hyp_side="home", pick_side="home",
            n01_prior={"p_home": 0.71}, n02_market={"p": {"home": 0.55},
                                                    "market_missing": False})
    st = asyncio.run(n03_gate.run(st, Ctx()))
    assert st.n03_gate["prior_suspect"] is True
    assert "prior_suspect" in st.to_json(), "스냅샷에 표지가 없다"


# ── (c) 둘 다 없을 때만 멈춘다 ─────────────────────────────────────

def test_pipe2_사전값이_없어도_시장이_있으면_진행한다_side_없이():
    """🔴 [정정] **`side` 에 매이면 안 된다.**

    사전값이 없으면 ①이 `hyp_side` 를 정하지 않는다. ③이 쪽별로 시장을
    조회하면 그때 `p_mkt` 가 None 이라 "시장도 없다"로 오판한다 — 재생
    실측에서 축구 6경기(사전값 없음·시장 있음)가 그대로 얼었다.
    """
    st = _s(hyp_side=None, pick_side=None,
            n01_prior={"p_home": None, "p_away": None, "missing": ["A", "B"]},
            n02_market={"market_missing": False,
                        "p": {"home": 0.37, "draw": 0.31, "away": 0.32}})
    g = asyncio.run(n03_gate.run(st, Ctx())).n03_gate
    assert g["gate"] == NO_PRIOR and g["stop"] is False, g


def test_pipe2_시장표에_우리쪽_값이_없으면_사전값단독():
    """⚠️ 지어낸 0 으로 gap 을 만들지 않는다."""
    st = _s(hyp_side="home", pick_side="home",
            n01_prior={"p_home": 0.6},
            n02_market={"market_missing": False, "p": {"away": 0.4}})
    g = asyncio.run(n03_gate.run(st, Ctx())).n03_gate
    assert g["gate"] == PRIOR_ONLY and g["stop"] is False, g


def test_pipe2_둘_다_없으면_보드고정():
    g = _gate(prior=False, market=False)
    assert g["gate"] == BOARD and g["stop"] is True, g


def test_pipe2_시장만_없으면_사전값단독():
    g = _gate(+0.0, market=False)
    assert g["gate"] == PRIOR_ONLY and g["stop"] is False, g


# ── (d) 사전값없음에서 승패 픽 금지 ────────────────────────────────

def test_pipe2_사전값없음에서는_승패픽을_만들지_않는다():
    st = _s(pick_side="away", n03_gate={"gate": NO_PRIOR},
            n02_market={"odds": {"away": 1.35}, "derivatives": {}},
            n08_pcode={"p_code_pick": 0.95})
    v = asyncio.run(n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_BOARD, v


def test_pipe2_의심표지가_픽에_실린다():
    st = _s(pick_side="away", n03_gate={"gate": OVER, "prior_suspect": True},
            n02_market={"odds": {"away": 1.35}, "derivatives": {}},
            n08_pcode={"p_code_pick": 0.95})
    v = asyncio.run(n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_ML and v["prior_suspect"] is True, v


def test_pipe2_문턱_숫자를_바꾸지_않았다():
    from app.flow import rules as R

    assert R.get("gate_pp.freeze") == 12.0
    assert R.get("gate_pp.agree") == 4.0
