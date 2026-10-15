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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **대회 일정 퇴로 — LLM 없이 찾는다**(사용자 지시 2026-10-15)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-15(MLS 11:30): `LA Galaxy`·`Los Angeles FC` 경기가 `games`
#     표에 **없었고** ⑥단(`findgame`)도 못 찾았다. 까닭은 그 길이 **LLM 으로
#     이름을 푸는데**(`_by_llm_names`) 공급자가 둘 다 죽어 있었기 때문이다
#     (`LLM_TIMEOUT` 7건). 🔴 그런데 같은 경기들이 `tools/slate_queue.py` 에는
#     **다 보였다** — 그것은 **대회 일정**(fotmob `league_matches`)을 읽는다.
#  🔴 그래서 마지막 퇴로로 그 일정을 읽는다 — **망 한 번 · LLM 0건**.
#     ⚠️ 적는 SQL 은 `collect.ingest._UPSERT_GAME` 하나다(사본 금지 ·
#        `findgame.find_and_store` 와 같은 길).
#     🔴 이름 맞추기는 `verify.same_team` 하나다 — 그 문이 남의 팀을 거부한다.

#: 🔴 일정에서 볼 **창** — 뒤로 3시간(도는 경기) · 앞으로 36시간
SCHED_BACK_H = 3.0
SCHED_AHEAD_H = 36.0


async def _by_schedule(pool: Any, q: Question, *, state: RunState,
                       net: Any) -> MatchRef | None:
    """🔴 대회 일정에서 그 경기를 찾아 `games` 에 적고 입구를 다시 돌린다."""
    from datetime import datetime, timedelta, timezone

    from app import verify
    from app.collect import fotmob as fm
    from app.collect.ingest import _UPSERT_GAME
    from app.core import competition as comp

    said = [str(x or "").strip()
            for x in (getattr(q, "team", ""), getattr(q, "opponent", ""))
            if str(x or "").strip()]
    if not said:
        return None
    now = datetime.now(timezone.utc)
    lo, hi = (now - timedelta(hours=SCHED_BACK_H),
              now + timedelta(hours=SCHED_AHEAD_H))
    for key, row in comp.rows().items():
        ids = [str(x) for x in
               ((row.get("sources") or {}).get("fotmob_ids") or [])]
        if not ids:
            continue
        try:
            rows = await fm.league_matches(net, ids[0])
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s1 일정 퇴로 — `{key}` 를 못 읽었다: {exc!r}")
            continue
        for m in rows:
            got_utc = str(m.get("utc") or "")
            if not got_utc:
                continue
            try:
                when = datetime.fromisoformat(got_utc.replace("Z", "+00:00"))
            except ValueError:
                continue
            # 🔴 **tz 를 확인한다**(절대규칙 2 · 계약 `test_time_contract`) —
            #    naive 가 새면 창 비교가 거짓이 된다
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if not (lo <= when <= hi):
                continue
            sides = [str(m.get("home") or ""), str(m.get("away") or "")]
            # 🔴 물어본 이름이 **그 경기 양쪽에** 있어야 한다(한 팀만 물었으면 한쪽)
            hit = all(any(verify.same_team(one, x) for x in sides)
                      for one in said)
            if not hit:
                continue
            names = [str(x) for x in (list(row.get("names") or [])
                                      + list((row.get("sources") or {})
                                             .get("fotmob_names") or []))]
            lg = max(names, key=len) if names else key
            if lg.islower():
                lg = lg.title()
            state.note(f"s1 일정 퇴로 — `{key}` 에서 찾았다: "
                       f"{sides[0]} vs {sides[1]} · {got_utc}")
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **열쇠에 접두를 붙인다** — 사용자 지시 2026-10-15
            # ══════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-15(BG Pathum vs Adelaide): 이 자리가 날숫자
            #     `6054753` 을 적었다. 그런데 fotmob 어댑터는 **접두를 요구**한다
            #     (`fotmob.sources_context` — *"안 요구하면 MLB 숫자 ext_id 도
            #     통과해"*). 그래서 ② 가 **받을 주소가 0건**이 되어
            #     `XI 0/2 · 감독 0/2` 가 났다 — 라인업이 발표돼 있어도 같았다.
            #     ⚠️ 게다가 `fotmob:6054753` 행이 따로 있어 **같은 경기가 두 행**
            #     이 됐다(`ON CONFLICT (sport, ext_id)` 가 다른 열쇠로 본다).
            #  🔴 열쇠를 만드는 곳은 `matchkey.make` 하나다(사본 금지 —
            #     `fotmob.slate_row` 도 그것을 쓴다).
            from app import matchkey
            ext = matchkey.make("fotmob", str(m.get("id") or ""))
            await pool.fetchval(
                _UPSERT_GAME, "soccer", lg, ext,
                sides[0], sides[1], None, when, when + timedelta(hours=9),
                None, ("finished" if m.get("finished") else "scheduled"),
                None, None, None)
            # 🔴🔴 **입구를 다시 믿지 않는다** — ⚠️ 실측 2026-10-15: 행을
            #    적은 **뒤에도** `resolve.match_of` 가 또 그 튀니지 경기를
            #    골랐다(02:24:44 에 `LA Galaxy vs Portland Timbers` 를 적었는데도).
            #    🔴 그래서 **방금 적은 그 행**을 열쇠(`ext_id`)로 바로 집는다 —
            #       `_by_key` 가 그 길이다(표를 읽는 SQL 은 `slate.by_key` 하나).
            out = await _by_key(pool, ext, state=state)
            if out is None:
                state.note("s1 일정 퇴로 — 적었는데 열쇠로 못 집었다")
                return None
            ok_name, why = asked_match(q, out)
            if not ok_name:
                state.note(f"s1 일정 퇴로 {why}")
                return None
            state.match_key = out.id
            return out
    state.note("s1 일정 퇴로 — 선언된 대회 일정에 그 경기가 없다")
    return None


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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **solar 경기 찾기 퇴로** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 봇에 **경기 검색 solar api** 를 추가해라
#
#  ⚠️ 실사고 2026-10-15(남아공 `Hope FC` 22:30): 퇴로 셋이 **전부** 못 찾았다 —
#     ① 철자(이름표가 그 팀을 모른다) ② ⑥단 findgame(fotmob 색인에 **없다**)
#     ③ 대회 일정(남아공 리그가 **대회 표에 없다**). 그래서 ① 단계에서
#     `openworld_not_found` 로 멈췄고, **상대 팀 이름을 모르는 것**이 벽이었다.
#  🔴 그래서 네 번째 퇴로: **solar 가 상대 팀 이름을 읽어 온다.**
#
#  🔴🔴 **규율 — 사실은 문서에서만 온다**(절대규칙 5 · CLAUDE.md #4)
#    ① 모델에게 *"무슨 경기가 있나"* 를 **기억으로 묻지 않는다** — 검색으로 받은
#       **본문을 주고** 그 안에서 두 팀 이름을 **고르게** 한다.
#    ② 모델이 낸 이름과 인용이 **받은 본문에 글자로 없으면 버린다**(지어낸 것).
#    ③ 이름이 서면 **기존 길로 되돌아간다**(⑥단 findgame → 입구) — 확정 기준
#       (`verify.same_team`·`asked_match`·창 검사)은 **그대로** 돈다.
#    ④ 공급자 순서는 `llm.ORDER`(solar → deepseek) 하나다(사본 금지).
#
#  ⚠️ **`findgame._by_llm_names` 와 무엇이 다른가**(사본 금지 조항):
#     · 그쪽은 LLM 이 **같은 팀의 다른 철자·슬러그**를 내고 **fotmob 팀 색인**
#       에서 확인한다 — 🔴 색인에 **없는 팀은 구조적으로 못 찾는다**(Hope FC).
#     · 이쪽은 LLM 이 **모르는 상대 팀 이름**을 **기사 본문**에서 읽는다 —
#       색인 밖 팀도 이름이 서고, 그 뒤 **⑥단 findgame** 으로 되돌아간다.
#     🔴 둘은 **입력이 다르다**(색인 ↔ 본문). 같은 일을 두 번 하지 않는다.

#: 🔴 solar 에게 줄 **문서 수 상한**
LLM_FIND_DOCS = 3
#: 🔴 던질 질의 — 문지기 규칙(낱말 1~6 · 연산자 금지)에 맞춘다
LLM_FIND_Q = ("{t} next match opponent", "{t} fixtures today")
#: 🔴 본문이 이보다 짧으면 안 읽는다(껍데기 · `fetch.shell_like` 와 같은 결)
LLM_FIND_MIN = 400


def _find_schema():
    """🔴 solar 출력 — **이름 둘과 원문 인용**뿐이다(수·확률 없다)."""
    from pydantic import BaseModel, Field

    class Out(BaseModel):
        home: str = Field(default="", description="홈 팀 이름(글에 적힌 그대로)")
        away: str = Field(default="", description="원정 팀 이름(글에 적힌 그대로)")
        quote: str = Field(default="", description="그 경기를 말한 원문 한 문장")

    return Out


async def _by_llm(pool: Any, q: Question, *, state: RunState,
                  net: Any) -> MatchRef | None:
    """🔴🔴 네 번째 퇴로 — **solar 가 문서에서 상대 팀을 읽는다**(위 머리말)."""
    from app import search as _search
    from app import verify
    from app.core import llm
    from app.core.search import fetch as _ft

    team = (str(getattr(q, "team", "") or "").strip()
            or str(getattr(q, "raw", "") or "").strip())
    if not team:
        return None
    chain = _search.build_chain()
    docs: list[tuple[str, str]] = []
    for one in LLM_FIND_Q:
        said_q = one.format(t=team)
        try:
            hits = await chain.query(said_q, lang="en")
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s1 solar 찾기 — 검색 실패 `{said_q}`: {exc!r}")
            continue
        state.note(f"s1 solar 찾기 — `{said_q}` → {len(hits)}건")
        for h in list(hits)[:4]:
            url = str(getattr(h, "url", "") or "")
            if not url or any(url == u for u, _ in docs):
                continue
            try:
                body, _when, _rungs = await _ft.body_of(net, url)
            except Exception:                               # noqa: BLE001
                continue
            if len(str(body or "")) < LLM_FIND_MIN:
                continue
            docs.append((url, str(body)[:4000]))
            if len(docs) >= LLM_FIND_DOCS:
                break
        if len(docs) >= LLM_FIND_DOCS:
            break
    if not docs:
        state.note("s1 solar 찾기 — 🔴 본문을 하나도 못 받았다(읽을 글이 없다)")
        return None

    Out = _find_schema()
    said_body = "\n\n".join(f"[{i + 1}] {u}\n{b[:1800]}"
                              for i, (u, b) in enumerate(docs))
    msgs = [
        llm.Message(role="system", content=(
            "너는 **글에 적힌 것만 고르는 사람**이다. 네 기억으로 경기를 "
            "말하지 말고, 아래 글에서 **그 팀의 다음 경기**를 찾는다. "
            "글에 없으면 빈 글자로 둔다.")),
        llm.Message(role="user", content=(
            f"찾는 팀: **{team}**\n\n{said_body}\n\n"
            "🔴 위 글에서 이 팀의 **다음 경기 두 팀 이름**을 고른다.\n"
            "  · `home` — 홈 팀 이름(글에 적힌 **그대로**)\n"
            "  · `away` — 원정 팀 이름(글에 적힌 **그대로**)\n"
            "  · `quote` — 그 경기를 말한 **원문 한 문장**(글자 그대로)\n"
            "⚠️ 글에 그 경기가 없으면 **셋 다 비워라** — 지어내면 버려진다"
            "(코드가 본문과 대조한다).")),
    ]
    got, said_pv = llm.ask_first(purpose="recall", messages=msgs, out=Out,
                                 state=state)
    state.note(f"s1 solar 찾기 — 공급자 {said_pv}")
    if not isinstance(got, Out):
        return None
    home = str(getattr(got, "home", "") or "").strip()
    away = str(getattr(got, "away", "") or "").strip()
    quote = str(getattr(got, "quote", "") or "").strip()
    said_all = "\n".join(b for _u, b in docs).lower()

    def _grounded(said: str) -> bool:
        return bool(said) and said.lower() in said_all

    if not (home and away):
        state.note("s1 solar 찾기 — ⬜ 모델이 두 팀을 못 골랐다(글에 없다)")
        return None
    bad = [x for x in (home, away) if not _grounded(x)]
    if bad or not _grounded(quote[:40]):
        # 🔴 **지어낸 것이다** — 본문에 그 글자가 없다(위 규율 ②)
        state.note(f"s1 solar 찾기 — 🔴 **본문에 없는 글자**를 냈다 "
                   f"{bad or [quote[:30]]} → 버린다")
        return None
    # 🔴 **물어본 팀이 그 경기 한쪽이어야 한다**(남의 경기 금지 · same_team 하나)
    if not any(verify.same_team(team, x) for x in (home, away)):
        state.note(f"s1 solar 찾기 — 🔴 물어본 `{team}` 이 "
                   f"`{home} vs {away}` 에 없다 → 버린다")
        return None
    state.note(f"s1 solar 찾기 — ✅ `{home} vs {away}` · 인용 `{quote[:60]}`")
    # 🔴 이름이 서면 **기존 길로 되돌아간다**(위 규율 ③)
    q2 = q.model_copy(update={"team": home, "opponent": away})
    got_ref = await _openworld(pool, q2, state=state, net=net)
    if got_ref is not None:
        return got_ref
    return await _try(pool, home, away, state=state, net=net, openworld=True)


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **입구가 고른 것도 이름 검문을 먼저 지난다**(지시 2026-10-15)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-15(두 번째): 검문을 **퇴로 뒤**에 뒀더니, 입구가 `ok` 로
    #     남의 경기를 주면 퇴로 블록에 **아예 안 들어갔다** — 거절만 하고 끝나
    #     `LA Galaxy` 는 끝까지 못 찾았다.
    #  🔴 그래서 **여기서** 검문한다 — 안 맞으면 `ok` 를 내리고 퇴로로 흘린다.
    said_bad = ""
    # 🔴 `Lookup.ok` 는 **읽기 전용 속성**이다(실측 2026-10-15: 대입이 터졌다)
    #    — 그래서 여기 지역 깃발로 든다.
    ok_entry = bool(getattr(look, "ok", False))
    if ok_entry:
        try_ref = adapt.ref_of(
            look.ref, competition_short=queries.competition_short(
                getattr(look.ref, "competition", "")),
            openworld=bool(getattr(look, "openworld", False)))
        if try_ref is not None:
            ok_name, said_bad = asked_match(q, try_ref)
            if not ok_name:
                state.note(f"s1 {said_bad} — **퇴로로 간다**")
                ok_entry = False
    if not ok_entry:
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **① solar 경기 찾기가 맨 앞이다** — 사용자 지시 2026-10-15
        # ══════════════════════════════════════════════════════════════
        #
        #  > solar 로 그냥 넣어라 **맨 처음으로**
        #
        #  ⚠️ 종전 순서는 철자 → ⑥단 → 일정 → solar(맨 뒤)였다. 그런데 실측
        #     2026-10-15(`Hope FC`): 앞 셋이 **전부** 못 찾는 경기에서 앞 셋을
        #     다 기다리는 데만 시간이 갔다(⑥단 findgame 이 가장 느리다).
        #  🔴 그래서 **solar 를 먼저** 돈다 — 그래도 확정 기준은 그대로다:
        #     모델이 낸 이름은 **본문 대조**를 지나야 하고, 선 이름은 **기존
        #     길**(⑥단 → 입구 → `same_team`·창 검사)로 되돌아가 확인된다.
        got = await _by_llm(pool, q, state=state, net=net)
        if got is not None:
            return got
        # 🔴 ② **철자** — 이름표가 모르는 글자가 원인일 수 있다(실측: `한국`)
        got = await _respell(pool, q, state=state, net=net)
        if got is not None:
            return got
        # 🔴 ③ 그래도 없으면 `findgame` 의 ⑥단(`fotmob …` 질의)
        got = await _openworld(pool, q, state=state, net=net, board_text=board_text)
        if got is not None:
            return got
        # 🔴🔴 ④ **대회 일정 퇴로**(위 머리말) — LLM 이 죽어도 도는 길이다
        got = await _by_schedule(pool, q, state=state, net=net)
        if got is not None:
            return got
        reason = getattr(getattr(look, "reason", None), "value", "?")
        rows = list(getattr(look, "candidates", None) or ())[:6]
        return Ambiguous(
            why=(said_bad + " · 퇴로 셋도 못 찾았다" if said_bad
                 else f"🔴 경기를 확정하지 못했다 — `{reason}`(퇴로 넷 다)"),
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
