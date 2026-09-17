"""MKT-4 계약 — **요구 확률(1/배당)** 로 "값이 있나"를 가른다.

🔴 목표 분석(2026-09-17): "마진 제거 시 KIA 62.3% — 내 판정 63%와 0.7%p 차로
   완전 동의입니다. **문제는 가격: KIA 1.49는 요구 확률 67.1%라 내 63%로는
   값이 없고**"
   디빅 62.3% → **방향** · 요구 67.1% → **값**. 우리는 앞만 있었다.
⚠️ 게이트·추천을 안 바꾼다 — 이 단위는 **숫자를 만들어 보여줄 뿐**이다.
"""
import inspect

import pytest

from app.engine import analyze as AN
from app.engine import market_edge as ME

BLK = {"home": "KIA", "away": "키움", "league": "KBO", "p_market": 0.623,
       "gap_pp": 0.7, "gate": "동의", "adj_pp": {}, "p_code": 0.63,
       "kickoff_kst": "x", "home_facts": {}, "away_facts": {}}


def test_목표분석_숫자를_재현한다():
    """🔴 1.49 → 67.1% · 우리 63% → −4.1%p (값 없음)."""
    assert ME.break_even(1.49) == pytest.approx(0.6711, abs=1e-4)
    assert ME.price_edge_pp(0.63, 1.49) == pytest.approx(-4.1, abs=0.05)


def test_값이_있으면_양수다():
    assert ME.price_edge_pp(0.63, 2.46) > 0


@pytest.mark.parametrize("odds", [None, "x", 1.0, 0.9, 0, -1])
def test_못_쓰는_배당은_None이다(odds):
    """🔴 0 이나 0.5 로 채우지 않는다."""
    assert ME.break_even(odds) is None
    assert ME.price_edge_pp(0.63, odds) is None


def test_우리_확률이_없으면_None이다():
    assert ME.price_edge_pp(None, 1.49) is None


def test_디빅과_다른_값이다():
    """🔴 요구는 마진 **포함**, 디빅은 **제거**. 한 이름으로 부르면 못 가른다."""
    # ⚠️ `implied_probs` 는 **home/away 키**를 요구한다(팀 이름이 아니다).
    odds = {"home": 1.49, "away": 2.46}
    devig = ME.implied_probs(odds)
    assert devig is not None
    assert ME.break_even(1.49) > devig["home"]
    assert abs(sum(devig.values()) - 1.0) < 0.01     # 디빅은 1.0
    assert ME.break_even(1.49) + ME.break_even(2.46) > 1.0   # 요구는 1 초과


# ── 분석 입력

def test_입력_블록에_들어간다():
    t = AN.build_input({**BLK, "odds": 1.49, "break_even": 0.6711,
                        "price_edge_pp": -4.1})
    assert "요구 확률 0.6711" in t
    assert "-4.1" in t and "값 없음" in t


def test_배당이_없으면_줄이_안_난다():
    """🔴 야구는 1북이고 그마저 없는 경기가 있다."""
    assert "[가격]" not in AN.build_input(BLK)
    assert "[가격]" not in AN.build_input({**BLK, "break_even": None})


# ── 🔴 반대 위험

def test_게이트를_안_바꿨다():
    """🔴 `classify` 는 종전 그대로다 — 값으로 픽을 거르는 것은 별도 결정이다."""
    src = inspect.getsource(ME.classify)
    assert "break_even" not in src and "price_edge" not in src
    got = ME.classify(0.63, "home", {"home": 1.49, "away": 2.46})
    assert got["market_prob"] is not None and "divergence_pp" in got


def test_내재확률_규약을_재사용한다():
    """🔴 "1.0 이하면 None" 의 원본은 `pick_ledger._implied_prob` 다."""
    src = inspect.getsource(ME.break_even)
    assert "_implied_prob" in src
    from app.engine.pick_ledger import _implied_prob
    assert _implied_prob(1.0) is None and _implied_prob(2.0) == 0.5


def test_원장이_배당을_읽는다():
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL.record_confirm_and_analysis)
    sel = src.split("FROM pick_ledger", 1)[0]
    assert "odds" in sel
