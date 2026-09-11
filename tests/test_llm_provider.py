"""[B-1~B-4] LLM provider 추상화.

성공 기준은 하나다: **코드를 고치지 않고 .env만 바꿔 provider를 갈아끼울 수
있는가.** 나머지 테스트는 그 과정에서 조용히 틀어지는 것을 막는다.
"""

import json

import pytest

from app.config import Settings
from app.llm import provider as P


def _settings(**over):
    # ⚠️ `force_mock=False`를 **명시**한다. conftest가 FORCE_MOCK=true를 걸어두는데,
    #    이 파일의 테스트들은 네트워크를 치지 않고 **라우팅만** 본다(build_provider는
    #    인스턴스를 만들 뿐 호출하지 않는다). 목 게이트가 켜져 있으면 라우팅이
    #    전부 MockProvider로 접혀 "env만 바꿔서 벤더 전환" 자체를 검증할 수 없다.
    # ⚠️ [2026-09-06] 예시 provider 가 `anthropic` 이었다. Anthropic 은 이제
    #    역할 체인에 없다(2차 최종 판정 전용) — `xai` 로 바꾼다. 검증하는
    #    성질은 그대로다: "코드 수정 없이 env 만으로 벤더가 바뀐다".
    base = dict(force_mock=False,
                interpreter_provider="mock", judge_a_provider="xai",
                judge_a_model="grok-x", judge_b_provider="",
                narrator_provider="xai", xai_api_key="k")
    base.update(over)
    return Settings(**base)


SCHEMA = {"type": "object",
          "properties": {"p": {"type": "number"}, "why": {"type": "string"},
                         "ok": {"type": "boolean"}, "tags": {"type": "array"}},
          "required": ["p", "why", "ok", "tags"], "additionalProperties": False}


# ---------------------------------------------------------------- B-2 라우팅

def test_env_alone_switches_provider():
    """🔴 이 작업의 성공 기준 — 코드 수정 없이 provider가 바뀌어야 한다."""
    a = P.provider_chain("judge_a", _settings(judge_a_provider="xai"))
    g = P.provider_chain("judge_a", _settings(judge_a_provider="gemini",
                                              gemini_api_key="g"))
    o = P.provider_chain("judge_a", _settings(judge_a_provider="ollama"))
    assert [p.name for p in (a[0], g[0], o[0])] == ["xai", "gemini", "ollama"]
    assert isinstance(g[0], P.GeminiProvider)
    assert isinstance(o[0], P.OpenAICompatProvider)
    # 🔴 anthropic 은 역할 체인에서 **거절**된다 — 2차 최종 판정 전용이다.
    with pytest.raises(P.LLMError, match="알 수 없는 provider"):
        P.provider_chain("judge_a", _settings(judge_a_provider="anthropic"))


def test_openai_compatible_backends_share_one_implementation():
    """Groq·DeepSeek·Ollama는 같은 형식이다 — 셋을 따로 구현하면 버그를 세 번 고친다."""
    s = _settings(groq_api_key="g", deepseek_api_key="d")
    made = {k: P.build_provider(k, "m", s) for k in ("groq", "deepseek", "ollama")}
    assert all(isinstance(v, P.OpenAICompatProvider) for v in made.values())
    # 그래도 **어느 백엔드였는지는 구분돼야 한다** (폴백 추적·병렬 채점용)
    assert {k: v.name for k, v in made.items()} == {
        "groq": "groq", "deepseek": "deepseek", "ollama": "ollama"}
    assert made["groq"].base_url != made["deepseek"].base_url


def test_model_falls_back_to_existing_setting():
    """새 설정을 안 넣어도 종전 동작이 유지돼야 한다."""
    s = _settings(judge_a_model="", judge_model="claude-old",
                  narrator_model="", report_model="sonnet-old")
    assert P.resolve_model("judge_a", s) == "claude-old"
    assert P.resolve_model("narrator", s) == "sonnet-old"


def test_disabled_role_raises_instead_of_silently_mocking():
    """🔴 꺼진 역할을 mock으로 대체하면 목 판정이 실판정으로 오인된다."""
    s = _settings(judge_b_provider="")
    assert P.role_enabled("judge_b", s) is False
    with pytest.raises(P.LLMError, match="비활성"):
        P.provider_chain("judge_b", s)


def test_unknown_provider_and_role_fail_loudly():
    with pytest.raises(P.LLMError, match="알 수 없는 provider"):
        P.build_provider("gpt5-turbo-max", "m", _settings())
    with pytest.raises(P.LLMError, match="알 수 없는 역할"):
        P.provider_chain("umpire", _settings())


def test_fallback_chain_is_parsed_from_env():
    s = _settings(judge_a_fallback="gemini,groq:custom-model",
                  gemini_api_key="g", groq_api_key="q")
    chain = P.provider_chain("judge_a", s)
    assert [p.name for p in chain] == ["xai", "gemini", "groq"]
    assert chain[2].model == "custom-model", "체인에서 모델까지 지정할 수 있어야 한다"
    # 🔴 폴백에 모델을 안 적으면 **그 벤더의 기본 모델**을 쓴다.
    #   역할 모델(grok-x)은 1순위 provider의 것이라 물려주면 404가 난다.
    assert chain[1].model.startswith("gemini-"), \
        f"폴백에 다른 벤더 모델명이 갔다: {chain[1].model}"


# ---------------------------------------------------------------- B-1 Mock

@pytest.mark.asyncio
async def test_mock_provider_runs_without_network_or_credit():
    """🔴 크레딧 없이도 개발·테스트가 가능해야 한다."""
    r = await P.MockProvider("none").complete([{"role": "user", "content": "x"}],
                                              schema=SCHEMA)
    assert r.provider == "mock" and r.data is not None
    assert set(r.data) == {"p", "why", "ok", "tags"}
    assert r.data["p"] == 0.0 and r.data["tags"] == [] and r.data["ok"] is False


def test_mock_stub_does_not_fabricate_plausible_values():
    """목 출력이 실데이터로 오인되면 안 된다 — 그럴듯한 값을 만들지 않는다."""
    stub = P.stub_from_schema(SCHEMA)
    assert stub["why"] == "(mock)"
    assert stub["p"] == 0.0, "0.58 같은 그럴듯한 승률을 만들면 안 된다"


# ---------------------------------------------------------------- B-3 구조화

def test_extract_json_handles_fences_and_prose():
    assert P.extract_json('```json\n{"a":1}\n```') == {"a": 1}
    assert P.extract_json('네, 결과입니다: {"a": 2} 이상입니다.') == {"a": 2}
    with pytest.raises(P.LLMParseError):
        P.extract_json("JSON이 없는 산문입니다")


def test_json_instruction_added_only_for_non_native_providers():
    assert "JSON 스키마" in P.json_instruction(SCHEMA)


class _Recorder(P.Provider):
    """네이티브 미지원 provider — 프롬프트 폴백 경로를 본다."""

    name = "rec"
    supports_native_schema = False

    def __init__(self, replies):
        super().__init__("m")
        self.replies, self.seen = list(replies), []

    async def _call(self, system, messages, schema, max_tokens, temperature,
                    thinking=0):
        self.seen.append(system)
        return self.replies.pop(0), None


@pytest.mark.asyncio
async def test_non_native_provider_gets_json_prompt_and_parses():
    p = _Recorder(['{"p": 0.61, "why": "x", "ok": true, "tags": []}'])
    r = await p.complete([{"role": "user", "content": "q"}], schema=SCHEMA)
    assert r.data["p"] == 0.61 and r.attempts == 1
    assert "JSON 스키마" in p.seen[0], "스키마를 프롬프트로 요구하지 않았다"


@pytest.mark.asyncio
async def test_parse_failure_retries_exactly_once_then_fails():
    """🔴 무한 재시도는 비용만 태운다 — 1회만 재요청한다."""
    p = _Recorder(["산문뿐", "여전히 산문"])
    with pytest.raises(P.LLMParseError):
        await p.complete([{"role": "user", "content": "q"}], schema=SCHEMA)
    assert len(p.seen) == 2, f"{len(p.seen)}회 호출 — 정확히 2회여야 한다"
    assert "파싱되지 않았다" in p.seen[1]


@pytest.mark.asyncio
async def test_retry_succeeds_and_reports_attempt_count():
    p = _Recorder(["산문", '{"p":0.5,"why":"y","ok":false,"tags":[]}'])
    r = await p.complete([{"role": "user", "content": "q"}], schema=SCHEMA)
    assert r.attempts == 2 and r.data["why"] == "y"


def test_gemini_schema_strips_unsupported_keys():
    """미지원 키를 남기면 400이 나고, 그 400이 조용한 폴백을 부른다."""
    out = P.gemini_schema(SCHEMA)
    assert "additionalProperties" not in out
    assert set(out["properties"]) == set(SCHEMA["properties"])
    nested = P.gemini_schema({"type": "object", "properties": {
        "x": {"type": "object", "additionalProperties": False,
              "properties": {"y": {"type": "string"}}}}})
    assert "additionalProperties" not in nested["properties"]["x"]


# ---------------------------------------------------------------- B-4 폴백

class _Boom(P.Provider):
    name = "boom"
    supports_native_schema = True

    async def _call(self, *a, **kw):
        raise P.LLMError("죽었다")


class _Fine(P.Provider):
    name = "fine"
    supports_native_schema = True

    async def _call(self, system, messages, schema, max_tokens, temperature,
                    thinking=0):
        return "ok", {"p": 0.7, "why": "z", "ok": True, "tags": []}


@pytest.mark.asyncio
async def test_fallback_records_who_actually_answered(monkeypatch):
    """🔴 조용한 폴백 금지 — 다른 모델이 판정한 사실이 리포트까지 가야 한다."""
    monkeypatch.setattr(P, "provider_chain",
                        lambda role, settings=None: [_Boom("a"), _Fine("b")])
    r = await P.complete("judge_a", [{"role": "user", "content": "q"}], schema=SCHEMA)
    assert r.provider == "fine" and r.data["p"] == 0.7
    assert r.fell_back_from == ("boom",)
    assert "폴백" in r.label and "boom" in r.label


@pytest.mark.asyncio
async def test_no_fallback_leaves_label_clean(monkeypatch):
    monkeypatch.setattr(P, "provider_chain", lambda role, settings=None: [_Fine("b")])
    r = await P.complete("judge_a", [{"role": "user", "content": "q"}], schema=SCHEMA)
    assert r.fell_back_from == () and r.label == "fine/b"


@pytest.mark.asyncio
async def test_whole_chain_failing_raises_with_trail(monkeypatch):
    monkeypatch.setattr(P, "provider_chain",
                        lambda role, settings=None: [_Boom("a"), _Boom("b")])
    with pytest.raises(P.LLMError, match="체인 전부 실패"):
        await P.complete("judge_a", [{"role": "user", "content": "q"}])


@pytest.mark.asyncio
async def test_quota_error_stops_chain_without_fallback(monkeypatch):
    from app.collectors.base import ApiQuotaError
    from app.engine.credit_guard import reset

    reset()
    hit = []

    class Quota(P.Provider):
        name = "anthropic"
        supports_native_schema = True

        async def _call(self, *a, **kw):
            hit.append("anthropic")
            raise ApiQuotaError("anthropic", "credit balance too low")

    class Fine(P.Provider):
        name = "fine"
        supports_native_schema = True

        async def _call(self, *a, **kw):
            hit.append("fine")
            return "ok", {"p": 0.7, "why": "z", "ok": True, "tags": []}

    monkeypatch.setattr(P, "provider_chain",
                        lambda role, settings=None: [Quota("a"), Fine("b")])
    monkeypatch.setattr(P, "_ledger_redis", _noop)
    with pytest.raises(ApiQuotaError):
        await P.complete("judge_a", [{"role": "user", "content": "q"}])
    assert hit == ["anthropic"]
    reset()


# ---------------------------------------------------------------- Gemini 실측 반영

def test_provider_default_model_beats_role_fallback():
    """🔴 provider만 바꿨을 때 **다른 벤더의 모델명이 가면 404**다.

    실측(2026-08-27): INTERPRETER_PROVIDER=gemini 로만 바꿨더니
    'claude-opus-4-6'이 Gemini로 넘어갔다.
    """
    s = _settings(interpreter_provider="gemini", interpreter_model="",
                  judge_model="claude-opus-4-6", gemini_api_key="g")
    assert P.resolve_model("interpreter", s, "gemini").startswith("gemini-")
    chain = P.provider_chain("interpreter", s)
    assert chain[0].model.startswith("gemini-")


def test_fallback_provider_uses_its_own_vendor_model():
    """폴백이 앞 provider의 모델명을 물려받으면 벤더가 바뀌는 순간 404다."""
    s = _settings(judge_a_provider="xai", judge_a_model="grok-x",
                  judge_a_fallback="gemini", gemini_api_key="g")
    chain = P.provider_chain("judge_a", s)
    assert chain[0].model == "grok-x"
    assert chain[1].model.startswith("gemini-"), \
        f"폴백에 앞 벤더 모델명이 갔다: {chain[1].model}"


def test_gemini_default_model_is_not_a_retired_one():
    """🔴 모델명을 추측하지 마라.

    `gemini-2.5-flash`는 신규 사용자에게 제공되지 않는다
    (실측: 404 "no longer available to new users. Please update to gemini-3.6-flash").
    """
    assert P._PROVIDER_DEFAULT_MODEL["gemini"] != "gemini-2.5-flash"
    assert P._PROVIDER_DEFAULT_MODEL["gemini"].startswith("gemini-3")


def test_thinking_budget_is_per_role():
    """🔴 사고 예산을 제어하지 않으면 **답이 아예 안 온다.**

    실측: 300토큰 예산 중 285를 사고가 먹고 content가 비어서 왔다
    (finishReason=MAX_TOKENS). Anthropic max_tokens 32000 사고와 같은 계열.

    짧은 판정(2단·서술·의도)은 끄고, 추론이 필요한 3단만 켠다.
    """
    s = _settings()
    assert P.thinking_budget("interpreter", s) == 0, "2단은 사고를 꺼야 한다"
    assert P.thinking_budget("narrator", s) == 0
    assert P.thinking_budget("intent", s) == 0
    assert P.thinking_budget("judge_a", s) > 0, "3단은 사고가 필요하다"
    assert P.thinking_budget("judge_b", s) > 0


@pytest.mark.asyncio
async def test_budget_starvation_is_classified_not_silent(monkeypatch):
    """🔴 조용한 빈 응답은 **목 출력과 구분되지 않는다.**

    "판정 0건"의 원인을 영영 못 찾는다 → 전용 예외 + 알림.
    """
    class _Starved(P.Provider):
        name = "starved"
        supports_native_schema = True

        async def _call(self, *a, **kw):
            raise P.LLMBudgetError("사고가 285토큰 소모, 본문 0자")

    sent = []
    monkeypatch.setattr(P, "provider_chain", lambda role, settings=None: [_Starved("m")])
    monkeypatch.setattr(P, "_notify_budget",
                        lambda *a, **k: sent.append(a) or _noop())
    with pytest.raises(P.LLMError, match="체인 전부 실패"):
        await P.complete("judge_a", [{"role": "user", "content": "q"}])
    assert sent, "예산 부족인데 알림이 안 갔다"


async def _noop():
    return None


@pytest.mark.asyncio
async def test_disabled_provider_is_skipped_without_http(monkeypatch):
    """disabled_providers에 있는 벤더는 HTTP를 나가지 않고 다음으로 간다."""
    hit = []

    class Boom(P.Provider):
        name = "groq"
        supports_native_schema = True

        async def _call(self, *a, **kw):
            hit.append("groq")
            raise RuntimeError("disabled provider must not be called")

    class Ok(P.Provider):
        name = "anthropic"
        supports_native_schema = True

        async def _call(self, *a, **kw):
            hit.append("anthropic")
            return '{"p": 0.6, "why": "x", "ok": true, "tags": []}', {
                "p": 0.6, "why": "x", "ok": True, "tags": []}

    s = _settings(disabled_providers="groq,gemini")
    monkeypatch.setattr(P, "provider_chain", lambda *a, **k: [Boom("m"), Ok("m")])
    monkeypatch.setattr(P, "_ledger_redis", _noop)
    res = await P.complete("interpreter", [{"role": "user", "content": "q"}],
                           settings=s)
    assert hit == ["anthropic"]
    assert res.provider == "anthropic"
    assert "groq(disabled)" in res.fell_back_from


def test_force_mock_blocks_every_provider():
    """🔴 절대 규칙 3 — 강제 목 모드에서는 **어떤 벤더도** 실제로 호출되지 않는다.

    실사고 2026-08-27: gemini·groq를 추가하면서 이 게이트를 빠뜨렸다.
    config의 mock_* 프로퍼티는 anthropic·pplx·xai만 막고 있었고,
    provider_chain은 force_mock을 아예 보지 않았다 — 테스트가 실제로 Groq를
    쳐서 429 재시도로 스위트가 멈춰 섰다.
    provider를 새로 추가할 때 이 테스트가 먼저 깨져야 한다.
    """
    from app.config import Settings
    from app.llm.provider import MockProvider, provider_chain

    s = Settings(force_mock=True, interpreter_provider="groq",
                 interpreter_fallback="gemini,xai",
                 groq_api_key="x", gemini_api_key="y", xai_api_key="z")
    chain = provider_chain("interpreter", s)
    assert all(isinstance(p, MockProvider) for p in chain), \
        f"실 provider가 새어 나갔다: {[type(p).__name__ for p in chain]}"


def test_force_mock_still_respects_disabled_role():
    """목 모드라고 꺼진 역할을 켜주지는 않는다 — 목 판정을 실판정으로 오인하면 안 된다."""
    import pytest

    from app.config import Settings
    from app.llm.provider import LLMError, provider_chain

    s = Settings(force_mock=True, judge_b_provider="")
    with pytest.raises(LLMError):
        provider_chain("judge_b", s)


# ── [GRD-1 2026-09-11 사용자 지시] 크레딧 소진이 조용히 지나갔다 ───────────
#   🔴 실사고 2026-09-10: Gemini 가 429 본문
#        "Your prepayment credits are depleted … RESOURCE_EXHAUSTED"
#      로 죽었는데 **아무 경보도 안 나갔다.** KBO 4/4 · NPB 6/6 판정 0건이
#      됐고, 내가 직접 파보기 전까지 아무도 몰랐다.
#      `api:blocked:*` 에도 gemini 가 없었다 — 워치독이 볼 수가 없었다.
#
#   원인: `_mark_exhausted` 는 **파이썬 dict** 에만 쓴다.
#        Redis 차단 키도, 텔레그램 알림도, 재기동 후 기억도 없다.
#        `api_guard.trip_credit` 이 그 셋을 이미 다 하는데 LLM 경로가 안 부른다.
#
#   ⚠️ **일일 한도와 크레딧 소진은 다르다.**
#      groq TPD 200k 소진은 **내일 풀린다** — 영구 차단하면 멀쩡한 provider 를
#      사람이 손으로 풀 때까지 버리는 것이다(차단은 시간으로 안 풀린다).
#      크레딧 소진만 `trip_credit` 대상이다.

def test_credit_wording_is_recognized():
    """실제 응답 문구로 맞춘다 — 추측한 문구는 안 맞는다(모듈 주석의 교훈)."""
    from app.llm.provider import _looks_credit

    real = ("gemini: {'error': {'code': 429, 'message': 'Your prepayment "
            "credits are depleted. Please go to AI Studio…', "
            "'status': 'RESOURCE_EXHAUSTED'}}")
    assert _looks_credit(Exception(real)), "실측 gemini 크레딧 문구를 못 잡는다"
    anthropic = "Your credit balance is too low to access the Anthropic API"
    assert _looks_credit(Exception(anthropic))


def test_daily_ratelimit_is_not_credit():
    """⚠️ 반대 위험 — TPD 소진은 **내일 풀린다.** 영구 차단하면 안 된다."""
    from app.llm.provider import _looks_credit, _looks_daily

    tpd = ("groq 레이트리밋: Rate limit reached for model `openai/gpt-oss-120b` "
           "on tokens per day (TPD): Limit 200000, Used 198512. "
           "Please try again in 37m1.776s")
    assert _looks_daily(Exception(tpd)), "일일 한도로는 잡아야 한다"
    assert not _looks_credit(Exception(tpd)), "TPD 를 크레딧으로 오분류했다"

    otpm = ("Request too large … on output tokens per minute (OTPM): "
            "Limit 1000, Requested 1837")
    assert not _looks_credit(Exception(otpm)), "분당 한도를 크레딧으로 오분류했다"


@pytest.mark.asyncio
async def test_credit_exhaustion_trips_the_block(monkeypatch):
    """크레딧 소진이면 Redis 차단 + 알림 경로(`trip_credit`)를 탄다."""
    import app.llm.provider as P

    seen = {}

    async def fake_trip(name, detail):
        seen["name"], seen["detail"] = name, detail
        return True

    monkeypatch.setattr("app.api_guard.trip_credit", fake_trip)
    P.reset_exhausted()
    await P._note_exhaustion("gemini", Exception(
        "Your prepayment credits are depleted. RESOURCE_EXHAUSTED"))
    assert seen.get("name") == "gemini", f"차단 경로를 안 탔다: {seen}"
    assert P._is_exhausted("gemini"), "프로세스 내 건너뛰기도 유지돼야 한다"


@pytest.mark.asyncio
async def test_daily_limit_does_not_trip_the_block(monkeypatch):
    """⚠️ 반대 위험 — 일일 한도는 차단하지 않는다(프로세스 내 건너뛰기만)."""
    import app.llm.provider as P

    called = {"n": 0}

    async def fake_trip(name, detail):
        called["n"] += 1
        return True

    monkeypatch.setattr("app.api_guard.trip_credit", fake_trip)
    P.reset_exhausted()
    await P._note_exhaustion("groq", Exception(
        "Rate limit reached … tokens per day (TPD): Limit 200000"))
    assert called["n"] == 0, "TPD 로 영구 차단을 걸었다"
    assert P._is_exhausted("groq"), "이 프로세스에서는 건너뛰어야 한다"


@pytest.mark.asyncio
async def test_explicit_quota_error_also_trips(monkeypatch):
    """400-크레딧(anthropic 류) 명시 예외도 차단·알림까지 간다."""
    import app.llm.provider as P

    seen = {}

    async def fake_trip(name, detail):
        seen["name"] = name
        return True

    monkeypatch.setattr("app.api_guard.trip_credit", fake_trip)
    P.reset_exhausted()
    await P._note_exhaustion("anthropic", Exception(
        "Your credit balance is too low to access the Anthropic API"))
    assert seen.get("name") == "anthropic"
