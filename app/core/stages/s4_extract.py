"""🔴🔴 **v6 s4 — 변수 추출.** `MatchRef, list[Doc] → list[VarCandidate]`(§5).

지시서 §5 s4:

> 하위마다 `llm.ask(provider="solar", purpose="extract", out=list[VarCandidate])`
> **1회**. 입력은 그 하위의 `Doc` 문단(BM25+재정렬 상위)과 머리표 `[doc_id]`.
> 스키마가 `subject`·`doc_id`·`type` 을 **enum 으로 강제**(§4). 결과 0개이고
> 하위 검색 예산이 남으면, 1차 결과 제목에서 **코드가** 고유명사 2개를 뽑아 좁힌
> 질의로 s3 ①~③ 을 한 번 더 → 추출 1회 더. **그 이상은 없다.**

══════════════════════════════════════════════════════════════════
🔴 이 단계가 **루프를 안 돈다**는 것이 요점이다
══════════════════════════════════════════════════════════════════

⚠️ 실측 2026-10-06: 에이전트 루프(LLM 이 검색어를 정하고 → 검색 → 다시 생각 →
   fetch → … → `done`)는 하위 8개 × 7턴으로 **26.8분**과 `budget_cut` 을 만들었다.
🔴 찾는 일은 **코드가**(s3), 읽고 뽑는 일만 **LLM 이 한 번에**(여기) 한다.
"""
from __future__ import annotations

from typing import Any

from app.core import adapt
from app.core.schema import (Doc, DropReason, LlmFail, MatchRef, SubtaskId,
                             VarCandidate, VarCandidates)
from app.core.state import RunState

#: 🔴 하위 과제 여덟 — 열거값이 원본이다(§3). ⚠️ 여기서 이름을 지어내지 않는다.
SIDS: tuple[str, ...] = tuple(SubtaskId.__args__)      # type: ignore[attr-defined]

#: 🔴 좁히기에 쓸 고유명사 **2개**(지시서 §5 s4). ⚠️ 늘리면 질의가 길어져 0건이다.
NARROW_N = 2


def group_kinds(sid: str) -> list[str]:
    """🔴 그 하위 과제가 **담당하는 유형군 이름**들 — `subtask_groups.yaml` 이 원본.

    ⚠️ 유형 이름을 코드에 적지 않는다(#1 사본 금지) — 표가 자라면 따라가야 한다.
    """
    from app.research import subtasks as _st
    key = str(sid).split("-")[0]
    for row in _st.groups():
        if str(row.get("key")) == key:
            return [str(k) for k in (row.get("kinds") or [])]
    return []


def kinds_of(sid: str, sport: str = "") -> list[str]:
    """🔴 그 하위에 **enum 으로 줄 유형** — 카탈로그 이름 ∩ **그 종목**.

    🔴 옮기는 것은 `adapt.catalog_type` **하나**다(§2: 변환은 한 곳에서만) —
       s3 의 검색 낱말도 같은 함수를 지난다.
    🔴 **종목으로 한 번 더 거른다**(사용자 지시 2026-10-06 ③) — 실측 2026-10-06:
       축구 경기 enum 에 `pitcher_state`(야구)가 있어 피로 기사가 그 유형으로 붙고
       방향이 **자기 쪽**이 됐다. ⚠️ 종목을 안 주면 거르지 않는다(옛 호출부 호환).
    """
    ok = set(rules_types(sport)) if sport else None
    out: list[str] = []
    for kind in group_kinds(sid):
        got = adapt.catalog_type(kind)
        if not got or got in out:
            continue
        if ok is not None and got not in ok:
            continue
        out.append(got)
    return out


def rules_types(sport: str) -> list[str]:
    """🔴 그 종목의 카탈로그 유형 — 표가 원본이다(`rules.types_for_sport`)."""
    from app import rules
    return rules.types_for_sport(sport)


def kinds_dropped(sid: str, sport: str) -> list[str]:
    """🔴 **종목 때문에 빠진 유형** — 사유로 남긴다(#3 조용한 0 금지)."""
    ok = set(rules_types(sport))
    out = []
    for kind in group_kinds(sid):
        got = adapt.catalog_type(kind)
        if got and got not in ok:
            out.append(f"{got}(종목 밖)")
    return out


def unmapped_of(sid: str) -> list[str]:
    """🔴 그 하위에서 **카탈로그로 못 옮긴** 유형군 이름들 — 사유로 남긴다(#3)."""
    return [k for k in group_kinds(sid) if not adapt.catalog_type(k)]


def paragraphs_of(docs: list[Doc], kinds: list[str], *, cap: int = 0,
                  note: Any = None) -> tuple[str, dict[str, str]]:
    """🔴 ④ 문단 묶음 + **머리표 → 문서 id** 표. `(글, 표)`.

    문단마다 `[D1-P3] (도메인, 발행일)` 머리표를 붙인다 — 모델은 `doc_id` 만
    적고(스키마 enum), 어느 문단이었는지는 **인용을 되맞춰** 코드가 찾는다.
    🔴 머리표에 **URL 을 적지 않는다** — 실측 2026-10-06: 모델이 도메인을 `doc_id`
       칸에 적어 전부 폐기됐다(그래서 enum 으로 막았고, 머리표도 id 로 적는다).
    """
    from app import readtext
    from app.core import rank
    from app.core.llm import cfg
    cap = cap or int((((cfg().get("budget") or {}).get("per_subtask") or {})
                      .get("paras_max")) or 18)
    want = " ".join(str(k) for k in (kinds or ()))
    lines: list[str] = []
    where: dict[str, str] = {}
    for d in docs:
        paras = readtext.paragraphs(d.body)
        # 🔴 **녹음·재생을 거친다**(`rank`) — 재생에서 순서가 갈리면 추출 요청이
        #    갈리고 LLM 카세트가 전부 빗나간다(실측 2026-10-06).
        got, said = rank.paragraphs(want, paras)
        if not got:
            got = paras                    # ⚠️ 못 받았으면 **원래 순서**다
            if note is not None:
                note(f"s4 재정렬을 못 받았다({d.id}) — 원래 순서로 간다: "
                     f"{said[:90]}")
        for j, para in enumerate(got[:6], 1):
            if len(lines) >= cap:
                break
            tag = f"[{d.id}-P{j}]"
            when = (f"{d.published_at:%Y-%m-%d}" if d.published_at
                    else "발행일 없음")
            lines.append(f"{tag} ({d.domain}, {when}) {para}")
            where[tag] = d.id
    return "\n".join(lines), where


def _system(sid: str, kinds: list[str], ref: MatchRef) -> str:
    """🔴 추출 규칙 글. ⚠️ **열쇠 목록을 적지 않는다** — 스키마가 강제한다(§6).

    > 프롬프트에 enum 목록 적는 코드(스키마가 강제하므로 불필요) — §6 "지운다"
    """
    return (
        "너는 아래 문단들에서 **그 경기의 변수만** 뽑는다. 웹에 닿을 수 없다.\n"
        f"\n🔴 네 담당은 `{sid}` 의 유형들뿐이다: {', '.join(kinds)}.\n"
        "🔴 `quote` 는 **문단의 글자 그대로**다(한 글자도 바꾸지 않는다) — "
        "검증층이 본문에 대고 맞춰 보고, 없으면 그 줄을 버린다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **머리표를 인용에 넣지 마라** — 실측 2026-10-06
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 후보 16개 중 **11개**가 `quote` 를 `[A-home-D1-P2] (biz.chosun.com,
        #     2026-10-05) 본문…` 으로 적었다. 머리표는 **우리가 붙인 것**이고
        #     기사 본문에 없으니 `quote_not_found` 로 전부 버려졌다(변수 14 → 5).
        #  🔴 그래서 **적지 말라고 적는다** — 어느 문서인지는 `doc_id` 칸이 받는다.
        "🔴 `quote` 에 **머리표를 넣지 마라** — `[A-home-D1-P2] (도메인, 날짜)` 는 "
        "우리가 붙인 표지이고 기사에 없는 글자다. **본문 글자만** 적는다"
        "(어느 문서인지는 `doc_id` 칸이 받는다).\n"
        "🔴 `claim` 은 그 사실을 **한 문장**으로 적은 것이다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`target` = 병합 열쇠** — 사용자 지시 2026-10-06 ①
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-06: 김민재 결장이라는 **한 사실**이 변수 11개로 셌다.
        #     문장이 저마다 달라 문장 유사도로는 묶이지 않는다.
        #  🔴 그래서 **"누가·무엇"** 을 모델이 한 낱말로 적게 하고, 코드가 그
        #     열쇠로 합친다(같은 subject·type·target = 한 사실).
        "🔴 `target` 은 그 사실의 **핵심 대상 하나**다 — 선수 이름(`Kim Min-jae`) "
        "또는 사건 한 낱말(`record`·`travel`). ⚠️ 같은 사실을 여러 기사에서 봤다면 "
        "`target` 을 **같은 글자**로 적어라(그것으로 합친다). 문장을 넣지 마라.\n"
        "⚠️ 문단에 없는 사실은 **쓰지 않는다.** 없으면 `variables` 를 빈 배열로 "
        "둔다 — 빈 것이 지어낸 것보다 낫다.\n"
        f"⚠️ 이 경기는 {ref.home_name}(홈) 대 {ref.away_name}(원정)이다 — "
        "다른 경기 이야기는 뽑지 않는다.\n"
        "🔴 도구는 없다. **한 번에** JSON 으로만 답한다.")


async def run(ref: MatchRef, docs: list[Doc], *, state: RunState,
              chain: Any = None, net: Any = None,
              cache: dict[str, Doc] | None = None) -> list[VarCandidate]:
    """🔴 하위 여덟마다 추출 1회(+조건부 1회). `VarCandidate` 목록."""
    out: list[VarCandidate] = []
    for sid in SIDS:
        mine = [d for d in docs if d.subtask == sid]
        got = _ask(sid, mine, ref, state=state)
        if not got and mine and chain is not None:
            # 🔴 **0개이고 예산이 남으면 좁혀서 한 번 더**(§5 s4) — 그 이상은 없다
            more = await _narrow(sid, ref, mine, state=state, chain=chain,
                                 net=net, cache=cache)
            if more:
                got = _ask(sid, more, ref, state=state, second=True)
                docs += more
        out += got
    state.set("candidates", len(out))
    return out


def _ask(sid: str, mine: list[Doc], ref: MatchRef, *, state: RunState,
         second: bool = False) -> list[VarCandidate]:
    """🔴 그 하위 추출 **한 번**. ⚠️ 실패해도 예외를 위로 던지지 않는다(§5)."""
    from app.core import llm
    tag = f"s4/{sid}" + ("(2차)" if second else "")
    kinds = kinds_of(sid, ref.sport)
    gone = unmapped_of(sid) + kinds_dropped(sid, ref.sport)
    if gone:
        # 🔴 **조용히 빠뜨리지 않는다** — 이 이름들은 카탈로그에 없어서 enum 에
        #    들어가지 못했다. ⚠️ 그래서 그 각도는 **이 경기에서 안 뽑힌다.**
        state.note(f"{tag} enum 에서 빠진 유형 {gone} — 카탈로그에 없거나 **그 종목이 "
                   f"아니다**(그 각도의 변수는 뽑히지 않는다)")
    if not mine:
        state.note(f"{tag} 문서 0건 — 추출을 돌리지 않았다")
        return []
    if not kinds:
        state.drop(tag, DropReason.TYPE_OFF_CATALOG,
                   f"`{sid}` 담당 유형을 표에서 못 찾았다")
        return []
    block, _where = paragraphs_of(mine, kinds, note=state.note)
    if not block.strip():
        state.drop(tag, DropReason.BODY_MISSING,
                   f"문서 {len(mine)}건에서 문단을 못 뽑았다")
        return []
    said = llm.ask(
        provider="solar", purpose="extract", out=VarCandidates, state=state,
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **그 요청만의 열거값** — §4 가 말하는 구조적 차단
        # ══════════════════════════════════════════════════════════════
        #
        #  `subject` 는 그 경기 **두 열쇠만**, `doc_id` 는 **그 하위에 넘긴 id
        #  만**, `type` 은 **그 하위 담당 유형만**, `subtask` 는 **그 하위만**.
        #  ⚠️ 실측 2026-10-06 의 폐기 사유 셋(`name_not_key`·머리표 아님·카탈로그
        #     밖 유형)이 전부 **낼 길이 없어진다.**
        enums={"subject": [ref.home, ref.away],
               "doc_id": [d.id for d in mine],
               "type": kinds, "subtask": [sid]},
        messages=[llm.Message(role="system",
                              content=_system(sid, kinds, ref)),
                  llm.Message(role="user", content=block)])
    if isinstance(said, LlmFail):
        state.drop(tag, said.reason, said.detail[:120])
        return []
    got = list(said.variables)
    state.note(f"{tag} 문서 {len(mine)}건 → 후보 {len(got)}개")
    return got


async def _narrow(sid: str, ref: MatchRef, mine: list[Doc], *,
                  state: RunState, chain: Any, net: Any,
                  cache: dict[str, Doc] | None) -> list[Doc]:
    """🔴 ⑥ 좁히기 1회 — **1차 결과 제목에서 코드가** 고유명사를 뽑는다(§5 s4).

    🔴 낱말을 **지어내지 않는다**(#4) — 받은 제목에 있는 것만 쓴다.
    """
    from app.core.stages import s3_docs
    from app.research import subtasks as _st
    words = _st.narrow_words([{"title": d.title} for d in mine])[:NARROW_N]
    if not words:
        state.note(f"s4/{sid} 좁힐 고유명사가 제목에 없다 — 2차를 돌리지 않았다")
        return []
    state.note(f"s4/{sid} 후보 0개 → 좁히기 낱말 {words}")
    return await s3_docs.regather(ref, sid, words, state=state, chain=chain,
                                  net=net, cache=cache, start=len(mine))
