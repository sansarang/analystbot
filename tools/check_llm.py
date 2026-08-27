"""LLM provider 연결 점검 — 키가 실제로 동작하는지, 어떤 모델이 있는지.

추측하지 않고 **실호출로 확인**한다. 모델명을 잘못 잡으면 404가 나고, 그 404가
폴백을 유발해 다른 모델이 조용히 판정하게 된다.

사용: PYTHONPATH=. uv run python tools/check_llm.py
"""

import asyncio
import json
import sys

import httpx

from app.config import get_settings

SCHEMA = {
    "type": "object",
    "properties": {"symbol": {"type": "string", "enum": ["▲", "▼", "="]},
                   "reason": {"type": "string"}},
    "required": ["symbol", "reason"],
}


async def gemini_models(key: str, base: str) -> list[str]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{base}/models", params={"key": key})
    if r.status_code >= 400:
        print(f"  🔴 모델 목록 실패 HTTP {r.status_code}: {r.text[:220]}")
        return []
    out = []
    for m in r.json().get("models") or []:
        if "generateContent" in (m.get("supportedGenerationMethods") or []):
            out.append(m["name"].removeprefix("models/"))
    return out


async def smoke(role: str) -> None:
    from app.llm import complete, provider_chain, role_enabled

    s = get_settings()
    if not role_enabled(role, s):
        print(f"  {role:12} 비활성")
        return
    chain = [(p.name, p.model) for p in provider_chain(role, s)]
    print(f"  {role:12} 체인 {chain}")
    try:
        res = await complete(
            role,
            [{"role": "user", "content": json.dumps(
                {"facts": ["직전 경기 투수 9명 투입 · 구원 37타자 상대"]},
                ensure_ascii=False)}],
            system="야구 분석가다. 사실만 보고 ▲▼= 중 하나와 한 줄 사유를 낸다. "
                   "사유에 사실의 숫자를 반드시 인용하라.",
            schema=SCHEMA, max_tokens=300, settings=s)
        print(f"     ✅ {res.label} → {res.data}")
    except Exception as exc:
        print(f"     🔴 {type(exc).__name__}: {str(exc)[:220]}")


async def main() -> None:
    s = get_settings()
    print("═══ 키 보유 현황 (값은 표시하지 않는다) ═══")
    for name, val in (("ANTHROPIC", s.anthropic_api_key), ("GEMINI", s.gemini_api_key),
                      ("GROQ", getattr(s, "groq_api_key", None)),
                      ("DEEPSEEK", getattr(s, "deepseek_api_key", None)),
                      ("XAI", s.xai_api_key)):
        mark = f"있음(길이 {len(val)}, 접두 {val[:4]}…)" if val else "없음"
        print(f"  {name:10} {mark}")

    if s.gemini_api_key:
        base = s.gemini_base_url or "https://generativelanguage.googleapis.com/v1beta"
        print(f"\n═══ Gemini 사용 가능 모델 ({base}) ═══")
        models = await gemini_models(s.gemini_api_key, base)
        if models:
            for m in models[:14]:
                print(f"  {m}")
            print(f"  … 총 {len(models)}개")
        else:
            print("  (조회 실패 — 키 형식·권한을 확인하라)")

    print("\n═══ 역할별 실호출 ═══")
    for role in ("interpreter", "narrator", "judge_a", "judge_b", "intent"):
        await smoke(role)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
