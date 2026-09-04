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


def available(provider: str) -> bool:
    import os

    ep = ENDPOINTS.get(provider)
    return bool(ep and (os.environ.get(ep[1]) or "").strip())


async def complete(provider: str, model: str, prompt: str, *,
                   max_tokens: int = 6000, timeout: float = 180.0) -> dict:
    """1회 호출. 반환 {text, ok, status, elapsed, retries, error, usage}.

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
    t0 = time.monotonic()
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(f"{base}/chat/completions", json=body,
                                 headers={"Authorization": f"Bearer {key}"})
        except Exception as exc:
            out["retries"] = attempt + 1
            out["error"] = f"{type(exc).__name__}: {exc}"
            if attempt == 2:
                break
            continue
        out["status"] = r.status_code
        if r.status_code == 429:
            # 🔴 우회하지 않는다. 한도는 한도다 — 오디션 점수에 반영한다.
            out["error"] = "429 rate limited"
            out["retries"] = attempt + 1
            if attempt == 2:
                break
            import asyncio

            await asyncio.sleep(8 * (attempt + 1))
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
