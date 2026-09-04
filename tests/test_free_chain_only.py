"""[2026-09-04] 무료 사슬로 간다 — 유료로 내려가지 않는다.

사용자 지시: "무료사슬로 진행해야한다", "폼이 없으면 분석자체 의미가 없다".

🔴 무엇이 망가져 있었나 (운영 실측 2026-09-04 16:37):
   ① `_complete_free` 가 **"응답이 비어 있지 않다"만** 성공으로 봤다.
      Nemotron 이 JSON 대신 영어 사고문을 주면 `ok=True` 라 그대로 반환됐고,
      호출부가 파싱에 실패했다. 재시도는 **같은 provider** 로 갔다 —
      2·3순위 무료 후보는 한 번도 안 불렸다.
   ② 그렇게 두 번 실패하면 사슬 끝의 **Anthropic** 을 불렀다. 잔액 0 →
      400 → `ApiQuotaError` → `trip_credit` → **종목 전체 중단.**
      `[NPB] 팀 폼 0/10팀 — 크레딧 부족` · `NPB 파이프라인 0/1경기`.
      같은 실행에서 KBO 는 `6/10팀 — 파싱 실패` 로 살아남았다.

🔴 고친 뒤 실측 (같은 폼 프롬프트 1852자, 사고 OFF, 각 3회):
      nvidia/nemotron-3-ultra   파싱 3/3
      groq/qwen3.8-27b          파싱 3/3
      openrouter/gemma-4-31b:free 0/3 (429 — 무료 20req/분 한도)
   → 1·2순위만으로 충분하다. 3순위는 여유분이다.
"""
import pytest


@pytest.mark.asyncio
async def test_unparseable_response_advances_to_the_next_free_provider(monkeypatch):
    """🔴 이것이 핵심 결함이었다 — 사고문을 받고도 다음 후보로 안 갔다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    called = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True):
        called.append(provider)
        if provider == "nvidia":                 # 사고문 — 비어 있지 않지만 JSON 아님
            return {"ok": True, "text": "The user wants me to analyze…",
                    "elapsed": 1.0, "error": None, "usage": {}, "status": 200}
        return {"ok": True, "text": '{"team":"A","불펜":{}}',
                "elapsed": 1.0, "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("nvidia", "n"), ("groq", "g")], "p", 100, "form")

    assert called == ["nvidia", "groq"], "다음 무료 후보로 넘어가지 않았다"
    assert out == '{"team":"A","불펜":{}}'


@pytest.mark.asyncio
async def test_all_free_failing_does_not_call_anthropic(monkeypatch):
    """무료가 전부 실패해도 유료를 부르지 않는다 — 그 400 이 종목을 죽였다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True):
        return {"ok": False, "text": "", "elapsed": 0.1, "error": "503",
                "usage": {}, "status": 503}

    monkeypatch.setattr(oc, "complete", _fake)

    def _boom(*a, **k):
        raise AssertionError("Anthropic 클라이언트를 만들면 안 된다")

    monkeypatch.setattr(tf.anthropic, "AsyncAnthropic", _boom)
    monkeypatch.setenv("JUDGE_PROVIDER", "nvidia")
    monkeypatch.setenv("FREE_FORM_MODEL", "nvidia/n,groq/g")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        out = await tf.complete_json("p", model="m", max_tokens=100,
                                     role="form", mock=False)
    finally:
        get_settings.cache_clear()
    # 빈 문자열 → 호출부가 파싱 실패로 읽고 **사슬 전체를 한 번 더** 탄다.
    assert out == ""


def test_chain_has_no_paid_tail_when_free_is_configured(monkeypatch):
    from app.config import get_settings
    from app.llm.judge_route import chain

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "nvidia")
    monkeypatch.setenv("FREE_FORM_MODEL", "nvidia/n,groq/g,openrouter/x:free")
    try:
        got = chain("form")
    finally:
        get_settings.cache_clear()
    assert [p for p, _ in got] == ["nvidia", "groq", "openrouter"]
    assert "anthropic" not in [p for p, _ in got], "비상 꼬리가 다시 붙었다"


def test_chain_falls_back_to_paid_only_when_no_free_candidate(monkeypatch):
    """무료 후보가 하나도 없으면 종전 경로로 되돌아간다 — 조용히 죽지 않는다."""
    from app.config import get_settings
    from app.llm.judge_route import chain

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "nvidia")
    monkeypatch.setenv("FREE_FORM_MODEL", "")
    try:
        got = chain("form")
    finally:
        get_settings.cache_clear()
    assert [p for p, _ in got] == ["anthropic"]


def test_form_failure_is_still_loud():
    """폼은 보조가 아니다 — 실패하면 파이프라인 리포트에 그대로 뜬다."""
    from pathlib import Path

    src = Path("app/engine/team_form.py").read_text(encoding="utf-8")
    assert "응답이 JSON 이 아니다" in src
    assert "무료 사슬 전부 실패" in src
