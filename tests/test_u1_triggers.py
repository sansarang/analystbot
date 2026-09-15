"""U1 — 트리거 13종 · 창 ±30h · ingest_gap.

🔴 왜 이 파일이 있나: J1·K리그1·ACL 이 **18일간 0건**이었는데 아무도 몰랐다
   (P2-0 — 배당 차단기가 2026-08-27 에 내려간 뒤 09-14 까지). 매 실행 로그는
   "축구 일정 소스 실패" 한 줄뿐이었고 "경기가 없다"와 구분되지 않았다.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import odds_move as M
from app.engine import triggers as T

KO = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def test_트리거는_13종이다():
    assert len(T.ALL_KINDS) == 13, sorted(T.ALL_KINDS)
    assert len(T.KINDS) == 5 and len(T.ACTIONS) == 8
    assert set(T.KINDS) & set(T.ACTIONS) == set(), "이름이 겹친다"
    rows = T.plan(KO)
    assert len(rows) == 13
    assert {r["kind"] for r in rows} == set(T.ALL_KINDS)


def test_킥오프_NULL이면_0행():
    assert T.plan(None) == []


@pytest.mark.parametrize("kind,off", [
    ("model", timedelta(hours=-24)), ("recheck", timedelta(hours=-3)),
    ("lineup_poll", timedelta(minutes=-90)), ("rejudge", timedelta(minutes=-60)),
    ("card", timedelta(minutes=-30)), ("satellite_stop", timedelta(minutes=-10)),
    ("kickoff", timedelta(0)), ("result", timedelta(hours=3)),
])
def test_행동_트리거_시각(kind, off):
    row = next(r for r in T.plan(KO) if r["kind"] == kind)
    assert row["due_at"] == KO + off


# ── 🔴 반대 위험: 행동 kind 가 snap_tag 로 새면 이동 분석이 죽는다

def test_KINDS는_BASELINE_ORDER의_부분집합이다():
    assert set(T.KINDS) <= set(M.BASELINE_ORDER)


def test_행동_kind는_BASELINE_ORDER에_없다():
    """있으면 안 된다 — snap_tag 가 되어선 안 되는 이름이다."""
    assert set(T.ACTIONS) & set(M.BASELINE_ORDER) == set()


def test_is_snapshot이_스냅샷만_참이다():
    for k in T.KINDS:
        assert T.is_snapshot(k) is True, k
    for k in T.ACTIONS:
        assert T.is_snapshot(k) is False, k
    assert T.is_snapshot(None) is False and T.is_snapshot("없는것") is False


def test_이름표는_스냅샷_종류만_붙인다():
    """🔴 `_triggers_tick` 이 kind 를 그대로 snap_tag 에 넣는다.
    행동 kind 가 새면 record_move 의 order.index() 가 ValueError 로 터진다."""
    from app import scheduler as SC

    src = inspect.getsource(SC._triggers_tick)
    i = src.index("_TRIGGER_TAG_SQL")
    before = src[:i]
    assert "T.is_snapshot(" in before, "가드 없이 이름표를 붙인다"


def test_창이_전후_30시간이다():
    from app import scheduler as SC

    src = inspect.getsource(SC._triggers_tick)
    assert "now - timedelta(hours=30)" in src
    assert "now + timedelta(hours=30)" in src
    assert "now - timedelta(hours=6)" not in src


# ── ingest_gap

def test_ingest_gap은_차이가_0이면_조용하다():
    """🔴 반대 위험 — 오탐은 감시를 무디게 만든다(실사고 2026-09-05)."""
    assert T.ingest_gap({"J1 리그": 5}, {"J1 리그": 5}) == []
    assert T.ingest_gap({}, {}) == []
    assert T.ingest_gap_note([]) == ""
    # DB 가 더 많은 것은 경고하지 않는다 — 다른 소스가 넣었을 수 있다
    assert T.ingest_gap({"EPL": 3}, {"EPL": 7}) == []


def test_ingest_gap이_리그별로_센다():
    gaps = T.ingest_gap({"J1 리그": 5, "K리그1": 3, "EPL": 2},
                        {"J1 리그": 0, "K리그1": 3, "EPL": 2})
    assert [g["league"] for g in gaps] == ["J1 리그"]
    assert gaps[0] == {"league": "J1 리그", "src_n": 5, "db_n": 0, "missing": 5}
    assert "J1 리그 소스5/DB0(−5)" in T.ingest_gap_note(gaps)


def test_ingest_gap이_18일_상황을_잡는다():
    """실측 재현 — 소스엔 있고 DB 는 0."""
    gaps = T.ingest_gap({"J1 리그": 10, "K리그1": 6, "ACL엘리트": 8},
                        {})
    assert len(gaps) == 3
    assert [g["missing"] for g in gaps] == [10, 8, 6]   # 큰 것부터


def test_ingest_gap이_배선돼_있다():
    """🔴 함수만 만들고 안 부르면 영원히 조용하다."""
    from app import pipeline as PL

    src = inspect.getsource(PL._load_soccer_fixtures)
    assert "ingest_gap(" in src and "_src_counts" in src


def test_종류가_늘면_기존_경기에도_붙는다():
    """🔴 실측 2026-09-15: ACTIONS 8종을 넣었는데 game=8205 는 5행 그대로였다.
    계획 SQL 이 `kind='close'` 하나를 보초로 써서, 그게 있으면 경기를 통째로
    건너뛰었다. 트리거 **개수**를 함께 봐야 한다."""
    from app import scheduler as SC

    sql = SC._TRIGGER_PLAN_SQL
    assert "count(*)" in sql and "COALESCE(t.n, 0) < $3" in sql, sql
    # 킥오프 변경 조건은 그대로 남아 있어야 한다
    assert "close_due IS DISTINCT FROM g.starts_at" in sql

    src = inspect.getsource(SC._triggers_tick)
    assert "len(T.ALL_KINDS)" in src, "종류 수를 손으로 적었다(사본 금지)"
    assert "13" not in src.split("_TRIGGER_PLAN_SQL")[1][:300]
