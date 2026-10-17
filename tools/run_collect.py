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
s1_resolve → s2_facts(fotmob: XI·결장·감독) → s4b_gapsearch(LLM 서치)
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


#: 🔴🔴 **단계 장부** — 사용자 지시 2026-10-15: *"16단계 중 어느 하나 그냥
#   넘어가면 안된다..모니터링 해라"*
#
#  꼴: `{단계: (상태, 한 줄)}` · 상태는 `✅ 돌았다` · `⬜ 못 돌았다` · `🔴 빈손`
#  🔴 **빈손**은 돌았지만 산출이 0 인 것이다 — `✅` 와 **가른다**(#3).
LEDGER: dict = {}

#: 🔴 16단계의 **이름표** — 하나라도 장부에 없으면 보고가 빨개진다
STEPS: tuple[str, ...] = (
    "① 경기", "② fotmob(XI·결장·감독)", "②-b 선수단 교체", "③ 딥서치",
    "④ 추출", "⑤ 검증", "⑤-b 포메이션·전략",
    # 🔴 **선수 능력치**(사용자 지시 2026-10-17) — 교체 짝의 자리별 백분위
    "⑤-b1 선수 능력치",
    "⑤-b2 전략 전문가(LLM)",
    # 🔴 **충돌·단독 갈래 판정**(사용자 지시 2026-10-16) — 상대 모델이 서치해서 본다
    "⑤-b3 갈래 판정",
    "⑤-c 리그·컵 분석",
    "3+5 통합", "⑥ LLM 표적 질의", "⑦ 표적 문서", "⑧ 표적 추출",
    "⑩ 변수 배치", "⑬⑭ 상성·축", "⑮⑯ 확률·시뮬", "⑯ 종합 평(solar)",
    "⑯ 종합 평(deepseek)")


def say_var(v, cut: int = 100) -> None:
    """🔴🔴 변수 한 줄 — **꼬리표 사유는 따로 찍는다**(사용자 지시 2026-10-16).

    ⚠️ 실사고 2026-10-16(Obolon Kyiv): 카드에 `… 🔴 **안전장치**: 🔴 ` 까지만
       찍히고 **사유가 잘렸다** — 글을 `claim[:100]` 으로 잘랐기 때문이다.
       🔴 *조용한 0* 은 아니었지만, **왜 맥락 전용인지 읽을 수 없었다**(#3 의 뜻은
       "이름으로 남긴다"이지 "글자를 남긴다"가 아니다).
    ⚠️ 실사고 2026-10-17(Necaxa vs Atlas): **갈래 판정** 사유도 같은 병이었다.
    🔴 그래서 꼬리표를 **둘째 줄**로 온전히 적는다 — 쪼개는 곳은
       `core/crosscheck.tails_of` 하나다(#1 사본 금지).
    """
    from app.core import crosscheck as _cc
    head, tails = _cc.tails_of(getattr(v, "claim", ""))
    print(f"- `{v.id}` [{v.type}] {head[:cut]}"
          + (f" · 원천 {v.n_sources}곳" if getattr(v, "n_sources", 0) else ""),
          flush=True)
    for said_t in tails:
        print(f"    └ {said_t}"[:450], flush=True)


def mark(step: str, state: str, said: str = "") -> None:
    """🔴 장부에 적는다. ⚠️ 적지 않으면 보고가 *"그냥 넘어갔다"* 로 센다."""
    LEDGER[step] = (state, said)
    print(f"    [장부] {step} — {state}" + (f" · {said[:110]}" if said else ""),
          flush=True)


def report_ledger() -> int:
    """🔴🔴 **정직한 보고** — 돌은 칸·빈손 칸·안 돈 칸을 가른다. 돌려주는 것은
    *"그냥 넘어간 칸 수"* 다(0 이어야 한다)."""
    print("\n" + "=" * 66)
    print("## 🔎 16단계 장부 — 어느 하나 그냥 넘어가면 안 된다")
    print("=" * 66)
    gone, empty, ok = [], [], []
    for step in STEPS:
        state, said = LEDGER.get(step, ("⬜ 안 적혔다", ""))
        print(f"{state:<12} {step:<22} {said[:90]}")
        if state.startswith("✅"):
            ok.append(step)
        elif state.startswith("🔴"):
            empty.append(step)
        else:
            gone.append(step)
    print("-" * 66)
    print(f"✅ 돌았다 {len(ok)} · 🔴 빈손 {len(empty)} · ⬜ 안 돌았다 {len(gone)}")
    if empty:
        print(f"🔴 **빈손**(돌았는데 산출 0) — {empty}")
    if gone:
        print(f"⬜ **안 돌았다** — {gone}")
    if not empty and not gone:
        print("🟢 **16단계 전부 산출이 있다**")
    return len(gone)


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

    # 🔴🔴 **중단 지점** — 사용자 지시 2026-10-15: *"첫단계부터 변수 수집
    #    단계까지만 한다 … 추가한 변수가 섰는지 확인 목적이다"*.
    #    ⚠️ 뒤 단계를 **돌리지 않는다**(예산·시간을 안 쓴다) — 장부는 그대로 찍어
    #       무엇을 안 돌렸는지 남긴다(#3 조용한 0 금지).
    said_until = ""
    rest = [x for x in argv[1:] if not str(x).startswith("--until")]
    for x in argv[1:]:
        if str(x).startswith("--until"):
            said_until = str(x).partition("=")[2] or "vars"
    argv = [argv[0], *rest]
    asked = argv[1] if len(argv) > 1 else "Feyenoord Como"
    st = RunState()
    # 🔴🔴 **시계는 `clock` 에 꽂는다** — 사용자 지시 2026-10-15(타임아웃 수정).
    #    ⚠️ 실사고 2026-10-15: 여기가 `st.deadline` 이었고 **읽는 곳이 없었다**
    #       (`state.clock` 이 그 칸이다 · `core/pipeline:97` 가 그렇게 한다).
    #       그래서 카드 상한이 **아예 안 걸려** MLS 10:30 실행이 27분 멈췄다.
    #    🔴 상한 값은 운영과 같은 그것이다(사본 금지 — `slate.CARD_CAP_MIN`).
    from app.core import slate as _slate
    st.clock = _dl.Deadline(_slate.CARD_CAP_MIN)
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
        for x in list(getattr(st, "notes", None) or [])[-6:]:
            print("  ·", str(x)[:150])
        return 2
    print(f"## ① 경기\n- {ref.home_name or ref.home} vs "
          f"{ref.away_name or ref.away} · {ref.competition} · "
          f"{ref.kickoff_utc}\n", flush=True)
    mark("① 경기", "✅ 돌았다",
         f"{ref.home_name or ref.home} vs {ref.away_name or ref.away}")

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
    n_xi = sum(1 for s2 in ("home", "away")
               if dict(getattr(facts, "xi", None) or {}).get(
                   str(getattr(ref, s2, "") or "")) is not None)
    n_co = sum(1 for s2 in ("home", "away")
               if str(getattr(dict(getattr(facts, "coach", None) or {}).get(
                   str(getattr(ref, s2, "") or "")), "name", "") or ""))
    n_ms = sum(len(v or []) for v in
               dict(getattr(facts, "missing", None) or {}).values())
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **XI 가 없는 까닭을 가른다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 라인업 발표가 됐는데 계속 못 찾는 이유가 뭐냐?
    #
    #  ⚠️ 실사고 2026-10-15: `XI 0/2` 한 줄로는 **셋을 구분할 수 없었다** —
    #     ① 라인업이 아직 안 나왔다(킥오프 1~2시간 전) ② **열쇠에 어댑터가
    #     없다**(`6054753` 처럼 접두가 빠져 받을 주소가 0건) ③ 받았는데 못 떴다.
    #     BG Pathum 은 ②였고, 그것을 ①로 읽어 **하루를 헛봤다**.
    #  🔴 그래서 열쇠의 어댑터를 **원본 라우팅**(`ingest.context_of`)으로 확인해
    #     적는다(사본 금지). 남은 시간도 함께 적는다.
    said_why = ""
    if not n_xi:
        from app.collect import ingest as _ing
        got_fn = _ing.context_of(ref.competition, ref.id)
        if not callable(got_fn):
            said_why = (f" · 🔴 **열쇠에 어댑터가 없다**(`{ref.id}`) — "
                        f"받을 주소가 0건이다(라인업 발표와 무관)")
        else:
            said_left = ""
            if getattr(ref, "kickoff_utc", None):
                from datetime import datetime, timezone
                mins = (ref.kickoff_utc
                        - datetime.now(timezone.utc)).total_seconds() / 60
                said_left = f" · 킥오프까지 {mins:.0f}분"
            said_why = (f" · ⬜ 주소는 있다(`{ref.id}`){said_left} — "
                        f"**아직 안 올라왔다**고 본다")
        print(f"    🔎 XI 못 받은 까닭 —{said_why.lstrip(' ·')}", flush=True)
    mark("② fotmob(XI·결장·감독)",
         "✅ 돌았다" if n_xi else "🔴 빈손",
         f"XI {n_xi}/2 · 감독 {n_co}/2 · 결장 {n_ms}명 · 사다리 "
         + "/".join(f"{r.get('rung')}{r.get('got')}" for r in rungs)
         + said_why)

    # ── ②-b 선수단 교체 — 🔴 s3 **앞**이다(파이프라인 순서 그대로 · 지시
    #    2026-10-10 ③). 재료는 `facts` 뿐이다(새 통신 0건).
    turn = {side: _turn.read(ref, facts, side=side) for side in ("home", "away")}
    print("## ②-b 선수단 교체")
    for side, one in turn.items():
        print(f"- {side} — " + ("🔴 **켜졌다** · " if one.get("on") else "")
              + str(one.get("why") or "")[:160])
    mark("②-b 선수단 교체", "✅ 돌았다",
         " · ".join(f"{k} {'켜짐' if dict(v).get('on') else '꺼짐'}"
                    for k, v in turn.items()))
    print(flush=True)

    # ── ③ LLM 서치 수확 — 🔴 **딥서치는 지웠다**(사용자 지시 2026-10-17)
    #    🔴 입구는 `s4b_gapsearch.harvest` **하나**다 — 운영도 그것을 부른다
    #       (#1 사본 금지: 종전엔 이 배선이 러너에만 있었다).
    cache: dict = {}
    docs, _why_h = await s4b_gapsearch.harvest(
        ref, facts, state=st, chain=chain, net=net, cache=cache, variables=None)
    print(f"## ③ LLM 서치 — 문서 **{len(docs)}건**", flush=True)
    # 🔴🔴 **왜 그만큼인지 보인다** — 사용자 지시 2026-10-15: *"왜 이렇게
    #    빈손인지 확인해라"*. ⚠️ 종전엔 **수만** 찍어서 질의가 나빴는지,
    #    검색이 0건이었는지, 검문이 버렸는지 **구분할 수 없었다**(#3).
    # ⚠️ `state.notes` 는 **리스트**다(메서드가 아니다 — 실측 2026-10-15)
    for one in list(getattr(st, "notes", None) or []):
        said = str(one)
        if any(k in said for k in ("질의", "s3", "버린", "사유", "후보")):
            print(f"    · {said[:200]}", flush=True)
    for d in list(docs)[:8]:
        print(f"    📄 {str(getattr(d, 'title', '') or '')[:70]} · "
              f"{str(getattr(d, 'url', '') or '')[:70]}", flush=True)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **버린 문서를 사유별로 적는다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-15(BG Pathum): 열기 시도 열 번 중 **여섯 번이
    #     `받은 문서 0건`** 이었고 53·55건 중 손에 든 것은 **5건**이었다.
    #     그런데 장부는 `✅ 돌았다 · 문서 5건` 만 찍어서 **버린 것이 안 보였다**
    #     (#3 조용한 0 금지 · 버린 사유는 `state.drops` 에 **이미 있었다**).
    #  🔴 그래서 사유를 **종류별로 세어** 찍고, 가장 아픈 몇 줄은 **글자로** 적는다.
    said_drop = [d for d in list(getattr(st, "drops", None) or [])
                 if str(getattr(d, "stage", "") or "").startswith("s3")]
    if said_drop:
        box: dict = {}
        for d in said_drop:
            key = str(getattr(getattr(d, "reason", ""), "value", "")
                      or getattr(d, "reason", ""))
            box[key] = box.get(key, 0) + 1
        print("- 🔴 **버린 문서** "
              + " · ".join(f"{k} {v}건" for k, v in
                           sorted(box.items(), key=lambda kv: -kv[1])),
              flush=True)
        for d in said_drop[:6]:
            print(f"    🗑 {str(getattr(d, 'what', ''))[:46]} — "
                  f"{str(getattr(d, 'detail', ''))[:150]}", flush=True)
    print(flush=True)
    mark("③ 딥서치", "✅ 돌았다" if docs else "🔴 빈손",
         f"문서 {len(docs)}건"
         + (f" · 🔴 버림 {len(said_drop)}건" if said_drop else ""))

    # ── ④⑤ 추출 · 검증
    cands = await s4_extract.run(ref, docs, state=st, chain=chain, net=net,
                                 cache=cache)
    docs = list(cache.values()) or docs
    # 🔴🔴 **`turnover=turn` 을 넘긴다** — 운영 `pipeline` 이 그렇게 부른다.
    #    ⚠️ 실사고 2026-10-15: 내가 `turnover={}` 로 불러 `TURN-*` 변수가 1차에서
    #       안 만들어졌고, 표적 s5 에서만 나와 **varset 이 둘로 갈렸다**.
    variables = s5_verify.run(ref, facts, docs, cands, state=st, turnover=turn)
    print(f"## ④⑤ 추출·검증 — 후보 {len(cands)} → 변수 **{len(variables)}개**")
    mark("④ 추출", "✅ 돌았다" if cands else "🔴 빈손", f"후보 {len(cands)}개")
    mark("⑤ 검증", "✅ 돌았다" if variables else "🔴 빈손",
         f"변수 {len(variables)}개")
    for v in variables[:12]:
        say_var(v, 100)
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
    mark("⑤-b 포메이션·전략",
         "✅ 돌았다" if list(getattr(plan, "lines", None) or []) else "🔴 빈손",
         f"판정 {getattr(plan, 'audit', '?')} · 줄 "
         f"{len(list(getattr(plan, 'lines', None) or []))}개")
    print(flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑤-b2 전략 전문가(LLM)** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 라인업 확장 포메이션 결장 선수가 **주요선수가 뜨면** 전략 전문가
    #  > deepseek 에게 **변수 생성하는 프롬프트**를 주입해라.
    #
    #  🔴 트리거가 있을 때만 부른다 · 공급자는 **deepseek 우선**(죽으면 solar).
    #  🔴 LLM 은 **글만** 낸다 — 방향(`favors`)·가중은 코드가 넣는다(절대규칙 5).
    #     그래서 이 변수들은 지금 🟡 **표시·검증·가설**이다(축을 안 민다).
    from app.core import strategy_llm as _sl
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑤-b1 선수 능력치**(사용자 지시 2026-10-17) — 교체 짝 + 핵심 선수의
    #    **자리별 백분위**를 받아 `강점/보통/약점` 글자로 ⑤-b2 에 넘긴다.
    # ══════════════════════════════════════════════════════════════════
    from app.core import ability as _ab3
    said_tg, said_why_tg = _ab3.targets(ref, facts, plan)
    said_box, said_why_ab = await _ab3.fetch(net, said_tg, clock=st.clock)
    said_ability = _ab3.said_of(said_tg, said_box, ref=ref)
    print("## ⑤-b1 선수 능력치")
    print(f"- {said_why_tg} · {said_why_ab}")
    for one in said_ability:
        print(f"  {one}")
    mark("⑤-b1 선수 능력치",
         "✅ 돌았다" if said_box else "🔴 빈손", said_why_ab[:110])
    print(flush=True)
    # 🔴 **최근 5경기 기준**으로도 갈래를 찾게 재료를 넘긴다(지시 2026-10-15)
    # 🔴🔴 **충돌·단독 갈래 그릇**(지시 2026-10-16) — 아래 ⑤-b3 가 판정한다
    said_branch: list = []
    var_sl, said_sl = _sl.ask(ref, facts, plan, state=st,
                              recent=_sl.recent_of(variables),
                              # 🔴 **기사 사실도 넘긴다**(지시 2026-10-15) —
                              #    확률은 기사를 안 세고, 내용 판단은 여기서 한다
                              # 🔴 **피로도 재료**(지시 2026-10-16) — 휴식일·
                              #    직전 경기일·최근 경기 수(코드가 센 수다)
                              rest=_sl.rest_of(ref, facts),
                              news=_sl.news_of(variables),
                              # 🔴 **능력치 재료**(지시 2026-10-17)
                              ability=said_ability,
                              branches=said_branch)
    print("## ⑤-b2 전략 전문가(LLM)")
    print(f"- {said_sl}")
    for one in var_sl:
        print(f"    `{one.id}` {one.claim[:150]}")
    mark("⑤-b2 전략 전문가(LLM)",
         "✅ 돌았다" if var_sl else "🔴 빈손", said_sl[:110])
    print(flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑤-b3 갈래 판정** — 사용자 지시 2026-10-16
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 충돌되는 것·한쪽만 나오는 것도 **버리는 게 아니라 어느 쪽이 맞는지
    #  > 확인**해야 한다 … 각 LLM 이 낸 내용을 **다른 LLM 이 서치해서 검증**
    #
    #  🔴 1단 코드가 가진 수 → 2단 교차 검증(상대 모델이 서치) → 3단 채택·보류
    print("## ⑤-b3 갈래 판정(충돌·단독)")
    if var_sl and said_branch:
        from app.core import branchjudge as _bj
        var_sl, said_bj = await _bj.run(said_branch, var_sl, ref, facts, plan,
                                        state=st, net=net, chain=chain)
        print(f"- {said_bj}")
        for one in said_branch:
            print(f"    [{one.mode}] `{one.kind}` — {one.why or '⬜ 사유 없음'}")
            # 🔴 양쪽 주장 한 줄은 `Branch.said()` 하나가 만든다(사본 금지)
            print(f"        주장 — {one.said()}")
            for c in one.claims:
                print(f"        `{c.provider}` `{c.cmp}` 판정 "
                      f"{c.ruling or '⬜ 안 물었다'}"
                      + (f" · 판정자 {c.judge_pv}" if c.judge_pv else "")
                      + (f" · 인용 「{c.quote[:70]}」" if c.quote else ""))
        mark("⑤-b3 갈래 판정",
             "✅ 돌았다" if any(b.picked for b in said_branch) else "🟡 보류",
             said_bj[:110])
    else:
        print("- ⬜ 충돌·단독 갈래가 없다 — 판정할 것이 없다")
        mark("⑤-b3 갈래 판정", "⬜ 갈래 없음", "충돌·단독 0개")
    print(flush=True)

    # 🔴 **여기서 멈춘다**(`--until=vars`) — 변수 수집까지만 보는 실행이다
    if said_until in ("vars", "변수", "5b2"):
        print("## 🔴 **변수 수집까지만 돌렸다**(`--until=vars`) — 뒤 단계는 "
              "안 돌렸다\n")
        # ⚠️ `var_lr`(⑤-c 리그·컵)은 **아직 안 돌았다** — 여기 넣으면 터진다
        said_all = list(variables) + list(var_sl)
        print(f"### 거둔 변수 **{len(said_all)}개**")
        from app.core import crosscheck as _cc3
        for one in said_all:
            # 🔴 꼬리표(안전장치·갈래 판정)는 **자르지 않는다**(2026-10-17)
            said_h, said_tails = _cc3.tails_of(getattr(one, "claim", ""))
            print(f"- `{one.id}` [{one.type}] favors={one.favors} · "
                  f"goals={one.goals} · w={one.weight} · "
                  f"기준가능={getattr(one, 'usable_as_basis', '?')}\n"
                  f"    {said_h[:170]}")
            for said_t in said_tails:
                print(f"    └ {said_t}"[:450])
        print(flush=True)
        return report_ledger() and 0 or 0

    # ── 3+5 통합 — 사다리 칸 4 를 기사로 다시 센다
    got_r, why_r = _ab.recount(rungs, variables,
                               keys=[str(ref.home), str(ref.away)])
    print(f"## 3+5 통합\n- {why_r}\n", flush=True)
    n4 = next((int(x.get("got") or 0) for x in got_r
               if str(x.get("rung")) == "국내 기사"), 0)
    mark("3+5 통합", "✅ 돌았다" if n4 else "🔴 빈손", f"칸 4 = {n4}건")

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
    mark("⑤-c 리그·컵 분석", "✅ 돌았다" if var_lr else "🔴 빈손",
         f"변수 {len(var_lr)}개 · {str(why_lr)[:80]}")
    print(flush=True)

    # ── ⑥⑦ LLM 서치 **2차** — 🔴 변수를 본 뒤 빈 칸을 겨냥한다
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **손으로 짠 판을 걷었다** — #1 사본 금지(2026-10-17)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 자리에는 `need`→`ask`→`Subtask`→`gap_docs` 를 **손으로 엮은
    #     80여 줄**이 있었고 운영(`pipeline`)에는 그 배선이 **없었다** — 러너
    #     에서만 도는 길이었다(*"안 이은 코드는 없는 코드보다 나쁘다"* · #2).
    #  🔴 이제 입구는 `s4b_gapsearch.harvest` 하나고 운영도 같은 것을 부른다.
    print("## ⑥⑦ LLM 서치 2차(변수 본 뒤)")
    got_docs, why_h2 = await s4b_gapsearch.harvest(
        ref, facts, state=st, chain=chain, net=net, cache=cache,
        variables=variables, tag="gap2")
    print(f"- {why_h2}")
    mark("⑥⑦ LLM 서치 2차", "✅ 돌았다" if got_docs else "🔴 빈손",
         f"문서 {len(got_docs)}건 · {str(why_h2)[:70]}")
    print(f"- 표적 문서 **{len(got_docs)}건**")
    mark("⑦ 표적 문서", "✅ 돌았다" if got_docs else "🔴 빈손",
         f"문서 {len(got_docs)}건")
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
        # 🔴 **하나의 varset** 에 들어갈 목록에 담는다(위 ② 의 까닭)
        gap_vars = [v for v in said_v2
                    if v.id not in {x.id for x in variables}]
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
        mark("⑧ 표적 추출", "✅ 돌았다" if said_v2 else "🔴 빈손",
             f"후보 {len(more)} → 변수 {len(said_v2)}개")
        for v in said_v2:
            say_var(v, 110)
        # 🔴 **자리**를 보인다 — 확률에 닿는가(축·λ상수)가 그 칸에서 보인다
        from app.core import routing as _rt
        # ⚠️ 여기서 또 배치하지 않는다 — ⑩ 이 **하나의 varset** 을 만든다.
        #    이 줄은 표적 변수의 자리만 미리 보이는 **참고**다.
        box = _rt.place(list(gap_vars))
        AX = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
        print("## ⑨ 배치 — 확률에 닿는가")
        for row in box.rows:
            hit = "✅ 닿는다" if (set(row.places) & AX) else "— 표시·검증·가설만"
            print(f"- `{row.id}` [{row.type}] 자리 {row.places} {hit}")
        for bad in box.fails[:4]:
            print(f"- 🔴 {bad}")
    else:
        print("## ⑧ 표적 추출 — ⬜ **문서 0건이라 안 돌렸다**")
        mark("⑧ 표적 추출", "⬜ 안 돌았다", "표적 문서가 0건이다")
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

    # 🔴🔴 **varset 은 하나다** — 운영 `pipeline:233` 이 그렇게 한다.
    #    ⚠️ 실사고 2026-10-15: ⑩ 배치 출력은 `variables + said_v2 + var_lr` 로
    #       찍고 축이 쓴 varset 은 `variables + var_lr` 였다 → **배치와 축
    #       refs 가 어긋났다**(TURN-away 가 축0·축1·축3 근거에서 빠졌다).
    # 🔴 전략 전문가 변수도 **같은 묶음**에 넣는다(묶음이 둘이면 배치와 축이
    #    어긋난다 — 실사고 2026-10-15 그 자리다)
    all_vars = list(variables) + list(gap_vars) + list(var_lr) + list(var_sl)
    varset = _rt2.place(all_vars)
    print("## ⑩ 변수 배치")
    AX2 = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
    for row in varset.rows:
        hit = "✅ 확률에 닿는다" if (set(row.places) & AX2) else "— 표시·검증·가설"
        print(f"- `{row.id}` [{row.type}] 자리 {row.places} {hit}")
    for bad in varset.fails[:4]:
        print(f"- 🔴 {bad}")
    AXm = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
    n_hit = sum(1 for r in varset.rows if set(r.places) & AXm)
    mark("⑩ 변수 배치", "✅ 돌았다" if varset.rows else "🔴 빈손",
         f"변수 {len(varset.rows)}개 · 확률에 닿는 것 {n_hit}개")
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
    # 🔴 `mr.total` 은 **없는 칸**이었다 — 참값은 `matchup.total_of`(verdict.score)
    print(f"- 축 종합 — {_mu.total_of(mr):+.4f}\n", flush=True)
    n_ax = sum(1 for k in ("axis0", "axis1", "axis2", "axis3")
               if getattr(mr.axis(k), "home", None) is not None)
    mark("⑬⑭ 상성·축", "✅ 돌았다" if n_ax else "🔴 빈손",
         f"선 축 {n_ax}/4 · 종합 {_mu.total_of(mr):+.4f}")

    print("## ⑮ 확률 + ⑯ 시뮬", flush=True)
    prob = _pm.run(ref, facts, mr, varset, edge=edge, state=st)
    if not prob.ok():
        print(f"- 🔴 확률을 못 냈다 — {prob.gap or prob.why}")
        return 4
    print(f"- **홈 {prob.home:.1%} · 무 {prob.draw:.1%} · 원정 {prob.away:.1%}**")
    # 🔴 **λ·오버·스코어는 뺐다**(사용자 결정 2026-10-15 3번) — 비었으면 ⬜ 로
    #    적고 지어내지 않는다(#3).
    if not dict(prob.lam or {}):
        print("- λ(기대 득점)·오버·스코어 — 🔴 **뺐다**(3번 · 승무패는 λ 를 "
              "안 본다)")
    if dict(prob.lam or {}):
        print(f"- λ — 홈 {float(dict(prob.lam or {}).get('home') or 0):.3f} · "
              f"원정 {float(dict(prob.lam or {}).get('away') or 0):.3f}")
    if dict(prob.over or {}):
        print("- 오버 — " + " · ".join(
            f"{k} {float(v):.1%}" for k, v in list(dict(prob.over or {}).items())[:5]))
    # 🔴🔴 **자르지 않는다** — 실사고 2026-10-15: 420자로 잘라 찍었더니 λ 보정
    #    글자가 안 보여 *"보정이 안 걸렸다"* 로 **잘못 결론**했다(규율 #4).
    print(f"- 유도 — {str(prob.why or '')}")
    said_lr_txt = ("✅ 걸렸다" if "λ 보정" in str(prob.why or "")
                   else "🔴 **안 걸렸다**")
    print(f"- λ 보정 — {said_lr_txt}\n", flush=True)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **전략 변수를 빼면 확률이 어떻게 되나** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 경기가 진행하지 않았다는 근거하에 **확률이 어떻게 바뀄는지** 보여주라
    #
    #  🔴 효과를 떼려면 **같은 자료로 넣고/빼고** 재야 한다 — 수집을 다시 하지
    #     않고 **배치·축·확률만** 다시 돈다(LLM 비용 0 · 순수 계산).
    #  ⚠️ 이 둘을 섞어 적지 않는다 — 운영 값은 **넣은 쪽**이다.
    if var_sl:
        said_wo = [v for v in all_vars if not str(v.id).startswith("SL")]
        set_wo = _rt2.place(said_wo)
        mr_wo = _mu.report(ref, facts, edge, set_wo, strategy=plan,
                           turnover=turn)
        prob_wo = _pm.run(ref, facts, mr_wo, set_wo, edge=edge, state=st)
        print("## 🔬 전략 변수 효과(같은 자료 · 배치·축·확률만 다시 셌다)")
        # 🔴 **센 것을 보인다** — 수가 같으면 비교 자체가 거짓이다(#3)
        print(f"- 축2 변수 — 넣고 {len(varset.of('axis2'))}개 ↔ 빼고 "
              f"{len(set_wo.of('axis2'))}개 · 전략 변수 {len(var_sl)}개")
        print(f"- 축2 사유(넣고) — {str(mr.axis('axis2').why or '')[:150]}")
        print(f"- 축2 사유(빼고) — {str(mr_wo.axis('axis2').why or '')[:150]}")
        if prob_wo.ok():
            print(f"- **빼면** 홈 {prob_wo.home:.1%} · 무 {prob_wo.draw:.1%} "
                  f"· 원정 {prob_wo.away:.1%}")
            print(f"- **넣으면** 홈 {prob.home:.1%} · 무 {prob.draw:.1%} "
                  f"· 원정 {prob.away:.1%}")
            print(f"- 차 — 홈 {prob.home - prob_wo.home:+.1%} · "
                  f"무 {prob.draw - prob_wo.draw:+.1%} · "
                  f"원정 {prob.away - prob_wo.away:+.1%}")
            lam_a = dict(prob.lam or {})
            lam_b = dict(prob_wo.lam or {})
            print(f"- λ — 홈 {float(lam_b.get('home') or 0):.3f} → "
                  f"{float(lam_a.get('home') or 0):.3f} · 원정 "
                  f"{float(lam_b.get('away') or 0):.3f} → "
                  f"{float(lam_a.get('away') or 0):.3f}")
            o_a = dict(prob.over or {})
            o_b = dict(prob_wo.over or {})
            if "2.5" in {str(k) for k in o_a} or 2.5 in o_a:
                k = 2.5 if 2.5 in o_a else "2.5"
                print(f"- 오버 2.5 — {float(o_b.get(k) or 0):.1%} → "
                      f"{float(o_a.get(k) or 0):.1%}")
            for key in ("axis0", "axis1", "axis2", "axis3"):
                x, y = mr_wo.axis(key), mr.axis(key)
                gx = getattr(x, "gap", None)
                gy = getattr(y, "gap", None)
                if gx is None and gy is None:
                    continue
                print(f"    {key} 차 {float(gx or 0):+.4f} → "
                      f"{float(gy or 0):+.4f}")
        else:
            print(f"- 🔴 빼고는 확률을 못 냈다 — {prob_wo.gap or prob_wo.why}")
        print(flush=True)
    mark("⑮⑯ 확률·시뮬", "✅ 돌았다",
         f"홈 {prob.home:.1%}/무 {prob.draw:.1%}/원정 {prob.away:.1%} · "
         f"스코어 칸 {len(dict(prob.scores or {}))}개")

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑯ 종합 평 — solar**(지시 2026-10-15)
    # ══════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **두 모델을 같은 묶음으로** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > solar 서술형 카드와 deepseek 서술형 카드 **동시에** 보여주라
    #
    #  🔴 묶음은 **한 번만** 만들고 둘에게 **그대로** 넘긴다 — 다시 만들면
    #     미세하게 달라져 비교가 뜻을 잃는다.
    print("## ⑯ 종합 평 — solar · deepseek **같은 묶음**", flush=True)
    # 🔴 **문서도 넘긴다**(지시 2026-10-15) — 평이 기사·출처를 쓰게 한다
    # 🔴🔴 **포메이션·전략도 넘긴다**(사용자 지시 2026-10-15: *"포메이션 전략
    #    등을 동반하여 예측글을 작성하라"*) — ⑤-b 판정(`plan`)과 ⑤-b2 전략
    #    전문가 변수(`var_sl`)다. ⚠️ 안 넘기면 묶음에 그 칸이 **⬜ 로만** 남고
    #    평이 전략을 말할 재료가 없다(실측 Atalanta vs Pafos).
    said_box = _vd.chain_of(ref, prob, mr, varset, docs=docs,
                            plan=plan, strat=var_sl)
    print(f"- 🔴 **묶음은 코드가 만들었다**({len(said_box)}줄) — 모델이 만든 "
          "글자가 하나도 없다")
    for one in said_box:
        print(f"    │ {one[:170]}")
    print(flush=True)
    said_cards: dict = {}
    for pv in ("solar", "deepseek"):
        got_vd, _b, why_vd = _vd.ask(ref, prob, mr, varset, state=st,
                                     provider=pv, box=said_box)
        v, bad = _vd.judge(got_vd, said_box)
        said_cards[pv] = (got_vd, v, bad)
        print(f"### {pv} — 호출 {why_vd}")
        print(_vd.said_of(got_vd, said_box, provider=pv))
        print(flush=True)
    # 🔴🔴 **두 평의 공통점 ↔ 확률**(사용자 지시 2026-10-15) — 코드가 센다
    print(_vd.agree_of({k: v[0] for k, v in said_cards.items()}, prob),
          flush=True)
    print(flush=True)
    # 🔴 장부는 **둘 다** 적는다(하나만 적으면 다른 쪽이 조용히 넘어간다)
    mark("⑯ 종합 평(solar)",
         "✅ 돌았다" if said_cards["solar"][0] is not None else "🔴 빈손",
         f"지어냄 **{said_cards['solar'][1]}**"
         + (f" · 위반 {len(said_cards['solar'][2])}건"
            if said_cards["solar"][2] else ""))
    mark("⑯ 종합 평(deepseek)",
         "✅ 돌았다" if said_cards["deepseek"][0] is not None else "🔴 빈손",
         f"지어냄 **{said_cards['deepseek'][1]}**"
         + (f" · 위반 {len(said_cards['deepseek'][2])}건"
            if said_cards["deepseek"][2] else ""))

    mo, day = (0.0, 0.0)
    try:
        from app import solar
        mo, day = solar.spent()
    except Exception:                                       # noqa: BLE001
        pass
    print(f"\n## 비용\n- 월 ${mo:.4f} · 오늘(UTC) ${day:.4f}", flush=True)
    # 🔴🔴 **정직한 보고** — 그냥 넘어간 칸이 있으면 돌림값이 0 이 아니다
    n_gone = report_ledger()
    return 0 if n_gone == 0 else 5


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
