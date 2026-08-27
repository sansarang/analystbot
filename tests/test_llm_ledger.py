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
