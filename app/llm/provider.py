"""[B-1~B-4] LLM provider 추상화.

**성공 기준: 코드를 고치지 않고 `.env`만 바꿔 Anthropic ↔ Gemini ↔ 자체호스팅
전환이 되어야 한다.** 그래서 호출부는 provider를 직접 알지 못하고 **역할**
(interpreter / judge_a / judge_b / narrator)만 안다.

왜 필요한가:
  판정·해석·서술이 각각 특정 SDK에 묶여 있었다. 크레딧이 끊기면 개발도 테스트도
  멈추고, "다른 모델이 더 나은가"를 물어볼 수도 없다. 역할과 구현을 끊는다.

⚠️ **어느 provider가 응답했는지 반드시 기록한다.** 폴백이 조용히 일어나면
   판정 품질이 바뀐 것을 아무도 모른다 — 그것이 정확히 우리가 겪은 유형의 사고다.
   `LLMResult.provider`가 리포트·predictions까지 따라간다.

⚠️ 구조화 출력 방식은 provider마다 다르다(tool_use / JSON mode / function calling).
   인터페이스에서 흡수하고, 미지원이면 **JSON 프롬프트 + 파싱 검증**으로 폴백한다.
   파싱이 실패하면 1회만 재요청하고 그래도 실패하면 실패로 둔다 — 무한 재시도는
   비용만 태운다.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# 역할 — 호출부는 이것만 안다.
ROLES = ("interpreter", "judge_a", "judge_b", "narrator")


class LLMError(RuntimeError):
    """provider 호출 실패."""


class LLMParseError(LLMError):
    """응답은 왔으나 구조화 결과를 꺼낼 수 없다."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    data: dict | None
    provider: str
    model: str
    attempts: int = 1
    fell_back_from: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """리포트에 찍을 표기. 폴백이 있었으면 그 사실이 보여야 한다."""
        base = f"{self.provider}/{self.model}"
        return f"{base} (폴백: {'→'.join(self.fell_back_from)}→{self.provider})" \
            if self.fell_back_from else base


# ---------------------------------------------------------------- 공통 도구

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict:
    """산문에 섞인 JSON 객체를 꺼낸다. 실패하면 LLMParseError."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|```$", "", raw).strip()
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        pass
    m = _JSON_BLOCK.search(raw)
    if m:
        try:
            return json.loads(m.group(0))
        except (TypeError, ValueError) as exc:
            raise LLMParseError(f"JSON 파싱 실패: {raw[:200]}") from exc
    raise LLMParseError(f"응답에 JSON이 없다: {raw[:200]}")


def json_instruction(schema: dict) -> str:
    """구조화 출력을 지원하지 않는 provider용 프롬프트 보강."""
    return ("\n\n반드시 아래 JSON 스키마에 맞는 **JSON 객체 하나만** 출력하라. "
            "설명·코드펜스·머리말을 붙이지 마라.\n"
            + json.dumps(schema, ensure_ascii=False))


# ---------------------------------------------------------------- 인터페이스


class Provider(ABC):
    """모든 LLM 호출의 단일 창구."""

    name: str = "base"
    #: 네이티브 구조화 출력을 지원하는가. False면 JSON 프롬프트로 폴백한다.
    supports_native_schema: bool = False

    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 120.0):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    @abstractmethod
    async def _call(self, system: str, messages: list[dict], schema: dict | None,
                    max_tokens: int, temperature: float) -> tuple[str, dict | None]:
        """(본문 텍스트, 구조화 결과 or None)."""

    async def complete(self, messages: list[dict], *, system: str = "",
                       schema: dict | None = None, max_tokens: int = 4096,
                       temperature: float = 0.0) -> LLMResult:
        """구조화 응답. schema를 주면 `data`가 채워진다.

        네이티브 미지원 provider는 프롬프트로 JSON을 요구하고 파싱한다.
        파싱 실패 시 **1회만** 재요청한다.
        """
        msgs = list(messages)
        sys = system
        if schema and not self.supports_native_schema:
            sys = (sys + json_instruction(schema)).strip()
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                text, data = await self._call(sys, msgs, schema, max_tokens, temperature)
                if schema and data is None:
                    data = extract_json(text)
                return LLMResult(text=text, data=data, provider=self.name,
                                 model=self.model, attempts=attempt)
            except LLMParseError as exc:
                last = exc
                if attempt == 2:
                    break
                logger.warning("[llm:%s] 구조화 파싱 실패 — 1회 재요청: %s", self.name, exc)
                sys = (sys + "\n\n이전 응답이 파싱되지 않았다. JSON 객체 **하나만** 출력하라.")
        raise LLMParseError(f"{self.name}/{self.model}: 재요청 후에도 파싱 실패") from last


# ---------------------------------------------------------------- 구현체


class MockProvider(Provider):
    """LLM 호출 0회. **크레딧 없이도 전 파이프라인이 완주해야 한다.**"""

    name = "mock"
    supports_native_schema = True

    async def _call(self, system, messages, schema, max_tokens, temperature):
        if schema:
            return "", stub_from_schema(schema)
        return "(mock 응답)", None


class AnthropicProvider(Provider):
    name = "anthropic"
    supports_native_schema = True

    async def _call(self, system, messages, schema, max_tokens, temperature):
        import anthropic

        from app.collectors.base import ApiQuotaError
        from app.research.perplexity import is_quota_error

        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        kwargs: dict[str, Any] = {
            "model": self.model, "max_tokens": max_tokens,
            "temperature": temperature, "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if schema:
            kwargs["tools"] = [{"name": "result", "description": "구조화 결과 제출",
                                "input_schema": schema}]
            kwargs["tool_choice"] = {"type": "tool", "name": "result"}
        try:
            resp = await client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            if is_quota_error(exc.status_code, str(exc)):
                raise ApiQuotaError("anthropic", str(exc)) from exc
            raise LLMError(f"anthropic: {exc}") from exc
        text = "".join(b.text for b in resp.content if b.type == "text")
        data = next((b.input for b in resp.content
                     if b.type == "tool_use" and b.name == "result"), None)
        if schema and data is None:
            raise LLMParseError("anthropic: tool_use 블록 없음")
        return text, data


class GeminiProvider(Provider):
    """Google Gemini — REST. SDK 없이 httpx로 호출한다(의존성 추가 없음)."""

    name = "gemini"
    supports_native_schema = True
    DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"

    async def _call(self, system, messages, schema, max_tokens, temperature):
        import httpx

        from app.collectors.base import ApiQuotaError

        base = self.base_url or self.DEFAULT_BASE
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens,
                                 "temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = gemini_schema(schema)
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{base}/models/{self.model}:generateContent",
                             params={"key": self.api_key}, json=body)
        if r.status_code in (429, 402) or "quota" in r.text.lower():
            raise ApiQuotaError("gemini", r.text[:300])
        if r.status_code >= 400:
            raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}")
        cands = (r.json().get("candidates") or [])
        text = "".join(p.get("text", "")
                       for cand in cands[:1]
                       for p in ((cand.get("content") or {}).get("parts") or []))
        return text, (extract_json(text) if schema else None)


class OpenAICompatProvider(Provider):
    """OpenAI 호환 `/chat/completions` — Groq · DeepSeek · Ollama · xAI 공통.

    **base_url만 바꾸면 된다.** 셋을 각각 구현하면 같은 버그를 세 번 고치게 된다.
    """

    name = "openai_compat"
    supports_native_schema = True

    async def _call(self, system, messages, schema, max_tokens, temperature):
        import httpx

        from app.collectors.base import ApiQuotaError

        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body: dict[str, Any] = {"model": self.model, "messages": msgs,
                                "max_tokens": max_tokens, "temperature": temperature}
        if schema:
            body["tools"] = [{"type": "function",
                              "function": {"name": "result",
                                           "description": "구조화 결과 제출",
                                           "parameters": schema}}]
            body["tool_choice"] = {"type": "function", "function": {"name": "result"}}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(f"{self.base_url.rstrip('/')}/chat/completions",
                             headers=headers, json=body)
        if r.status_code in (402, 429) or "credit" in r.text.lower():
            raise ApiQuotaError(self.name, r.text[:300])
        if r.status_code >= 400:
            raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}")
        choice = ((r.json().get("choices") or [{}])[0].get("message") or {})
        text = choice.get("content") or ""
        data = None
        for call in choice.get("tool_calls") or []:
            args = (call.get("function") or {}).get("arguments")
            data = args if isinstance(args, dict) else extract_json(args or "")
            break
        if schema and data is None:
            data = extract_json(text)      # JSON mode로 답한 경우
        return text, data


# ---------------------------------------------------------------- 스키마 보조


def gemini_schema(schema: dict) -> dict:
    """Gemini responseSchema는 JSON Schema 전체를 받지 않는다 — 미지원 키를 뗀다.

    ⚠️ 떼지 않으면 400이 나고, 그 400이 폴백을 유발해 **다른 모델이 조용히
       판정하게 된다.** 실패는 요란해야 한다.
    """
    drop = {"additionalProperties", "strict", "$schema", "definitions", "$defs"}
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k not in drop}
    if isinstance(out.get("properties"), dict):
        out["properties"] = {k: gemini_schema(v) for k, v in out["properties"].items()}
    if isinstance(out.get("items"), dict):
        out["items"] = gemini_schema(out["items"])
    return out


def stub_from_schema(schema: dict) -> Any:
    """스키마 모양의 결정적 더미. MockProvider 전용.

    ⚠️ 그럴듯한 값을 만들지 않는다 — 목 출력이 실데이터로 오인되면 안 된다.
    """
    t = (schema or {}).get("type")
    if t == "object":
        props = schema.get("properties") or {}
        req = schema.get("required") or list(props)
        return {k: stub_from_schema(props[k]) for k in req if k in props}
    if t == "array":
        return []
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if enum := (schema or {}).get("enum"):
        return enum[0]
    return "(mock)"


# ---------------------------------------------------------------- 라우팅 (B-2)


_KIND_TO_CLASS = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "mock": MockProvider,
    # 아래는 전부 OpenAI 호환 — base_url만 다르다
    "groq": OpenAICompatProvider,
    "deepseek": OpenAICompatProvider,
    "ollama": OpenAICompatProvider,
    "xai": OpenAICompatProvider,
    "openai_compat": OpenAICompatProvider,
}

# base_url 기본값. .env로 덮을 수 있다(자체호스팅 주소 등).
_DEFAULT_BASE = {
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "xai": "https://api.x.ai/v1",
}


def build_provider(kind: str, model: str, settings=None) -> Provider:
    """provider 종류·모델명 → 인스턴스. 알 수 없는 종류면 LLMError."""
    s = settings or get_settings()
    kind = (kind or "").strip().lower()
    cls = _KIND_TO_CLASS.get(kind)
    if cls is None:
        raise LLMError(f"알 수 없는 provider: {kind!r} "
                       f"(가능: {', '.join(sorted(_KIND_TO_CLASS))})")
    key = {
        "anthropic": s.anthropic_api_key, "gemini": getattr(s, "gemini_api_key", None),
        "groq": getattr(s, "groq_api_key", None),
        "deepseek": getattr(s, "deepseek_api_key", None),
        "xai": s.xai_api_key, "ollama": None, "mock": None,
    }.get(kind)
    base = getattr(s, f"{kind}_base_url", None) or _DEFAULT_BASE.get(kind)
    inst = cls(model=model, api_key=key, base_url=base)
    if cls is OpenAICompatProvider:
        inst.name = kind           # 어느 호환 백엔드였는지 기록에 남긴다
    return inst


# 역할별 모델 기본값 — `*_MODEL`이 비어 있을 때 쓸 기존 설정.
# 새 설정을 안 넣어도 **종전 동작이 그대로 유지**되게 한다.
_ROLE_MODEL_FALLBACK = {"judge_a": "judge_model", "judge_b": "judge_model",
                        "narrator": "report_model", "interpreter": "judge_model"}


def role_enabled(role: str, settings=None) -> bool:
    """그 역할이 켜져 있는가. `*_PROVIDER`가 비면 꺼진 것이다.

    ⚠️ 꺼진 역할을 mock으로 대체하지 않는다 — 목 판정이 실판정으로 오인되면
       "판정이 됐다"고 착각한 채 리포트가 나간다(실제로 겪은 유형의 사고다).
    """
    return bool((getattr(settings or get_settings(), f"{role}_provider", "") or "").strip())


def resolve_model(role: str, settings=None) -> str:
    s = settings or get_settings()
    return ((getattr(s, f"{role}_model", "") or "").strip()
            or getattr(s, _ROLE_MODEL_FALLBACK.get(role, ""), "") or "")


def provider_chain(role: str, settings=None) -> list[Provider]:
    """역할 → provider 폴백 체인. 첫 번째가 기본, 나머지는 폴백.

    설정 예: `JUDGE_A_PROVIDER=anthropic` · `JUDGE_A_FALLBACK=gemini,groq`
    """
    if role not in ROLES:
        raise LLMError(f"알 수 없는 역할: {role!r} (가능: {', '.join(ROLES)})")
    s = settings or get_settings()
    kind = (getattr(s, f"{role}_provider", "") or "").strip()
    if not kind:
        raise LLMError(f"역할 {role}이(가) 비활성이다 — {role.upper()}_PROVIDER 미설정")
    model = resolve_model(role, s)
    chain = [build_provider(kind, model, s)]
    raw = getattr(s, f"{role}_fallback", "") or ""
    for spec in [x.strip() for x in raw.split(",") if x.strip()]:
        k, _, m = spec.partition(":")
        chain.append(build_provider(k, m or model, s))
    return chain


async def complete(role: str, messages: list[dict], *, system: str = "",
                   schema: dict | None = None, max_tokens: int = 4096,
                   temperature: float = 0.0, settings=None) -> LLMResult:
    """역할로 호출한다. 실패하면 폴백 체인을 따라가고 **누가 답했는지 기록한다.**

    ⚠️ 조용한 폴백 금지. 판정 품질이 provider마다 다를 수 있으므로
       "어느 모델이 이 판정을 했는가"가 리포트·DB까지 따라가야 한다.
    """
    chain = provider_chain(role, settings)
    tried: list[str] = []
    last: Exception | None = None
    for p in chain:
        try:
            res = await p.complete(messages, system=system, schema=schema,
                                   max_tokens=max_tokens, temperature=temperature)
            if tried:
                logger.warning("[llm:%s] 폴백 — %s 실패 후 %s 응답",
                               role, "→".join(tried), p.name)
                return LLMResult(res.text, res.data, res.provider, res.model,
                                 res.attempts, tuple(tried))
            return res
        except Exception as exc:       # 다음 provider로 넘어간다
            logger.warning("[llm:%s] %s/%s 실패: %s", role, p.name, p.model, exc)
            tried.append(p.name)
            last = exc
    raise LLMError(f"역할 {role}: 체인 전부 실패 ({'→'.join(tried)})") from last
