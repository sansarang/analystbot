"""U7 — 확인 판정 H2. "자료가 많으면 픽"을 끝낸다.

🔴 U6 의 `fill_schema` 가 만든 구분이 이 판정의 전제다:
     값이 있다 → confirmed · `[]`/False → refuted · None → unknown
   `[]` 를 unknown 으로 읽으면 "결장 0명"이라는 **정보**가 "모른다"로 바뀌고
   멀쩡한 경기가 보드로 간다.
🔴 `unknown 과반 → 보드` 가 원칙 4·11 의 구현이다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import gate as G
from app.engine import hypothesis as H


def _h(label=G.DOUBT, **kw):
    kw.setdefault("sport", "soccer")
    kw.setdefault("side", "home")
    kw.setdefault("gap_pp", 12.0)
    return H.build(label, **kw)


# ── 세 갈래

@pytest.mark.parametrize("value,want", [
    (["A"], H.CONFIRMED), ("UCL 원정", H.CONFIRMED), (1, H.CONFIRMED),
    ([], H.REFUTED), ("", H.REFUTED), (False, H.REFUTED), ({}, H.REFUTED),
    (None, H.UNKNOWN),
])
def test_세_갈래가_갈린다(value, want):
    assert H._verdict_of(value) == want


def test_빈값은_refuted_지_unknown이_아니다():
    """🔴 반대 위험 — "결장 0명"은 정보다. 모른다고 치면 안 된다."""
    assert H._verdict_of([]) == H.REFUTED
    assert H._verdict_of([]) != H.UNKNOWN
    h = _h()
    r = H.confirm(h, {"home": {"out": []}, "away": {}})
    assert "home.out" in r[H.REFUTED]
    assert "home.out" not in r[H.UNKNOWN]


def test_None은_unknown():
    h = _h()
    r = H.confirm(h, {"home": {"out": None}, "away": {}})
    assert "home.out" in r[H.UNKNOWN]


def test_값이_있으면_confirmed():
    h = _h()
    r = H.confirm(h, {"home": {"out": ["A"], "midweek": "UCL"}, "away": {}})
    assert set(r[H.CONFIRMED]) == {"home.out", "home.midweek"}


# ── 문턱

def test_문턱을_넘으면_sufficient():
    h = _h()
    assert h.sufficient_count == 2
    r1 = H.confirm(h, {"home": {"out": ["A"]}, "away": {}})
    assert r1["sufficient"] is False, "1개인데 충족이다"
    r2 = H.confirm(h, {"home": {"out": ["A"], "midweek": "UCL"}, "away": {}})
    assert r2["sufficient"] is True


def test_빅매치는_문턱_3():
    h = _h(bigmatch=True)
    two = {"home": {"out": ["A"], "midweek": "UCL"}, "away": {}}
    assert H.confirm(h, two)["sufficient"] is False
    three = {"home": {"out": ["A"], "midweek": "UCL", "last3": "WWL"}, "away": {}}
    assert H.confirm(h, three)["sufficient"] is True


def test_need가_비면_sufficient는_False():
    """🔴 반대 위험 — 0 >= 0 으로 통과시키면 아무것도 안 찾고 픽이 나간다."""
    b = H.build(G.BOARD, sport="soccer", side=None)
    r = H.confirm(b, {})
    assert r["need_n"] == 0
    assert r["sufficient"] is False
    assert r["board"] is True, "찾을 것이 없으면 보드다"


# ── 미상 과반

def test_unknown_과반이면_보드():
    h = _h()
    n = len(h.need)
    assert n == 8
    # 미상 5/8 = 62.5% > 50% → 보드
    r = H.confirm(h, {"home": {"out": ["A"], "midweek": "UCL", "doubt": []},
                      "away": {}})
    assert len(r[H.UNKNOWN]) == 5 and r["board"] is True
    # 미상 3/8 = 37.5% → 보드 아님
    full = {"home": {"out": ["A"], "doubt": [], "bench_notable": [],
                     "midweek": "U", "last3": "WWL"},
            "away": {}}
    r2 = H.confirm(h, full)
    assert len(r2[H.UNKNOWN]) == 3 and r2["board"] is False


def test_문턱은_넘어도_미상_과반이면_보드():
    """🔴 둘은 독립이다 — 확인이 많아도 모르는 게 절반을 넘으면 픽을 안 낸다."""
    h = _h()
    r = H.confirm(h, {"home": {"out": ["A"], "midweek": "U", "doubt": []},
                      "away": {}})
    assert r["sufficient"] is True and r["board"] is True


def test_과반_기준이_상수다():
    from app.config import get_settings

    assert get_settings().unknown_board_ratio == 0.5
    src = inspect.getsource(H._unknown_ratio)
    assert "unknown_board_ratio" in src
    assert "rules.yaml" in src, "U13 이전이라는 표시가 없다"


# ── 🔴 반대 위험: 교차 오독

def test_상대편_칸을_내_것으로_읽지_않는다():
    h = _h()
    r = H.confirm(h, {"home": {}, "away": {"out": ["A"], "doubt": ["B"]}})
    assert set(r[H.CONFIRMED]) == {"away.out", "away.doubt"}
    assert "home.out" in r[H.UNKNOWN], "원정 값으로 홈을 채웠다"


def test_순수함수다():
    src = inspect.getsource(H.confirm)
    for bad in ("asyncpg", "httpx", "get_pool", "await "):
        assert bad not in src, bad


def test_원장_세_칸이_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    for col in ("confirmed", "refuted", "unknown_axes"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


def test_결과_모양이_원장에_그대로_든다():
    import json

    r = H.confirm(_h(), {"home": {"out": ["A"]}, "away": {}})
    assert set(r) == {"confirmed", "refuted", "unknown", "sufficient",
                      "board", "need_n", "sufficient_count"}
    json.dumps(r, ensure_ascii=False)
