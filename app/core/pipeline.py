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
                             HypoSet, Judgement, MarketEval, MatchRef,
                             Question, Variable)
from app.core.state import RunState


#: 🔴 그 경기의 **마지막 실행**을 들고 있는 자리(재분석이 그것을 불러온다 · §4-1)
#
#  ⚠️ 모듈 전역이지만 **실행 상태가 아니다** — 재분석이 *"지난번 무엇을 봤나"* 를
#     알아야 하고, 그것은 프로세스가 사는 동안의 기억이다(봇이 한 프로세스다).
#  🔴 24시간이 지나면 **버린다**(§4-5: 그때는 전체를 새로 돈다).
_LAST: dict[str, dict] = {}
#: 🔴 그 기억을 몇 시간까지 쓰나 — §4-5 가 **24시간**이라 적었다
LAST_TTL_HOURS = 24


async def analyze(raw: str, *, pool: Any, net: Any, chain: Any,
                  state: RunState | None = None, board: Board | None = None,
                  board_text: str = "",
                  now: datetime | None = None) -> Card | Ambiguous:
    """🔴 질문 하나 → 카드 하나. ⚠️ 경기를 **못 고르면** `Ambiguous`(묻는다).

    🔴 `board_text` 를 주면 **코드가 파싱한다**(축구 §4 · `app/core/board.py`) —
       LLM 이 보드를 읽지 않는다.
    """
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
    got_board, extra, bad = board, [], []
    if board_text.strip():
        from app.core import board as _board
        got_board, extra, bad = _board.parse(board_text)
        st.note(f"보드 {len(got_board.lines)}줄 · 추가 {len(extra)} · "
                f"못 읽음 {len(bad)}")
    said = s7_judge.run(ref, facts, variables, hypo, state=st, board=got_board,
                        now=now)
    card = card_of(ref, facts, variables, hypo, said, state=st,
                   board_extra=extra, board_bad=bad)
    # 🔴 **마지막 실행을 기억한다** — 재분석이 s3·s4 를 다시 돌지 않게(§4-1)
    _LAST[ref.id] = {"at": (now or datetime.now(timezone.utc)), "ref": ref,
                     "docs": docs, "cands": cands, "card": card,
                     "board_text": board_text}
    return card


async def reanalyze(raw: str, *, pool: Any, net: Any, chain: Any,
                    state: RunState | None = None,
                    now: datetime | None = None) -> Card | Ambiguous:
    """🔴🔴 **재분석**(축구 완성 지시서 §4) — s2 만 다시 돌고 s3·s4 는 **안 돈다**.

    > 1. 그 경기의 마지막 실행(RunState·Doc 캐시)을 불러온다. 기사 검색(s3)·추출(s4)은
    >    **다시 하지 않는다** — 비용·시간을 아끼고 변수가 회차마다 흔들리지 않게.
    > 2. s2 만 다시 돈다: XI(확정 여부), 결장 명단, 같은 조 먼저 끝난 경기 결과.
    > 3. 바뀐 사실로 IR01~IR03·IR05 변수를 다시 만들고, s6·s7 을 다시 돈다.
    > 4. 카드 맨 위에 `재분석 — 바뀐 것:` 한 블록.
    > 5. 마지막 실행이 24시간 넘었거나 없으면 **전체를 새로** 돈다.
    """
    from app.core.stages import (s1_resolve, s2_facts, s5_verify, s6_hypo,
                                 s7_judge)
    st = state if state is not None else RunState()
    q = _question(raw, now=now)
    ref = await s1_resolve.run(q, pool=pool, state=st, net=net)
    if isinstance(ref, Ambiguous):
        return ref
    st.match_key = ref.id
    last = _LAST.get(ref.id)
    when = now or datetime.now(timezone.utc)
    if last is None:
        st.note("재분석 — 🔴 마지막 실행이 **없다** → 전체를 새로 돈다(§4-5)")
        return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                             now=now)
    old = last["at"]
    if (when - old).total_seconds() > LAST_TTL_HOURS * 3600:
        st.note(f"재분석 — 마지막 실행이 {LAST_TTL_HOURS}시간을 넘었다"
                f"({old:%m-%d %H:%M}Z) → 전체를 새로 돈다(§4-5)")
        return await analyze(raw, pool=pool, net=net, chain=chain, state=st,
                             now=now)
    before: Card = last["card"]
    # ── ② s2 만 다시 돈다(기사·추출은 그대로 쓴다)
    facts = await s2_facts.run(ref, state=st, net=net)
    docs, cands = list(last["docs"]), list(last["cands"])
    st.set("docs", len(docs))
    st.set("candidates", len(cands))
    variables = s5_verify.run(ref, facts, docs, cands, state=st)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **변수가 그대로면 DeepSeek 를 다시 부르지 않는다**(사용자 지시 ④)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 재분석: 변수 목록이 **바뀌지 않았으면** DeepSeek 를 다시 부르지 않고 **이전
    #  > 시나리오를 그대로** 쓴다. 변수가 바뀐 경우에만 s6 재실행.
    #  > *"사실 그대로 → 등급 그대로"* 를 E2E 불변식으로.
    #
    #  ⚠️ 실측 2026-10-06: 사실이 하나도 안 바뀐 재분석에서 가설·시나리오가 새로
    #     나와 **등급이 흔들렸다**(`무패 원정 소액하단 → 없음`). 그것은 분석이 바뀐
    #     것이 아니라 **모델이 흔들린 것**이다 — 사용자가 보는 수가 그래서 변하면
    #     되돌아볼 수가 없다.
    same = _same_vars(before.variables, variables)
    if same and before.hypo is not None:
        hypo = before.hypo
        st.note(f"재분석 — 변수 {len(variables)}개가 **그대로다** → DeepSeek 를 "
                f"부르지 않고 이전 시나리오 {len(hypo.scenarios)}개를 그대로 쓴다")
        st.set("scenarios", len(hypo.scenarios))
    else:
        hypo = s6_hypo.run(ref, facts, variables, state=st)
    got_board, extra, bad = None, list(before.board_extra), list(before.board_bad)
    if last.get("board_text"):
        from app.core import board as _board
        got_board, extra, bad = _board.parse(str(last["board_text"]))
    said = s7_judge.run(ref, facts, variables, hypo, state=st, board=got_board,
                        now=now)
    card = card_of(ref, facts, variables, hypo, said, state=st,
                   board_extra=extra, board_bad=bad,
                   changed=_diff(before, facts, variables, said))
    _LAST[ref.id] = {**last, "at": when, "card": card}
    return card


def _diff(before: Card, facts: Facts, variables: list[Variable],
          said: Judgement) -> list[str]:
    """🔴 **바뀐 것**(§4-4) — XI 상태·변수·등급·걸린 방아쇠.

    ⚠️ *"바뀐 게 없다"* 도 적는다 — 빈 블록은 *"안 봤다"* 와 구분이 안 된다(#3).
    """
    out: list[str] = []
    for key, now_xi in facts.xi.items():
        was = before.facts.xi.get(key)
        old_state = was.state if was is not None else "없음"
        if old_state != now_xi.state:
            out.append(f"XI {key} — {old_state} → **{now_xi.state}**")
    old_ids = {v.id: v for v in before.variables}
    new_ids = {v.id: v for v in variables}
    for vid in sorted(set(new_ids) - set(old_ids)):
        out.append(f"변수 **생김** `{vid}` — {new_ids[vid].claim[:60]}")
    for vid in sorted(set(old_ids) - set(new_ids)):
        out.append(f"변수 **사라짐** `{vid}` — {old_ids[vid].claim[:60]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **열쇠에 기준선을 넣는다** — 실측 2026-10-06(콜롬비아–페루 재분석)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `handicap/Peru` 한 열쇠에 **두 줄**(`+0.5` 없음 · `+1.5` 소액)이 들어가
    #     사전이 뒤 줄로 덮였고, 그래서 *"소액 → 없음"* 이라는 **거짓 변화**를 적었다.
    #     🔴 보드 두 줄은 다른 마켓이다 — 기준선이 열쇠의 일부다.
    def _k(e: MarketEval) -> str:
        point = "" if e.line.point is None else f" {e.line.point}"
        return f"{e.line.market}/{e.line.side}{point}"

    was_grade = {_k(e): e.grade for e in before.evals}
    for e in said.evals:
        old_g = was_grade.get(_k(e))
        if old_g is not None and old_g != e.grade:
            out.append(f"등급 `{_k(e)}` — {old_g} → **{e.grade}**")
    if not out:
        out.append("바뀐 것 **없다**(XI 상태·변수·등급 모두 같다)")
    return out


def card_of(ref: MatchRef, facts: Facts, variables: list[Variable],
            hypo: HypoSet, said: Judgement, *, state: RunState,
            board_extra: list[str] | None = None,
            board_bad: list[str] | None = None,
            changed: list[str] | None = None) -> Card:
    """🔴 카드 하나로 모은다 — 렌더러가 보는 것은 **이 타입 하나**다(§3)."""
    return Card(
        board_extra=[str(x) for x in (board_extra or [])],
        board_bad=[str(x) for x in (board_bad or [])],
        changed=[str(x) for x in (changed or [])],
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

def _same_vars(before: list[Variable], now: list[Variable]) -> bool:
    """🔴 변수 목록이 **그대로인가** — 번호·유형·주체·방향·대상·근거 여부로 센다.

    ⚠️ `claim` 글자는 보지 않는다 — 같은 사실을 다른 문장으로 적는 것은 **같은 변수**다
       (그 흔들림이 재분석마다 등급을 바꾸는 것이 ④가 막으려는 것이다).
    🔴 무게(`weight`)와 `hardness` 는 **본다** — 그것이 바뀌면 생존 수가 바뀐다.
    """
    def key(v: Variable) -> tuple:
        return (v.id, v.type, v.subject, v.favors, v.goals, v.target,
                v.hardness, round(float(v.weight), 4), v.usable_as_basis)

    return sorted(key(v) for v in before) == sorted(key(v) for v in now)
