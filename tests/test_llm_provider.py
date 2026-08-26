"""[B-1~B-4] LLM provider 추상화.

성공 기준은 하나다: **코드를 고치지 않고 .env만 바꿔 provider를 갈아끼울 수
있는가.** 나머지 테스트는 그 과정에서 조용히 틀어지는 것을 막는다.
"""

import json

import pytest

from app.config import Settings
from app.llm import provider as P


def _settings(**over):
    base = dict(interpreter_provider="mock", judge_a_provider="anthropic",
                judge_a_model="claude-x", judge_b_provider="",
                narrator_provider="anthropic", anthropic_api_key="k")
    base.update(over)
    return Settings(**base)


SCHEMA = {"type": "object",
          "properties": {"p": {"type": "number"}, "why": {"type": "string"},
                         "ok": {"type": "boolean"}, "tags": {"type": "array"}},
          "required": ["p", "why", "ok", "tags"], "additionalProperties": False}


# ---------------------------------------------------------------- B-2 라우팅

def test_env_alone_switches_provider():
    """🔴 이 작업의 성공 기준 — 코드 수정 없이 provider가 바뀌어야 한다."""
    a = P.provider_chain("judge_a", _settings(judge_a_provider="anthropic"))
    g = P.provider_chain("judge_a", _settings(judge_a_provider="gemini",
                                              gemini_api_key="g"))
    o = P.provider_chain("judge_a", _settings(judge_a_provider="ollama"))
    assert [p.name for p in (a[0], g[0], o[0])] == ["anthropic", "gemini", "ollama"]
    assert isinstance(a[0], P.AnthropicProvider)
    assert isinstance(g[0], P.GeminiProvider)
    assert isinstance(o[0], P.OpenAICompatProvider)


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
    s = _settings(judge_a_fallback="gemini,groq:llama-3.3-70b",
                  gemini_api_key="g", groq_api_key="q")
    chain = P.provider_chain("judge_a", s)
    assert [p.name for p in chain] == ["anthropic", "gemini", "groq"]
    assert chain[2].model == "llama-3.3-70b", "체인에서 모델까지 지정할 수 있어야 한다"
    assert chain[1].model == "claude-x", "모델 미지정이면 역할 기본 모델을 쓴다"


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

    async def _call(self, system, messages, schema, max_tokens, temperature):
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

    async def _call(self, system, messages, schema, max_tokens, temperature):
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
