"""PA-27-c 계약 — 시장 되짚기는 **대체 전 원본 adj** 로 한다.

🔴 `reweigh` 는 배당을 다시 긁지 않고 `p_code = p_market + Σ축소(adj)` 를
   되짚어 시장값을 얻는다. PA-27-b 가 `주전결장` 을 빼고 난 **줄어든 adj** 로
   되짚으면 시장을 그만큼 높게 잡는다 — 대체했다면서 그 축을 **한 번 더 뺀다.**

실측 2026-09-17 (adj={'주전결장':-1.5,'짧은휴식':-2.0} · p_code=0.62 · 홈 결장 2명):
    되짚기 base_adj → 시장 0.6300 → p_after 0.6050   ← 틀렸다
    되짚기 orig_adj → 시장 0.6375 → p_after 0.6125   ← 맞다
**0.75%p** 이고 방향이 늘 결장 쪽이다.
"""
import inspect

import pytest

from app.engine import prob as P
from app.engine import rejudge as RJ

ORIG = {"주전결장": -1.5, "짧은휴식": -2.0}
DIFF = {"home": {"bench_notable": ["A", "B"], "surprise_in": []}}


def _run(adj, p=0.62, diff=DIFF):
    return RJ.reweigh(adj=dict(adj), p_code=p, diff=diff, players={},
                      grade="중")


def test_되짚기가_원본_adj를_쓴다():
    g = _run(ORIG)
    want = P.p_code(RJ._market_of(0.62, ORIG), g["adj_after"], "soccer")
    assert g["p_code_after"] == want


def test_실측값_그대로다():
    """🔴 방향만 재면 0.75%p 를 못 잡는다 — 숫자를 박는다."""
    assert _run(ORIG)["p_code_after"] == pytest.approx(0.6125, abs=1e-6)


def test_대체가_없으면_종전과_같다():
    """🔴 반대 위험 — 대체가 안 일어나는 경로는 안 건드린다."""
    base = {"짧은휴식": -2.0}
    g = _run(base)
    want = P.p_code(RJ._market_of(0.62, base), g["adj_after"], "soccer")
    assert g["p_code_after"] == want


def test_diff가_없으면_안_바꾼다():
    g = _run(ORIG, diff=None)
    assert g["adj_after"] == ORIG and g["p_code_after"] == 0.62


def test_대체해도_원본이_안_망가진다():
    """🔴 호출자가 넘긴 dict 를 건드리면 원장 저장이 오염된다."""
    caller = dict(ORIG)
    _run(caller)
    assert caller == ORIG


def test_되짚기를_두_번_하지_않는다():
    """🔴 `_market_of` 호출은 **한 번**이다 — 두 번이면 기준이 갈린다."""
    src = inspect.getsource(RJ.reweigh)
    assert src.count("_market_of(") == 1
