"""[1] disabled 프로바이더는 호출하지 않는다. 크레딧 소진은 회로를 연다."""
from __future__ import annotations

import httpx
import pytest

from app.api_guard import (
    block_info,
    clear_block,
    is_blocked,
    is_disabled,
    raise_if_unusable,
    trip_credit,
)
from app.collectors.base import (
    ApiQuotaError,
    ApiRateLimitError,
    BaseAPIClient,
    ProviderBlockedError,
    ProviderDisabledError,
)
from app.config import Settings
from app.notify import notify_api_error


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


@pytest.fixture
def live_odds(monkeypatch):
    s = _settings(disabled_providers="", odds_api_key="odds-key")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    return s


class Probe(BaseAPIClient):
    name = "odds"
    base_url = "https://example.test"

    def __init__(self):
        super().__init__(mock=False)
        self.calls = 0

    async def _send(self, method, url, params, headers, json_body):
        self.calls += 1
        req = httpx.Request(method, url)
        return httpx.Response(200, request=req, json={"ok": True})


async def test_disabled_never_sends_http(monkeypatch):
    s = _settings(disabled_providers="grok,perplexity", xai_api_key="k")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)

    class Grok(Probe):
        name = "grok"

    g = Grok()
    with pytest.raises(ProviderDisabledError):
        await g._get("/x")
    assert g.calls == 0
    assert is_disabled("grok")
    assert not is_disabled("odds")


async def test_notify_skips_disabled_and_blocked():
    assert await notify_api_error(ProviderDisabledError("grok", "disabled")) is False
    assert await notify_api_error(ProviderBlockedError("odds", "credit")) is False


async def test_credit_trips_and_second_call_does_not_send(monkeypatch, live_odds):
    class Dying(Probe):
        async def _send(self, method, url, params, headers, json_body):
            self.calls += 1
            req = httpx.Request(method, url)
            return httpx.Response(
                401, request=req,
                text='{"error_code":"OUT_OF_USAGE_CREDITS"}',
            )

    c = Dying()
    with pytest.raises(ApiQuotaError):
        await c._get("/odds")
    assert c.calls == 1
    assert await is_blocked("odds")

    c2 = Dying()
    with pytest.raises(ProviderBlockedError):
        await c2._get("/odds")
    assert c2.calls == 0


async def test_429_does_not_trip_breaker(monkeypatch, live_odds):
    async def fake_sleep(sec):
        return None

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)

    class RL(Probe):
        async def _send(self, method, url, params, headers, json_body):
            self.calls += 1
            req = httpx.Request(method, url)
            return httpx.Response(429, request=req, text="too many requests, rate limit")

    c = RL()
    with pytest.raises(ApiRateLimitError):
        await c._get("/x")
    assert c.calls >= 1
    assert not await is_blocked("odds")


async def test_key_change_unblocks(monkeypatch):
    s = _settings(disabled_providers="", odds_api_key="old-key")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    await trip_credit("odds", "OUT_OF_USAGE_CREDITS")
    assert await is_blocked("odds")

    s2 = _settings(disabled_providers="", odds_api_key="new-key")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s2)
    assert not await is_blocked("odds")
    assert await block_info("odds") is None


async def test_clear_block_is_the_human_unlock(monkeypatch, live_odds):
    await trip_credit("odds", "out")
    assert await is_blocked("odds")
    await clear_block("odds")
    assert not await is_blocked("odds")


async def test_time_does_not_auto_unblock(monkeypatch, live_odds):
    """차단 키에 TTL이 없다 — 시간이 지나도 풀리지 않는다."""
    await trip_credit("odds", "out")
    info = await block_info("odds")
    assert info and info["reason"] == "credit"
    from pathlib import Path

    src = Path("app/api_guard.py").read_text(encoding="utf-8")
    assert "TTL 없음" in src
    assert "await r.set(key, val)" in src
    assert "await r.set(key, val, ex" not in src


async def test_snapshot_odds_skips_when_blocked(monkeypatch, live_odds):
    from app.collectors.odds import snapshot_odds

    await trip_credit("odds", "out")
    assert await snapshot_odds(None, "mlb") == 0


async def test_raise_if_unusable_disabled_before_blocked(monkeypatch):
    s = _settings(disabled_providers="odds", odds_api_key="k")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    await trip_credit("odds", "out")
    with pytest.raises(ProviderDisabledError):
        await raise_if_unusable("odds")


async def test_block_survives_memory_reset_when_redis_used(monkeypatch, redis_client):
    from app import api_guard

    s = _settings(disabled_providers="", odds_api_key="k")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    api_guard.set_redis(redis_client)
    await trip_credit("odds", "out")
    api_guard.reset()          # 프로세스 메모리만 지움
    api_guard.set_redis(redis_client)
    assert await is_blocked("odds")


async def test_collect_research_does_not_build_grok_when_disabled():
    """호출 입구: _use_deep가 꺼지면 GrokClient를 만들지 않는다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index("_use_deep = get_settings().deepsearch_enabled(sport)")
    block = src[i:i + 1800]
    assert 'is_disabled("perplexity")' in block
    assert 'is_disabled("grok")' in block
    assert block.index('is_disabled("grok")') < block.index("GrokClient()")


async def test_already_blocked_does_not_alert_again(monkeypatch, live_odds):
    """회로가 열린 뒤에는 억제 창이 남아 있어도 크레딧 알림을 보내지 않는다."""
    from app.notify import notify_quota

    sent: list[str] = []

    async def fake(text: str) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr("app.notify.send_telegram", fake)
    assert await trip_credit("odds", "OUT_OF_USAGE_CREDITS") is True
    assert len(sent) == 1
    assert await trip_credit("odds", "또") is False
    assert await notify_quota("odds", "호출부 재알림") is False
    assert len(sent) == 1


async def test_prefetch_status_lines_unused_and_blocked(monkeypatch):
    from app.api_guard import prefetch_status_lines

    s = _settings(disabled_providers="grok,perplexity", odds_api_key="k")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    await trip_credit("odds", "OUT_OF_USAGE_CREDITS")
    lines = await prefetch_status_lines()
    unused = next(x for x in lines if x.startswith("미사용:"))
    assert "grok" in unused and "perplexity" in unused
    blocked = next(x for x in lines if x.startswith("차단 중:"))
    assert blocked.startswith("차단 중: odds(크레딧 소진, ")
    assert "grok" not in blocked


async def test_canonical_provider_collapses_judge_label():
    from app.api_guard import canonical_provider

    assert canonical_provider("anthropic(judge)") == "anthropic"
    assert canonical_provider("football_data") == "football_data"
    assert canonical_provider("football") == "football"
