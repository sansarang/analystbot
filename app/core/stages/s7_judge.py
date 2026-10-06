"""🔴🔴 **v6 s7 — 판정.** `Variable·HypoSet → Judgement`(§5). **LLM 을 안 부른다.**

지시서 §5 s7:

> 보드가 있으면 보드 줄만, 없으면 기준선 복수. 다중 스코어 시나리오는 스코어
> 전부 대입(○/△/✗). 생존율, 상한(XI·오픈월드·자료 얇음), 같은 방향 3개 상한,
> 시작한 경기 등급 없음, 블록 9 방향 문장(차이 0.15 이상이면 팀 이름, 미만이면
> 반반+기울기), 방아쇠. 이 단계는 **LLM 을 부르지 않는다.**

🔴 **수는 이 저장소의 표가 든다**(#1 사본 금지): 사다리는 `survive.verdict_word`,
   상한은 `rules.xi_state_cap`, 같은 방향 상한은 `scenario_rules.conclusion`,
   방향 문턱은 `survive.DIR_GAP`, 대입 산수는 `survive.apply` 다.
⚠️ 그 함수들에 **dict 를 넘기지 않는다** — `classify.Game`·`types.Market` 은
   타입이고, v6 타입에서 그 둘을 만드는 자리는 여기 하나다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.schema import (Board, BoardLine, Facts, Grade, HypoSet,
                             Judgement, MarketEval, MatchRef, Scenario,
                             Variable)
from app.core.state import RunState

#: 🔴 옛 `market_type` → v6 `(Market, side)`. ⚠️ 표를 **한 번만** 적는다.
#: 🔴 방아쇠 번호 — 규격이 `①~④` 라고 적었다(변수 번호와 섞이지 않게)
_CIRCLED = ("①", "②", "③", "④")

_MAP: dict[str, tuple[str, str]] = {
    "home": ("win", "home"), "away": ("win", "away"),
    "draw": ("draw", ""), "home_dc": ("unbeaten", "home"),
    "away_dc": ("unbeaten", "away")}


@dataclass(frozen=True)
class _Draft:
    """🔴 `survive` 의 무게·favorite 계산이 기대하는 **최소 꼴**(§6 부품).

    ⚠️ dict 가 아니다 — `id` 와 `scores` 두 칸만 보는 함수들이다.
    """

    id: str
    scores: list[str]


def run(ref: MatchRef, facts: Facts, variables: list[Variable],
        hypo: HypoSet, *, state: RunState, board: Board | None = None,
        now: Any = None) -> Judgement:
    """🔴 마켓마다 대입하고 등급을 매긴다. ⚠️ 등급이 없어도 **카드는 나온다**."""
    from app import survive
    notes: list[str] = []
    started, started_why = survive.started(ref.kickoff_utc, now)
    scen = list(hypo.scenarios)
    w = {s.id: float(s.strength) for s in scen}
    lines = _lines(ref, facts, scen, w, board=board, notes=notes)
    enough, thin_why = _enough(variables, scen)
    if not enough:
        notes.append(f"🔴 §7 R5 **자료 얇음 — 등급 없음**({thin_why}) · "
                     f"시나리오·대입·방향은 그대로 낸다")
    cap, cap_why = _cap(ref, facts, variables)
    notes.append(cap_why)
    evals: list[MarketEval] = []
    for old, line in lines:
        got = _one(old, line, ref, scen, w, cap=cap, enough=enough,
                   started=started, state=state)
        if got is not None:
            evals.append(got)
    evals = _same_direction_cap(evals, notes=notes)
    state.set("markets_graded", sum(1 for e in evals if e.grade != "자료부족"))
    direction = _direction(ref, scen, w)
    return Judgement(evals=evals, direction=direction,
                     conclusion=_conclusion(evals, started=started,
                                            enough=enough, thin_why=thin_why),
                     triggers=_triggers(variables, ref),
                     started=started, started_why=started_why, notes=notes)


# ══════════════════════════════════════════════════════════════════
# 보드 줄 — 🔴 있으면 보드만, 없으면 기준선 복수(§6-c-3)
# ══════════════════════════════════════════════════════════════════


def _lines(ref: MatchRef, facts: Facts, scen: list[Scenario],
           w: dict[str, float], *, board: Board | None,
           notes: list[str]) -> list[tuple[Any, BoardLine]]:
    """🔴 `(옛 Market, v6 BoardLine)` 짝 목록. ⚠️ 변환을 **한 곳**에 둔다."""
    from app import survive
    from app.core.stages.s5_verify import game_of
    if board is not None and board.lines:
        notes.append(f"보드 {len(board.lines)}줄을 받았다 — **보드 줄만** 센다")
        return [(_old_of(line), line) for line in board.lines]
    drafts = [_Draft(id=s.id, scores=[f"{h}-{a}" for h, a in s.outcomes])
              for s in scen]
    got, said = survive.our_board(game_of(ref), dict(facts.standings) or None,
                                  drafts=drafts, w=w)
    notes += [str(x) for x in said]
    out: list[tuple[Any, BoardLine]] = []
    for m in got:
        line = _new_of(m)
        if line is not None:
            out.append((m, line))
        else:
            notes.append(f"🔴 마켓 `{getattr(m, 'market_type', '?')}` 를 v6 "
                         f"꼴로 못 옮겼다 — 그 줄은 **세지 않았다**(#3)")
    return out


def _new_of(m: Any) -> BoardLine | None:
    """🔴 옛 `Market` → `BoardLine`. ⚠️ 모르는 꼴은 `None`(조용히 만들지 않는다)."""
    mt = str(getattr(m, "market_type", ""))
    team = str(getattr(m, "team", "") or "")
    line = getattr(m, "line", None)
    if mt in _MAP:
        kind, side = _MAP[mt]
        return BoardLine(market=kind, side=side)      # type: ignore[arg-type]
    if mt in ("handicap", "total", "btts"):
        return BoardLine(market=mt, side=team,        # type: ignore[arg-type]
                         point=(float(line) if line is not None else None))
    return None


def _old_of(line: BoardLine) -> Any:
    """🔴 `BoardLine` → 옛 `Market`(대입 산수가 그 타입을 받는다)."""
    from app.types import Market as OldMarket
    back = {("win", "home"): "home", ("win", "away"): "away",
            ("draw", ""): "draw", ("unbeaten", "home"): "home_dc",
            ("unbeaten", "away"): "away_dc"}
    mt = back.get((line.market, line.side))
    if mt:
        return OldMarket(market_type=mt)
    return OldMarket(market_type=line.market, team=line.side,
                     line=line.point)


# ══════════════════════════════════════════════════════════════════
# 대입 · 생존 · 등급
# ══════════════════════════════════════════════════════════════════


def _one(old: Any, line: BoardLine, ref: MatchRef, scen: list[Scenario],
         w: dict[str, float], *, cap: float, enough: bool, started: bool,
         state: RunState) -> MarketEval | None:
    """🔴 마켓 한 줄 — **스코어 전부 대입**하고 생존을 센다(§6-a)."""
    from app import survive
    marks: dict[str, str] = {}
    hit, mass = 0.0, 0.0
    unread: list[str] = []
    for s in scen:
        sym, ratio, bad = survive.apply(
            old, [f"{h}-{a}" for h, a in s.outcomes],
            home=ref.home_name, away=ref.away_name, sport=ref.sport)
        if sym == "?":
            # 🔴 **못 읽은 것은 분모에서 뺀다** — `False` 로 세면 생존이 거짓으로
            #    내려간다(조용한 0 금지). ⚠️ 그 사실을 이름으로 남긴다.
            unread.append(f"{s.id}({bad}개)")
            continue
        marks[s.id] = sym
        weight = float(w.get(s.id, 0.0))
        mass += weight
        hit += weight * float(ratio)
    if not marks:
        state.note(f"s7 `{survive.name_of(old)}` — 대입할 시나리오가 없다"
                   + (f"(못 읽음 {unread})" if unread else ""))
        return None
    survival = round(hit / mass, 4) if mass else 0.0
    grade = _grade(survival, cap=cap, enough=enough, started=started,
                   n_scen=len(marks))
    return MarketEval(line=line, marks=marks, survival=survival, cap=cap,
                      grade=grade,
                      dead=survive.dead_marks(marks, [s.id for s in scen]))


def _grade(survival: float, *, cap: float, enough: bool, started: bool,
           n_scen: int) -> Grade:
    """🔴 사다리는 `survive.verdict_word` **하나**다(#1) — 여기서 경계를 안 적는다.

    🔴 **상한을 씌운 수로** 등급을 매긴다 — 상한이 내린 등급을 되올리지 않는다
       (실측 pn8: 카드가 다시 계산해 `소액` 을 `낸다` 로 올렸다).
    ⚠️ 시작한 경기는 **등급이 없다**(M97) — 분석은 그대로 낸다.
    """
    from app import survive
    if started:
        return "없음"
    if not enough:
        return "자료부족"
    got = survive.verdict_word(min(float(survival), float(cap)))
    words = {survive.WORD_NAME: "낸다", survive.WORD_SMALL: "소액",
             survive.WORD_SMALL_LOW: "소액하단", survive.WORD_NONE: "없음"}
    return words.get(got, "없음")                     # type: ignore[return-value]


def _enough(variables: list[Variable], scen: list[Scenario]) -> tuple[bool, str]:
    """🔴 §7 R5 — *"변수 3개 미만·반대 방향 0개면 자료 부족."* **등급만** 거둔다.

    🔴 수는 `scenarios.MIN_VARIABLES`·`MIN_DIRECTIONS` 가 든다(#1 사본 금지).
    ⚠️ 그리고 §6-7 거짓 1.0: 변수가 `thin_set_vars` 미만이면 생존 1.0 은 *"죽을
       자리가 없다"* 는 뜻이다 — 그 경기는 등급을 내지 않는다.
    """
    from app import scenarios, thresholds
    sides = {v.favors for v in variables if v.favors in ("home", "away")}
    if len(variables) < scenarios.MIN_VARIABLES or \
            len(sides) < scenarios.MIN_DIRECTIONS:
        return False, (f"방향 있는 변수 {len(variables)}개(최소 "
                       f"{scenarios.MIN_VARIABLES}) · 방향 {len(sides)}종"
                       f"(최소 {scenarios.MIN_DIRECTIONS})")
    thin = int(thresholds.value("thin_set_vars"))
    if len(variables) < thin and len(scen) < int(scenarios.MIN_SCENARIOS):
        return False, (f"변수 {len(variables)}개 < {thin} 이고 시나리오 "
                       f"{len(scen)}개 < {scenarios.MIN_SCENARIOS} — 죽을 자리가 "
                       f"모자라 생존이 **공짜로** 높아진다(§6-7 거짓 1.0)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **분석이 만든 갈래가 하나도 없으면 등급을 내지 않는다** — 실측 2026-10-06
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 가설 단계가 빗나간 실행에서 시나리오가 **코드 보강 셋**(핸디 대응·실점
    #     동반)만 남았다. 그 셋은 **서로 안 죽이게** 생겨서 `홈 승` 이 생존 **1.0**
    #     을 받았고 카드가 *"죽는 시나리오 없음"* 이라 적었다.
    #  🔴 코드 보강은 *"이 갈래가 빠지면 공짜 1.0 이 된다"* 를 막는 **보험**이고,
    #     그것만으로 **판정의 근거가 되지는 않는다**(우리 분석이 그린 갈래가 없다).
    if scen and all(s.added_by == "code" for s in scen):
        return False, (f"시나리오 {len(scen)}개가 **전부 코드 보강**이다 — 분석이 "
                       f"그린 갈래가 0개다(가설 단계가 돌지 않았다)")
    return True, ""


def _cap(ref: MatchRef, facts: Facts, variables: list[Variable]
         ) -> tuple[float, str]:
    """🔴 상한 — **XI · 오픈월드 · 자료 얇음**의 **최솟값**(§5 s7).

    🔴 수는 `rules.xi_state_cap()` 표가 든다 — 오픈월드는 그 **사다리에서 한 칸
       내린다**(`survive.step_down`). ⚠️ `0.85` 같은 수를 여기 적지 않는다(#1):
       *"아는 리그보다 한 단계 보수적으로"* 가 규칙이고, 간격은 표가 정한다.
    """
    from app import survive
    xi = [facts.xi.get(k) for k in (ref.home, ref.away)]
    n_ok = sum(1 for x in xi if x is not None and x.state == "confirmed")
    n_pred = sum(1 for x in xi if x is not None and x.state == "predicted")
    said = ("양쪽확정" if n_ok == 2 else "한쪽확정" if n_ok == 1
            else "양쪽예상" if n_pred == 2 else "없음")
    cap = float(survive.cap_for(said))
    why = [f"XI `{said}` → 상한 {cap}"]
    if ref.openworld:
        cap = float(survive.step_down(cap))
        why.append(f"🌐 오픈월드(열쇠 임시 발급) → **한 칸 내림** {cap}")
    return cap, " · ".join(why)


def _same_direction_cap(evals: list[MarketEval], *, notes: list[str]
                        ) -> list[MarketEval]:
    """🔴 같은 방향 **3줄 상한** — 수는 `scenario_rules.conclusion` 이 든다(#1).

    ⚠️ 넘치는 줄은 **지우지 않는다** — 등급만 거둔다(분석은 보여 준다).
    """
    from app import rules
    cap = int((rules.conclusion_cfg() or {}).get("max_same_direction") or 0)
    if cap <= 0:
        return evals
    named = [e for e in evals if e.grade in ("낸다", "소액", "소액하단")]
    out: list[MarketEval] = []
    by_side: dict[str, int] = {}
    cut = 0
    for e in evals:
        if e not in named:
            out.append(e)
            continue
        side = f"{e.line.market}/{e.line.side}"
        by_side[side] = by_side.get(side, 0) + 1
        if len(named) > cap and sum(by_side.values()) > cap:
            out.append(e.model_copy(update={"grade": "없음"}))
            cut += 1
            continue
        out.append(e)
    if cut:
        notes.append(f"🔴 추천 줄이 상한({cap})을 넘어 {cut}줄의 등급을 거뒀다 — "
                     f"줄은 그대로 보여 준다")
    return out


# ══════════════════════════════════════════════════════════════════
# 블록 9 방향 · 결론 · 방아쇠
# ══════════════════════════════════════════════════════════════════


def _direction(ref: MatchRef, scen: list[Scenario], w: dict[str, float]) -> str:
    """🔴🔴 **블록 9 는 매 경기 한 줄**(지시서 §2-2) — 등급과 무관하다.

    🔴 문턱(`DIR_GAP`)과 문장 꼴은 `survive.direction_line` 하나가 든다(#1).
    """
    from app import survive
    mass = sum(float(w.get(s.id, 0.0)) for s in scen) or 0.0
    got = {"home": 0.0, "away": 0.0, "draw": 0.0}
    for s in scen:
        weight = float(w.get(s.id, 0.0))
        if not s.outcomes:
            continue
        for h, a in s.outcomes:
            key = "home" if h > a else "away" if a > h else "draw"
            got[key] += weight / len(s.outcomes)
    if mass:
        got = {k: round(v / mass, 4) for k, v in got.items()}
    return survive.direction_line(got["home"], got["away"], got["draw"],
                                  home=ref.home_name, away=ref.away_name)


def _conclusion(evals: list[MarketEval], *, started: bool, enough: bool,
                thin_why: str) -> str:
    """🔴 결론 — **죽는 시나리오를 함께** 적는다(`✗` 와 `△` 둘 다 · §2-1)."""
    from app import survive
    if started:
        return ("🔴 **이미 시작한 경기다 — 등급 없음.** 분석은 그대로 낸다"
                "(예측이 아니라 사후 설명이 되기 때문이다)")
    if not enough:
        return f"🔴 **등급 없음 — 자료 얇음**({thin_why})"
    named = [e for e in evals if e.grade in ("낸다", "소액", "소액하단")]
    if not named:
        best = max(evals, key=lambda e: e.survival, default=None)
        return ("등급 없음 — 문턱을 넘은 줄이 없다"
                + (f"(가장 높은 줄 생존 {best.survival})" if best else
                   "(대입할 줄이 없다)"))
    rows = [{"market": f"{e.line.market}/{e.line.side}", "dead": e.dead,
             "verdict": ("name" if e.grade == "낸다" else "small")}
            for e in named]
    out = []
    for e in named:
        dead = ", ".join(e.dead) or "없음"
        point = f" {e.line.point}" if e.line.point is not None else ""
        out.append(f"**{e.line.market} {e.line.side}{point}** — {e.grade} "
                   f"(생존 {e.survival} · 상한 {e.cap}) · 죽는 시나리오 {dead}")
    tail = survive.same_branch_note(rows)
    return "\n".join(out) + (f"\n{tail}" if tail else "")


def _triggers(variables: list[Variable], ref: MatchRef) -> list[str]:
    """🔴 방아쇠 — *무엇이 보이면 → 무엇이 바뀌고 → 상한 얼마*(규격 블록 10).

    🔴 조건 꼴은 `config/trigger_conditions.yaml` 이 든다(`rules.trigger_checks`)
       — 글자를 코드에 적지 않는다(#1).
    """
    from app import rules, triggers
    checks = rules.trigger_checks()
    out: list[str] = []
    for v in variables:
        said = checks.get(v.type)
        if not said:
            continue
        # 🔴 **번호는 ①~④ 다**(규격 블록 10). ⚠️ `triggers.label_of` 는 `R1` 꼴을
        #    돌려주는데 그것은 **변수 번호**와 같은 글자다 — 실측 2026-10-06 카드가
        #    `R3 … → R4` 로 찍혀 어느 것이 변수인지 안 보였다.
        out.append(f"{_CIRCLED[len(out)]} {said} → `{v.id}`"
                   f"({v.type} · {v.claim[:40]}) 가 바뀌면 다시 센다 · "
                   f"{triggers.when_of(v.type, ref.kickoff_utc)}")
        if len(out) >= 4:
            break
    return out
