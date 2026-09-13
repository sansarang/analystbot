"""CLV-1 — 판정 시각 배당과 마감 배당을 남긴다. **저장만** 한다.

사용자 지시 2026-09-13(4단계): "판정의 값어치를 측정할 유일한 지표를 남긴다.
§4-1 '배당은 판정 입력 금지'는 그대로 — 여기서는 저장만 한다."

🔴 실측(운영 원장 is_final·채점 완료 178경기):
     판정 확률 AUC 0.5122 · 브라이어 0.2537 (50%로 찍는 것보다 나쁘다)
     시장 확률 AUC 0.6421 · 브라이어 0.2394   ← 유일하게 유의
   적중률만으로는 판정이 시장보다 나은지 알 수 없다. CLV 가 그것을 재는
   표준 지표인데 지금 그 칸이 없다.

⚠️ 기존 `odds`·`market_prob` 는 **한 시점의 값**이다(`_fill_market` 이 나중에
   채운다). 판정 시각과 마감 시각을 구분해 두 번 남겨야 차이를 계산할 수 있다.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import pick_ledger as PL

UTC = timezone.utc


def test_스키마에_세_칸이_있다():
    src = open("db/schema.sql", encoding="utf-8").read()
    for col in ("odds_at_verdict", "odds_closing", "clv"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


def test_배당이_판정_비교에_들어가지_않는다():
    """🔴 가장 큰 반대 위험 — 배당이 바뀔 때마다 재판정 행이 생기면 안 된다."""
    src = inspect.getsource(PL._same_judgement)
    for col in ("odds_at_verdict", "odds_closing", "clv"):
        assert col not in src, col


def test_판정_경로가_이_칸을_읽지_않는다():
    """🔴 §4-1 — 배당은 판정·폼·서술의 입력에 절대 넣지 않는다."""
    import pathlib

    hits = []
    for p in pathlib.Path("app").rglob("*.py"):
        if p.name == "pick_ledger.py":
            continue
        t = p.read_text(encoding="utf-8")
        if "odds_at_verdict" in t or "odds_closing" in t:
            hits.append(str(p))
    assert hits == [], hits


def test_확률_변환을_다시_만들지_않는다():
    """⚠️ 사본 금지 — 배당→확률 변환식이 두 곳에 있으면 한쪽만 바뀐다."""
    src = inspect.getsource(PL)
    assert src.count("def _implied_prob") <= 1


@pytest.mark.parametrize("odds,expect", [
    (2.00, 0.50), (1.50, 2 / 3), (4.00, 0.25), (None, None), (0, None), (-1, None),
])
def test_배당을_확률로_바꾼다(odds, expect):
    got = PL._implied_prob(odds)
    if expect is None:
        assert got is None
    else:
        assert abs(got - expect) < 1e-9, (odds, got)


def test_clv는_확률_퍼센트포인트_차이다():
    """판정 시각 2.00(50%) → 마감 1.50(66.7%) 이면 우리가 **불리해진** 것이다.
    부호 규약: clv = (판정시각 확률 − 마감 확률) × 100 %p.
    양수면 우리가 좋은 값에 잡았다는 뜻이다."""
    assert PL.clv_pp(2.00, 2.50) == pytest.approx(10.0, abs=0.01)   # 50% → 40%
    assert PL.clv_pp(2.00, 1.50) == pytest.approx(-16.67, abs=0.01)
    assert PL.clv_pp(None, 2.0) is None
    assert PL.clv_pp(2.0, None) is None


@pytest.mark.asyncio
async def test_킥오프_이전_마지막_스냅샷만_쓴다():
    """🔴 마감 배당이 킥오프 **후** 값이면 오염이다 — 경기가 시작된 뒤의 배당은
    결과를 반영한다."""
    # 조건은 SQL 상수에 있다 — 함수 본문이 아니라 그 자리를 본다
    assert "starts_at" in PL._CLV_SNAP, PL._CLV_SNAP
    assert "captured_at <=" in PL._CLV_SNAP, PL._CLV_SNAP
    assert "LEAST(" in PL._CLV_SNAP, "킥오프와 기준시각 중 이른 쪽을 써야 한다"
    assert "record_clv" in inspect.getsource(PL)


@pytest.mark.asyncio
async def test_배당이_없으면_NULL로_남긴다():
    """⚠️ 없는 것을 0 으로 채우지 않는다."""
    class _Conn:
        def __init__(self): self.saved = None
        async def fetchval(self, sql, *a): return None
        async def execute(self, sql, *a): self.saved = a

    class _Pool:
        def __init__(self): self.c = _Conn()
        def acquire(self):
            pool = self
            class _Ctx:
                async def __aenter__(self): return pool.c
                async def __aexit__(self, *a): return False
            return _Ctx()

    p = _Pool()
    out = await PL.record_clv(p, game_id=1, at="verdict")
    assert out is None, out
    assert p.c.saved is None, p.c.saved


def test_두_시점_모두_배선돼_있다():
    """🔴 함수만 만들고 안 부르면 원장은 영원히 NULL 이다."""
    a = inspect.getsource(PL.record_analysis)
    g = inspect.getsource(PL.grade_pending)
    assert 'record_clv(pool, game_id=row["game_id"], at="verdict")' in a, a[-400:]
    assert 'at="closing"' in g, g[:600]


def test_채점_결과에_배당을_쓰지_않는다():
    """🔴 §4-1 — 저장 전용이다. hit 판정에 배당이 끼면 안 된다."""
    g = inspect.getsource(PL.grade_pending)
    i = g.index("winner =")
    assert "odds" not in g[i:i + 600], g[i:i + 600]
