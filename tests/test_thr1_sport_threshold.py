"""THR-1 계약 — 잡음 문턱이 **종목을 가른다.**

🔴 실측 2026-09-17: 딥서치가 "서호철 1군 말소"·"고종욱 1군 말소"를 찾아냈는데
   가감이 0 이었다. 결장 1명 = 1.5%p 인데 문턱이 2.0 이라 **늘 버려진다.**
   야구는 결장이 대개 한 명씩 난다.
🔴 **크기는 맞았다**(FORKS F-10). WAR/162 — 평균 주전 2 WAR = 1.2%p ·
   좋은 주전 4 WAR = 2.5%p. 1.5%p 는 "평균 주전" 자리다.
   틀린 것은 문턱이었다 — 2.0 은 WAR 3.2 미만을 전부 버린다.
⚠️ 축구는 다르다 — "라인업 변경 하나 = 승률 2~9%p"(F-1)라 문턱을 넘는다.

사용자 승인 2026-09-17: "해제하고 고쳐라"
"""
import inspect

import pytest

from app.engine import adjust as A
from app.engine import rejudge as RJ
from app.engine.scoring import BASEBALL_SPORTS

ONE = {"home": {"bench_notable": ["P0"], "surprise_in": []}}


def _rw(sport, adj=None, diff=ONE):
    return RJ.reweigh(adj=dict(adj or {}), p_code=0.66, diff=diff, players={},
                      grade="중", sport=sport, source=RJ.SRC_NEWS)


# ── 문턱

@pytest.mark.parametrize("sport", sorted(BASEBALL_SPORTS))
def test_야구는_1점0이다(sport):
    assert A.min_contrib(sport) == 1.0


def test_축구는_2점0_그대로다():
    """🔴 반대 위험 — 낮출 근거가 없다(F-1: 라인업 변경 하나 = 2~9%p)."""
    assert A.min_contrib("soccer") == 2.0


def test_종목을_모르면_종전값이다():
    """🔴 옛 호출부가 안 깨진다."""
    assert A.min_contrib(None) == A.MIN_CONTRIB_PP == 2.0
    assert A.min_contrib("") == 2.0


def test_모르는_종목은_축구로_본다():
    assert A.min_contrib("cricket") == 2.0


# ── 실제 동작

def test_야구_결장_한_명이_반영된다():
    g = _rw("kbo")
    assert g["adj_after"] == {"라인업결장:home": -1.5}
    assert g["changed"] is True


def test_축구_결장_한_명은_종전대로_제외된다():
    """🔴 반대 위험 — 이 수정이 축구를 건드리면 안 된다."""
    g = _rw("soccer")
    assert g["adj_after"] == {}
    assert g["changed"] is False


def test_야구도_잡음은_버린다():
    """🔴 문턱을 **없애는** 것이 아니라 크기에 맞추는 것이다."""
    keep, drop = A.drop_small({"잡음": -0.5, "실제": -1.5}, "kbo")
    assert keep == {"실제": -1.5} and drop == {"잡음": -0.5}


def test_인자를_안_주면_종전_동작이다():
    keep, drop = A.drop_small({"a": -1.5})
    assert keep == {} and drop == {"a": -1.5}


# ── 사본 금지

def test_숫자를_손으로_안_적었다():
    """🔴 1.0·2.0 은 `config/rules.yaml` 이 원본이다."""
    lines = [ln for ln in inspect.getsource(A.min_contrib).splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    body = "\n".join(lines).split('"""')[-1]
    assert "min_contrib_pp_by_sport" in body
    assert "1.0" not in body and "2.0" not in body


def test_종목_분류를_새로_안_만들었다():
    """🔴 `scoring.BASEBALL_SPORTS` 가 원본이다(`prob._table` 과 같은 것)."""
    src = inspect.getsource(A.min_contrib)
    assert "BASEBALL_SPORTS" in src
    for s in ("kbo", "npb", "mlb"):
        assert f'"{s}"' not in src


def test_reweigh가_종목을_넘긴다():
    assert "A.drop_small(add, sport)" in inspect.getsource(RJ.reweigh)


def test_U13_대조가_쓰는_이름을_지키지_않았다면_실패():
    """🔴 `test_u13_rules` 가 `MIN_CONTRIB_PP` 이름으로 rules.yaml 을 대조한다."""
    assert hasattr(A, "MIN_CONTRIB_PP")
