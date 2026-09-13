"""MBM-1 — 야구 기본 모델 (야구 모델 지시문 3단계).

구성: 선발 축 · 불펜 축 · 타선 축 · 환경 → 기대 실점 → 피타고리안 → 승률.
**전부 코드가 계산한다. LLM 개입 없음.**

⚠️ 판정 입력은 최근 폼 전용이지만 모델의 **사전값(prior)** 은 시즌 누적을 써도
   된다(지시문 5번) — 사전값은 "최근 3~5경기를 얼마나 믿을지 정하는 축소 계수"
   로만 쓴다. Gemini 에게는 사전값이 아니라 **합쳐진 확률만** 간다.
🔴 누수 금지: 경기 t 의 입력에 t 이후 정보가 들어가면 안 된다.
"""
import math

import pytest

from app.model_baseball import model as M


# ── 축소 결합

def test_표본이_없으면_사전값_그대로():
    assert M.shrink(recent=None, n=0, prior=4.20, k=30) == pytest.approx(4.20)


def test_표본이_많을수록_최근값에_가깝다():
    a = M.shrink(recent=2.00, n=10, prior=4.20, k=30)
    b = M.shrink(recent=2.00, n=60, prior=4.20, k=30)
    assert 4.20 > a > b > 2.00, (a, b)


def test_축소는_이닝_가중이다():
    """K_sp 단위가 **이닝**이다(지시문: 초기 30이닝)."""
    assert M.shrink(recent=2.0, n=30, prior=4.0, k=30) == pytest.approx(3.0)


# ── 선발 축

def test_선발_최근_5등판만_본다():
    starts = [{"ip": 6.0, "r": 2} for _ in range(8)]
    starts[0]["r"] = 99                      # 가장 최근이 이상치
    out = M.sp_axis(starts, prior=4.2, k=30, window=5)
    assert out["n_ip"] == pytest.approx(30.0)   # 5 × 6이닝
    assert out["ra9"] > 4.2                      # 이상치가 끌어올린다


def test_선발_기대이닝은_7을_넘지_않는다():
    starts = [{"ip": 9.0, "r": 0} for _ in range(5)]
    assert M.sp_axis(starts, prior=4.2)["ip"] == pytest.approx(7.0)


def test_선발_기록이_없으면_사전값과_리그_평균이닝():
    out = M.sp_axis([], prior=4.2)
    assert out["ra9"] == pytest.approx(4.2)
    assert 4.0 <= out["ip"] <= 6.0


# ── 불펜 축

def test_불펜_가용성_보정():
    """최근 3일 투구한 필승조 1명당 +0.3 (초기값, 변수 대장 범위 안)."""
    base = M.bp_axis([{"ip": 30.0, "r": 12}], prior=4.2, tired=0)
    worn = M.bp_axis([{"ip": 30.0, "r": 12}], prior=4.2, tired=2)
    assert worn["ra9"] == pytest.approx(base["ra9"] + 0.6, abs=1e-9)


# ── 타선 축

def test_타선은_리그_평균_대비로_환산한다():
    lg = {"woba": 0.320, "rpg": 4.40}
    same = M.off_axis(woba=0.320, league=lg)
    up = M.off_axis(woba=0.360, league=lg)
    assert same == pytest.approx(4.40)
    assert up > same


def test_타순이_없으면_표시가_남는다():
    out = M.team_offense(order_woba=None, fallback_woba=0.315,
                         league={"woba": 0.320, "rpg": 4.40})
    assert out["lineup_missing"] is True
    assert out["rpg"] > 0


# ── 기대 실점 · 승률

def test_기대실점은_선발과_불펜의_이닝_배분이다():
    ra = M.expected_runs(sp_ra9=3.0, sp_ip=6.0, bp_ra9=6.0)
    # 6이닝 3.0 + 3이닝 6.0 = (3*6 + 6*3)/9 = 4.0
    assert ra == pytest.approx(4.0)


def test_피타고리안_지수는_183이다():
    assert M.PYTHAG_EXP == 1.83
    p = M.pythag(rs=5.0, ra=4.0)
    assert 0.5 < p < 0.7


def test_홈이점이_승률을_올린다():
    a = M.win_prob(rs_h=4.4, ra_h=4.4, rs_a=4.4, ra_a=4.4, hfa=0.0)
    b = M.win_prob(rs_h=4.4, ra_h=4.4, rs_a=4.4, ra_a=4.4, hfa=0.04)
    assert a == pytest.approx(0.5) and b > a


def test_승률은_0과_1_사이다():
    p = M.win_prob(rs_h=99.0, ra_h=0.1, rs_a=0.1, ra_a=99.0, hfa=0.04)
    assert 0.0 < p < 1.0


# ── 출력 계약

def test_예측은_기여값을_함께_낸다():
    out = M.predict(
        home={"sp": {"ra9": 3.5, "ip": 6.0}, "bp": {"ra9": 4.0}, "off": {"rpg": 4.6}},
        away={"sp": {"ra9": 4.5, "ip": 5.0}, "bp": {"ra9": 4.8}, "off": {"rpg": 4.2}},
        park=1.0, hfa=0.04)
    assert 0.0 < out["p_home"] < 1.0
    assert out["exp_total"] > 0
    for k in ("sp_home", "sp_away", "bp_home", "bp_away",
              "off_home", "off_away", "park", "hfa"):
        assert k in out["components"], k


def test_LLM을_부르지_않는다():
    """🔴 전부 코드가 계산한다.

    ⚠️ 실제 **호출·임포트**만 본다. 주석에 "Gemini 에게는 확률만 간다"고 적는
       것은 허용한다 — 그 규칙이 코드에서 떨어지면 다음 사람이 사전값을 준다.
       (오늘 같은 부류의 무딘 계약을 네 번 만들었다: tor⊂collectors,
        elo⊂주석, date=⊂주석, gemini⊂주석)
    """
    import inspect

    src = inspect.getsource(M)
    for bad in ("complete_json", "judge_route", "import httpx",
                "app.llm", "app.engine"):
        assert bad not in src, bad


# ── [MBM-2] 확률이 폭주하지 않는다

def test_wOBA_환산_계수가_표준이다():
    """🔴 **실측 2026-09-13**: 계수를 1/0.0125 = 80 으로 뒀더니 2024시즌
    확률 범위가 **0.0400 ~ 1.0000**(표준편차 0.2509)으로 폭주했다.
    야구 단일 경기 승률이 100% 일 수 없다.

    표준 환산: `wRAA/PA = (wOBA − lg) / wOBA_scale(1.25)`,
    경기당 타석 약 38 → 계수 ≈ **30**.
    """
    assert 25.0 <= M.WOBA_TO_RPG <= 35.0, M.WOBA_TO_RPG


def test_wOBA_차이가_현실적인_득점차를_만든다():
    lg = {"woba": 0.320, "rpg": 4.40}
    # 리그 최상위와 최하위 타선 차이는 대략 wOBA 0.040
    hi = M.off_axis(woba=0.340, league=lg)
    lo = M.off_axis(woba=0.300, league=lg)
    assert 0.8 <= (hi - lo) <= 3.0, (hi, lo)


def test_승률에_현실적인_상하한이_있다():
    """🔴 완벽한 정보를 가져도 MLB 단일 경기 예측 상한은 약 72% 다
    (`scoring.cap_probability` 주석의 근거와 같은 사실)."""
    p = M.win_prob(rs_h=99.0, ra_h=0.1, rs_a=0.1, ra_a=99.0, hfa=0.04)
    assert p <= M.P_CAP, p
    q = M.win_prob(rs_h=0.1, ra_h=99.0, rs_a=99.0, ra_a=0.1, hfa=0.04)
    assert q >= 1.0 - M.P_CAP, q


def test_상하한이_승률_상한_규약과_같다():
    """⚠️ 숫자를 두 곳에 적지 않는다 — 0.68 은 `config.max_win_prob_mlb` 다."""
    from app.config import get_settings

    assert M.P_CAP == pytest.approx(float(get_settings().max_win_prob_mlb))


# ── [MBM-3] 방향. 분포만 재면 부호가 뒤집혀도 통과한다.

_LG = {"woba": 0.320, "rpg": 4.40}


def _side(sp_r=3.0, bp_r=4.0, woba=None):
    return {"sp": M.sp_axis([{"ip": 6.0, "r": sp_r}] * 3, 4.40),
            "bp": M.bp_axis([{"ip": 10.0, "r": bp_r}], 4.40),
            "off": M.team_offense(woba, None, _LG)}


#: 양쪽이 똑같을 때의 값. ⚠️ 0.5 가 아니다 — 홈 이점이 들어 있다.
#  방향 계약은 **이 값 대비**로 본다. 0.5 로 재면 불펜처럼 효과가 작은 축은
#  홈 이점에 묻혀 "원정이 나은데도 홈 승률 0.51" 이 되고, 계약이 헛돈다.
_NEUTRAL = M.predict(_side(), _side())["p_home"]


def test_중립값은_홈_이점만큼이다():
    assert _NEUTRAL == pytest.approx(0.54, abs=1e-9)


def test_선발이_좋은_쪽이_이긴다():
    """🔴 MBM-3 — 이 계약이 없어서 부호가 뒤집힌 채 배포됐다."""
    out = M.predict(_side(sp_r=1.0), _side(sp_r=6.0))
    assert out["p_home"] > _NEUTRAL, out["components"]
    rev = M.predict(_side(sp_r=6.0), _side(sp_r=1.0))
    assert rev["p_home"] < _NEUTRAL, rev["components"]


def test_불펜이_좋은_쪽이_이긴다():
    assert M.predict(_side(bp_r=2.0), _side(bp_r=8.0))["p_home"] > _NEUTRAL
    assert M.predict(_side(bp_r=8.0), _side(bp_r=2.0))["p_home"] < _NEUTRAL


def test_타선이_좋은_쪽이_이긴다():
    assert M.predict(_side(woba=0.360), _side(woba=0.280))["p_home"] > _NEUTRAL
    assert M.predict(_side(woba=0.280), _side(woba=0.360))["p_home"] < _NEUTRAL


def test_양쪽을_맞바꾸면_확률이_뒤집힌다():
    """홈 이점만큼만 어긋난다."""
    # ⚠️ 절사(0.32~0.68) 밖으로 나가면 합이 1.0 으로 눌린다 — 안쪽 입력을 쓴다.
    h, a = _side(sp_r=3.4, woba=0.330), _side(sp_r=4.2, woba=0.312)
    p1 = M.predict(h, a)["p_home"]
    p2 = M.predict(a, h)["p_home"]
    assert p1 + p2 == pytest.approx(1.0 + 2 * 0.04, abs=0.02), (p1, p2)


def test_총득점은_배정과_무관하다():
    """`(rs+ra)` 넷의 합이라 홈/원정 배정이 바뀌어도 같다."""
    h, a = _side(sp_r=1.0, woba=0.360), _side(sp_r=7.0, woba=0.280)
    assert M.predict(h, a)["exp_total"] == pytest.approx(M.predict(a, h)["exp_total"])


def test_극단에서도_절사된다():
    lo = M.predict(_side(sp_r=12.0, bp_r=12.0, woba=0.250),
                   _side(sp_r=0.0, bp_r=0.0, woba=0.400))["p_home"]
    hi = M.predict(_side(sp_r=0.0, bp_r=0.0, woba=0.400),
                   _side(sp_r=12.0, bp_r=12.0, woba=0.250))["p_home"]
    assert 1.0 - M.P_CAP <= lo and hi <= M.P_CAP, (lo, hi)
