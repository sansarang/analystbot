"""[BT-9] 백테스트 하네스 — **거짓말하지 않는지 먼저 잠근다.**

사용자 2026-09-23: "9월달에 우리가 경기가 시작안했다는 가정하에...바뀐코드의
승률을 전수 검사할려고 하니"

🔴 **이 도구의 위험은 결과가 틀리는 것이 아니라 "좋게 틀리는" 것이다.**
   오늘 자료로 9월을 예측하면 미래를 보고 맞히고, 그 좋은 숫자를 믿고 코드를
   고치면 운영이 망가진다. 그래서 계약이 세 가지를 잠근다:
     ① as-of 조회 — 킥오프 이후 자료를 안 읽는다
     ② DB 쓰기 차단 — `analysis_runs` 를 오염시키지 않는다
     ③ 흐름을 베끼지 않는다 — `run_game` 을 그대로 부른다
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect

import pytest

from tools import backtest_sep as BT

KICK = dt.datetime(2026, 9, 23, 9, 30, tzinfo=dt.UTC)


# ── ① 누수 차단 ─────────────────────────────────────────────────────

def test_모든_조회가_킥오프_이전만_본다():
    """🔴 **이 계약이 이 도구의 생명이다.** SQL 에 시점 조건이 없으면 미래가
    샌다 — 그러면 결과가 좋게 나오고 그 숫자가 거짓말이 된다."""
    for name in ("_ODDS_SQL", "_APPS_SQL", "_USUAL_SQL"):
        sql = getattr(BT, name)
        assert "<" in sql and ("captured_at" in sql or "starts_at" in sql), \
            f"{name} 에 시점 조건이 없다"
    # 배당: 킥오프 이후 스냅샷을 못 본다
    assert "o.captured_at <= $2" in BT._ODDS_SQL
    # 출전·평소: 그 경기 **이전** 경기만 (등호 없음 — 그 경기 자신도 제외)
    assert "g.starts_at < $3" in BT._APPS_SQL
    assert "g.starts_at < $3" in BT._USUAL_SQL


def test_elo_를_그_경기_직전까지로_만든다():
    """🔴 `team_elo.compute` 를 그대로 쓰면 감쇠 기준이 **전체 마지막 경기**가
    되어 미래가 샌다. `fit_elo.ratings_asof` 가 그것을 막는 원본이다."""
    src = inspect.getsource(BT._elo_asof)
    assert "ratings_asof" in src, "누수 차단 함수를 안 쓴다"
    assert "starts_at < $2" in src, "그 경기 이후 경기를 본다"
    assert "team_elo.compute" not in src and "compute(" not in src


def test_주전_판정을_다시_짓지_않았다():
    """🔴 사본 금지 — `lineup_diff.usual_from` 이 원본이다."""
    src = inspect.getsource(BT._usual_of)
    assert "usual_from" in src
    assert "regulars" not in src, "주전 판정을 여기서 다시 짰다"


def test_9월_뉴스는_지어내지_않는다():
    """⚠️ Redis TTL 26h 라 9월 기사 자료가 **없다.** 빈 목록을 넘겨
    ⑤가 `미실행` 으로 적게 한다 — 있는 척하지 않는다."""
    src = inspect.getsource(BT.build_ctx)
    assert '"changes": []' in src


# ── ② DB 쓰기 차단 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_쓰기를_삼키고_읽기는_통과한다():
    """🔴 `run_game` 은 노드마다 `analysis_runs` 에 INSERT 한다. 백테스트가
    그것을 쓰면 운영 지표(단계별 통과율·CLV)가 통째로 오염된다."""
    class _P:
        def __init__(self):
            self.reads = 0
            self.writes = 0

        async def fetch(self, *a, **k):
            self.reads += 1
            return ["row"]

        async def fetchrow(self, *a, **k):
            self.reads += 1
            return {"x": 1}

        async def fetchval(self, *a, **k):
            self.reads += 1
            return 7

        async def execute(self, *a, **k):
            self.writes += 1

    real = _P()
    ro = BT._ReadOnly(real)
    assert await ro.fetch("SELECT 1") == ["row"]
    assert await ro.fetchrow("SELECT 1") == {"x": 1}
    assert await ro.fetchval("SELECT 1") == 7
    await ro.execute("INSERT INTO analysis_runs ...")
    await ro.execute("DELETE FROM games")
    assert real.writes == 0, "🔴 쓰기가 DB 까지 갔다"
    assert real.reads == 3
    assert ro.blocked == 2


def test_하네스가_읽기전용_풀을_쓴다():
    """🔴 배선의 끝 — 만들어 놓고 안 쓰면 소용없다."""
    src = inspect.getsource(BT.build_ctx)
    assert "_ReadOnly(pool)" in src
    assert "Ctx(pool=ro" in src, "진짜 풀을 그대로 넘긴다"


# ── ③ 흐름을 베끼지 않는다 ──────────────────────────────────────────

def test_흐름을_다시_짜지_않았다():
    """🔴 흐름을 베끼면 흐름이 아니라 하네스를 테스트하게 된다."""
    src = inspect.getsource(BT.run_one)
    assert "run_game" in src
    tree = ast.parse(inspect.getsource(BT))
    called = {getattr(c.func, "attr", "") or getattr(c.func, "id", "")
              for c in ast.walk(tree) if isinstance(c, ast.Call)}
    for node in ("n01_prior", "n03_gate", "n05_evidence", "n08_pcode",
                 "n11_value"):
        assert node not in called, f"노드를 직접 불렀다: {node}"


def test_대상_조회가_결과와_배당을_요구한다():
    """⚠️ 결과가 없으면 채점을 못 하고, 킥오프 前 배당이 없으면 ②가 빈다."""
    sql = BT._GAMES_SQL
    assert "status = 'final'" in sql
    assert "home_score IS NOT NULL" in sql
    assert "o.captured_at <= games.starts_at" in sql


# ── 집계 ────────────────────────────────────────────────────────────

def test_지표가_맞다():
    """⚠️ 집계가 틀리면 결론이 통째로 틀린다 — 손으로 검산한다."""
    m = BT._metrics([(1.0, 1.0), (0.0, 0.0)])
    assert m["brier"] == 0.0 and m["hit"] == 1.0 and m["auc"] == 1.0
    m2 = BT._metrics([(0.5, 1.0), (0.5, 0.0)])
    assert m2["brier"] == 0.25
    assert m2["auc"] == 0.5, "동점 처리가 틀렸다"
    assert BT._metrics([])["n"] == 0
    # 한쪽 결과만 있으면 AUC 는 정의되지 않는다 — 지어내지 않는다
    assert BT._metrics([(0.6, 1.0)])["auc"] is None


def test_보고가_세_확률을_나란히_잰다():
    """🔴 기준선은 **시장**이다. 우리 것만 재면 좋아 보일 뿐이다."""
    src = inspect.getsource(BT.summarize)
    for k in ("우리 ⑧", "시장 ②", "사전값 ①"):
        assert k in src
