"""잔액 400이면 같은 프로세스에서 추가 Anthropic 호출을 막는다."""
import pytest

from app.collectors.base import ApiQuotaError
from app.engine.credit_guard import abort_if_credit_gone, reset, stopped_at, trip_credit


def test_trip_then_abort_without_http():
    reset()
    assert stopped_at() is None
    abort_if_credit_gone("before")  # 소진 전 — 예외 없음
    trip_credit("form:kbo:한화", ApiQuotaError("anthropic", "credit balance too low"))
    assert stopped_at() == "form:kbo:한화"
    with pytest.raises(ApiQuotaError, match="잔액 소진으로 중단"):
        abort_if_credit_gone("form:kbo:KIA")
    reset()
    abort_if_credit_gone("after-reset")
