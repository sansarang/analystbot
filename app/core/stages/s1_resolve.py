"""🔴🔴 **v6 s1 — 경기 확정.** `Question → MatchRef | Ambiguous`(§5).

지시서 §5 s1: *"기존 이름표·열쇠 사다리·오픈월드 ⑥단·`window.inside` 를
`adapt.py` 로 감싸 `MatchRef` 를 만든다. 확정 기준(두 팀 일치·36시간 창·정확히
1개)은 그대로."*

⚠️ 후보가 둘 이상이면 `Ambiguous` 를 돌려 **사용자에게 묻는다** — 하나를 골라 주면
   남의 경기를 분석할 수 있고 그 카드는 통째로 거짓이다(§17-g-3 · M14).
"""
from __future__ import annotations

from typing import Any

from app.core import adapt
from app.core.schema import (Ambiguous, DropReason, LlmFail, MatchRef,
                              Question, SpellOut)
from app.core.state import RunState


#: 🔴 철자 후보를 **몇 개까지** 돌려 볼까. ⚠️ 많이 돌리면 검색이 늘어난다.
SPELL_TRIES = 3


async def _spell(name: str, *, state: RunState) -> list[str]:
    """🔴🔴 **⑥-1 철자 후보** — 지시서 §5 s1: `llm.ask(purpose="spell")` 로 바꾼다.

    ⚠️ 실측 2026-10-06: 옛 ⑥-1 이 *"JSON 을 안 냈다"* 로 돌아갔다 — 산문 파싱이
       만든 결함 ②의 전형이다. 🔴 구조화 출력이면 그 길이 없다.
    🔴 **이름표가 모르는 이름**만 여기로 온다(`한국` 은 모르고 `대한민국`·
       `South Korea` 는 안다 — 실측). 그 둘을 모델이 알려 주면 사다리가 다시 돈다.
    ⚠️ 모델이 **경기를 고르지 않는다** — 철자만 낸다(고르는 것은 확정 기준이다).
    """
    from app.core import llm
    said = llm.ask(
        provider="solar", purpose="spell", out=SpellOut, state=state,
        messages=[
            llm.Message(role="system", content=(
                "너는 스포츠 팀·대표팀 이름의 **다른 표기**를 낸다.\n"
                "🔴 같은 팀을 가리키는 **공식 표기·영어 표기·현지 표기**를 "
                "`candidates` 에 넣는다(많아도 5개).\n"
                "⚠️ 다른 팀을 넣지 않는다. 설명·문장을 넣지 않는다 — 이름만.")),
            llm.Message(role="user", content=str(name))])
    if isinstance(said, LlmFail):
        state.note(f"s1 ⑥-1 철자 실패 — {said.reason.value}: {said.detail[:80]}")
        return []
    got = [str(x).strip() for x in said.candidates if str(x).strip()]
    state.note(f"s1 ⑥-1 철자 후보 — {got[:5]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **거른 뒤에 자른다** — 실측 2026-10-06(축구 §6 1회차)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `got[:3]` 으로 **먼저 자르고** 호출부가 이름표로 걸렀다. 그래서
    #     후보가 `['한국', 'Korea', '한국 국가대표팀', '대한민국', …]` 로 오면
    #     **이름표가 아는 `대한민국` 이 잘려 나갔고** 그 경기를 못 찾았다
    #     (같은 경기를 전에는 찾았다 — 모델이 순서를 바꾼 것뿐이다).
    #  🔴 그러니 **이름표가 아는 것만** 남기고 그 다음에 자른다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **후보를 이름표 꼴로 다듬는다** — 같은 꼴의 실패가 **두 번** 났다
    # ══════════════════════════════════════════════════════════════════
    #
    #  실측 2026-10-06(두 회차):
    #    ① `['한국','Korea','한국 국가대표팀','대한민국',…]` → 자르기가 `대한민국` 을 잘랐다
    #    ② `['대한민국 대표팀','한국 대표팀','South Korea national team','KOR','한국']`
    #       → **하나도** 이름표에 없다(이름표는 `대한민국`·`South Korea` 를 안다)
    #
    #  🔴 어느 원칙으로 막혔어야 했나 — **"한 가지 일은 한 곳"**(v6 원칙 3). 이름
    #     해석이 두 곳에서 서로를 모른 채 돈다: 이름표 사다리는 별칭표를 보고, 철자
    #     단계는 모델에게 묻는다. 🔴 그래서 모델이 **이름표에 없는 꼴**(`대한민국
    #     대표팀`)을 내면 그 후보는 쓸 수 없는데 모델은 그것을 알 길이 없다.
    #  ⚠️ 별칭표에 글자를 넣는 것은 §9 의 *"데이터로 우회"* 다 — 하지 않는다.
    #     🔴 대신 **꼬리말을 떼어** 이름표에 다시 묻는다(이름 다듬기는 해석이 아니다).
    from app import teamref
    out: list[str] = []
    for cand in got:
        for said in (cand, *_trimmed(cand)):
            if teamref.key_of(said)[0] and said not in out:
                out.append(said)
                break
    if out:
        state.note(f"s1 ⑥-1 이름표가 아는 꼴로 다듬었다 — {out[:SPELL_TRIES]}")
        return out[:SPELL_TRIES]
    state.note(f"s1 ⑥-1 🔴 후보 {len(got)}개 **전부** 이름표가 모른다 — "
               f"그대로 돌려본다({got[:SPELL_TRIES]})")
    return got[:SPELL_TRIES]


#: 🔴 팀 이름 **꼬리말** — 이름표는 팀 이름만 안다(`대한민국`·`South Korea`).
#  ⚠️ 글자를 **더하지 않는다** — 떼는 것뿐이다(별칭을 짓는 것이 아니다).
_TAILS = ("국가대표팀", "대표팀", "국대", "national team", "national football team",
          "men's national team", "nt", "xi")


def _trimmed(name: str) -> list[str]:
    """🔴 꼬리말을 뗀 꼴들. ⚠️ 뗄 것이 없으면 빈 목록(같은 글자를 또 안 넣는다)."""
    said = " ".join(str(name or "").split())
    out: list[str] = []
    low = said.lower()
    for tail in _TAILS:
        if low.endswith(tail):
            got = said[: len(said) - len(tail)].strip(" ·-")
            if got and got != said:
                out.append(got)
    return out


async def _respell(pool: Any, q: Question, *, state: RunState,
                   net: Any) -> MatchRef | None:
    """🔴 **이름표가 모르는 쪽만** 철자를 바꿔 입구를 다시 돌린다(§5 s1 ⑥-1).

    ⚠️ 확정 기준(두 팀 일치·36시간 창·정확히 1개)은 **그대로다** — 바꾸는 것은
       *"무슨 글자로 물었나"* 뿐이다.
    """
    from app import teamref
    pairs: list[tuple[str, str]] = []
    team, opp = q.team or q.raw, q.opponent or ""
    for side, name in (("team", team), ("opponent", opp)):
        if not name or teamref.key_of(name)[0]:
            continue                       # 🔴 이름표가 **아는** 쪽은 안 바꾼다
        for cand in await _spell(name, state=state):
            if teamref.key_of(cand)[0]:
                pairs.append((side, cand))
    if not pairs:
        return None
    for side, cand in pairs:
        t, o = (cand, opp) if side == "team" else (team, cand)
        state.note(f"s1 ⑥-1 다시 묻는다 — `{t}` vs `{o}`")
        got = await _try(pool, t, o, state=state, net=net, openworld=True)
        if got is not None:
            return got
    return None


async def _try(pool: Any, team: str, opp: str, *, state: RunState, net: Any,
               openworld: bool) -> MatchRef | None:
    """🔴 그 두 글자로 입구를 한 번 돌린다. 못 찾으면 `None`."""
    from app import queries, resolve
    try:
        look = await resolve.match_of(pool, team=team, opponent=opp, net=net)
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s1 재시도가 터졌다 — {exc!r}")
        return None
    for said in (getattr(look, "steps", None) or ()):
        state.note(f"s1(재) {said}")
    if not getattr(look, "ok", False):
        return None
    raw = look.ref
    got = adapt.ref_of(raw, competition_short=queries.competition_short(
        getattr(raw, "competition", "")), openworld=openworld)
    if got is not None:
        state.match_key = got.id
    return got


async def _openworld(pool: Any, q: Question, *, state: RunState,
                     net: Any, board_text: str = "") -> MatchRef | None:
    """🔴 **두 번째 ⑥단 부품** — `findgame` 이 `fotmob …` 질의를 만든다.

    ⚠️ 찾으면 `games` 표에 적고(`find_and_store`) **입구를 다시 돌린다** — 그러면
       이름표·창 검사가 그 행에 대해 **그대로** 돈다(확정 기준은 안 바꾼다 · §5 s1).
    🔴 못 찾으면 `None` — 호출부가 `Ambiguous` 를 낸다.
    """
    from app import findgame, queries, resolve
    try:
        found = await findgame.find_and_store(
            pool, team=q.team or q.raw, opponent=q.opponent or "", net=net,
            # 🔴 §1-1 ① — **보드가 가장 정확한 단서**다(날짜·시각·두 팀·리그)
            board_text=board_text)
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s1 ⑥(findgame) 터졌다 — {exc!r}")
        return None
    state.note(f"s1 ⑥(findgame) — 행 {len(getattr(found, 'ids', None) or [])}개 "
               f"· {getattr(found, 'why', '') or ''}"[:160])
    if not (getattr(found, "ids", None) or []):
        return None
    try:
        again = await resolve.match_of(
            pool, team=q.team or q.raw, opponent=q.opponent or "", net=net)
    except Exception as exc:                                # noqa: BLE001
        state.note(f"s1 ⑥ 뒤 입구가 터졌다 — {exc!r}")
        return None
    for said in (getattr(again, "steps", None) or ()):
        state.note(f"s1(2차) {said}")
    if not getattr(again, "ok", False):
        return None
    raw = again.ref
    got = adapt.ref_of(
        raw, competition_short=queries.competition_short(
            getattr(raw, "competition", "")),
        # 🔴 이 경기는 **⑥단으로 들어왔다** — 상한이 그것을 본다(§7)
        openworld=True)
    if got is not None:
        state.match_key = got.id
    return got


async def run(q: Question, *, pool: Any, state: RunState,
              net: Any = None, board_text: str = "") -> MatchRef | Ambiguous:
    """🔴 질문 → 그 경기 하나. ⚠️ 못 고르면 `Ambiguous`(예외를 안 던진다)."""
    from app import queries, resolve
    try:
        look = await resolve.match_of(
            pool, team=q.team or q.raw, opponent=q.opponent or "",
            net=net)
    except Exception as exc:                                # noqa: BLE001
        state.drop("s1", DropReason.NO_DOC, f"입구가 터졌다: {exc!r}")
        return Ambiguous(why=f"🔴 입구가 터졌다 — {exc!r}")
    for said in (getattr(look, "steps", None) or ()):
        state.note(f"s1 {said}")
    if not getattr(look, "ok", False):
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **질의 만드는 곳이 둘이다** — 실측 2026-10-06
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ `resolve` 의 ⑥-2 는 `South Korea Uzbekistan 축구` 를 던져 **경기
        #     페이지를 0개** 집었다(뉴스·블로그만 왔다). 같은 날 북아일랜드는
        #     `findgame` 쪽이 `fotmob Northern Ireland Georgia` 를 던져 **찾았다**.
        #  🔴 두 곳이 다른 질의를 만든다 — 그것이 ③ 결함(사본)이다.
        #  ⚠️ §9 는 4단계 전까지 **옛 경로 수정**을 금지한다. 그래서 고치지 않고,
        #     **s1 이 두 부품을 다 쓴다**(§5 s1: *"기존 … 오픈월드 ⑥단 … 을 감싸"*).
        #  🔴 5단계에서 **질의 만드는 곳을 하나로** 줄인다(§6 "사본 전부").
        # 🔴 ① **철자부터** — 이름표가 모르는 글자가 원인일 수 있다(실측: `한국`)
        got = await _respell(pool, q, state=state, net=net)
        if got is not None:
            return got
        # 🔴 ② 그래도 없으면 `findgame` 의 ⑥단(`fotmob …` 질의)
        got = await _openworld(pool, q, state=state, net=net, board_text=board_text)
        if got is not None:
            return got
        reason = getattr(getattr(look, "reason", None), "value", "?")
        return Ambiguous(
            why=f"🔴 경기를 확정하지 못했다 — `{reason}`",
            candidates=[f"{r.get('away')} @ {r.get('home')} · {r.get('league')}"
                        for r in (getattr(look, "candidates", None) or ())][:6])
    raw = look.ref
    got = adapt.ref_of(
        raw, competition_short=queries.competition_short(
            getattr(raw, "competition", "")),
        # 🔴 쌓인 표에 없던 경기면 ⑥단을 탔다 — 상한이 그것을 본다(§7)
        openworld=bool(getattr(look, "openworld", False)))
    if got is None:
        return Ambiguous(
            why=("🔴 경기를 찾았는데 **열쇠나 킥오프가 비었다** — 그 값으로는 "
                 "창을 자를 수 없다(절대규칙 2)"))
    state.match_key = got.id
    return got
