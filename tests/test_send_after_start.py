"""SND-1 — 판정이 오래 걸려도 **시작한 경기에는 카드가 안 나간다.**

🔴 실사고 2026-09-10: `아시아 판정 19:06 (소요 38분 18초)` 가 18:28 에 시작해
   19:06 에 끝났고, 그때 `09/10 18:30` 시작 KBO 경기 2건(KT@롯데·NC@KIA)의
   **1차 카드**가 나갔다 — 시작 36분 뒤다.

   잡이 머리에서 `now` 를 한 번 잡아 발송까지 들고 갔고, 그 사이
   `rejudge_after_lineup`(LLM)이 38분을 먹었다. 그래서 발송 직전
   `still_upcoming(starts_at, now)` 는 **38분 전의 시각**으로 판단했다.
   "그 카드는 정확해도 걸 수가 없다"는 마감선의 취지가 통째로 무너진다.

🔴 **반대 위험을 같이 잠근다.** 시계를 고치면서 정상 발송까지 막으면 그게
   더 나쁘다 — 잡이 빠를 때는 종전과 똑같이 나가야 한다.
"""

from datetime import UTC, datetime, timedelta

import pytest

import app.engine.pregame_push as pp

JOB_START = datetime(2026, 9, 10, 9, 28, tzinfo=UTC)      # 18:28 KST
GAME_AT = datetime(2026, 9, 10, 9, 30, tzinfo=UTC)        # 18:30 KST


class _Redis:
    async def get(self, key):
        return None

    async def set(self, *a, **k):
        return True


def _row():
    return {"id": 1730, "sport": "kbo", "home": "롯데 자이언츠",
            "away": "KT 위즈", "starts_at": GAME_AT, "lineup_status": "none",
            "home_pitcher": None, "away_pitcher": None}


@pytest.fixture
def stage(monkeypatch):
    """발송·강제판정을 목으로 갈고, 잡의 경과 시간을 손으로 돌린다."""
    import app.pipeline as pl
    import app.scheduler as sch

    tick = {"t": 0.0}
    # ⚠️ `raising=False` — 수정 전 코드에는 `_monotonic` 이 없다. 여기서
    #    AttributeError 로 죽으면 "심볼이 없다"로 실패하고, 정작 **결함
    #    자체를 겨눈 단언**(시작한 경기에 카드가 나간다)에 닿지 못한다.
    monkeypatch.setattr(pp, "_monotonic", lambda: tick["t"], raising=False)

    calls: list = []

    async def _send(redis, row, date_s, *, now=None):
        calls.append(now)
        # 실사고와 같은 순서: 첫 발송은 판정이 없어 실패한다.
        return "skipped" if len(calls) == 1 else "sent"

    monkeypatch.setattr(pp, "send_game_prediction", _send)
    monkeypatch.setattr(pl, "analysis_cache_ready", lambda *a, **k: True)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(pl, "ensure_analysis_cache", _noop)
    return sch, tick, calls


async def _run(sch, rows=None):
    return await sch.guarantee_first_cards(
        None, _Redis(), "kbo", "2026-09-10", rows or [_row()], JOB_START, {}, [])


# ═══════════════ ① 실사고 그대로

@pytest.mark.asyncio
async def test_강제_판정이_38분_걸리면_카드가_안_나간다(stage, monkeypatch):
    """🔴 이 결함의 본체. 실측된 소요 그대로 38분을 돌린다."""
    import app.pipeline as pl

    sch, tick, calls = stage

    async def _slow(row, ctx):
        tick["t"] += 38 * 60          # 재판정 = LLM 호출
        return True

    monkeypatch.setattr(pl, "rejudge_after_lineup", _slow)
    n = await _run(sch)
    assert n == 0, "시작한 경기에 카드가 나갔다"
    assert len(calls) == 1, "강제 판정 뒤에도 발송을 시도했다"


@pytest.mark.asyncio
async def test_두_번째_발송이_받는_시각은_실제_호출_시점이다(stage, monkeypatch):
    """느리지만 아직 시작 전이면 — 나가되 **그 시각으로** 나가야 한다."""
    import app.pipeline as pl

    sch, tick, calls = stage

    async def _slow(row, ctx):
        tick["t"] += 60               # 1분 — 아직 18:29, 시작 전이다
        return True

    monkeypatch.setattr(pl, "rejudge_after_lineup", _slow)
    n = await _run(sch)
    assert n == 1, "아직 시작 전인데 막았다"
    assert calls[1] == JOB_START + timedelta(seconds=60), calls[1]


# ═══════════════ ② 반대 위험 — 정상 발송을 막지 않는다

@pytest.mark.asyncio
async def test_잡이_빠르면_종전과_같다(stage, monkeypatch):
    """경과가 0 이면 잡 머리의 시각과 같다 — 기존 동작이 그대로 유지된다."""
    import app.pipeline as pl

    sch, tick, calls = stage

    async def _fast(row, ctx):
        return True

    monkeypatch.setattr(pl, "rejudge_after_lineup", _fast)
    n = await _run(sch)
    assert n == 1
    assert all(c == JOB_START for c in calls), calls


# ═══════════════ ③ 시계 자체의 계약

def test_시계는_뒤로_가지_않는다(monkeypatch):
    tick = {"t": 100.0}
    monkeypatch.setattr(pp, "_monotonic", lambda: tick["t"])
    c = pp.Clock(JOB_START)
    tick["t"] = 40.0                  # monotonic 이 뒤로 가는 이상 상황
    assert c.utc() == JOB_START


def test_시계는_흐른_만큼_더한다(monkeypatch):
    tick = {"t": 0.0}
    monkeypatch.setattr(pp, "_monotonic", lambda: tick["t"])
    c = pp.Clock(JOB_START)
    tick["t"] = 90.0
    assert c.utc() == JOB_START + timedelta(seconds=90)


def test_시계는_항상_tz_를_갖는다():
    naive = datetime(2026, 9, 10, 9, 28)
    assert pp.Clock(naive).utc().tzinfo is not None
    assert pp.Clock().utc().tzinfo is not None


def test_메서드_이름이_now_가_아니다():
    """🔴 `tests/test_time_discipline` 이 인자 없는 `now()` 를 AST 로 막는다.

    가드를 느슨하게 하는 대신 이름을 피했다 — 규율이 새 코드에 양보하면
    그 규율은 다음번에도 양보한다.
    """
    assert hasattr(pp.Clock, "utc") and not hasattr(pp.Clock, "now")
