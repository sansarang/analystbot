"""[v1.4 STEP 13] 운영 경로 전환 계약 — **두 경로가 동시에 카드를 내지 않는다.**

🔴 지시문 STEP 13: 스위치가 true 면 기존 발송은 **반드시 skip** 한다.
   동시에 나가면 실패다 — 사용자는 같은 경기 카드를 두 장 받는다.
🔴 **기본은 꺼짐**이다. 켜기 전 24h 기존 동작을 관측한다(지시문 §7).
🔴 되돌림은 스위치 하나다 — 코드를 되돌릴 필요가 없다.
"""
from __future__ import annotations

import pytest

from app.engine import pregame_push as PP


class _Redis:
    def __init__(self):
        self.store: dict = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, **kw):
        self.store[k] = v

    async def incr(self, k):
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    async def expire(self, k, s):
        return True

    async def hincrby(self, k, f, n=1):
        self.store.setdefault(k, {})
        self.store[k][f] = int(self.store[k].get(f, 0)) + n
        return self.store[k][f]


def _row(**kw):
    from datetime import UTC, datetime, timedelta

    return dict({"id": 1, "sport": "kbo",
                 "starts_at": datetime.now(UTC) + timedelta(minutes=40)}, **kw)


def test_스위치는_기본_꺼짐이다():
    """🔴 배포해도 무해해야 한다 — 켜는 것은 사람이 한다."""
    from app.config import get_settings

    assert get_settings().pipeline_v14 is False


@pytest.mark.asyncio
async def test_스위치가_켜지면_기존_발송이_비킨다(monkeypatch):
    from app import config as C

    class _S:
        pipeline_v14 = True

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    got = await PP.send_game_prediction(_Redis(), _row(), "2026-09-18")
    assert got == "skipped"


@pytest.mark.asyncio
async def test_사유를_남기고_비킨다(monkeypatch):
    """🔴 조용한 0 금지 — "왜 안 나갔나"가 집계에 남아야 한다."""
    from app import config as C
    from app.engine import dispatch_stats as ds

    reasons: list = []

    class _S:
        pipeline_v14 = True

    async def _rec(redis, sport, date, reason):
        reasons.append(reason)

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    monkeypatch.setattr(ds, "record", _rec)
    await PP.send_game_prediction(_Redis(), _row(), "2026-09-18")
    assert reasons == ["pipeline_v14"], reasons


@pytest.mark.asyncio
async def test_스위치가_꺼지면_종전대로_간다(monkeypatch):
    """🔴 반대 위험 — 꺼진 상태에서 동작이 바뀌면 되돌림이 불가능해진다.

    ⚠️ 종전 경로의 **첫 관문**은 `SPORTS` 다. 스위치가 꺼져 있으면 그 관문까지
       가야 한다 — `pipeline_v14` 사유로 빠지면 안 된다.
    """
    from app import config as C
    from app.engine import dispatch_stats as ds

    reasons: list = []

    class _S:
        pipeline_v14 = False

    async def _rec(redis, sport, date, reason):
        reasons.append(reason)

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    monkeypatch.setattr(ds, "record", _rec)
    await PP.send_game_prediction(_Redis(), _row(sport="없는종목"), "2026-09-18")
    assert reasons == ["not_supported"], reasons


def test_배타_가드가_SPORTS_관문보다_앞에_있다():
    """🔴 뒤에 두면 `SPORTS` 에 없는 종목이 먼저 걸러져 스위치가 안 듣는다."""
    import inspect

    src = inspect.getsource(PP.send_game_prediction)
    code = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert code.index("pipeline_v14") < code.index("sport not in SPORTS")
