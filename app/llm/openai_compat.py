"""[오디션] OpenAI 호환 엔드포인트 어댑터 — **하나로 여럿을 쓴다.**

base_url·키만 다르고 요청 형식은 같다. provider 마다 클라이언트를 새로
만들면 그만큼 고칠 곳이 늘어난다 — 어댑터는 하나다.

⚠️ 이 모듈은 **오디션용**이다. 판정 경로에 배선하는 것은 오디션 결과를
   보고 승인받은 뒤 별도 사이클이다(표본 재시작 규칙 포함).
⚠️ 재시도·타임아웃은 config 가 원본이고, 429 는 그대로
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
    # 🔴 [2026-09-07 사용자 지시] **Anthropic 소진 시 최종 판정 대체.**
    #    실측(현행 프롬프트 17,741자, 다저스전): grok-4.3-latest 가 전개·
    #    홈/원정 경로·분기점·예상점수를 모두 냈고 10초·출력 735토큰으로
    #    후보 중 가장 경제적이었다. 검색 모델이 아니라 판정 규칙(배당·사전
    #    지식 금지)을 우회할 위험도 없다(퍼플렉시티는 그 위험이 있다).
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    # 🔴 [P0 안정성 2026-09-05] Gemini 를 **사슬에 넣는다.** 종전에는 별도
    #    클라이언트(`app/llm/gemini.py`)만 있어 판정 사슬에서 쓸 수 없었다.
    #    Google 이 OpenAI 호환 엔드포인트를 제공하므로 구조를 그대로 쓴다.
    #    승격 근거(실측 2026-09-05, 동일 프롬프트 10회):
    #      nemotron  산포 10.00%p · 우세 뒤집힘 4회  ❌
    #      gpt-oss   산포 12.00%p · 뒤집힘 3회       ❌
    #      gemini    산포  2.00%p · 뒤집힘 0회       ✅  ← 유일한 실질 합격
    #    ⚠️ `app/llm/gemini.py` 는 지우지 않았다 — 감시 L2·L3 가 쓴다.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai",
               "GEMINI_API_KEY"),
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
    # ⚠️ 무료 티어는 429 가 잦다(오디션에서 10회 중 2회 503/429). 유료 전환
    #    후에도 간격은 남긴다 — 없애는 것은 실측을 보고 결정한다.
    "gemini": 2.0,
}

#: `seed` 를 받지 않는 provider. **실호출로 확인한 것만 넣는다.**
#   실측 2026-09-05 (OpenAI 호환 엔드포인트):
#     nvidia·groq·openrouter  seed 200 수용
#     gemini                  400 `Unknown name "seed"` — 나머지 필드는 전부 수용
#   ⚠️ seed 를 못 싣는다고 판정 자격을 잃지 않는다. 결정성의 실체는 오디션
#      산포이지 파라미터 수용 여부가 아니다 — Gemini 는 seed 없이도 산포
#      2.00%p·뒤집힘 0 으로 사슬에서 유일하게 합격했다.
_NO_SEED = {"gemini"}

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


#: 사고를 줄이는 값의 **강등 순서.** 제공자가 거부하면 다음으로 내려간다.
#  🔴 추측으로 만든 목록이 아니다 — 400 응답이 직접 알려준 값들이다:
#     "`reasoning_effort` must be one of `low`, `medium`, or `high`" (groq gpt-oss)
_REASONING_OFF = ("none", "low")


def _next_reasoning(cur: str | None) -> str | None:
    """현재 값 다음 단계. 끝이면 None (= 필드를 뺀다)."""
    try:
        i = _REASONING_OFF.index(cur or "")
    except ValueError:
        return None
    return _REASONING_OFF[i + 1] if i + 1 < len(_REASONING_OFF) else None


async def complete(provider: str, model: str, prompt: str, *,
                   max_tokens: int = 6000, timeout: float = 180.0,
                   reasoning: bool = True, seed: int | None = None) -> dict:
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
    # [P0 안정성 2026-09-05] 같은 재료는 같은 숫자를 내야 한다.
    #   ⚠️ `temperature=0` 만으로는 결정적이지 않다 — 대형 MoE 서빙은 배치
    #      구성에 따라 부동소수 누산 순서가 달라진다. `seed` 는 그 위에 얹는
    #      **최선 노력** 장치이고, 실제 효과는 오디션 실측으로 판단한다
    #      (수용 여부: nvidia·groq·openrouter 전부 200, 2026-09-05 실측).
    if seed is not None and provider not in _NO_SEED:
        body["seed"] = int(seed)
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
        body["reasoning_effort"] = _REASONING_OFF[0]
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
        if r.status_code in (429, 401):
            # 🔴 [CHN-1 2026-09-15 사용자 지시] **기다리지 않는다 — 즉시 다음
            #    제공자로 간다.** 종전 규칙("우회하지 않는다. 기다린다")의 전제는
            #    쓸 만한 제공자가 하나뿐이라는 것이었다. 이제 둘이다.
            #    실측 2026-09-15: 이 자리에서 **453초**를 기다렸고(4회 × 상한 60초 +
            #    간격), 그동안 슬레이트 전체가 멈췄다. groq 무료 티어는
            #    `x-ratelimit-limit-tokens = 8000`(분당)이라 판정 1콜에 바로 걸린다.
            #    401 도 같이 즉시 나간다 — 키가 틀린 것은 기다려도 안 풀린다
            #    (openrouter `User not found` 로 사슬이 통째로 늦어졌다).
            #    ⚠️ **분류는 바꾸지 않는다**(아래 종전 주석 그대로). 보이게만 한다.
            #    ⚠️ 라운드로빈 본 구현 전까지의 임시 규칙이다 — `remaining` 추적은
            #       아직 없다.
            #    `Retry-After` 가 있으면 그것을 따르고, 없으면 그 provider 의
            #    최소 간격만큼 쉰다.
            # 🔴 [LLM-1 2026-09-08] **본문을 버리지 않는다.** 종전에는 이 줄이
            #    `"429 rate limited"` 로 덮어써서 응답이 무슨 말을 했든 사라졌다.
            #    바로 아래 5xx 분기는 `r.text[:160]` 을 보존하는데 429 만 버렸다.
            #    실사고 2026-09-08: 운영 gemini 가 이렇게 답하고 있었다 —
            #      429 RESOURCE_EXHAUSTED "Your prepayment credits are depleted.
            #                              Please go to AI Studio ... billing."
            #    로그에는 "rate limited" 만 남아 사람이 "기다리면 풀린다"로 읽었고,
            #    잔액이 0인 채로 **11경기 판정이 0건**으로 슬레이트가 지나갔다.
            #    ⚠️ **분류는 바꾸지 않는다.** 429 를 credit 으로 승격시키면 반대
            #       사고가 난다 — 2026-09-05, 툴 결함으로 세 역할이 gemini 로 몰려
            #       난 429 가 credit 으로 오분류돼 체인이 통째로 멈췄다
            #       (W-LLM-FAIL 24회, `provider.py` 주석). 어댑터는 분류하지
            #       않는다. 재시도·대기·차단기 전부 그대로다. **보이게만 한다.**
            detail = (r.text or "").strip().replace("\n", " ")[:160]
            kind = "429 rate limited" if r.status_code == 429 else "401 unauthorized"
            out["error"] = f"{kind} — {detail}" if detail else kind
            out["retries"] = attempt + 1
            logger.warning("[net] %s %d — 즉시 다음 제공자로 (대기 0초) · 본문: %s",
                           provider, r.status_code, detail or "(없음)")
            break
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
        if r.status_code == 400 and "reasoning_effort" in (r.text or ""):
            # 🔴 [실측 2026-09-04] 값이 제공자·모델마다 다르다. 추측하지 않고
            #    **응답이 말해주는 대로** 한 단계씩 내려간다.
            #      groq `qwen/qwen3.8-27b`   → "none" 수용
            #      groq `openai/gpt-oss-120b` → 400
            #        "`reasoning_effort` must be one of `low`, `medium`, or `high`"
            #    마지막에는 필드를 아예 뺀다 — 사고가 켜지지만 **호출은 된다.**
            #    한 모델이 이 필드를 모른다고 그 후보를 통째로 버리면,
            #    사슬을 여럿 둔 의미가 없어진다.
            cur = body.get("reasoning_effort")
            nxt = _next_reasoning(cur)
            if nxt is not None:
                logger.warning("[net] %s reasoning_effort=%r 거부 — %r 로 재시도",
                               provider, cur, nxt)
                body["reasoning_effort"] = nxt
            else:
                logger.warning("[net] %s reasoning_effort 미지원 — 필드를 빼고 재시도",
                               provider)
                body.pop("reasoning_effort", None)
            out["retries"] = attempt + 1
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
