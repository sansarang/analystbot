"""FOT-2 — FotMob 호출부 (수집 맨 앞 + T-60 재호출). 사용자 지시.

🔴 오늘 밤 완료 조건이 이것 위에 선다: Torino-Roma T-60(00:30 KST)에서
   `lineupType` 이 confirmed 로 바뀌면 예상 XI 와 **코드가** 대조해
   bench_notable·surprise_in 을 채우고 **두 시점 모두 원장에** 남긴다.
"""
import ast
import inspect
from datetime import UTC, datetime

import pytest

from app import scheduler
from app.collectors import satellite as SAT
from app.engine import game_trace as GT


def _calls(fn, name):
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "attr", "") == name
                 or getattr(n.func, "id", "") == name)]


def test_수집은_어댑터보다_먼저_붙인다():
    """층1(부상표·피드)보다 앞이어야 어댑터가 그 값을 본다."""
    src = inspect.getsource(SAT.gather)
    assert src.index("fotmob.attach") < src.index("await adapter("), src[:200]


def test_T60_트리거가_라인업을_다시_받는다():
    assert _calls(scheduler._triggers_tick, "_lineup_recheck"), "T-60 재호출이 없다"
    assert _calls(scheduler._lineup_recheck, "attach"), "재호출이 FotMob 을 안 부른다"
    src = inspect.getsource(scheduler._triggers_tick)
    # 🔴 분(分)을 코드에 적지 않는다 — 시점 이름은 triggers.KINDS 가 원본이다.
    assert '"lineup"' in src and "60" not in src.split("_lineup_recheck")[0][-200:]


class _Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *args):
        self.rows.append(args)
        return "INSERT 1"


@pytest.mark.asyncio
async def test_못_받아도_원장에_남긴다(monkeypatch):
    """🔴 "안 바뀌었다"와 "못 받았다"를 갈라야 내일 다시 재지 않는다."""
    async def _attach(jg, **k):
        return {}

    monkeypatch.setattr("app.collectors.fotmob.attach", _attach)
    pool = _Pool()
    row = {"game_id": 7433, "sport": "soccer", "home": "Torino FC",
           "away": "AS Roma", "starts_at": datetime(2026, 9, 14, 16, 30, tzinfo=UTC)}

    await scheduler._lineup_recheck(pool, row, datetime.now(UTC))

    assert len(pool.rows) == 1
    gid, sport, _d, stage, summary, ref = pool.rows[0]
    assert gid == 7433 and sport == "soccer" and stage == GT.COLLECT
    assert "받지 못했다" in summary and '"lineup_type": null' in ref


@pytest.mark.asyncio
async def test_confirmed_면_diff_를_원장에_남긴다(monkeypatch):
    async def _attach(jg, **k):
        return {"lineup_type": "confirmed",
                "home": {"starters": [{"id": 1, "name": "Perri"}]},
                "away": {"starters": [{"id": 3, "name": "Dybala"}]},
                "missing": [],
                "diff": {"away": {"bench_notable": ["Soulé"],
                                  "surprise_in": ["Dybala"]}}}

    monkeypatch.setattr("app.collectors.fotmob.attach", _attach)
    pool = _Pool()
    row = {"game_id": 7433, "sport": "soccer", "home": "Torino FC",
           "away": "AS Roma", "starts_at": datetime(2026, 9, 14, 16, 30, tzinfo=UTC)}

    await scheduler._lineup_recheck(pool, row, datetime.now(UTC))

    _, _, _, stage, summary, ref = pool.rows[0]
    assert stage in GT.STAGES, "새 stage 를 만들지 않는다"
    assert "confirmed" in summary and "surprise_in" in ref
    assert "Dybala" in ref and "away_xi" in ref, "두 시점 값이 원장에 남아야 한다"
