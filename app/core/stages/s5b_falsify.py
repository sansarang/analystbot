"""🔴🔴 **⑫b 반증 딥서치** — 수정 지시서 2026-10-12 [3b].

> 하는 일: 조건마다 반증 질의를 ③ 딥서치와 **같은 검색·신원·날짜 문을 그대로**
> 써서 돌린다(**새 검색기 만들지 않는다**).
>   질의: 팀·선수 현지어+영어 별칭(신원표) × 종류별 단어(결장·부상·로테이션·복귀·선발).
>   구조 사실로 확인 가능한 것(K2·K3·K4)은 **질의 없이** 기존 사실로 판정.
> 결과: 각 조건 상태 = 확인-무너짐 / 확인-무너짐 없음 / 미확인 · 출처·시각·강도.

🔴 이 단계는 **확률을 만지지 않는다**(B3) — 확률 모듈을 import 하지 않는다.
   등급만 바꾼다(C2 · [3d]). 라인업·결장 사실이면 ④로 되돌린다([3c]).
⚠️ **재생(카세트)에서는 검색하지 않는다** — 녹음이 그 질의를 모른다. 그때는
   구조 사실 판정만 하고 나머지는 `미확인`으로 남긴다(#3 조용한 0 금지).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.schema import BreakCondition, Facts, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 세 상태 — **글자가 계약이다**(카드·등급 판정이 이 글자를 본다)
BROKEN = "확인-무너짐"
INTACT = "확인-무너짐 없음"
UNKNOWN = "미확인"

#: 🔴🔴 **질의 없이** 기존 사실로 판정하는 종류(지시서 [3b])
#
#  ⚠️ K5(우선순위 지수)도 여기다 — 그 수는 ⑦ 이 이미 셌고 검색할 것이 없다.
NO_QUERY_KINDS: tuple[str, ...] = ("K2", "K3", "K4", "K5")

#: 🔴 종류별 **반증 낱말** — 질의에 붙는다. ⚠️ 낱말 목록의 원본은
#   `config/search_words.yaml` 이고, 여기 적은 것은 *그 열쇠 이름*이다(#1).
QUERY_WORDS: dict[str, tuple[str, ...]] = {
    "K1": ("absence", "lineup_rotation"),
    "K6": ("returning",),
}

#: 🔴 조건 하나에 던지는 질의 상한 — 반증이 본 단계보다 커지면 안 된다
PER_COND = 2
#: 🔴 이 단계 전체 검색 상한
SEARCH_CAP = 6


def by_structure(rows: list, *, xi_state: str = "",
                 h2h_against: bool | None = None,
                 priority_low: bool | None = None) -> list:
    """🔴🔴 **구조 사실로 판정한다**(통신 0회) — K2·K3·K4·K5.

    🔴 판정 재료는 **이미 센 것**뿐이다:
      · K2 — 조건을 만들 때 `꺼진 무기`가 적혀 있었다 → 그 자체가 무너짐이다
      · K4 — `xi_state` 가 `confirmed` 가 아니면 무너짐(판정이 흔들린다)
      · K3 — 맞대결이 반대 방향인가(`h2h_against`) · 모르면 `미확인`
      · K5 — 우선순위 지수가 문턱 아래인가 · 모르면 `미확인`
    ⚠️ 모르는 칸을 `무너짐 없음`으로 적지 않는다 — 그것이 조용한 0 이다(#3).
    """
    out: list = []
    for one in (rows or []):
        kind = str(getattr(one, "kind", "") or "")
        if kind not in NO_QUERY_KINDS:
            out.append(one)
            continue
        state, said, strength = UNKNOWN, "", ""
        if kind == "K4":
            if xi_state:
                broke = str(xi_state) != "confirmed"
                state = BROKEN if broke else INTACT
                said = f"라인업 상태 `{xi_state}`"
                # 🔴 확정이 아닌 것은 **hard** 다 — 명단이 바뀌면 판정이 바뀐다
                strength = "hard" if broke else ""
        elif kind == "K2":
            # 🔴 조건이 선 까닭 자체가 "꺼진 무기가 있다"다(⑧ 이 셌다)
            state = BROKEN
            said = str(getattr(one, "said", "") or "")
            strength = "soft"
        elif kind == "K3":
            if h2h_against is not None:
                state = BROKEN if h2h_against else INTACT
                said = ("맞대결이 반대 방향이다" if h2h_against
                        else "맞대결이 같은 방향이다")
                strength = "soft" if h2h_against else ""
        elif kind == "K5":
            if priority_low is not None:
                state = BROKEN if priority_low else INTACT
                said = str(getattr(one, "said", "") or "")
                strength = "soft" if priority_low else ""
        out.append(one.model_copy(update={
            "state": state, "strength": strength,
            "source": "구조 사실",
            "said": (f"{getattr(one, 'said', '')}"
                     + (f" → {said}" if said else ""))}))
    return out


def _h2h_against(facts: Facts, ref: MatchRef, edge: str) -> bool | None:
    """🔴 맞대결이 **우위 팀과 반대**인가. 못 세면 `None`(미확인)."""
    box = dict(getattr(facts, "h2h", None) or {})
    again = dict(box.get("recounted") or {})
    if again.get("n"):
        w, lose = int(again.get("w") or 0), int(again.get("l") or 0)
    else:
        said = box.get("summary")
        n = int(box.get("count") or 0)
        if not (isinstance(said, (list, tuple)) and len(said) == 3 and n):
            return None
        w, lose = int(said[0]), int(said[2])
    if w == lose:
        return False
    lead = "home" if w > lose else "away"
    return bool(edge) and lead != edge


async def run(ref: MatchRef, facts: Facts, rows: list, *, state: RunState,
              chain: Any = None, net: Any = None, edge: str = "",
              xi_state: str = "", priority: dict | None = None) -> list:
    """🔴🔴 ⑫b — 조건 목록의 **상태를 채운다**. 돌려주는 것은 같은 목록이다.

    🔴 검색은 ③ 의 문(`s3_docs._candidates`)을 그대로 지난다 — 신원·날짜·도메인
       등급 검사가 거기 붙어 있다(새 검색기를 만들지 않는다).
    ⚠️ `chain` 이 없으면(재생·오프라인) 질의 종류는 **미확인**으로 남는다.
    """
    from app import cassette as _cas
    got = by_structure(
        rows, xi_state=xi_state,
        h2h_against=_h2h_against(facts, ref, edge),
        priority_low=(None if not dict(priority or {}) else None))
    asked = 0
    replay = _cas.mode() == _cas.REPLAY
    if chain is not None and not replay:
        got, asked = await _by_query(ref, got, state=state, chain=chain)
    elif replay:
        state.note("⑫b 반증 — ⬜ **재생이라 질의를 안 던졌다**(녹음이 모른다) · "
                   "구조 사실만 판정했다")
    else:
        state.note("⑫b 반증 — ⬜ 검색 통로가 없다(`chain` 이 없다) · 구조 "
                   "사실만 판정했다")
    n_broke = sum(1 for c in got if c.state == BROKEN)
    n_intact = sum(1 for c in got if c.state == INTACT)
    n_unknown = sum(1 for c in got if c.state == UNKNOWN)
    logger.info("[s5b] 반증 — 조건 %d · 질의 %d · 무너짐 %d · 없음 %d · 미확인 %d",
                len(got), asked, n_broke, n_intact, n_unknown)
    state.note(f"⑫b 반증 — 조건 {len(got)} · 질의 {asked} · 무너짐 {n_broke} · "
               f"없음 {n_intact} · 미확인 {n_unknown}")
    return got


async def _by_query(ref: MatchRef, rows: list, *, state: RunState,
                    chain: Any) -> tuple[list, int]:
    """🔴 질의로 확인하는 종류(K1·K6) — ③ 의 문을 그대로 쓴다."""
    from app.core.stages import s3_docs as _s3
    from app.research.subtasks import Budget, Subtask
    out: list = []
    asked = 0
    for one in rows:
        kind = str(getattr(one, "kind", "") or "")
        if kind in NO_QUERY_KINDS or one.state != UNKNOWN:
            out.append(one)
            continue
        who = str(getattr(one, "player_name", "") or "")
        if not who or asked >= SEARCH_CAP:
            out.append(one.model_copy(update={
                "said": str(getattr(one, "said", ""))
                + (" → ⬜ 상한에 닿아 안 던졌다" if who else
                   " → ⬜ 대상 선수를 못 골랐다")}))
            continue
        # 🔴 하위 과제 **한 개**를 만들어 ③ 의 문을 지난다(예산은 작게)
        sub = Subtask(
            name=f"반증/{one.id}", group="BRK", label="반증",
            kinds=tuple(QUERY_WORDS.get(kind, ())), side="",
            team=str(getattr(ref, "home_name", "") or ""),
            opp=str(getattr(ref, "away_name", "") or ""),
            team_key=str(getattr(ref, "home", "") or ""),
            opp_key=str(getattr(ref, "away", "") or ""),
            seed=f"{who} 결장", rerank_query="absent injured rested bench",
            budget=Budget(search_cap=PER_COND, fetch_cap=PER_COND,
                          out_cap=PER_COND, turns=1))
        queries = [(f"{who} {w}", "en") for w in ("absent injured", "starting")]
        hits = await _s3._candidates(sub, ref, state=state, chain=chain,
                                     queries=queries[:PER_COND],
                                     tag=f"반증/{one.id}")
        asked += min(PER_COND, len(queries))
        if hits:
            doc, why = hits[0][0], str(hits[0][1] or "")
            out.append(one.model_copy(update={
                "state": BROKEN, "strength": "soft",
                "source": str(getattr(doc, "url", "") or why)[:200],
                "found_at": str(getattr(doc, "published_at", "") or ""),
                "said": str(getattr(one, "said", "")) + " → 기사가 걸렸다"}))
        else:
            out.append(one.model_copy(update={
                "state": INTACT, "source": "질의 0건",
                "said": str(getattr(one, "said", ""))
                + " → 반증 기사 0건(무너짐 없음)"}))
    return out, asked
