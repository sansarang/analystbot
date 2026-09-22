"""[감시 L2·L3] Gemini REST 클라이언트 — **감시 전용.**

🔴 **판정·딥서치 경로에 연결하지 않는다.** 이 클라이언트를 부르는 곳은
   `shadow_panel` 뿐이고, 그 결과는 기록 테이블에만 쌓인다.

⚠️ SDK(`google-genai`)를 넣지 않는다 — 의존성을 늘리지 않으려고 REST 직접 호출.
⚠️ 무료 티어는 분당 10요청이다. 호출 간 최소 간격을 **클라이언트에 내장**해
   호출부가 잊어도 지켜지게 한다. 429 는 30초 후 **1회만** 재시도한다.
⚠️ 키가 없으면 `is_available()=False` — L2·L3 전체가 휴면이고, 그 사실을
   기동 로그에 한 줄 남긴다(조용히 꺼지지 않는다).
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 60.0
RETRY_AFTER_429_SEC = 30.0

#: 마지막 호출 시각 (프로세스 내). 최소 간격을 여기서 지킨다.
_last_call: float = 0.0


def _settings():
    from app.config import get_settings

    return get_settings()


def is_available() -> bool:
    return bool((_settings().gemini_api_key or "").strip())


def model_name() -> str:
    return _settings().gemini_model


async def _throttle() -> None:
    """무료 티어 분당 10요청 — 간격을 강제한다."""
    import asyncio

    global _last_call
    gap = float(_settings().gemini_min_interval_sec)
    wait = gap - (time.monotonic() - _last_call)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call = time.monotonic()


async def generate(prompt: str, *, max_tokens: int = 2048) -> str | None:
    """텍스트 1회 생성. 실패하면 None — 예외를 밖으로 던지지 않는다.

    🔴 [LLM0 2026-09-22 사용자 지시] 스위치가 꺼져 있으면 **부르지 않는다.**
       원본은 `api_guard.llm_enabled` 하나다(사본 금지).
    """
    from app.api_guard import llm_enabled

    if not llm_enabled():
        return None
    import asyncio

    import httpx

    if not is_available():
        return None
    s = _settings()
    url = f"{BASE}/{s.gemini_model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0,
                                 "maxOutputTokens": int(max_tokens)}}
    for attempt in (1, 2):
        await _throttle()
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post(url, json=body,
                                 headers={"x-goog-api-key": s.gemini_api_key})
                if r.status_code == 429 and attempt == 1:
                    logger.warning("[gemini] 429 — %.0f초 후 1회 재시도",
                                   RETRY_AFTER_429_SEC)
                    await asyncio.sleep(RETRY_AFTER_429_SEC)
                    continue
                r.raise_for_status()
                data = r.json()
            parts = (((data.get("candidates") or [{}])[0].get("content") or {})
                     .get("parts") or [])
            return "".join(p.get("text", "") for p in parts) or None
        except Exception as exc:
            logger.warning("[gemini] 호출 실패 (%d/2): %s", attempt, exc)
            if attempt == 2:
                return None
    return None


def parse_json_lenient(text: str | None):
    """JSON 계약 위반을 **파싱만** 관대하게 다룬다.

    🔴 어댑터로 **내용을 고치지 않는다.** 코드펜스 제거·앞뒤 잡음 제거까지다.
       모델이 다른 말을 했으면 그건 그 건을 skip 할 사유이지, 우리가
       원하는 모양으로 주물러 넣을 일이 아니다.
    """
    import json
    import re

    if not text:
        return None
    s = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(),
               flags=re.MULTILINE).strip()
    for lo, hi in (("[", "]"), ("{", "}")):
        i, j = s.find(lo), s.rfind(hi)
        if i >= 0 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except ValueError:
                continue
    return None
