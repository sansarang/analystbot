"""🔴🔴 **v6 s7 — 판정.** `Variable + 격자 → Judgement`(§5). **LLM 을 안 부른다.**

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

from app.core.schema import (Board, BoardLine, Facts, Grade,
                             Judgement, MarketEval, MatchRef,
                             Variable)
from app.core.state import RunState

#: 🔴 옛 `market_type` → v6 `(Market, side)`. ⚠️ 표를 **한 번만** 적는다.
#: 🔴 방아쇠 번호 — 규격이 `①~④` 라고 적었다(변수 번호와 섞이지 않게)
_CIRCLED = ("①", "②", "③", "④")

#: 🔴 결장 계열 — 그 선수가 **나오면** 변수가 사라진다(반대는 복귀 유형이다)
_ABSENT = ("absence", "absence_att", "def_absence", "fatigue", "suspension",
           "injury")

_MAP: dict[str, tuple[str, str]] = {
    "home": ("win", "home"), "away": ("win", "away"),
    "draw": ("draw", ""), "home_dc": ("unbeaten", "home"),
    "away_dc": ("unbeaten", "away")}


# ⚠️ **`_Draft` 는 지웠다** — 시나리오를 `survive` 의 무게 계산에 넘기던
#    최소 꼴이다. §1 처분으로 시나리오가 없다.
def run(ref: MatchRef, facts: Facts, variables: list[Variable],
        *, state: RunState, board: Board | None = None,
        board_source: str = "", dist: dict | None = None,
        now: Any = None) -> Judgement:
    """🔴 마켓마다 대입하고 등급을 매긴다. ⚠️ 등급이 없어도 **카드는 나온다**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **F5 — 생존 = 시뮬 확률**(지시서 2026-10-11)
    ══════════════════════════════════════════════════════════════════

    > ⑭ 생존은 ⑪ 스코어 분포에서 **직접** 계산. 시나리오(⑬)와 필수형 보강
    > 갈래는 **표시용** — 생존 계산에 안 쓴다.

    `dist` 는 `{(홈, 원정): 확률}`(`ProbOut.scores`)다. ⚠️ 없으면 **옛 길**
    (시나리오 무게)로 센다 — 그 사실을 사유에 적는다(#3).
    """
    from app import survive
    notes: list[str] = []
    started, started_why = survive.started(ref.kickoff_utc, now)
    lines, src = _lines(ref, facts, board=board, notes=notes,
                        source=board_source, dist=dist, ref_names=(
                            ref.home_name, ref.away_name))
    enough, thin_why = _enough(variables)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대회를 못 알아보면 등급을 전부 보류**(사용자 지시 2026-10-09(4차) §2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 못 알아보면 … 그 상태로 **등급은 전부 보류.**
    #
    #  🔴 기준·리그 평균·홈 이점 표가 다 비어 있으므로 생존 수의 뜻이 달라진다 —
    #     그 수에 등급을 붙이면 **없는 기준 위에 이름을 적는 것**이다.
    #  ⚠️ 생존·대입·방향은 **그대로 낸다**(`enough=False` 와 같은 길이다).
    from app.core.stages.s5_verify import comp_kind
    if not comp_kind(ref, facts):
        enough = False
        thin_why = (f"대회를 알아보지 못했다 — 받은 표기 "
                    f"`{ref.competition or '없음'}`"
                    + (f" · {thin_why}" if thin_why else ""))
        notes.append(f"🔴🔴 **대회 미식별 — 등급 전부 보류**(받은 표기 "
                     f"`{ref.competition or '없음'}`) · 운영자 알림으로 보냈다")
        _tell_operator(ref)
    if not enough:
        notes.append(f"🔴 §7 R5 **자료 얇음 — 등급 없음**({thin_why}) · "
                     f"시나리오·대입·방향은 그대로 낸다")
    cap, cap_why = _cap(ref, facts, variables)
    notes.append(cap_why)
    evals: list[MarketEval] = []
    for old, line in lines:
        got = _one(old, line, ref, cap=cap, enough=enough,
                   started=started, state=state, dist=dist)
        if got is not None:
            evals.append(got)
    evals = _same_direction_cap(evals, notes=notes)
    if src == "none":
        # 🔴🔴 **보드가 없으면 등급을 안 붙인다**(지시 ②) — `보류(보드 없음)`
        #    ⚠️ 생존·상한·마크는 **그대로 보인다**(참고표로 쓸 수 있게).
        evals = [e.model_copy(update={
            "grade": "보류",
            "why": (f"{e.why} · 보드 없음 — 걸 줄이 없어 **보류**").strip(" ·")})
            for e in evals]
        notes.append("🔴 등급 **전부 보류** — 사용자 보드도 피드 메인 라인도 없다")
    state.set("markets_graded", sum(1 for e in evals
                                    if e.grade not in ("자료부족", "보류")))
    # ⚠️ **방향은 여기서 안 센다** — 종전엔 시나리오 무게로 셌고(§1 처분으로
    #    시나리오가 없다), 지금은 `pipeline._direction` 이 **확률**로 센다.
    return Judgement(evals=evals, direction="",
                     board_source=src,
                     conclusion=_conclusion(evals, started=started,
                                            enough=enough, thin_why=thin_why,
                                            source=src),
                     triggers=_triggers(variables, ref),
                     started=started, started_why=started_why, notes=notes)


# ══════════════════════════════════════════════════════════════════
# 보드 줄 — 🔴 있으면 보드만, 없으면 기준선 복수(§6-c-3)
# ══════════════════════════════════════════════════════════════════


def _lines(ref: MatchRef, facts: Facts, *, board: Board | None,
           notes: list[str], source: str = "", dist: dict | None = None,
           ref_names: tuple[str, str] = ("", "")
           ) -> tuple[list[tuple[Any, BoardLine]], str]:
    """🔴 `(옛 Market, v6 BoardLine)` 짝 목록과 **출처**. ⚠️ 변환을 한 곳에 둔다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **출처 순서**(사용자 지시 2026-10-07 ①)
    ══════════════════════════════════════════════════════════════════

    > 사용자 보드 **>** 피드의 메인 라인(총점·핸디 `point` 그대로) **>** 없음.

    🔴 돌려주는 둘째 값이 그 출처다(`user_board`·`feed`·`none`). ⚠️ `none` 이면
       기준선 표는 **참고**이고 등급은 전부 `보류` 다(지시 ②) — 그 판단은 `_one` 이
       아니라 `run` 이 한다(한 가지 일은 한 곳).
    """
    from app import survive
    from app.core.stages.s5_verify import game_of
    if board is not None and board.lines:
        notes.append(f"보드 {len(board.lines)}줄을 받았다({source or '출처 미상'})"
                     f" — **보드 줄만** 센다")
        out: list[tuple[Any, BoardLine]] = []
        for line in board.lines:
            old = _old_of(line, ref)
            if old is None:
                # 🔴 못 옮긴 줄은 **이름으로 남긴다**(#3 조용한 0 금지)
                notes.append(f"🔴 보드 줄 `{line.market}/{line.side}` 를 대입 꼴로 "
                             f"못 옮겼다 — 그 줄은 **세지 않았다**")
                continue
            out.append((old, line))
        return out, (source or "user_board")
    # 🔴 보드가 **없다** — 기준선 목록은 **참고용**으로만 만든다(등급을 붙이지 않는다)
    notes.append("🔴 **보드가 없다** — 기준선 대입표는 **참고**이고 등급은 "
                 "전부 `보류` 다(사용자 지시 2026-10-07 ②)")
    # 🔴🔴 **강팀은 격자가 댄다**(§1 처분 — 시나리오 무게가 없다) — §11 과 **같은
    #    함수**를 쓴다(`underdog.read`). ⚠️ 격자가 없으면 강팀도 없다(핸디 줄 없음).
    fav = dog = ""
    fav_why = "🔴 **격자가 없다** — 강팀을 못 고른다(핸디 줄을 만들지 않는다)"
    if dist:
        from app.core import underdog as _ud
        said_read = _ud.read(dict(dist), home_name=ref_names[0],
                             away_name=ref_names[1])
        if said_read.fav:
            fav, dog = said_read.fav_name, said_read.dog_name
            fav_why = f"강팀은 **격자**가 골랐다 — {said_read.why}"
        else:
            fav_why = said_read.why
    got, said = survive.our_board(game_of(ref), dict(facts.standings) or None,
                                  fav=fav, dog=dog, fav_why=fav_why)
    notes += [str(x) for x in said]
    out: list[tuple[Any, BoardLine]] = []
    for m in got:
        line = _new_of(m)
        if line is not None:
            out.append((m, line))
        else:
            notes.append(f"🔴 마켓 `{getattr(m, 'market_type', '?')}` 를 v6 "
                         f"꼴로 못 옮겼다 — 그 줄은 **세지 않았다**(#3)")
    return out, "none"


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


def _old_of(line: BoardLine, ref: MatchRef | None = None) -> Any:
    """🔴 `BoardLine` → 옛 `Market`(대입 산수가 그 타입을 받는다).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **핸디·팀총점의 `team` 은 팀 이름이어야 한다**(실측 2026-10-06)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 보드 파서는 쪽을 `home`·`away` 로 적는데 `survive.apply` 는 **팀 이름**으로
       센다 — `team="home"` 이면 `'?'` 가 돌아와 그 줄이 **카드에서 사라졌다**
       (사용자 보드의 `핸디 -0.5` 가 대입 표에 안 보였다 · 9차 ③ 점검표).
    🔴 그래서 `ref` 로 **이름으로 바꿔** 넘긴다. ⚠️ `ref` 가 없으면 옛 꼴 그대로다
       (그때는 그 줄이 사라지고, 사유가 남는다).
    """
    from app.types import Market as OldMarket
    back = {("win", "home"): "home", ("win", "away"): "away",
            # 🔴🔴 **피드가 무승부를 `win/draw` 로 준다**(네 층 §2-5) — 보드 파서는
            #    `draw/""` 로 적는다. ⚠️ 그 꼴을 안 적어 둬서 네이션스리그 라이브
            #    실행이 통째로 죽었다(실측 2026-10-06: `market_type='win'` 거부).
            ("win", "draw"): "draw", ("draw", ""): "draw",
            ("draw", "draw"): "draw",
            ("unbeaten", "home"): "home_dc", ("unbeaten", "away"): "away_dc"}
    mt = back.get((line.market, line.side))
    if mt:
        return OldMarket(market_type=mt)
    if line.market == "win":
        # 🔴 모르는 쪽 이름이 온 `win` 줄은 **버린다** — 옛 타입에 `win` 이 없다
        return None
    team = str(line.side)
    if ref is not None and team in ("home", "away"):
        team = ref.home_name if team == "home" else ref.away_name
    return OldMarket(market_type=line.market, team=team, line=line.point)


# ══════════════════════════════════════════════════════════════════
# 대입 · 생존 · 등급
# ══════════════════════════════════════════════════════════════════


def _one(old: Any, line: BoardLine, ref: MatchRef, *, cap: float,
         enough: bool, started: bool, state: RunState,
         dist: dict | None = None) -> MarketEval | None:
    """🔴 마켓 한 줄 — **생존은 시뮬 분포 하나에서** 온다(F5/R7).

    🔴🔴 §1 처분(2026-10-12 셋째): **시나리오가 없다**. 종전에는 시나리오마다
       기호(`marks`)를 찍고 그 무게로 생존을 셌다 — 그 길은 *"확률이 없을 때 도는
       다른 모형"* 이었고 지금은 **격자 하나**가 그 일을 한다.
    ⚠️ 분포가 없으면 **보류**다(확률 없이 등급을 붙이지 않는다).
    """
    from app import survive
    if not dist:
        state.note(f"s7 `{survive.name_of(old)}` — 🔴 **시뮬 분포가 없다** → "
                   f"생존·등급 **보류**")
        return MarketEval(line=line, survival=0.0, cap=cap, grade="보류",
                          why="🔴 보류 — 확률 없음(시뮬 분포가 없다)")
    survival = round(survive.from_dist(
        old, dist, home=ref.home_name, away=ref.away_name,
        sport=ref.sport), 4)
    grade = _grade(survival, cap=cap, enough=enough, started=started)
    return MarketEval(line=line, survival=survival, cap=cap, grade=grade)


def _grade(survival: float, *, cap: float, enough: bool,
           started: bool) -> Grade:
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **3d 반증 판정** — 수정 지시서 2026-10-12 [3d]
# ══════════════════════════════════════════════════════════════════
#
# > 판정 칸 = 기존 등급 계산 결과 **위에** 반증 규칙을 얹는다:
# >   모든 조건 "확인-무너짐 없음" → 간다
# >   "미확인" 하나 이상, hard 무너짐 없음 → 조건부 · 미확인 조건을 방아쇠로 자동 등록
# >   hard 무너짐 1개 이상 → 접는다(등급 없음)
# >   soft 무너짐만 → 한 단계↓
# > 확률 불변(C2). 시장(V6)은 이 판정에 안 들어간다(C12).

#: 🔴 등급 사다리 — `_grade_by_check` 와 **같은 목록**이다(사본이면 한쪽만 고쳐진다)
BREAK_LADDER: tuple[str, ...] = ("낸다", "소액", "소액하단", "없음")


# ⚠️ **`by_breaks` 는 지웠다** — ㉒ 반증 판정이 §1 처분으로 **§14 판정
#    행동**(이변 경고·InfoQ)으로 흡수됐다(지시서 2026-10-12 셋째).
#    🔴 등급 사다리 `BREAK_LADDER` 는 **남는다** — `infoquality`·`upset`
#    이 그 한 목록을 쓴다(사본 금지).
def _tell_operator(ref) -> None:
    """🔴 §2 마지막 줄 — **운영자 알림에 받은 표기를 보낸다**(다음에 표에 넣게).

    ⚠️ 실패해도 **카드를 막지 않는다** — 알림은 곁딸린 일이다.
    """
    try:
        from app import auditlog
        auditlog.unknown_competition(str(ref.competition or ""),
                                     match=str(ref.id or ""))
    except Exception:                                       # noqa: BLE001
        pass


def _enough(variables: list[Variable]) -> tuple[bool, str]:
    """🔴 §7 R5 — *"변수 3개 미만·반대 방향 0개면 자료 부족."* **등급만** 거둔다.

    🔴 수는 `scenarios.MIN_VARIABLES`·`MIN_DIRECTIONS` 가 든다(#1 사본 금지).
    ⚠️ **시나리오 칸은 걷었다**(§1 처분 2026-10-12 셋째) — 종전에는 *"변수가 적고
       시나리오도 적으면 생존 1.0 이 공짜"* 를 그 수로 셌다. 🔴 지금 생존은 **격자**
       에서 오므로 *"죽을 자리"* 라는 개념 자체가 없다(격자가 모든 스코어를 센다).
    """
    from app import scenarios
    # 🔴 **승패 방향으로만 센다**(사용자 지시 2026-10-06 ④)
    sides = {v.favors for v in variables if v.favors in ("home", "away")}
    if len(variables) < scenarios.MIN_VARIABLES or \
            len(sides) < scenarios.MIN_DIRECTIONS:
        return False, (f"방향 있는 변수 {len(variables)}개(최소 "
                       f"{scenarios.MIN_VARIABLES}) · 방향 {len(sides)}종"
                       f"(최소 {scenarios.MIN_DIRECTIONS})")
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


# ⚠️ **`_direction` 은 지웠다** — 방향을 **시나리오 무게**로 세던 함수다.
#    §1 처분으로 시나리오가 없고, 방향은 `pipeline._direction` 이 **확률**로
#    센다(문장 꼴은 `survive.direction_line` 하나다 · 사본 금지).
def _conclusion(evals: list[MarketEval], *, started: bool, enough: bool,
                thin_why: str, source: str = "") -> str:
    """🔴 결론 — **죽는 시나리오를 함께** 적는다(`✗` 와 `△` 둘 다 · §2-1).

    🔴 보드가 없으면(출처 `none`) 결론은 *"보드를 주면 판정"* 으로 끝난다(지시 ②).
    """
    from app import survive
    if source == "none":
        best = max(evals, key=lambda e: e.survival, default=None)
        return ("⏸ **보류 — 보드가 없다.** 평가할 마켓 줄이 없어 등급을 붙이지 "
                "않는다(아래 표는 **참고**다"
                + (f" · 가장 두꺼운 줄 {best.line.market} {best.line.side} "
                   f"{best.survival:.3f}" if best else "")
                + ") → 🔴 **보드를 주면 판정**한다")
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **사람이 읽는 문장**(축구 완성 지시서 §5 블록 10)
        # ══════════════════════════════════════════════════════════════
        #
        #  > "확정 XI 에 김민재가 있으면 R1 이 사라져 → 다시 센다(T-60, 19:00 KST)".
        #  > `player:{star} in XI` 같은 **내부 표기를 그대로 찍지 않는다.**
        #
        #  ⚠️ 실측 2026-10-06 카드가 그 내부 표기를 그대로 찍었다.
        who = str(v.target or "그 선수")
        # 🔴 **확정 XI 기준 T-60** — 머리글 재분석 시각과 **같은 기준**이다
        #    (사용자 지시 2026-10-07 재가중 ③). ⚠️ 세포가 깨는 시각(T-360)이 아니다 —
        #    그것은 *"검색을 도는 때"* 이고 이 줄은 *"확정 XI 를 보는 때"* 다.
        when = triggers.xi_when(ref.kickoff_utc)
        out.append(f"{_CIRCLED[len(out)]} 확정 XI 에 **{who}** 가 "
                   f"{'있으면' if v.type in _ABSENT else '없으면'} `{v.id}` 가 "
                   f"사라져 → 다시 센다 · {when}")
        if len(out) >= 4:
            break
    return out
