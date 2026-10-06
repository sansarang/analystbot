"""🔴🔴 **v6 파이프라인 — 단계를 순서로 잇는다**(§5 · §8 3단계).

```
Question → s1 → s2 → s3 → s4 → s5 → s6 → s7 → Card
```

🔴 **단계는 예외를 위로 던지지 않는다** — 빈 출력 + `state` 의 사유로 다음 단계가
   돈다. 그래서 **카드는 항상 나온다**(§5). ⚠️ 그것이 2026-10-06 의 결함 ④
   (*"카드가 통째로 안 나왔다"*)를 구조로 막는 자리다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.schema import (Ambiguous, Board, Card, Doc, Facts, Funnel,
                             HypoSet, Judgement, MatchRef, Question, Variable)
from app.core.state import RunState


async def analyze(raw: str, *, pool: Any, net: Any, chain: Any,
                  state: RunState | None = None, board: Board | None = None,
                  now: datetime | None = None) -> Card | Ambiguous:
    """🔴 질문 하나 → 카드 하나. ⚠️ 경기를 **못 고르면** `Ambiguous`(묻는다)."""
    from app.core.stages import (s1_resolve, s2_facts, s3_docs, s4_extract,
                                 s5_verify, s6_hypo, s7_judge)
    st = state if state is not None else RunState()
    q = _question(raw, now=now)
    ref = await s1_resolve.run(q, pool=pool, state=st, net=net)
    if isinstance(ref, Ambiguous):
        return ref
    st.match_key = ref.id
    facts = await s2_facts.run(ref, state=st, net=net)
    cache: dict[str, Doc] = {}
    docs = await s3_docs.run(ref, facts, state=st, chain=chain, net=net,
                             cache=cache)
    cands = await s4_extract.run(ref, docs, state=st, chain=chain, net=net,
                                 cache=cache)
    # 🔴 s4 가 좁히기 2차로 문서를 더 받았을 수 있다 — **캐시가 전부를 든다**
    docs = list(cache.values()) or docs
    variables = s5_verify.run(ref, facts, docs, cands, state=st)
    hypo = s6_hypo.run(ref, facts, variables, state=st)
    said = s7_judge.run(ref, facts, variables, hypo, state=st, board=board,
                        now=now)
    return card_of(ref, facts, variables, hypo, said, state=st)


def card_of(ref: MatchRef, facts: Facts, variables: list[Variable],
            hypo: HypoSet, said: Judgement, *, state: RunState) -> Card:
    """🔴 카드 하나로 모은다 — 렌더러가 보는 것은 **이 타입 하나**다(§3)."""
    return Card(
        match=ref, facts=facts, variables=variables,
        drops=[*state.drops, *hypo.drops], hypo=hypo, evals=said.evals,
        direction=said.direction, conclusion=said.conclusion,
        triggers=said.triggers,
        funnel=Funnel(counts=state.counted(),
                      drops=[*state.drops, *hypo.drops]),
        cost=state.wallet.snapshot(), started=said.started)


def _question(raw: str, *, now: datetime | None = None) -> Question:
    """🔴 `"A vs B"` 를 가른다. ⚠️ 못 가르면 **통째로** 한 이름으로 둔다(s1 이 본다)."""
    said = str(raw or "").strip()
    low = said.lower()
    team, opp = said, ""
    # 🔴 구분자 목록은 **옛 핸들러와 같다**(`app/bot/main.py`) — 4단계에서 입구를
    #    갈아끼웠으니 받는 꼴이 좁아지면 그것은 **기능 퇴화**다.
    for sep in (" vs ", " vs. ", " - ", " 대 ", " : "):
        if sep in low:
            i = low.index(sep)
            team, opp = said[:i].strip(), said[i + len(sep):].strip()
            break
    else:
        # ⚠️ `중국 팔레스타인` 처럼 **두 낱말**이면 둘째를 상대로 본다(옛 규칙).
        words = said.split()
        if len(words) == 2:
            team, opp = words[0], words[1]
    return Question(raw=said, team=team, opponent=opp,
                    asked_at=(now or datetime.now(timezone.utc)))
