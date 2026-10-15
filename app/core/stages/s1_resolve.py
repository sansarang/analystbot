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


def picks_of(rows: list[dict]) -> list[dict]:
    """🔴🔴 §1-3 — `games` 행들 → **버튼으로 고를 후보**.

    > 후보 2개 이상 → 텔레그램 버튼으로 고르게 한다(**리그·날짜·시각을 붙여서**).

    🔴 `key` 는 `games.ext_id` 다 — 사용자가 누르면 그 열쇠로 **못 박는다**
       (`run(pick_key=…)`). ⚠️ 다시 찾으면 또 여럿이 나와 같은 자리에서 멈춘다.
    ⚠️ 열쇠가 없는 행은 **버튼으로 내지 않는다** — 누르면 못 찾는 버튼이다.
    """
    from app import timefmt
    out: list[dict] = []
    for r in (rows or []):
        key = str(dict(r).get("ext_id") or "").strip()
        if not key:
            continue
        when = dict(r).get("starts_kst") or dict(r).get("starts_utc")
        said = ""
        if when is not None:
            try:
                said = timefmt.kst_label(timefmt.aware(when, where="후보"))
            except (TypeError, ValueError):
                said = ""
        out.append({"key": key,
                    "home": str(dict(r).get("home") or ""),
                    "away": str(dict(r).get("away") or ""),
                    "league": str(dict(r).get("league") or ""),
                    "kst": said})
    return out


async def _by_key(pool: Any, key: str, *, state: RunState
                  ) -> MatchRef | None:
    """🔴🔴 §1-3 — **버튼으로 고른 경기 하나**를 표에서 집는다. 없으면 `None`.

    🔴 표를 읽는 SQL 은 `app/slate.py` 의 `by_key` 하나다(사본 금지) — 여기서
       질의를 다시 쓰지 않는다.
    ⚠️ 확정 기준(창·이름표)은 **적용하지 않는다** — 사용자가 **그 경기를 골랐다**.
       🔴 그 대신 *"이미 시작했나"* 는 뒤 단계가 그대로 센다(등급이 거둬진다).
    """
    from app import queries, slate
    got = await slate.by_key(pool, key)
    rows = list(getattr(got, "games", None) or [])
    if not rows:
        state.note(f"s1 고른 경기 — 🔴 `{key}` 가 표에 없다")
        return None
    from app import matchref
    raw = matchref.ref_from_row(rows[0])
    ref = adapt.ref_of(raw, competition_short=queries.competition_short(
        getattr(raw, "competition", "")), openworld=True)
    if ref is None:
        state.note(f"s1 고른 경기 — 🔴 `{key}` 행으로 ref 를 못 만들었다")
        return None
    state.match_key = ref.id
    state.note(f"s1 **사용자가 고른 경기** — `{key}` · {ref.home_name} vs "
               f"{ref.away_name} · {ref.competition}")
    return ref


async def _spell_hints(q: Question, *, state: RunState) -> dict:
    """🔴 §1-1 ② — **이름표가 모르는 쪽의 철자 후보**(`{물은 이름: [후보…]}`).

    🔴 철자는 `_spell`(로컬 LLM · `purpose="spell"`)이 낸다 — ⚠️ 모델이 경기를
       **고르지 않는다**(철자만 낸다 · 절대규칙 5).
    ⚠️ 이름표가 **아는** 이름은 묻지 않는다(통신·시간 낭비).
    """
    from app import teamref
    out: dict[str, list[str]] = {}
    for name in (q.team or q.raw, q.opponent or ""):
        said = str(name or "").strip()
        if not said or teamref.key_of(said)[0]:
            continue
        got = await _spell(said, state=state)
        if got:
            out[said] = got
    if out:
        state.note(f"s1 ⑥-1 철자 후보(색인용) — {out}")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **확정한 경기가 물어본 그 경기인가** — 사용자 지적 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-15(MLS 11:30): `"Los Angeles FC Austin FC"` 도,
#     `"LA Galaxy Portland Timbers"` 도 **`Avenir de La Marsa vs Etoile
#     Métlaoui`**(튀니지 Ligue I)로 확정됐다. 그 경기는 `games` 표에서 **가장
#     최근에 적힌 행**이었고, 물어본 세 경기는 표에 **없었다**.
#     🔴 즉 입구가 *"못 찾았다"* 대신 **남의 경기**를 `ok` 로 돌려줬고, 봇은
#        그것으로 16단계를 다 돌렸다(돈과 시간을 썼다).
#  🔴 그래서 **이름 대 이름**으로 검문한다 — 한쪽도 안 맞으면 쓰지 않는다.
#     문은 `verify.same_team` 하나다(사본 금지 · 2026-10-15 에 그 문을 하나로
#     합쳤다). ⚠️ 느슨하지 않다 — 짧은 이름(`Como`)과 긴 이름(`Como 1907`)은
#     통과하고 남의 팀은 거부한다(그 함수의 계약이 센다).


def asked_match(asked: object, ref: object) -> tuple[bool, str]:
    """🔴 물어본 이름이 그 경기의 **어느 쪽에라도** 있나. `(맞나, 사유)`.

    `asked` 는 `Question` 이거나 **이름 목록**이다(퇴로는 이름만 들고 있다).
    🔴 묻는 이름이 **하나도 없으면** 검문하지 않는다 — 그때는 고를 근거가
       질문에 없다(슬레이트·보드가 고른 것이다).
    """
    from app import verify
    raw = (list(asked) if isinstance(asked, (list, tuple))
           else [getattr(asked, "team", ""), getattr(asked, "opponent", "")])
    said = [str(x or "").strip() for x in raw if str(x or "").strip()]
    if not said:
        return True, ""
    sides = [x for x in (str(getattr(ref, k, "") or "")
                         for k in ("home_name", "away_name", "home", "away"))
             if x]
    for one in said:
        if any(verify.same_team(one, side) for side in sides):
            return True, ""
    return False, (f"🔴 **물어본 팀이 그 경기에 없다** — 물음 "
                   f"{' · '.join(said)} ↔ 확정 {' vs '.join(sides[:2])}")


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
        # 🔴🔴 **이름 검문**(`asked_match` 머리말) — 검색·철자 퇴로가 데려온
        #    경기가 더 위험하다. 안 맞으면 **안 쓴다**.
        ok_name, said_name = asked_match([team, opp], got)
        if not ok_name:
            state.note(f"s1(퇴로) {said_name}")
            return None
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **철자 후보를 색인 쪽으로도 넘긴다**(§1-1 ② · 2026-10-10 재작성)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `_respell` 은 **이름표가 아는 철자만** 받는다(그 경로의 규율이다).
    #     🔴 그런데 fotmob 팀 색인은 **이름표와 무관한 출처**다 — 이름표가 모르는
    #        외국 구단의 한글 음차(`우니온`)도 그 색인에서는 풀린다.
    #     실측 2026-10-10: 그 가림 때문에 `우니온 vs 데펜사` 가 끝까지 안 풀렸다.
    said = await _spell_hints(q, state=state)
    try:
        found = await findgame.find_and_store(
            pool, team=q.team or q.raw, opponent=q.opponent or "", net=net,
            # 🔴 §1-1 ① — **보드가 가장 정확한 단서**다(날짜·시각·두 팀·리그)
            board_text=board_text, spell=said)
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
        # 🔴🔴 **이름 검문**(`asked_match` 머리말) — 검색·철자 퇴로가 데려온
        #    경기가 더 위험하다. 안 맞으면 **안 쓴다**.
        ok_name, said_name = asked_match(q, got)
        if not ok_name:
            state.note(f"s1(퇴로) {said_name}")
            return None
        state.match_key = got.id
    return got


async def run(q: Question, *, pool: Any, state: RunState,
              net: Any = None, board_text: str = "",
              pick_key: str = "") -> MatchRef | Ambiguous:
    """🔴 질문 → 그 경기 하나. ⚠️ 못 고르면 `Ambiguous`(예외를 안 던진다).

    🔴🔴 **`pick_key` 는 사용자가 버튼으로 고른 경기**다(§1-3 · 2026-10-10
       재작성). 그것이 오면 **찾지 않는다** — 표에서 그 행 하나를 집는다.
       ⚠️ 다시 찾으면 또 여럿이 나와 같은 자리에서 멈춘다.
    """
    from app import queries, resolve
    if str(pick_key or "").strip():
        got = await _by_key(pool, str(pick_key).strip(), state=state)
        if got is not None:
            return got
        return Ambiguous(
            why=f"🔴 고른 경기를 표에서 못 찾았다 — `{pick_key}`",
            candidates=[])
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
        rows = list(getattr(look, "candidates", None) or ())[:6]
        return Ambiguous(
            why=f"🔴 경기를 확정하지 못했다 — `{reason}`",
            candidates=[f"{r.get('away')} @ {r.get('home')} · {r.get('league')}"
                        for r in rows],
            # 🔴 §1-3 — **버튼으로 고르게 한다**(리그·날짜·시각을 붙여서)
            picks=picks_of(rows))
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
    # 🔴🔴 **이름 검문**(`asked_match` 머리말) — 남의 경기를 분석하지 않는다
    ok_name, said_name = asked_match(q, got)
    if not ok_name:
        state.note(f"s1 {said_name}")
        rows = list(getattr(look, "candidates", None) or ())[:6]
        return Ambiguous(
            why=said_name,
            candidates=[f"{r.get('away')} @ {r.get('home')} · {r.get('league')}"
                        for r in rows],
            picks=picks_of(rows))
    state.match_key = got.id
    return got
