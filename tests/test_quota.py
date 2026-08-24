"""API 크레딧/쿼터 소진 감지 + 사용자 알림 + 우아한 폴백 검증."""

import pytest

import app.bot.main as botmod
import app.pipeline as pipemod
from app.collectors.base import ApiQuotaError, is_quota_error
from app.collectors.football import check_apifootball_quota
from app.engine.judge import Judge
from app.notify import notify_quota, reset_notified
from app.pipeline import run_pipeline

DATE = "2026-08-22"


@pytest.fixture(autouse=True)
def _reset_notify_dedup():
    reset_notified()
    yield
    reset_notified()


def test_is_quota_error_detection():
    assert is_quota_error(402, "anything")                            # 결제 필요
    assert is_quota_error(429, "usage limit reached for this month")  # 쿼터성 429
    assert is_quota_error(401, "insufficient credits")                # 크레딧 소진
    assert is_quota_error(403, "your quota has been exceeded")
    assert not is_quota_error(429, "too many requests, slow down")    # 순수 rate limit
    assert not is_quota_error(401, "invalid api key")                 # 인증 오류
    assert not is_quota_error(500, "credit")                          # 서버 오류


def test_apifootball_quota_in_200_response():
    # API-Football은 쿼터 초과를 HTTP 200 + errors로 반환한다
    with pytest.raises(ApiQuotaError):
        check_apifootball_quota(
            {"errors": {"requests": "You have reached the request limit for the day"}}
        )
    ok = {"errors": [], "response": [1]}
    assert check_apifootball_quota(ok) is ok


async def test_notify_without_telegram_config_is_safe(monkeypatch):
    # 토큰/채팅ID가 없으면 로그로 대체하고 False 반환 (크래시 금지)
    from app.config import Settings, get_settings
    monkeypatch.setattr(
        "app.notify.get_settings",
        lambda: Settings(_env_file=None, telegram_bot_token=None),
    )
    assert await notify_quota("test-svc", "detail") is False
    # 같은 서비스는 프로세스당 1회만 (중복 발송 방지)
    assert await notify_quota("test-svc", "detail") is False


async def test_bot_replies_friendly_message_on_quota(monkeypatch):
    sent = []

    async def fake_pipeline(*a, **kw):
        raise ApiQuotaError("odds", "OUT_OF_USAGE_CREDITS")

    async def fake_notify(exc):
        sent.append(exc.service)
        return True

    monkeypatch.setattr(botmod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(botmod, "notify_api_error", fake_notify)

    reply = await botmod.answer_query("mlb", DATE)
    assert "크레딧이 소진" in reply and "odds" in reply  # 사용자에게 안내 메시지
    assert sent == ["odds"]                              # 관리자 알림 발송


async def test_pipeline_falls_back_to_mock_judge_on_quota(db_pool, redis_client, monkeypatch):
    sent = []

    async def broke_judge(self, payload):
        raise ApiQuotaError("anthropic(judge)", "credit balance is too low")

    async def fake_notify(exc):
        sent.append(exc.service)
        return True

    monkeypatch.setattr(Judge, "judge", broke_judge)
    monkeypatch.setattr(pipemod, "notify_api_error", fake_notify)

    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "15경기" in report and "🎯" in report  # 목 판정 폴백으로 카드는 나온다
    assert "anthropic(judge)" in sent          # 알림은 발송됐다


async def test_quota_notify_includes_recharge_guidance(monkeypatch):
    """크레딧 소진 알림에 '충전' 안내와 서비스별 충전 URL이 포함된다."""
    import app.notify as notify

    notify.reset_notified()
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    monkeypatch.setattr(notify, "send_telegram", fake_send)
    assert await notify.notify_quota("perplexity", "402 Payment Required")
    assert "충전이 필요합니다" in sent[0]
    assert "https://www.perplexity.ai/settings/api" in sent[0]

    assert await notify.notify_quota("anthropic(judge)", "credit balance too low")
    assert "console.anthropic.com" in sent[1]

    # 미등록 서비스도 충전 안내 문구는 나온다
    assert await notify.notify_quota("unknown-svc", "quota exceeded")
    assert "충전" in sent[2]

    # 같은 서비스는 1회만
    assert not await notify.notify_quota("perplexity", "again")
    notify.reset_notified()


async def test_deep_research_quota_error_notifies(monkeypatch, redis_client):
    """심층 리서치 경로에서 크레딧 소진 시 충전 알림이 발송된다."""
    from datetime import UTC, datetime

    import app.notify as notify
    import app.research.deep as deepmod
    from app.collectors.base import ApiQuotaError

    notify.reset_notified()
    sent = []

    async def fake_send(text):
        sent.append(text)
        return True

    async def quota_boom(*a, **kw):
        raise ApiQuotaError("perplexity", "402 Payment Required — 잔액 부족")

    monkeypatch.setattr(notify, "send_telegram", fake_send)
    monkeypatch.setattr(deepmod, "deep_research_game", quota_boom)
    game = {"game_id": 999999, "home": "A", "away": "B",
            "starts_at": datetime.now(UTC).isoformat()}
    data, status = await deepmod.get_game_research(redis_client, game, "soccer")
    assert data is None and status == "missing"
    assert sent and "충전이 필요합니다" in sent[0] and "perplexity" in sent[0]
    notify.reset_notified()


# ---------------------------------------------------------------- [6] 429 오분류·레이트리밋

def test_429_rate_limit_is_not_credit_exhaustion():
    """[6] 회귀: 429 request_rate_limit_exceeded를 '크레딧 소진'으로 오분류하면 안 된다.

    실사고: 계정에 $6.90이 남아 있는데 429 때문에 '충전 필요' 알림이 발송됐다.
    """
    from app.collectors.base import classify_api_error

    assert classify_api_error(429, '{"error":{"type":"request_rate_limit_exceeded"}}') == "rate_limit"
    assert not is_quota_error(429, '{"error":{"type":"request_rate_limit_exceeded"}}')
    assert classify_api_error(429, "Too Many Requests") == "rate_limit"
    # 월 사용량 상한은 여전히 크레딧 소진으로 본다
    assert classify_api_error(429, "usage limit reached for this month") == "credit"
    assert classify_api_error(402, "payment required") == "credit"
    assert classify_api_error(401, "invalid api key") == "auth"
    assert classify_api_error(401, "insufficient credits") == "credit"
    assert classify_api_error(503, "upstream down") == "server"


async def test_rate_limit_sends_no_user_notification(monkeypatch):
    """[6] 429는 사용자 알림 대상이 아니다 — 내부 재시도로만 처리."""
    import app.notify as notify
    from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError

    notify.reset_notified()
    sent = []
    monkeypatch.setattr(notify, "send_telegram", lambda text: _record(sent, text))

    assert await notify.notify_api_error(ApiRateLimitError("perplexity", "rate limited")) is False
    assert sent == []                                   # 알림 0건
    await notify.notify_api_error(ApiAuthError("perplexity", "invalid api key"))
    assert sent and "키 오류" in sent[0] and "충전" not in sent[0]
    await notify.notify_api_error(ApiQuotaError("perplexity", "insufficient credits"))
    assert any("충전" in s for s in sent)


async def _record(bucket, text):
    bucket.append(text)
    return True


async def test_429_retries_with_backoff_then_succeeds(monkeypatch):
    """[6] 429 → Retry-After/백오프로 재시도해 복구된다 (예외로 끝나지 않는다)."""
    import httpx

    from app.collectors.base import BaseAPIClient

    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)

    class Client(BaseAPIClient):
        name = "perplexity"
        base_url = "https://example.test"
        rate_limit_backoff = (2.0, 6.0, 15.0)

        def __init__(self):
            super().__init__(mock=False)
            self.calls = 0

        async def _send(self, method, url, params, headers, json_body):
            self.calls += 1
            req = httpx.Request(method, url)
            if self.calls < 3:
                return httpx.Response(429, request=req, text="rate limit exceeded")
            return httpx.Response(200, request=req, json={"ok": True})

    client = Client()
    assert await client._post("/x") == {"ok": True}
    assert client.calls == 3
    assert slept == [2.0, 6.0]        # 지수 백오프 2s → 6s


async def test_retry_after_header_wins(monkeypatch):
    """[6] Retry-After 헤더가 있으면 그 값을 우선한다."""
    import httpx

    from app.collectors.base import BaseAPIClient

    slept = []
    monkeypatch.setattr("app.collectors.base.asyncio.sleep",
                        lambda s: _record_sleep(slept, s))

    class Client(BaseAPIClient):
        name = "perplexity"
        base_url = "https://example.test"
        rate_limit_backoff = (2.0, 6.0, 15.0)

        def __init__(self):
            super().__init__(mock=False)
            self.calls = 0

        async def _send(self, method, url, params, headers, json_body):
            self.calls += 1
            req = httpx.Request(method, url)
            if self.calls == 1:
                return httpx.Response(429, request=req, headers={"Retry-After": "4"},
                                      text="rate limit")
            return httpx.Response(200, request=req, json={"ok": True})

    await Client()._post("/x")
    assert slept == [4.0]


async def _record_sleep(bucket, sec):
    bucket.append(sec)


async def test_rate_limit_exhaustion_raises_dedicated_error(monkeypatch):
    """[6] 재시도 3회 소진 시 ApiRateLimitError (ApiQuotaError 아님 — 충전 안내 금지)."""
    import httpx

    from app.collectors.base import ApiQuotaError as _Quota
    from app.collectors.base import ApiRateLimitError, BaseAPIClient

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", lambda s: _record_sleep([], s))

    class Client(BaseAPIClient):
        name = "perplexity"
        base_url = "https://example.test"
        rate_limit_backoff = (2.0, 6.0, 15.0)

        def __init__(self):
            super().__init__(mock=False)

        async def _send(self, method, url, params, headers, json_body):
            return httpx.Response(429, request=httpx.Request(method, url), text="rate limit")

    with pytest.raises(ApiRateLimitError) as ei:
        await Client()._post("/x")
    assert not isinstance(ei.value, _Quota)


async def test_perplexity_throttle_settings_applied():
    """[6] Perplexity 클라이언트에 동시 실행 상한·최소 간격·429 백오프가 걸려 있다."""
    from app.research.perplexity import PerplexityClient

    c = PerplexityClient(mock=True)
    assert c.max_concurrency <= 2
    assert c.min_interval >= 1.5
    assert c.rate_limit_backoff == (2.0, 6.0, 15.0)


async def test_min_interval_serializes_requests(monkeypatch):
    """[6] 요청 간 최소 간격이 실제로 적용된다 (동시 폭주 방지)."""
    import httpx

    from app.collectors.base import BaseAPIClient

    slept = []

    async def fake_sleep(sec):
        slept.append(sec)

    async def fake_request(self, method, url, **kw):
        return httpx.Response(200, request=httpx.Request(method, url), json={"ok": 1})

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("httpx.AsyncClient.request", fake_request)

    class Client(BaseAPIClient):
        name = "throttled-test"
        base_url = "https://example.test"
        max_concurrency = 1
        min_interval = 1.5

        def __init__(self):
            super().__init__(mock=False)

    c = Client()
    await c._post("/a")          # 첫 요청은 대기 없음
    await c._post("/b")          # 두 번째는 최소 간격만큼 대기
    assert len(slept) == 1 and 0 < slept[0] <= 1.5


async def test_agent_api_response_is_normalized():
    """[6] Agent API 전환 대비 — typed output 응답을 Sonar 형태로 정규화한다."""
    from app.research.perplexity import normalize_response

    raw = {"output": [
        {"type": "search_results", "results": [{"url": "https://a.test"}]},
        {"type": "message", "role": "assistant",
         "content": [{"type": "output_text", "text": '{"home_recent_form": {}}'}]},
    ]}
    norm = normalize_response(raw)
    assert norm["choices"][0]["message"]["content"] == '{"home_recent_form": {}}'
    assert norm["citations"] == ["https://a.test"]
    # Sonar 응답은 그대로 통과
    sonar = {"choices": [{"message": {"content": "x"}}], "citations": []}
    assert normalize_response(sonar) is sonar


async def test_perplexity_endpoint_is_config_driven(monkeypatch):
    """[6] 엔드포인트·모델이 config에서 오므로 코드 수정 없이 Agent API로 전환된다."""
    from app.config import Settings
    from app.research.perplexity import PerplexityClient

    monkeypatch.setattr("app.research.perplexity.get_settings",
                        lambda: Settings(_env_file=None, pplx_api_key="k",
                                         pplx_api_mode="agent", pplx_agent_preset="high"))
    c = PerplexityClient(mock=False)
    assert c.mode == "agent" and c.agent_path == "/v1/agent" and c.agent_preset == "high"

    captured = {}

    async def fake_post(path, headers=None, json_body=None):
        captured.update(path=path, body=json_body)
        return {"output": [{"type": "message", "content": [{"text": "hi"}]}]}

    monkeypatch.setattr(c, "_post", fake_post)
    out = await c.chat("질문")
    assert captured["path"] == "/v1/agent"
    assert captured["body"] == {"preset": "high", "input": "질문"}
    assert out["choices"][0]["message"]["content"] == "hi"


async def test_research_failure_reasons_are_counted(redis_client):
    """[5] 리서치 실패를 원인별(레이트리밋/타임아웃/파싱)로 집계한다."""
    import httpx

    from app.collectors.base import ApiRateLimitError
    from app.research.deep import (
        ResearchUnusableError,
        classify_research_failure,
        record_research_failure,
        research_failure_report,
    )

    assert classify_research_failure(ApiRateLimitError("perplexity", "429")) == "rate_limit"
    assert classify_research_failure(httpx.ReadTimeout("timed out")) == "timeout"
    assert classify_research_failure(ResearchUnusableError("재료 없음")) == "parse"
    assert classify_research_failure(ValueError("no JSON object")) == "parse"

    date = "2026-01-01"
    for reason in ("rate_limit", "rate_limit", "timeout", "parse"):
        await record_research_failure(redis_client, reason, date)
    assert await research_failure_report(redis_client, date) == {
        "rate_limit": 2, "timeout": 1, "parse": 1}


async def test_rate_limited_game_goes_to_retry_queue(redis_client):
    """[6] 레이트리밋 최종 실패 경기는 큐에 적재돼 다음 사이클에 재시도된다."""
    from app.research.deep import RETRY_QUEUE_KEY, queue_for_retry

    await redis_client.delete(RETRY_QUEUE_KEY)
    await queue_for_retry(redis_client, {"game_id": 42, "home": "H", "away": "A"}, "mlb")
    assert await redis_client.llen(RETRY_QUEUE_KEY) == 1
    import json as _json
    item = _json.loads(await redis_client.lindex(RETRY_QUEUE_KEY, 0))
    assert item["game_id"] == 42 and item["sport"] == "mlb"


async def test_retry_call_counts_toward_daily_cap(redis_client, monkeypatch):
    """[6] 재요청도 비용이다 — 일 상한 집계에 실제 콜 수가 반영된다."""
    import json as _json

    import app.research.deep as deepmod
    from app.research.perplexity import PerplexityClient

    good = _json.dumps({"home_recent_form": {"form": "WWLWL", "runs_avg": 4.2},
                        "away_recent_form": {}, "absences": [], "expert_picks": []})
    bad = _json.dumps({"home_recent_form": {"form": None, "note": "확인할 수 없습니다"},
                       "away_recent_form": {}, "absences": [], "expert_picks": []})

    class TwoCallClient(PerplexityClient):
        def __init__(self):
            super().__init__(mock=False)

        async def chat(self, prompt):
            self.calls += 1
            return {"choices": [{"message": {"content": bad if self.calls == 1 else good}}]}

    monkeypatch.setattr(deepmod, "PerplexityClient", TwoCallClient)
    key = deepmod._quota_key()
    before = int(await redis_client.get(key) or 0)
    game = {"game_id": 991, "home": "H", "away": "A", "league": "MLB",
            "starts_at": "2099-01-01T00:00:00+00:00"}
    await redis_client.delete(f"research:{game['game_id']}")
    data, status = await deepmod.get_game_research(redis_client, game, "mlb")
    assert status == "refreshed" and data["home_recent_form"]["form"] == "WWLWL"
    assert int(await redis_client.get(key)) - before == 2   # 최초 + 재요청


async def test_retry_queue_survives_missing_kickoff(redis_client, monkeypatch):
    """[6] 킥오프 미상 경기도 큐 재시도에서 깨지지 않는다."""
    import json as _json

    import app.research.deep as deepmod
    from app.research.deep import RETRY_QUEUE_KEY, drain_retry_queue, queue_for_retry
    from app.research.perplexity import PerplexityClient

    body = _json.dumps({"home_recent_form": {"form": "WWLWL"}, "away_recent_form": {},
                        "absences": [], "expert_picks": []})

    class OkClient(PerplexityClient):
        def __init__(self):
            super().__init__(mock=False)

        async def chat(self, prompt):
            self.calls += 1
            return {"choices": [{"message": {"content": body}}]}

    monkeypatch.setattr(deepmod, "PerplexityClient", OkClient)
    await redis_client.delete(RETRY_QUEUE_KEY)
    await queue_for_retry(redis_client, {"game_id": 993, "home": "H", "away": "A"}, "mlb")
    assert _json.loads(await redis_client.lindex(RETRY_QUEUE_KEY, 0))["starts_at"] is None
    assert await drain_retry_queue(redis_client) == 1
    assert await redis_client.llen(RETRY_QUEUE_KEY) == 0
