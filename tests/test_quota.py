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

    async def fake_notify(service, detail):
        sent.append(service)
        return True

    monkeypatch.setattr(botmod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(botmod, "notify_quota", fake_notify)

    reply = await botmod.answer_query("mlb", DATE)
    assert "크레딧이 소진" in reply and "odds" in reply  # 사용자에게 안내 메시지
    assert sent == ["odds"]                              # 관리자 알림 발송


async def test_pipeline_falls_back_to_mock_judge_on_quota(db_pool, redis_client, monkeypatch):
    sent = []

    async def broke_judge(self, payload):
        raise ApiQuotaError("anthropic(judge)", "credit balance is too low")

    async def fake_notify(service, detail):
        sent.append(service)
        return True

    monkeypatch.setattr(Judge, "judge", broke_judge)
    monkeypatch.setattr(pipemod, "notify_quota", fake_notify)

    report = await run_pipeline(db_pool, redis_client, sport="mlb", date=DATE)
    assert "오늘 경기 15건" in report          # 목 판정 폴백으로 리포트는 나온다
    assert "anthropic(judge)" in sent          # 알림은 발송됐다
