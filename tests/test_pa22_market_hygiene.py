"""PA-22 계약 — 시장 확률 위생 (지시문 2단계).

🔴 **검사 위치를 나눈다.** 지시문은 "p_mkt 합이 100±0.5 아니면 폐기"라고
   적었는데 그건 **디빅된 확률** 전제다. 우리가 저장하는 것은 배당 **원값**이라
   합이 마진만큼 100 을 넘는 것이 정상이다.
   실측 2026-09-17 (48h · h2h 묶음 523개):
     합 100±0.5 안 0 · 밖 523 · 내재확률 합 101.5 ~ 105.1 ~ 109.0 %
   지시문 숫자를 원값에 그대로 걸면 배당이 **523/523 전부 폐기**된다.
   → 사용자 결정: 원값은 마진 범위 · 디빅 후 합 100±0.5.

⚠️ 채택한 범위로 다시 재니 **523/523 통과 · 폐기 0건**이다(반대 위험 0).
"""
import pytest

from app.engine import market_edge as ME


def test_실측_마진이_통과한다():
    """🔴 반대 위험 — 정상 배당을 버리면 전 경기가 보드 고정이 된다."""
    for odds, want in [({"home": 1.81, "away": 2.05}, 101.5),   # 마진 낮은 쪽
                       ({"home": 1.50, "away": 2.62}, 105.0),   # 중앙 부근
                       ({"home": 2.10, "away": 1.80}, 103.2)]:
        assert ME.margin_ok(odds), (odds, ME.margin_pct(odds))


def test_마진_0은_막는다():
    """실제 북에는 없는 값이다 — 만들어진 확률이거나 자리표다."""
    assert not ME.margin_ok({"home": 2.0, "away": 2.0})          # 정확히 100
    assert not ME.margin_ok({"home": 2.05, "away": 2.05})        # 97.6


def test_마진_과대도_막는다():
    assert not ME.margin_ok({"home": 1.5, "away": 1.7})          # 125%


def test_한쪽만_있으면_못_잰다():
    """🔴 한쪽만으로 디빅하면 마진이 안 빠져 확률이 부푼다(implied_probs 규칙)."""
    assert ME.margin_pct({"home": 1.81}) is None
    assert not ME.margin_ok({"home": 1.81})


def test_3way도_잰다():
    odds = {"home": 2.10, "draw": 3.40, "away": 3.60}
    assert ME.margin_pct(odds) is not None
    assert ME.margin_ok(odds)


def test_디빅_뒤_합은_1이다():
    """지시문 100±0.5 는 **여기** 자리다."""
    p = ME.implied_probs({"home": 1.81, "away": 2.05})
    assert ME.devig_ok(p)
    assert not ME.devig_ok({"home": 0.4, "away": 0.4})
    assert not ME.devig_ok(None)


def test_placeholder_중복을_잡는다():
    """🔴 실사고 SEA@ATH 40.9/59.1 이 두 경기에 그대로 들어왔다."""
    me = {"home": 0.409, "away": 0.591}
    assert ME.placeholder_suspect(me, [{"home": 0.409, "away": 0.591}])
    assert not ME.placeholder_suspect(me, [{"home": 0.410, "away": 0.590}])
    assert not ME.placeholder_suspect(me, [])
    assert not ME.placeholder_suspect(None, [me])


def test_placeholder는_폐기가_아니다():
    """⚠️ 표시만 한다 — 우연히 같을 가능성이 0은 아니다."""
    import inspect
    src = inspect.getsource(ME.placeholder_suspect)
    assert "표시만" in src
    assert src.strip().endswith("return False")


def test_문턱을_상수로_둔다():
    assert ME.MARGIN_MIN_PCT == 100.5
    assert ME.MARGIN_MAX_PCT == 115.0
    assert ME.DEVIG_TOL == 0.005


@pytest.mark.parametrize("bad", [None, {}, {"home": "x", "away": "y"},
                                 {"home": 0.5, "away": 0.5}])
def test_이상한_입력에도_안_터진다(bad):
    assert ME.margin_pct(bad) is None
    assert ME.margin_ok(bad) is False
