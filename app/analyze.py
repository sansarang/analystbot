"""**배선** — 질문 한 줄 → 카드 한 장 (STEP 1~7).

사용자 지시 2026-10-02: *"배선해라.."*

## 🔴 이 파일이 있는 이유

블록 열두 개가 **하나하나는 섰는데 이어진 곳이 없었다.** `tests/test_wiring.py` 의
`NOT_WIRED` 가 그 사실을 이름으로 들고 있었다 — *"부르는 쪽은 오케스트레이션이고
아직 없다"*. CLAUDE.md §배선: **안 이어진 코드는 없는 코드보다 나쁘다.**

```
사실 수집(세포)  →  §4 분류  →  §5 시나리오  →  §6 생존  →  §7 방아쇠  →  카드
   gather()        classify     scenarios       survive      triggers     render
```

## 🔴 판정은 수집과 **따로** 돈다

`tests/test_wiring.py::test_수집이_판정하지_않는다` 가 그것을 잠근다. 그래서 이
파일은 `app/collect/` 를 고치지 않고 **세포를 직접 부른다** — 수집기는 사실만 모으고,
판정은 여기서 시작한다.

## ⚠️ 발송은 여기 없다

§11-11 — `SEND_ENABLED` 는 단계 9 전까지 off 다. 이 파일은 **글만 만든다.**
부르는 쪽(`app/bot/main.py`)이 그 글을 답으로 돌려준다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import ledgerbook as _ledgerbook
from app import (classify, funnel as _funnel, league, rules, scenarios,
                 survive, timefmt, triggers)
from app.blackboard import Blackboard
from app.cells import (ASK, DEEP, Q_INTENT, Q_LINEUP, Q_STANDINGS,
                       Q_STARTER_RECENT, Budget, Cell, Question, SourceScores)
from app.net import Net
from app.reasons import Reason
from app.searchcells import (coach_cell, intent_cell, lineup_cell,
                            standings_cell, starter_recent_cell)

logger = logging.getLogger(__name__)

#: 🔴 어느 세포를 부르나. `(이름, 질문 타입, 상대를 주나)` 셋을 적는다.
#
#  ⚠️ 종전에는 이름만 적고 `getattr(searchcells, f"{name}_cell")` 로 불렀다.
#     🔴 그러면 **배선 계약이 호출부를 못 본다** — 실측 2026-10-03: 새로 만든
#     `standings_cell` 이 *"부르는 곳이 없다"* 로 빨개졌다(옳은 지적이다 ·
#     문자열로 부르면 사람도 기계도 흐름을 못 따라간다).
#  🔴 그래서 **함수를 직접** 넣는다 — `searchcells` 를 모듈 꼭대기에서 들인다.
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **신원(질의)과 귀속(판정)은 다르다** — 사용자 수정 ① (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  행의 다섯째 칸 `opp_in_query` 는 *"**질의에** 상대 이름을 넣나"* 다.
#  넷째 칸 `with_opponent` 와 **다른 질문**이다 — 그쪽은 *"**귀속 판정에** 상대를
#  요구하나"*(§17-g-3)다. 🔴 이 저장소는 그 둘을 섞어 전에 다쳤다.
#
#  ⚠️ `starter_recent` 만 `False` 다: 그 질문은 **지난 경기**를 묻는다(선발의 최근
#     등판). 🔴 거기에 오늘 상대를 넣으면 **없는 기사**를 찾는 질의가 된다 —
#     그 투수는 오늘 상대와 지난주에 안 붙었다.
CELL_PLAN = (("lineup", Q_LINEUP, True, lineup_cell, True),
             ("intent", Q_INTENT, False, intent_cell, True),
             ("coach", Q_INTENT, True, coach_cell, True),
             ("starter_recent", Q_STARTER_RECENT, False, starter_recent_cell,
              False),
             # 🔴🔴 **순위 세포**(사용자 기술 지시 2026-10-03 · ③ 추출기 배선).
             #    ⚠️ 종전에 순위는 **어댑터 깊이로만** 왔다 — 그래서 어댑터가
             #       순위를 안 주는 리그(KBO·국제 친선)는 `stakes`·`home_field`
             #       변수가 **통째로 0** 이었다. §17-b 의 `L3` 추출기도 그래서
             #       부르는 곳이 **0곳**이었다(만들어 두고 안 썼다 · #2 배선).
             #    🔴 **공식 깊이가 있으면 그쪽이 이긴다** — 아래 호출부가 깊이가
             #       비었을 때만 건다(§19-b-4 대체).
             ("standings", Q_STANDINGS, True, standings_cell, True))

#: 🔴 라인업 세포는 **T-70분부터** 깨어 있다(§19-d). 질문이 그보다 일찍 오면 깨우려고
#   시계를 당긴다 — 그러지 않으면 질문마다 *"아직 시간이 아니다"* 만 돌아온다.
#   ⚠️ 검증기의 "지금"은 **당기지 않는다** — 날짜 검사가 느슨해지면 안 된다.
LINEUP_NUDGE_MIN = 30


def _agent_note(game: dict, team: str, other: str, fun, seen=None) -> str:
    """🔴 §3 에이전트를 돌리고 **한 줄**을 돌려준다(카드가 그것을 적는다).

    ⚠️ 키가 없거나 예산을 넘었으면 **돌지 않고 사유만** 남긴다 — v4 규칙 경로가
       그대로 돈다(§3 이 그것을 대체하는 것은 §10 게이트 2 뒤다).
    ✅ **도구는 꽂혔다**(§3-2 · 2026-10-04) — 세포가 받아 둔 검색 결과·본문을
       `Tools.search`/`fetch` 가 낸다(`cells.Seen`). 🔴 **새로 긁지 않는다**:
       세포들이 이미 받았고, 또 긁으면 같은 페이지를 두 배로 두드린다.
    🔴🔴 **게이트 2 가 켜졌다**(사용자 지시 2026-10-04: *"게이트2 켜라 에이전트
       돌려봐라"*). ⚠️ 돌리는 것은 `_run_agent` 이고 이 함수는 **못 돌리는 사유**
       만 돌려준다 — 빈 문자열이면 *"돌려도 된다"* 는 뜻이다.
    """
    from app.config import get_settings
    s = get_settings()
    if not s.solar_ready:
        return ("⚠️ §3 에이전트를 **안 돌렸다** — `UPSTAGE_API_KEY` 가 없다. "
                "v4 규칙 경로가 돈다(키 부재로 크래시하지 않는다)")
    from app import solar
    ok, why = solar.gate()
    if not ok:
        fun.drop(Reason.LLM_UNAVAILABLE, "agent_vars")
        return f"🔴 §3 에이전트를 **안 돌렸다** — {why}"
    got = seen.line() if seen is not None else "§3-2 — 받아 둔 것을 안 모았다"
    if not s.agent_enabled:
        # 🔴 **스위치가 꺼짐이다.** ⚠️ 비용을 코드가 혼자 켜지 않는다.
        return ("⚠️ §3 에이전트 **안 돌렸다** — `AGENT_ENABLED` 가 꺼짐이다"
                f"(게이트 2). 도구는 꽂혔다({got}) · {solar.MatchBudget().line()}")
    return ""


def _book_parts(tasks: list, live: list) -> list[dict]:
    """🔴 장부에 넣을 칸들 — **한 곳**에서 만든다(#1 사본 금지).

    🔴🔴 `budget_cut` 을 **함께 싣는다**(사용자 지시 2026-10-06 ③):
       > 한 팀 하위 4개 중 **하나라도 `budget_cut`** 이면 2차 보충 대상.
    ⚠️ 변수를 몇 개 냈어도 막힌 것은 막힌 것이다 — 그 하위는 할 말을 다 못 했다.
    """
    out: list[dict] = []
    for t, (got, _n) in zip(tasks, live, strict=False):
        out.append({
            "group": t.group, "team_key": t.team_key,
            "searched": t.budget.search_used,
            "variables": got or [], "verified": len(got or []),
            # 🔴 예산에 막혔나 — `MatchBudget.cut_why` 가 그 사실을 들고 있다
            "budget_cut": str(getattr(t.budget, "cut_why", "") or "")})
    return out


async def _run_agent(game: dict, side: str, fun, seen,
                     facts: list, kick, langs,
                     chain=None, net=None, pot=None,
                     subtask=None) -> tuple[list, str]:
    """🔴🔴 **게이트 2 — §3 에이전트를 돌린다.** `(판정층 변수들, 한 줄)`.

    ══════════════════════════════════════════════════════════════════
    🔴 **새로 긁지 않는다** — 세포가 받아 둔 것을 준다(§3-2)
    ══════════════════════════════════════════════════════════════════

    ⚠️ `solar.chat` 은 **동기**다. 🔴 그대로 부르면 그 몇 분 동안 이벤트 루프가
       멈추고 다른 세포가 **아무것도 못 한다** — `asyncio.to_thread` 로 뺀다.
    🔴 사유는 **빈 문자열로 두지 않는다**(#3) — 안 돌았으면 왜인지 적는다.
    """
    # 🔴 §8-1 — 인자는 **쪽**(`home`/`away`)이다. 이름은 `game` 에서 꺼낸다.
    #    ⚠️ 계약이 내 첫 판(`team: str`)을 잡았다 — **맞았다**: 이름을 인자로
    #       받으면 그 함수가 또 하나의 해석 지점이 된다(§8-1).
    team = str(game.get("home" if side == "home" else "away") or "")
    other = str(game.get("away" if side == "home" else "home") or "")
    said = _agent_note(game, team, other, fun, seen)
    if said:
        return [], said
    from app import agentloop, verifylayer
    try:
        inp = agentloop.AgentInput(
            match_key=str(game.get("ext_id") or ""),
            home=str(game.get("home_id") or ""),
            away=str(game.get("away_id") or ""),
            # 🔴 §8-1 — **열쇠로** 이름을 얻는다(이름을 넘기지 않는다)
            home_names=tuple(_names_of_key(game.get("home_id"))),
            away_names=tuple(_names_of_key(game.get("away_id"))),
            competition=str(game.get("league") or ""),
            sport=str(game.get("sport") or ""),
            # 🔴🔴 **카탈로그를 넘긴다**(사용자 지시 2026-10-05). ⚠️ 이 칸이
            #    **비어 있었다** — `remind_line` 이 말할 준비가 돼 있었는데
            #    재료가 없었다(#2 배선). 🔴 목록은 설정이 원본이다.
            # 🔴🔴 **하위 과제**(딥서치 재구축 §2) — 담당 유형군만 맡는다.
            #    ⚠️ 하위가 없으면(옛 경로) 종전처럼 **카탈로그 전체**다.
            subtask=subtask,
            checklist=(tuple(subtask.kinds) if subtask is not None
                       else tuple(sorted(rules.variable_types()))),
            # 🔴🔴 **빈 구조 칸**(지시서 §3-3) — 미등록 리그는 어댑터가 아무
            #    것도 안 준다. ⚠️ 그 사실을 **이름으로** 넘겨야 그가 찾는다.
            gaps=tuple(gaps_of(facts, sport=str(game.get("sport") or ""))),
            kickoff_utc=kick, venue=str(game.get("venue") or ""),
            langs=tuple(langs or ("en",)))
    except (ValueError, TypeError) as exc:
        return [], f"🔴 §3 에이전트 입력을 못 만들었다(§3-1): {exc}"
    ctx = verifylayer.Context(
        home=inp.home, away=inp.away,
        home_names=list(inp.home_names), away_names=list(inp.away_names),
        competition=inp.competition, roster=list(roster_of(facts, team)),
        kickoff=kick, bodies=dict(getattr(seen, "bodies", {}) or {}),
        # 🔴 **저장소를 넘긴다**(지시서 §3) — 날짜를 `doc_date` 로 읽는다
        seen=seen)
    import asyncio as _aio
    try:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **쪽마다 예산의 반**을 준다 — 사용자 결정 2026-10-04
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측(게이트2 2판): 한쪽이 출력 예산을 다 써 `budget_cut` 으로
        #     **변수 0개**를 냈다 — MLB 밀워키 0/파드리스 6 · KBO 한화 0/키움 2.
        #     🔴 KBO 는 그래서 `verified_vars 2` 로 끝났다.
        #  🔴 `share=0.5` 는 **쪽이 둘**이라는 사실에서 온다 — 손으로 고른
        #     계수가 아니다(홈·원정 둘이 각자 반을 쓴다).
        from app import solar as _solar
        got, why = await _aio.to_thread(
            agentloop.run, inp, ctx, funnel=fun, seen=seen,
            # 🔴 쪽 상한 25k + **경기 합계 40k**(지시서 §1-4 · 2026-10-05).
            #    ⚠️ 종전 `share=0.5`(20k 고정)는 상대가 쉬어도 그 몫을 못 쓰게
            #       했다 — 25k 는 그 여유이고, 합계는 `pot` 이 막는다.
            # 🔴 하위가 있으면 **하위 상한**(4,000)이 걸린다(M59) — 합계는
            #    `pot` 이 그대로 막는다(§2: "합계는 기존 상한 그대로").
            budget=_solar.MatchBudget(
                side=True, pot=pot,
                # 🔴 **하위 객체를 든다**(M59 집행) — 상한을 거기서 읽고 쓴 것을
                #    거기에 적는다. ⚠️ 합계(`pot`)는 그대로 벽이다.
                subtask=subtask,
                subtask_out=(subtask.budget.out_cap if subtask is not None
                             else 0)),
            # 🔴 결정 ③ — 세포가 안 찾으니 **에이전트가 찾고 연다**
            #    ⚠️ `fetcher=` 다 — `net=` 은 `solar.chat` 의 시험용 대역이다
            chain=chain, fetcher=net)
    except Exception as exc:                            # noqa: BLE001
        logger.warning("[analyze] §3 에이전트 실패: %r", exc)
        # 🔴 **깔때기에도 남긴다**(⑭ · 실측 2026-10-05) — 세포 장부에만 적히면
        #    깔때기만 읽는 사람은 *"두 팀이 다 돌았다"* 로 읽는다.
        if fun is not None:
            fun.drop(Reason.AGENT_CRASHED, "agent_vars")
        return [], f"🔴 §3 에이전트가 **터졌다** — {exc!r}"
    # 🔴🔴 §5-4 — **방향은 코드가 다시 정한다**(모델 힌트를 쓰지 않는다)
    g = classify.Game(home=game.get("home") or "", away=game.get("away") or "",
                      sport=game.get("sport") or "",
                      league=game.get("league") or "",
                      home_id=game.get("home_id") or "",
                      away_id=game.get("away_id") or "")
    rows = classify.from_agent_vars(got, g)
    kept = [r for r in rows if r.is_variable]
    dropped = [r for r in rows if not r.is_variable]
    # 🔴 **M50** — 기호로 시작하지 않는다(카드가 접두로 거르지 않게 됐으니
    #    기호를 앞에 둘 까닭도 없다). ⚠️ 실측: `✅ …` 로 시작해 걸러졌다.
    note = (f"§3 에이전트 — {why} → 판정층 변수 **{len(kept)}개**"
            + (f" · 쪽을 못 가린 것 {len(dropped)}개" if dropped else ""))
    return kept, note


def _names_of_key(key: object) -> list[str]:
    """🔴 그 팀을 가리키는 **모든 이름**(공식명·별칭).

    ⚠️ §8-1 — 인자는 **열쇠**다(이름이 아니다). 🔴 이름을 인자로 받으면 그
       함수가 또 하나의 해석 지점이 되고, §8-1 은 그것을 `resolve()` 한 곳으로
       묶는다. ✅ 계약이 내 첫 판(`_ent_names(team)`)을 잡았다 — **맞았다.**
    """
    from app import entities, teamref
    k = str(key or "")
    if not k:
        return []
    # 🔴 **영어 대표명이 맨 앞**이다 — 검색 순서가 그 순서다(§4-2).
    got = [teamref.label_of(k, lang) for lang in ("en", "ko", "ja", "es")]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이름표가 든 것을 전부 꺼낸다**(실측 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전은 `label_of(k, lang)` **넷**뿐이었다 — 그것은 언어마다 **대표
    #     이름 하나**다. 🔴 이름표는 `names['en']` 에 여럿을 든다:
    #
    #       reg.teams["team:000338"].all_names()
    #         → ['Milwaukee Brewers', 'mlb:158', 'Brewers', '브루어스', …]
    #       _names_of_key(…)  →  ['Milwaukee Brewers', '밀워키 브루어스']
    #                             🔴 **'Brewers' 를 흘렸다**
    #
    #  🔴 그래서 공식 API 의 짧은 이름을 받게 고쳐도 **효과가 0 이었다** —
    #     에이전트 질의 7건이 그대로 `query_too_bare` 로 거부됐다.
    #     ⚠️ 판정 함수를 고치고 **쓰는 곳을 안 고친** 그 병이다(CLAUDE.md #2).
    ref = teamref.registry().teams.get(k)
    if ref is not None:
        got += ref.all_names()
    # 🔴 별칭은 `entities` 가 든다(현지 매체가 부르는 이름 · 사본 금지)
    got += list(entities.names_of(got[0] if got else ""))
    out: list[str] = []
    for n in got:
        # 🔴 **외부 id 는 이름이 아니다**(`mlb:158`·`fdorg:103`) — 이름표가
        #    별칭으로 들고 있지만 검색어로 쓰면 아무 데도 없는 글자다.
        if not n or ":" in n or teamref.is_code(n):
            continue
        if n not in out:
            out.append(n)
    return out


def _required_forms_for(st: dict | None) -> list[str]:
    """🔴🔴 **DeepSeek 에 내릴 필수형 이름들** — 지시서 §3-3.

    > 이 필수형은 v5 §6-2 자동 보강 목록에 추가하고, DeepSeek 단계 3 의
    > `required_types` 입력에도 넣는다.

    ⚠️ 그런데 §6-2 표의 줄은 **대부분 무조건**이고 90분 무승부형만 **조건부**다
       (단판일 때만). 🔴 리그 경기에 *"90분 무승부를 반드시 넣어라"* 를 내리면
       그것은 **거짓 필수형**이고, 모델이 없는 갈래를 지어낸다.
    🔴 조건은 `when_formats` 가 **가리키는 표**가 든다(`scenario_rules.draw_90`)
       — 형식 목록을 여기 베끼지 않는다(#1 사본 금지).
    """
    fmt = str((st or {}).get("match_format") or "unknown")
    out: list[str] = []
    for name, row in rules.required_forms().items():
        points_at = str((row or {}).get("when_formats") or "").strip()
        if points_at and fmt not in _formats_of(points_at):
            continue
        out.append(str(name))
    return sorted(out)


def _formats_of(table: str) -> tuple[str, ...]:
    """🔴 `when_formats` 가 가리키는 표의 형식 목록. ⚠️ 모르는 표 이름이면 빈 것."""
    if table == "draw_90":
        return scenarios.draw_formats()
    logger.warning("[analyze] `when_formats: %s` 가 가리키는 표를 모른다 — "
                   "그 필수형을 내리지 않는다", table)
    return ()


def _hypo_row(i: int, c, *, tag: str = "R") -> dict:
    """🔴 단계 3·4 입력의 변수 한 줄 — **번호는 카드와 같다**(사본 금지)."""
    return {"id": f"{tag}{i + 1}", "type": c.type, "team": c.team,
            "direction": c.direction, "favors": getattr(c, "favors", ""),
            "hardness": 2 if c.hardness == "hard" else 1,
            "claim": _clip(str(c.text or ""), 220)}


def split_basis(varis: list) -> tuple[list, list]:
    """🔴🔴 **근거로 쓸 수 있는 것 / 맥락 전용** — 지시서 2026-10-06 §4-1.

    > `HypoInput.variables` 에는 가설 근거로 쓸 수 있는 변수만 넣는다. 표본
    > 부족·검증 탈락·충돌 버림 변수는 `context_only` 목록으로 따로 보낸다.
    > **반증 단계(단계 4)도 같은 분리.**

    ⚠️ **검증 탈락은 애초에 여기 안 온다** — `is_variable` 이 그것을 걸렀다.
       🔴 여기서 가르는 것은 **통과했지만 근거로는 약한** 것들이다:
       표본 부족(`thin_sample`)과 충돌(hardness 가 `none` 으로 내려간 것).
    """
    basis, ctx = [], []
    for c in (varis or []):
        thin = bool(getattr(c, "thin_sample", ""))
        zero = str(getattr(c, "hardness", "")) == "none"
        (ctx if (thin or zero) else basis).append(c)
    return basis, ctx


def _run_hypo(card, game, items, st, sc):
    """🔴🔴 **단계 3 — DeepSeek 가설·시나리오**(v5-A §3). 지시 ②③ 2026-10-05.

    돌려주는 것은 `hypo.HypoResult` — ⚠️ **못 돌았어도 그 꼴**이다(사유가 든다).

    🔴 하는 일 둘:
      ① `card.hypotheses[*].claim` 에 **문장**을 넣는다(지시 ②)
      ② `sc.drafts` 를 **DeepSeek 시나리오로 바꾼다**(지시 ③) — 템플릿은
         **필수형 보강만** 남기고 `added_by` 가 그것을 말한다

    ⚠️ 실패를 삼키지 않는다 — 사유가 카드 블록 1 에 남는다(#3).
    """
    from app import hypo
    from app.reasons import Reason
    # 🔴 §4-1 — 근거/맥락을 가른다(번호는 전체 목록 순서를 지킨다)
    _basis, _ctx = split_basis(list(card.variables or []))
    if _ctx:
        sc.notes.append(
            f"§4-1 근거 불가 변수 {len(_ctx)}개를 `context_only` 로 보냈다 — "
            f"표본 부족·충돌(그 번호를 인용한 문장은 버려진다)")
    inp = hypo.HypoInput(
        # 🔴 원장이 한 경기로 모이게 — solar 와 **같은 열쇠**다(⑫)
        match_key=str(getattr(card, "match_key", "") or ""),
        home=str(getattr(game, "home_id", "") or ""),
        away=str(getattr(game, "away_id", "") or ""),
        sport=str(getattr(game, "sport", "") or ""),
        competition=str(getattr(game, "league", "") or ""),
        # 🔴🔴 **근거로 쓸 수 있는 것만 `variables` 다** — 지시서 §4-1.
        #    ⚠️ 실측 2026-10-06: 근거에서 뺀 `R1`(h2h 표본 1경기)이 입력에 그대로
        #       들어가 DeepSeek 문장이 그 번호를 인용했다. 🔴 **원인 제거**다.
        #    🔴 번호는 **카드와 같아야** 한다 — 전체 목록으로 매기고 뒤에 가른다.
        variables=[_hypo_row(i, c) for i, c in enumerate(card.variables)
                   if c in _basis],
        context_only=[_hypo_row(i, c) for i, c in enumerate(card.variables)
                      if c in _ctx],
        facts=dict(card.form or {}),
        # ⚠️ `Result` 에 `required_types` 칸이 **없다**(재서 고쳤다) —
        #    필수형 목록은 `rules.required_forms()` 가 든다(사본 금지).
        # 🔴 §3-3 — **조건부 필수형**은 그 조건이 맞을 때만 내린다
        required_types=_required_forms_for(st),
        lineup_state=dict(getattr(card, "xi", {}) or {}))
    got = hypo.run(inp)
    card.ds_why = got.why
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **안전망 — 출력에서 거른다**(지시서 §4-2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 가설 문장은 **그 문장을 버리고** 사유 `cited_excluded:R1` 을 블록 5 에
    #  > 적는다(문장을 고쳐 쓰지 않는다). 시나리오는 그 번호만 `driver_vars`
    #  > 에서 빼고, 남은 driver 가 0개면 시나리오를 버린다.
    #
    #  ⚠️ 입력에서 뺐는데도 모델이 그 번호를 쓸 수 있다 — 그때를 위한 그물이다.
    _ban = hypo.excluded_ids(inp)
    if _ban:
        got.hypotheses, _d1 = hypo.drop_cited(got.hypotheses or {},
                                              excluded=_ban)
        got.scenarios, _d2 = hypo.strip_cited(got.scenarios or [],
                                              excluded=_ban)
        for said in (_d1 + _d2):
            sc.notes.append(f"§4-2 {said}")
    if got.reason is not Reason.OK or not got.scenarios:
        # 🔴 **0개면 그 사실을 이름으로** 남긴다(지시 ③)
        sc.notes.append(
            f"🔴 **DeepSeek 시나리오 0개** — 템플릿으로 돈다(M45): "
            f"{got.why or got.reason.value}")
        if hasattr(Reason, "DEEPSEEK_NO_SCENARIO"):
            sc.incomplete_why.append(
                f"🔴 `{Reason.DEEPSEEK_NO_SCENARIO.value}` — {_clip(str(got.why or ""), 120)}")
        return got
    # ── ① 가설 **문장**
    for h in (card.hypotheses or []):
        # 🔴 꼴 읽기는 `hypo_sentences` **한 곳**이다(#1 사본 금지 · #2 배선).
        wins, breaks = hypo_sentences(got.hypotheses or {}, side=h.side)
        box = (got.hypotheses or {}).get(h.side) or {}
        if not box and (got.hypotheses or {}):
            # 🔴 **빈 것과 자리를 못 맞춘 것을 가른다**(#3) — 모델이 자리를
            #    안 쓰고 이름으로 줬다면 그 사실이 보여야 한다.
            sc.notes.append(
                f"⚠️ DeepSeek 가설이 자리(`{h.side}`)로 안 왔다 — 받은 열쇠 "
                f"{sorted(got.hypotheses)[:4]}(지시 ②)")
        raw = len(box.get("reasons") or []) + len(box.get("breaks") or [])
        if raw and raw > len(wins) + len(breaks):
            # 🔴 **조용히 버리지 않는다**(#3) — 몇 개가 번호뿐이었나를 적는다
            sc.notes.append(
                f"⚠️ `{h.team}` 가설 {raw - len(wins) - len(breaks)}개가 "
                f"**문장이 아니라 번호**였다 — 버렸다(지시 ②)")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **근거가 0건이면 "이긴다면" 을 적지 않는다** — 사용자 지시 ⑦
        # ══════════════════════════════════════════════════════════════
        #
        #  > 한 팀 근거가 0건이면 **"이긴다면" 문장 대신** "근거 변수 없음 —
        #  > 반대 팀 가설이 무너지는 조건만" 경로로 쓴다.
        #
        #  ⚠️ 실측 2026-10-06(북아일랜드–조지아) 카드:
        #       `Georgia: 근거 0건 · 깨는 변수 4건`
        #       `  이긴다면: 최근 5경기에 승리를 포함해 … 흐름이 있다(R4).`
        #     🔴 R4 는 **홈 쪽** 변수다. 근거가 0건인데 세 문장이 섰다 — 그
        #     문장들은 **받치는 변수가 없는 말**이고, 그것이 §1 이 금지한
        #     *"변수 없는 주장"* 이다.
        if not h.supports:
            h.win_why, h.break_why = [], breaks[:4]
            h.claim = ""
            h.claim_by = ("근거 변수 없음 — 반대 팀 가설이 무너지는 조건만"
                          + (f"(표본 부족으로 뺀 것 {len(h.thin_dropped)}개)"
                             if h.thin_dropped else ""))
            if wins:
                # 🔴 **버린 사실을 적는다**(#3) — 모델은 문장을 냈고 우리가 뺐다
                sc.notes.append(
                    f"§7 `{h.team}` — 근거 변수가 **0개**라 DeepSeek 의 "
                    f"*이긴다면* {len(wins)}문장을 **쓰지 않았다**"
                    f"(사용자 지시 2026-10-06 ⑦)")
            continue
        h.win_why, h.break_why = wins[:4], breaks[:4]
        if h.win_why or h.break_why:
            h.claim = h.win_why[0] if h.win_why else ""
            h.claim_by = "v5-A §3 DeepSeek(단계 3)"
    # ── ② 시나리오 **교체** — 템플릿은 필수형 보강만 남긴다
    keep = [d for d in (sc.drafts or []) if d.added_by == "required"]
    fresh = scenarios.from_deepseek(got.scenarios, game, keep=keep)
    if fresh:
        sc.drafts = fresh
        sc.notes.append(
            f"🔴 **시나리오를 DeepSeek 것으로 바꿨다**(지시 ③) — "
            f"{len(got.scenarios)}개 + 코드 필수형 {len(keep)}개")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **판 이 바뀌었으니 다시 센다** — 실측 2026-10-05 (pn10)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고: 난타전 판정이 `generate` 안에서 **템플릿**을 보고 돌았고,
        #     카드는 *"4골 합계가 하나도 없다"* 라고 적으면서 바로 아래
        #     `A ['3-1','2-1']` 을 보여 줬다 — 지나간 패로 판정했다.
        #  🔴 `require_slugfest` 가 **자기 흔적을 걷고** 다시 센다.
        scenarios._slugfest_gate(sc, game, st)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **격자를 다시 붙인다** — 실측 2026-10-05
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고: 갈아 치운 시나리오에 `probability` 가 **없었다** — 포아송
        #     격자(§5-c-1 ②)가 템플릿에만 붙어 있었고 교체로 통째로 사라졌다.
        #  🔴 그러면 `total_probability` 가 `None` 이 되고 무게가 확률이 아니라
        #     **개수**로만 선다 — 지시 ③ 이 바란 것이 아니다.
        scenarios.attach_probability(sc, game, st)
        # 🔴 **형식 필수형도 다시 센다**(M108) — 난타전과 같은 길이다.
        scenarios.require_draw(
            sc, game,
            fmt=str((st or {}).get("match_format") or "unknown"))
        # 🔴 **회귀형 필수**(M107) — 보정 평균이 1.0 이상 낮으면 저득점 갈래가
        #    있어야 한다. ⚠️ 못 재면 강제하지 않는다(지어내지 않는다).
        for _who, _raw in ((game.home, (card.form or {}).get(game.home)),
                           (game.away, (card.form or {}).get(game.away))):
            box = dict(_raw or {})
            a, b = box.get("recent_scored_avg"), box.get("recent_trimmed_avg")
            if a is None or b is None:
                continue
            need, why = scenarios.regression_needed(float(a), float(b))
            if need:
                sc.notes.append(f"§3-2 {_who} — {why}")
    return got


def _run_redteam(card, game, sc, st, probs, board):
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **`game` 은 `classify.Game` 이다 — dict 가 아니다**(실측 2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 서명을 `game: dict` 로 적고 `game.get(...)` 을 썼다. 🔴 DeepSeek 를
    #     켜자 **카드 시험 열 개가 터졌다**(`'Game' object has no attribute
    #     'get'`) — 반증이 꺼져 있던 동안 이 줄이 **한 번도 안 돌았다.**
    #  🔴 안 이어진 코드는 없는 코드보다 나쁘다(#2) — 켜 보기 전까지 몰랐다.
    """🔴🔴 **v5-A §4 반증을 돌린다.** ⚠️ 못 돌면 `Outcome` 에 사유가 남는다.

    🔴 `grade` 를 **여기서 만든다** — §6 을 다시 짓지 않고 `survive.run` 을
       그대로 부른다(#1 사본 금지). ⚠️ 그래야 1차와 재대입이 **같은 자**다.
    """
    from app import hypo, judgeorder, survive as _sv

    def grade(rows: list) -> dict:
        got = _sv.run(rows, game, board=board, variables=card.variables,
                      fold=sc.fold_markets,
                      xi_state=xi_state(card.xi, game),
                      standings=st, probs=probs)
        return {_sv.name_of(m): float(m.survival or 0)
                for m in (got.markets or [])}

    # 🔴 §4-1 — 반증도 근거/맥락을 가른다
    _rt_basis, _rt_ctx = split_basis(list(card.variables or []))
    inp = hypo.HypoInput(
        # 🔴 원장이 한 경기로 모이게 — solar 와 **같은 열쇠**다(⑫)
        match_key=str(getattr(card, "match_key", "") or ""),
        home=str(getattr(game, "home_id", "") or ""),
        away=str(getattr(game, "away_id", "") or ""),
        sport=str(getattr(game, "sport", "") or ""),
        competition=str(getattr(game, "league", "") or ""),
        # 🔴🔴 **반증 단계도 같은 분리다** — 지시서 2026-10-06 §4-1 마지막 줄.
        #    ⚠️ 반증이 근거 불가 변수를 **반증 대상**으로 삼으면, 그 변수가
        #       근거였던 적이 없는데 *"이 근거가 틀렸다"* 를 쓴다.
        #    🔴 번호(`V1`…)는 단계 3 의 `R1`… 과 **다른 꼬리표**다 — 그 둘을
        #       섞으면 블록 5 와 반증 블록이 다른 것을 같은 이름으로 부른다.
        variables=[_hypo_row(i, c, tag="V")
                   for i, c in enumerate(card.variables) if c in _rt_basis],
        context_only=[_hypo_row(i, c, tag="V")
                      for i, c in enumerate(card.variables) if c in _rt_ctx],
        facts={}, board=[], required_types=list(sc.incomplete_why or []))
    try:
        return judgeorder.run(inp, list(sc.drafts or []), grade=grade)
    except Exception as exc:                                # noqa: BLE001
        logger.warning("[analyze] §4 반증 실패: %r", exc)
        return None


def _cells_seen():
    """🔴 §3-2 — `cells.Seen` 하나. ⚠️ 가져오기를 함수로 둬서 순환을 피한다."""
    from app.cells import Seen
    return Seen()


def state_shown(why: object) -> bool:
    """🔴🔴 **그 상태 줄을 카드에 적나**(§8-5 · M50).

    ══════════════════════════════════════════════════════════════════
    🔴 기준이 **두 번** 줄을 삼켰다 — 그래서 기준을 걷었다
    ══════════════════════════════════════════════════════════════════

    ① 종전 판정은 글자 넷(`unknown`·`error`·`묻지 않는다`·`없`)을 **포함할
       때만** 보여 줬다. 카드 머리글은 *"세포 **78개**"* 라고 적었고 나온 줄은
       **47개**였다 — `에이전트:{팀}` 상태가 **네 번 내내** 안 나왔다.
    ② 그래서 표시(🔴·⚠️)로 골랐다. 🔴 **또 삼켰다** — 내가 에이전트 줄을
       `✅ …` 로 시작했고 그 글자가 목록에 없었다.

    🔴 작업 지시서 §1 **M50**: *"카드 파이프라인은 **접두 기호로 줄을 거르지
       않는다**."* → **기호·낱말 판정을 전부 걷었다.** 글자가 있으면 나온다.
    ⚠️ 그래도 카드가 덮이지 않는 까닭: `_tally` 가 **같은 말을 `×N` 으로
       묶는다**(카탈로그 28줄의 교훈은 그쪽에서 이미 풀렸다).
    """
    return bool(str(why or "").strip())



def _depth_fetches(depth: list) -> int:
    """🔴🔴 **깊이 세포의 열기 예산** — 소스마다 `1 + 따라가기 몫`.

    ⚠️ 종전은 `len(depth) + 1` 이었다. 그러면 **따라가기가 공짜**로 셈돼, 먼저 온
       소스의 따라가기가 예산을 다 쓰고 뒤 소스는 한 번도 안 돈다.
    🔴 실측 2026-10-04(밀워키 vs 샌디에이고): 예산 3 · 박스스코어 1 + 따라가기 3 →
       새로 붙인 `MLB 예고 선발` 이 **`예산소진`** 으로 **한 번도 안 돌았다.**
       ①(예고 선발 배선)이 **예산에 막혀** 값을 못 냈다.
    ⚠️ 이 수는 **공식 API 호출**이다(키 없음·카드 없음·`verify=False` 1층) —
       그래도 늘리는 것이니 선언에서 자라게 둔다. 🔴 몫을 안 적은 소스는 0 이고,
       그러면 종전과 같은 수가 된다(NHL: 1+0+1 = 2).
    """
    return sum(1 + int(getattr(s, "follow_max", 0) or 0) for s in depth) + 1


def depth_sources(game: dict) -> list:
    """🔴 그 경기의 **공식 API 깊이**(맞대결·폼·선수·순위).

    ⚠️ **어댑터가 `sources_context` 를 가질 때만이다** — 없는 종목에 있는 척하지
       않는다(K리그·해외축구는 아직 없다). 그 사실은 사유로 남는다.
    🔴 원본은 어댑터다(`mlb.sources_context`·`nhl.…`) — 주소를 여기 적지 않는다.
    """
    from app.collect import ingest
    ext = game.get("ext_id")
    if not ext:
        return []
    # 🔴🔴 **어느 어댑터가 아나는 `ingest` 가 정한다**(한 곳에만 둔다).
    #
    #  ⚠️ 리그 이름이 표에 없을 수 있다 — 봇이 스스로 찾아 적은 경기는
    #     `Friendlies`·`fifa.friendly` 처럼 온다(실측 2026-10-02: 그래서 깊이가 0 이고
    #     **변수 0건 · §7 R5 자료 부족**으로 끝났다). 그때 `ext_id` 접두가 가리킨다.
    fn = ingest.context_of(game.get("league") or "", str(ext))
    if not callable(fn):
        return []
    try:
        return list(fn(str(ext)))
    except Exception as exc:                                # noqa: BLE001
        logger.warning("[analyze] 깊이 소스 실패 %s: %r", game.get("league"), exc)
        return []


#: 🔴 `states` 안에서 깔때기가 앉는 자리. ⚠️ 사람이 읽는 사유 줄과 섞이지 않게
#   **이름으로 가른다** — 카드 렌더러가 이 열쇠를 따로 꺼내 쓴다.
_FUNNEL_KEY = "__funnel__"
#: 🔴🔴 **게이트 2** — §3 에이전트가 낸 **검증 통과 변수**를 `build` 로 나른다.
#  ⚠️ 사람이 읽는 사유 줄과 섞이지 않게 열쇠를 붙인다(깔때기와 같은 결).
_AGENT_KEY = "__agent_vars__"



async def gather(game: dict, *, net: Net | None = None,
                 scores: SourceScores | None = None, search=None,
                 mode: str = DEEP) -> tuple[list, dict]:
    """세포를 돌려 **사실**을 모은다. 돌려주는 것은 `(facts, 세포 상태)`.

    🔴 **세포가 멈춘 사유까지** 돌려준다 — 카드 블록 1(자료 한계 고백)이 그것을 쓴다.
    """
    from app import queries, searchcells
    # 🔴 **한 분석 동안만 캐시를 켠다**(`Net(cache=True)`). 같은 페이지에 다른 질문이
    #    걸린다 — npb.jp 월간 일정이 ① 장소별 득점 ② 예고선발·날씨를 함께 들고 있다.
    #    ⚠️ 라이브 스코어 주기에는 켜지 않는다(점수가 멈춘다).
    net = net or Net(cache=True)
    # 🔴🔴 **경기 합계 지갑**(지시서 §1-4 · 2026-10-05) — 두 쪽이 **함께 본다**.
    #    ⚠️ 팀별 25k 뿐이면 합계가 50k 가 된다. 🔴 합계 40k 가 벽이고, 그 벽은
    #       두 쪽이 **같은 객체**를 볼 때만 선다.
    from app import solar as _sol
    pot = _sol.MatchPot()
    scores = scores or SourceScores()
    # 🔴🔴 **깔때기 하나**를 모든 세포가 함께 쓴다(사용자 기술 지시 2026-10-03).
    #    ⚠️ 세포마다 따로 만들면 합치는 코드가 또 필요하고, 합치기를 빠뜨린 세포가
    #       조용히 빠진다. 🔴 같은 그릇을 넘기면 **빠질 수가 없다.**
    fun = _funnel.Funnel()
    # 🔴🔴 **v5 §3-2 — 본 것을 모으는 자리**(게이트 2). 경기 하나에 **하나**다.
    #    ⚠️ 세포마다 따로 두면 에이전트가 그 중 하나만 본다(깔때기와 같은 결).
    seen = _cells_seen()
    if search is None:
        from app.search import build_chain
        search = build_chain()
    kick = game["kickoff"]
    day = kick.date()
    facts: list = []
    states: dict[str, str] = {}
    # 🔴🔴 **경기 하나의 장부**(딥서치 재구축 §3-2) — 유형군 × 팀 칸.
    #  > 하위가 검색을 돌았으면 `searched`, **검증 통과 변수가 생기면 `found`**,
    #  > 검색했는데 후보 0 이면 `empty`, 실패했으면 `not_tried` + 사유.
    #  🔴 `found` 배선이 이번 재구축에서 완성됐다 — 종전엔 `searched` 만 섰다.
    book = _ledgerbook.Book()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **GDELT 경기당 횟수를 0 으로** — 사용자 지시 2026-10-06 ⑥
    # ══════════════════════════════════════════════════════════════════
    #
    #  > GDELT: **경기당 최대 4회**, SearXNG 가 5건 이상 준 하위에서는 생략.
    #
    #  ⚠️ `GdeltSearch._state` 는 **과정 전체** 칸이다(간격·벌점을 지키려고
    #     그렇게 뒀다). 🔴 그래서 *"경기당"* 을 세려면 경기 경계를 **누군가
    #     말해 줘야** 한다 — 그 자리가 여기다(한 경기의 입구).
    #  ⚠️ 벌점(`rest_until`)은 **안 건드린다** — 그것은 GDELT 가 준 것이다.
    from app.search import GdeltSearch as _Gdelt
    _Gdelt.reset_match()
    for side in ("home", "away"):
        team, other = game[side], game["away" if side == "home" else "home"]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **상대의 현지 표기는 쪽에 따라 뒤집힌다**(실측 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  `game["local"]`·`game["opponent_local"]` 은 **홈 기준**으로 담긴다
        #  (`ref.home_local`·`ref.away_local`). ⚠️ 그래서 **원정 팀 세포**에서
        #  그대로 쓰면 상대가 자기 자신이 된다 — 실측 로그 원문:
        #
        #      `Scotland manager said **Scotland** фудбал`
        #      `Scotland standings magic number **Scotland** фудбал`
        #
        #  🔴 쪽을 보고 **바꿔 넣는다.** 한 곳에서 하면 빠질 수가 없다.
        my_local = game.get("local" if side == "home" else "opponent_local") or ""
        other_local = game.get("opponent_local" if side == "home" else "local") or ""
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **공식 깊이는 자기 세포로 돈다** (실측 2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  종전에는 깊이 소스를 **라인업 세포에 얹었다**. 두 가지가 깨졌다:
        #    ① 세포가 **첫 성공에서 돌아간다** → 순위표만 들어오고 월간 득점·
        #       예고선발·날씨는 **영영 안 왔다**(포아송 격자가 안 선 까닭).
        #    ② 깊이가 라인업 질문의 **답으로 세어졌다** — 순위표 사실이 왔다고
        #       라인업을 찾은 것이 아니다.
        #  🔴 그래서 떼어 `collect_all` 세포로 둔다. 질문 id 에 `:depth` 를 붙여
        #     라인업 세포와 칸이 겹치지 않게 한다(파서가 그 뒤에 `:standings` 등
        #     접미사를 붙이므로 유형 판정은 그대로 돈다).
        depth = depth_sources(game)
        if depth:
            dq = Question(Q_LINEUP, f"{game.get('league') or ''}:{team}:{day}:depth",
                          game_id=game.get("game_id"), team=team,
                          league=game.get("league") or "", deadline=kick,
                          opponent=other,
                          # 🔴 쪽을 따른다 — 원정 세포에서 홈 기준은 뒤집힌다
                          local=my_local or None,
                          opponent_local=other_local or None)
            dcell = Cell(dq, depth, collect_all=True, funnel=fun, seen=seen,
                         budget=Budget(searches=0,
                                       fetches=_depth_fetches(depth)))
            bb = Blackboard()
            try:
                states[f"{team}:깊이"] = await dcell.run(net, bb, search=search,
                                                       scores=scores)
            except Exception as exc:                        # noqa: BLE001
                states[f"{team}:깊이"] = f"error {exc!r}"
                logger.warning("[analyze] %s 깊이 세포 실패: %r", team, exc)
            else:
                for _qid, slot in bb.slots.items():
                    facts.extend(slot.facts)
                for qid, reason in bb.unknowns():
                    states.setdefault(qid, reason)
            logger.info("[analyze] %s 깊이 소스 %d개 → 사실 누적 %d건",
                        team, len(depth), len(facts))
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **한 바퀴 더** — 모은 사실이 다음 주소를 가리킨다(§19-c)
            # ══════════════════════════════════════════════════════════
            #
            #  선발 보정(딥서치 2026-10-03 · A)은 **선발의 ERA** 를 요구한다. 그런데
            #  주소를 알려면 **두 사실을 먼저** 가져야 한다: 누가 선발인가(일정
            #  페이지) + 그 선수 페이지 주소(등록 명단). `Source.follow` 는 자기가
            #  연 페이지만 보므로 그것으로는 닿지 않는다.
            #  ⚠️ **한 바퀴뿐이다** — 이 결과에 다시 `sources_followup` 을 걸지 않는다.
            more = followup_sources(game, facts)
            if more:
                fq = Question(Q_LINEUP,
                              f"{game.get('league') or ''}:{team}:{day}:depth2",
                              game_id=game.get("game_id"), team=team,
                              league=game.get("league") or "", deadline=kick,
                              opponent=other)
                fcell = Cell(fq, more, collect_all=True, funnel=fun, seen=seen,
                             budget=Budget(searches=0, fetches=len(more) + 1))
                bb = Blackboard()
                try:
                    states[f"{team}:깊이2"] = await fcell.run(
                        net, bb, search=search, scores=scores)
                except Exception as exc:                    # noqa: BLE001
                    states[f"{team}:깊이2"] = f"error {exc!r}"
                    logger.warning("[analyze] %s 2차 깊이 실패: %r", team, exc)
                else:
                    for _qid, slot in bb.slots.items():
                        facts.extend(slot.facts)
                    for qid, reason in bb.unknowns():
                        states.setdefault(qid, reason)
                logger.info("[analyze] %s 2차 깊이 %d개 → 사실 누적 %d건",
                            team, len(more), len(facts))
        else:
            # 🔴🔴 **거짓 사유를 적지 않는다**(§8-6) — 아래를 보라
            states.setdefault(f"{team}:깊이", depth_why(game))
        for name, qtype, with_opponent, make, opp_in_query in CELL_PLAN:
            ok, why = queries.asks(game.get("sport") or "", qtype)
            if not ok:
                states[f"{team}:{name}"] = f"묻지 않는다 — {why}"
                continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **순위는 공식 깊이가 있으면 안 묻는다**(§19-b-4 대체)
            # ══════════════════════════════════════════════════════════
            #
            #  🔴 공식 순위표는 **검색 기사보다 정확하다** — 숫자가 표에 있다.
            #  ⚠️ 그런데 그 깊이가 **없는 리그**가 있다(KBO·국제 친선). 거기서만
            #     검색+`L3` 로 간다. 둘 다 돌리면 같은 사실을 두 번 세고(§12-c-4)
            #     예산도 두 배로 쓴다.
            if name == "standings" and _has_official_standings(facts, team):
                states[f"{team}:standings"] = (
                    "묻지 않는다 — **공식 순위표를 이미 받았다**(어댑터 깊이). "
                    "검색은 그것이 없을 때의 대체다(§19-b-4)")
                continue
            kw = dict(team=team, league=game.get("league") or "", day=day,
                      game_id=game.get("game_id"), starts=kick, mode=mode)
            if with_opponent:
                kw["opponent"] = other
            # 🔴 **질의에 신원을 싣는다**(사용자 수정 ① · 실측 +25%~+100%).
            #    ⚠️ 종목·언어는 사다리가 정한 것을 그대로 내린다 — 세포가 다시
            #       계산하면 한쪽이 늘 늦는다(실측 2026-10-03: 언어를 두 번 쟀다).
            if opp_in_query:
                kw["opp_q"] = other
                kw["opp_q_local"] = other_local
            kw["sport"] = game.get("sport") or ""
            kw["langs"] = tuple(game.get("langs") or ())
            if name == "lineup":
                kw["now"] = kick - timedelta(minutes=LINEUP_NUDGE_MIN)
                # 🔴🔴 **공식 API 깊이를 얹는다.** 이것이 없으면 질문 경로는
                #    검색 운에만 매달린다 — 실측 2026-10-02(라이브 2회):
                #      NPB ヤクルト   사실 4건 · 변수 **0건** → 자료 부족
                #      NHL Detroit   사실 6건 · 변수 **0건** → 자료 부족
                #    열기 20/20 을 굿즈몰·호텔·블로그에 태우고 끝났다.
                #    ⚠️ 수집 경로(`ingest._game_cells`)는 **이미 이것을 하고 있었다**
                #       — 질문 경로만 빠져 있었다. 같은 문을 쓴다(사본 금지).
                # 🔴 깊이는 **위 깊이 세포가** 받는다 — 여기 얹으면 첫 성공에서
                #    돌아가 라인업을 찾지 않는다(위 주석 ②).
                kw["extra"] = []
                kw["venue"] = game.get("venue") or ""
                # 🔴 **쪽을 따른다**(위 주석) — 홈 기준 그대로 쓰면 뒤집힌다
                kw["local"] = my_local
                kw["opponent_local"] = other_local
            cell, _ = make(**kw)
            # 🔴 **같은 깔때기를 건다** — 세포마다 따로 만들면 합치기를 빠뜨린
            #    세포가 조용히 빠진다
            cell.funnel = fun
            # 🔴 §3-2 — **같은 `Seen`** 을 건다(에이전트가 그것을 읽는다)
            cell.seen = seen
            # 🔴 이미 모은 사실로 명단을 걸어 둔다 — 라인업 세포가 자기 명단을
            #    만들기 전이면 비어 있고, 그때는 검사가 "못 쟀다"로 돈다.
            cell.roster = roster_of(facts, team)
            bb = Blackboard()
            try:
                states[f"{team}:{name}"] = await cell.run(
                    net, bb, search=search, scores=scores)
            except Exception as exc:                        # noqa: BLE001
                # 🔴 **사유를 남기고 계속한다** — 한 세포가 죽어 카드가 사라지면
                #    "자료가 없다"와 "코드가 터졌다"를 구분할 수 없다
                states[f"{team}:{name}"] = f"error {exc!r}"
                logger.warning("[analyze] %s:%s 세포 실패: %r", team, name, exc)
                continue
            head = cell.question.id
            for qid, slot in bb.slots.items():
                if qid == head or qid.startswith(head + ":"):
                    facts.extend(slot.facts)
            for qid, reason in bb.unknowns():
                states.setdefault(f"{qid}", reason)

        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **카탈로그 — 경기마다 유형 전부를 돌린다**(사용자 설계 2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 내 "딥서치"의 8할은 **이 경기에서 뭘 확인해야 하는지 아는 것**이다
        #
        #  🔴 "무엇을 찾을지"를 모델에게 묻지 않는다 — 유형표가 정한다.
        #  ⚠️ 템플릿이 없는 유형은 세포를 만들지 않는다(구조 자료에서 온다).
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **감독·핵심 선수 이름을 넘긴다** (사용자 기술 지시 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  > **감독·주장·핵심 선수 이름도 검색어가 된다.** 오늘 자메이카 이탈자
        #  > 5명은 `Speid` 로 찾았다.
        #
        #  ⚠️ `catalog_variants` 는 `{coach}`·`{star}` 자리를 **전부터 받고 있었다** —
        #     그런데 여기서 안 넘겨서 그 템플릿들이 *"자리표 못 채움"* 으로 **매번
        #     건너뛰어졌다**(실측 로그에 그 줄이 있다). 선언이 있는데 안 쓰인 자리다.
        #  🔴 감독은 **자료가 선언을 이긴다**(`entities.coach_of`) — 감독은 바뀐다.
        #  🔴 핵심 선수는 **그 경기 자료**에서 온다(최다 득점자) — yaml 에 박지 않는다.
        from app import entities
        coach, coach_why = entities.coach_of(team, facts)
        star = _star_of(facts, team)
        if coach:
            logger.info("[analyze] %s 감독 `%s` (%s) — 검색어로 쓴다",
                        team, coach, coach_why)
        else:
            # 🔴 §8-2 [#11] — **감독 미상은 탈락 사유가 아니다.** 그 각도만
            #    건너뛴다. ⚠️ 깔때기 사유 코드(§8-6)를 **붙이지 않는다.**
            states.setdefault(f"감독:{team}", coach_why)
        # ══════════════════════════════════════════════════════════════
        # 🔴 §8-2 — 엔티티 **여섯 칸**을 카드가 보여 준다(출처와 함께)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 못 채운 칸을 **이름으로** 남긴다 — *"없다"* 와 *"아직 안 쟀다"* 를
        #     가르는 그 규율이다(#3). 🔴 `country`·`league`·`langs` 는 손으로
        #     적지 않고 이름표·리그 명부·Babel 에서 꺼낸다(사본 금지).
        prof = entities.profile(team)
        miss = [k for k in ("coach", "captain", "home_venue", "country",
                            "league", "langs") if prof.get(k) is None]
        if miss:
            states.setdefault(
                f"엔티티:{team}",
                "⚠️ §8-2 못 채운 칸 — " + " · ".join(
                    f"`{k}`({prof['_why'][k]})" for k in miss))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **v5 §3 에이전트 루프** (2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  §1: *"에이전트는 **제안만** 한다 … **검증층을 통과한 변수만 변수**다."*
        #
        #  ⚠️ **키가 없으면 돌지 않는다**(`solar_ready`) — 그때는 v4 규칙 경로가
        #     그대로 돈다. 🔴 키 부재로 크래시하지 않는다.
        #  ⚠️ **예산 가드가 먼저** 묻는다(§2) — 월·하루 상한을 넘었으면 `chat` 이
        #     거부하고 `llm_unavailable` 사유가 남는다.
        #  🔴 적용 순서(§0)가 §3 을 §5·§6 **앞**에 두었다 — 에이전트가 낸 변수가
        #     검증층을 지나 **같은 판정층**으로 간다.
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **게이트 2 — §3 에이전트를 돌린다**(사용자 지시 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ **카탈로그 세포 뒤**다 — 세포가 받아 둔 검색 결과·본문을 그대로
        #     주므로(§3-2) 그 전에 돌리면 에이전트가 **빈손**이다.
        #  🔴 한 팀에 한 번 돈다. ⚠️ 종전 주석은 *"두 팀이 **같은 지갑**을
        #     쓴다"* 였다 — 🔴 **결정 ② 가 그것을 바꿨다**: 쪽마다 **반**을
        #     준다(한쪽이 다 써서 다른쪽이 0개가 되는 것을 막는다).
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **딥서치 재구축 §2 — 하위 과제 병렬**(지시서 2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 경기 하나 = 하위 과제 **8개**(유형군 4 × 홈/원정). 한 에이전트가
        #  > 경기 전체를 돌면 경기당 12분이고, 한쪽이 예산을 다 써서 다른 쪽이
        #  > 0개가 된다(실측 2026-10-04~05).
        #
        #  ⚠️ 이 자리는 **팀마다** 돈다 — 그래서 여기서 그 팀의 하위 **4개**를
        #     병렬로 돌린다(두 팀 합쳐 8개).
        #  🔴 하위 하나가 터져도 나머지가 산다(M63) — `lead.run_all` 이 격리한다.
        from app.research import lead as _lead
        from app.research import subtasks as _subtasks
        side = "home" if team == game.get("home") else "away"
        mine = [t for t in _subtasks.split(game) if t.side == side]
        jobs = [_run_agent(
            game, side, fun, seen, facts, kick,
            tuple(game.get("langs") or ()),
            chain=search, net=net, pot=pot, subtask=t) for t in mine]
        live, bad = await _lead.run_all(jobs)
        # 🔴 **병합은 리드가 한다**(§3-1) — 같은 주장이면 독립 출처 수를 올린다
        merged = _lead.merge([{"name": t.name, "group": t.group,
                               "kinds": t.kinds,
                               "variables": got or []}
                              for t, (got, _n) in zip(mine, live,
                                                      strict=False)])
        agent_vars = merged["variables"]
        notes = [n for _g, n in live]
        if bad:
            # 🔴 **터진 하위를 이름으로 남긴다**(#3) — 깔때기에도 간다
            notes.append(f"🔴 하위 {len(bad)}개가 터졌다: "
                         + " · ".join(f"{type(e).__name__}: {e}"[:70]
                                      for e in bad))
            fun.drop(Reason.AGENT_CRASHED, "agent_vars", n=len(bad))
        # 🔴 **하위별 한 줄 + 합계**(§3-4) — 표 없이 "됐다"는 보고가 아니다
        rows = [{"name": t.name, "searched": t.budget.search_used,
                 "passed": t.budget.search_used,
                 "rejected": 0, "fetched": t.budget.fetch_used,
                 "cands": len(got or []), "verified": len(got or []),
                 "out": t.budget.out_used, "secs": 0.0}
                for t, (got, _n) in zip(mine, live, strict=False)]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **2차 보충 — 최대 1회**(§3-3 · M64)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 장부에서 `not_tried`·`empty` 인 유형군만 골라, **남은 예산**
        #  > (미사용 search/fetch/토큰) 안에서 해당 하위 과제를 **한 번** 다시
        #  > 돌린다(턴 6). 2차 뒤에도 비면 그대로 `gaps` 로 — **3차는 없다.**
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **1차 결과를 먼저 장부에 쓴다** — 실측 2026-10-06
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 `second_round` 가 **장부를 읽은 뒤**에 1차 결과를 썼다.
        #     🔴 그래서 2차 판정이 **빈 장부**를 보고 늘 네 칸 전부를 골랐다 —
        #     `found` 배선(§3-2)이 2차에 **아무 영향도 못 줬다.**
        #     (실측: `2차 보충 4칸 — A/… · B/… · C/… · D/…` — 한 팀 전부)
        #  🔴 쓰고 나서 읽는다. 그래야 *"찾은 칸은 건너뛴다"* 가 실제로 돈다.
        _lead.write_book(book, _book_parts(mine, live))
        keys = sorted({t.team_key for t in mine})
        again = _lead.second_round(book, [t.group for t in mine], keys)
        # 🔴 **쏠렸으면 그 도메인을 빼고 현지어로**(§4-2) — 2차 1회 안에서다.
        skew, skew_why = skewed_host(agent_vars)
        if skew:
            notes.append(skew_why)
            for t in mine:
                t.avoid_host = skew
                t.second = True
        left = _lead.second_budget(rows)
        if again and (left["search"] > 0 or left["out"] > 0):
            back = [t for t in mine if (t.group, t.team_key) in set(again)]
            jobs2 = [_run_agent(
                game, side, fun, seen, facts, kick,
                tuple(game.get("langs") or ()),
                chain=search, net=net, pot=pot, subtask=t) for t in back]
            live2, bad2 = await _lead.run_all(jobs2)
            got2 = _lead.merge([{"name": f"{t.name}(2차)", "group": t.group,
                                 "variables": g or []}
                                for t, (g, _n) in zip(back, live2,
                                                      strict=False)])
            agent_vars += got2["variables"]
            notes.append(f"🔴 **2차 보충 {len(back)}칸**(남은 예산 "
                         f"search {left['search']}·출력 {left['out']}) → "
                         f"변수 {len(got2['variables'])}줄"
                         + (f" · 터진 것 {len(bad2)}" if bad2 else ""))
            _lead.write_book(book, _book_parts(back, live2))
        elif again:
            notes.append(f"⚠️ 2차 보충을 **못 돌렸다** — 빈 칸 {len(again)}개가 "
                         f"남았는데 예산이 없다(남은 search {left['search']})")
        said_rows = _lead.funnel_lines(rows)
        notes += said_rows
        # 🔴 **로그에도 찍는다**(§3-4) — 카드는 긴 줄을 자르고,
        #    `tools/research_report.py` 는 로그에서 표를 읽는다.
        for line in said_rows:
            logger.info("[analyze] 하위 %s", line.strip())
        agent_note = " | ".join(notes)
        # 🔴 장부는 **위에서 이미 썼다**(2차 판정 전) — 여기서 다시 쓰면 2차가
        #    적은 `found` 를 1차 값으로 **되돌린다**.
        states.setdefault(f"에이전트:{team}", agent_note)
        if agent_vars:
            states.setdefault(_AGENT_KEY, [])
            states[_AGENT_KEY].extend(agent_vars)
        cat, cat_dropped = searchcells.catalog_cells(
            team=team, league=game.get("league") or "", day=day,
            game_id=game.get("game_id"), starts=kick, opponent=other,
            coach=coach, star=star,
            # 🔴 **종목을 넘긴다** — 안 넘기면 야구 전용 유형이 축구 경기에서
            #    돈다(실측 2026-10-03: `pitcher_state` 가 MLB 선수 페이지를 열었다)
            sport=game.get("sport") or "",
            # 🔴 사다리가 정한 기사 언어 — 없으면 현지어 템플릿이 전부 건너뛴다
            langs=tuple(game.get("langs") or ()),
            # 🔴 쪽을 따른다(2026-10-04) — 카탈로그 질의도 현지 표기를 쓴다
            local=my_local)
        # 🔴🔴 **카탈로그의 "템플릿 없음"은 이 경기의 사실이 아니다.**
        #
        #  ⚠️ 라이브 실측 2026-10-02: 유형 14종 × 팀 2 = **28줄**이 블록 1 에 쏟아졌고
        #     전부 같은 말이었다(*"검색 템플릿이 없다 — 구조 자료에서만 온다"*).
        #     그것은 **카탈로그의 성질**이고 이 경기에 대해 아무것도 말하지 않는다.
        #  🔴 지우지 않는다 — **한 줄로 묶어 센다**(조용한 0 금지는 "세라"는 뜻이지
        #     "스물여덟 줄로 적어라"는 뜻이 아니다).
        no_tpl = [w.split(":")[0] for w in cat_dropped if "템플릿이 없다" in w]
        if no_tpl:
            states.setdefault(
                f"카탈로그:{team}:템플릿없음",
                f"검색 템플릿이 없는 유형 {len(no_tpl)}종 — 구조 자료에서만 온다"
                f"({', '.join(sorted(set(no_tpl)))})")
        for why in cat_dropped:
            if "템플릿이 없다" in why:
                continue
            # 🔴 열쇠는 **유형 이름**이다 — 사유의 앞 60자를 열쇠로 쓰면 카드가 같은
            #    문장을 **두 번** 적는다(열쇠로 한 번, 값으로 한 번). 실측 2026-10-03:
            #      `카탈로그:El Salvador:pitcher_state: 묻지 않는다 — …
            #       : pitcher_state: 묻지 않는다 — … (이 유형이 보는 세포가 …)`
            #    ⚠️ `cat_dropped` 의 모든 줄이 `"{유형}: 사유"` 꼴이다(원본은
            #       `searchcells.catalog_cells`) — 그 앞머리를 열쇠로 쓴다.
            states.setdefault(f"카탈로그:{team}:{why.split(':')[0].strip()}", why)
        # 🔴 **명단을 먼저 만든다** — 앞선 세포들이 모은 사실에서 나온다.
        #    ⚠️ 카탈로그 세포가 **그 뒤에** 도는 까닭이 이것이다: 명단이 없으면
        #       명단 검사가 아무것도 막지 못한다(실측 2026-10-02 손흥민).
        squad = roster_of(facts, team)
        if squad:
            logger.info("[analyze] %s 명단 %d명 — 카탈로그 세포에 건다",
                        team, len(squad))
        else:
            states.setdefault(
                f"명단:{team}",
                "스쿼드 명단을 못 모았다 — 선수명 검사를 못 한다(사실은 soft 로 내려간다)")
        for cell in cat:
            cell.roster = squad
            cell.funnel = fun
            # 🔴 §3-2 — **같은 `Seen`** 을 건다(에이전트가 그것을 읽는다)
            cell.seen = seen
            bb = Blackboard()
            try:
                states[f"{team}:{cell.question.id.rsplit(':', 1)[-1]}"] = \
                    await cell.run(net, bb, search=search, scores=scores)
            except Exception as exc:                        # noqa: BLE001
                states[f"{team}:{cell.question.id.rsplit(':', 1)[-1]}"] = \
                    f"error {exc!r}"
                logger.warning("[analyze] 카탈로그 %s 실패: %r",
                               cell.question.id, exc)
                continue
            for qid, slot in bb.slots.items():
                facts.extend(slot.facts)
                # 🔴🔴 **독립 출처 수를 사유로 올린다**(기술 6). 같은 보도자료가
                #    여럿 와도 하나다 — 그 사실이 카드 블록 1 에 적힌다.
                #    ⚠️ 단독 출처는 **버리지 않는다** — 그렇다고 적는다(§11-3).
                if slot.source_note and "단독" in slot.source_note:
                    states.setdefault(f"출처:{qid}", slot.source_note)
            for qid, reason in bb.unknowns():
                states.setdefault(qid, reason)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **깔때기 ⑤ `facts`** — 세포들이 실제로 올린 사실 수
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `kept_date` 와 다를 수 있다 — 깊이 세포(공식 API)는 검증기를 안 걸고,
    #     같은 사실이 두 질문에 올라오기도 한다. 🔴 두 수가 다르면 그 차이 자체가
    #     진단이다(어디서 늘고 줄었는지).
    # ⚠️ v5 §8-5 에 `facts` 칸이 **없다** — §1 이 정규식 유형표를 버리는 것에
    #    넣었고 읽기 주체가 에이전트로 간다. 🔴 사실 수는 `fetched`(본문을 받은
    #    문서)와 뜻이 다르므로 **그 칸에 넣지 않는다** — 카드 머리줄이 따로 적는다.

    # ⚠️ `typed`·`variables` 는 **아직 안 쟀다** — 0 이라고 외치지 않는다
    fun.log("gather", judge=False)
    # 🔴 `states` 에 실어 보낸다 — `gather` 서명을 바꾸면 부르는 곳이 전부 따라야
    #    하고, 깔때기는 **보고용**이지 흐름의 입력이 아니다.
    states[_FUNNEL_KEY] = fun
    # 🔴 **장부를 카드로 넘긴다**(#3) — 어느 유형군이 비었나가 보여야 한다
    states["장부"] = book.line() if hasattr(book, "line") else str(book.cells)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **전송 실패를 상태 코드별로 적는다** — 사용자 지시 2026-10-06 ④
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `llm_unavailable` 건은 **HTTP 상태 코드별로 집계**해 보고.
    #
    #  ⚠️ 실측 2026-10-06: 깔때기가 `llm_unavailable 14` 를 적었는데 실제 전송
    #     실패는 **1건**이었다(나머지는 예산). 🔴 이 줄이 그 둘을 가른다 —
    #     429(속도)·5xx(서버)·응답없음(망)은 **고칠 곳이 다르다.**
    from app import solar as _solar
    states["전송"] = (_solar.http_fail_line()
                    + f" · Solar 동시 호출 {_solar.solar_concurrency()}"
                    + (" 🔴 **429 를 받아 낮췄다**" if _solar.SAW_429 else ""))
    return facts, states


def _has_official_standings(facts: list, team: str) -> bool:
    """🔴 그 팀의 **공식 순위 사실**이 이미 들어왔나.

    ⚠️ 이름으로 찾지 않는다 — 질문 id 의 접미사가 `standings` 인 사실이 곧 그것이다
       (`classify.TYPES_OF_SUFFIX` 가 같은 열쇠를 쓴다 · 사본 금지).
    """
    for f in (facts or []):
        qid = str(getattr(f, "question_id", ""))
        if ":standings" not in qid and not qid.startswith("standings"):
            continue
        who = str(getattr(f, "team", "") or "")
        v = f.value if isinstance(getattr(f, "value", None), dict) else {}
        if not who:
            who = str(v.get("team") or "")
        # 🔴 팀 칸이 비면 **리그 전체 표**다 — 그것도 공식 순위다
        if not who or who == team:
            return True
    return False


def _star_of(facts: list, team: str) -> str:
    """🔴 그 팀의 **핵심 선수 이름** — 검색어로 쓴다(사용자 기술 지시 2026-10-03).

    ⚠️ yaml 에 박지 않는다 — 핵심은 경기마다 바뀌고, 박으면 **빠진 선수**를 계속
       검색하게 된다(사용자 분석의 하메스·킨테로가 그 꼴이다).
    🔴 `classify._mark_top_scorer` 가 표시해 둔 **팀 최다 득점자**를 쓴다. 없으면
       빈 문자열이고 `{star}` 템플릿은 그대로 건너뛴다(사유가 남는다).
    """
    for f in facts:
        v = f.value if isinstance(getattr(f, "value", None), dict) else {}
        if not v.get("top_scorer"):
            continue
        if str(v.get("team") or "") != str(team or ""):
            continue
        got = str(v.get("player") or "").strip()
        if got:
            return got
    return ""


def depth_why(game: dict) -> str:
    """🔴🔴 **깊이가 0 인 까닭** — *"없다"* 와 *"못 만들었다"* 를 가른다.

    ══════════════════════════════════════════════════════════════════
    🔴 종전 한 줄이 **거짓이었다**(실측 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    ```
    "공식 깊이 소스가 없다 — 이 리그 어댑터에 `sources_context` 가 없다"
    ```

    ⚠️ MLB 어댑터에는 **있다.** `keymigrate` 가 열쇠를 `statsapi:849825` 로
       옮긴 뒤 `pk.isdigit()` 이 실패해 **빈 목록**을 냈을 뿐이다. 그 카드가
       *"어댑터에 없다"* 고 적었고, 그것을 읽은 사람은 **엉뚱한 곳을 고친다.**

    🔴 §8-6 — 두 경우의 **고칠 곳이 다르다**:

        어댑터가 없다      → 그 종목·리그를 아직 안 만들었다(만들 일)
        빈 목록을 냈다      → **그 열쇠로** 못 만들었다(열쇠/파서를 볼 일)
        열쇠가 없다        → 수집이 `ext_id` 를 안 적었다
    """
    from app.collect import ingest
    ext = str(game.get("ext_id") or "")
    league = str(game.get("league") or "")
    fn = ingest.context_of(league, ext)
    if not callable(fn):
        return (f"공식 깊이 소스가 **없다** — 리그 `{league}`·열쇠 `{ext or '없음'}` "
                f"로 고를 어댑터가 없거나 그 어댑터에 `sources_context` 가 없다")
    if not ext:
        return (f"공식 깊이를 못 걸었다 — 어댑터는 있는데 **경기 열쇠가 없다**"
                f"(수집이 `ext_id` 를 안 적었다)")
    return (f"공식 깊이 소스가 **빈 목록**이다 — 어댑터 "
            f"`{getattr(fn, '__module__', '?')}` 는 있는데 열쇠 `{ext}` 로 "
            f"주소를 못 만들었다(§8-1 열쇠 꼴·파서를 보라)")


def xi_state(xi: dict, game) -> str:
    """🔴🔴 **분석 과정 5단계** — 라인업을 얼마나 아는가. `확정` · `예상` · `없음`.

    사용자 분석 과정 10단계 그림 2026-10-03:

    ```
    5. 라인업 상태 → 상한        확정 1.0 / 예상 0.85 / 없음 0.8
    ```

    우리 자료의 세 상태를 그림의 세 칸에 이렇게 맞췄다(맞춤은 yaml 에 적어 뒀다):

    | 칸 | 우리 자료 |
    |---|---|
    | `확정` | 공식 발표 라인업이 **양 팀 다** 있다(`lineup` 세포가 받은 것) |
    | `예상` | XI 가 **양 팀 다** 있는데 하나라도 기준(직전 경기·예상)이다 |
    | `없음` | 한 팀이라도 XI 가 **없다** |

    ══════════════════════════════════════════════════════════════════
    🔴 종전 함수에 **잠복 결함**이 있었다
    ══════════════════════════════════════════════════════════════════

    ```python
    if str((got or {}).get("lineup_kind")) != "confirmed":   # 종전
    ```
    ⚠️ `_xi` 가 적는 칸은 `confirmed`(불리언)이고 **`lineup_kind` 라는 칸은 없다.**
       그래서 이 검사는 **언제나 False** 였다 — 확정 XI 를 두 팀 다 받아도 상한이
       **절대 안 풀렸다.** 🔴 fail-closed 라 수가 틀리지는 않았지만, *"확정이면
       1.0"* 이라는 규칙 자체가 **한 번도 동작한 적이 없었다.**
    """
    if not xi:
        return "없음"
    teams = [getattr(game, "home", ""), getattr(game, "away", "")]
    got = [xi.get(t) if isinstance(xi, dict) else None for t in teams]
    if any(not g or not (g or {}).get("players") for g in got):
        return "없음"
    # 🔴 `_xi` 가 적는 칸이다 — 이름을 여기서 다시 짓지 않는다
    sure = [bool((g or {}).get("confirmed")) for g in got]
    state = ("양쪽확정" if all(sure) else
             "한쪽확정" if any(sure) else "양쪽예상")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§6-5 — 발표됐으나 미검증이면 "미검증"으로 적는다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `verified` 칸이 **없는 자료**가 있다(옛 세포가 적지 않았다). 🔴 그때
    #     *"검증됐다"* 로 보지 않는다 — 없는 것은 **모르는 것**이고, 모르면
    #     한 단계 아래가 fail-closed 다.
    #  🔴 확정이 하나도 없으면(`양쪽예상`) 붙이지 않는다 — **발표된 적이 없는**
    #     XI 를 *"미검증"* 이라 적으면 그것이 거짓 사유다(§8-6).
    if state != "양쪽예상" and not all(
            bool((g or {}).get("verified")) for g, ok in zip(got, sure, strict=True)
            if ok):
        return state + survive.UNVERIFIED_MARK
    return state


def followup_sources(game: dict, facts: list) -> list:
    """🔴 **이미 모은 사실이 가리키는 다음 주소**. 어댑터가 `sources_followup` 을
    가질 때만이다 — 없는 종목에 있는 척하지 않는다.

    ⚠️ `depth_sources` 와 같은 규약으로 어댑터를 고른다(리그 → ext_id 접두).
    """
    from app.collect import ingest
    ext = str(game.get("ext_id") or "")
    if not ext:
        return []
    fn = ingest.followup_of(game.get("league") or "", ext)
    if not callable(fn):
        return []
    try:
        return list(fn(facts, ext))
    except Exception as exc:                            # noqa: BLE001
        logger.warning("[analyze] 2차 깊이 실패: %r", exc)
        return []


#: 🔴 **어댑터가 흘린 모양**을 센다(§8-3 · 조용한 0 금지 #3).
#   ⚠️ 비워 두지 않는다 — 쌓이면 그 어댑터가 계약을 어긴 것이다.
ROSTER_SHAPE_DROPPED: list[str] = []


def roster_of(facts: list, team: str) -> tuple[str, ...]:
    """🔴 그 팀의 **스쿼드 명단** — *이 경기에서 모은 사실*에서 만든다.

    사용자 설계 2026-10-02: *"fotmob 스쿼드 명단과 기사 속 선수명 대조"*.

    ⚠️ **DB `players` 표를 쓰지 않는다** — 실측 2026-10-02: 그 표에 10줄뿐이다
       (로스터 주기가 아직 안 채웠다). 그런데 경기 페이지는 **그 경기의 스쿼드**를
       바로 준다(`:player`·`:baseline` 사실) — 더 정확하고 더 신선하다.
    🔴 못 모았으면 **빈 tuple** 이고, 그러면 명단 검사가 *"못 쟀다"* 로 돈다
       (통과시키는 것이 아니다 — `ids.squad_check` 가 soft 로 내린다).
    """
    out: list[str] = []
    for f in facts:
        if str(getattr(f, "team", "") or "") != team:
            continue
        val = f.value if isinstance(f.value, dict) else {}
        for key in ("player", "player_name", "name"):
            got = str(val.get(key) or "").strip()
            if got and got not in out:
                out.append(got)
        # 🔴 기준 XI·확정 XI 는 **목록**으로 온다.
        #    ⚠️ `squad`(선발+교체 26명)를 **먼저** 넣는다 — 선발 11명만 쓰면 교체
        #       명단 선수가 기사에 나올 때 *"남의 팀"* 으로 멀쩡한 사실을 버린다
        #       (실측 2026-10-03: 명단이 11명이었다).
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`list[str]` 만 받는다** — v5 §8-3 (사용자 결정 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-04(게이트2 2판): NPB 어댑터가 `players` 에 **dict**
        #     (이름 → 주소)를 넣어 `list + dict` 가 터졌고 **경기 전체가 죽었다.**
        #  🔴 터지지도 **주워 쓰지도** 않는다 — 주워 쓰면(dict 의 키를 꺼내면)
        #     어댑터가 모양을 흘린 사실이 **아무 데도 안 남는다**(#3).
        #     ⚠️ 그러면 다음 어댑터가 또 흘리고 아무도 모른다.
        for key in ("squad", "players"):
            said = val.get(key)
            if said is None:
                continue
            if not isinstance(said, list) or \
                    any(not isinstance(x, str) for x in said):
                # 🔴 **거부하고 센다** — 고칠 곳은 그 어댑터다(§8-3)
                ROSTER_SHAPE_DROPPED.append(
                    f"{team}·{key}={type(said).__name__}")
                logger.warning(
                    "[analyze] 🔴 `%s` 칸이 **list[str] 이 아니다**(%s) — "
                    "어댑터가 고유 모양을 밖으로 냈다(§8-3). 그 칸을 버린다",
                    key, type(said).__name__)
                continue
            for nm in said:
                nm = nm.strip()
                if nm and nm not in out:
                    out.append(nm)
    return tuple(out)


def context(facts: list) -> dict:
    """순위표 사실 + **§5-c 가 쓰는 보조 신호**를 한 묶음으로.

    🔴 이 함수가 전에 **시험 파일 안에** 있었다(`tests/.../_collect`). 그러면 운영이
       그 조립을 안 한다 — 시험만 초록인 자리였다. 원본을 `app/` 으로 옮긴다.
    """
    out: dict = {}
    #: 🔴 장소별 득점 조각(`:runs_month`) — **달마다 하나씩** 온다. 합치는 것이 여기다.
    parts: list[dict] = []
    for f in facts:
        suffix = str(f.question_id).rpartition(":")[2]
        val = f.value if isinstance(f.value, dict) else {}
        if suffix == "standings" and val:
            out.update(val)
        elif suffix == "runs_month" and val.get("venue_rows_part"):
            parts.append(val)
        elif suffix == "starter" and val.get("team"):
            # 🔴 **선발 보정의 입력**(딥서치 2026-10-03 · A). 홈/원정으로 가르는 것은
            #    `classify.starters_for` 다 — 여기는 모으기만 한다(경기를 모른다).
            out.setdefault("starter_rows", []).append(dict(val))
        elif suffix == "h2h" and val:
            out["h2h_window_avg_goals"] = val.get("window_avg_goals")
            # 🔴 §8-3 정본 — `count`(종전 `window_games` 는 fotmob 고유 칸)
            out["h2h_window_games"] = val.get("count")
        elif suffix == "form" and val.get("recent_avg_goals") is not None:
            # 🔴 §5-c-1 ③ 은 *"한쪽"* 최근 평균이다 — 둘 중 **큰** 쪽을 본다
            out["recent_avg_goals"] = max(out.get("recent_avg_goals") or 0.0,
                                          float(val["recent_avg_goals"]))
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **팀별로도 담는다** — 지시 ④ (2026-10-05)
            # ══════════════════════════════════════════════════════════
            #
            #  > 양 팀 최근 평균 득점 **합이 4 이상**이거나 **한쪽 평균 3 이상**
            #
            #  ⚠️ 최댓값만 담으면 **합을 못 센다**. 🔴 실측 pn7: 2.8 + 3.4 = 6.2
            #     였는데 난타전 시나리오가 없어 `언더 3.5` 가 1.0 이 됐다.
            #  🔴🔴 **총득점이 아니라 팀 득점이다** — 결정 2026-10-05.
            #     ⚠️ 실사고: 여기 `recent_avg_goals`(경기 총득점)를 담고
            #        난타전이 **두 팀 것을 더해** 3.2+2.8=6.0 을 봤다 —
            #        총득점을 두 번 세어 거의 모든 경기가 난타전 필수였다.
            #     🔴 못 재면 **안 담는다**(#3) — 0 을 넣으면 면제된다.
            who = str(f.team or getattr(f, "team", "") or "")
            scored = val.get("recent_scored_avg")
            if who and scored is not None:
                out.setdefault("avg_goals_by_team", {})[who] = float(scored)
            elif who:
                out.setdefault("avg_goals_missing", []).append(who)
    if parts:
        out.update(_merge_runs(parts))
    return out


def _merge_runs(parts: list[dict]) -> dict:
    """달별 장소 득점 조각 → `venue_rows` · `venue_averages` · 총점 기준선.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 (실측 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    야구는 포아송 격자가 **한 번도 선 적이 없다.** 순위표에 득점이 없어서다
    (`goals_for = None`). 그 결과 시나리오가 템플릿 둘(홈·거울상)뿐이고 생존이
    `0.0/0.5/1.0` 세 값만 가능해, §6-b 가 이름을 적는 자리(1.0)가 거의 안 나왔다.
    사람이 손으로 한 분석은 시나리오 **다섯** · 승 생존 **0.85** 였다.

    🔴 자료는 월간 일정의 스코어다 — **지어낸 수가 아니다**(`npb.parse_month_runs`).
    ⚠️ 이 함수는 **합치기만** 한다. 어느 달을 읽을지는 어댑터·yaml 이 정한다.
    """
    box: dict[tuple[str, str], dict] = {}
    months: list[str] = []
    games = 0
    for part in parts:
        months.append(str(part.get("month") or "?"))
        games += int(part.get("games") or 0)
        rows = part.get("venue_rows_part") or {}
        for side in ("home", "away"):
            for r in rows.get(side) or []:
                key = (side, str(r.get("team") or ""))
                cur = box.setdefault(key, {"team": r.get("team"), "played": 0,
                                           "wins": None, "losses": None,
                                           "draws": None, "goals_for": 0,
                                           "goals_against": 0, "goal_diff": 0})
                cur["played"] += int(r.get("played") or 0)
                cur["goals_for"] += int(r.get("goals_for") or 0)
                cur["goals_against"] += int(r.get("goals_against") or 0)
                cur["goal_diff"] = cur["goals_for"] - cur["goals_against"]
    rows = {"home": [v for (s, _), v in box.items() if s == "home"],
            "away": [v for (s, _), v in box.items() if s == "away"]}
    if not rows["home"] or not rows["away"]:
        return {}
    avgs = league.venue_averages(rows["home"], rows["away"])
    if avgs is None:
        return {}
    allr = rows["home"] + rows["away"]
    out = {"venue_rows": rows, "venue_averages": avgs,
           # 🔴 **리그 평균·총점 기준선은 `league.py` 가 원본이다** — 여기 셈을
           #    다시 적지 않는다(사본 금지). `avg_goals` 는 `gf/(gp/2)` 라
           #    장소 줄을 합쳐 넣으면 경기당 총득점이 된다.
           "league_avg_goals": league.avg_goals(allr),
           "total_baseline": league.baseline_total(allr),
           "venue_window": f"{min(months)}~{max(months)} · {games}경기"}
    logger.info("[analyze] 장소별 득점 합계 — 홈 평균 %.3f · 원정 평균 %.3f "
                "(%s)", avgs["home"], avgs["away"], out["venue_window"])
    return out


def grid(standings: dict | None, game) -> dict | None:
    """포아송 스코어 격자. 🔴 못 만들면 `None` — 무게가 §5-d 로 내려간다."""
    avgs = (standings or {}).get("venue_averages")
    if not avgs:
        return None
    hr = scenarios._venue_row(standings, "home", game.home)
    ar = scenarios._venue_row(standings, "away", game.away)
    if hr is None or ar is None:
        return None
    # 🔴🔴 **변수가 λ 에 닿는 자리**(딥서치 2026-10-03 · A). 선발 보정을 넘긴다 —
    #    `scenarios._grid` 도 **같은 함수**를 부른다(사본 금지).
    exp = league.expected_goals(hr, ar, avgs,
                               starters=classify.starters_for(standings, game))
    if exp is None:
        return None
    for why in (exp.get("starter_notes") or []):
        logger.info("[analyze] 선발 보정 — %s", why)
    return league.score_probabilities(exp["home"], exp["away"])


# ══════════════════════════════════════════════════════════════════
# 카드 — 사용자 출력 블록 **열 개**(docs/fable/output_spec.md)
# ══════════════════════════════════════════════════════════════════


@dataclass
class Card:
    """블록 열 개. 🔴 **못 만든 블록은 사유를 들고 있어야** 한다."""

    game: object = None
    #: 🔴🔴 **킥오프**(UTC · tz 있는 `datetime`) — 지시 ③ 2026-10-05.
    #   ⚠️ 실사고 2026-10-05(pn12): 이 칸이 **없어서** `survive.run` 이
    #      `getattr(card, "kickoff", None)` 으로 늘 `None` 을 받았다. 머리글은
    #      *"이미 시작"* 을 찍는데 결론 줄은 `소액` 을 적었다 — 지시 ③ 이
    #      조용히 꺼져 있었다. 🔴 **칸으로 든다**(없는 칸은 숨는다).
    kickoff: object = None
    #: 🔴🔴 **경기 열쇠**(`ext_id`) — 비용 원장이 한 경기로 모이게 한다
    #   (⑫ · 2026-10-05). ⚠️ `Game`·`Card` 어디에도 없어서 단계 3·4 가
    #   `f"{home}|{away}"` 를 적었고 둘이 비면 `'|'` 가 남았다 — 그 행은
    #   **어느 경기인지 알 수 없다**. 🔴 `kickoff` 과 같은 길로 **칸에 든다**.
    match_key: str = ""
    #: 🔴🔴 **깔때기** — 어느 칸에서 0 이 됐나(사용자 기술 지시 2026-10-03).
    #   ⚠️ 블록 1 **맨 위**에 적는다 — 스무 줄 사유 아래 묻히면 못 본다.
    funnel: object = None
    limits: list[str] = field(default_factory=list)      # 1 자료 한계 고백
    xi: dict = field(default_factory=dict)               # 2 기준 XI
    form: dict = field(default_factory=dict)             # 3 폼
    variables: list = field(default_factory=list)        # 4 뒤집는 변수
    #: 🔴 **배경과 미결정을 따로** 들고 있다 — 섞으면 고칠 곳을 못 찾는다(§4).
    #  배경은 *규칙이 "방향 없음"으로 판단한 것*, 미결정은 *자료가 없어 못 판단한 것*.
    background: list = field(default_factory=list)
    undecided: list = field(default_factory=list)
    hypotheses: list = field(default_factory=list)       # 5 가설
    scenarios: object = None                             # 6 시나리오
    survival: object = None                              # 7·8·9 보드·결론·방향
    triggers: object = None                              # 10 방아쇠
    states: dict = field(default_factory=dict)
    #: 🔴 포아송 `λ` 두 수. **격자를 다시 만들 열쇠다** — 채점이 그때의 확률을 묻는다
    lam: dict = field(default_factory=dict)
    #: 🔴🔴 **v5-A §7** — 이 경기에 **실제로 밟은 판정 순서**. ⚠️ 반증이 꺼져
    #  있으면 그 칸이 빠진다(그 사실이 카드에 적힌다).
    judge_steps: tuple = ()
    #: 🔴 §4 반증 결과(`judgeorder.Outcome`). ⚠️ `None` 이면 **안 돌았다**.
    redteam: object = None

    @property
    def insufficient(self) -> bool:
        return bool(self.scenarios is None or self.scenarios.insufficient)

    @property
    def incomplete(self) -> bool:
        """🔴🔴 **§6-2 `scenario_incomplete` — 카드 금지.**

        ⚠️ `insufficient`(§7 R5)와 **다른 상태**다: R5 는 *"변수가 모자라
           시작도 못 했다"* 이고, 이쪽은 *"변수는 있는데 **반대 시나리오를 만들 수
           없다**"* 다. 🔴 섞으면 고칠 곳이 사라진다(§8-6).
        """
        return bool(getattr(self.scenarios, "incomplete", False))

    @property
    def incomplete_why(self) -> list[str]:
        return list(getattr(self.scenarios, "incomplete_why", []) or [])


#: 🔴🔴 **구조 칸** — 어댑터가 주는 것들. 지시서 §3-3 이 이름을 댔다.
#
#  > 구조 자료가 비면 `AgentInput.gaps` 에 그 칸(**순위·최근 5경기·상대전·
#  > XI·결장**)을 넣고, 시스템 프롬프트에 *"gaps 의 구조 칸은 카탈로그 유형보다
#  > **먼저** 찾아라"* 를 둔다. — 지시서 §3-3
#
#  ⚠️ 미등록 리그는 어댑터가 **아무것도 안 준다** — 그 사실을 에이전트에게
#     **이름으로** 넘겨야 그가 찾는다(실측: 라네로스는 어댑터가 없다).
#  🔴 종목이 칸을 정한다 — 야구에 `xi` 를 묻지 않는다(선발 투수가 그 자리다).
STRUCT_CELLS: dict = {
    "soccer": ("standings", "last5", "h2h", "xi"),
    "baseball": ("standings", "last5", "h2h", "starter"),
    "hockey": ("standings", "last5", "h2h", "xi"),
}

#: 🔴 그 칸이 **채워졌는지** 어느 사실로 보나. ⚠️ 이름을 두 곳에 적지 않는다.
_STRUCT_MARK: dict = {
    "standings": ("standings", "rank"),
    "last5": ("form", "last5"),
    "h2h": ("h2h", "head_to_head"),
    "xi": ("lineup", "baseline", "squad", "players"),
    "starter": ("starter", "pitcher", "probable"),
}


def gaps_of(facts: list, *, sport: str = "soccer") -> list[str]:
    """🔴 **빈 구조 칸들** — 에이전트에게 *"이것부터 찾아라"* 로 넘긴다(§3-3).

    ⚠️ **있는 것을 빈 것으로 적지 않는다**(#3 의 반대쪽) — 어댑터가 준 칸은
       빼야 에이전트가 **중복으로 안 찾는다**(예산이 두 배가 된다).
    """
    want = STRUCT_CELLS.get(str(sport), STRUCT_CELLS["soccer"])
    said = []
    for f in (facts or []):
        qid = str(getattr(f, "question_id", "") or "")
        val = getattr(f, "value", None)
        said.append(qid.lower())
        if isinstance(val, dict):
            said += [str(k).lower() for k in val]
    blob = " ".join(said)
    return [c for c in want
            if not any(m in blob for m in _STRUCT_MARK.get(c, (c,)))]


#: 🔴 **번호만** 온 항목 — `R4` · `R4, R10` · `['R1']` 같은 것.
#  ⚠️ 실측 pn10: 카드 가설이 `이긴다면: R1` 이었다 — 지시 ②가 요구한 것은
#     *"가설을 문장으로"* 다. 번호를 문장 자리에 찍으면 **독자가 읽을 것이 없다.**
_ID_ONLY = re.compile(r"^[\s\[\]'\"(),.·]*(?:R\d+[\s\[\]'\"(),.·]*)+$")


def is_sentence(said: str) -> bool:
    """🔴 그 항목이 **문장**인가 — 번호 나열이면 아니다(지시 ②).

    ⚠️ 문장 판정을 길이로 하지 않는다 — `R10, R12, R9` 는 10자가 넘는다.
    🔴 **번호 말고 아무것도 없으면** 문장이 아니다. 그 하나만 본다(과하게
       까다롭게 굴면 쓸 만한 짧은 문장까지 버린다).
    """
    return bool(str(said or "").strip()) and not _ID_ONLY.match(str(said))


def hypo_sentences(said: dict, *, side: str) -> tuple[list, list]:
    """🔴 DeepSeek `hypotheses` → `(이긴다면, 무너지면)` — 지시 ② (2026-10-05).

    🔴🔴 **열쇠는 자리다**(`home`·`away`) — 팀 이름이 아니다.
       ⚠️ 종전엔 팀 이름으로 찾았다. 그러면 두 가지가 동시에 샌다:
         ① §8-1 — 이름을 인자로 받는 자리가 **하나 늘어난다**(계약이 센다)
         ② 모델이 이름을 **달리 적으면**(`Portugal` ↔ `Portugal (POR)`) 가설이
            통째로 빈다 — 그런데 그 빔은 *"가설이 없다"* 와 구별되지 않는다
       🔴 자리는 **우리가 정하는 두 글자**다. 모델이 바꿀 여지가 없다.
    🔴 자리가 안 맞으면 **빈 목록**이다 — 다른 팀 문장을 붙이지 않는다.
    🔴 **번호만 온 것은 버린다**(`is_sentence`) — 버린 수는 호출부가 센다
       (조용히 지우지 않는다 · #3).
    """
    box = (said or {}).get(str(side)) or {}
    return ([str(x) for x in (box.get("reasons") or []) if is_sentence(x)],
            [str(x) for x in (box.get("breaks") or []) if is_sentence(x)])


def var_line(c, *, form: dict | None = None) -> str:
    """🔴🔴 **변수 한 줄** — 무슨 사실인가 + 인용 + 규칙이 본 것.

    ══════════════════════════════════════════════════════════════════
    🔴 실측 2026-10-05 — **사실이 카드에 없었다**
    ══════════════════════════════════════════════════════════════════

    ```
    R4 [absence·home·soft] §3 에이전트 + §5 검증층 통과 · 등급 `local`(무게 1)
                           · 힌트 `away` → **코드가 정한 쪽** `home`(§5-4)
    ```

    ⚠️ 유형·방향·등급·힌트는 있는데 **무슨 결장인지**가 없다 — 독자가
       *"호날두가 왜 빠지나"* 를 **URL 을 열어야** 알았다.
    🔴 종전 코드는 `_clip(why) if why else _clip(text)` 였다 — **`or` 로 하나만**
       찍었다. ⚠️ 그런데 바로 위 주석은 *"둘을 **함께** 적는다"* 라고 적혀
       있었다 — **주석이 거짓이었다**(이 저장소가 경계하는 꼴이다).

    🔴 순서가 뜻이다: **사실이 먼저**(독자가 읽는 것) · 규칙 사유는 뒤(감사).
    """
    text = " ".join(str(getattr(c, "text", "") or "").split())
    why = " ".join(str(getattr(c, "why", "") or "").split())
    # 🔴 **묶음이면 그렇다고 적는다** — 지시 ⑧ (실측 2026-10-05).
    #    ⚠️ 한 변수가 여러 사실을 담으면 방향·hardness 가 무엇에 붙었는지
    #       알 수 없다. 버리지 않고 **표시**한다(#3).
    lump = " 🔴 **여러 사실 묶음**(한 변수 = 한 사실이 아니다)" \
        if classify.is_lump(text) else ""
    # 🔴 **폼 기록과 어긋나면 적는다**(지시 ⑨) — 어느 쪽이 맞는지는 고르지 않는다.
    #    ⚠️ 폼은 **인자로** 받는다. `Classified` 에 `last5` 칸이 **없어서**
    #       `getattr(c, "last5", [])` 는 늘 빈 목록이었다 — `Card.kickoff` 와
    #       같은 함정이다(실측 2026-10-05).
    box = dict((form or {}).get(str(getattr(c, "team", "") or "")) or {})
    clash = classify.clash_with_form(text, box.get("last5") or [])
    if clash:
        lump += " · " + clash
    if text and why:
        return f"{_clip(text, 190)} · {_clip(why, 110)}{lump}"
    return _clip(text or why, 190) + lump


def _of(game, field: str) -> str:
    """🔴 `game` 이 **dict 로도 온다**(`scheduler._rerun_card`) — 둘 다 읽는다.

    ⚠️ `getattr` 만 쓰면 dict 경로에서 **조용히 빈칸**이 되고, 그러면 형식이
       `unknown` 으로 떨어진 까닭이 *"자료가 없다"* 로 잘못 읽힌다(#3).
    """
    if isinstance(game, dict):
        return str(game.get(field) or "")
    return str(getattr(game, field, "") or "")


def build(facts: list, game, *, board=None, states: dict | None = None,
          kickoff=None, match_key: str = "") -> Card:
    """사실 → 카드. 🔴 **여기서 LLM 이 말하지 않는다**(§17-c).

    🔴 `kickoff` 은 **방아쇠의 "언제 보나"를 시계 시각으로** 적는 데 쓴다
       (분석 과정 10단계 *"확인 항목 첨부"* · 사용자 글 `KST 10:00 XI`).
       ⚠️ 없으면 상대 시각(`T-70분`)만 적는다 — 지어내지 않는다.
    """
    card = Card(game=game, states=dict(states or {}), kickoff=kickoff,
                match_key=str(match_key or ""))
    # 🔴 깔때기는 **사유가 아니다** — 사람이 읽는 줄과 섞이면 블록 1 이 깨진다
    fun = card.states.pop(_FUNNEL_KEY, None) or _funnel.Funnel()
    items = classify.classify_facts(facts, game)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **게이트 2 — 에이전트 변수가 판정층에 닿는다**(§1)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > §1: *"**검증층을 통과한 변수만 변수**이고, 판정층이 계산한 등급만
    #  > 등급이다."*
    #
    #  ⚠️ `gather` 가 §5 를 지난 변수를 `states` 에 실어 보낸다 — 여기서 **규칙
    #     경로 변수와 같은 목록**에 넣는다. 🔴 그래야 시나리오·생존이 그것을 쓴다.
    #  🔴 섞는 것이 맞다: §1 은 두 경로를 가르지 않는다. 어디서 왔는지는
    #     `why` 가 말한다(`§3 에이전트 + §5 검증층 통과`).
    from_agent = list(card.states.pop(_AGENT_KEY, None) or [])
    if from_agent:
        items = list(items) + from_agent
        logger.info("[analyze] §3 에이전트 변수 %d개를 판정층에 넣었다",
                    len(from_agent))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **깔때기 ⑥⑦** — `typed` 와 `variables`(사용자 기술 지시 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > typed:    사실은 있는데 **유형 판정 규칙이 없거나 좁다**
    #  > variables: 유형은 붙었는데 **방향이 없다**(팀 귀속 불명 등)
    #
    #  ⚠️ 이 둘을 가르는 것이 요점이다. `facts 9 → typed 0` 이면 **유형 규칙표**를
    #     고쳐야 하고, `typed 9 → variables 0` 이면 **방향 규칙·귀속**을 고쳐야 한다.
    #     둘을 한 칸으로 세면 어느 쪽인지 알 수 없다.
    #  🔴 `is_variable` 이 **유형+방향이 둘 다 선** 것이다(`classify.Classified`).
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §8-5 — `agent_vars` / `verified_vars`**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ §3 에이전트가 **아직 없다**(적용 순서: §8 → §2 → §3). 그 사이 v4 규칙
    #     경로가 도므로, 그 경로의 두 수를 같은 뜻의 칸에 넣는다:
    #
    #       유형이 붙은 것      → `agent_vars`   (= 변수 **후보**)
    #       방향까지 선 것      → `verified_vars`(= **승격된** 변수)
    #
    #  🔴 §3 이 오면 `agent_vars` 는 에이전트 출력이 되고 `verified_vars` 는 §5
    #     여섯 검사를 지난 것이 된다 — **칸의 뜻은 그대로**이고 채우는 쪽이 바뀐다.
    fun.set("agent_vars", sum(1 for c in items if c.type))
    fun.set("verified_vars", sum(1 for c in items if c.is_variable))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **떨어진 것 하나하나의 사유** — 사용자 수정 ④ (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `typed→variables` 탈락 사유 로그: **17건 각각** 왜 변수가 안 됐는지
    #  > (팀 귀속 없음 / 방향 규칙 없음 / 날짜 없음) 한 줄씩. 🔴 이게 없으면
    #  > **다음 단계 수정이 추측이 된다.**
    #
    #  ⚠️ 실측 2026-10-04: `typed 20 → variables 3` 인데 카드는 **7줄**만 적었다
    #     (미결정만 보였다). 나머지 10건은 `background` 로 **조용히** 갔다 —
    #     그쪽은 *"규칙이 방향 없음으로 판단했다"* 라서 카드가 줄을 안 만든다.
    #  🔴 세 갈래를 **이름으로** 가른다. 고칠 곳이 셋 다 다르다:
    #     `유형 없음` → §4 유형 판정표 · `방향 없음` → §4 방향 규칙 ·
    #     `팀 귀속 없음` → `side_of`·이름표 · `미결정` → 수집(자료가 없다)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **탈락은 사유 코드별 개수로** — v5 §8-5·§8-6
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ v4 는 **문장**을 쌓았다. 실측 2026-10-04 에 그 줄이 **열일곱 개**가 돼
    #     카드를 덮었고, *"어느 사유가 몇 건인지"* 는 세어 봐야 알았다.
    #  🔴 §8-5 는 **개수**를 요구하고 §8-6 은 **enum** 을 요구한다 — 문장을
    #     지어 넣으면 거짓 사유가 된다(실사고 2026-10-03 *"창 밖"*).
    #  ⚠️ 사람이 읽을 줄은 `reasons.SAY` 하나가 짓는다(여기서 짓지 않는다).
    for c in items:
        if c.is_variable:
            continue
        if c.undecided:
            got = Reason.INSUFFICIENT
        elif not c.type:
            # 🔴 §4 유형 판정표가 못 붙였다 — §1 이 버리기로 한 그 자리다
            got = Reason.AGENT_ZERO
        elif c.team is None:
            got = Reason.SIDE_MISMATCH
        elif c.direction is None:
            got = Reason.H2H_ZEROED if c.type == "h2h_pattern" \
                else Reason.STALE_SAMPLE
        else:
            got = Reason.SCENARIO_INCOMPLETE
        fun.drop(got, "verified_vars")
    fun.log("build")
    card.funnel = fun
    st = context(facts)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **경기 형식을 구조 사실에 넣는다** — 지시서 §3-3 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 it7(인도네시아–태국 **결승**): `games.round_note` 가 `None` 이라
    #     형식이 `unknown` 이었고, 90분 무승부 필수형(`require_draw`)이 *"강제하지
    #     않는다"* 로 지나갔다. 🔴 그런데 경기 페이지는 `"roundName":"final"` 을
    #     **명시**하고 있었다 — 읽지 않은 것이다(실측으로 받아 확인했다).
    #  🔴 사실이 형식을 주면 **그쪽이 이긴다**(`standings.match_format`) —
    #     라운드 표기는 그것이 없을 때의 재료다.
    #  🔴 **조용한 unknown 을 만들지 않는다**(#3) — 왜 그 형식인지 사유로 남긴다.
    if not st.get("match_format"):
        _fmt, _fmt_why = scenarios.match_format(
            round_note=_of(game, "round_note"), competition=_of(game, "league"))
        st["match_format"] = _fmt
        card.states.setdefault("§3-3 형식", _fmt_why)
    card.variables = [c for c in items if c.is_variable]
    card.background = [c for c in items if not c.is_variable and not c.undecided]
    card.undecided = [c for c in items if c.undecided]
    card.hypotheses = classify.hypotheses(items, game)
    card.xi = _xi(facts)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **XI 를 변수로 바꾼다** — 지시서 §3-1 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 it4: XI 를 **이름 목록으로만** 들고 있었다. 태국 5백·에이스
    #     벤치가 변수로 서지 않아 *"버티기·역습 → 저득점"* 신호를 놓쳤다.
    #  🔴 **코드가 만든다**(리드·에이전트 아님) — 재현 가능해야 한다.
    for _team, _box in (card.xi or {}).items():
        for _row in classify.xi_variables(
                team=str(_team), formation=_box.get("formation"),
                players=_box.get("players") or [],
                url=str(_box.get("source_url") or _box.get("from_match") or ""),
                confirmed=bool(_box.get("confirmed")),
                last_xi=_box.get("last_xi") or (),
                bench=_box.get("bench") or (),
                out_last=_box.get("out_last") or ()):
            states.setdefault(_AGENT_KEY, [])
            states[_AGENT_KEY].append(_row)
    card.form = _form(facts, st)
    probs = grid(st, game)
    card.lam = dict(probs.get("lam") or {}) if probs else {}
    sc = scenarios.generate(items, game, standings=st, board=None)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **단계 3(DeepSeek 가설·시나리오)을 잇는다** — 지시 ②③ (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-05: `hypo.run` 이 **아무 데서도 안 불렸다** — 단계 3 이
    #     통째로 미배선이었고, 카드 시나리오는 전부 **템플릿**이었다.
    #     🔴 `Hypothesis.claim_by` 가 *"§5-e L6 미배선"* 이라 **적혀 있었다** —
    #     그 자리가 여기다.
    #  🔴 지시 ③: *"카드 시나리오 = DeepSeek 시나리오. 각 시나리오에
    #     `driver_vars` 번호와 `mechanism` 문장을 출력. 템플릿 시나리오는 **코드
    #     필수형 보강일 때만**, `added_by:code` 표시와 함께."*
    #  ⚠️ 장애·꺼짐이면 **템플릿으로 돈다**(M45) — 그 사실을 사유로 남긴다.
    card.ds = _run_hypo(card, game, items, st, sc)
    card.scenarios = sc
    # 🔴 v5 §8-5 — `scenarios` 칸.
    #    ⚠️ 종전엔 `insufficient` 면 **0 을 적었다**. 🔴 이제 R5 는 등급 금지만
    #       뜻하고 시나리오는 만들어진다(사용자 규칙 2026-10-06) — 만든 수를
    #       그대로 적는다. 0 을 적으면 깔때기가 **거짓말**을 한다.
    fun.set("scenarios", len(sc.drafts or []))
    if sc.insufficient:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§7-5 — R5 를 선언할 자격이 있나**
        # ══════════════════════════════════════════════════════════════
        #
        #  > **사다리 2단계 이상 · 도구 호출 6회 이상**을 실제로 돈 로그가 있을
        #  > 때만 R5 자료 부족을 선언한다. 그 전에 선언하면
        #  > `premature_insufficient` 실패.
        #
        #  ⚠️ 실측 2026-10-02(중국 vs 팔레스타인): 사실 6건 · 변수 0건으로
        #     *"자료 부족"* 을 적었다. 🔴 그런데 자료 주소는 `ext_id` 에 있었고
        #     깊이 라우팅이 안 돌아 **아예 안 찾은** 것이었다 — 우리 결함이
        #     **자료 탓으로** 기록됐다.
        #  🔴 그래서 사유를 **갈라 적는다**: 자격이 있으면 `insufficient`(수집),
        #     없으면 `premature_insufficient`(**판정** = 우리 버그).
        from app import r5gate
        gate = r5gate.may_declare(fun)
        sc.notes.append(gate.line())
        # 🔴 **떨어지는 칸이 바뀌었다** — 시나리오는 만들어졌고 **등급**이
        #    없다(사용자 규칙 2026-10-06). ⚠️ `scenarios` 에 떨어뜨리면
        #    깔때기가 *"시나리오를 못 만들었다"* 로 읽힌다.
        fun.drop(gate.reason if not gate.ok else Reason.INSUFFICIENT,
                 "markets_graded")
        fun.set("markets_graded", 0)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§6-2 — 불완전한 세트로는 등급을 매기지 않는다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 하나라도 못 만들면 그 경기는 `scenario_incomplete` 로 **카드 금지.**
    #
    #  🔴 **왜 생존부터 막나**: §6-7 이 *"생존 1.0 은 시나리오를 다 만든 뒤에만
    #     성립한다"* 고 적었다. 세트가 모자란 채 `survive.run` 을 돌리면 죽을
    #     자리가 없어 **공짜로 1.0** 이 나오고, 그 수가 원장에 쌓인다.
    #  ⚠️ 시나리오는 **지우지 않는다** — 만든 것은 카드에 그대로 적고 등급만
    #     막는다(#3 조용한 0 금지: 왜 등급이 없는지 보여야 한다).
    if sc.incomplete:
        fun.drop(Reason.SCENARIO_INCOMPLETE, "markets_graded")
        fun.set("markets_graded", 0)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시나리오가 있으면 돈다** — 사용자 규칙 2026-10-06
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 시나리오·**대입**·방향 판정은 **항상** 낸다.
    #
    #  ⚠️ 종전엔 `not sc.incomplete` 도 걸려 있었다. 🔴 그런데 §6-2 의 주석이
    #     스스로 *"시나리오는 지우지 않는다 — 만든 것은 카드에 그대로 적고
    #     **등급만** 막는다"* 라고 적어 뒀다 — 코드는 `survive` 를 통째로
    #     막아 **대입까지** 없앴다.
    #  🔴 실측 2026-10-06(재실행): 시나리오 **7개**가 섰는데 블록 7~8 이
    #     *"못 셌다"* 이고 블록 9 가 *"시나리오가 없어 확률이 서지 않았다"* 라고
    #     적었다 — **거짓 사유**다(§8-6).
    #  🔴 그래서 둘 다 `thin_why` 로 넘긴다 — 거두는 것은 **등급**뿐이다.
    _no_grade = " · ".join(x for x in (
        str(sc.thin_why or ""),
        ("§6-2 `scenario_incomplete` — " + "; ".join(sc.incomplete_why)[:160]
         if sc.incomplete else "")) if x)
    if sc.drafts:
        card.survival = survive.run(sc.drafts, game, board=board,
                                    # 🔴 얇거나 세트가 모자라면 **등급만** 거둔다
                                    thin_why=_no_grade,
                                    # 🔴 거짓 1.0 계약의 재료(사용자 수정 ⑤)
                                    variables=card.variables,
                                    fold=sc.fold_markets,
                                    # 🔴 **분석 과정 5단계** — 라인업 상태가
                                    #    상한을 정한다(확정 1.0/예상 0.85/없음 0.8)
                                    xi_state=xi_state(card.xi, game),
                                    standings=st, probs=probs,
                                    # 🔴 **킥오프가 지났으면 등급을 거둔다**
                                    #    (지시 ③ 2026-10-05) — 분석은 낸다.
                                    kickoff=card.kickoff)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **v5-A §7 — 판정 순서**: 보강 → 1차 대입 → **반증** → 재대입
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ `enabled=false` 면 `judgeorder.steps()` 에 **반증이 없다** —
        #     그때는 아무 일도 안 하고 로그에 `redteam:off` 한 줄이다(§4-7).
        #  🔴 반증이 켜지면 1차 생존을 보고 0.8+ 마켓이 있을 때만 묻는다
        #     (v5-A §4) — 그 판단은 `redteam.due` 가 한다.
        #  🔴 재대입 뒤 **M44**(생존율 상승 금지)를 보고, 올라가면 **카드 금지**다.
        from app import judgeorder
        card.judge_steps = judgeorder.steps()
        card.redteam = None
        if "반증" in card.judge_steps:
            card.redteam = _run_redteam(card, game, sc, st, probs, board)
            if card.redteam and card.redteam.blocked:
                # 🔴🔴 **M44** — 카드 금지. ⚠️ 등급을 지우지 않고 **막는다** —
                #    왜 막혔는지 보여야 한다(#3).
                fun.drop(Reason.SCENARIO_INCOMPLETE, "markets_graded")
                states.setdefault("§4 반증", card.redteam.blocked)
        else:
            logger.info("[analyze] %s — 반증 단계를 건너뛴다(v5-A §7)",
                        judgeorder.off_note())
        # 🔴 v5 §8-5 — `markets_graded`: 등급이 **선** 마켓 수.
        #    ⚠️ 생존 수가 있는 줄이 아니라 **등급을 받은** 줄이다 — 상한·§6-7·
        #       M18 이 거둔 뒤의 수여야 *"왜 결론이 비었나"* 를 말한다.
        graded = [m for m in (card.survival.markets or [])
                  if str(m.verdict) != "none"]
        fun.set("markets_graded", len(graded))
        if not graded:
            # 🔴 거둔 사유가 노트에 남는다 — 그중 아는 것을 코드로 센다
            joined = " ".join(card.survival.notes or [])
            # 🔴 **시작해서 거둔 것이 먼저다** — 실측 pn14: 이 칸이 비어
            #    *"시나리오가 모자랐나"* 와 구별되지 않았다(#3).
            #    ⚠️ 글은 `survive.started` 가 만든다(사본 금지) — 그 글의
            #       조항 번호로 찾는다.
            if "지시 ③" in joined:
                fun.drop(Reason.KICKOFF_PASSED, "markets_graded")
            elif "M18" in joined:
                fun.drop(Reason.SCENARIO_INCOMPLETE, "markets_graded")
            elif "시나리오 세트 불완전" in joined:
                fun.drop(Reason.SCENARIO_INCOMPLETE, "markets_graded")
        card.triggers = triggers.run(items, game, board=board, standings=st,
                                     probs=probs, kickoff=kickoff)
    card.limits = _limits(items, sc, card.survival, card.states)
    return card


def _xi(facts: list) -> dict:
    """블록 2 기준 XI. 🔴 **어느 경기의 XI 인지** 함께 들고 온다.

    ══════════════════════════════════════════════════════════════════
    🔴 감독을 **아는데 미상이라고 적었다** (실측 2026-10-03)
    ══════════════════════════════════════════════════════════════════

    엘살바도르 vs 자메이카 로그:

    ```
    [analyze] Jamaica 감독 `Rudolph Speid` (선언(config/entities.yaml)) — 검색어로 쓴다
    ```
    그런데 **카드 블록 2 는 `감독 미상`** 이라고 적었다. 🔴 같은 실행 안에서 이름을
    쓰고 있는데 사용자에게는 모른다고 말했다 — 아는 것을 안 적으면 그것도 거짓이다.

    ⚠️ 까닭: `fotmob` 기준 XI 가 `coach=None` 을 주고, `_xi` 는 **그 칸만** 봤다.
    🔴 `entities.coach_of` 가 *"자료가 선언을 이긴다"* 를 이미 들고 있다 — 여기서
       다시 고르지 않고 **그것을 부른다**(사본 금지). 출처까지 함께 적는다.
    """
    from app import entities
    out: dict = {}
    for f in facts:
        suffix = str(f.question_id).rpartition(":")[2]
        val = f.value if isinstance(f.value, dict) else {}
        if suffix in ("baseline", "lineup") and val.get("players"):
            team = str(f.team or val.get("team") or "")
            coach, why = entities.coach_of(team, facts)
            out[team] = {
                "from_match": val.get("from_match"),
                "formation": val.get("formation"),
                # 🔴 `coach_of` 가 경기 자료를 먼저 보므로 `val["coach"]` 와 같은
                #    값이거나 더 낫다. ⚠️ 없으면 **왜 없는지**를 들고 간다.
                "coach": coach,
                "coach_why": why,
                "players": [str(p) for p in val["players"]],
                "confirmed": suffix == "lineup"}
    return out


def _form(facts: list, st: dict) -> dict:
    """블록 3 폼. 🔴 **못 잰 칸은 넣지 않는다** — 0 으로 메우지 않는다."""
    out: dict = {}
    for f in facts:
        suffix = str(f.question_id).rpartition(":")[2]
        val = f.value if isinstance(f.value, dict) else {}
        if suffix == "form" and val:
            out[str(val.get("team") or f.team or "")] = {
                k: val[k] for k in ("last5", "rest_days", "recent_avg_goals")
                if val.get(k) is not None}
        elif suffix == "standings" and val.get("rank") is not None:
            out.setdefault(str(val.get("team") or ""), {})["rank"] = val["rank"]
    if st.get("league_avg_goals"):
        out["리그"] = {"평균 총득점": st["league_avg_goals"],
                      "총점 기준선": st.get("total_baseline")}
    return out


#: 🔴 한 줄의 상한. 넘치면 **몇 자를 줄였는지 함께 적는다**(조용히 자르지 않는다).
LINE_CAP = 160


def _fold(text: str) -> str:
    """긴 사유를 **줄이되 잘렸음을 적는다.**

    ⚠️ 실측 2026-10-02(라이브 NPB): 한 세포의 사유가 **3천 자 한 덩어리**로 나와
       블록 1 을 읽을 수 없었다 — 열기 20건의 사유를 그대로 이어 붙였기 때문이다.
    🔴 그런데 **지울 수는 없다**(조용한 0 금지). 그래서 앞머리만 남기고
       *"…그리고 N 자 더"* 를 붙인다 — 전문은 로그·`Cell.tried` 에 그대로 있다.
    """
    one = " ".join(str(text or "").split())
    if len(one) <= LINE_CAP:
        return one
    return f"{one[:LINE_CAP]}… (그리고 {len(one) - LINE_CAP}자 더 — 전문은 로그에)"


def _clip(text: str, n: int) -> str:
    """🔴 `n` 자로 줄이되 **잘렸음을 적는다**(#3 조용한 0 금지).

    ⚠️ 실측 2026-10-03: 블록 4 가 `why[:150]` 으로 **표시 없이** 잘랐고, 그 줄이
       `… hardness hard→likely(§4 sampl` 에서 끝났다 — 읽는 사람은 그것이 사유의
       전부인지 잘린 것인지 알 수 없다. 🔴 `_fold` 가 같은 일을 하고 있었는데
       (*"그리고 N자 더"*) 이 자리만 날것으로 잘랐다.
    """
    one = " ".join(str(text or "").split())
    return one if len(one) <= n else f"{one[:n]}…(+{len(one) - n}자 · 전문은 로그에)"


def _tally(lines: list[str]) -> list[str]:
    """🔴 **같은 말은 묶어 센다.** 지우는 것이 아니라 `×N` 으로 세는 것이다.

    ⚠️ 라이브에서 *"플레이오프 경계를 모른다"* 가 두 번 나왔다(양 팀). 같은 사유를
       두 줄로 내면 블록이 길어지기만 하고 뜻이 늘지 않는다.
    """
    seen: dict[str, int] = {}
    for x in lines:
        seen[x] = seen.get(x, 0) + 1
    return [f"{k} ×{n}" if n > 1 else k for k, n in seen.items()]


def source_spread(rows: list) -> tuple[int, str]:
    """🔴🔴 **변수가 몇 출처에서 왔나** — 지시 ⑦ (실측 2026-10-05).

    ⚠️ 실사고: 검증 변수 5개 중 **3개가 같은 URL**(한 프리뷰 기사)에서 왔고
       셋 다 `aggregator`(무게 0)였다. 🔴 카드만 보면 *"다섯 각도에서 봤다"* 로
       읽힌다 — 실제로는 **한 기사**다.
    🔴 상한을 걸지 않는다(변수가 더 줄어든다) — **사실을 적는다**(#3).
    """
    from urllib.parse import urlparse
    seen: dict[str, int] = {}
    for r in (rows or []):
        url = str((r.get("source_url") if isinstance(r, dict)
                   else getattr(r, "source_url", "")) or "")
        host = (urlparse(url).netloc or "").lower().removeprefix("www.")
        if host:
            seen[host] = seen.get(host, 0) + 1
    if not seen:
        return 0, "⚠️ **출처 호스트를 못 쟀다** — 변수에 URL 이 없다"
    top = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
    worst, n = top[0]
    tail = " · ".join(f"{h} {c}건" for h, c in top[:4])
    mark = (" 🔴 **한 출처에 쏠렸다**"
            if n * 2 >= sum(seen.values()) and len(seen) > 1 else "")
    return len(seen), (f"출처 {len(seen)}곳 — {tail}{mark} "
                       f"(가장 많은 곳 `{worst}` {n}건)")


#: 🔴 **쏠림으로 보는 비율** — 지시서 §4-2: *"한 도메인이 검증 변수 근거의
#  **50% 초과**면"*. ⚠️ 정확히 50% 는 아니다(초과여야 한다).
SKEW_OVER = 0.5


def skewed_host(rows: list) -> tuple[str | None, str]:
    """🔴🔴 **한 도메인에 쏠렸나** — 지시서 §4-2 (2026-10-05).

    `(쏠린 호스트 또는 None, 사유)`.

    ⚠️ 실사고 it4/it5: `fotmob.com 22건` 이 검증 변수 근거의 대부분이었다.
       🔴 그때 2차 보충을 **같은 곳**에 또 던지면 뜻이 없다 — 그 도메인을
       빼고 **현지어로** 한 번 돌린다(2차 1회 안에서 · 횟수 추가 아님).
    """
    from urllib.parse import urlparse
    tally: dict[str, int] = {}
    for r in (rows or []):
        url = str((r.get("source_url") if isinstance(r, dict)
                   else getattr(r, "source_url", "")) or "")
        host = (urlparse(url).netloc or "").lower().removeprefix("www.")
        if host:
            tally[host] = tally.get(host, 0) + 1
    total = sum(tally.values())
    if not total:
        return None, "⚠️ **출처를 못 쟀다** — 변수에 URL 이 없다"
    host, n = max(tally.items(), key=lambda kv: (kv[1], kv[0]))
    pct = n / total
    if pct <= SKEW_OVER or len(tally) < 2:
        return None, (f"출처 {len(tally)}곳 — 가장 많은 곳 `{host}` "
                      f"{n}/{total}({pct * 100:.0f}%) · 쏠리지 않았다")
    return host, (f"🔴 **`{host}` 에 쏠렸다** — {n}/{total}"
                  f"({pct * 100:.0f}% > {SKEW_OVER * 100:.0f}%). 2차 보충은 "
                  f"그 도메인을 **빼고 현지어로** 돌린다(§4-2)")


def _limits(items: list, sc, sv, states: dict) -> list[str]:
    """블록 1 **자료 한계 고백.** 🔴 이 블록이 비면 그것이 거짓이다.

    모으는 곳 다섯: 미결정 항목 · 세포가 멈춘 사유 · §5 기록 · §6 경고 ·
    그리고 **아직 세포가 없는 §4 유형**(`rules.unimplemented_types`).

    🔴 **줄이되 지우지 않는다** — 같은 말은 `×N` 으로 묶고, 긴 줄은 몇 자를 줄였는지
       적는다. 전문은 로그와 `Cell.tried` 에 그대로 있다.
    """
    out: list[str] = []
    # 🔴 **출처 쏠림**을 맨 앞에 적는다(지시 ⑦) — 변수 수가 각도 수가 아니다
    said = [{"source_url": str(getattr(c, "source_url", "") or "")}
            for c in items if getattr(c, "source_url", "")]
    if said:
        out.append(source_spread(said)[1])
    out += _tally([f"미결정: {_fold(c.undecided)}" for c in items if c.undecided])
    cells_: list[str] = []
    for key, why in sorted(states.items()):
        if state_shown(why):
            cells_.append(f"세포 {key}: {_fold(why)}")
    out += _tally(cells_)
    out += _tally([_fold(x) for x in (sc.notes if sc else [])])
    out += _tally([_fold(x) for x in (getattr(sv, "notes", []) or [])])
    # 🔴 **세포가 아직 없는 유형을 이름으로** — v4 §4 표에 있고 구현이 없는 것
    miss = rules.unimplemented_types()
    if miss:
        out.append(f"§4 유형 중 아직 세포가 없는 것: {', '.join(sorted(miss))} "
                   f"— 그 방향은 변수로 서지 않는다")
    # 🔴 **v4 에 없는 유형을 썼으면 밝힌다**(사용자 지시로 더한 것).
    #    ⚠️ 읽는 사람이 *"이건 v4 표에 있는 규칙이구나"* 로 오해하면 안 된다.
    #    ⚠️ `added_types()` 는 **dict 목록**이다(유형·날짜·지시·근거 문서) — 집합으로
    #       쓰면 터진다(실측 2026-10-02: `unhashable type: dict`).
    used = {c.type for c in items if c.type}
    added = [a for a in rules.added_types() if a.get("type") in used]
    for a in added:
        out.append(
            f"🔴 `{a['type']}` 은 v4 §4 표에 **없는** 유형이다 — 사용자 지시"
            f"({a.get('date')}: \"{a.get('instruction')}\")로 더했다. 근거 "
            f"{a.get('doc')}")
    return out


# ══════════════════════════════════════════════════════════════════
# 글
# ══════════════════════════════════════════════════════════════════


def _dir_block(card, sv=None) -> list[str]:
    """🔴🔴 **블록 9 는 매 경기 한 줄이다** — 지시서 §2-2 (2026-10-05).

    > 카드 블록 9 는 **등급 유무와 무관하게** 매 경기 한 줄을 낸다.
    > ⚠️ 시작한 경기(M97)도 방향 줄은 낸다 — **등급만** 거둔다.

    ⚠️ 실사고 it6: 시나리오가 0개여서 렌더러가 **세 자리에서** 일찍 돌아갔고
       블록 9 가 통째로 없었다(`insufficient`·`incomplete`·`sv is None`).
    🔴 그래서 **한 함수**로 뺐다 — 세 자리가 같은 것을 쓴다(#1 사본 금지).
    """
    g = card.game
    rows = list(getattr(sv, "rows", []) or []) if sv is not None else []
    by = {r["market"].market_type: float(r["survival"] or 0)
          for r in rows if r.get("market") is not None}
    out = ["\n■ 9 방향 판정",
           "  " + survive.direction_line(
               by.get("home", 0.0), by.get("away", 0.0), by.get("draw", 0.0),
               home=str(getattr(g, "home", "") or "홈"),
               away=str(getattr(g, "away", "") or "원정"))]
    if not rows:
        # 🔴 **무엇이 없어서인지 가른다**(§8-6 거짓 사유 금지) — 실측
        #    2026-10-06: 시나리오 7개가 있는데 *"시나리오가 없어"* 라고 적었다.
        n = len(getattr(card.scenarios, "drafts", []) or []) \
            if card.scenarios is not None else 0
        out.append("     (⚠️ " + (
            f"시나리오 {n}개는 있는데 **대입을 못 셌다** — 보드·격자가 없거나 "
            f"생존이 안 돌았다" if n else
            "시나리오가 **하나도 없어** 확률을 못 쟀다")
            + " · 방향 줄은 그래도 낸다 · §2-2)")
    else:
        wins = [r for r in rows
                if r["market"].market_type in survive.WIN_MARKETS]
        named = [r["name"] for r in wins if r["verdict"] != "none"]
        out.append(f"     (승패 {len(wins)}줄 중 등급이 선 것 {len(named)}줄"
                   + (f": {' · '.join(named)}" if named else "") + ")")
    return out


def render(card: Card) -> str:
    """블록 열 개를 **순서대로**. 🔴 순서가 규격이다(`docs/fable/output_spec.md`).

    ⚠️ 배당 숫자를 쓰지 않는다(§7 R8). 나오는 수는 생존·확률·스코어뿐이다.
    """
    g = card.game
    from app.bot import aliases
    # 🔴 **사람이 읽는 이름으로 적는다** — 표기는 KST 와 같은 규율이다(§2).
    #    ⚠️ 모르면 원문을 그대로 둔다(`kr_team` 이 그렇게 돈다) — 지어내지 않는다.
    home_ko = aliases.kr_team(getattr(g, "home", "") or "?")
    away_ko = aliases.kr_team(getattr(g, "away", "") or "?")
    out = [f"{away_ko} @ {home_ko}"
           f"  ·  {getattr(g, 'league', '') or getattr(g, 'sport', '')}"]

    out.append("\n■ 1 자료 한계")
    # 🔴🔴 **깔때기를 맨 위에** — *"어디서 0 이 됐나"* 가 다른 모든 줄보다 먼저다
    #    (사용자 기술 지시 2026-10-03: *"고치기 전에 진단"*).
    if card.funnel is not None:
        out += [f"  {ln}" for ln in card.funnel.report().splitlines()]
    out += [f"  · {x}" for x in card.limits] or ["  · (없다고 적을 근거가 없다)"]

    out.append("\n■ 2 기준 XI")
    if not card.xi:
        out.append("  · 못 잡았다 — 기준 XI 없이 아래 변수를 읽어야 한다")
    for team, v in card.xi.items():
        tag = "확정" if v.get("confirmed") else f"기준({v.get('from_match') or '출처 미상'})"
        # 🔴 감독을 **아는 만큼 적고, 어디서 왔는지**까지 적는다. 모르면 **왜**다.
        if v.get("coach"):
            cw = f"감독 {v['coach']}" + (f"({v['coach_why']})"
                                        if v.get("coach_why") else "")
        else:
            cw = f"감독 미상 — {v.get('coach_why') or '사유 없음'}"
        out.append(f"  {team} [{tag}] {v.get('formation') or ''} {cw}")
        out.append(f"    {', '.join(v['players'][:11])}")

    out.append("\n■ 3 폼")
    for team, v in card.form.items():
        out.append(f"  {team}: " + " · ".join(f"{k} {x}" for k, x in v.items()))

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **변수를 사람이 읽을 수 있게** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  종전 카드의 변수 줄 다섯이 이랬다:
    #    `R3 [individual·home·soft] lineup:…:depth:player — (칸 없음)`
    #  🔴 질문 id 와 `(칸 없음)` 뿐이다 — **무슨 사실인지 사람이 모른다.**
    #
    #  🔴 판정 사유(`why`)에는 그 내용이 **이미 들어 있다**:
    #    *"§4 h2h_pattern '패턴 방향' — 최근 10경기 홈 6승 원정 1승 ·
    #      **4경기 연속 전반 리드**(표본 4경기)"*
    #  ⚠️ 사유를 안 적고 `text` 만 적는 것이 결함이었다. 둘을 **함께** 적는다 —
    #     `text` 는 어느 사실에서 왔나이고 `why` 는 규칙이 무엇을 봤나다.
    out.append("\n■ 4 뒤집는 변수")
    for i, c in enumerate(card.variables):
        head = (f"  {triggers.label_of(i)} [{c.type}·{c.direction}·"
                f"{c.hardness}] ")
        out.append(head + var_line(c, form=dict(card.form or {})))
        # 🔴 **출처를 한 줄 더** — 되짚을 수 있어야 한다(§12-c 감사)
        #    ⚠️ 주소는 **자르지 않는다** — 잘린 주소는 열리지 않으므로 되짚는다는
        #       이 줄의 목적 자체가 사라진다(종전 `src[:100]`).
        src = " ".join(str(c.source_url or "").split())
        if src:
            out.append(" " * len(head) + f"↳ {src}")
    if not card.variables:
        out.append("  · 0건")

    out.append("\n■ 5 가설과 무너지는 조건")
    for h in card.hypotheses:
        out.append(f"  {h.team}: 근거 {len(h.supports)}건 · 깨는 변수 "
                   f"{len(h.breaks)}건")
        # 🔴 **어느 변수가 받치고 어느 변수가 깨나**를 이름으로 적는다.
        #    ⚠️ 사용자 분석의 가설 블록이 그 꼴이다:
        #       *"무너지는 조건: R1·R2·R3 — 신인 GK·첫 선발 원톱…"*
        for word, rows in (("근거", h.supports), ("깨는", h.breaks)):
            if not rows:
                continue
            names = [f"{triggers.label_of(card.variables.index(c))}"
                     f"{'(' + str(c.type) + ')' if c.type else ''}"
                     for c in rows if c in card.variables]
            if names:
                out.append(f"      {word}: {' · '.join(names)}")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **가설을 문장으로** — 지시 ② (2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 pn8: 이 블록이 **번호만** 적었다(`근거: R1 · R2 · …`) —
        #     *"이긴다면 왜"* 를 읽을 수가 없었다.
        #  🔴 문장은 **DeepSeek 가 쓴다**(v5-A §3) — 코드가 지어내지 않는다.
        #     비면 그 사실이 보인다(번호만 남는다).
        # 🔴🔴 **근거가 0건이면 그 사실을 적는다** — 사용자 지시 2026-10-06 ⑦
        if not h.supports:
            out.append(f"      🔴 **근거 변수 없음** — 반대 팀 가설이 무너지는 "
                       f"조건만 쓴다(사용자 규칙 2026-10-06)")
            for c in (getattr(h, "thin_dropped", []) or [])[:3]:
                out.append(f"        · 표본 부족으로 뺀 근거: "
                           f"{_clip(str(c.thin_sample or c.type), 110)}")
        for word, rows in (("이긴다면", getattr(h, "win_why", []) or []),
                           ("무너지면", getattr(h, "break_why", []) or [])):
            for line in rows[:3]:
                out.append(f"      {word}: {_clip(str(line), 180)}")

    out.append("\n■ 6 시나리오")
    sc = card.scenarios
    if card.insufficient:
        # 🔴🔴 **등급만 없다** — 사용자 규칙 2026-10-06. ⚠️ 종전엔 여기서
        #    `return` 해서 DeepSeek 시나리오 6개가 통째로 사라졌다(실측).
        out.append(f"  🔴 **자료 얇음 — 등급 없음**"
                   + (f"({sc.thin_why})" if sc is not None and sc.thin_why
                      else "(§7 R5)")
                   + " · 시나리오·대입·방향은 그대로 낸다")
    if sc is None or not sc.drafts:
        out.append("  ⚠️ 시나리오가 **하나도 없다** — 템플릿도 DeepSeek 도 "
                   "아무것도 내지 못했다(그 사유는 블록 1 에 있다)")
        out += _dir_block(card)          # 🔴 방향은 그래도 낸다(§2-2)
        return "\n".join(out)
    if card.incomplete:
        # 🔴 §6-2 — **카드 금지**다. ⚠️ 그래도 **만든 시나리오는 보여 준다** —
        #    무엇이 모자란지 보이지 않으면 고칠 수 없다(#3).
        out.append("  🔴🔴 **§6-2 `scenario_incomplete` — 등급을 내지 않는다**")
        for why in card.incomplete_why:
            out.append(f"    · {why}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시나리오가 왜 그 시나리오인가** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  사용자 분석의 시나리오 줄은 **메커니즘 + 변수 + 스코어**다:
    #    *"B 저블록이 로테이션 콜롬비아를 막고, 알미론 역습 (R1·R2·R6·R8) → 0-1 / 1-1"*
    #
    #  봇은 `A ['2-1','1-0'] 근거 4.2 [soccer_home_normal]` 만 적었다 —
    #  🔴 **어느 변수가 그 시나리오를 만들었는지**가 사라져 있었다. 그런데 `Draft` 는
    #     그것을 들고 있다(`variables`·`why`). 적지 않은 것이 결함이었다.
    #  ⚠️ **문장을 지어내지 않는다** — §5-e 는 그 일을 LLM L6 에 뒀고 아직 안 이었다.
    #     여기서 하는 것은 **들고 있는 것을 보이는 것**뿐이다.
    for d in sc.drafts:
        p = f"확률 {d.probability}" if d.probability is not None else \
            f"근거 {d.strength}"
        vs = " ".join(str(x) for x in (d.variables or []))
        out.append(f"  {d.id} {d.scores} {p} [{d.template_id}]"
                   + (f" ← {vs}" if vs else ""))
        why = " ".join(str(d.why or "").split())
        if why:
            out.append(f"      {_clip(why, 150)}")
    if sc.uncovered:
        out.append(f"  🔴 어느 시나리오에도 없는 결과 {sc.uncovered} — "
                   f"{' · '.join(f'{k} {v}' for k, v in sc.uncovered_scores[:4])}")

    sv = card.survival
    if sv is None:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **방향 줄은 여기서도 낸다** — 지시서 §2-2 (2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 카드 블록 9 는 **등급 유무와 무관하게** 매 경기 한 줄을 낸다.
        #
        #  ⚠️ 실사고 it6: 시나리오가 0개여서 여기서 돌아갔고 **블록 9 가
        #     통째로 없었다** — *"방향 없음"* 과 같은 병이다(판정이 못 섰다는
        #     이유로 방향을 안 적는다).
        #  🔴 못 쟀으면 **못 쟀다고** 적는다(#3) — 줄을 없애지 않는다.
        out.append("\n■ 7~8 보드·결론 — 못 셌다")
        out += _dir_block(card)          # 🔴 방향은 그래도 낸다(§2-2)
        return "\n".join(out)

    ids = [d.id for d in sc.drafts]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **마켓 단위로 그린다** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 핸드 +1.5 두팀다 성립이 안된다는거야..축구는 승무패 **왜 어느 한쪽에만
    #  > 핸디가 적용된다**..언오버는 토탈이고
    #
    #  종전에는 열세 줄을 **독립 베팅처럼** 늘어놓았다. 실제 보드는 마켓 단위다:
    #    승무패 한 마켓(세 쪽) · 핸디 한 라인이 한 마켓(두 쪽) · 토탈 한 기준선(두 쪽)
    #  🔴 한 마켓의 두 쪽은 **여집합**이다 — 그 둘을 나란히 보여야 *"둘 다 산다"* 가
    #     애초에 말이 안 되는 것이 눈에 보인다.
    out.append("\n■ 7 보드 대입  (" + " ".join(ids) + ")")
    groups: dict[tuple, list] = {}
    for r in sv.rows:
        groups.setdefault(r["market_key"], []).append(r)
    LABEL = {"win": "승무패", "handicap": "핸디", "total": "토탈",
             "btts": "양팀득점"}
    for key, rows in groups.items():
        head = LABEL.get(key[0], key[0])
        if key[0] == "handicap":
            head = f"핸디 {key[1]:g}"
        elif key[0] == "total":
            head = f"토탈 {key[1]:g}"
        out.append(f"  ▸ {head}"
                   + ("  — 두 쪽은 여집합이다(동시에 맞을 수 없다)"
                      if key[0] in ("handicap", "total") else ""))
        for r in rows:
            marks = " ".join(r["marks"][i] for i in ids)
            p = f" · 격자 {r['p_market']}" if r["p_market"] is not None else ""
            out.append(f"      {r['name']:26s} {marks}  생존 {r['survival']}"
                       f"({r['verdict']}){p}")

    out.append("\n■ 8 결론")
    # 🔴🔴 **§6-8 등급 어휘 범례** — 다섯 글자를 센 쪽부터 적는다.
    #
    #  ⚠️ 왜 카드에 두나: `소액 하단` 은 **새로 생긴 글자**다(종전엔 0.8 과 0.9 가
    #     둘 다 `소액` 이었다). 범례가 없으면 사용자가 *"하단이 뭔가"* 를 물어야
    #     한다. 🔴 어휘 목록을 여기 베끼지 않는다 — `survive.verdict_words()` 다.
    out.append("  등급: " + " > ".join(survive.verdict_words())
               + "  (§6-8 · 경계는 `config/thresholds.yaml`)")
    named = [r for r in sv.rows if r["verdict"] in ("name", "small")]
    if not named:
        # 🔴 §6-b · §6-e — 살아남는 마켓이 없으면 **그 말만** 적는다
        out.append("  살아남는 마켓 없음")
    for r in named:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **상한이 내린 등급을 다시 올리지 않는다** — 지시 ② (2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 pn8: 상한이 `언더 3.5` 를 **`small` 로 내렸는데**
        #     (`§5단계 상한 0.85 … → small`) 결론 줄이
        #     `verdict_word(survival=1.0)` 으로 **다시 계산해 `낸다`** 를 적었다.
        #  🔴 그래서 카드가 *"낸다: 언더 3.5 (생존 1.0) — 죽는 시나리오 G"* 라는
        #     **모순**을 냈다. 상한을 건 일이 **무효가 된 것**이다.
        #  🔴 `r["verdict"]` 가 **이미 그 판정**이다(`name`·`small`·`low`·`none`) —
        #     그것을 글자로 바꾸기만 한다. ⚠️ 생존 수로 다시 재지 않는다.
        word = survive.word_of(str(r.get("verdict") or ""))
        # 🔴 **`△` 도 죽는 목록이다**(지시서 §2-1) — `FAIL` 만 세면
        #    *"죽는 시나리오 없다"* 가 거짓이 된다(실측 it4).
        dead = survive.dead_marks(r["marks"], ids)
        # 🔴 **어느 마켓의 어느 쪽인가**를 함께 적는다 — 그것을 안 적으면 두 줄이
        #    같은 마켓인지 다른 마켓인지 사람이 알 수 없다(사용자 지적 2026-10-03).
        key = r["market_key"]
        where = (f"핸디 {key[1]:g}" if key[0] == "handicap"
                 else f"토탈 {key[1]:g}" if key[0] == "total"
                 else "양팀득점" if key[0] == "btts" else "승무패")
        out.append(f"  {word}: [{where}] {r['name']} (생존 {r['survival']}) — "
                   f"죽는 시나리오 {dead or '없다'}")

    out += _dir_block(card, sv)

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5-A §4 — `■ 반증`**(그 부록의 출력 예 그대로)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 꺼져 있으면 **그 사실 한 줄**이다 — 블록을 **숨기지 않는다**(#3).
    #     🔴 숨기면 *"반증이 돌았나"* 를 카드만 보고는 알 수 없다.
    from app import judgeorder as _jo
    out.append("\n■ 반증")
    if card.redteam is None:
        out.append(f"  {_jo.off_note()} — 반증 단계가 꺼져 있다(v5-A §7)"
                   if "반증" not in (card.judge_steps or ())
                   else "  ⚠️ 반증을 돌렸지만 결과를 못 받았다(사유는 블록 1)")
    else:
        out += _jo.card_block(card.redteam)
        for n in (card.redteam.notes or []):
            out.append(f"  · {n}")

    out.append("\n■ 10 " + triggers.render(card.triggers).replace("\n", "\n  "))
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# DB — 🔴 §3 산출을 **표에 적는다**
# ══════════════════════════════════════════════════════════════════


async def persist(pool, game_id: int, card: Card) -> dict:
    """§3 산출을 표에 적는다. 돌려주는 것은 표마다 몇 줄인가.

    🔴 **표를 만들고 아무도 안 읽으면 그 칸은 영영 안 찬다**(배선 계약).
    ⚠️ 멱등으로 적는다 — 같은 경기를 다시 분석해도 줄이 겹치지 않는다.
    """
    import json as _json
    n = {"variables": 0, "background": 0, "sufficiency": 0, "scenarios": 0,
         "survival": 0, "board": 0}
    items = card.variables
    for i, c in enumerate(items):
        v, why = c.to_variable(f"V{i + 1}")
        if v is None:
            logger.info("[analyze] 변수 %d 를 못 만들었다: %s", i + 1, why)
            continue
        # 🔴 칸 이름은 **스키마가 원본이다**(`type`·`text`). 처음에 `var_type`·
        #    `claim` 으로 적었다가 배선에서 틀린 것을 알았다 — 코드와 표의 어휘가
        #    갈리면 적재가 터진다.
        await pool.execute(
            "INSERT INTO variables (game_id, var_key, type, direction, "
            "hardness, weight, is_premise, text, source_url, published_at, "
            "dateless_reason, collected_at_step) "
            # 🔴 **`$6::numeric(2,1)` 로 깎는다.** 실측 2026-10-02: 파이썬
            #    float `0.4` 가 NUMERIC 으로 가면
            #    `0.4000000000000000222…` 가 되고 `variables_weight_ck`
            #    (`weight = 0.4`)가 **거부한다.** 배선 전에는 적재가 없어서
            #    아무도 몰랐다 — 스키마와 코드가 같은 수를 다르게 본 자리다.
            "VALUES ($1,$2,$3,$4,$5,$6::numeric(2,1),$7,$8,$9,$10,$11,$12) "
            "ON CONFLICT (game_id, var_key) DO UPDATE SET text = EXCLUDED.text",
            game_id, v.id, v.type, v.direction, v.hardness, v.weight,
            v.is_premise, v.text, v.source_url, v.published_at,
            v.dateless_reason, v.collected_at_step)
        n["variables"] += 1
    for i, c in enumerate(card.background):
        b, why = c.to_background(f"B{i + 1}")
        if b is None:
            continue
        await pool.execute(
            "INSERT INTO background (game_id, bg_key, text, source_url, "
            "published_at, dateless_reason) VALUES ($1,$2,$3,$4,$5,$6) "
            "ON CONFLICT (game_id, bg_key) DO NOTHING",
            game_id, b.id, b.text, b.source_url, b.published_at,
            b.dateless_reason)
        n["background"] += 1
    sc = card.scenarios
    n_dir = len(items)
    n_opp = _opposites(items)
    # 🔴 **λ 두 수를 적는다** — 격자 64칸을 저장하지 않고 **다시 만들 수 있다**.
    #    채점이 *"그때 이 결과에 얼마를 줬나"* 를 물으려면 이것이 있어야 한다
    #    (사용자 지시 2026-10-02 *"뭘쌓는데???"* 가 이 구멍을 찾았다).
    lam = card.lam or {}
    await pool.execute(
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **UPDATE 가 `n_opposite`·`reason` 을 빼먹고 있었다**(실측 2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  그 탓에 **그날 카드가 DB 에 안 들어갔다**: `sufficiency_follows_counts_ck`
        #  위반 — 낡은 `n_opposite=0` 위에 새 `verdict='pass'` 가 얹혀 "반대 변수
        #  0인데 통과"가 됐다.
        #  ⚠️ 첫 적재는 통과하고 **두 번째 적재에서만** 터진다 — 그래서 늦게 보였다.
        #  🔴 갱신 절은 INSERT 가 적는 칸을 **빠짐없이** 적는다. 한 칸이라도 빠지면
        #     한 줄 안에 두 시점이 섞이고, CHECK 가 그것을 거짓으로 읽는다.
        "INSERT INTO sufficiency (game_id, n_directional, n_opposite, verdict, "
        "reason, lam_home, lam_away) VALUES ($1,$2,$3,$4,$5,$6,$7) "
        "ON CONFLICT (game_id) DO UPDATE SET "
        "n_directional = EXCLUDED.n_directional, "
        "n_opposite = EXCLUDED.n_opposite, verdict = EXCLUDED.verdict, "
        "reason = EXCLUDED.reason, "
        "lam_home = EXCLUDED.lam_home, lam_away = EXCLUDED.lam_away",
        game_id, n_dir, n_opp,
        "insufficient" if card.insufficient else "pass",
        " · ".join(sc.notes)[:400] if card.insufficient else "",
        lam.get("home"), lam.get("away"))
    n["sufficiency"] = 1
    if card.insufficient:
        return n
    for d in sc.drafts:
        await pool.execute(
            "INSERT INTO scenarios (game_id, scenario_id, var_keys, scores, "
            "strength, template_id, narrative, probability) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
            "ON CONFLICT (game_id, scenario_id) DO UPDATE SET "
            "scores = EXCLUDED.scores, strength = EXCLUDED.strength, "
            "probability = EXCLUDED.probability",
            game_id, d.id, list(d.variables), list(d.scores), d.strength,
            # 🔴 `strength`(근거 합)와 `probability` 는 **다른 수다** — 한 칸에 담지
            #    않는다. 채점이 *"0.11 이라고 한 것이 났나"* 를 묻는다
            d.template_id, "", d.probability)
        n["scenarios"] += 1
    # 🔴 **폼을 표에 적는다**(미배선 마무리). 카드가 이미 들고 있던 것이다.
    for side_name, form in (card.form or {}).items():
        if side_name == "리그" or not form:
            continue
        side = "home" if side_name == getattr(card.game, "home", "") else "away"
        await pool.execute(
            "INSERT INTO team_form (game_id, side, recent5, midweek, note) "
            "VALUES ($1,$2,$3::jsonb,$4,$5) "
            "ON CONFLICT (game_id, side) DO UPDATE SET recent5 = EXCLUDED.recent5",
            game_id, side,
            _json.dumps(form.get("last5") or [], ensure_ascii=False),
            # 🔴 **모르면 `None`** — 주중 경기인지 못 세면 0 으로 때우지 않는다
            None,
            " · ".join(f"{k}={v}" for k, v in form.items()))
        n["team_form"] = n.get("team_form", 0) + 1
    # 🔴 **전제 검사를 적는다**(§4 `is_premise`). STEP 2 의 자리다.
    #    ⚠️ `replaced` 는 **반대 검색**이 있어야 쓸 수 있다 — 아직 없다. 그래서 지금
    #       적히는 것은 `kept` 뿐이고, 그 사실이 사유에 남는다(조용한 0 금지).
    for i, c in enumerate(items):
        v, _why = c.to_variable(f"V{i + 1}")
        if v is None or not v.is_premise:
            continue
        await pool.execute(
            "INSERT INTO premise_check (game_id, premise_key, query_used, "
            "result, replacement_var_key) VALUES ($1,$2,$3,'kept',NULL) "
            "ON CONFLICT (game_id, premise_key) DO NOTHING",
            game_id, v.id, [c.source_url])
        n["premise_check"] = n.get("premise_check", 0) + 1
    for r in (card.survival.rows if card.survival else []):
        m = r["market"]
        await pool.execute(
            "INSERT INTO board (game_id, market_type, team, line) "
            "VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            game_id, m.market_type, m.team, m.line)
        n["board"] += 1
    for ms in (card.survival.markets if card.survival else []):
        await pool.execute(
            "INSERT INTO survival (game_id, market_type, team, line, "
            "alive_scenarios, dead_scenarios, survival, verdict) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
            "ON CONFLICT (game_id, market_type, team, line) DO UPDATE SET "
            "survival = EXCLUDED.survival, verdict = EXCLUDED.verdict",
            game_id, ms.market_type, ms.team, ms.line,
            list(ms.alive_scenarios), list(ms.dead_scenarios),
            ms.survival, ms.verdict)
        n["survival"] += 1
    return n


def _opposites(items: list) -> int:
    """§1 자료 충분성 — **반대 방향 변수 수.** 🔴 수가 판정을 정한다."""
    dirs = {c.direction for c in items}
    if len(dirs) < 2:
        return 0
    counts = {d: sum(1 for c in items if c.direction == d) for d in dirs}
    return min(counts.values())


# ══════════════════════════════════════════════════════════════════
# 질문 한 줄 → 카드 한 장
# ══════════════════════════════════════════════════════════════════


def _adapters() -> dict:
    """🔴 수집 어댑터 표. **원본은 `collect.ingest.ADAPTERS` 하나다**(사본 금지).

    ⚠️ 모듈 꼭대기에서 들이면 `analyze` ↔ `ingest` 가 서로를 부르게 된다 —
       부를 때 들인다.
    """
    from app.collect.ingest import ADAPTERS
    return ADAPTERS


async def _fill_slate(pool, league: str, day) -> str:
    """🔴 그 리그의 **일정을 받아 표에 적는다**. 돌려주는 것은 사람이 읽을 사유.

    ⚠️ 수집 전체(`ingest.collect`)를 부르지 않는다 — 그것은 순위·명단·라인업까지
       도는 **아침 작업**이고, 질문 하나가 그것을 끌고 오면 사람이 기다린다.
       🔴 필요한 것은 **슬레이트 한 조각**이다. 적는 SQL 은 `ingest` 것을 쓴다.
    """
    from app.cells import Q_SLATE, Cell, Question
    from app.collect import ingest
    mod = _adapters()[league]
    bb = Blackboard()
    # 🔴 어댑터가 *"전부 모아라"* 라고 선언하면 그대로 한다(`kbo.SLATE_COLLECT_ALL`)
    cell = Cell(Question(Q_SLATE, league, league=league), mod.sources_slate(day),
                collect_all=bool(getattr(mod, "SLATE_COLLECT_ALL", False)))
    why = await cell.run(Net(), bb, search=None)
    # 🔴 사실을 전부 펼쳐 모은다 — `bb.value()` 는 `collect_all` 에서 비어 온다
    #    (그 까닭은 `ingest.slate_rows` 독스트링에 있다)
    rows = ingest.slate_rows(bb, league)
    n = 0
    for r in rows:
        if not r.get("starts_utc"):
            continue            # 🔴 시각을 모르면 표에 넣지 않는다(`ingest` 와 같다)
        await pool.fetchval(
            ingest._UPSERT_GAME, r["sport"], r["league"], r["ext_id"], r["home"],
            r["away"], r.get("venue"), r["starts_utc"], r["starts_kst"],
            r.get("starts_local"), r["status"], r.get("round_note"),
            r.get("home_score"), r.get("away_score"))
        n += 1
    return f"`{league}` 어댑터로 {n}경기를 표에 적었다" + (f" — {why}" if not n else "")


#: 🔴 `games.status` 중 **예정이 아닌 것**. 원본은 `db/schema.sql` 의 주석이다
#   (`scheduled | delayed | postponed | inprogress | final`).
#   ⚠️ `delayed`·`postponed` 는 **시작 안 한 것**이다 — 예측이 아직 뜻이 있다.
PLAYED_STATUS = ("inprogress", "final")


def _after_kickoff(kick, status: str) -> str:
    """🔴 이 경기가 **이미 시작했나**. 시작했으면 그 사실을 한 문장으로.

    둘 중 하나라도 걸리면 예측이 아니다:
      ① `status` 가 `inprogress`·`final` — 자료 제공자가 **직접** 그렇게 말한다
      ② 킥오프 시각이 **지났다** — 상태가 아직 안 갱신된 경우를 잡는다

    ⚠️ ②만 보면 상태 갱신이 빠른 제공자에서 늦게 잡히고, ①만 보면 갱신이 느린
       제공자(실측: fotmob 이 예정으로 둔 채 경기가 시작했다)에서 **아예 못 잡는다.**
    🔴 못 잡으면 그 카드가 원장에 **예측으로** 들어가고, 그때 성적이 거짓이 된다.
    """
    from datetime import datetime as _dt
    bits: list[str] = []
    st = (status or "").strip().lower()
    if st in PLAYED_STATUS:
        bits.append(f"자료가 `{st}` 라고 말한다")
    now = _dt.now(timefmt.KST)
    if kick is not None and timefmt.kst(kick) <= now:
        gone = int((now - timefmt.kst(kick)).total_seconds() // 60)
        bits.append(f"킥오프({timefmt.kst_label(kick)})가 {gone}분 지났다")
    if not bits:
        return ""
    return ("이미 시작한 경기다 — **예측이 아니다**: " + " · ".join(bits)
            + ". 카드는 그대로 내지만 **원장에 넣지 않는다**"
            + "(예측과 채점을 섞으면 성적이 거짓이 된다)")


async def answer(pool, *, team: str | None = None, league: str | None = None,
                 day=None, days: int = 2, board=None, save: bool = True,
                 mode: str = ASK, opponent: str | None = None,
                 look_up: bool = True) -> str:
    """🔴 **이것이 배선의 끝이다** — 질문을 받아 카드 글을 돌려준다.

    ⚠️ 경기를 **고르지 않는다** — 여럿이 맞으면 목록을 돌려주고 사용자가 고른다
       (§17-g-3 · M14: 남의 경기를 분석하면 전부 거짓이 된다).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **입구는 하나다**(2단계 · 사용자 설계 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 입구에서 **단 한 번** 이름을 ID 로 바꾸고, 그 뒤로는 ID 만 쓴다.
    #
    #  ⚠️ 종전에는 이 함수가 직접 별칭을 풀고, 리그를 묻고, 표를 뒤지고, 못 찾으면
    #     다시 찾고 — **네 군데에서 이름을 다시 비교했다.** 그 사이에서 언어가
    #     갈리면 자기가 찾은 것을 버렸다(실측 2026-10-03: 네 번).
    #  🔴 그 전부를 `resolve.match_of` 로 옮겼다. 여기는 **결과를 받아 쓴다**.
    from app import resolve
    from app.matchref import Reason
    pre_notes: dict[str, str] = {}
    look = await resolve.match_of(pool, team=team or "", opponent=opponent or "",
                                  day=day, days=days, league=league or "",
                                  look_up=look_up)
    pre_notes["입구"] = "\n".join(look.steps)
    logger.info("[analyze] 입구 → %s", look.reason.value)
    if not look.ok:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **사용자 문장은 사유 표가 준다**(4단계 · 사용자 설계 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 사유 문자열을 **사람이 쓰지 않는다** — 실패한 `if` 문이 enum 을 돌려준다.
        #
        #  ⚠️ 종전엔 여기서 사유마다 문장을 **손으로** 적었다. 그러면 *"무엇이
        #     막았나"* 와 *"무엇이 막았다고 내가 생각했나"* 가 갈린다 — 실측
        #     2026-10-03 에 이름 문제를 *"창 밖"* 이라 적어 사용자를 두 번 헛돌게 했다.
        #  🔴 `matchref.SAY` 가 **한 표**다. 여기는 그것을 꺼내 쓸 뿐이다.
        from app.matchref import say
        body = [say(look.reason, asked=team or ""), ""]
        for row in look.candidates[:6]:
            body.append(f"  · {row.get('starts_kst')} · {row.get('league')} · "
                        f"{row.get('away')} @ {row.get('home')}")
        # 🔴 **우리가 고쳐야 풀리는 종류**면 그렇다고 적는다 — 사용자가 다시
        #    물어 봐야 헛돈다(그 구분이 `Reason` 에 들어 있다).
        if look.reason.is_our_bug:
            body.append("\n⚠️ 이것은 **봇을 고쳐야** 풀린다 — 다시 물어도 같다")
        body += ["", "밟은 단계:"] + [f"  {x}" for x in look.steps]
        return "\n".join(body)
    ref = look.ref
    row = {"id": ref.game_id, "home": ref.home, "away": ref.away,
           "sport": ref.sport, "league": ref.competition, "venue": ref.venue,
           "ext_id": ref.key, "starts_kst": ref.kickoff_utc,
           # 🔴 §3-3 형식의 재료 — 입구(`matchref`)가 읽어 온 라운드 표기
           "round_note": ref.round_note}
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **v5 §8-1 — 열쇠가 출처를 말하나**(이관 진척을 숫자로 본다)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 쌓인 행에 옛 꼴(`fotmob-5181780`)과 **접두 없는 꼴**(`849825`)이 있다.
    #     🔴 뒤쪽은 라우팅이 못 찾아 **깊이 소스가 통째로 안 돈다** — 그 사실을
    #        카드가 말해야 한다(#3 조용한 0 금지).
    from app import matchkey as _mk
    if not _mk.is_canonical(ref.key):
        pre_notes["열쇠"] = (
            f"⚠️ 경기 열쇠가 **옛 꼴**이다(`{ref.key}`) — §8-1 은 "
            f"`출처:경기ID` 를 요구한다. 출처 `{_mk.source_of(ref.key) or '미상'}` · "
            f"id `{_mk.id_of(ref.key)}`"
            + ("  🔴 **출처를 못 읽어 깊이 소스를 고를 수 없다**"
               if not _mk.source_of(ref.key) else ""))
    # 🔴 **팀 열쇠를 넘긴다**(3단계) — `side_of` 가 글자가 아니라 이것으로 가린다
    g = classify.Game(home=ref.home, away=ref.away,
                      sport=ref.sport, league=ref.competition,
                      home_id=ref.home_id, away_id=ref.away_id,
                      # 🔴 §3-3 — 이 칸이 `match_format` 을 만든다
                      round_note=ref.round_note)
    kick = ref.kickoff_utc
    # 🔴 **사람이 기다리는 질문은 `ASK` 예산이다**(§12-d · `cells.SECONDS_OF`).
    #    ⚠️ `DEEP`(300초 · 20회)으로 물으면 세포 하나가 몇 분을 쓴다 — 실측
    #       2026-10-01 에 한 세포가 **15분 51초**를 썼다. 서버가 미리 쌓을 때가
    #       `DEEP` 이고, 질문은 `ASK` 다.
    facts, states = await gather(
        {"home": g.home, "away": g.away, "league": g.league, "sport": g.sport,
         # ══════════════════════════════════════════════════════════════
         # 🔴🔴 **팀 열쇠를 넘긴다**(§8-1 · 게이트 2 가 요구한다)
         # ══════════════════════════════════════════════════════════════
         #
         #  ⚠️ 실측 2026-10-04(게이트 2 첫 판): 에이전트가 **입구에서 막혔다** —
         #     *"🔴 `home` 은 **열쇠**여야 한다(§8-1): ''"*. `answer` 는
         #     `ref.home_id` 를 알고 있었는데 **그 칸을 안 넘겼다.**
         #  🔴 §3-1 이 열쇠를 요구하는 것은 맞다(1~3단계가 고친 병이 입구에서
         #     되살아나지 않게) — 고칠 곳은 **넘기는 쪽**이었다.
         "home_id": ref.home_id, "away_id": ref.away_id,
         "game_id": row.get("id"), "kickoff": kick,
         # 🔴 `ext_id` 가 공식 API 깊이의 열쇠다 — 없으면 검색만 남는다
         "ext_id": row.get("ext_id"), "venue": row.get("venue"),
         # ══════════════════════════════════════════════════════════════
         # 🔴🔴 **사다리가 받아 온 현지 표기**를 넘긴다(실측 2026-10-03)
         # ══════════════════════════════════════════════════════════════
         #
         #  ④단(팀 직접 조회)이 `strTeamAlternate` 로 `柏レイソル` 을 받는다.
         #  ⚠️ 그런데 그것을 **안 넘겨서** 질의가 `Kashiwa Reysol スタメン` 이었다 —
         #     일본 매체는 `柏レイソル` 이라고 쓴다. 받아 놓고 안 쓴 자리다.
         #  🔴 `entities.yaml` 선언이 **먼저**다(`queries.variants` 가 그렇게 고른다)
         #     — 사다리가 받아 온 것은 선언이 없을 때의 **대체**다.
         # 🔴 **입구가 준 현지 표기**를 넘긴다 — 검색어가 그것으로 만들어진다
         "local": ref.home_local,
         # 🔴 사다리가 정한 **기사 언어**를 내린다(2026-10-04 보기 C)
         "langs": tuple(look.langs or ()),
         "opponent_local": ref.away_local}, mode=mode)
    for k, v in pre_notes.items():
        states.setdefault(k, v)
    card = build(facts, g, board=board, states=states, kickoff=kick,
                 match_key=str(row.get("ext_id") or ""))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예측인가** — 킥오프가 지났으면 이것은 예측이 아니다(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  실측(엘살바도르 vs 자메이카): `status = inprogress` · 킥오프 11:00 KST ·
    #  질문 12:05 KST. 🔴 **이미 시작한 경기**인데 카드가 예정 경기와 **똑같이**
    #  생겼다 — 한 줄도 그 말을 하지 않았다.
    #
    #  ⚠️ 그 규칙은 이 저장소에 **이미 적혀 있었다**(`slate.py`):
    #     *"끝난 경기를 예정으로 보이면 사용자가 그것을 분석 대상으로 여긴다(§2)."*
    #     슬레이트는 `[inprogress]` 를 찍고 있었고 **질문 경로만 빠져 있었다.**
    #
    #  🔴 그리고 **원장에 넣지 않는다.** CLAUDE.md 가 못 박았다 — *"예측을 안 했다와
    #     틀렸다를 가른다... 섞으면 성적이 거짓이 된다."* 결과가 (일부라도) 드러난
    #     뒤에 적은 카드를 예측으로 채점하면 성적이 **우리에게 유리한 쪽으로** 거짓이
    #     된다. ⚠️ 카드 자체는 그대로 낸다 — 사용자가 물었으니 답은 준다.
    late = _after_kickoff(kick, str(row.get("status") or ""))
    if save and late:
        logger.warning("[analyze] 적재하지 않는다 — %s", late)
        states["적재"] = f"원장에 넣지 않았다 — {late}"
    elif save and row.get("id"):
        try:
            got = await persist(pool, int(row["id"]), card)
            logger.info("[analyze] 적재 %s", got)
        except Exception as exc:                            # noqa: BLE001
            # 🔴 적재 실패로 **답을 잃지 않는다** — 사유는 로그에 남는다
            logger.warning("[analyze] 적재 실패: %r", exc)
    # 🔴 **KST 로 바꿔서** 적는다 — `starts_kst` 는 `timestamptz` 라 asyncpg 가
    #    UTC 로 돌려준다. 그대로 찍으면 9시간 틀린다(실측 2026-10-03: 11:00 경기가
    #    `02:00 KST` 로 찍혔다). 변환은 `timefmt` 하나다(절대규칙 2).
    head = (f"{timefmt.kst_label(kick)} · "
            f"사실 {len(facts)}건 · 세포 {len(states)}개\n")
    # 🔴 **맨 위에 적는다** — 블록 1 안에 묻으면 사용자가 예정 경기로 읽는다
    if late:
        head = f"🔴 {late}\n" + head
    return head + render(card)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **데이터가 쌓인다** — 채점 원장 (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# > 데이타가 쌓이고 그럼 그거가지고 분석을 하고... 스포츠는 정답이 없는거다...
#
# 🔴 정답지를 지웠으니 **기준은 하나만 남는다 — 실제 결과.** 경기가 끝나면 그때
#    우리가 적은 것을 꺼내 결과와 맞춰 보고 `ledger` 에 쌓는다.
# ⚠️ **예측은 고치지 않는다**(§3: *"결과 후 survival.json 수정 금지(불변)"*).
#    쌓이는 것은 채점이고, 그 둘이 서로를 바꾸면 기록이 거짓이 된다.
#
# 🔴🔴 **쌓인 것은 검증에만 쓴다** — 사용자 지시 2026-10-02:
#
# > 쌓이는거는 우리 로직이 맞냐 틀렸냐만 **검증하는 방법으로만** 사용한다..
#
#    원장으로 **규칙을 고치지 않는다** — 계수를 맞추지도, 문턱을 조정하지도,
#    가중치를 학습하지도 않는다. 묻는 것은 하나다: *우리 로직이 제가 한 말대로 했나.*
#    ⚠️ 전에 *"원장이 쌓이면 λ 보정 계수를 측정해서 짓는다"* 고 적었다 — **걷었다.**


def _cost_rows() -> list:
    """🔴 `solar` 가 디스크에 적어 둔 **비용 줄**. ⚠️ 없으면 빈 목록.

    🔴 그 파일이 원본이다(`ledger/cost_{YYYYMM}.jsonl`) — 여기서 수를 다시
       세지 않는다(#1 사본 금지).
    """
    import json as _json
    import pathlib
    out: list = []
    root = pathlib.Path("ledger")
    if not root.is_dir():
        return out
    for path in sorted(root.glob("cost_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(_json.loads(line))
            except ValueError:
                # ⚠️ 깨진 줄은 **건너뛴다** — 비용 기록이 채점을 막지 않는다
                continue
    return out


async def score_finished(pool, *, day=None, days: int = 3,
                         limit: int = 50) -> dict:
    """끝난 경기를 **실제 결과로** 채점해 `ledger` 에 쌓는다.

    🔴 **이미 채점한 경기는 다시 쓰지 않는다**(원장은 그때의 기록이다).
    ⚠️ 카드를 그때 저장하지 않은 경기는 **채점할 수 없다** — 사유를 센다.
       그것이 *"예측을 안 했다"* 와 *"틀렸다"* 를 가른다(조용한 0 금지).
    """
    from app import survive
    out: dict = {"graded": 0, "skipped": {}, "rows": []}
    rows = await pool.fetch(
        "SELECT g.id, g.home, g.away, g.sport, g.league, g.home_score, "
        "       g.away_score, g.ext_id "
        "  FROM games g "
        " WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL "
        "   AND NOT EXISTS (SELECT 1 FROM ledger l WHERE l.game_id = g.id) "
        " ORDER BY g.starts_kst DESC LIMIT $1", int(limit))
    for r in rows:
        gid = int(r["id"])
        mk = await pool.fetch(
            "SELECT market_type, team, line, survival, verdict "
            "  FROM survival WHERE game_id = $1", gid)
        sc = await pool.fetch(
            "SELECT scenario_id, scores, probability FROM scenarios "
            " WHERE game_id = $1", gid)
        lam = await pool.fetchrow(
            "SELECT lam_home, lam_away FROM sufficiency WHERE game_id = $1", gid)
        if not mk or not sc:
            # 🔴 **예측이 없는 경기다** — 틀린 것이 아니다. 둘을 섞지 않는다
            key = "카드를 저장한 적이 없다" if not mk else "시나리오가 없다"
            out["skipped"][key] = out["skipped"].get(key, 0) + 1
            continue

        class _M:
            def __init__(self, row):
                self.market_type = row["market_type"]
                self.team = row["team"]
                self.line = float(row["line"]) if row["line"] is not None else None
                self.survival = float(row["survival"])
                self.verdict = row["verdict"]

        class _D:
            def __init__(self, row):
                self.id = row["scenario_id"]
                self.scores = list(row["scores"])

        game = classify.Game(home=r["home"], away=r["away"],
                             sport=r["sport"] or "", league=r["league"] or "")
        # 🔴 **격자를 λ 로 되살린다** — 64칸을 저장하지 않고도 그때의 확률을 센다.
        #    ⚠️ λ 가 없으면 확률 칸은 **비운다**(지어내지 않는다)
        probs = None
        if lam and lam["lam_home"] is not None and lam["lam_away"] is not None:
            probs = league.score_probabilities(float(lam["lam_home"]),
                                               float(lam["lam_away"]))
        got = survive.grade([_M(x) for x in mk], [_D(x) for x in sc],
                            int(r["home_score"]), int(r["away_score"]),
                            game=game, probs=probs)
        import json as _json
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§7-4 — 실패 유형을 둘로 가른다**
        # ══════════════════════════════════════════════════════════════
        #
        #  > *없던 시나리오가 터짐*(규칙 결함 → M 계약 후보) /
        #  > *죽는 시나리오가 터짐*(무게 보정 대상)
        #
        #  🔴 섞으면 *"시나리오를 안 만들었다"* 와 *"만들었는데 낮게 봤다"* 가
        #     한 글자가 되고 **어느 쪽도 안 고쳐진다.**
        #  ⚠️ **무게 보정은 하지 않는다**(사용자 지시 2026-10-02: 원장은
        #     **검증에만**). 이름만 가른다.
        from app import ledgerkind
        covered = got["realized"] is not None
        # 🔴 덮였으면 **그 시나리오가 살아 있었나** — 이름 적은 마켓이 맞았나로 본다
        alive = None
        if covered:
            named = [v for v in got["verdicts"]
                     if v["hit"] is not None and v["verdict"] != "none"]
            alive = any(bool(v["hit"]) for v in named) if named else None
        kind = ledgerkind.classify(covered=covered, realized_alive=alive)
        # 🔴 §7-4 — **비용**. ⚠️ `solar` 가 줄 단위로 적어 둔 것을 합친다
        #    (두 번째 계수기를 만들지 않는다). 🔴 줄이 없으면 `None`(0 아니다).
        cost = ledgerkind.cost_of(str(r.get("ext_id") or ""), _cost_rows())
        await pool.execute(
            "INSERT INTO ledger (game_id, realized_scenario_id, "
            "missed_variables, card_verdicts_result, premise_failures, "
            "result_score, result_probability, covered, failure_kind, "
            "cost_usd) "
            "VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,$10) "
            "ON CONFLICT (game_id) DO NOTHING",
            gid, got["realized"], [],
            # 🔴 **등급·생존까지 싣는다** — 그것 없이는 *"'낸다' 가 '소액' 보다 더
            #    맞았나"* 를 못 센다(사용자 지시 2026-10-02 가 찾은 구멍)
            _json.dumps([{"market": v["market"], "hit": bool(v["hit"]),
                          "verdict": v["verdict"], "survival": v["survival"]}
                         for v in got["verdicts"] if v["hit"] is not None],
                        ensure_ascii=False),
            # 🔴 전제 실패 자리에 **"어느 시나리오에도 없던 결과"** 를 적는다 —
            #    그것이 우리가 틀린 가장 큰 방식이다
            [n for n in got["notes"] if "어느 시나리오에도 없었다" in n],
            got["result"], got.get("result_probability"),
            covered, kind, cost)
        out["graded"] += 1
        if kind:
            out.setdefault("failures", {})
            out["failures"][kind] = out["failures"].get(kind, 0) + 1
            logger.info("[score] %s @ %s — %s", r["away"], r["home"],
                        ledgerkind.say(kind))
        out["rows"].append({"game": f"{r['away']} @ {r['home']}",
                            "result": got["result"],
                            "realized": got["realized"],
                            "named": got["named"], "hit": got["hit"]})
        logger.info("[score] %s @ %s %s — 이름 적은 마켓 %d 중 %d 맞음 · 시나리오 %s",
                    r["away"], r["home"], got["result"], got["named"],
                    got["hit"], got["realized"] or "없음(결과를 안 그렸다)")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴 발송 — **스위치가 꺼져 있다**(§11-11). 길만 이어 둔다
# ══════════════════════════════════════════════════════════════════
#
# 사용자 지시 2026-10-02: *"배선 안 된 것도 마무리 지어라 … 사유만 남기고 나중에 하지
# 않으면 안 하는 이보다 못하다"*
#
# 🔴 `tg.send` 가 `NOT_WIRED` 의 마지막 함수였다. 이유는 *"단계 9 전까지 발송 off"* 로
#    맞지만, **길을 안 이어 두면 단계 9 에서 또 새 코드를 쓴다** — 그때 처음 돌리는
#    코드가 진짜 발송 경로가 된다. 그것이 가장 위험하다.
# ✅ 그래서 **지금 잇는다.** 안전한 까닭:
#      · `tg.send` 자신이 `SEND_ENABLED` 가 꺼져 있으면 **보내지 않고 False** 를 낸다
#      · 금지 어구(§7 R8·R9)도 `tg.send` 가 먼저 막는다
#      · 부르는 곳은 **1회성 CLI** 뿐이다 — 주기가 아니다(`scheduler card`)
# ⚠️ 그래서 이 함수를 불러도 **아무것도 나가지 않는다.** 나가는 조건은 사용자가
#    `.env` 의 스위치를 켜는 것 하나다.


async def deliver(pool, *, team: str, day=None, days: int = 2,
                  board=None) -> dict:
    """카드를 만들어 **보낸다**(스위치가 켜져 있을 때만).

    돌려주는 것: `{"sent": bool, "why": str, "chars": int}`.
    🔴 **보냈나와 왜 안 보냈나를 둘 다** 낸다 — 조용히 안 보내면 그것이 가장 나쁘다.
    """
    from app import tg
    from app.config import get_settings
    body = await answer(pool, team=team, day=day, days=days, board=board)
    s = get_settings()
    if not s.send_enabled:
        # 🔴 §11-11 — 단계 9 전까지 꺼짐. 글은 만들었고 **보내지 않았다**
        logger.info("[analyze] 발송 스위치 꺼짐 — 카드 %d자를 만들고 보내지 않았다",
                    len(body))
        return {"sent": False, "why": "SEND_ENABLED 가 꺼져 있다(§11-11 · 단계 9)",
                "chars": len(body)}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§10-4 게이트 7 — 발송은 마지막 칸이다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `SEND_ENABLED` 가 켜지는 것만으로는 부족하다 — **단계 게이트 표**가
    #     그 칸을 `통과` 로 적고 **사용자 서명**이 붙어야 한다(§10-4).
    #  🔴 스위치는 실수로도 켜진다(`.env` 한 줄이다). 게이트 표는 **서명 파일**을
    #     요구하므로 두 겹이다.
    #  🔴 내가 그 칸을 `통과` 로 적지 않는다(사용자 지시 2026-09-30).
    gate = rules.stage_gates().get(7) or {}
    if str(gate.get("state")) != "통과":
        logger.warning("[analyze] 🔴 §10-4 게이트 7 이 `%s` 다 — 보내지 않는다",
                       gate.get("state"))
        return {"sent": False,
                "why": (f"🔴 §10-4 **게이트 7 이 `{gate.get('state')}`** 다 — "
                        f"{gate.get('criterion')}. 사용자 서명이 있어야 보낸다"),
                "chars": len(body)}
    ok = await tg.send(body)
    return {"sent": bool(ok),
            "why": "" if ok else "tg.send 가 거부했다(금지 어구·토큰·스위치)",
            "chars": len(body)}
