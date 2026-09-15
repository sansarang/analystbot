"""SNAP-1 — 진짜 개장가와 '우리가 처음 본 값'을 구분한다.

🔴 실측 2026-09-15:
     snap_tag 분포(48,310행) — (NULL) 48,119(99.6%) · pre 53 · close 41 ·
                               lineup 41 · late 41 · open 15
     ACL 7경기 × 24행 = 168행 전부 태그 0
     배당이 18일간 차단돼(P2-0) 해제 직후 받은 첫 값은 T-4.7h ~ T-13.0h 였다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import odds_free as OF
from app.engine import odds_move as M
from app.engine.triggers import KINDS

KO = datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc)


def test_open_proxy가_이름표에_있다():
    assert "open_proxy" in M.BASELINE_ORDER


def test_이동_순서표에_open_proxy가_open_뒤다():
    """🔴 반대 위험 — 순서에 없으면 record_move 의 order.index 가 터진다."""
    o = list(M.BASELINE_ORDER)
    assert o.index("open") < o.index("open_proxy") < o.index("pre")
    # 원본(triggers.KINDS)의 5개가 전부 순서표에 있어야 한다 — 사본 금지
    assert set(KINDS) <= set(M.BASELINE_ORDER)


@pytest.mark.parametrize("hours,want", [
    (30, "open"), (24.1, "open"), (24, "open"),
    (23.9, "open_proxy"), (4.7, "open_proxy"), (0, "open_proxy"),
])
def test_T24h_이전_첫값은_open_이후는_open_proxy(hours, want):
    assert M.open_tag(KO, KO - timedelta(hours=hours)) == want


def test_킥오프나_시각을_모르면_open이라_부르지_않는다():
    """🔴 모르면 낮은 쪽이 안전하다 — 개장가라고 우기지 않는다."""
    assert M.open_tag(None, KO) == "open_proxy"
    assert M.open_tag(KO, None) == "open_proxy"


def test_open_기준이_triggers를_원본으로_쓴다():
    """사본 금지 — T-24h 숫자를 odds_move 에 적지 않았다."""
    import inspect

    src = inspect.getsource(M.open_tag)
    assert "KINDS" in src
    assert "24" not in src, "T-24h 를 손으로 적었다"


# ── 🔴 반대 위험: 트리거가 붙인 태그를 덮지 않는다

def test_트리거가_붙인_태그를_덮지_않는다():
    sql = OF._TAG_OPEN_SQL
    assert "snap_tag IS NULL" in sql, "이미 태그가 있는 행을 건드린다"
    assert "NOT EXISTS" in sql and "'open', 'open_proxy'" in sql, \
        "open 계열이 이미 있는데 또 붙인다"


def test_소급_태그는_멱등이다():
    """같은 SQL 을 두 번 돌려도 두 번째는 0행이어야 한다 — NOT EXISTS 가 막는다."""
    sql = OF._TAG_OPEN_SQL
    assert sql.count("NOT EXISTS") == 1
    assert "min(captured_at)" in sql, "가장 이른 행이 아니라 아무 행에 붙인다"


@pytest.mark.asyncio
async def test_적재하면_이름표가_붙는다(monkeypatch):
    calls = []

    class _Pool:
        async def execute(self, sql, *a):
            calls.append(("exec", sql.strip()[:20], a))

        async def fetchrow(self, sql, *a):
            return {"ko": KO, "first_seen": KO - timedelta(hours=4.7), "already": 0}

    rows = [{"book": "oddsportal-avg", "market": "h2h", "side": "A", "odds": 1.5}]
    n = await OF.store_rows(_Pool(), 1, rows, "oddsportal")
    assert n == 1
    tagged = [c for c in calls if "UPDATE" in c[1] or "WITH" in c[1]]
    assert tagged, "적재만 하고 이름표를 안 붙였다"
    assert tagged[-1][2][2] == "open_proxy", tagged[-1]


@pytest.mark.asyncio
async def test_이미_태그가_있으면_아무것도_안_한다():
    class _Pool:
        def __init__(self):
            self.execs = []

        async def execute(self, sql, *a):
            self.execs.append(sql)

        async def fetchrow(self, sql, *a):
            return {"ko": KO, "first_seen": KO, "already": 1}

    p = _Pool()
    assert await OF.tag_open(p, 1, "oddsportal") is None
    assert p.execs == []


# ═══════════════ U0-b — 묶음 태깅 · NULL 제외

def test_첫값은_같은_묶음_전체에_붙는다():
    """🔴 실측 2026-09-15: g=8199 open_proxy **1행** / None 35행.
    홈·무·원정은 행마다 따로 INSERT 돼 captured_at 이 마이크로초 단위로 다르다.
    `= min(captured_at)` 으로 잡으면 셋 중 하나만 붙는다."""
    sql = OF._TAG_OPEN_SQL
    assert "= (SELECT min(captured_at)" not in sql, "여전히 한 행만 잡는다"
    assert "< (SELECT min(captured_at)" in sql
    assert "interval '1 second'" in sql


def test_창은_1초다_다음_스냅샷을_삼키지_않는다():
    """🔴 반대 위험 — 창이 넓으면 다음 회차까지 open 으로 이름 붙는다."""
    import re

    m = re.search(r"interval '(\d+) (second|minute|hour)", OF._TAG_OPEN_SQL)
    assert m, OF._TAG_OPEN_SQL
    assert (m.group(1), m.group(2)) == ("1", "second"), m.groups()
    # 2차 방어: open 계열이 이미 있으면 아예 안 붙는다
    assert "NOT EXISTS" in OF._TAG_OPEN_SQL


def test_NULL_행은_이동계산에서_빠진다():
    """⚠️ 규칙 정정(사용자 2026-09-15): NULL 0% 가 목표가 아니다.
    경기당 open 계열 1묶음 + 5시점 묶음이고 나머지 NULL 은 이름 없는 중간값이다.
    대신 그 NULL 이 이동·CLV 계산에 **섞이면 안 된다**."""
    import inspect

    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL)
    i = src.index("SELECT o.provider, o.snap_tag")
    assert "snap_tag IS NOT NULL" in src[i:i + 400], "NULL 행이 섞인다"
    # baseline 도 태그가 있는 것부터 고른다
    assert "BASELINE_ORDER" in inspect.getsource(M.baseline)
