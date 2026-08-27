"""LLM 연결·쿼터 **한 번에** 점검. 작업을 시작하기 전에 이것부터 돌린다.

추측하지 않고 실호출로 확인한다. 이 프로젝트에서 실제로 겪은 함정들:
  · 모델명 추측 → `gemini-2.5-flash`는 신규 사용자에게 제공되지 않는다(404)
  · provider만 바꾸면 다른 벤더 모델명이 간다(Claude 이름이 Gemini로 → 404)
  · 사고 토큰이 출력 예산을 잠식해 **200 OK인데 본문이 빈다**
  · 429가 소진인지 분당 제한인지 구분하지 않으면 엉뚱한 결론을 낸다

사용: PYTHONPATH=. uv run python tools/check_llm.py
"""

import asyncio
import json
import time

import httpx

from app.config import get_settings
from app.llm import provider as P

SMOKE_SCHEMA = {
    "type": "object",
    "properties": {"symbol": {"type": "string", "enum": ["▲", "▼", "="]},
                   "reason": {"type": "string"}},
    "required": ["symbol", "reason"],
}
SMOKE_FACT = "직전 경기 투수 9명 투입 · 구원 37타자 상대"
SMOKE_SYSTEM = ("야구 분석가다. 사실만 보고 ▲▼= 중 하나와 한 줄 사유를 낸다. "
                "사유에 사실의 숫자를 반드시 인용하라.")

# (표시명, config 키, provider 종류)
PROVIDERS = (
    ("Gemini", "gemini_api_key", "gemini"),
    ("Groq", "groq_api_key", "groq"),
    ("Anthropic", "anthropic_api_key", "anthropic"),
    ("DeepSeek", "deepseek_api_key", "deepseek"),
    ("xAI", "xai_api_key", "xai"),
    ("Ollama", None, "ollama"),          # 키 불필요 — 자체 호스팅
)


def mask(v: str | None) -> str:
    """⚠️ 키 값을 절대 그대로 찍지 않는다 — 로그·화면은 공유된다."""
    return f"길이{len(v)}·{v[:4]}…" if v else "없음"


async def list_models(kind: str, key: str, base: str | None) -> list[str]:
    """가능한 provider는 실제 모델 목록을 받아온다."""
    try:
        if kind == "gemini":
            b = base or P.GeminiProvider.DEFAULT_BASE
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{b}/models", params={"key": key})
            return [m["name"].removeprefix("models/")
                    for m in r.json().get("models") or []
                    if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        if kind in ("groq", "deepseek", "xai", "ollama"):
            b = base or P._DEFAULT_BASE.get(kind, "")
            h = {"Authorization": f"Bearer {key}"} if key else {}
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(f"{b.rstrip('/')}/models", headers=h)
            return [m.get("id", "") for m in (r.json().get("data") or [])]
    except Exception:
        return []
    return []


async def smoke(kind: str, model: str, s) -> tuple[str, str]:
    """단발 구조화 호출. 반환 (상태, 설명)."""
    try:
        prov = P.build_provider(kind, model, s)
    except P.LLMError as exc:
        return "🔴", str(exc)[:120]
    t0 = time.monotonic()
    try:
        res = await prov.complete(
            [{"role": "user", "content": json.dumps({"facts": [SMOKE_FACT]},
                                                    ensure_ascii=False)}],
            system=SMOKE_SYSTEM, schema=SMOKE_SCHEMA, max_tokens=600,
            thinking=0)
        ms = int((time.monotonic() - t0) * 1000)
        return "✅", f"{ms}ms · {(res.data or {}).get('symbol')} " \
                     f"{str((res.data or {}).get('reason'))[:60]}"
    except P.LLMBudgetError as exc:
        return "🟠", f"예산 부족 — {str(exc)[:110]}"
    except Exception as exc:
        msg = str(exc)
        if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
            # ⚠️ 소진과 분당 제한은 다르다 — 분당 제한이면 기다리면 풀린다.
            return "🟡", f"레이트리밋/쿼터 — {msg[:110]}"
        return "🔴", f"{type(exc).__name__}: {msg[:110]}"


async def main() -> None:
    s = get_settings()

    print("═══ 1. 키 보유 (값은 표시하지 않는다) ═══")
    for label, keyattr, kind in PROVIDERS:
        key = getattr(s, keyattr, None) if keyattr else None
        note = "키 불필요" if keyattr is None else mask(key)
        print(f"  {label:10} {note}")

    print("\n═══ 2. provider 연결·모델 ═══")
    for label, keyattr, kind in PROVIDERS:
        key = getattr(s, keyattr, None) if keyattr else None
        if keyattr and not key:
            print(f"  {label:10} 건너뜀 (키 없음)")
            continue
        base = getattr(s, f"{kind}_base_url", None)
        models = await list_models(kind, key or "", base)
        default = P._PROVIDER_DEFAULT_MODEL.get(kind, "?")
        ok = "✅" if (not models or default in models) else "⚠️"
        seen = f"{len(models)}개" if models else "목록 조회 불가"
        print(f"  {label:10} 모델 {seen} · 기본 {default} {ok}")
        if models and default not in models:
            print(f"             🔴 기본 모델이 목록에 없다 — 후보: {models[:4]}")

    print("\n═══ 3. 구조화 호출 스모크 ═══")
    for label, keyattr, kind in PROVIDERS:
        if keyattr and not getattr(s, keyattr, None):
            continue
        mark, detail = await smoke(kind, P._PROVIDER_DEFAULT_MODEL.get(kind, ""), s)
        print(f"  {label:10} {mark} {detail}")

    print("\n═══ 4. 역할별 체인 (실제 호출) ═══")
    for role in P.ROLES:
        if not P.role_enabled(role, s):
            print(f"  {role:12} 비활성")
            continue
        chain = " → ".join(f"{p.name}/{p.model}" for p in P.provider_chain(role, s))
        budget = P.thinking_budget(role, s)
        print(f"  {role:12} 사고{budget:>5} · {chain}")
        try:
            res = await P.complete(
                role, [{"role": "user", "content": json.dumps(
                    {"facts": [SMOKE_FACT]}, ensure_ascii=False)}],
                system=SMOKE_SYSTEM, schema=SMOKE_SCHEMA, max_tokens=600, settings=s)
            print(f"               ✅ **{res.label}** → {res.data}")
        except Exception as exc:
            print(f"               🔴 {type(exc).__name__}: {str(exc)[:140]}")


if __name__ == "__main__":
    asyncio.run(main())
