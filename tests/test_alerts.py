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


class FakeRedis:
    """프로세스 밖 공유 저장소 — 여러 '프로세스'가 같은 인스턴스를 본다."""

    def __init__(self):
        self.store: dict = {}

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v
        return True

    async def get(self, k):
        return self.store.get(k)

    async def incr(self, k):
        self.store[k] = int(self.store.get(k, 0)) + 1
        return self.store[k]

    async def expire(self, k, sec):
        return True

    async def delete(self, *ks):
        for k in ks:
            self.store.pop(k, None)

    async def keys(self, pattern):
        return list(self.store)

    async def aclose(self):
        pass


@pytest.fixture
def shared(monkeypatch):
    """모든 발송이 공유하는 Redis — 프로세스 경계를 넘는 억제를 재현한다."""
    r = FakeRedis()

    async def fake_redis():
        return r

    monkeypatch.setattr(alerts, "_redis", fake_redis)
    return r


@pytest.fixture
def sent(monkeypatch, shared):
    """발송된 메시지를 모은다 — 실제 텔레그램은 부르지 않는다."""
    box: list[str] = []

    async def fake_send(text: str) -> bool:
        box.append(text)
        return True

    # 발송 지점은 notify 하나다 — alerts는 그 모듈 속성을 부른다.
    import app.notify as notify_mod

    monkeypatch.setattr(notify_mod, "send_telegram", fake_send)
    return box


# ---------------------------------------------------------------- 원인 분류

def test_classify_exception_maps_api_errors():
    assert classify_exception(ApiQuotaError("anthropic", "잔액 부족")) == "credit_400"
    assert classify_exception(ApiAuthError("pplx", "401")) == "auth"
    assert classify_exception(ApiRateLimitError("pplx", "429")) == "rate_limit"


def test_classify_exception_uses_status_code_for_sdk_errors():
    """Anthropic 크레딧 소진은 400으로 온다 — SDK 예외도 분류돼야 한다."""

    class FakeSDKError(Exception):
        status_code = 400

    exc = FakeSDKError("Your credit balance is too low to access the Anthropic API")
    assert classify_exception(exc) == "credit_400"


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


def test_stage_line_includes_form_causes():
    st = StageResult("팀 폼", ok=0, total=10, cause="credit_400", detail="unavailable credit_400:10")
    line = st.line()
    assert "credit_400" in line and "크레딧 부족" in line
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
async def test_suppressed_count_is_reported_after_window(sent, shared):
    st = StageResult("판정", ok=0, total=15, cause="credit")
    await stage_failed(st)
    await stage_failed(st)      # 억제 1건
    await stage_failed(st)      # 억제 2건
    # 30분 창이 만료된 것처럼 (TTL 만료 = 키 소멸)
    shared.store.pop("alert:sup:stage:판정:credit")
    await stage_failed(st)
    assert "2건" in sent[-1], "억제한 건수를 밝히지 않으면 사고 규모를 숨기게 된다"


@pytest.mark.asyncio
async def test_suppression_survives_process_restart(sent, shared):
    """★ 실사고 회귀: 알림 주체가 매 실행마다 새 프로세스여도 억제돼야 한다.

    억제 상태를 프로세스 메모리에 두면 스케줄러 잡·CLI 실행처럼
    짧게 살다 죽는 프로세스에서는 전혀 억제되지 않는다.
    (2026-08-25: 같은 실패 알림이 1분 간격으로 30분 넘게 반복 발송됐다)
    """
    st = StageResult("판정", ok=0, total=15, cause="credit")
    for _ in range(10):
        alerts.reset()          # 프로세스가 새로 뜬 상황을 재현
        await stage_failed(st)
    assert len(sent) == 1, f"프로세스가 바뀌어도 1건이어야 하는데 {len(sent)}건 발송됨"


@pytest.mark.asyncio
async def test_global_budget_blocks_flood(sent, shared):
    """어떤 이유로든 폭주하면 전역 예산이 막는다 — 마지막 방어선."""
    for i in range(40):
        alerts.reset()
        await stage_failed(StageResult(f"단계{i}", ok=0, total=5, cause="missing"))
    assert len(sent) <= alerts.GLOBAL_BUDGET, f"{len(sent)}건 — 전역 예산이 무력하다"


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


@pytest.mark.asyncio
async def test_prefetch_report_footer_unused_and_blocked(sent, monkeypatch):
    """미사용·차단은 단계 실패(🔴)가 아니라 하단 한 줄이다."""
    from app.api_guard import trip_credit
    from app.config import Settings

    # 유료 모드일 때만 odds 차단이 상태로 뜬다 (무과금 전환 2026-09-02).
    s = Settings(_env_file=None, disabled_providers="grok,perplexity",
                 odds_api_key="k", odds_provider="theodds")
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    await trip_credit("odds", "OUT_OF_USAGE_CREDITS")
    await prefetch_report([StageResult("경기 적재", 15, 15)], 10.0, "정상")
    body = sent[-1]
    assert "미사용: grok, perplexity" in body
    assert "차단 중: odds(크레딧 소진," in body
    assert "✅ 경기 적재" in body


@pytest.mark.asyncio
async def test_unused_key_block_is_not_reported_as_a_status(sent, monkeypatch):
    """🔴 무과금 전환 후 `odds` 차단은 상태가 아니다.

    실사고 2026-09-02 14:12: 프리페치 리포트가 `차단 중: odds(크레딧 소진)` 을
    계속 적어, 무료 소스로 바꿨는데도 사용자가 "배당이 고장났다"로 읽었다.
    쓰지 않는 키의 차단은 보고할 상태가 아니다.
    """
    from app.api_guard import trip_credit
    from app.config import Settings

    s = Settings(_env_file=None, odds_api_key="k")      # 기본 = free
    monkeypatch.setattr("app.api_guard.get_settings", lambda: s)
    await trip_credit("odds", "OUT_OF_USAGE_CREDITS")
    await prefetch_report([StageResult("경기 적재", 15, 15)], 10.0, "정상")
    assert "차단 중" not in sent[-1]


# ---------------------------------------------------------------- 종합 결론

def test_verdict_calls_out_missing_judgment():
    stages = [StageResult("경기 적재", 15, 15), StageResult("판정", 0, 15, cause="credit")]
    assert "판정 없이" in overall_verdict(stages)


def test_verdict_calls_out_missing_lambda():
    stages = [StageResult("판정", 15, 15), StageResult("λ 산출", 0, 15, cause="missing")]
    assert "폴백" in overall_verdict(stages)


def test_verdict_clean_when_all_ok():
    assert "정상" in overall_verdict([StageResult("판정", 15, 15)])


# ---------------------------------------------------------------- [§8-10] 단계 계측 커버리지

def test_all_pipeline_stages_are_instrumented():
    """파이프라인의 모든 주요 단계가 `record()`로 계측돼야 한다.

    실사고(2026-08-26 점검): 12단계 중 **5개만** 계측돼 있었다. 결장 0/15 사고가
    늦게 발견된 이유가 이것이다 — 조용히 비어도 어디에도 기록되지 않았다.
    조용한 실패는 실패가 아니라 **성공으로 보인다**는 것이 이 프로젝트의 최대 위험이다.
    """
    import re
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    recorded = set(re.findall(r'await record\("([^"]+)"', src))
    required = {
        "경기 적재", "배당 수집", "리서치", "판정", "λ 산출",
        "날씨", "결장", "구장", "라인업", "라인업 수집", "픽 선정", "조합 구성", "서술",
        "팀 폼", "매치업 판정", "게이트·발송",
    }
    missing = required - recorded
    assert not missing, f"계측이 빠진 단계: {sorted(missing)}"


def test_every_stage_declares_impact():
    """실패 시 '무엇이 나빠지는가'를 반드시 적는다 — 알림이 행동으로 이어지게."""
    import re
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    # ⚠️ 블록 경계는 **전방탐색**으로 잡는다. 소비형으로 쓰면 연속된 record() 중
    #    뒤쪽이 앞 매치에 먹혀 검사에서 통째로 빠진다(실제로 '결장'이 빠졌었다).
    blocks = re.findall(r'await record\("([^"]+)"(.*?)(?=\n\s*(?:await |try:|if |#|\w+ =))',
                        src, re.S)
    names = [n for n, _ in blocks]
    assert len(blocks) >= 12, f"record 블록을 {len(blocks)}개만 찾았다 — 정규식 점검 필요"
    for key in ("결장", "날씨", "구장", "라인업 수집", "게이트·발송", "조합 구성"):
        assert key in names, f"'{key}' 블록이 검사 대상에서 빠졌다"
    for name, body in blocks:
        assert "impact=" in body, f"'{name}' 단계에 impact 설명이 없다"


async def test_stage_records_appear_in_analysis(db_pool, redis_client):
    """실제 파이프라인 1회 실행에서 계측이 실제로 쌓이는지 — 선언만으로는 부족하다."""
    import json

    from app.pipeline import run_pipeline

    await run_pipeline(db_pool, redis_client, "mlb", "2026-08-22", force_refresh=True)
    a = json.loads(await redis_client.get("analysis:mlb:2026-08-22"))
    names = {st["name"] for st in a.get("stages") or []}
    for key in ("경기 적재", "팀 폼", "매치업 판정", "라인업 수집", "게이트·발송"):
        assert key in names, f"'{key}' 계측이 실행 결과에 없다 (수집된: {sorted(names)})"


def test_zero_picks_is_not_a_failure():
    """[§8-15] 추천 0건은 **정상 결과**다 — 실패로 알리면 안 된다.

    실사고(2026-08-26 14:48): KBO 1경기가 판정 저신뢰로 전 마켓 제외되자
    '픽 선정 0/1 실패' 알림이 나갔다. "오늘은 걸 만한 게 없다"는 정상 결론이
    매번 🔴으로 나가면 알림이 무의미해진다.
    진짜 실패는 **마켓 보드 자체가 비었을 때**다.
    """
    import re
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    m = re.search(r'await record\("픽 선정",\s*([^,]+),', src)
    assert m, "픽 선정 계측을 찾지 못했다"
    assert "recommended" not in m.group(1), (
        "추천 건수를 성공 지표로 쓰고 있다 — 0건이 실패로 알림된다")
    assert "_board_rows" in m.group(1)


def test_lineup_stage_is_not_disabled_by_sport():
    """[§8-16] 라인업 계측을 종목으로 끄지 않는다.

    한때 "KBO엔 라인업 수집기가 없으니 계측을 끄자"고 고쳤는데 방향이 틀렸다.
    **소스가 없는 게 아니라 경로가 없었을 뿐이다** — statsapi는 MLB 전용이지만
    딥서치(Perplexity `lineup` 필드 + Grok 속보)가 KBO·NPB의 라인업 소스다.
    계측을 끄면 "라인업을 못 받고 있다"는 사실 자체가 보이지 않게 된다.
    """
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("라인업"')
    guard = src[max(0, i - 700):i]
    assert 'sport in ("mlb", "soccer")' not in guard, "라인업 계측이 종목으로 막혀 있다"
    # 딥서치 폴백 경로가 실제로 있어야 한다
    assert '_lu.get("status") == "confirmed"' in src, "딥서치 라인업 폴백이 없다"


def test_combo_stage_only_fails_with_legs():
    """배당이 있는 승인 레그가 0이면 조합 0이 정상이다 — 그때는 알리지 않는다.

    야구는 배당을 조회하지 않으므로 레그 p만 있고 odds=None인 채로 승인된다.
    그 레그로 조합을 못 만드는 것은 실패가 아니다.
    """
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("조합 구성"')
    guard = src[max(0, i - 500):i]
    assert "if _priced_legs:" in guard, "배당 있는 레그 가드가 없다"


def test_baseball_crosscheck_zero_is_not_failure():
    """공식 1소스 리그는 대조됨=0이 구조다. cause=missing이면 zero_ok가 죽은 코드다."""
    from pathlib import Path

    from app.alerts import StageResult

    st = StageResult(name="출처 대조", ok=0, total=80, unit="값",
                     cause=None, expect_full=False, zero_ok=True)
    assert not st.failed and st.icon == "✅"
    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("출처 대조"')
    block = src[i:i + 500]
    assert "zero_ok=_one_axis" in block
    assert '_one_axis = sport in ("mlb", "kbo", "npb")' in src
