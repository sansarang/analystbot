"""🔴🔴 **수집 단계까지만 돌린다** — 사용자 지시 2026-10-14.

> 지금 수정된 단계까지만 돌려라..llm 호출해서...전부다 돌리지 말어라..
> 라인업 확인후 **결장자·팀관련뉴스·감독이름·감독부임후 성적·팀내 불화** 가
> 전부 이 단계에서 나와야 한다. 이 내용들은 **fob과 서치**를 통하여 찾아야 한다.

```
PYTHONPATH=. uv run python tools/run_collect.py "Feyenoord Como"
```

🔴 **실제 단계를 import 해서 부른다**(규율 #12 프로브 금지) — 여기서 로직을
   다시 짜지 않는다. 확률·시뮬·카드는 **안 돌린다**(그것이 "전부"다).

돌리는 것:
```
s1_resolve → s2_facts(fotmob: XI·결장·감독) → s3_docs(딥서치)
→ s4_extract(추출) → s5_verify(검증) → absence 3+5 통합
→ s4b_gapsearch(LLM 이 **질의**를 쓴다) → 그 질의를 사슬에 던진다 → 2차 추출
```
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main(argv: list[str]) -> int:
    from app import rules  # noqa: F401  (설정을 먼저 읽힌다)
    from app.core import absence as _ab
    from app.core import deadline as _dl
    from app.core.stages import (s1_resolve, s2_facts, s3_docs, s4_extract,
                                 s4b_gapsearch, s5_verify)
    from app.core.pipeline import _question
    from app.core.state import RunState
    from app.db import get_pool
    from app import config as _cfg
    from app.net import Net
    import app.search as _search

    asked = argv[1] if len(argv) > 1 else "Feyenoord Como"
    st = RunState()
    st.deadline = _dl.Deadline(10.0)
    # 🔴 DB 풀은 봇이 쓰는 그것이다(`app/bot/main` 과 같은 길) — s1 이 슬레이트를
    #    읽고 적는다. ⚠️ `None` 을 주면 입구가 터진다(실측 2026-10-14).
    pool = await get_pool(_cfg.get_settings().database_url)
    net = Net(cache=True)
    # 🔴 사슬은 **운영이 쓰는 그 공장**으로 만든다(사본 금지)
    chain = _search.build_chain()
    q = _question(asked)
    print(f"# 수집 단계 점검 — {asked!r}\n", flush=True)

    # ── ① 경기
    from app.core.schema import Ambiguous
    ref = await s1_resolve.run(q, pool=pool, state=st, net=net,
                               pick_key=(argv[2] if len(argv) > 2 else ""))
    if isinstance(ref, Ambiguous):
        # 🔴 **고르지 않는다**(`Ambiguous` 머리말: 하나를 골라 주면 남의 경기를
        #    분석할 수 있다). 후보를 보이고 멈춘다 — 두 번째 인자로 열쇠를 준다.
        print(f"⚠️ **후보가 여럿이다** — {ref.why}")
        for i, one in enumerate(list(ref.candidates or []), 1):
            print(f"  {i}. {one}")
        for one in list(getattr(ref, "picks", None) or [])[:8]:
            print(f"     열쇠 `{one.get('key') if isinstance(one, dict) else one}`")
        return 3
    if ref is None:
        print("🔴 경기를 못 찾았다")
        for x in (st.notes() if hasattr(st, "notes") else [])[-6:]:
            print("  ·", str(x)[:150])
        return 2
    print(f"## ① 경기\n- {ref.home_name or ref.home} vs "
          f"{ref.away_name or ref.away} · {ref.competition} · "
          f"{ref.kickoff_utc}\n", flush=True)

    # ── ② fotmob 구조 사실 (XI · 결장 사다리 · 감독)
    facts = await s2_facts.run(ref, state=st, net=net)
    print("## ② fotmob — XI · 결장 · 감독", flush=True)
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        name = str(getattr(ref, f"{side}_name", "") or "") or key
        xi = dict(getattr(facts, "xi", None) or {}).get(key)
        co = dict(getattr(facts, "coach", None) or {}).get(key)
        ms = list(dict(getattr(facts, "missing", None) or {}).get(key) or [])
        print(f"- **{name}**")
        print(f"    XI — " + (
            f"{getattr(xi, 'formation', '') or '⬜ 포메이션 없음'} "
            f"[{getattr(xi, 'kind', '') or getattr(xi, 'state', '') or '?'}] · "
            f"{len(getattr(xi, 'players', None) or [])}명"
            if xi is not None else "⬜ **미확보**"))
        print(f"    감독 — " + (
            f"**{co.name}**"
            + (f" · 부임 {co.since}" if str(getattr(co, 'since', '') or '') else "")
            + (f" · 성적 {co.record}" if str(getattr(co, 'record', '') or '') else
               " · 성적 ⬜")
            + (f" · 원천 {co.source}" if str(getattr(co, 'source', '') or '') else "")
            if co is not None and str(getattr(co, "name", "") or "")
            else "⬜ **미확보**(경기 페이지 `isCoach` 비었다)"))
        print(f"    결장 — " + (
            " · ".join(f"{getattr(x, 'name', '?')}"
                       f"({getattr(x, 'reason', '') or '사유 미상'})"
                       for x in ms[:8]) if ms else "⬜ 0명"))
    rungs = list(getattr(facts, "absence_rungs", None) or [])
    print("    🪜 사다리 — " + " / ".join(
        f"{r.get('rung')} {r.get('got')}건" for r in rungs) + "\n", flush=True)

    # ── ③ 딥서치
    cache: dict = {}
    docs = await s3_docs.run(ref, facts, state=st, chain=chain, net=net,
                             cache=cache)
    print(f"## ③ 딥서치 — 문서 **{len(docs)}건**\n", flush=True)

    # ── ④⑤ 추출 · 검증
    cands = await s4_extract.run(ref, docs, state=st, chain=chain, net=net,
                                 cache=cache)
    docs = list(cache.values()) or docs
    variables = s5_verify.run(ref, facts, docs, cands, state=st, turnover={})
    print(f"## ④⑤ 추출·검증 — 후보 {len(cands)} → 변수 **{len(variables)}개**")
    for v in variables[:12]:
        print(f"- `{v.id}` [{v.type}] {str(v.claim or '')[:100]}"
              + (f" · 원천 {v.n_sources}곳" if getattr(v, "n_sources", 0) else ""))
    print(flush=True)

    # ── 3+5 통합 — 사다리 칸 4 를 기사로 다시 센다
    got_r, why_r = _ab.recount(rungs, variables,
                               keys=[str(ref.home), str(ref.away)])
    print(f"## 3+5 통합\n- {why_r}\n", flush=True)

    # ── ⑥ LLM 이 **질의를 쓴다**(못 찾은 칸만)
    n_conf = sum(1 for v in variables
                 if str(getattr(v, "type", "")) == "coach_conflict")
    # 🔴 이름으로 적는다(열쇠 `team:000455` 가 아니라)
    said_names = {str(ref.home): str(ref.home_name or ref.home),
                  str(ref.away): str(ref.away_name or ref.away)}
    want = s4b_gapsearch.need(facts, keys=[str(ref.home), str(ref.away)],
                              conflict_docs=n_conf, names=said_names)
    # 🔴🔴 **변수가 얇은 묶음**도 겨냥한다(지시 2026-10-14: *"llm이 검색할 대상은
    #    변수에 관련된 내용이다 … x search 가 약해서 하는거다"*)
    thin = s4b_gapsearch.thin_kinds(variables)
    print("## ⑥ LLM 표적 검색")
    print(f"- 못 찾은 칸 — {want or '없다'}")
    print(f"- 변수 0개인 묶음 — {list(thin) or '없다'}", flush=True)
    qs, why_q = s4b_gapsearch.ask(ref, facts, state=st, want=want, thin=thin,
                                  langs=["en", "it", "nl"])
    print(f"- {why_q}")
    for one in qs:
        print(f"    질의 `{one}`")
    # ── ⑦ 그 질의를 **우리 사슬**에 던진다
    hits = []
    for one in qs:
        try:
            got = await chain.query(one, lang="en")
        except Exception as exc:                            # noqa: BLE001
            print(f"    🔴 `{one}` 실패 — {exc!r}")
            continue
        print(f"    `{one}` → {len(got or [])}건")
        hits += list(got or [])
    print(f"- 표적 검색 결과 **{len(hits)}건**", flush=True)
    for h in hits[:10]:
        print(f"    · {str(getattr(h, 'title', '') or '')[:80]} — "
              f"{str(getattr(h, 'url', '') or '')[:70]}")
    mo, day = (0.0, 0.0)
    try:
        from app import solar
        mo, day = solar.spent()
    except Exception:                                       # noqa: BLE001
        pass
    print(f"\n## 비용\n- 월 ${mo:.4f} · 오늘(UTC) ${day:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
