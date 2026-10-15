"""🔴🔴 **축2 가 변수를 센다** — 사용자 결정 2026-10-15(1번).

⚠️ 실측 2026-10-15(노리치 A/B): 배치표가 축2 로 보낸 변수가 값에 **한 푼도**
   안 들어갔다 — `varset` 은 `refs`(근거 이름표)에만 쓰였다. 전략 변수 넷을
   넣고 빼도 확률이 **0.0%p** 로 같았다.
🔴 크기는 **새로 짓지 않는다** — 규칙 하나당 쓰는 `per_rule` 그대로다.
"""
from __future__ import annotations

from app.core import matchup as mu


class _V:
    def __init__(self, vid: str, favors: str) -> None:
        self.id, self.favors = vid, favors


class _Set:
    """🔴 대역 — **그 자리를 물었을 때만** 변수를 돌려준다(배치표 흉내)."""

    def __init__(self, rows: list, place: str = "axis2") -> None:
        self._rows, self._place = rows, place

    def of(self, place: str) -> list:
        return list(self._rows) if place == self._place else []


def _box() -> dict:
    """🔴 축2 가 돌 최소 재료 — 스타일이 있어야 센다(없으면 ⬜)."""
    return {"style": {"home": {}, "away": {}}, "fired2": [], "off": {}}


def _per() -> float:
    return float(dict(mu.table().get("axis2") or {}).get("per_rule") or 0.0)


def test_변수가_축2_값을_움직인다() -> None:
    per = _per()
    assert per > 0, "🔴 `per_rule` 이 없다 — 표를 먼저 본다"
    # 🔴 변수가 **하나도 없으면** 종전대로 ⬜ 다(값 0 이 아니다 · #3)
    zero = mu.axis2(_box(), _Set([]))
    assert zero.home is None, "🔴 빈 축을 0 으로 적었다"
    one = mu.axis2(_box(), _Set([_V("SL1", "home")]))
    two = mu.axis2(_box(), _Set([_V("SL1", "home"), _V("SL2", "home")]))
    assert one.home == per, (one.home, per)
    assert two.home - one.home == per, (two.home, one.home, per)


def test_방향은_favors_가_가리키는_쪽이다() -> None:
    got = mu.axis2(_box(), _Set([_V("SL1", "away")]))
    assert got.away > got.home, (got.home, got.away)


def test_both_는_안_센다() -> None:
    """🔴 방향 없는 변수는 축을 밀지 않는다(지어내지 않는다)."""
    zero = mu.axis2(_box(), _Set([]))
    got = mu.axis2(_box(), _Set([_V("SL1", "both")]))
    assert (got.home, got.away) == (zero.home, zero.away)


def test_몇_개를_셌는지_사유에_적는다() -> None:
    """🔴 #3 — 센 것을 숨기지 않는다(카드가 그 글을 적는다)."""
    got = mu.axis2(_box(), _Set([_V("SL1", "home"), _V("SL2", "away")]))
    assert "변수 2개" in got.why, got.why


def test_근거_이름표는_그대로_남는다() -> None:
    got = mu.axis2(_box(), _Set([_V("SL1", "home"), _V("R2", "both")]))
    assert got.refs == ["SL1", "R2"], got.refs


def test_크기를_새로_짓지_않았다() -> None:
    """🔴 계수 금지 — 축2 의 변수 크기는 `per_rule` **그 값**이다."""
    import inspect
    src = inspect.getsource(mu.axis2)
    i = src.index("축2 가 변수를 센다")
    tail = src[i:]
    assert "val[side] = val.get(side, 0.0) + per * cnt" in tail, tail[:400]
    assert "PROVISIONAL" in src, "🔴 임시값 꼬리가 빠졌다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **축3 도 변수를 센다** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════


def _box3() -> dict:
    """🔴 축3 이 돌 최소 재료 — 골 프로필이 있어야 센다(없으면 ⬜)."""
    return {"profile": {"home": {}, "away": {}}, "fired": []}


def _per3() -> float:
    return float(dict(mu.table().get("axis3") or {}).get("per_rule") or 0.0)


def test_축3_도_변수를_센다() -> None:
    per = _per3()
    assert per > 0
    r = {"home": 1.0, "away": 1.0}
    zero = mu.axis3(_box3(), _Set([], "axis3"), r=r)
    one = mu.axis3(_box3(), _Set([_V("SL1", "home")], "axis3"), r=r)
    assert zero.home == 0.0, zero.home
    assert one.home == per, (one.home, per)
    assert "변수 1개" in one.why, one.why


def test_축3_도_both_는_안_센다() -> None:
    r = {"home": 1.0, "away": 1.0}
    got = mu.axis3(_box3(), _Set([_V("SL1", "both")], "axis3"), r=r)
    assert (got.home, got.away) == (0.0, 0.0)


def test_축3_변수에도_r_가중이_걸린다() -> None:
    """🔴 C8 — 선수단 교체 팀은 과거를 덜 믿는다. 변수도 같이 깎인다."""
    per = _per3()
    got = mu.axis3(_box3(), _Set([_V("SL1", "home")], "axis3"),
                   r={"home": 0.5, "away": 1.0})
    assert got.home == round(per * 0.5, 4), (got.home, per)


def test_축3_도_크기를_새로_짓지_않았다() -> None:
    import inspect
    src = inspect.getsource(mu.axis3)
    assert "축3 도 변수를 센다" in src
    assert "val[fav] = val.get(fav, 0.0) + per" in src
