"""W-STALE-GAME — 소스가 끝내 확정하지 않은 경기의 계약.

실측 2026-09-07 (운영 DB, 24시간 문턱):
  kbo 7건 (최장 1531h·63.8일) · npb 4건 (643h) · soccer 16건 (354h) = **27건**
  전부 `scheduled`. `reconcile_stale_games` 는 매일 집어가며 `{'kbo':0,'npb':0}`.
  원인은 둘 다 소스 쪽 — KBO 공식 소스가 10일 뒤에도 `scheduled`,
  NPB `2021039384` 는 야후 원문이 `試合中止`(취소).
  KBO `cancelled` 6건은 정상이라 경보 대상이 **아니다**.

🔴 이 감시의 핵심 계약은 **서 있는 더미가 아니라 늘어난 것만 울린다**는 것이다.
   27건이 남아 있는 한 상시 경보는 15분마다 영원히 울리고, 내일 슬레이트에서
   정작 봐야 할 `W-SEND-PENDING`·`W-CARD-LATE` 를 덮는다.
"""

import re

import pytest

from app.watchdog import (STALE_ALERT_MULT, STALE_SEEN_KEY,
                          check_stale_games)

WATCH = open("app/watchdog.py", encoding="utf-8").read()


def _segment() -> str:
    i = WATCH.index("async def check_stale_games")
    return WATCH[i:WATCH.index("\ndef ", i + 10)]


class _Pool:
    def __init__(self, rows=(), exc=None):
        self.rows, self.exc, self.calls = list(rows), exc, []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if self.exc:
            raise self.exc
        return self.rows


class _Redis:
    """`get`/`set` 만 쓰는 최소 목. `store=None` 이면 키가 없는 첫 실행이다."""

    def __init__(self, store=None, exc=None):
        self.store, self.exc, self.sets = store, exc, []

    async def get(self, key):
        if self.exc:
            raise self.exc
        return self.store

    async def set(self, key, val, ex=None):
        if self.exc:
            raise self.exc
        self.sets.append((key, val, ex))
        self.store = val


def _g(gid, sport="kbo", hrs=234, away="A팀", home="B팀"):
    return {"id": gid, "sport": sport, "home": home, "away": away, "hrs": hrs}


# ═══════════════ ① 증가분만 운다 — 이 감시의 존재 이유

@pytest.mark.asyncio
async def test_첫_실행은_기준선만_심고_울리지_않는다():
    """🔴 배포 직후 27건이 한꺼번에 터지는 것이야말로 이 설계가 막는 것이다."""
    pool = _Pool([_g(i) for i in range(1, 28)])
    redis = _Redis(store=None)
    assert await check_stale_games(pool, redis) == []
    assert redis.sets, "기준선을 기록하지 않으면 다음 회차에 27건이 터진다"
    assert redis.sets[0][0] == STALE_SEEN_KEY


@pytest.mark.asyncio
async def test_서_있는_더미는_다시_울리지_않는다():
    """등록부(evidence/OPEN.md #15)가 할 일을 사이렌에 시키지 않는다."""
    pool = _Pool([_g(1), _g(2), _g(3)])
    assert await check_stale_games(pool, _Redis(store="1,2,3")) == []


@pytest.mark.asyncio
async def test_새로_생긴_것만_울린다():
    pool = _Pool([_g(1), _g(2), _g(9, hrs=25, away="키움", home="두산")])
    out = await check_stale_games(pool, _Redis(store="1,2"))
    assert len(out) == 1
    code, target, detail = out[0]
    assert (code, target) == ("W-STALE-GAME", "KBO")
    assert "1건" in detail and "키움@두산" in detail
    assert "25시간" in detail


@pytest.mark.asyncio
async def test_종목별로_나눠_운다():
    """억제 키가 `code:target` 이라 종목을 섞으면 한쪽이 묻힌다."""
    pool = _Pool([_g(1, "kbo"), _g(2, "npb"), _g(3, "soccer")])
    out = await check_stale_games(pool, _Redis(store=""))
    assert [t for _, t, _ in out] == ["KBO", "NPB", "SOCCER"]


@pytest.mark.asyncio
async def test_해소된_경기는_상태에서_빠져_재발_시_다시_운다():
    """현재 집합으로 **덮어쓴다** — 합치면 해소된 경기가 영원히 남는다."""
    redis = _Redis(store="1,2,3")
    await check_stale_games(_Pool([_g(2)]), redis)
    assert redis.store == "2"
    # 1번이 다시 미확정이 되면 새 것으로 취급돼야 한다.
    out = await check_stale_games(_Pool([_g(1), _g(2)]), redis)
    assert len(out) == 1 and "1건" in out[0][2]


@pytest.mark.asyncio
async def test_미확정_경기가_없으면_침묵한다():
    assert await check_stale_games(_Pool([]), _Redis(store="1,2")) == []


# ═══════════════ ② 못 믿을 때는 울리지 않는다

@pytest.mark.asyncio
async def test_상태를_못_읽으면_점검을_건너뛴다():
    """기준선 없이 울리면 그게 곧 27건 폭주다."""
    pool = _Pool([_g(i) for i in range(1, 28)])
    assert await check_stale_games(pool, _Redis(exc=RuntimeError("redis down"))) == []


@pytest.mark.asyncio
async def test_조회가_실패해도_워치독을_죽이지_않는다():
    assert await check_stale_games(_Pool(exc=RuntimeError("boom")), _Redis("")) == []


@pytest.mark.asyncio
async def test_pool_이나_redis_가_없으면_조용히_넘어간다():
    assert await check_stale_games(None, _Redis("")) == []
    assert await check_stale_games(_Pool([_g(1)]), None) == []


# ═══════════════ ③ 반대 위험 — 정상 데이터를 태우지 않는가

@pytest.mark.asyncio
async def test_취소_계열은_질의에서_제외된다():
    """🔴 실측: 취소 미제외 시 kbo 53건 → 제외 시 7건. 오탐 46건을 막는다."""
    pool = _Pool([])
    await check_stale_games(pool, _Redis(""))
    sql = pool.calls[0][0]
    where = sql[sql.index("WHERE"):sql.index("ORDER BY")]
    for 정상 in ("'cancelled'", "'postponed'", "'suspended'"):
        assert 정상 in where, f"{정상} 를 빼지 않으면 정상 데이터가 경보가 된다"
    assert "'final'" in where


@pytest.mark.asyncio
async def test_정합_잡이_한_사이클_돌_여유를_준다():
    """문턱이 `STALE_AFTER_HOURS` 보다 커야 한다 — 정합 잡이 돌기 전에
    울리면 '아직 안 돌았다'를 결함으로 보고하는 셈이다."""
    from app.collectors.finals import STALE_AFTER_HOURS

    pool = _Pool([])
    await check_stale_games(pool, _Redis(""))
    hours = pool.calls[0][1][0]
    assert hours == STALE_AFTER_HOURS * STALE_ALERT_MULT
    assert hours > STALE_AFTER_HOURS
    assert hours >= 24, "정합 잡은 하루 한 번(13:00 KST) 돈다"


# ═══════════════ ④ 사본 금지 · 다른 눈

def test_문턱을_베껴_적지_않고_원본을_참조한다():
    """실사고 2026-09-02: 워치독 오탐 4건이 전부 '코드 값을 베낀 것' 이었다."""
    seg = _segment()
    assert "from app.collectors.finals import STALE_AFTER_HOURS" in seg
    assert not re.search(r"hours\s*=\s*\d", seg), \
        "문턱을 숫자로 적었다 — 원본이 바뀌면 따라가지 않는다"


def test_앞으로_6시간만_보는_점검과_다른_눈이다():
    """`W-GAME-INVISIBLE` 은 `starts_at > now()` 를 본다. 이 점검은 **지난**
    경기를 봐야 한다 — 같은 눈으로 보면 그때 놓친 것을 또 놓친다."""
    seg = _segment()
    assert "starts_at < now() - make_interval" in seg
    assert "starts_at > now()" not in seg


# ═══════════════ ⑤ 배선 — 등록되지 않은 점검은 없는 것과 같다

def test_run_checks_에_등록돼_있다():
    assert '("stale_games", check_stale_games(pool, redis))' in WATCH


def test_경보_코드가_등록돼_있다():
    """코드가 없으면 알림이 '점검 필요' 로 뭉개져 grep 이 안 된다."""
    from app.alerts import WATCHDOG_CODES

    assert "W-STALE-GAME" in WATCHDOG_CODES
