"""[오디션] OpenAI 호환 엔드포인트 어댑터 — **하나로 여럿을 쓴다.**

base_url·키만 다르고 요청 형식은 같다. provider 마다 클라이언트를 새로
만들면 그만큼 고칠 곳이 늘어난다 — 어댑터는 하나다.

⚠️ 이 모듈은 **오디션용**이다. 판정 경로에 배선하는 것은 오디션 결과를
   보고 승인받은 뒤 별도 사이클이다(표본 재시작 규칙 포함).
⚠️ `polite_client` 와 같은 정신: 재시도·타임아웃은 config, 429 는 그대로
   돌려주고 우회하지 않는다.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

#: provider → (base_url, 키 env 이름). **여기가 원본이다** — 호출부에 URL 을
#  다시 적지 않는다.
ENDPOINTS: dict[str, tuple[str, str]] = {
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

#: 🔴 [2026-09-04 실측] provider 별 **최소 호출 간격(초).**
#   프리페치 첫 실전에서 폼 10팀을 연속으로 때렸다가 이렇게 무너졌다:
#     nvidia  3건 성공(18.7~55.2초) → 4번째 `503 Service temporarily overloaded`
#     mistral 폴백 → `429 rate limited`  (RPM 2 한도)
#   둘 다 **영구 실패가 아니다** — 간격을 두면 통과한다. 간격 없이 때린 것이
#   문제였고, Mistral RPM 2 는 가입 조사 때 내가 직접 적어놓고도 무시했다.
#   ⚠️ [재실측 14:30] Mistral 은 31초 간격을 두고 4회 재시도해도 **계속 429** 였다
#      (95초 낭비 후 실패). 무료 티어가 사실상 막혀 있다 — **폴백에서 뺐다.**
#      대신 Groq(0.4s)·OpenRouter(3.3s) 가 즉시 응답했다.
MIN_INTERVAL_SEC: dict[str, float] = {
    "mistral": 31.0,      # RPM 2 → 30초 + 여유 (현재 폴백 미사용)
    "nvidia": 2.0,        # RPM ~40 → 1.5초면 되지만 503 여유를 둔다
    "groq": 2.0,
    "openrouter": 2.0,
}

#: provider 별 마지막 호출 시각(프로세스 내).
_last_call: dict[str, float] = {}


async def _throttle(provider: str) -> None:
    """그 provider 의 최소 간격을 지킨다. **호출부가 잊어도 지켜진다.**"""
    import asyncio

    gap = MIN_INTERVAL_SEC.get(provider, 1.0)
    last = _last_call.get(provider)
    if last is not None:
        wait = gap - (time.monotonic() - last)
        if wait > 0:
            logger.info("[net] %s 최소 간격 %.1fs 대기", provider, wait)
            await asyncio.sleep(wait)
    _last_call[provider] = time.monotonic()


def available(provider: str) -> bool:
    import os

    ep = ENDPOINTS.get(provider)
    return bool(ep and (os.environ.get(ep[1]) or "").strip())


async def complete(provider: str, model: str, prompt: str, *,
                   max_tokens: int = 6000, timeout: float = 180.0,
                   reasoning: bool = True) -> dict:
    """1회 호출. 반환 {text, ok, status, elapsed, retries, error, usage}.

    `reasoning=False` 면 추론을 끈다 — 짧은 구조화 출력(폼 평가서)에서
    사고가 출력 예산을 잠식하는 것을 막는다. 판정(matchup)은 켠 채로 둔다.

    ⚠️ **예외를 던지지 않는다.** 오디션은 실패도 데이터다 — 어느 후보가
       몇 번 실패했는지가 채점 항목(⑤)이다.
    """
    import os

    import httpx

    out = {"text": "", "ok": False, "status": None, "elapsed": 0.0,
           "retries": 0, "error": None, "usage": None}
    ep = ENDPOINTS.get(provider)
    if not ep:
        out["error"] = f"unknown provider {provider}"
        return out
    base, env = ep
    key = (os.environ.get(env) or "").strip()
    if not key:
        out["error"] = f"{env} 없음"
        return out
    body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "user", "content": prompt}]}
    if not reasoning:
        # 🔴 [실측 2026-09-04] 추론 토큰이 `max_tokens` 를 통째로 먹었다.
        #    Nemotron 3 Ultra 는 `reasoning_content` 를 따로 주기도 하고
        #    `content` 안에 그대로 쏟기도 한다(비결정적). 후자일 때 1500토큰
        #    예산이 사고로 소진돼 JSON 이 아예 안 나왔다.
        #      · 프리페치 15:13 Samsung Lions 1회차 resp 599자 = 잘린 JSON
        #      · 2회차 resp 3881자 = 영어 사고문 ("The user wants me to analyze…")
        #    같은 사고가 2026-08-27 에 이미 있었다(2단 해석봇, 300 중 285를 사고가
        #    소모). 그때 결론이 "짧은 판정은 사고를 끈다" 였다.
        #    ⚠️ 세 제공자 모두 이 필드를 받는 것을 실호출로 확인했다
        #       (nvidia reasoning 222자→0자 · groq 200 · openrouter 200).
        body["reasoning_effort"] = "none"
    t0 = time.monotonic()
    for attempt in range(4):
        await _throttle(provider)
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(f"{base}/chat/completions", json=body,
                                 headers={"Authorization": f"Bearer {key}"})
        except Exception as exc:
            out["retries"] = attempt + 1
            out["error"] = f"{type(exc).__name__}: {exc}"
            if attempt == 3:
                break
            import asyncio

            await asyncio.sleep(3.0 * (attempt + 1))
            continue
        out["status"] = r.status_code
        if r.status_code == 429:
            # 🔴 우회하지 않는다. **기다린다** — 한도는 한도이고, 기다리면 풀린다.
            #    `Retry-After` 가 있으면 그것을 따르고, 없으면 그 provider 의
            #    최소 간격만큼 쉰다.
            out["error"] = "429 rate limited"
            out["retries"] = attempt + 1
            if attempt == 3:
                break
            import asyncio

            ra = r.headers.get("Retry-After")
            try:
                wait = float(ra) if ra else MIN_INTERVAL_SEC.get(provider, 30.0)
            except (TypeError, ValueError):
                wait = MIN_INTERVAL_SEC.get(provider, 30.0)
            logger.warning("[net] %s 429 — %.0f초 후 재시도 (%d/4)",
                           provider, wait, attempt + 1)
            await asyncio.sleep(min(wait, 60.0))
            continue
        if r.status_code >= 500:
            # 🔴 [실측] `503 Service temporarily overloaded` 가 무료 인프라의
            #    주 실패 형태다. 오디션 6건 중 1건, 프리페치 연속 호출에선
            #    4번째부터 났다. **잠깐 밀린 것이지 거절이 아니다** — 쉬고 다시.
            out["error"] = f"{r.status_code} {r.text[:160]}"
            out["retries"] = attempt + 1
            if attempt == 3:
                break
            import asyncio

            wait = 4.0 * (2 ** attempt)
            logger.warning("[net] %s %d — %.0f초 후 재시도 (%d/4)",
                           provider, r.status_code, wait, attempt + 1)
            await asyncio.sleep(wait)
            continue
        if r.status_code != 200:
            out["error"] = f"{r.status_code} {r.text[:200]}"
            break
        try:
            d = r.json()
            ch = (d.get("choices") or [{}])[0]
            out["text"] = ((ch.get("message") or {}).get("content") or "")
            out["usage"] = d.get("usage")
            out["ok"] = bool(out["text"].strip())
            if not out["ok"]:
                out["error"] = "빈 응답"
        except Exception as exc:
            out["error"] = f"파싱 실패: {exc}"
        break
    out["elapsed"] = round(time.monotonic() - t0, 1)
    return out
