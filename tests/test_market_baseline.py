"""[시장 기준선 C1] 우리 판정 vs 시장 — **사후 전용, 게이트 아님.**

🔴 이번 구현은 계산·표기·채점뿐이다. "시장 동의 → 추천 강등"은 게이트
   변경이라 동결 대상이고 v1.4 후보로만 예약한다. 이 파일이 그 경계를 잠근다.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.engine import market_baseline as MB

SRC = Path("app/engine/market_baseline.py").read_text(encoding="utf-8")
NOW = datetime.now(UTC)


# ═════════ 1. de-vig — 실배당 표본 ═════════

def test_devig_with_real_odds():
    """어제 실배당(LAD 1.32 / STL 3.42, espn/draftkings).

    1/1.32=0.7576 · 1/3.42=0.2924 · 합 1.0500 → 0.7576/1.0500 = **0.7215**.
    ⚠️ 지시서의 "≈0.715" 는 어림값이고 정확값은 0.7215 다.
       마진(5.0%)을 빼지 않으면 0.7576 으로 5.6%p 부푼다.
    """
    assert MB.devig_two_way(1.32, 3.42) == 0.7215
    assert MB.devig_two_way(1.32, 3.42) < 1.0 / 1.32   # 마진이 실제로 빠졌다


def test_devig_guards():
    for bad in ((None, 2.0), (1.32, None), (1.0, 3.42), (1.01, 3.42),
                ("x", 2.0), (0.5, 2.0)):
        assert MB.devig_two_way(*bad) is None, bad


def test_devig_symmetry():
    p = MB.devig_two_way(2.0, 2.0)
    assert p == 0.5


# ═════════ 2. 시장 우세 · even ═════════

def test_even_band():
    assert MB.favored_of(0.505) == MB.EVEN
    assert MB.favored_of(0.495) == MB.EVEN
    assert MB.favored_of(0.511) == "home"
    assert MB.favored_of(0.489) == "away"
    assert MB.favored_of(None) is None


# ═════════ 3. 기준 스냅샷 — 나이·결측·팀명 ═════════

class Pool:
    def __init__(self, rows=None, our_hit=None):
        self._rows = rows or []
        self._our_hit = our_hit
        self.updates = []

    async def fetch(self, sql, *a):
        return self._rows

    async def fetchval(self, sql, *a):
        return self._our_hit

    async def execute(self, sql, *a):
        self.updates.append(a)


def _row(side, odds, age_min):
    return {"side": side, "odds": odds,
            "captured_at": NOW - timedelta(minutes=age_min)}


GAME = {"id": 1, "sport": "mlb", "home": "Los Angeles Dodgers",
        "away": "St. Louis Cardinals", "starts_at": NOW + timedelta(hours=1)}


@pytest.mark.asyncio
async def test_fresh_snapshot_is_used():
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 10),
                 _row("St. Louis Cardinals", 3.42, 10)])
    out = await MB.p_market(pool, GAME, purpose=MB.SEND)
    assert out["p"] == 0.7215 and out["reason"] is None
    # ⚠️ **정확히 10.0 을 요구하지 마라.** `NOW` 는 모듈 임포트 시각이고
    #    `p_market` 은 호출 시각을 쓴다 — 스위트가 길어지면 그 차이만큼
    #    나이가 늘어난다. 단독 실행은 통과하고 전체 실행은 깨진다.
    #    (오늘 세 번째 시간 의존 테스트 실수다 → ENGINEERING §3)
    assert 10.0 <= out["age_min"] < 90.0


@pytest.mark.asyncio
async def test_stale_snapshot_is_refused_for_the_card():
    """🔴 오래된 배당은 **지금 시장이 아니다.** 상한은 config 가 원본."""
    from app.config import get_settings

    assert get_settings().market_snapshot_max_age_min == 90
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 91),
                 _row("St. Louis Cardinals", 3.42, 91)])
    out = await MB.p_market(pool, GAME, purpose=MB.SEND)
    assert out["p"] is None and out["reason"] == "stale"


@pytest.mark.asyncio
async def test_close_purpose_has_no_age_limit():
    """마감 근사치는 오래돼도 그게 마감이다."""
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 500),
                 _row("St. Louis Cardinals", 3.42, 500)])
    out = await MB.p_market(pool, GAME, purpose=MB.CLOSE)
    assert out["p"] == 0.7215 and out["reason"] is None


@pytest.mark.asyncio
async def test_missing_side_is_refused():
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 5)])
    out = await MB.p_market(pool, GAME)
    assert out["p"] is None and out["reason"] == "no_snapshot"


@pytest.mark.asyncio
async def test_bad_odds_is_refused():
    pool = Pool([_row("Los Angeles Dodgers", 1.00, 5),
                 _row("St. Louis Cardinals", 3.42, 5)])
    out = await MB.p_market(pool, GAME)
    assert out["p"] is None and out["reason"] == "bad_odds"


def test_provider_comes_from_the_registry():
    """담당 provider 는 레지스트리가 원본 — 우선순위를 손으로 적지 않는다."""
    assert "from app.registry import active_providers" in SRC
    assert MB.provider_for("mlb") in ("espn", "sharp", None)
    assert MB.provider_for("nonexistent") is None


# ═════════ 4. 채점 — void · our_hit 복사 ═════════

def _pending(status="final", h=5, a=3):
    return [{"id": 9, "game_id": 1, "sport": "mlb", "home": "H", "away": "A",
             "starts_at": NOW - timedelta(hours=3), "status": status,
             "home_score": h, "away_score": a}]


@pytest.mark.asyncio
async def test_draw_is_void_and_market_hit_null(monkeypatch):
    pool = Pool(_pending(h=4, a=4), our_hit=None)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.62, "provider": "oddsportal", "age_min": 5, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    out = await MB.grade(pool)
    assert out == {"graded": 1, "void": 1}
    # UPDATE 인자 순서: (id, p_close, fav, market_hit, our_hit, void)
    args = pool.updates[0]
    assert args[3] is None            # market_hit — 무승부는 비교 불가
    assert args[5] is True            # void


@pytest.mark.asyncio
async def test_market_hit_is_computed_from_close(monkeypatch):
    pool = Pool(_pending(h=5, a=3), our_hit=True)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.62, "provider": "oddsportal", "age_min": 5, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    await MB.grade(pool)
    args = pool.updates[0]
    assert args[1] == 0.62 and args[2] == "home"
    assert args[3] is True            # 시장이 홈 우세, 홈 승 → 적중
    assert args[4] is True            # our_hit 복사


@pytest.mark.asyncio
async def test_our_hit_is_copied_never_recomputed():
    """🔴 재계산하면 두 숫자가 어긋난다 — 원본은 `pick_ledger` 다."""
    assert "SELECT hit FROM pick_ledger" in SRC
    assert "predicted_side" not in SRC, "우리 적중을 다시 계산하고 있다"


@pytest.mark.asyncio
async def test_even_market_gives_null_hit(monkeypatch):
    pool = Pool(_pending(), our_hit=True)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.502, "provider": "espn", "age_min": 3, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    await MB.grade(pool)
    args = pool.updates[0]
    assert args[2] == MB.EVEN and args[3] is None


# ═════════ 5. 동결 정합 — 게이트가 아니다 ═════════

def test_this_layer_is_not_a_gate():
    """🔴 게이트는 동결 대상이다. 이 모듈은 게이트 판정을 만들지 않는다."""
    for banned in ("gate_result", "GATE_RECOMMENDED", "qualifies",
                   "judge_confidence =", "demote"):
        assert banned not in SRC, f"{banned} — 게이트를 건드린다"


def test_grading_reuses_the_existing_job():
    """새 잡 금지 — 기존 grade 잡에 이어붙인다(타이밍 결합 회피)."""
    pl = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "from app.engine.market_baseline import grade" in pl
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert "market_baseline" not in sch, "스케줄러에 새 잡이 생겼다"


def test_draw_odds_are_not_collected():
    """무승부 배당 수집 확장 금지 — 2-way 로만 계산한다."""
    assert "Draw" not in SRC and "무승부" in SRC
    assert "devig_two_way" in SRC and "three" not in SRC.lower()
