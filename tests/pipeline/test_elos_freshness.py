"""[ELO-S] 캐시가 낡았으면 다시 만든다 — 하루 낡은 사전값이 ①을 망쳤다.

사용자 2026-09-23: "1,2 하고 npb.kbo 재 예측해라"

🔴 실측이 가리킨 자리:
```
elo:kbo:2026-09-23   팀당 53~56경기  TTL 3h   ← 오늘 판정이 쓴 것
elo:kbo:2026-09-24   팀당 68~76경기  TTL 21h  ← 프리페치가 하루 먼저 만든다
DB sport='kbo' 종료   팀당 93경기
```
키가 날짜별이고 프리페치가 **내일 것을 오늘** 만든다. 그러면 다음 날
`ensure_elo` 가 "있으면 쓴다"로 통과시켜 **어제 자료**로 판정한다.

⚠️ 종전 계약(`test_ensure_elo_는_있으면_다시_계산하지_않는다`)이 바로 그
   동작을 잠그고 있었다. 그 계약의 취지는 "**경기마다** 36배 재계산 금지"이지
   "낡아도 쓴다"가 아니다 — 슬레이트당 1회 재계산은 조회 1회 + 메모리 replay 다.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.flow import bridge as B


class _R:
    def __init__(self, raw=None):
        self.raw = raw

    async def get(self, k):
        return self.raw


def _cache(n_per_team: int, teams: int = 10) -> str:
    import json
    return json.dumps({f"T{i}": {"레이팅": 1500.0, "리그평균대비": 0.0,
                                 "경기수": n_per_team} for i in range(teams)},
                      ensure_ascii=False)


class _Pool:
    def __init__(self, n):
        self.n = n
        self.asked = []

    async def fetchrow(self, sql, *a):
        self.asked.append((sql, a))
        return {"n": self.n}


# ── 신선도 ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_낡은_캐시는_다시_만든다():
    """🔴 이 단위의 핵심. 캐시 54경기 · DB 93경기 → 다시 만든다."""
    calls = []

    async def _refresh(pool, redis, sport, date, **k):
        calls.append((sport, date))
        return {"T0": {"레이팅": 1500.0, "경기수": 93}}

    # 팀당 108 출전 = 540경기... 가 아니라 팀당 경기수 108/2 → 아래로 맞춘다
    got = await B.ensure_elo(_Pool(468), _R(_cache(54)), "kbo", "2026-09-23",
                             refresh=_refresh)
    assert got is True
    assert calls == [("kbo", "2026-09-23")], "낡았는데 다시 안 만들었다"


@pytest.mark.asyncio
async def test_최신이면_다시_만들지_않는다():
    """⚠️ 반대 위험 — 매번 재계산하면 종전 계약의 취지를 깬다."""
    calls = []

    async def _refresh(*a, **k):
        calls.append(a)
        return {}

    # 팀당 경기수 94 × 10팀 / 2 = 470 ≥ DB 468
    got = await B.ensure_elo(_Pool(468), _R(_cache(94)), "kbo", "2026-09-23",
                             refresh=_refresh)
    assert got is True
    assert calls == [], "최신인데 다시 만들었다"


@pytest.mark.asyncio
async def test_풀이_없으면_종전대로_있으면_쓴다():
    """🔴 드라이런·테스트에는 DB 가 없다 — 대조할 수 없으면 종전 동작이다."""
    calls = []

    async def _refresh(*a, **k):
        calls.append(a)
        return {}

    assert await B.ensure_elo(None, _R(_cache(54)), "kbo", "d",
                              refresh=_refresh) is True
    assert calls == [], "풀도 없는데 재계산을 시도했다"
    assert await B.ensure_elo(None, _R(None), "kbo", "d",
                              refresh=_refresh) is False


@pytest.mark.asyncio
async def test_다시_만들다_실패해도_있던_값을_버리지_않는다():
    """🔴 낡아도 없느니 낫다 — 실패가 ①을 None 으로 만들면 전건 보드고정이다."""
    async def _refresh(*a, **k):
        return {}

    assert await B.ensure_elo(_Pool(468), _R(_cache(54)), "kbo", "d",
                              refresh=_refresh) is True


@pytest.mark.asyncio
async def test_대조에_실패하면_있던_값을_쓴다():
    """⚠️ 개수 조회가 터져도 슬레이트를 멈추지 않는다."""
    class _Boom:
        async def fetchrow(self, *a):
            raise RuntimeError("DB 없음")

    calls = []

    async def _refresh(*a, **k):
        calls.append(a)
        return {}

    assert await B.ensure_elo(_Boom(), _R(_cache(54)), "kbo", "d",
                              refresh=_refresh) is True
    assert calls == [], "대조 실패를 낡음으로 읽었다"


@pytest.mark.asyncio
async def test_캐시가_없으면_종전대로_만든다():
    calls = []

    async def _refresh(pool, redis, sport, date, **k):
        calls.append((sport, date))
        return {"T0": {"레이팅": 1500.0}}

    assert await B.ensure_elo(_Pool(468), _R(None), "mlb", "2026-09-19",
                              refresh=_refresh) is True
    assert calls == [("mlb", "2026-09-19")]


# ── 경기수 해석 ─────────────────────────────────────────────────────

def test_경기수_합의_절반이_경기_수다():
    """🔴 `경기수` 는 **팀당 출전 수**다. 절반을 안 하면 항상 최신으로 읽혀
    이 수정이 통째로 무력해진다."""
    assert B._cached_matches({"A": {"경기수": 10}, "B": {"경기수": 10}}) == 10
    assert B._cached_matches({}) == 0
    assert B._cached_matches(None) == 0
    assert B._cached_matches({"A": {"경기수": "x"}, "B": {"경기수": None}}) == 0
    assert B._cached_matches({"A": 1500.0}) == 0


# ── 사본 잠금 ───────────────────────────────────────────────────────

def _where(sql: str) -> set[str]:
    """WHERE 절의 조건들을 공백·개행 무시하고 집합으로."""
    seg = sql[sql.index("WHERE") + 5:]
    for stop in ("ORDER BY", "GROUP BY", "LIMIT"):
        if stop in seg:
            seg = seg[:seg.index(stop)]
    return {re.sub(r"\s+", " ", c).strip() for c in seg.split("AND") if c.strip()}


def test_개수_조회가_레이팅_조회와_같은_조건이다():
    """🔴 사본 금지의 대안 — 원본이 상수가 아니라 못 읽어오니, 두 조건이
    **같다는 것**을 여기서 잠근다. 한쪽만 바뀌면 이 계약이 깨진다."""
    from app.models import team_elo as TE

    src = inspect.getsource(TE.refresh)
    i = src.index("SELECT home, away")
    ref = src[i:src.index('"""', i)]
    assert _where(ref) == _where(B._ELO_COUNT_SQL), (
        f"조건이 어긋났다\n  team_elo: {_where(ref)}\n  bridge  : {_where(B._ELO_COUNT_SQL)}")


def test_낡음을_조용히_넘기지_않는다():
    """⚠️ 조용한 재계산은 다음 세션이 원인을 못 찾는다."""
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(B.ensure_elo).splitlines())
    assert "logger.info" in src
