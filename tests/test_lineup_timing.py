"""[라인업 발표 시각] "아직 발표 전"과 "수집 실패"를 시각으로 가른다.

🔴 실사고 2026-08-27: 킥오프 6시간 전 라인업 0건이 **실패**로 분류돼 매일
   거짓 실패 알림이 나갔다. 0건은 두 가지를 뜻할 수 있고, 시각으로만 구분된다.

⚠️ 이 파일의 기준값은 **리그 관행**이지 실측이 아니다. 실측 교체 전까지
   이 숫자로 "수집이 늦다"고 결론짓지 마라.
"""
import asyncio
from datetime import UTC, datetime, timedelta

from app.alerts import StageResult
from app.engine import lineup_timing as LT

NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)     # KST 15:00


def _g(hours_ahead: float, gid: int = 1, status: str = "none") -> dict:
    return {"game_id": gid, "lineup_status": status,
            "starts_at": (NOW + timedelta(hours=hours_ahead)).isoformat()}


# ------------------------------------------------------------ 리그별 관행값

def test_lead_hours_per_league():
    assert LT.lead_hours("kbo") == 1.0
    assert LT.lead_hours("npb") == 1.0
    assert LT.lead_hours("mlb") == 3.0
    assert LT.lead_hours("soccer") == 1.0
    assert LT.lead_hours("모르는종목") == 1.0, "모르는 종목은 가장 짧은 기준으로"


# ------------------------------------------------------------ 정상 / 실패

def test_kbo_zero_before_one_hour_is_normal():
    """KBO 킥오프 3시간 전 라인업 0건 — 아직 공시 전이므로 정상."""
    ok, why = LT.classify([_g(3), _g(3.5)], 0, "kbo", now=NOW)
    assert ok and "아직 발표 전" in why


def test_kbo_zero_after_one_hour_is_a_failure():
    """공시 시각이 지났는데 0건이면 수집 실패다 — 이건 알려야 한다."""
    ok, why = LT.classify([_g(0.5), _g(0.4)], 0, "kbo", now=NOW)
    assert not ok and "수집 실패" in why


def test_mlb_uses_a_longer_window():
    """MLB는 2~4시간 전 발표 관행 → 3시간. 같은 3시간 전이 KBO와 다르게 읽힌다."""
    assert LT.classify([_g(2.5)], 0, "mlb", now=NOW)[0] is False
    assert LT.classify([_g(2.5)], 0, "kbo", now=NOW)[0] is True


def test_one_late_game_makes_the_whole_stage_suspect():
    """🔴 하나라도 발표 시각을 지났는데 0건이면 정상이라고 말하지 않는다."""
    ok, _ = LT.classify([_g(5), _g(5), _g(0.2)], 0, "kbo", now=NOW)
    assert not ok


def test_unknown_kickoff_is_not_evidence_of_normal():
    """🔴 모르는 것을 정상의 근거로 쓰면 시각 파싱이 깨진 날 전부 '정상'이 된다."""
    ok, _ = LT.classify([{"game_id": 1, "starts_at": None}], 0, "kbo", now=NOW)
    assert not ok


def test_any_collected_lineup_is_always_normal():
    assert LT.classify([_g(0.1)], 2, "kbo", now=NOW) == (True, "")


# ------------------------------------------------------------ 계측 연동

def test_stage_severity_follows_the_clock():
    """발표 전 0건은 '정상', 발표 후 0건은 '실패'로 나와야 알림이 정확해진다."""
    early = StageResult(name="라인업", ok=0, total=5, unit="경기",
                        expect_full=False, zero_ok=True)
    late = StageResult(name="라인업", ok=0, total=5, unit="경기",
                       expect_full=False, zero_ok=False)
    assert early.severity == "정상" and not early.failed
    assert late.severity == "실패" and late.failed


def test_zero_ok_does_not_hide_a_real_cause():
    """수집기가 예외로 죽었으면 시각과 무관하게 실패다."""
    st = StageResult(name="라인업", ok=0, total=5, cause="exception", zero_ok=True)
    assert st.severity == "실패"


# ------------------------------------------------------------ 관측 (실측 교체용)

class _FakeRedis:
    def __init__(self):
        self.h = {}

    async def hexists(self, key, field):
        return field in self.h.get(key, {})

    async def hset(self, key, field, val):
        self.h.setdefault(key, {})[field] = val

    async def hgetall(self, key):
        return dict(self.h.get(key) or {})

    async def expire(self, key, ttl):
        return True


def test_observation_records_lead_time_once_per_game():
    """🔴 폴링이 반복 기록하면 분포가 '마지막 관측'으로 쏠린다 — 첫 건만 센다."""
    r = _FakeRedis()
    asyncio.run(LT.observe(r, "kbo", 1, _g(2.0)["starts_at"], now=NOW))
    asyncio.run(LT.observe(r, "kbo", 1, _g(0.5)["starts_at"], now=NOW))
    leads = asyncio.run(LT.observed(r, "kbo"))
    assert leads == [2.0], f"첫 관측만 남아야 한다: {leads}"


def test_observation_skips_games_without_kickoff():
    r = _FakeRedis()
    asyncio.run(LT.observe(r, "kbo", 1, None, now=NOW))
    assert asyncio.run(LT.observed(r, "kbo")) == []


def test_thin_observations_never_produce_a_number():
    """🔴 얇은 표본의 중앙값이 관행값을 갈아치우는 근거로 쓰이면 안 된다."""
    out = LT.summarize([1.1, 0.9, 1.4])
    assert "표본 부족" in out and "중앙값" not in out


def test_enough_observations_report_a_median():
    out = LT.summarize([1.0] * 10 + [2.0] * 10)
    assert "중앙값 1.5시간 전" in out and "20건" in out
