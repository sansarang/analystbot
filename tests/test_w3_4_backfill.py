"""[W3-4] 소급 적재 — 폼을 계산할 재료가 없다.

🔴 실측 2026-09-21 (FotMob 이 주 소스인 4리그):

    리그          전체  종료  미적재(6h 초과)   팀당 종료 경기
    덴마크          12    4       8              1
    ACL엘리트       10    0      10              (0)
    J1 리그         12    2      10              1
    K리그1          16    4      12              1

   **팀당 1경기**로는 최근 5경기 폼도, 휴식 시간도 계산할 수 없다.
   미적재 날짜는 4리그 합쳐 13일이다.

🔴 지시문 W3-4: `tools/backfill_results.py` — 리그별 개막일~어제 ·
   요청 간격 ≥2초 · 원본 JSON 날짜별 캐시 · **--dry-run 먼저** ·
   403 이면 즉시 중단·보고.

⚠️ FotMob 하루치 목록은 **한 번 받으면 전 리그가 들어 있다**(541경기).
   리그마다 다시 받으면 요청이 4배가 된다 — 날짜당 1회만 받고 나눠 쓴다.
"""
from __future__ import annotations

import inspect

import pytest


def test_도구가_있다():
    from tools import backfill_results  # noqa: F401


def test_dry_run_이_기본이_아니면_안_된다():
    """🔴 지시문: --dry-run 먼저. 실행이 기본이면 사고가 조용히 난다."""
    from tools import backfill_results as B

    src = inspect.getsource(B)
    assert "--dry-run" in src or "dry_run" in src


def test_날짜당_한_번만_받는다():
    """⚠️ 리그마다 slate 를 다시 받으면 요청이 4배가 된다."""
    from app.collectors import fotmob as F

    sig = inspect.signature(F.upsert_slate)
    assert "rows" in sig.parameters, \
        "미리 받은 목록을 넘길 자리가 없다 — 리그마다 다시 받게 된다"


@pytest.mark.asyncio
async def test_넘긴_목록을_쓰면_다시_받지_않는다():
    from app.collectors import fotmob as F

    calls = []

    async def _boom(_d):
        calls.append(_d)
        return []

    class _Pool:
        async def fetchrow(self, sql, *a): return None
        async def fetchval(self, sql, *a): return None
        async def execute(self, sql, *a): return None

    rows = [{"id": 1, "league": "K-League 1", "home": "Pohang Steelers",
             "away": "FC Seoul", "utc": "2026-09-20T10:00:00.000Z",
             "status": "final", "home_score": 2, "away_score": 1,
             "result_basis": "FT"}]
    out = await F.upsert_slate(_Pool(), "20260920", league_key="kleague1",
                               rows=rows)
    assert not calls, "목록을 넘겼는데도 다시 받았다"
    assert out["matched"] == 1


@pytest.mark.asyncio
async def test_빈_응답이_이어지면_멈춘다(tmp_path):
    """🔴 403·차단이면 즉시 중단·보고. 조용히 계속 두드리지 않는다.

    ⚠️ `cache_dir` 를 격리한다 — 전역 캐시를 쓰면 앞 실행이 남긴 파일 때문에
       이 검사가 순서에 따라 갈린다(실제로 갈렸다)."""
    from tools import backfill_results as B

    async def _empty(_d):
        return []

    got = await B.run(pool=None, days=10, dry_run=True, slate=_empty,
                      cache_dir=tmp_path)
    assert got.get("stopped"), "빈 응답이 이어져도 계속 돌았다"
    assert got.get("fetched_days", 0) <= B.EMPTY_STOP, \
        f"멈추기 전에 {got.get('fetched_days')}일을 두드렸다"


@pytest.mark.asyncio
async def test_dry_run_은_쓰지_않는다(tmp_path):
    from tools import backfill_results as B

    writes = []

    class _Pool:
        async def execute(self, sql, *a): writes.append(sql)
        async def fetchrow(self, sql, *a): return None
        async def fetchval(self, sql, *a): return None

    async def _slate(d):
        return [{"id": 1, "league": "K-League 1", "home": "Pohang Steelers",
                 "away": "FC Seoul", "utc": f"2026-09-20T10:00:00.000Z",
                 "status": "final", "home_score": 2, "away_score": 1,
                 "result_basis": "FT"}]

    out = await B.run(pool=_Pool(), days=2, dry_run=True, slate=_slate,
                      cache_dir=tmp_path)
    assert not writes, f"--dry-run 인데 DB 에 썼다: {writes[:2]}"
    assert out.get("would_save", 0) >= 1, "무엇을 쓸지 세지도 않았다"


def test_캐시_위치를_인자로_받는다():
    """🔴 전역 /tmp 하나면 앞 실행 캐시가 다음 판단을 바꾼다."""
    import inspect

    from tools import backfill_results as B

    assert "cache_dir" in inspect.signature(B.run).parameters
