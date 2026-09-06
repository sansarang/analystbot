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

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

from app.llm import ledger as _ledger      # noqa: E402  (순환 import 회피)

# 역할 — 호출부는 이것만 안다.
ROLES = ("interpreter", "judge_a", "judge_b", "narrator", "intent")


class LLMError(RuntimeError):
    """provider 호출 실패."""


class LLMParseError(LLMError):
    """응답은 왔으나 구조화 결과를 꺼낼 수 없다."""


class LLMBudgetError(LLMError):
    """[§9] **예산 부족** — 사고 토큰이 출력 예산을 잠식해 답이 오지 않았다.

    ⚠️ 이것을 조용한 빈 응답으로 넘기면 **목 출력과 구분되지 않는다.**
       "판정 0건"의 원인을 영영 못 찾는다. 별도 예외로 올려 알림까지 간다.
       재시도해도 같은 결과다 — 예산을 올리거나 사고를 줄여야 한다.
    """


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
                    max_tokens: int, temperature: float,
                    thinking: int = 0) -> tuple[str, dict | None]:
        """(본문 텍스트, 구조화 결과 or None).

        `thinking`: 사고 토큰 예산. -1=모델 자율 · 0=끔 · 양수=그만큼.
        provider가 자기 방식으로 매핑하고, 해당 개념이 없으면 무시한다.
        """

    async def complete(self, messages: list[dict], *, system: str = "",
                       schema: dict | None = None, max_tokens: int = 4096,
                       temperature: float = 0.0, thinking: int = 0) -> LLMResult:
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
                text, data = await self._call(sys, msgs, schema, max_tokens,
                                              temperature, thinking)
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

    async def _call(self, system, messages, schema, max_tokens, temperature, thinking=0):
        if schema:
            return "", stub_from_schema(schema)
        return "(mock 응답)", None


# 🔴 [2026-09-06 사용자 지시] **AnthropicProvider 를 지웠다.**
#    "2차 판정만 안트로픽 사용하고 관련없는 거는 빼라."
#    이 클래스는 역할 체인(`provider_chain`)용이었다 — interpreter·judge_a·
#    narrator·intent 가 여기로 갔다. 2차 판정과는 **무관한 경로**다:
#    최종 판정은 `team_form.complete_json` 이 Anthropic SDK 를 직접 부른다.
#    기본값에서 빼는 것만으로는 부족하다. 종전에도 운영 env 가 덮고 있었을
#    뿐 코드는 열려 있었고, 덮개 없는 환경에서 그대로 새어 나갔다 —
#    실측 2026-09-06: `interpreter` 의 400(credit) 이 `trip_credit` 으로
#    번져 NC 최종 판정을 막았다. 이제 **경로 자체가 없다.**
#    되살리려면 이 클래스와 `_KIND_TO_CLASS` 항목을 함께 되돌려야 한다.


def _S():
    return get_settings()


class _Throttle:
    """provider별 호출 간격. **무료 티어는 대부분 분당 제한이다.**

    2단 해석봇은 경기당 2콜(팀별)이라 슬레이트를 돌리면 연속으로 나간다.
    간격이 없으면 곧바로 429를 맞고, 폴백이 연쇄로 소모된다.
    """

    def __init__(self):
        self._last: dict[str, float] = {}
        self._gate = asyncio.Lock()

    async def wait(self, key: str, interval: float) -> None:
        if interval <= 0:
            return
        import time

        async with self._gate:
            gap = interval - (time.monotonic() - self._last.get(key, 0.0))
            if gap > 0:
                await asyncio.sleep(gap)
            self._last[key] = time.monotonic()


_THROTTLE = _Throttle()


def retry_wait_cap(timeout: float) -> float:
    """이 요청에서 429를 **기다려도 되는 최대 시간**.

    근거는 임의값이 아니라 **한 번의 호출 타임아웃**이다. 한 번 부르는 것보다
    오래 기다려야 한다면 그 provider는 이 요청에 대해 사용 불가이고, 기다리는
    것보다 **다음 provider로 넘어가는 것이 항상 빠르다.**

    ⚠️ 실사고 2026-08-27: Groq가 `Retry-After: 1182`(20분)를 돌려줬고 코드가
       그대로 잤다. 사용자 요청 하나가 20분을 잡았다. Retry-After를 무조건
       따르는 것은 배치 작업의 예의이지 대화형 요청의 규율이 아니다.
    """
    return float(timeout)


def _retry_after(headers) -> float | None:
    """429 응답의 Retry-After(초). 없으면 None."""
    v = (headers or {}).get("retry-after") or (headers or {}).get("Retry-After")
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


class GeminiProvider(Provider):
    """Google Gemini — REST. SDK 없이 httpx로 호출한다(의존성 추가 없음).

    ⚠️ 무료 티어는 **분당 제한**이다(실측 2026-08-27: 4콜 만에 429가 났다가
       몇 분 뒤 풀렸다 — 소진이 아니었다). Perplexity와 같은 방식으로
       호출 간격을 둔다. 간격이 없으면 배칭한 5칸 호출이 연달아 나가며
       바로 429를 맞는다.
    """

    name = "gemini"
    supports_native_schema = True
    DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"
    async def _throttle(self) -> None:
        await _THROTTLE.wait("gemini", _S().gemini_min_interval)

    async def _call(self, system, messages, schema, max_tokens, temperature, thinking=0):
        import httpx

        from app.collectors.base import ApiQuotaError

        base = self.base_url or self.DEFAULT_BASE
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages]
        gen: dict[str, Any] = {"maxOutputTokens": max_tokens,
                               "temperature": temperature}
        # ⚠️ **사고 예산을 제어하지 않으면 답이 안 온다.** Gemini 3.x는 사고형이라
        #    사고가 max_tokens를 다 먹고 `finishReason=MAX_TOKENS` + 빈 content로
        #    끝난다(실측 2026-08-27: 300 중 285를 사고가 소모).
        #    이 프로젝트가 Anthropic에서 겪은 max_tokens 사고와 **같은 유형**이다.
        # ⚠️ 0은 그대로 보내면 안 된다 — gemini-3.6-flash는 400으로 거부한다.
        #   "사고를 최소로"는 **최소 양수**를 보내는 것으로 구현한다.
        if thinking >= 0:
            budget = thinking if thinking > 0 else _S().gemini_min_thinking
            gen["thinkingConfig"] = {"thinkingBudget": budget}
        body: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = gemini_schema(schema)
        await self._throttle()
        url = f"{base}/models/{self.model}:generateContent"
        # 5xx(과부하)는 재시도한다 — Gemini는 503 UNAVAILABLE을 흔하게 낸다.
        # ⚠️ 4xx는 재시도하지 않는다. 모델명 오타·키 오류를 반복 호출해도
        #    같은 답이 오고 쿼터만 태운다.
        last = None
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            rate_left = _S().llm_rate_retries
            for delay in (0, 2, 6):
                if delay:
                    await asyncio.sleep(delay)
                r = await c.post(url, params={"key": self.api_key}, json=body)
                last = r
                # 429는 **분당 제한**일 수 있다(실측: 몇 분 뒤 풀렸다).
                # Retry-After가 오면 그것을 따르고, 없으면 짧게 기다린다.
                if r.status_code == 429 and rate_left > 0:
                    wait = _retry_after(r.headers) or 20.0
                    cap = retry_wait_cap(self.timeout)
                    if wait > cap:
                        logger.warning("[gemini] 429 — %.0fs 대기 요구(상한 %.0fs) "
                                       "→ 기다리지 않고 폴백", wait, cap)
                        break
                    rate_left -= 1
                    logger.warning("[gemini] 429 — %.0fs 후 재시도 (남은 %d회)",
                                   wait, rate_left)
                    await asyncio.sleep(wait)
                    continue
                if r.status_code < 500:
                    break
                logger.warning("[gemini] HTTP %d — %ds 후 재시도", r.status_code, delay or 2)
        r = last
        if r.status_code in (429, 402) or "quota" in r.text.lower():
            raise ApiQuotaError("gemini", r.text[:300])
        if r.status_code == 404:
            raise LLMError(f"gemini: 모델 '{self.model}'을 찾을 수 없다. "
                           f"`tools/check_llm.py`로 사용 가능한 모델을 확인하라")
        if r.status_code >= 400:
            raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}")

        data = r.json()
        # 안전 필터에 걸리면 candidates가 **비어서** 온다. 200 OK인데 내용이 없다 —
        # 조용히 빈 결과로 넘기면 "판정 0건"의 원인을 영영 못 찾는다.
        block = ((data.get("promptFeedback") or {}).get("blockReason"))
        if block:
            raise LLMError(f"gemini: 프롬프트가 안전 필터에 차단됨 ({block})")
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError(f"gemini: 후보 응답 없음 — {str(data)[:200]}")
        cand = cands[0]
        text = "".join(p.get("text", "")
                       for p in ((cand.get("content") or {}).get("parts") or []))
        finish = cand.get("finishReason")
        thoughts = (data.get("usageMetadata") or {}).get("thoughtsTokenCount") or 0
        if finish == "MAX_TOKENS" or not text.strip():
            # 재요청해도 같은 결과다 — 예산을 올리거나 사고를 줄여야 한다.
            raise LLMBudgetError(
                f"gemini/{self.model}: 예산 부족 — 출력 {max_tokens}토큰 중 "
                f"사고가 {thoughts}토큰 소모, 본문 {len(text)}자 "
                f"(finish={finish}). 사고 예산({thinking})을 줄이거나 "
                f"max_tokens를 올려라")
        if finish and finish not in ("STOP", "MAX_TOKENS"):
            raise LLMError(f"gemini: 비정상 종료 ({finish})")
        return text, (extract_json(text) if schema else None)


#: 툴 호출이 **거부된** 400 인가. 진짜 잘못된 요청(스키마 오류 등)과 구분한다.
#  🔴 문구는 실측한 응답에서 왔다 — 상상해 넣지 않았다:
#     "Tool call validation failed: attempted to call tool 'json' which was
#      not in request.tools" (groq openai/gpt-oss-120b, 2026-09-04)
_TOOL_REJECT_MARKS = ("tool_use_failed", "tool call validation failed",
                      "attempted to call tool")


def _tool_call_rejected(body: str) -> bool:
    low = (body or "").lower()
    return any(m in low for m in _TOOL_REJECT_MARKS)


class OpenAICompatProvider(Provider):
    """OpenAI 호환 `/chat/completions` — Groq · DeepSeek · Ollama · xAI 공통.

    **base_url만 바꾸면 된다.** 셋을 각각 구현하면 같은 버그를 세 번 고치게 된다.
    """

    name = "openai_compat"
    supports_native_schema = True

    async def _call(self, system, messages, schema, max_tokens, temperature, thinking=0):
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
        await _THROTTLE.wait(self.name, _S().openai_compat_min_interval)
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        rate_left = _S().llm_rate_retries
        tool_left = 1          # 툴 호출이 거부되면 표준 구조화 출력으로 1회 강등
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            while True:
                r = await c.post(url, headers=headers, json=body)
                # 🔴 [실측 2026-09-04] Groq `openai/gpt-oss-120b` 는 강제 함수호출
                #    (`tool_choice`)에서 **자기 내부 `json` 툴을 대신 부른다**:
                #      400 "Tool call validation failed: attempted to call tool
                #           'json' which was not in request.tools"
                #    입력에 따라 나기도 안 나기도 하는 간헐 결함이라 후보를
                #    통째로 버릴 수 없다. 표준 구조화 출력으로 한 번 강등한다 —
                #    같은 모델·같은 스키마로 `response_format: json_schema` 는
                #    두 번 다 200 이었다(실측).
                #    ⚠️ 이 경로가 죽으면 narrator·interpreter·intent 가 전부
                #       gemini 로 몰려 429 가 나고, 그 429 가 credit 으로
                #       오분류돼 체인이 통째로 멈췄다(W-LLM-FAIL 24회).
                if (r.status_code == 400 and schema and tool_left > 0
                        and _tool_call_rejected(r.text)):
                    tool_left -= 1
                    body.pop("tools", None)
                    body.pop("tool_choice", None)
                    body["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": "result", "schema": schema}}
                    logger.warning("[%s] 툴 호출 거부 — 표준 구조화 출력으로 재시도",
                                   self.name)
                    continue
                # ⚠️ 429를 크레딧 소진으로 오분류하면 **잔액이 있는데 폴백**한다.
                #    이 프로젝트가 Perplexity에서 이미 겪은 사고다.
                if r.status_code == 429 and rate_left > 0:
                    wait = _retry_after(r.headers) or 5.0
                    cap = retry_wait_cap(self.timeout)
                    if wait > cap:
                        # 🔴 20분을 자느니 다음 provider가 항상 빠르다
                        #   (실측 2026-08-27: Groq가 Retry-After 1182를 줬다).
                        logger.warning("[%s] 429 — %.0fs 대기 요구(상한 %.0fs) "
                                       "→ 기다리지 않고 폴백", self.name, wait, cap)
                        break
                    rate_left -= 1
                    logger.warning("[%s] 429 — %.0fs 후 재시도 (남은 %d회)",
                                   self.name, wait, rate_left)
                    await asyncio.sleep(wait)
                    continue
                break
        if r.status_code == 402 or (r.status_code != 429
                                    and "credit" in r.text.lower()):
            raise ApiQuotaError(self.name, r.text[:300])
        if r.status_code == 429:
            # 🔴 [실측 2026-09-04] 429 를 `ApiQuotaError` 로 던지면 **체인이
            #    거기서 멈춘다** — 크레딧 소진은 폴백 없이 즉시 중단이기 때문이다.
            #    Gemini 무료 티어의 429 본문은 "quota"·"billing"을 말하지만
            #    그것은 **분당·일일 한도**이지 잔액이 아니다. 시간이 지나면
            #    풀린다(실측: 같은 키가 몇 분 뒤 정상 응답).
            #    한도 초과는 **다음 provider 로 넘어갈 사유**이지 중단 사유가 아니다.
            #    CLAUDE.md 가 기록한 "429를 크레딧 소진으로 오분류" 사고의 재발이다.
            raise LLMError(f"{self.name} 레이트리밋 재시도 소진: {r.text[:250]}")
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


#: 🔴 `anthropic` 은 **여기 없다** (2026-09-06). 역할 체인으로는 Anthropic 에
#   갈 수 없다 — 유일한 경로는 2차 최종 판정(`judge_route.MATCHUP_ROLE`)이다.
#   `*_PROVIDER=anthropic` 을 넣으면 `build_provider` 가 LLMError 로 거절한다.
_KIND_TO_CLASS = {
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
        "gemini": getattr(s, "gemini_api_key", None),
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
                        "narrator": "report_model", "interpreter": "judge_model",
                        "intent": "intent_model"}

# provider별 기본 모델.
# ⚠️ **역할 폴백보다 우선한다.** 역할 폴백은 Claude 모델명(judge_model)을 주는데,
#    `INTERPRETER_PROVIDER=gemini`만 바꾸고 모델을 안 넣으면 **Gemini에 Claude
#    이름이 가서 404가 난다**(실측 2026-08-27: 'claude-opus-4-6'이 그대로 넘어갔다).
#    provider를 바꾸는 것만으로 동작해야 한다는 것이 이 계층의 존재 이유다.
_PROVIDER_DEFAULT_MODEL = {
    # ⚠️ 모델명을 **추측하지 마라.** `gemini-2.5-flash`는 신규 사용자에게
    #    제공되지 않는다(실측 2026-08-27: 404 "no longer available to new users").
    #    API가 직접 권한 모델을 쓴다. 바꾸기 전 `tools/check_llm.py`로 확인하라.
    "gemini": "gemini-3.6-flash",
    # ⚠️ 모델명을 추측하지 마라. `llama-3.3-70b-versatile`은 이 계정에
    #    존재하지 않았다(404, 실측 2026-08-27). `tools/check_llm.py`가 잡았다.
    "groq": "openai/gpt-oss-120b",
    "deepseek": "deepseek-chat",
    "ollama": "llama3.1",
    "xai": "grok-4.3-latest",
    "mock": "none",
}


def role_enabled(role: str, settings=None) -> bool:
    """그 역할이 켜져 있는가. `*_PROVIDER`가 비면 꺼진 것이다.

    ⚠️ 꺼진 역할을 mock으로 대체하지 않는다 — 목 판정이 실판정으로 오인되면
       "판정이 됐다"고 착각한 채 리포트가 나간다(실제로 겪은 유형의 사고다).
    """
    return bool((getattr(settings or get_settings(), f"{role}_provider", "") or "").strip())


def resolve_model(role: str, settings=None, kind: str = "") -> str:
    """역할의 모델명. 명시값 → provider 기본값 → 역할 폴백 순.

    ⚠️ provider 기본값이 역할 폴백보다 **먼저**다. 안 그러면 provider만 바꿨을 때
       다른 벤더의 모델명이 넘어간다.
    """
    s = settings or get_settings()
    explicit = (getattr(s, f"{role}_model", "") or "").strip()
    if explicit:
        return explicit
    if kind and kind in _PROVIDER_DEFAULT_MODEL:
        return _PROVIDER_DEFAULT_MODEL[kind]
    return getattr(s, _ROLE_MODEL_FALLBACK.get(role, ""), "") or ""


def provider_chain(role: str, settings=None) -> list[Provider]:
    """역할 → provider 폴백 체인. 첫 번째가 기본, 나머지는 폴백.

    설정 예: `JUDGE_A_PROVIDER=gemini` · `JUDGE_A_FALLBACK=groq`
    ⚠️ `anthropic` 은 이 체인에 없다 — 2차 최종 판정 전용이다.
    """
    if role not in ROLES:
        raise LLMError(f"알 수 없는 역할: {role!r} (가능: {', '.join(ROLES)})")
    s = settings or get_settings()
    kind = (getattr(s, f"{role}_provider", "") or "").strip()
    if not kind:
        raise LLMError(f"역할 {role}이(가) 비활성이다 — {role.upper()}_PROVIDER 미설정")
    # 🔴 **강제 목 모드는 이 계층에서도 지켜져야 한다.**
    #   `force_mock`은 config에서 anthropic·pplx·xai만 막고 있었고,
    #   gemini·groq를 추가할 때 여기에 게이트를 두지 않았다. 그 결과 테스트가
    #   실제로 Groq를 쳐서 429 재시도(20초×n)로 스위트가 멈춰 섰다
    #   (실측 2026-08-27). 절대 규칙 3은 provider를 늘릴 때마다 다시 지켜야 한다.
    if getattr(s, "force_mock", False):
        return [build_provider("mock", "none", s)]
    chain = [build_provider(kind, resolve_model(role, s, kind), s)]
    raw = getattr(s, f"{role}_fallback", "") or ""
    for spec in [x.strip() for x in raw.split(",") if x.strip()]:
        k, _, m = spec.partition(":")
        # 🔴 폴백 provider는 **자기 벤더의 기본 모델**을 쓴다.
        #   역할에 명시된 모델(`JUDGE_A_MODEL=claude-x`)은 **1순위 provider의 것**이다.
        #   그것을 폴백에 물려주면 벤더가 달라지는 순간 404가 나고, 그 404가
        #   "체인 전부 실패"로 보여 원인을 엉뚱한 데서 찾게 된다.
        chain.append(build_provider(
            k, m or _PROVIDER_DEFAULT_MODEL.get(k) or resolve_model(role, s, k), s))
    return chain


def thinking_budget(role: str, settings=None) -> int:
    """역할의 사고 예산. 없으면 0(끔).

    ⚠️ 2단 해석봇처럼 짧은 판정은 **꺼야 한다.** 사고가 출력 예산을 잠식해
       답이 아예 안 온다(실측 2026-08-27: 300 중 285를 사고가 소모).
    """
    return int(getattr(settings or get_settings(), f"{role}_thinking", 0) or 0)


async def complete(role: str, messages: list[dict], *, system: str = "",
                   schema: dict | None = None, max_tokens: int = 4096,
                   temperature: float = 0.0, thinking: int | None = None,
                   settings=None) -> LLMResult:
    """역할로 호출한다. 실패하면 폴백 체인을 따라가고 **누가 답했는지 기록한다.**

    ⚠️ 조용한 폴백 금지. 판정 품질이 provider마다 다를 수 있으므로
       "어느 모델이 이 판정을 했는가"가 리포트·DB까지 따라가야 한다.
    """
    chain = provider_chain(role, settings)
    budget = thinking_budget(role, settings) if thinking is None else thinking
    tried: list[str] = []
    last: Exception | None = None
    starved = False        # 예산 부족이 한 번이라도 있었나 — 알림 대상이다
    # [#73] 어느 provider가 언제 죽었는지 남긴다. 폴백 순서를 바꾸기 전에 볼 표다.
    redis = await _ledger_redis()
    s = settings or get_settings()
    from app.collectors.base import ApiQuotaError
    from app.engine.credit_guard import abort_if_credit_gone

    abort_if_credit_gone(role)
    for p in chain:
        if s.is_disabled(p.name):
            tried.append(f"{p.name}(disabled)")
            continue
        if (why := _is_exhausted(p.name)):
            tried.append(f"{p.name}(소진·생략)")
            last = last or LLMError(f"{p.name}: {why}")
            continue
        try:
            res = await p.complete(messages, system=system, schema=schema,
                                   max_tokens=max_tokens, temperature=temperature,
                                   thinking=budget)
            await _ledger.record_call(redis, p.name, role, True)
            # [운영 안정화 2] 성공하면 연속 실패를 끊는다 — 안 끊으면 경보가 남는다.
            await _wd_ok(redis)
            if tried:
                logger.warning("[llm:%s] 폴백 — %s 실패 후 %s 응답",
                               role, "→".join(tried), p.name)
                return LLMResult(res.text, res.data, res.provider, res.model,
                                 res.attempts, tuple(tried))
            return res
        except ApiQuotaError as exc:
            logger.error("[llm:%s] 크레딧 소진 — 체인 폴백 없이 즉시 중단: %s",
                         role, exc)
            tried.append(f"{p.name}(credit)")
            last = exc
            await _ledger.record_call(redis, p.name, role, False)
            await _ledger.record_outage(redis, p.name, role,
                                        _outage_kind(exc), str(exc))
            # 크레딧 소진은 체인 폴백 없이 즉시 중단이다 — 여기서 세지 않으면
            # 아래 전멸 카운터에 닿지 못해 워치독이 못 본다.
            await _wd_fail(redis, f"{role}: 크레딧 소진 {exc}")
            raise
        except LLMBudgetError as exc:
            # 🔴 **조용히 넘기지 않는다.** 빈 응답으로 넘어가면 목 출력과
            #    구분되지 않아 "판정 0건"의 원인을 영영 못 찾는다.
            logger.error("[llm:%s] 🔴 예산 부족 — %s", role, exc)
            starved = True
            tried.append(f"{p.name}(예산부족)")
            last = exc
            await _ledger.record_call(redis, p.name, role, False)
            await _ledger.record_outage(redis, p.name, role, "budget", str(exc))
        except Exception as exc:       # 다음 provider로 넘어간다
            logger.warning("[llm:%s] %s/%s 실패: %s", role, p.name, p.model, exc)
            tried.append(p.name)
            last = exc
            await _ledger.record_call(redis, p.name, role, False)
            await _ledger.record_outage(redis, p.name, role,
                                        _outage_kind(exc), str(exc))
            if _looks_daily(exc):
                _mark_exhausted(p.name, str(exc))
    if starved:
        await _notify_budget(role, budget, max_tokens, last)
    # [#73] 체인 전부 실패 = 전멸. 하루 누적을 세어 provider 추가 필요를 알린다.
    await _ledger.record_blackout(redis, role)
    # [운영 안정화 2] 연속 실패를 워치독에 남긴다 — 3회면 경보가 나간다.
    await _wd_fail(redis, f"{role}: 체인 전멸 ({'→'.join(tried)})")
    raise LLMError(f"역할 {role}: 체인 전부 실패 ({'→'.join(tried)})") from last


async def _wd_fail(redis, detail: str) -> None:
    """LLM 실패 1건을 워치독 카운터에 올린다. 실패해도 호출 흐름을 막지 않는다."""
    try:
        from app.watchdog import note_llm_failure

        n = await note_llm_failure(redis, detail)
        if n:
            logger.warning("[llm] 연속 실패 %d회 — %s", n, detail[:120])
    except Exception as exc:
        logger.debug("[llm] 워치독 기록 실패: %s", exc)


async def _wd_ok(redis) -> None:
    try:
        from app.watchdog import clear_llm_failures

        await clear_llm_failures(redis)
    except Exception as exc:
        logger.debug("[llm] 워치독 초기화 실패: %s", exc)


# [소진 차단] 오늘 쿼터가 끝난 provider는 **이 프로세스에서 다시 부르지 않는다.**
#   🔴 실사고 2026-08-27: Groq TPD가 소진된 뒤에도 호출마다 groq→gemini를 다시
#      두드렸고, gemini 429 재시도(20초×2)를 매번 물었다. 호출 하나당 40초 이상이
#      순수 대기였고 5경기 분석이 20분을 넘겼다.
#      "재시도"는 일시적 장애를 위한 것이지 **하루치가 끝난 키**를 위한 것이 아니다.
#   ⚠️ 프로세스 수명 동안만 기억한다. 키를 충전하고 재시작하면 다시 시도한다.
_EXHAUSTED: dict[str, str] = {}


def _mark_exhausted(name: str, why: str) -> None:
    if name not in _EXHAUSTED:
        logger.warning("[llm] %s 오늘 소진 — 이 프로세스에서는 건너뛴다 (%s)",
                       name, why[:80])
    _EXHAUSTED[name] = why


def _is_exhausted(name: str) -> str | None:
    return _EXHAUSTED.get(name)


def reset_exhausted() -> None:
    """테스트·재기동용."""
    _EXHAUSTED.clear()


# 하루치 소진을 뜻하는 문구 — 분당 제한(잠시 뒤 풀림)과 **구분해야 한다.**
#   분당 제한을 소진으로 오분류하면 멀쩡한 provider를 통째로 버린다.
#   ⚠️ **실제 응답 문구로 맞춘다.** "quota exceeded"로 적었더니 Gemini의
#      "You exceeded your current quota"가 안 걸렸다(어순이 다르다) — 추측한
#      문구는 안 맞는다. 새 provider를 붙이면 실제 429 본문을 보고 추가하라.
_DAILY_MARKERS = ("per day", "tpd", "daily", "quota exceeded",
                  "exceeded your current quota", "resource_exhausted",
                  "credit balance", "used all available credits",
                  "monthly spending limit")


def _looks_daily(exc: Exception) -> bool:
    txt = str(exc).lower()
    return any(m in txt for m in _DAILY_MARKERS)


def _outage_kind(exc: Exception) -> str:
    """예외 → 장애 종류. **429를 크레딧 소진으로 세지 않는다** — 이 프로젝트가
    Perplexity에서 이미 겪은 오분류다(잔액이 있는데 충전 알림을 보냈다)."""
    from app.collectors.base import ApiAuthError, ApiQuotaError, ApiRateLimitError

    if isinstance(exc, ApiRateLimitError):
        return "rate_limit"
    if isinstance(exc, ApiAuthError):
        return "auth"
    if isinstance(exc, ApiQuotaError):
        txt = str(exc).lower()
        return "rate_limit" if "레이트리밋" in str(exc) or "rate limit" in txt else "quota"
    return "other"


async def _ledger_redis():
    """기록용 redis. 없으면 None — 계측이 없다고 판정이 멈추면 안 된다.

    🔴 **강제 목 모드에서는 기록하지 않는다.** 테스트가 실 Redis에 써서 운영
       `/health`에 `fine`·`boom`·`starved` 같은 **테스트 더미 provider가 섞였다**
       (실측 2026-08-27). 계측이 오염되면 그 숫자를 근거로 한 판단이 전부 틀어진다
       — 테스트가 외부 API를 치는 것과 같은 종류의 누출이다.
    """
    if getattr(_S(), "force_mock", False):
        return None
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(_S().redis_url, decode_responses=True)
    except Exception:
        return None


async def _notify_budget(role: str, budget: int, max_tokens: int,
                         exc: Exception | None) -> None:
    """예산 부족을 운영 알림으로 올린다 — 설정으로만 고칠 수 있는 문제다."""
    try:
        from app.notify import send_telegram

        await send_telegram(
            f"🔴 LLM 예산 부족 — 역할 {role}\n"
            f"사고 예산 {budget} · 출력 {max_tokens}\n"
            f"{str(exc)[:300]}\n"
            f"→ {role.upper()}_THINKING 을 낮추거나 max_tokens를 올려라")
    except Exception as notify_exc:      # 알림 실패가 본체를 죽이지 않는다
        logger.warning("[llm] 예산 알림 실패: %s", notify_exc)
