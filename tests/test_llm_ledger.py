"""[#73] provider 사용량·장애 이력."""
import asyncio
import json

from app.llm import ledger as L
from app.llm.provider import _outage_kind, retry_wait_cap


class _FakeRedis:
    def __init__(self):
        self.h, self.l = {}, {}

    async def hincrby(self, key, field, n):
        self.h.setdefault(key, {})[field] = self.h.setdefault(key, {}).get(field, 0) + n

    async def hgetall(self, key):
        return {k: str(v) for k, v in (self.h.get(key) or {}).items()}

    async def lpush(self, key, val):
        self.l.setdefault(key, []).insert(0, val)

    async def lrange(self, key, a, b):
        return (self.l.get(key) or [])[a:b + 1]

    async def ltrim(self, key, a, b):
        self.l[key] = (self.l.get(key) or [])[a:b + 1]

    async def expire(self, key, ttl):
        return True

    async def hset(self, key, field, val):
        self.h.setdefault(key, {})[field] = val

    async def incr(self, key):
        self.h.setdefault("_n", {})[key] = self.h.setdefault("_n", {}).get(key, 0) + 1
        return self.h["_n"][key]

    async def get(self, key):
        return self.h.get("_n", {}).get(key)


def test_retry_cap_is_the_call_timeout_not_an_invented_number():
    """🔴 상한은 임의값이 아니라 **한 번의 호출 타임아웃**이다.

    실사고 2026-08-27: Groq가 Retry-After 1182초(20분)를 줬고 코드가 그대로 잤다.
    한 번 부르는 것보다 오래 기다려야 하면 폴백이 항상 빠르다.
    """
    assert retry_wait_cap(120.0) == 120.0
    assert 1182 > retry_wait_cap(120.0), "20분 대기가 상한 안에 들어오면 안 된다"


def test_rate_limit_is_not_counted_as_credit_exhaustion():
    """🔴 429를 소진으로 세면 잔액이 있는데 충전 알림이 나간다 (기존 사고)."""
    from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError

    assert _outage_kind(ApiRateLimitError("groq", "429")) == "rate_limit"
    assert _outage_kind(ApiQuotaError("groq", "레이트리밋 재시도 소진: 429")) == "rate_limit"
    assert _outage_kind(ApiQuotaError("anthropic", "credit balance too low")) == "quota"
    assert _outage_kind(ApiAuthError("x", "401")) == "auth"


def test_records_calls_and_outages():
    r = _FakeRedis()
    asyncio.run(L.record_call(r, "groq", "interpreter", True))
    asyncio.run(L.record_call(r, "groq", "interpreter", False))
    asyncio.run(L.record_outage(r, "groq", "interpreter", "rate_limit", "429"))
    data = asyncio.run(L.summary(r, days=1))
    assert data["calls"]["groq"] == {"ok": 1, "fail": 1}
    assert data["outages"][0]["kind"] == "rate_limit"
    out = "\n".join(L.format_summary(data))
    assert "groq 1건(실패 1)" in out and "레이트리밋" in out


def test_no_redis_is_a_noop_not_a_crash():
    """계측이 없다고 판정이 멈추면 안 된다 (절대 규칙 3)."""
    asyncio.run(L.record_call(None, "groq", "interpreter", True))
    asyncio.run(L.record_outage(None, "groq", "interpreter", "quota"))
    assert L.summary.__name__          # 호출만으로 예외가 없어야 한다
    assert asyncio.run(L.summary(None)) == {"calls": {}, "outages": []}


def test_health_never_guesses_remaining_credit():
    """🔴 벤더가 안 주는 잔여 크레딧을 추정해 표시하면 그 추정이 근거가 된다."""
    r = _FakeRedis()
    asyncio.run(L.record_call(r, "gemini", "narrator", True))
    out = "\n".join(L.format_summary(asyncio.run(L.summary(r, days=1))))
    for word in ("잔여", "남은 크레딧", "remaining"):
        assert word not in out


def test_last_success_marks_alive_and_dead():
    """🟢/🔴는 **관측**이다 — 최근 성공이 있으면 살아 있다고 본다."""
    from datetime import UTC, datetime, timedelta

    from app.llm.ledger import _alive

    now = datetime.now(UTC)
    assert _alive((now - timedelta(hours=1)).isoformat(), now)
    assert not _alive((now - timedelta(hours=9)).isoformat(), now)
    assert not _alive(None, now), "기록이 없으면 살아 있다고 말할 수 없다"
    assert not _alive("깨진 값", now)


def test_unknown_provider_is_not_shown_as_dead():
    """🔴 부르지 않은 provider를 '죽음'으로 표시하면 멀쩡한 것을 의심하게 된다."""
    r = _FakeRedis()
    asyncio.run(L.record_call(r, "groq", "interpreter", True))
    out = "\n".join(L.format_summary(asyncio.run(L.summary(r, days=1))))
    assert "groq" in out and "gemini" not in out and "ollama" not in out


def test_blackout_counts_and_warns():
    r = _FakeRedis()
    for _ in range(L.BLACKOUT_WARN):
        n = asyncio.run(L.record_blackout(r, "interpreter"))
    assert n == L.BLACKOUT_WARN
    out = "\n".join(L.format_summary(asyncio.run(L.summary(r, days=1))))
    assert f"전멸 {L.BLACKOUT_WARN}회" in out and "provider 추가가 필요" in out


def test_one_blackout_warns_softly():
    r = _FakeRedis()
    asyncio.run(L.record_blackout(r, "interpreter"))
    out = "\n".join(L.format_summary(asyncio.run(L.summary(r, days=1))))
    assert "전멸 1회" in out and "provider 추가가 필요" not in out


def test_tests_never_write_to_the_production_ledger():
    """🔴 테스트 더미 provider가 운영 /health에 섞였다 (fine·boom·starved·mock).

    계측이 오염되면 그 숫자를 근거로 한 판단이 전부 틀어진다.
    """
    from app.llm.provider import _ledger_redis

    assert asyncio.run(_ledger_redis()) is None, \
        "강제 목 모드인데 실 Redis 핸들이 나왔다 — 테스트가 운영 계측을 오염시킨다"
