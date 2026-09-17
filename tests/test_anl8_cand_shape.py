"""ANL-8 계약 — `l1` 이 `구조_후보` 모양을 **믿지 않는다.**

🔴 실측 2026-09-17 운영 (SSG@NC · game 1754):
     [analysis] game=1754 분석 실패: 'str' object has no attribute 'get'
   `for c in out["구조_후보"]: c.get("시장")` 이 dict 를 가정했다.
🔴 **ANL-2 가 분석을 살려내니 그 다음 방어선이 무너졌다** — 어제까지는 JSON
   자체가 안 와서 이 줄에 도달한 적이 없었다.
🔴 모양이 틀린 것은 **반려 사유**지 크래시가 아니다. 크래시는 analyze_failed
   로도 안 남고 로그 한 줄로 사라진다(로그는 재배포로 날아간다).
"""
import inspect

import pytest

from app.engine import analyze as AN
from app.engine import structure as ST

FULL = {"결정축": "x", "결정축_근거": "서호철 결장", "결정축_방향": "홈 하향",
        "반대축": "y", "시장_판단": "과대", "시장_판단_이유": "",
        "불확실": "", "근거_수": 1}
BLK = {"home": "NC", "away": "SSG", "league": "KBO", "p_market": 0.66,
       "gap_pp": -10.3, "gate": "시장 과대", "adj_pp": {}, "p_code": 0.66,
       "kickoff_kst": "x", "home_facts": {"out": ["서호철"]}, "away_facts": {}}


def _l1(cand):
    return AN.l1({**FULL, "구조_후보": cand}, BLK)


@pytest.mark.parametrize("bad", [["스프레드 -1.5"], [None], [123], [["x"]]])
def test_모양이_틀리면_반려한다(bad):
    """🔴 터지지 않는다."""
    ok, why = _l1(bad)
    assert ok is False and "모양이 표 밖" in why


def test_빈_목록은_통과한다():
    """🔴 반대 위험 — 후보가 없는 것은 정상이다."""
    assert _l1([])[0] is True
    assert _l1(None)[0] is True


def test_파생에_없는_시장은_종전대로_반려한다():
    ok, why = _l1([{"시장": "없는시장"}])
    assert ok is False and "파생 디빅에 없는" in why


def test_파생에_있으면_통과한다():
    blk = dict(BLK, derived=[{"시장": "spreads", "라인": -1.5,
                              "쪽": "home", "확률": 0.5}])
    assert AN.l1({**FULL, "구조_후보": [{"시장": "spreads"}]}, blk)[0] is True


# ── 프롬프트가 모양을 말한다

def test_프롬프트가_항목_모양을_말한다():
    """⚠️ '시장'만 찾으면 `시장_판단` 때문에 헐겁게 통과한다 — 항목 키로 좁힌다."""
    spec = AN.output_spec()
    for k in ST.CAND_FIELDS:
        assert k in spec, k


# ── 사본 금지

def test_항목_이름을_손으로_안_적었다():
    for fn in (AN.l1, AN.output_spec, AN._cand_fields):
        src = inspect.getsource(fn)
        lines = [ln for ln in src.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        body = "\n".join(lines)
        for k in ST.CAND_FIELDS:
            assert f'"{k}"' not in body, f"{fn.__name__} 가 {k} 를 손으로 적었다"


def test_생산물의_키가_상수와_같다():
    """🔴 상수만 고치고 **생산을 안 고치는** 사고를 막는다."""
    rows = [{"market": "spreads", "side": "home", "line": -1.5, "odds": 1.9},
            {"market": "spreads", "side": "away", "line": 1.5, "odds": 2.0}]
    got = ST.attach_derived({}, rows, home="NC", away="SSG")["derived"]
    assert got, "파생이 안 만들어졌다"
    assert set(got[0]) == set(ST.CAND_FIELDS)


def test_반려가_원장을_막지_않는다():
    """🔴 ANL-2 에서 잠근 성질 — 그대로다."""
    tail = inspect.getsource(AN.run).split("ok1, why1 = l1(", 1)[1]
    assert "to_ledger(parsed" in tail and "failed=True" not in tail
