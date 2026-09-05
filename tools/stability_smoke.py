"""[배포 게이트] 판정 안정성 스모크 — 같은 프롬프트 3회, 우세가 갈리면 막는다.

🔴 **실호출이다.** mock 으로는 "같은 재료가 같은 숫자를 내는가"를 잴 수 없다 —
   그것이 이 검사의 존재 이유다. 판정 캐시·원장·텔레그램에는 쓰지 않는다.

⚠️ **인프라 장애와 불안정을 구분한다.** 유효 응답이 2건 미만이면 SKIP 이다
   (exit 0). 503 이 배포를 막으면 이 게이트는 곧 꺼진다 — 꺼진 게이트는 없는
   게이트다. 막는 것은 **응답이 왔는데 우세가 갈린** 경우뿐이다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

REPS = 3


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=REPS)
    a = ap.parse_args()

    from tools.stability_audition import (
        _load_env, build_prompt, call_once, chain_candidates, read_verdict,
    )

    _load_env()
    from app.config import get_settings

    s = get_settings()
    budget = int(s.matchup_max_tokens)
    seed = int(s.llm_seed) or None
    cands = chain_candidates()
    if not cands:
        print("  ⏭  판정 사슬이 비었다 — SKIP")
        return 0
    provider, model = cands[0][0], cands[0][1]
    if provider == "anthropic":
        print(f"  ⏭  주전이 유료({model}) — 무료 스모크 SKIP")
        return 0

    prompt = build_prompt()
    print(f"  판정 안정성 스모크 — {provider}/{model} × {a.reps}회 "
          f"(seed={seed}, 동일 프롬프트 {len(prompt)}자)")
    sides, ps = [], []
    for i in range(a.reps):
        r = await call_once(provider, model, prompt, budget, seed)
        if not r.get("ok"):
            print(f"    {i+1}/{a.reps}  호출 실패 — {str(r.get('error'))[:60]}")
            continue
        p, side = read_verdict(r.get("text") or "")
        if p is None:
            print(f"    {i+1}/{a.reps}  파싱 실패")
            continue
        side = side or ("home" if p >= 0.5 else "away")
        ps.append(p)
        sides.append(side)
        print(f"    {i+1}/{a.reps}  p_home={p:.3f}  우세={side}")

    if len(sides) < 2:
        print(f"  ⏭  유효 응답 {len(sides)}건 — 안정성을 판단할 수 없다. SKIP "
              "(인프라 장애는 배포를 막지 않는다)")
        return 0
    spread = (max(ps) - min(ps)) * 100
    if len(set(sides)) > 1:
        print(f"  🔴 우세가 갈렸다: {sides} — 같은 재료가 다른 답을 냈다. 배포 중단")
        return 1
    print(f"  ✅ 우세 일치 ({sides[0]}) · 산포 {spread:.2f}%p")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
