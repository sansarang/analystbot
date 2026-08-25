"""[6][7] 버전 추적·실패 알림 — 조용한 실패 금지 장치가 실제로 동작하는지."""

import pytest

from app import alerts
from app.alerts import (
    StageResult,
    classify_exception,
    crashed,
    our_frames,
    overall_verdict,
    prefetch_report,
    stage_failed,
)
from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError


@pytest.fixture(autouse=True)
def _clean():
    alerts.reset()
    yield
    alerts.reset()


@pytest.fixture
def sent(monkeypatch):
    """발송된 메시지를 모은다 — 실제 텔레그램은 부르지 않는다."""
    box: list[str] = []

    async def fake_send(text: str) -> bool:
        box.append(text)
        return True

    monkeypatch.setattr(alerts, "send_telegram", fake_send)
    return box


# ---------------------------------------------------------------- 원인 분류

def test_classify_exception_maps_api_errors():
    assert classify_exception(ApiQuotaError("anthropic", "잔액 부족")) == "credit"
    assert classify_exception(ApiAuthError("pplx", "401")) == "auth"
    assert classify_exception(ApiRateLimitError("pplx", "429")) == "rate_limit"


def test_classify_exception_uses_status_code_for_sdk_errors():
    """Anthropic 크레딧 소진은 400으로 온다 — SDK 예외도 분류돼야 한다."""

    class FakeSDKError(Exception):
        status_code = 400

    exc = FakeSDKError("Your credit balance is too low to access the Anthropic API")
    assert classify_exception(exc) == "credit"


def test_classify_exception_ordinary_400_is_not_credit():
    class FakeSDKError(Exception):
        status_code = 400

    assert classify_exception(FakeSDKError("max_tokens must be > 0")) == "exception"


# ---------------------------------------------------------------- 스택 트레이스

def test_our_frames_prefers_our_code():
    """라이브러리 프레임이 아니라 우리 코드 위치를 보여줘야 한다."""
    try:
        from app.engine.scoring import cap_probability

        cap_probability("문자열은 비교 불가", "mlb")   # TypeError 유발
    except Exception as exc:
        frames = our_frames(exc)
        assert frames, "프레임이 비면 원인 파악이 불가능하다"
        assert all(f.strip().startswith("app/") for f in frames)
        assert len(frames) <= 5


# ---------------------------------------------------------------- 단계 결과

def test_stage_icons_distinguish_partial_and_total_failure():
    assert StageResult("리서치", ok=15, total=15).icon == "✅"
    assert StageResult("리서치", ok=12, total=15).icon == "🟡"
    assert StageResult("판정", ok=0, total=15).icon == "🔴"


def test_stage_line_includes_cause_and_counts():
    st = StageResult("판정", ok=0, total=15, cause="credit", detail="400 invalid_request")
    line = st.line()
    assert "판정" in line and "0/15" in line and "크레딧 부족" in line


@pytest.mark.asyncio
async def test_stage_failed_sends_impact_line(sent):
    st = StageResult("λ 산출", ok=0, total=15, cause="missing",
                     impact="확률이 폴백 경로로 계산됩니다")
    assert await stage_failed(st) is True
    assert "λ 산출" in sent[0]
    assert "확률이 폴백 경로로 계산됩니다" in sent[0], "영향 한 줄이 빠지면 알림이 무의미하다"


@pytest.mark.asyncio
async def test_stage_success_sends_nothing(sent):
    assert await stage_failed(StageResult("판정", ok=15, total=15)) is False
    assert sent == []


# ---------------------------------------------------------------- [7-6] 스팸 방지

@pytest.mark.asyncio
async def test_same_error_suppressed_within_window(sent):
    st = StageResult("판정", ok=0, total=15, cause="credit")
    assert await stage_failed(st) is True
    assert await stage_failed(st) is False
    assert await stage_failed(st) is False
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_suppressed_count_is_reported_after_window(sent, monkeypatch):
    st = StageResult("판정", ok=0, total=15, cause="credit")
    await stage_failed(st)
    await stage_failed(st)      # 억제 1건
    await stage_failed(st)      # 억제 2건
    # 창이 지난 것처럼 만든다
    alerts._last_sent.clear()
    await stage_failed(st)
    assert "2건" in sent[-1], "억제한 건수를 밝히지 않으면 사고 규모를 숨기게 된다"


@pytest.mark.asyncio
async def test_crash_bypasses_suppression(sent):
    """[7-3] 크래시는 억제 대상이 아니다 — 반복돼도 매번 알린다."""
    exc = RuntimeError("파이프라인 폭발")
    await crashed("프리페치 축구", exc)
    await crashed("프리페치 축구", exc)
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_prefetch_report_always_sends_even_when_all_ok(sent):
    """[7-1] 성공해도 리포트는 온다 — '아무 소식 없음'이 정상인지 실패인지 알 수 없다."""
    stages = [StageResult("경기 적재", 15, 15), StageResult("판정", 15, 15)]
    assert await prefetch_report(stages, 120.0, "정상") is True
    assert "프리페치 완료" in sent[0]
    # 두 번째도 억제되지 않는다
    assert await prefetch_report(stages, 120.0, "정상") is True
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_prefetch_report_shows_each_stage(sent):
    stages = [
        StageResult("경기 적재", 15, 15),
        StageResult("리서치", 12, 15, cause="rate_limit"),
        StageResult("λ 산출", 0, 15, cause="missing"),
        StageResult("판정", 0, 15, cause="credit"),
    ]
    await prefetch_report(stages, 1080.0, overall_verdict(stages))
    body = sent[0]
    for name in ("경기 적재", "리서치", "λ 산출", "판정"):
        assert name in body
    assert "18분" in body
    assert "12/15" in body and "0/15" in body


# ---------------------------------------------------------------- 종합 결론

def test_verdict_calls_out_missing_judgment():
    stages = [StageResult("경기 적재", 15, 15), StageResult("판정", 0, 15, cause="credit")]
    assert "판정 없이" in overall_verdict(stages)


def test_verdict_calls_out_missing_lambda():
    stages = [StageResult("판정", 15, 15), StageResult("λ 산출", 0, 15, cause="missing")]
    assert "폴백" in overall_verdict(stages)


def test_verdict_clean_when_all_ok():
    assert "정상" in overall_verdict([StageResult("판정", 15, 15)])
