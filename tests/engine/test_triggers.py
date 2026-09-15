"""TRG-1 — 경기별 시점 트리거 (Part A).

⚠️ **Part A 사양을 받은 적이 없다.** 두 지시문이 참조하는 것에서 최소 사양을
   도출했다:
     · Part 1-B-1  스냅샷 5시점 — open T-24h · pre T-3h · lineup T-60m ·
                   late T-10m · close T+0
     · Part 1 허가 "Part A `game_triggers` 에 스냅샷 트리거 5행"
     · Part 4 7-3 "매 1분 due 트리거 실행(Part A)"
   그 이상은 만들지 않는다 — 사양 없는 기능을 지어내면 그것이 사본이다.

🔴 트리거는 **시각만 관리한다.** 무엇을 할지는 호출부가 정한다 — 여기에
   수집·검색·판정을 넣으면 트리거가 파이프라인이 된다.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import triggers as T


KO = datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)


# ── 계획

def test_열세_시점이다():
    """🔴 [U1 2026-09-15] 스냅샷 5 + 행동 8. 종전 5종에는 S4~S11 이 붙을
    시각이 없었다. ⚠️ 이름표는 여전히 `KINDS` 5종만 붙는다."""
    rows = T.plan(KO)
    assert len(rows) == 13
    assert {r["kind"] for r in rows} == set(T.ALL_KINDS)
    assert set(T.KINDS) < set(T.ALL_KINDS)


def test_시점_오프셋이_지시문_그대로다():
    got = {r["kind"]: r["due_at"] for r in T.plan(KO)}
    assert got["open"] == KO - timedelta(hours=24)
    assert got["pre"] == KO - timedelta(hours=3)
    assert got["lineup"] == KO - timedelta(minutes=60)
    assert got["late"] == KO - timedelta(minutes=10)
    assert got["close"] == KO


def test_킥오프가_없으면_계획이_없다():
    """🔴 시각을 지어내지 않는다."""
    assert T.plan(None) == []


def test_이미_지난_시점도_계획에_남긴다():
    """⚠️ 지난 시점을 빼면 '늦게 등록된 경기'가 open 을 영영 못 받는다.
       지났는지는 due 조회가 판단한다."""
    late = datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc)
    assert len(T.plan(late)) == 13


# ── 순서·중복

def test_시점은_시간순이다():
    rows = T.plan(KO)
    assert [r["due_at"] for r in rows] == sorted(r["due_at"] for r in rows)


def test_같은_경기에_같은_종류가_둘이_아니다():
    kinds = [r["kind"] for r in T.plan(KO)]
    assert len(kinds) == len(set(kinds))


# ── SQL 계약

def test_테이블이_스키마에_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS game_triggers" in s
    for col in ("game_id", "kind", "due_at", "fired_at", "attempts"):
        assert col in s


def test_같은_경기_같은_종류는_유일하다():
    """🔴 없으면 재등록할 때마다 트리거가 불어난다."""
    s = open("db/schema.sql", encoding="utf-8").read()
    i = s.index("CREATE TABLE IF NOT EXISTS game_triggers")
    blk = s[i:i + 1200]
    assert "UNIQUE" in blk and "game_id" in blk and "kind" in blk


def test_due_조회는_안_쏜_것만_본다():
    assert "fired_at IS NULL" in T.DUE_SQL
    assert "due_at <=" in T.DUE_SQL


def test_동시_실행_상한이_있다():
    """Part 4 7-3: 동시 실행 상한 3. 토요일 15:00 동시 킥오프 대비."""
    assert T.MAX_CONCURRENT == 3


def test_우선순위는_괴리_큰_순이다():
    rows = [{"game_id": 1, "gap_pp": 2.0}, {"game_id": 2, "gap_pp": -9.0},
            {"game_id": 3, "gap_pp": 5.0}, {"game_id": 4, "gap_pp": None}]
    assert [r["game_id"] for r in T.prioritize(rows)] == [2, 3, 1, 4]


# ── 격리

def test_트리거는_수집도_판정도_하지_않는다():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(T))
    mods = {a.name.split(".")[0]
            for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0]
             for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"__future__", "logging", "datetime"}, mods
