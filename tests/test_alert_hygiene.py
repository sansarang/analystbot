"""[알림 정리] 화면이 못 쓰게 되는 네 가지를 고정한다.

전부 2026-08-27에 실제로 사용자 화면에서 관측된 증상이다.
  ① 단계 실패가 매번 발송돼 카드가 안 보였다
  ② Odds 크레딧 알림이 11:05·11:15·11:26 세 번 왔다 (30분 억제 미작동)
  ③ "기사 발췌 3/5"가 '실패 · 원인 예외'로 분류됐다 (부분 수집은 정상)
  ④ 5경기 슬레이트에 "출처 대조 438경기"가 나갔다 (단위 오류)
"""
import ast
import asyncio
import pathlib

import pytest

import app.notify as notify_mod
from app.alerts import StageResult, stage_failed, stages_summary

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def shared(monkeypatch):
    """모든 발송이 공유하는 Redis — **프로세스 경계를 넘는 억제**를 재현한다.
    이것이 없으면 이 파일의 억제 테스트는 실사고를 재현하지 못한다."""
    import app.alerts as alerts_mod
    from tests.test_alerts import FakeRedis

    r = FakeRedis()

    async def fake_redis():
        return r

    monkeypatch.setattr(alerts_mod, "_redis", fake_redis)
    return r


@pytest.fixture
def sent(monkeypatch, shared):
    box: list[str] = []

    async def fake_send(text: str) -> bool:
        box.append(text)
        return True

    monkeypatch.setattr(notify_mod, "send_telegram", fake_send)
    return box


# ---------------------------------------------------- ③ 실패 / 부분 / 정상

def test_partial_collection_is_not_a_failure():
    """🔴 5경기 중 3경기에만 기사가 있는 것은 정상이다."""
    st = StageResult(name="기사 발췌", ok=3, total=5, unit="경기", expect_full=False)
    assert st.severity == "정상"
    assert not st.failed and not st.partial
    assert st.icon == "✅"


def test_partial_where_full_is_expected_is_partial_not_failure():
    st = StageResult(name="판정", ok=3, total=5)
    assert st.severity == "부분" and st.partial and not st.failed
    assert st.icon == "🟡"


def test_zero_is_always_a_failure():
    """0건은 부분 수집이 정상인 단계에서도 실패다 — 아무것도 못 모았다."""
    st = StageResult(name="기사 발췌", ok=0, total=5, expect_full=False)
    assert st.severity == "실패" and st.icon == "🔴"


def test_no_cause_is_never_reported_as_exception(sent):
    """🔴 원인이 없는데 '원인 예외'로 나갔다 — cause=None의 폴백 라벨이 문제였다."""
    asyncio.run(stage_failed(StageResult(name="기사 발췌", ok=0, total=5)))
    assert sent, "전면 중단은 발송돼야 한다"
    assert "원인" not in sent[0], f"없는 원인을 지어냈다: {sent[0]}"


# ---------------------------------------------------- ① 도배 금지

def test_one_analysis_sends_one_summary(sent):
    stages = [StageResult(name=f"단계{i}", ok=0, total=3, cause="missing")
              for i in range(6)]
    asyncio.run(stages_summary(stages, where="kbo 분석"))
    assert len(sent) == 1, f"요약 1건이어야 한다 — {len(sent)}건 발송됨"
    assert "단계 실패 6건" in sent[0]


def test_summary_is_silent_when_only_partial(sent):
    """부분 수집만 있으면 알리지 않는다 — 알릴 일이 아니다."""
    asyncio.run(stages_summary([
        StageResult(name="기사 발췌", ok=3, total=5, expect_full=False),
        StageResult(name="라인업", ok=2, total=5, expect_full=False)]))
    assert sent == []


def test_pipeline_does_not_send_per_stage():
    """🔴 record()가 단계마다 발송하면 도배가 재발한다 — 소스로 고정."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    body = src[src.index("async def record("):src.index("await progress(1, 4")]
    assert "stage_failed" not in body, "record()가 다시 즉시 발송한다"
    assert "stages_summary" in src, "분석 끝 요약 발송이 없다"


# ---------------------------------------------------- ② 하루 1회 억제 (크레딧)

def test_quota_alert_is_suppressed_across_processes(sent):
    """🔴 프로세스 내 집합으로 막으면 봇·스케줄러가 각각 보낸다 (실측 3회).
    크레딧은 이제 KST 하루 1회 — 같은 날 두 번째부터는 막힌다."""
    assert asyncio.run(notify_mod.notify_quota("odds", "OUT_OF_USAGE_CREDITS"))
    assert not asyncio.run(notify_mod.notify_quota("odds", "OUT_OF_USAGE_CREDITS"))
    assert not asyncio.run(notify_mod.notify_quota("odds", "또 왔다"))
    assert len(sent) == 1, f"같은 크레딧 알림이 {len(sent)}번 나갔다"


def test_already_blocked_sends_zero_even_if_window_reset(sent, shared):
    """이미 차단된 곳은 억제 키를 지워도(창이 다시 열려도) 알림 0건."""
    from app.api_guard import clear_block, trip_credit

    assert asyncio.run(trip_credit("odds", "OUT_OF_USAGE_CREDITS"))
    assert len(sent) == 1
    shared.store.clear()
    assert not asyncio.run(notify_mod.notify_quota("odds", "다시"))
    assert len(sent) == 1
    asyncio.run(clear_block("odds"))


def test_quota_window_is_until_kst_midnight():
    from datetime import datetime, timedelta

    from app.alerts import KST, quota_window_sec

    now = datetime.now(KST)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    assert quota_window_sec() == max(60, int((nxt - now).total_seconds()))


def test_quota_notify_uses_daily_window_not_thirty_min():
    src = (ROOT / "app/notify.py").read_text(encoding="utf-8")
    assert "quota_window_sec" in src
    assert "allow_when_blocked" in src


def test_suppression_is_per_service(sent):
    asyncio.run(notify_mod.notify_quota("odds", "x"))
    asyncio.run(notify_mod.notify_quota("anthropic", "y"))
    assert len(sent) == 2, "서비스가 다르면 각각 알려야 한다"


def test_notify_does_not_bind_send_telegram_locally():
    """🔴 발송 지점이 둘로 갈라지면 한쪽만 막았을 때 조용히 새어 나간다."""
    import app.alerts as alerts_mod

    assert not hasattr(alerts_mod, "send_telegram")


# ---------------------------------------------------- ④ 단위

def test_every_pipeline_stage_declares_its_unit():
    """🔴 단위를 안 붙이면 팀 수·값 개수가 '경기'로 둔갑한다."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    missing = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "record"
                and node.args and isinstance(node.args[0], ast.Constant)):
            if "unit" not in {k.arg for k in node.keywords}:
                missing.append((node.args[0].value, node.lineno))
    assert not missing, f"단위 미선언 계측: {missing}"


def test_stage_line_uses_its_own_unit():
    assert "10/10팀" in StageResult(name="1군 등록", ok=10, total=10, unit="팀").line()
    assert "20/438값" in StageResult(name="출처 대조", ok=20, total=438,
                                     unit="값", expect_full=False).line()


def test_limitation_line_never_calls_values_games():
    """🔴 5경기 슬레이트에 '출처 대조 438경기'가 나갔다."""
    from app.pipeline import data_limitation_line

    line = data_limitation_line({"stages": [
        {"name": "출처 대조", "ok": 20, "total": 438, "cause": None,
         "unit": "값", "severity": "부분"}]})
    assert line and "418값" in line and "경기" not in line


def test_limitation_line_drops_normal_partials():
    """부분 수집이 정상인 단계는 '한계'에 싣지 않는다."""
    from app.pipeline import data_limitation_line

    assert data_limitation_line({"stages": [
        {"name": "기사 발췌", "ok": 3, "total": 5, "cause": None,
         "unit": "경기", "severity": "정상"}]}) is None


# ---------------------------------------------------- ④ 분모가 대상 수와 맞는가

def _record_calls():
    """(이름, 분자AST, 분모AST, 단위, 줄번호)"""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "record"
                and node.args and isinstance(node.args[0], ast.Constant)):
            kw = {k.arg: k.value for k in node.keywords}
            yield (node.args[0].value,
                   node.args[1] if len(node.args) > 1 else None,
                   node.args[2] if len(node.args) > 2 else None,
                   getattr(kw.get("unit"), "value", None), node.lineno)


# 단위별로 분모가 세어야 하는 것. 실측 2026-08-27 KBO 슬레이트로 확인했다:
#   전체 5경기 · 예정 5경기 · KBO 10팀 · 구장 9 → 불일치 0건
# 팀·구장 분모는 **이름 붙은 실측 상수**여야 한다. 리터럴을 흩뿌리면
# 리그가 늘 때 한 곳만 고치고 나머지를 놓친다.
_COUNT_NAMES = {"팀": {"KBO_TEAMS", "NPB_TEAMS"},
                "구장": {"KBO_PARKS", "MLB_PARKS"}}


def test_fixed_denominators_use_named_measured_constants():
    """🔴 분모가 실제 대상 수가 아니면 '10팀 중 9팀 실패' 같은 거짓말이 나온다."""
    for name, _num, total, unit, line in _record_calls():
        if unit not in _COUNT_NAMES or total is None:
            continue
        expr = ast.unparse(total)
        assert expr in _COUNT_NAMES[unit], \
            f"{name}(L{line}): {unit} 분모가 {expr} — 실측 상수를 쓰라"


def _core(node) -> str:
    """`max(1, X or 1)` 같은 방어 껍데기를 벗긴 알맹이."""
    expr = ast.unparse(node)
    for a, b in (("max(1, ", ""), (" or 1", ""), (" or len(games)", "")):
        expr = expr.replace(a, b)
    return expr.strip().rstrip(")")


def test_a_denominator_is_never_its_own_numerator():
    """🔴 분모가 분자와 같으면 ok==total이라 **절대 실패할 수 없다.**

    실측 2026-08-27: 구장 계측이 `len(parks) / max(1, len(parks) or 1)`이었다.
    계측이 아니라 장식이었고, MLB 30구장 중 0개가 와도 '정상'으로 나갔다.
    같은 결함이 '경기 적재'에도 있었다.
    """
    bad = [(n, l) for n, num, tot, _u, l in _record_calls()
           if num is not None and tot is not None and _core(num) == _core(tot)
           and "len(" in _core(num)]
    assert not bad, f"분모가 분자와 같은 계측(절대 실패 불가): {bad}"


def test_game_denominators_are_derived_from_the_game_list():
    """단위가 '경기'면 분모는 경기 수에서 나와야 한다 — 리터럴 상수면 어긋난다."""
    for name, _num, total, unit, line in _record_calls():
        if unit != "경기" or total is None:
            continue
        assert not isinstance(total, ast.Constant), \
            f"{name}(L{line}): 경기 분모가 상수 {ast.unparse(total)}다"
        assert "len(" in ast.unparse(total) or ast.unparse(total).startswith("_"), \
            f"{name}(L{line}): 경기 분모가 경기 수에서 나오지 않는다 — {ast.unparse(total)}"


def test_no_stage_declares_an_unknown_unit():
    """오탈자 단위는 표시 계층에서 조용히 이상한 말을 만든다."""
    allowed = {"경기", "팀", "구장", "값", "행", "건"}
    for name, _num, _total, unit, line in _record_calls():
        assert unit in allowed, f"{name}(L{line}): 모르는 단위 {unit!r}"


# ---------------------------------------------------- ⑤ 프리페치 계측이 사실을 말하는가

def test_prefetch_copy_keeps_unit_and_zero_ok():
    """스케줄러가 필드를 빼면 구장 30개가 '30/30경기'가 되고, 라인업 0이 🔴이 된다."""
    from dataclasses import replace

    park = StageResult(name="구장", ok=30, total=30, unit="구장")
    assert "30/30구장" in replace(park, name="[MLB] 구장").line()
    intent = StageResult(name="라인업 의도", ok=0, total=7, unit="경기",
                         expect_full=False, zero_ok=True)
    dropped = StageResult(name="[MLB] 라인업 의도", ok=intent.ok, total=intent.total,
                          cause=intent.cause, detail=intent.detail)
    assert dropped.failed and dropped.icon == "🔴"
    kept = replace(intent, name="[MLB] 라인업 의도")
    assert not kept.failed and kept.icon == "✅"
    src = (ROOT / "app/scheduler.py").read_text(encoding="utf-8")
    assert "replace(st, name=" in src
    assert "StageResult(name=f\"[{sport_kr}] {st.name}\", ok=st.ok" not in src


def test_research_cause_is_not_compared_to_all_games():
    """분모는 예정 경기인데 실패 여부를 전체 경기 수와 비교하면 끝난 경기 때문에 🔴."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("리서치"')
    block = src[max(0, i - 900):i + 200]
    assert "_research_total" in block
    assert "_ok_research == len(games)" not in block
    assert '_OK_STATES = ("refreshed", "cached", "off", "stale_fallback")' in src


def test_judge_record_uses_hits_not_raw_len():
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("판정", _judged')
    assert "_verdict_hits" in src[i - 400:i]


def test_lineup_intent_zero_ok_is_not_overridden_by_cause():
    """cause가 있으면 zero_ok는 죽은 코드다 — 0건이 정상인데도 🔴."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("라인업 의도"')
    block = src[i:i + 400]
    assert "zero_ok=not compared" in block
    assert 'cause=None if compared else "missing"' not in block


def test_research_partial_is_yellow_not_red():
    """일부만 받은 리서치는 전량 실패가 아니다."""
    st = StageResult(name="리서치", ok=3, total=7, unit="경기")
    assert st.icon == "🟡" and st.partial and not st.failed
