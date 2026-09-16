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
    # 🔴 [CLV-3] 부호를 바로잡았다 — 마감보다 좋은 값에 잡으면 **양수**다.
    assert PL.clv_pp(2.00, 2.50) == pytest.approx(-10.0, abs=0.01)   # 50% → 40%
    assert PL.clv_pp(2.00, 1.50) == pytest.approx(16.67, abs=0.01)
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
        # [CLV-3] 방향은 정해지지만 스냅샷이 없는 경우다
        async def fetchrow(self, sql, *a):
            return {"favored": "home", "p_home": 0.6, "predicted_side": None,
                    "home": "H", "away": "A"}
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
    # ⚠️ [CLV-2] 트랜잭션 안이라 **커넥션**을 넘긴다(풀이면 교착한다)
    # 🔴 [PA-19 2026-09-16] CLV 호출이 `_record_side_effects` 안으로 한 단계
    #    들어갔다 — 부수 기록을 한 곳에 모았기 때문이다(사본 금지).
    #    뜻은 그대로다: 판정 시각 배당을 **커넥션으로** 기록한다.
    a += inspect.getsource(PL._record_side_effects)
    assert 'record_clv(conn, game_id=game_id, at=clv_at)' in a, a[-400:]
    assert 'at="closing"' in g, g[:600]


def test_채점_결과에_배당을_쓰지_않는다():
    """🔴 §4-1 — 저장 전용이다. hit 판정에 배당이 끼면 안 된다."""
    g = inspect.getsource(PL.grade_pending)
    i = g.index("winner =")
    assert "odds" not in g[i:i + 600], g[i:i + 600]


def test_clv를_갱신되는_값으로_계산한다():
    """🔴 실측 2026-09-13: MLB 8건 전부 두 칸이 찼는데 clv 가 NULL 이었다.
    `UPDATE` 안의 `CASE` 는 **갱신 전 값**을 읽는다 — 지금 쓰는 칸은 `$2` 다."""
    v, c = PL._CLV_SAVE["verdict"], PL._CLV_SAVE["closing"]
    assert "1.0/$2" in v and "odds_closing IS NOT NULL" in v, v
    assert "1.0/$2" in c and "odds_at_verdict IS NOT NULL" in c, c
    # ⚠️ 실측 2026-09-13: 캐스트가 없으면 AmbiguousParameterError 로 죽는다
    for q in (v, c):
        assert q.count("$2::double precision") >= 2, q
    # 자기 자신을 컬럼명으로 읽으면 안 된다
    assert "1.0/odds_at_verdict" not in v, v
    assert "1.0/odds_closing" not in c, c


@pytest.mark.asyncio
async def test_열린_커넥션을_그대로_쓴다():
    """🔴 **실측 2026-09-13**: `record_analysis` 가 `conn.transaction()` 안에서
    `record_clv(pool, …)` 를 불러 **교착**했다(EXIT=124 타임아웃). 바깥
    트랜잭션이 잠근 같은 행을 새 커넥션이 UPDATE 하려 했기 때문이다.

    ⚠️ 커넥션을 받으면 **새로 얻지 않는다.**
    """
    class _Conn:
        def __init__(self): self.n = 0
        async def fetchrow(self, *a):
            return {"favored": "home", "p_home": 0.6, "predicted_side": None,
                    "home": "H", "away": "A"}
        async def fetchval(self, *a): return 2.0
        async def execute(self, *a): self.n += 1

    c = _Conn()
    out = await PL.record_clv(c, game_id=1, at="verdict")
    assert out == 2.0 and c.n == 1


def test_기록부가_커넥션을_넘긴다():
    """🔴 배선이 없으면 교착이 그대로 남는다."""
    import inspect

    src = inspect.getsource(PL.record_analysis)
    # 🔴 [PA-19 2026-09-16] CLV 호출이 `_record_side_effects` 안으로 한 단계
    #    들어갔다 — 부수 기록을 한 곳에 모았기 때문이다(사본 금지).
    #    뜻은 그대로다: 판정 시각 배당을 **커넥션으로** 기록한다.
    src += inspect.getsource(PL._record_side_effects)
    assert "record_clv(conn" in src, "pool 을 그대로 넘기고 있다"


# ── [CLV-3] 부호와 사이드 (2026-09-13)

def test_마감보다_좋은_값에_잡으면_양수다():
    """🔴 종전 부호가 뒤집혀 있었다.

    2.00 에 잡아 1.50 에 닫혔으면 **시장을 크게 이긴 것**이다(우리가 더 좋은
    값을 먹었다). 종전 식은 그걸 −16.67 로 찍었고, 머리말은 "양수면 좋은 값에
    잡았다"고 적혀 있었다 — **식과 말이 반대**였다. 수익을 재는 유일한
    지표라 부호가 뒤집히면 결론이 통째로 뒤집힌다.
    """
    from app.engine import pick_ledger as PL

    assert PL.clv_pp(2.00, 1.50) == pytest.approx(+16.67, abs=0.01)   # 이겼다
    assert PL.clv_pp(2.00, 2.50) == pytest.approx(-10.00, abs=0.01)   # 졌다
    assert PL.clv_pp(2.00, 2.00) == pytest.approx(0.0, abs=1e-9)


def test_SQL도_같은_부호를_쓴다():
    """🔴 파이썬과 SQL 이 다른 부호를 쓰면 원장과 집계가 반대를 말한다."""
    from app.engine import pick_ledger as PL

    for k in ("verdict", "closing"):
        sql = PL._CLV_SAVE[k]
        # (마감 확률 − 판정시각 확률) 순서여야 한다
        assert "odds_closing" in sql and "odds_at_verdict" in sql
    v, c = PL._CLV_SAVE["verdict"], PL._CLV_SAVE["closing"]
    assert "(1.0/odds_closing) - (1.0/$2" in v.replace("\n", " "), v
    assert "(1.0/$2::double precision) - (1.0/odds_at_verdict)" in c.replace("\n", " "), c


def test_스냅샷은_우리가_고른_쪽만_본다():
    """🔴 한 경기에 홈·원정 스냅샷이 각 38행씩 있다(실측 2026-09-13 game 1741).

    side 를 안 가리면 **마지막에 들어온 아무 쪽**을 집는다. 판정 시각엔 홈,
    마감엔 원정을 집으면 그 차이는 아무 의미가 없다.
    """
    from app.engine import pick_ledger as PL

    import inspect

    s = PL._CLV_SNAP.replace("\n", " ")
    assert "o.side = $3" in s, s
    # 🔴 방향은 **채점과 같은 헬퍼**가 정한다 — 컬럼만 읽으면 안 된다.
    #    실측: `predicted_side` 컬럼이 오늘 9행 전부 NULL 인데 채점은 폴백으로 돈다.
    src = inspect.getsource(PL.record_clv)
    assert "predicted_side(" in src, src
    assert "_CLV_PICK" in src, src


@pytest.mark.asyncio
async def test_고른_쪽을_모르면_기록하지_않는다():
    """0 이나 반대쪽 값으로 채우지 않는다 — 무의미한 값이 NULL 보다 나쁘다."""
    from app.engine import pick_ledger as PL

    calls = []

    class _Conn:
        async def fetchrow(self, *a, **k):
            # 우세도 확률도 없다 → 방향을 못 정한다
            return {"favored": "박빙", "p_home": None, "predicted_side": None,
                    "home": "H", "away": "A"}
        async def fetchval(self, *a, **k):
            raise AssertionError("방향을 모르는데 스냅샷을 조회했다")
        async def execute(self, *a, **k):
            calls.append(a)

    out = await PL.record_clv(_Conn(), game_id=1, at="verdict")
    assert out is None and calls == []


@pytest.mark.asyncio
async def test_우세가_원정이면_원정_배당을_집는다():
    """🔴 반대쪽을 집으면 CLV 가 통째로 무의미해진다."""
    from app.engine import pick_ledger as PL

    seen = {}

    class _Conn:
        async def fetchrow(self, *a, **k):
            return {"favored": "away", "p_home": 0.62, "predicted_side": None,
                    "home": "Doosan Bears", "away": "NC Dinos"}
        async def fetchval(self, sql, *a):
            seen["team"] = a[2]
            return 2.13
        async def execute(self, *a, **k):
            seen["wrote"] = a

    out = await PL.record_clv(_Conn(), game_id=1741, at="verdict")
    assert seen["team"] == "NC Dinos", seen
    assert out == 2.13
