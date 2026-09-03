"""[감시 C3] 일일 요약 감시 줄 + 계측 카운터.

🔴 이 줄이 지켜야 할 성질은 두 가지다.
   ① 재료가 없으면 **나오지 않는다** — 매일 "0/0/0/0"을 보내면 휴면과 정상을
      구분할 수 없다.
   ② **카드가 아니다** — 분석 카드 텍스트는 감시가 켜지든 꺼지든 동일하다.
"""
import pytest

from app.engine import daily_summary as ds
from app.engine import monitor_metrics as mm


class FakeRedis:
    def __init__(self):
        self.h = {}

    async def hincrby(self, key, field, n):
        self.h.setdefault(key, {})[field] = self.h.setdefault(key, {}).get(field, 0) + n

    async def expire(self, key, ttl):
        return True

    async def hgetall(self, key):
        return {k: str(v) for k, v in self.h.get(key, {}).items()}


class FakePool:
    """fetchrow/fetchval 을 쿼리 문자열로 분기하는 최소 스텁."""

    def __init__(self, audit=None, review=None, panel=None, anomaly=0):
        self.audit, self.review, self.panel, self.anomaly = (
            audit, review, panel, anomaly)

    async def fetchrow(self, sql, *args):
        if "judgement_audit" in sql:
            return self.audit
        if "judge_review" in sql:
            return self.review
        if "shadow_panel" in sql:
            return self.panel
        return None

    async def fetchval(self, sql, *args):
        return self.anomaly


@pytest.mark.asyncio
async def test_no_materials_no_line():
    """감시가 휴면이면 줄이 아예 없다 — 빈 숫자를 매일 보내지 않는다."""
    out = await ds.monitor_lines(FakePool(), FakeRedis(), ("kbo",), "2026-09-03")
    assert out == []


@pytest.mark.asyncio
async def test_line_shape_matches_spec():
    r = FakeRedis()
    await mm.note_materials(r, "kbo", "2026-09-03", True)
    await mm.note_materials(r, "kbo", "2026-09-03", True)
    await mm.note_materials(r, "kbo", "2026-09-03", False)
    await mm.note_lineup_regress(r, "kbo", "2026-09-03")
    pool = FakePool(
        audit={"v": 41, "d": 6, "nf": 3, "m": 1, "n": 5},
        review={"k": 4, "j": 2, "n": 5},
        panel={"m": 1, "n": 5},
        anomaly=17)
    line = (await ds.monitor_lines(pool, r, ("kbo",), "2026-09-03"))[0]
    assert line.startswith("🔍 감시: ")
    assert "사실 41/6/3/1" in line
    assert "검사역 이의 4(유효 2)" in line
    assert "패널 편차>8%p 1건" in line
    assert "역행 1건" in line
    assert "자료8 주입 67%" in line          # 2/3
    assert "타순 길이 이상 17건" in line


@pytest.mark.asyncio
async def test_partial_materials_only_show_what_exists():
    """L2·L3 가 휴면(키 없음)이어도 L1·계측은 나온다."""
    r = FakeRedis()
    await mm.note_materials(r, "npb", "2026-09-03", True)
    pool = FakePool(audit={"v": 9, "d": 0, "nf": 0, "m": 0, "n": 1},
                    review={"k": 0, "j": 0, "n": 0},
                    panel={"m": 0, "n": 0})
    line = (await ds.monitor_lines(pool, r, ("npb",), "2026-09-03"))[0]
    assert "사실 9/0/0/0" in line
    assert "검사역" not in line and "패널" not in line


@pytest.mark.asyncio
async def test_threshold_is_read_from_config_not_hardcoded():
    """임계는 config 가 원본이다 — 줄에 8을 손으로 적지 않았다(사본 금지)."""
    from pathlib import Path

    from app.config import get_settings

    src = Path("app/engine/daily_summary.py").read_text(encoding="utf-8")
    assert "shadow_diverge_pp" in src
    r, pool = FakeRedis(), FakePool(panel={"m": 2, "n": 3})
    line = (await ds.monitor_lines(pool, r, ("kbo",), "2026-09-03"))[0]
    assert f"편차>{get_settings().shadow_diverge_pp * 100:.0f}%p" in line


@pytest.mark.asyncio
async def test_db_failure_does_not_break_the_summary():
    """감시 집계가 죽어도 요약 카드는 나간다 — 감시는 발송을 막지 않는다."""
    class Broken(FakePool):
        async def fetchrow(self, sql, *args):
            raise RuntimeError("boom")

        async def fetchval(self, sql, *args):
            raise RuntimeError("boom")

    assert await ds.monitor_lines(Broken(), FakeRedis(), ("kbo",), "2026-09-03") == []


@pytest.mark.asyncio
async def test_regress_counts_only_backwards():
    """정상 전이는 세지 않는다 — 셀 것은 '확정이라 해놓고 되돌아간' 것뿐이다."""
    import re
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    m = re.search(r'if r\["lineup_status"\] == "confirmed" and '
                  r'status != "confirmed":', src)
    assert m, "역행 조건이 폴러에 없다"


@pytest.mark.asyncio
async def test_counter_failure_is_silent():
    """계측 실패가 판정을 막지 않는다."""
    class Dead:
        async def hincrby(self, *a):
            raise RuntimeError("down")

        async def expire(self, *a):
            raise RuntimeError("down")

        async def hgetall(self, *a):
            raise RuntimeError("down")

    await mm.note_materials(Dead(), "kbo", "2026-09-03", True)   # 예외 없이 통과
    assert await mm.summary(Dead(), "kbo", "2026-09-03") == {
        "mat_total": 0, "mat_with8": 0, "regress": 0}


@pytest.mark.asyncio
async def test_none_redis_is_dormant():
    await mm.note_lineup_regress(None, "kbo", "2026-09-03")
    assert (await mm.summary(None, "kbo", "2026-09-03"))["mat_total"] == 0
