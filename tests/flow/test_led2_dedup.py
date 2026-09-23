"""[LED-2] 결정 원장이 **경기당 32행**으로 부풀었다. 가격도 비었다.

사용자 2026-09-23: "전부다 순서대로 수정해라"

🔴 실측 2026-09-23 16:15 운영:
```
flow_v14  740행 / 23경기 = 경기당 32.2행
bot_v14   369행 / 369경기 = 경기당  1.0행
game=1774  57행 · 서로 다른 확률 4 · 서로 다른 결정시각 57
충돌 키: (engine, game_id, market, line, side, ts_decided)
```
`ts_decided = now()` 가 충돌 키에 있어 **흐름이 15분마다 돌 때마다 새 행**이
생긴다. 57행 중 실제로 판단이 바뀐 것은 **4번**뿐이다.

🔴 부풀면 성적 통계가 거짓이 된다 — 한 경기가 32번 세어지면 그 경기의 결과가
   32배 가중된다. 실제로 "8건 전부 loss" 로 보였던 것이 **한 경기의 중복**
   이었다(탬파베이@양키스 1경기 × 8행).

🔴 그리고 `price_at_decision` 이 NULL 이라 **ROI 를 영영 못 낸다** — INSERT 가
   그 자리에 NULL 을 박고 있었다. ②가 배당을 갖고 있는데 안 실었다.

⚠️ 판단이 **바뀐** 기록은 남겨야 한다(라인 이동 학습의 재료다). 지우는 것은
   같은 쪽·같은 확률의 **되풀이**뿐이다.
"""
from __future__ import annotations

import pytest

from app.flow import record as R


class _S:
    run_id = "r1"
    game_id = "7"
    sport = "baseball"
    league = "KBO"
    stop_reason = None
    home = "두산"
    away = "KIA"
    pick_side = "home"
    n02_market = {"p": {"home": 0.62, "draw": None, "away": 0.38},
                  "odds": {"home": 1.70, "away": 2.20}}
    n03_gate = {"gate": "동의"}
    n07_adjust = []
    n08_pcode = {"p_code_pick": 0.6522}
    n09_conf = {"grade": "B"}


class _Ctx:
    def __init__(self, pool):
        self.pool = pool


class _Pool:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserts = []
        self.queries = []

    async def fetchrow(self, sql, *a):
        self.queries.append((sql, a))
        return self.existing

    async def execute(self, sql, *a):
        self.inserts.append((sql, a))


def test_가격을_싣는다():
    """🔴 `price_at_decision` 이 없으면 ROI 를 영영 못 낸다."""
    assert R.price_of(_S()) == 1.70


def test_원정_픽이면_원정_배당이다():
    """🔴 [SIDE-1 2026-09-23] 방향은 `pick_side` 가 정한다 — 확률이 아니다."""
    s = _S()
    s.pick_side = "away"
    s.n08_pcode = {"p_code_pick": 0.3294}
    assert R.price_of(s) == 2.20


def test_배당이_없으면_None():
    """🔴 지어내지 않는다."""
    s = _S()
    s.n02_market = {"p": {"home": 0.62}, "odds": {}}
    assert R.price_of(s) is None


@pytest.mark.asyncio
async def test_같은_판단이_두_번_안_들어간다():
    """🔴 이 단위의 전부 — 15분마다 같은 행이 쌓이던 자리다."""
    pool = _Pool(existing={"id": 1})          # 같은 쪽·같은 확률이 이미 있다
    ok = await R.record(_S(), _Ctx(pool))
    assert ok is False, "되풀이를 또 넣었다"
    assert not pool.inserts, pool.inserts


@pytest.mark.asyncio
async def test_판단이_바뀌면_새_행이다():
    """🔴 **지우는 것은 되풀이뿐이다.** 라인 이동 학습의 재료는 남긴다."""
    pool = _Pool(existing=None)               # 같은 확률의 행이 없다
    ok = await R.record(_S(), _Ctx(pool))
    assert ok is True
    assert pool.inserts, "판단이 바뀌었는데 안 남겼다"


@pytest.mark.asyncio
async def test_중복_검사가_확률까지_본다():
    """⚠️ 쪽만 보면 확률이 바뀌어도 안 남는다 — 그건 정보를 버리는 것이다."""
    pool = _Pool(existing=None)
    await R.record(_S(), _Ctx(pool))
    sql, args = pool.queries[0]
    assert "p_model" in sql, sql
    assert any(abs(float(x) - 0.6522) < 1e-9 for x in args
               if isinstance(x, (int, float))), args


@pytest.mark.asyncio
async def test_조회가_실패해도_흐름을_안_죽인다():
    class _Boom(_Pool):
        async def fetchrow(self, sql, *a):
            raise RuntimeError("DB")

    assert await R.record(_S(), _Ctx(_Boom())) is False
