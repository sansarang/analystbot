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


# 🔴 [P0 안정성 2026-09-05] **계약이 바뀌었다 — 한 판정은 한 모델이 낸다.**
#    종전 계약은 "사고문을 받으면 다음 무료 후보로 넘어간다"였다. 그것이
#    2026-09-04 사고(유료 400 → 종목 전체 중단)를 막았지만, 같은 경기의
#    재판정이 회차마다 다른 모델의 답을 받는 부작용을 낳았다 —
#    실측 2026-09-05 KBO game=1713 이 같은 재료로 기아 0.440 → 0.590 →
#    KT 0.450 으로 50% 선을 두 번 넘었다.
#    새 계약: 소프트 실패(JSON 아님)는 **같은 모델로 1회 재시도**하고,
#    그래도 안 되면 포기한다. provider 를 회전시키지 않는다.
#    ⚠️ 2026-09-04 사고의 방지선은 그대로다 — 아래
#       `test_all_free_failing_does_not_call_anthropic` 가 지킨다.
@pytest.mark.asyncio
async def test_soft_failure_retries_the_same_model_and_does_not_rotate(monkeypatch):
    """JSON 이 아니면 같은 모델 1회 재시도 — 다음 provider 로 가지 않는다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    called = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        called.append(provider)
        return {"ok": True, "text": "The user wants me to analyze…",
                "elapsed": 1.0, "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("nvidia", "n"), ("groq", "g")], "p", 100, "form")

    assert called == ["nvidia", "nvidia"], "같은 모델로 1회 재시도해야 한다"
    assert "groq" not in called, "소프트 실패로 provider 를 회전시켰다"
    assert out is None


@pytest.mark.asyncio
async def test_soft_failure_recovers_when_the_retry_parses(monkeypatch):
    """재시도가 성사되면 그 모델의 답을 쓴다 — 회전 없이 회복한다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    called = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        called.append(provider)
        if len(called) == 1:
            return {"ok": True, "text": "The user wants me to analyze…",
                    "elapsed": 1.0, "error": None, "usage": {}, "status": 200}
        return {"ok": True, "text": '{"team":"A","불펜":{}}',
                "elapsed": 1.0, "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("nvidia", "n"), ("groq", "g")], "p", 100, "form")

    assert called == ["nvidia", "nvidia"]
    assert out == '{"team":"A","불펜":{}}'


@pytest.mark.asyncio
async def test_hard_failure_falls_back_once_only(monkeypatch):
    """호출 자체가 불가하면 다음 후보로 — 단 1회다. 사슬을 다 걷지 않는다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    called = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        called.append(provider)
        return {"ok": False, "text": "", "elapsed": 1.0,
                "error": "503", "usage": None, "status": 503}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free(
        [("nvidia", "n"), ("groq", "g"), ("openrouter", "o")], "p", 100, "form")

    assert called == ["nvidia", "groq"], "폴백은 하드 실패 시 1회뿐이다"
    assert "openrouter" not in called
    assert out is None


@pytest.mark.asyncio
async def test_judgement_calls_carry_a_fixed_seed(monkeypatch):
    """결정성 — 판정 호출에 고정 seed 를 명시 전송한다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc
    from app.config import get_settings

    seen = {}

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        seen.update(kw)
        return {"ok": True, "text": '{"team":"A","불펜":{}}',
                "elapsed": 1.0, "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    await tf._complete_free([("nvidia", "n")], "p", 100, "matchup")
    assert seen.get("seed") == int(get_settings().llm_seed)


@pytest.mark.asyncio
async def test_all_free_failing_does_not_call_anthropic(monkeypatch):
    """무료가 전부 실패해도 유료를 부르지 않는다 — 그 400 이 종목을 죽였다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
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


# ── [P0 안정성 2026-09-05] Gemini 주전 승격 ──────────────────────────
# 오디션 실측(동일 프롬프트 10회): nemotron 산포 10.00%p·뒤집힘 4,
# gpt-oss 12.00%p·뒤집힘 3, gemini 2.00%p·뒤집힘 0 — 사슬에서 유일한 합격.
def test_gemini_is_reachable_through_the_chain():
    """Gemini 가 사슬 provider 로 등록돼 있다 — 별도 클라이언트만으로는 못 쓴다."""
    from app.llm.openai_compat import ENDPOINTS

    assert "gemini" in ENDPOINTS
    base, env = ENDPOINTS["gemini"]
    assert env == "GEMINI_API_KEY"
    assert base.endswith("/openai"), "OpenAI 호환 경로여야 사슬 구조를 쓴다"


def test_seed_is_omitted_for_providers_that_reject_it(monkeypatch):
    """Gemini 는 seed 를 400 으로 거부한다 — 실으면 판정이 통째로 죽는다."""
    import httpx

    import app.llm.openai_compat as oc

    sent = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {}}

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            sent.update(json or {})
            return _Resp()

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "x")
    # `httpx` 는 함수 안에서 임포트된다 — 모듈 자체를 갈아끼운다.
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    import asyncio

    asyncio.run(oc.complete("gemini", "m", "p", max_tokens=8, seed=42))
    assert "seed" not in sent, "Gemini 에 seed 를 실었다 — 400 이 난다"
    assert sent.get("temperature") == 0

    sent.clear()
    asyncio.run(oc.complete("nvidia", "m", "p", max_tokens=8, seed=42))
    assert sent.get("seed") == 42, "seed 를 받는 provider 에는 실어야 한다"


# ── [2026-09-06] 최종 판정은 단 한 번이다 ───────────────────────────
# 사용자 지시: "마지막 판정은 단 한 번으로 제한하고 안트로픽 fable 로 정해라."
# 같은 재료를 여러 번 물으면 회차마다 답이 달라진다 — 오늘 실측이 그것이었다.
def test_judgement_model_is_fable():
    from app.config import get_settings

    assert get_settings().matchup_model == "claude-fable-5"


@pytest.mark.asyncio
async def test_judgement_calls_the_model_only_once(monkeypatch):
    """🔴 판정은 실패해도 다시 묻지 않는다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    calls = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        calls.append(provider)
        return {"ok": True, "text": "사고문 — JSON 아님", "elapsed": 1.0,
                "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("gemini", "g"), ("nvidia", "n")], "p", 100,
                                  "matchup")
    assert calls == ["gemini"], f"판정을 {len(calls)}번 불렀다: {calls}"
    assert out is None


@pytest.mark.asyncio
async def test_form_still_retries(monkeypatch):
    """반대 위험 — 폼은 재료를 만드는 단계라 재시도가 남아야 한다."""
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    calls = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        calls.append(provider)
        return {"ok": True, "text": "사고문", "elapsed": 1.0,
                "error": None, "usage": {}, "status": 200}

    monkeypatch.setattr(oc, "complete", _fake)
    await tf._complete_free([("nvidia", "n")], "p", 100, "form")
    assert calls == ["nvidia", "nvidia"], "폼 재시도가 사라졌다"


# ── [2026-09-06] 유료가 주전이면 매 호출이 경보가 되면 안 된다 ───────
# 🔴 실사고 2026-09-02: 워치독 오탐 4건이 15분마다 울려 **진짜 고장 하나가
#    묻힐 뻔했다.** Fable 이 주전이 된 지금 종전 조건이면 경기마다(하루 26회+)
#    W-LLM-PAID 가 울린다.
@pytest.mark.asyncio
async def test_paid_primary_stays_quiet_until_near_cap(monkeypatch):
    import app.llm.judge_route as jr

    alerts = []

    class _R:
        def __init__(self):
            self.n = 0

        async def incr(self, k):
            self.n += 1
            return self.n

        async def expire(self, k, t):
            return True

    async def _wd(code, detail, target=None):
        alerts.append((code, detail))

    import app.alerts as al

    monkeypatch.setattr(al, "watchdog", _wd)
    monkeypatch.setattr(jr, "_cfg", lambda: type(
        "S", (), {"anthropic_daily_cap": 10, "judge_provider": "anthropic"})())
    monkeypatch.setattr("app.pipeline.today_kst", lambda: "2026-09-06")

    r = _R()
    for _ in range(7):                     # 캡 10의 80% = 8회 미만
        await jr.note_paid_call(r, "matchup")
    assert alerts == [], f"주전인데 {len(alerts)}번 울렸다"

    await jr.note_paid_call(r, "matchup")  # 8회째 — 80% 도달
    assert len(alerts) == 1
    assert "캡에 근접" in alerts[0][1]


@pytest.mark.asyncio
async def test_paid_fallback_alerts_on_first_call(monkeypatch):
    """반대 위험 — 유료가 **폴백**이면 1콜부터 울려야 한다.

    그건 "무료가 죽었다"는 신호이고, 조용하면 그 사실을 아무도 모른다.
    """
    import app.alerts as al
    import app.llm.judge_route as jr

    alerts = []

    class _R:
        async def incr(self, k):
            return 1

        async def expire(self, k, t):
            return True

    monkeypatch.setattr(al, "watchdog",
                        lambda c, d, target=None: alerts.append((c, d)) or _noop())
    monkeypatch.setattr(jr, "_cfg", lambda: type(
        "S", (), {"anthropic_daily_cap": 80, "judge_provider": "gemini"})())
    monkeypatch.setattr("app.pipeline.today_kst", lambda: "2026-09-06")

    await jr.note_paid_call(_R(), "matchup")
    assert len(alerts) == 1
    assert "무료 provider 가 실패" in alerts[0][1]


async def _noop():
    return None
