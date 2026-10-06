"""🔴🔴 **v6 파이프라인 실행기** — 지시서 2026-10-06 §8.

```
PYTHONPATH=. python tools/v6_run.py "기아 vs 삼성" --to s3 --record kbo_1
```

🔴 **옛 경로(`cmd_analyze`)를 안 부른다** — §9 는 4단계 전까지 옛 경로 수정을
   금지하고, v6 는 **옆에 짓는다**. 이 실행기가 새 경로의 입구다.
⚠️ `--to` 로 어디까지 돌릴지 정한다(2단계는 `s3` 까지다).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('쓰는 법: tools/v6_run.py "<팀> vs <상대>" [--to s1|s2|s3|card] [--record id]')
        return 2
    arg = argv[1]
    to = argv[argv.index("--to") + 1] if "--to" in argv else "card"
    from app import cassette
    for flag, mode in (("--record", cassette.RECORD), ("--replay", cassette.REPLAY)):
        if flag in argv:
            os.environ[cassette.MODE_ENV] = mode
            os.environ[cassette.RUN_ENV] = argv[argv.index(flag) + 1]
            print(f"[v6] 카세트 {mode} · 실행 id "
                  f"`{os.environ[cassette.RUN_ENV]}`", flush=True)
    if "--replay-fallthrough" in argv:
        os.environ[cassette.FALLTHROUGH_ENV] = "1"

    from app import net as _net_mod
    from app import search as _search
    from app.config import get_settings
    from app.core.schema import Ambiguous, Question
    from app.core.stages import (s1_resolve, s2_facts, s3_docs, s4_extract,
                                 s5_verify, s6_hypo, s7_judge)
    from app.core.state import RunState
    from app.db import get_pool
    from app.research import rerank

    team, opp = arg, ""
    low = arg.lower()
    for sep in (" vs ", " vs. ", " - ", " 대 "):
        if sep in low:
            i = low.index(sep)
            team, opp = arg[:i].strip(), arg[i + len(sep):].strip()
            break
    # 🔴 재정렬은 **전용 스레드가 소유한다** — 입구에서 올린다(§6 부품)
    print(f"[v6] 재정렬 예열 — {rerank.warm()}", flush=True)
    pool = await get_pool(get_settings().database_url)
    state = RunState()
    q = Question(raw=arg, team=team, opponent=opp,
                 asked_at=datetime.now(timezone.utc))

    net = _net_mod.Net()
    ref = await s1_resolve.run(q, pool=pool, state=state, net=net)
    if isinstance(ref, Ambiguous):
        print("🔴 s1 — 경기를 확정하지 못했다")
        print("  ", ref.why)
        for c in ref.candidates:
            print("   후보 ·", c)
        # 🔴 **밟은 단계를 찍는다**(#3) — 어디서 빗나갔나가 안 보이면 고칠 수 없다
        for n in state.notes:
            print("   밟음 ·", n[:150])
        return 1
    print(f"[s1] ✅ {ref.away_name} @ {ref.home_name} · {ref.competition_short}"
          f" · {ref.kickoff_utc:%Y-%m-%d %H:%M}Z · 열쇠 {ref.home}/{ref.away}"
          f" · 오픈월드 {ref.openworld}", flush=True)
    if to == "s1":
        return 0

    facts = await s2_facts.run(ref, state=state, net=net)
    print(f"[s2] 형식 {facts.match_format} · XI {len(facts.xi)}팀 · "
          f"순위 {len(facts.standings)}칸 · 폼 {len(facts.recent)}팀 · "
          f"출처 {len(facts.sources)}곳", flush=True)
    if to == "s2":
        return 0

    cache: dict = {}
    chain = _search.build_chain()
    docs = await s3_docs.run(ref, facts, state=state, chain=chain, net=net,
                             cache=cache)
    print(f"\n[s3] 문서 {len(docs)}건 · 장부 {state.book}")
    dated = sum(1 for d in docs if d.published_at is not None)
    print(f"     발행일 있는 것 {dated}/{len(docs)}"
          + (f" ({100 * dated // len(docs)}%)" if docs else ""))
    seen: dict[str, int] = {}
    for d in docs:
        seen[d.url] = seen.get(d.url, 0) + 1
    dup = {u: n for u, n in seen.items() if n > 1}
    print(f"     같은 URL 중복 {len(dup)}건" + (f" {list(dup)[:2]}" if dup else ""))
    for d in docs:
        print(f"  {d.id} [{d.subtask}] {d.tier:10} "
              f"{str(d.published_at)[:10] or '발행일 없음':10} "
              f"{d.date_source:9} {d.url[:70]}")
    _funnel(state)
    if to == "s3":
        return 0

    # ══════════════════════════════════════════════════════════════════
    # 🔴 s4~s7 · 카드 — **파이프라인 함수를 부른다**(프로브 금지 · CLAUDE.md #12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 여기서 단계를 다시 이으면 그것은 **프로브**다 — 실제 경로가 아니라
    #     이 파일의 순서를 검사하게 된다. 🔴 `pipeline.analyze` 가 입구다.
    from app.core import pipeline, render
    cands = await s4_extract.run(ref, docs, state=state, chain=chain, net=net,
                                 cache=cache)
    print(f"\n[s4] 후보 {len(cands)}개", flush=True)
    for c in cands:
        print(f"  [{c.subtask}] {c.type:18} {c.subject} ← {c.doc_id} "
              f"· {c.claim[:60]}")
    docs = list(cache.values()) or docs
    variables = s5_verify.run(ref, facts, docs, cands, state=state)
    print(f"\n[s5] 변수 {len(variables)}개 "
          f"(근거 가능 {sum(1 for v in variables if v.usable_as_basis)})")
    for v in variables:
        print(f"  {v.id} [{v.type:18}] {v.favors:10} {v.hardness:5} "
              f"{v.weight} · {v.claim[:60]}")
    hypo = s6_hypo.run(ref, facts, variables, state=state)
    print(f"\n[s6] 가설 {len(hypo.hypotheses)}팀 · 시나리오 "
          f"{len(hypo.scenarios)}개 · 반증 {len(hypo.redteam)}줄 · "
          f"버린 줄 {len(hypo.drops)}개")
    said = s7_judge.run(ref, facts, variables, hypo, state=state)
    print(f"[s7] 마켓 {len(said.evals)}줄 · 등급 낸 줄 "
          f"{sum(1 for e in said.evals if e.grade != '자료부족')}")
    card = pipeline.card_of(ref, facts, variables, hypo, said, state=state)
    _funnel(state)
    print("\n" + "=" * 70 + "\n[카드]\n" + "=" * 70)
    print(render.card_text(card))
    print("\n[밟은 자취]")
    for n in state.notes:
        print("  ·", n[:160])
    return 0


def _funnel(state: Any) -> None:
    """🔴 깔때기·버린 것·비용 — **안 잰 칸은 `null`** 로 보인다(#3)."""
    print(f"\n[깔때기] {json.dumps(state.counted(), ensure_ascii=False)}")
    by: dict[str, int] = {}
    for drop in state.drops:
        by[drop.reason.value] = by.get(drop.reason.value, 0) + 1
    print(f"[버린 것] {json.dumps(by, ensure_ascii=False)}")
    print(f"[비용] ${state.wallet.usd:.6f} · 호출 {state.wallet.calls}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(main(sys.argv)))
