"""U8 — 결장을 **이름 수**가 아니라 **중요도**로 센다.

🔴 종전에는 주전 3명 결장과 후보 3명 결장이 같은 −3 이었다.
   U6 가 시장가치를 저장했는데 쓰는 곳이 없었다.
🔴 그리고 main_axis 를 **미배선 analyze(LLM)** 가 채우게 돼 있었다.
   코드가 정해야 LLM 이 없어도 결정축이 선다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import adjust as A
from app.engine import prob as P

TT = 6352468                      # 가시마 선발 총가치(실측)
STAR = {"market_value": 3000000}
SUB = {"market_value": 200000}


def test_importance_공식():
    """0.5·(선발/10) + 0.5·(가치/(총가치/11))"""
    got = A.importance(STAR, team_total_value=TT, recent_starts=9)
    want = 0.5 * 0.9 + 0.5 * (3000000 / (TT / 11))
    assert got == pytest.approx(round(want, 3))


def test_주전과_후보가_다르게_세어진다():
    """🔴 이것이 이 U 의 본체다."""
    star3 = A.contrib_out([STAR] * 3, team_total_value=TT, recent_starts=9)
    sub3 = A.contrib_out([SUB] * 3, team_total_value=TT, recent_starts=1)
    assert star3 < sub3, (star3, sub3)
    assert star3 == -6.0 and sub3 == pytest.approx(-1.0, abs=0.2)


@pytest.mark.parametrize("role", A.MIN_IMPORTANCE_ROLES)
def test_GK_주장_득점1위는_최소_1(role):
    cheap = {"market_value": 1000, role: True}
    assert A.importance(cheap, team_total_value=TT, recent_starts=0) >= 1.0
    # 역할이 없으면 낮아야 한다 — 최소값이 전원에게 붙으면 안 된다
    assert A.importance({"market_value": 1000}, team_total_value=TT,
                        recent_starts=0) < 1.0


# ── 🔴 반대 위험: 없는 값을 0 으로 읽지 않는다

def test_출장이력이_없으면_시장가치_단독():
    """안 본 것과 안 뛴 것은 다르다 — 0 으로 읽으면 신입이 전부 0.5 가 된다."""
    only_mv = A.importance(STAR, team_total_value=TT)
    both = A.importance(STAR, team_total_value=TT, recent_starts=0)
    assert only_mv > both, (only_mv, both)
    assert only_mv == pytest.approx(3000000 / (TT / 11), rel=1e-3)


def test_총가치가_없으면_출장률_단독():
    assert A.importance(STAR, recent_starts=8) == pytest.approx(0.8)


def test_둘_다_없으면_중립_1():
    assert A.importance({}) == 1.0
    assert A.importance({"market_value": 0}, team_total_value=0) == 1.0


def test_총가치가_0이어도_안_터진다():
    assert A.importance(STAR, team_total_value=0, recent_starts=5) == pytest.approx(0.5)


# ── 결장·복귀

def test_결장은_1_5배_상한_6():
    assert A.OUT_MULT == 1.5 and A.OUT_CAP == 6.0
    one = A.contrib_out([SUB], team_total_value=TT, recent_starts=2)
    assert one == pytest.approx(-A.importance(SUB, team_total_value=TT,
                                              recent_starts=2) * 1.5, abs=0.01)
    assert A.contrib_out([STAR] * 10, team_total_value=TT, recent_starts=10) == -6.0


def test_복귀는_1_5의_1_5배():
    assert A.RETURN_MULT == 1.5
    imp = A.importance(SUB, team_total_value=TT, recent_starts=2)
    assert A.contrib_return([SUB], team_total_value=TT,
                            recent_starts=2) == pytest.approx(imp * 1.5 * 1.5,
                                                              abs=0.01)


def test_결장상한은_조정_전체상한과_다른_층이다():
    """🔴 반대 위험 — 섞으면 조정이 이중으로 잘린다."""
    assert A.OUT_CAP == 6.0 and P.ADJ_SUM_CAP == 6.0
    src = inspect.getsource(A.contrib_out)
    assert "ADJ_SUM_CAP" not in src, "전체 상한을 여기서 또 건다"


# ── contrib 제외

def test_contrib_2pp_미만은_빠진다():
    assert A.MIN_CONTRIB_PP == 2.0
    keep, drop = A.drop_small({"주전결장": -4.2, "짧은휴식": -1.1,
                               "주중대항전": -2.0})
    assert set(keep) == {"주전결장", "주중대항전"}
    assert set(drop) == {"짧은휴식"}


def test_경계는_2pp_포함():
    keep, drop = A.drop_small({"a": 2.0, "b": 1.999, "c": -2.0})
    assert set(keep) == {"a", "c"} and set(drop) == {"b"}


def test_제외는_축소_앞에서_한다():
    """🔴 반대 위험 — 뒤에서 빼면 축소된 값으로 2%p 를 재게 된다."""
    adj = {"a": -3.0, "b": -1.5}
    keep, _ = A.drop_small(adj)
    after = P.shrink_and_cap(adj)          # 축소하면 −1.5 → −0.75
    assert "b" in adj and abs(after["b"]) < A.MIN_CONTRIB_PP
    assert "b" not in keep, "축소 뒤에 걸러도 같은 결과처럼 보이지만 기준이 다르다"


# ── 결정축

def test_main_axis는_상위_2():
    got = A.axes({"주전결장": -4.2, "복귀": 2.6, "주중대항전": -2.0})
    assert got["main_axis"] == ["주전결장", "복귀"]


def test_counter_axis는_반대방향_1개():
    got = A.axes({"주전결장": -4.2, "복귀": 2.6, "주중대항전": -2.0})
    assert got["counter_axis"] == "복귀"
    assert got["direction"] == "away"


def test_반대방향이_없으면_counter도_없다():
    """🔴 반대 위험 — 같은 방향 2위를 반대축이라 부르면 거짓이다."""
    got = A.axes({"a": -4.0, "b": -3.0, "c": -2.0})
    assert got["counter_axis"] is None
    assert got["main_axis"] == ["a", "b"]


def test_빈_조정이면_축이_없다():
    got = A.axes({})
    assert got == {"main_axis": [], "counter_axis": None, "direction": None}
    assert A.axes({"a": 0.0})["main_axis"] == []


# ── 9종 · 원장

def test_ADJ_DEFS가_9종이다():
    src = inspect.getsource(A)
    for k in ("핵심결장", "직전대패"):
        assert k in src, k
    assert "key_out_importance" in A.ADJ_DEFS
    assert "rout_margin" in A.ADJ_DEFS


def test_원장에_adj_dropped가_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS adj_dropped" in src
