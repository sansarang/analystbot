"""PA-1 계약 — `adjust.attach` 는 문자열 `starts_at` 을 열어서 쓴다.

🔴 PART A 실측(2026-09-16, MLB 2경기)에서 경기당 4건이 같은 원인으로 죽었다.
   파이프라인이 넣는 `starts_at` 은 ISO **문자열**이고, asyncpg 의
   TIMESTAMPTZ 파라미터는 `datetime` 을 요구한다.
⚠️ CLAUDE.md 가 이미 적어둔 종류다(ODP-2·LH-2 와 같은 원인).
"""
import pathlib
from datetime import date, datetime, timezone

import pytest

from app.collectors.lineups import STATUS_CONFIRMED
from app.engine import adjust

ISO = "2026-09-16T01:38:00+00:00"


class _Pool:
    """받은 인자를 기록한다. 🔴 asyncpg 처럼 **타입을 검사한다** —
    검사하지 않으면 문자열이 지나가도 테스트가 초록으로 남는다."""

    def __init__(self):
        self.args = []

    async def fetch(self, sql, *args):
        self.args.extend(args)
        for a in args:
            if isinstance(a, str) and "T" in a and a[:2] == "20":
                raise TypeError("invalid input for query argument: "
                                f"{a!r} (expected datetime, got 'str')")
        return []

    async def fetchval(self, sql, *args):
        self.args.extend(args)
        return None


def _jg(starts):
    return {"game_id": 1, "sport": "mlb", "home": "A", "away": "B",
            "starts_at": starts, "lineup_status": STATUS_CONFIRMED,
            "research": {"today_nine": {"home": ["X"], "away": ["Y"]}}}


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    ISO,                       # 파이프라인이 실제로 넣는 모양
    "2026-09-16T01:38:00Z",    # Z 접미사
    "2026-09-16T01:38:00",     # tz 없음
])
async def test_문자열_starts_at도_datetime으로_간다(raw):
    pool = _Pool()
    await adjust.attach(_jg(raw), pool)
    sent = [a for a in pool.args if isinstance(a, datetime)]
    assert sent, f"{raw!r} 이 datetime 으로 안 갔다"
    assert all(a.tzinfo is not None for a in sent), "tz 없는 값이 갔다"
    assert not [a for a in pool.args
                if isinstance(a, str) and "T" in a and a[:2] == "20"], \
        "문자열이 그대로 쿼리로 갔다"


@pytest.mark.asyncio
async def test_이미_datetime이면_그대로():
    """🔴 반대 위험 — 스케줄러 경로는 asyncpg 가 datetime 을 준다.
    거기서 값이 바뀌면 안 된다."""
    dt = datetime.fromisoformat(ISO)
    pool = _Pool()
    await adjust.attach(_jg(dt), pool)
    assert dt in pool.args


@pytest.mark.asyncio
async def test_None이면_미계산으로_남는다():
    """🔴 반대 위험 — 시간을 모르는 경기를 '지금'으로 채우면 과거 경기를
    미래로 읽는다."""
    jg = _jg(None)
    await adjust.attach(jg, _Pool())
    assert jg.get("bullpen_b2b") is None
    assert "bullpen_b2b" in (jg.get("adj_missing") or [])


@pytest.mark.asyncio
async def test_못읽는_문자열도_미계산이다():
    jg = _jg("어제")
    await adjust.attach(jg, _Pool())
    assert jg.get("bullpen_b2b") is None


@pytest.mark.asyncio
async def test_불펜_today는_date다():
    """`count_b2b` 는 `date` 로 뺄셈한다 — datetime 을 주면 하루가 어긋난다."""
    seen = {}
    real = adjust.count_b2b

    def spy(apps, today):
        seen["today"] = today
        return real(apps, today)

    adjust.count_b2b = spy
    try:
        await adjust.attach(_jg(ISO), _Pool())
    finally:
        adjust.count_b2b = real
    if "today" in seen:                      # 행이 없으면 안 불릴 수 있다
        assert isinstance(seen["today"], date)
        assert not isinstance(seen["today"], datetime)


def test_파서를_다시_만들지_않았다():
    """🔴 사본 금지 — `starter_recent._aware` 가 원본이다."""
    src = pathlib.Path("app/engine/adjust.py").read_text(encoding="utf-8")
    assert "_aware" in src, "정규화가 없다"
    assert "fromisoformat" not in src, "파서를 여기서 다시 적었다"


def test_aware가_원본과_같은_것을_돌려준다():
    from app.engine.starter_recent import _aware

    got = _aware(ISO)
    assert got == datetime(2026, 9, 16, 1, 38, tzinfo=timezone.utc)
    assert _aware(None) is None and _aware("어제") is None
