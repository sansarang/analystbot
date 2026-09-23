"""[ODD-S] 물리적으로 불가능한 배당이 DB 에 들어오고 있다.

사용자 2026-09-23: "노이즈인지 실제 감지..." → 실측 → "가,나,다 먼저하고"

🔴 **실측 2026-09-23** — 배당 이동이 노이즈인지 재다가 원인을 찾았다:
```
증분 lag-1 자기상관 ρ₁   kbo −0.5849 · npb −0.5751   (−0.5 = 완전 교대)
                        mlb +0.0001 · soccer +0.1040 (랜덤워크 = 진짜)
종가가 시가보다          mlb·soccer 개선 · **npb 악화(−0.00896)**
```
원인은 **한쪽 배당만 두 값 사이를 오가는 것**이었다:
```
g1774 롯데@한화   홈 2.08 고정 · 원정 2.20 ↔ 1.71 반복
  2.08/2.20 → 1/2.08 + 1/2.20 = 0.935   ← 합이 1 미만 = 차익거래. 존재할 수 없다
  2.08/1.71 → 1/2.08 + 1/1.71 = 1.066   ← 정상(마진 6.6%)
```
불가능한 값을 빼면 진동이 줄어든다: kbo ρ₁ −0.5849 → **−0.1561**

보유량: kbo 3,625 중 145(4.0%) · npb 3,789 중 94(2.5%) · mlb 7,179 중 5(0.1%)

🔴 **`odds_math.margin()` 이 이미 있고 "위생 검사용"이라 적혀 있는데
   쓰는 곳이 0곳이었다.** 만들어 놓고 안 이은 자리다 — 새로 만들지 않고 잇는다.

⚠️ **축구를 2-way 로 재면 안 된다.** 무승부 몫 때문에 `1/홈 + 1/원정 < 1` 이
   정상이다(실측 중앙 0.78). 완전한 결과 집합으로 재야 한다.
"""
from __future__ import annotations

import pytest

from app.flow.odds_math import impossible_set, margin


# ── 판정 ────────────────────────────────────────────────────────────

def test_합이_1_미만이면_불가능하다():
    """🔴 g1774 실물. 북은 마진 없이 호가를 내지 않는다."""
    assert impossible_set([2.08, 2.20]) is True      # 0.935
    assert impossible_set([2.08, 1.71]) is False     # 1.066


def test_npb_실물도_잡는다():
    """⚠️ 1.98/1.97 은 합 1.0127 — **불가능은 아니다.** 얇을 뿐이다.
    여기서 잡으면 정상 데이터를 버린다(반대 위험). 잡지 않는 것이 맞다."""
    assert impossible_set([1.98, 1.97]) is False
    assert impossible_set([1.98, 1.77]) is False


def test_축구_3way_는_셋을_다_넣어야_한다():
    """🔴 **이 계약이 오탐을 막는다.** 둘만 넣으면 축구 99.4% 가 폐기된다."""
    assert impossible_set([2.30, 3.10]) is True          # 둘만 = 0.757 → 불가능 판정
    assert impossible_set([2.30, 3.40, 3.10]) is False   # 무승부까지 = 1.052


def test_한쪽만으로는_판정하지_않는다():
    """🔴 모르면 버리지 않는다 — 조용한 폐기는 조용한 오염만큼 위험하다."""
    assert impossible_set([1.90]) is False
    assert impossible_set([]) is False
    assert impossible_set([None, 1.90]) is False


def test_쓰레기_값에_터지지_않는다():
    for bad in ([0, 2.0], [1.0, 2.0], ["x", 2.0], [-1, 2.0], [None, None]):
        assert impossible_set(bad) is False, bad


def test_원본은_margin_이다():
    """🔴 사본 금지 — 오버라운드를 여기서 다시 짜지 않았다."""
    import inspect

    assert "margin(" in inspect.getsource(impossible_set)
    assert abs(margin(2.08, 2.20) - (-0.0648)) < 1e-3


# ── 적재 게이트 ─────────────────────────────────────────────────────

_ROWS = [
    {"book": "b1", "market": "h2h", "line": None, "side": "Hanwha", "odds": 2.08},
    {"book": "b1", "market": "h2h", "line": None, "side": "Lotte", "odds": 2.20},
    {"book": "b2", "market": "h2h", "line": None, "side": "Hanwha", "odds": 2.08},
    {"book": "b2", "market": "h2h", "line": None, "side": "Lotte", "odds": 1.71},
]


def test_불가능한_묶음만_버린다():
    """🔴 묶음은 (북·마켓·라인)이다. 한 북이 깨졌다고 다른 북을 버리지 않는다."""
    from app.collectors.odds_free import screen_rows

    kept, dropped = screen_rows(_ROWS)
    assert [r["book"] for r in kept] == ["b2", "b2"]
    assert len(dropped) == 2 and all(r["book"] == "b1" for r in dropped)


def test_라인이_다르면_다른_묶음이다():
    """⚠️ 토탈 9.5 와 8.5 를 섞어 재면 마진이 엉뚱해진다."""
    from app.collectors.odds_free import screen_rows

    rows = [{"book": "b", "market": "totals", "line": 9.5, "side": "Over", "odds": 1.90},
            {"book": "b", "market": "totals", "line": 9.5, "side": "Under", "odds": 1.95},
            {"book": "b", "market": "totals", "line": 8.5, "side": "Over", "odds": 2.60},
            {"book": "b", "market": "totals", "line": 8.5, "side": "Under", "odds": 2.70}]
    kept, dropped = screen_rows(rows)
    assert len(kept) == 2 and len(dropped) == 2
    assert {r["line"] for r in kept} == {9.5}


def test_한쪽만_온_묶음은_남긴다():
    from app.collectors.odds_free import screen_rows

    rows = [{"book": "b", "market": "h2h", "line": None, "side": "A", "odds": 1.90}]
    kept, dropped = screen_rows(rows)
    assert kept == rows and dropped == []


def test_빈_입력에_터지지_않는다():
    from app.collectors.odds_free import screen_rows

    assert screen_rows([]) == ([], [])
    assert screen_rows(None) == ([], [])


# ── 배선 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_적재가_거른_뒤에_넣는다():
    """🔴 배선의 끝 — 거르기만 만들고 안 이으면 `margin()` 과 같은 신세가 된다."""
    from app.collectors import odds_free as OF

    seen = []

    class _P:
        async def execute(self, sql, *a):
            seen.append(a)
        async def fetch(self, *a, **k):
            return []
        async def fetchrow(self, *a, **k):
            return None

    n = await OF.store_rows(_P(), 7, _ROWS, "test")
    assert n == 2, f"불가능한 행을 걸렀어야 한다: {n}"
    assert all(a[4] != 2.20 and a[5] != 2.20 for a in seen), seen


def test_유료_경로도_같은_문을_지난다():
    """⚠️ 적재 지점이 둘이다(`odds.py`·`odds_free.py`). 한 곳만 막으면 샌다."""
    import inspect

    from app.collectors import odds as OD

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(OD.snapshot_odds).splitlines())
    assert "screen_rows" in src, "유료 경로가 검사를 안 지난다"
