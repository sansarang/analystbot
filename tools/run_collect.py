"""🔴🔴 **⑯ 단계까지 돌린다** — 사용자 지시 2026-10-15.

> **16단계가 마지막이다** · 각 단계별 배선 완벽하게 하고 테스트 ·
> llm **solar** 가 종합 평을 낸다 · deepseek… **확률 먼저** ·
> 변수가 이래케 저렇게 되서 이렇게 나온다 · **코드 만으로** ·
> solar **지어냈는지 안지어냈는지 결론내다** · **17단계 이후는 없어도 된다**

⚠️ 종전 머리말(아래)은 **수집까지**였다 — 이제 ⑯(확률·시뮬·종합 평)까지 간다.

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
    from app.core import turnover as _turn
    from app.core.stages import (s1_resolve, s2_facts, s2d_strategy, s3_docs,
                                 s4_extract, s4b_gapsearch, s5_verify)
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
    # 🔴🔴 **재정렬기를 예열한다** — `app/bot/main.py:165` 가 운영에서 부르는 그것.
    #    ⚠️ 실사고 2026-10-14: 러너가 이걸 빠뜨려 `rerank_unavailable` 이 났고,
    #       후보 95개의 **순서가 뒤죽박죽**인 채 열기 상한 3개가 아무 문서나
    #       집었다 → 표적 문서 **0건**. 🔴 검문이 좁은 게 아니라 **고르지
    #       못한 것**이었다(사유 집계로 확인: STALE 48 · IDENTITY 31).
    from app.core import rank as _rank
    print(f"- 재정렬 예열 — {_rank.warm()}", flush=True)
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

    # ── ②-b 선수단 교체 — 🔴 s3 **앞**이다(파이프라인 순서 그대로 · 지시
    #    2026-10-10 ③). 재료는 `facts` 뿐이다(새 통신 0건).
    turn = {side: _turn.read(ref, facts, side=side) for side in ("home", "away")}
    print("## ②-b 선수단 교체")
    for side, one in turn.items():
        print(f"- {side} — " + ("🔴 **켜졌다** · " if one.get("on") else "")
              + str(one.get("why") or "")[:160])
    print(flush=True)

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

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **포메이션·전략 판정**(지시 2026-10-14: *"지금 단계에 포메이션 전략이
    #    끝나있어야 한다"*)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 `s2d_strategy.run` 은 **확률을 안 받는다**(`ref · facts · turnover`
    #     뿐) — 그래서 이 단계에서 끝낼 수 있다.
    #  ⚠️ 전술 **예측**(`s9_say`)은 다르다: `saybundle` 이 `our_prob`·`matchup`·
    #     `shape` 를 읽으므로 확률·상성 뒤에 선다.
    plan = s2d_strategy.run(ref, facts, state=st, news=variables, turnover=turn)
    print("## ⑤-b 포메이션·전략 판정")
    print(f"- 판정 `{getattr(plan, 'audit', '') or '?'}`"
          + (f" · 양상 **{plan.shape}**" if str(getattr(plan, "shape", "") or "")
             else " · 양상 ⬜"))
    for one in list(getattr(plan, "lines", None) or []):
        side = str(getattr(one, "side", "") or "")
        name = str(getattr(ref, f"{side}_name", "") or "") or side
        print(f"- **{name}** — `{getattr(one, 'strategy', '') or '?'}`"
              f" · 근거 {list(getattr(one, 'fact_refs', None) or [])}")
        print(f"    {str(getattr(one, 'why', '') or '')[:230]}")
    box = dict(getattr(plan, "facts", None) or {})
    print(f"- §2-1 사실 **{len(box)}개**")
    for fid, txt in list(box.items())[:16]:
        print(f"    `{fid}` {str(txt)[:110]}")
    for bad in list(getattr(plan, "violations", None) or [])[:4]:
        print(f"- 🔴 {bad}")
    print(flush=True)

    # ── 3+5 통합 — 사다리 칸 4 를 기사로 다시 센다
    got_r, why_r = _ab.recount(rungs, variables,
                               keys=[str(ref.home), str(ref.away)])
    print(f"## 3+5 통합\n- {why_r}\n", flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑤-c 리그·컵 정보 분석**(지시 2026-10-14) — fotmob 표를 LLM 이 읽는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > fotmob에 받아서 llm이 그컵이나 리그정보 **분석만** 해서 변수에 넣는다
    #
    #  🔴 표적 검색(⑥)보다 **먼저**다 — 순위·승점·라운드는 fotmob 이 주므로
    #     웹에서 긷지 않는다(그 길은 오류만 많았다 · 실측 2026-10-14).
    from app.core.stages import s4c_leagueread as _lr
    said_lr, why_lr = _lr.ask(ref, facts, state=st)
    print("## ⑤-c 리그·컵 분석")
    print(f"- {why_lr}")
    var_lr = _lr.variable(ref, said_lr)
    for v in var_lr:
        print(f"- 변수 `{v.id}` [{v.type}] {str(v.claim or '')[:150]}")
    if not var_lr:
        print("- ⬜ **변수 없다** — 판단이 `모르겠다` 거나 표를 못 받았다")
    print(flush=True)

    # ── ⑥ LLM 이 **질의를 쓴다**(못 찾은 칸만)
    n_conf = sum(1 for v in variables
                 if str(getattr(v, "type", "")) == "coach_conflict")
    # 🔴 이름으로 적는다(열쇠 `team:000455` 가 아니라)
    said_names = {str(ref.home): str(ref.home_name or ref.home),
                  str(ref.away): str(ref.away_name or ref.away)}
    # 🔴🔴 **쪽을 넘긴다**(지시 2026-10-14) — 이동·일정·거리는 원정팀만,
    #    홈 최근 5경기는 홈팀만 묻는다.
    said_sides = {str(ref.home): "home", str(ref.away): "away"}
    want = s4b_gapsearch.need(facts, keys=[str(ref.home), str(ref.away)],
                              conflict_docs=n_conf, names=said_names,
                              sides=said_sides)
    # 🔴🔴 **변수가 얇은 묶음**도 겨냥한다(지시 2026-10-14: *"llm이 검색할 대상은
    #    변수에 관련된 내용이다 … x search 가 약해서 하는거다"*)
    thin = s4b_gapsearch.thin_kinds(variables)
    print("## ⑥ LLM 표적 검색")
    print(f"- 못 찾은 칸 — {want or '없다'}")
    print(f"- 변수 0개인 묶음 — {list(thin) or '없다'}", flush=True)
    qs, why_q = s4b_gapsearch.ask(ref, facts, state=st, want=want, thin=thin)
    print(f"- {why_q}")
    for one in qs:
        print(f"    질의 `{one}`")
    # ── ⑦ 그 질의를 **우리 사슬**에 던진다
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑦ 표적 질의 → 문서 → 추출 → 변수**(사용자 지시 2026-10-14)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 경기 정보를 **llm 서치**하고 llm 결과를 **변수에 넣어야 한다**
    #
    #  🔴 `s3_docs.gap_docs` 가 `run` 과 **같은 둘**(`_candidates`·`_fetch`)을
    #     부른다 — 도메인 등급·신원·날짜·본문 받기가 1차와 같은 길이다.
    #  🔴🔴 **그 질의의 언어를 먼저 쓴다**(실측 2026-10-14: 이탈리아어 질의 둘이
    #     `nl` 로 던져졌다). ⚠️ 글자로는 nl·it 를 못 가린다(둘 다 ASCII) →
    #     **팀 이름**으로 가린다: 그 질의가 어느 팀을 담았나.
    said_langs = s4b_gapsearch.langs_of()
    print(f"- 언어 순서 — {said_langs}")
    pairs: list = []
    for one in qs:
        lg = said_langs[0]
        if len(said_langs) > 1 and str(ref.away_name or "") in one:
            lg = said_langs[1]
        pairs.append((one, lg))
        print(f"    `{one}` → 언어 `{lg}`")
    # 🔴 하위 묶음 — 어느 유형으로 추출할지가 여기 들어 있다(그 유형이 변수 type)
    #  🔴🔴 **쪽별로 쪼갠다** — 운영 하위가 `A-home`·`A-away` 로 갈리는 그 모양이다.
    #     ⚠️ 예산은 하위마다 `search_cap=3` 이다(설정) — 질의 6개를 한 하위에
    #        넣으면 **3개만 던져진다**(실측 2026-10-14). 쪽으로 쪼개면 각 3개다.
    #  🔴 질의를 **그 팀 것으로** 가른다 — 팀 이름이 든 쪽에 붙인다.
    from app.research.subtasks import Subtask, _budget
    KINDS = ("absence", "returning", "team_stats", "stakes", "fatigue",
             "travel_schedule", "coach_intent", "coach_conflict",
             "lineup_rotation", "coach_change")
    RERANK = ("standings points round fixtures travel tactics formation "
              "manager record unrest")
    got_docs: list = []
    for side in ("home", "away"):
        nm = str(getattr(ref, f"{side}_name", "") or "")
        mine = [x for x in pairs if nm and nm.split()[0] in x[0]]
        if not mine:
            print(f"- {side} — ⬜ 그 팀을 담은 질의가 없다")
            continue
        sub = Subtask(
            # 🔴🔴 **이름은 `F-home`·`F-away` 다** — `schema.SubtaskId` 가
            #    열거로 잠겨 있다(*"여기 없으면 터진다 — 그 쪽이 맞다"*).
            #    ⚠️ 실측 2026-10-14: `GAP-away` 로 넣었더니 `Doc` 이 거부했다.
            #    🔴 열거를 늘리지 않는다 — 하위 **F**(새 사실 72시간)가 이 일에
            #       맞는 묶음이고, 표적 검색도 "오늘 사실"을 긷는다.
            name=f"F-{side}", group="F", label="표적(LLM 서치)",
            kinds=KINDS, side=side, team=nm,
            opp=str(getattr(ref, f"{'away' if side == 'home' else 'home'}_name",
                            "") or ""),
            team_key=str(getattr(ref, side, "")),
            opp_key=str(getattr(ref, "away" if side == "home" else "home", "")),
            seed="", rerank_query=RERANK, budget=_budget())
        print(f"- {side} 질의 {len(mine)}개 → 던진다(상한 {sub.budget.search_cap})")
        got_docs += await s3_docs.gap_docs(
            ref, state=st, chain=chain, net=net, cache=cache,
            queries=mine, sub=sub, tag=f"gap-{side}")
    print(f"- 표적 문서 **{len(got_docs)}건**")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **0건이면 어디서 떨어졌나를 적는다**(규율 #3 조용한 0 금지)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-14: 표적 질의가 265건을 받았는데 `gap_docs` 를 지나자
    #     문서가 **0건**이 됐다. 🔴 어느 검문(도메인 등급·신원·날짜)에서
    #     떨어졌는지 **세어** 보지 않으면 추측으로 고치게 된다(#4).
    if not got_docs:
        import collections as _c
        tally = _c.Counter()
        for d in (st.drops or []):
            what = str(getattr(d, "what", "") or "")
            if "gap" in what:
                tally[str(getattr(d, "reason", "") or "?")] += 1
        print(f"    🔴 **0건 — 버린 사유** {dict(tally) or '⬜ 기록 없음'}")
        for one in [x for x in (st.notes or []) if "gap" in str(x)][-8:]:
            print(f"    · {str(one)[:170]}")
    for d in got_docs[:8]:
        # 🔴🔴 **본문·발행일·등급을 함께 적는다**(규율 #3) — *"자료가 안 왔다"* 와
        #    *"왔는데 못 뽑았다"* 를 가른다. ⚠️ 실측 2026-10-14: 표적 문서 5건이
        #    왔는데 추출 후보가 **0개**였다 — 어느 쪽인지 수로 가린다.
        body = str(getattr(d, "body", "") or getattr(d, "text", "") or "")
        print(f"    · {str(getattr(d, 'title', '') or '')[:70]}")
        print(f"        본문 {len(body):,}자 · 발행 "
              f"{str(getattr(d, 'published', '') or '⬜')} "
              f"· 날짜출처 {str(getattr(d, 'date_source', '') or '⬜')} "
              f"· 등급 {str(getattr(d, 'tier', '') or '⬜')} "
              f"· 하위 {str(getattr(d, 'subtask', '') or '⬜')}")
    # ── ⑧ 추출 → 검증 → **변수**
    if got_docs:
        more = await s4_extract.run(ref, got_docs, state=st, chain=chain,
                                    net=net, cache=cache)
        said_v2 = s5_verify.run(ref, facts, got_docs, more, state=st,
                                turnover=turn)
        print(f"## ⑧ 표적 추출·검증 — 후보 {len(more)} → 변수 **{len(said_v2)}개**")
        # 🔴 후보 0 이면 **추출이 무엇을 말했나**를 그대로 적는다(#3)
        if not more:
            for one in [x for x in (st.notes or [])
                        if "s4" in str(x) or "추출" in str(x)][-6:]:
                print(f"    🔴 {str(one)[:200]}")
            for d in (st.drops or [])[-6:]:
                what = str(getattr(d, "what", "") or "")
                if "s4" in what or "gap" in what:
                    print(f"    🔴 버림 {what[:60]} — "
                          f"{getattr(d, 'reason', '?')} · "
                          f"{str(getattr(d, 'detail', '') or '')[:110]}")
        for v in said_v2:
            print(f"- `{v.id}` [{v.type}] {str(v.claim or '')[:110]}"
                  + (f" · 원천 {v.n_sources}곳" if getattr(v, "n_sources", 0)
                     else ""))
        # 🔴 **자리**를 보인다 — 확률에 닿는가(축·λ상수)가 그 칸에서 보인다
        from app.core import routing as _rt
        box = _rt.place(list(variables) + list(said_v2) + list(var_lr))
        AX = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
        print("## ⑨ 배치 — 확률에 닿는가")
        for row in box.rows:
            hit = "✅ 닿는다" if (set(row.places) & AX) else "— 표시·검증·가설만"
            print(f"- `{row.id}` [{row.type}] 자리 {row.places} {hit}")
        for bad in box.fails[:4]:
            print(f"- 🔴 {bad}")
    else:
        print("## ⑧ 표적 추출 — ⬜ **문서 0건이라 안 돌렸다**")
    print(flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑩~⑯** — 배치 → 상성 → 확률 → 시뮬 → 종합 평(지시 2026-10-15)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 전부 **실제 단계**를 import 해서 부른다(규율 #12 프로브 금지).
    #  ⚠️ ⑰ 이후(세 열·보드·등급·카드)는 **안 돈다** — 지시: *"17단계 이후는
    #     그냥 없어도 된다"*.
    from app.core import matchup as _mu
    from app.core import probmodel as _pm
    from app.core import routing as _rt2
    from app.core.stages import s2e_matchup as _s2e
    from app.core.stages import s6_verdict as _vd

    all_vars = list(variables) + list(var_lr)
    varset = _rt2.place(all_vars)
    print("## ⑩ 변수 배치")
    AX2 = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
    for row in varset.rows:
        hit = "✅ 확률에 닿는다" if (set(row.places) & AX2) else "— 표시·검증·가설"
        print(f"- `{row.id}` [{row.type}] 자리 {row.places} {hit}")
    for bad in varset.fails[:4]:
        print(f"- 🔴 {bad}")
    print(flush=True)

    print("## ⑬ 상성 재료 + ⑭ 축 판정", flush=True)
    edge = await _s2e.run(ref, facts, state=st, net=net, varset=varset,
                          turnover=turn, strategy=plan)
    mr = _mu.report(ref, facts, edge, varset, strategy=plan, turnover=turn)
    for key in ("axis0", "axis1", "axis2", "axis3"):
        ax = mr.axis(key)
        h, a = getattr(ax, "home", None), getattr(ax, "away", None)
        if h is None or a is None:
            print(f"- {key} — ⬜ {str(getattr(ax, 'why', '') or '')[:110]}")
        else:
            print(f"- {key} — 홈 {h:.4f} · 원정 {a:.4f} · 차 {h - a:+.4f} "
                  f"· 근거 {list(getattr(ax, 'refs', None) or []) or '없다'}")
    print(f"- 축 종합 — {float(getattr(mr, 'total', 0.0) or 0.0):+.4f}\n",
          flush=True)

    print("## ⑮ 확률 + ⑯ 시뮬", flush=True)
    prob = _pm.run(ref, facts, mr, varset, edge=edge, state=st)
    if not prob.ok():
        print(f"- 🔴 확률을 못 냈다 — {prob.gap or prob.why}")
        return 4
    print(f"- **홈 {prob.home:.1%} · 무 {prob.draw:.1%} · 원정 {prob.away:.1%}**")
    print(f"- λ — 홈 {float(dict(prob.lam or {}).get('home') or 0):.3f} · "
          f"원정 {float(dict(prob.lam or {}).get('away') or 0):.3f}")
    print(f"- 오버 — " + " · ".join(
        f"{k} {float(v):.1%}" for k, v in list(dict(prob.over or {}).items())[:5]))
    print(f"- 유도 — {str(prob.why or '')[:420]}\n", flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑯ 종합 평 — solar**(지시 2026-10-15)
    # ══════════════════════════════════════════════════════════════════
    print("## ⑯ 종합 평 (solar)", flush=True)
    said_vd, said_box, why_vd = _vd.ask(ref, prob, mr, varset, state=st)
    print(f"- 호출 — {why_vd}")
    print(f"- 🔴 **묶음은 코드가 만들었다**({len(said_box)}줄) — 모델이 만든 "
          "글자가 하나도 없다")
    for one in said_box:
        print(f"    │ {one[:170]}")
    print()
    print(_vd.said_of(said_vd, said_box))
    print(flush=True)

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
