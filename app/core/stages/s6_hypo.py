"""🔴🔴 **v6 s6 — 가설·시나리오.** `list[Variable] → HypoSet`(§5).

지시서 §5 s6:

> DeepSeek 단계 3: 입력은 `usable_as_basis=True` 변수만 **근거 목록**으로, 나머지는
> `context_only` 로. 출력 `HypoOut`(가설 문장+`var_ids`, 시나리오
> `outcomes`·`driver_vars`·`mechanism`). **코드 검사**: `driver`·`var_ids` 가 근거
> 목록 밖이면 그 줄 버림(사유 `cited_excluded`/`unknown_var`). 필수형 보강(실점
> 동반·대량득점·회귀·난타전·90분 무승부·해석 규칙 `requires_scenario`). 단계 4
> 반증: **추가만**, 생존율 상승 금지. `strength` = 유형별 최댓값 합(weights).

🔴 **문장을 고쳐 쓰지 않는다** — 제외 번호를 인용했으면 그 줄을 **버린다**(§4-2).
   고쳐 쓰면 모델이 한 말과 우리가 한 말이 섞여 누가 틀렸는지 못 가린다.
"""
from __future__ import annotations

import json

from app.core.schema import (Drop, DropReason, Facts, Hypothesis, HypoLine,
                             HypoOut, HypoSet, LlmFail, MatchRef, RedTeamLine,
                             RedTeamOut, Scenario, ScenarioOut, Variable)
from app.core.state import RunState

#: 🔴 시나리오 글자 — `A`, `B`, … ⚠️ 모델이 적은 id 는 **쓰지 않는다**(겹친다).
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def run(ref: MatchRef, facts: Facts, variables: list[Variable], *,
        state: RunState) -> HypoSet:
    """🔴 가설·시나리오. ⚠️ LLM 이 안 돌아도 **필수형 보강은 돈다**(카드는 나온다)."""
    basis = [v for v in variables if v.usable_as_basis]
    ctx = [v for v in variables if not v.usable_as_basis]
    if ctx:
        state.note(f"s6 §4-1 — 근거 불가 변수 {len(ctx)}개를 `context_only` 로 "
                   f"보냈다({', '.join(v.id for v in ctx)}) · 그 번호를 인용한 "
                   f"줄은 **버려진다**")
    said = _ask(ref, facts, basis, ctx, state=state)
    drops: list[Drop] = []
    hypos: list[Hypothesis] = []
    scen: list[Scenario] = []
    if said is not None:
        hypos = _clean_hypos(said.hypotheses, basis=basis, ctx=ctx,
                             drops=drops)
        scen = _clean_scenarios(said.scenarios, basis=basis, ctx=ctx,
                               drops=drops, variables=variables)
    scen = _required(ref, facts, scen, variables, state=state)
    scen = [s.model_copy(update={"strength": _strength(s, variables)})
            for s in scen]
    red = _redteam(ref, scen, basis, state=state)
    state.set("scenarios", len(scen))
    return HypoSet(hypotheses=hypos, scenarios=scen, redteam=red, drops=drops)


# ══════════════════════════════════════════════════════════════════
# 단계 3 — DeepSeek
# ══════════════════════════════════════════════════════════════════


def system_prompt() -> str:
    """🔴 규칙 글 — 내용은 옛 `hypo.system_prompt` 에서 **옮겨 썼다**(§6).

    ⚠️ 옛 글의 *"출력은 JSON 하나다 …"* 꼬리는 **걷었다** — 스키마가 강제한다(§6
       *"프롬프트에 enum 목록 적는 코드"* 를 지운다).
    """
    return (
        "너는 스포츠 경기 하나의 가설과 시나리오를 쓴다. 웹에 닿을 수 없다.\n"
        "\n"
        "1. 🔴 너는 **사실을 만들지 않는다.** `variables` 와 `facts` 에 없는 "
        "사실은 쓰지 않는다. 모르면 시나리오에 넣지 않는다.\n"
        "1b. 🔴 `context_only` 의 변수는 **번호로 인용하지 마라. 근거로 쓰지 "
        "마라.** 표본이 모자라거나 출처가 약한 것들이다 — 맥락으로만 알아라. "
        "⚠️ 그 번호를 적은 문장·시나리오는 **버려진다.**\n"
        "2. 팀별 가설: `team` 은 **`home`·`away` 두 글자**다(팀 이름이 아니다). "
        "`reasons` 는 **이긴다면 왜**, `breaks` 는 **무너지는 조건**이다. 항목마다 "
        "**한 문장**(`text`)과 **근거 변수 번호**(`var_ids`)를 함께 적는다 — "
        "⚠️ 번호만 적으면 안 된다.\n"
        "3. 시나리오 4~6개. 각각 `driver_vars`(변수 번호), `mechanism`(그 변수들이 "
        "어떻게 작동해 그 결과가 나오는지 1~2문장), `outcomes`(스코어 1~2개를 "
        "`[홈, 원정]` 꼴로).\n"
        "4. 전부 같은 방향이면 안 된다 — 각 팀이 이기는 시나리오가 **적어도 "
        "하나씩** 있어야 한다.\n"
        "5. 맞대결 기록은 메커니즘(세트피스·역습 방식)이 있을 때만 driver 로 쓰고, "
        "**다른 시나리오를 누르는 근거로 쓰지 않는다.**\n"
        "6. 🔴 **등급·확률·승자·배당·추천 단어를 쓰지 않는다** — 그것은 코드가 "
        "수로 정한다.")


#: 🔴 폼에서 **보내는 칸만** — 이름을 적어 둔다(#1: 코드가 고르는 칸을 숨기지 않는다)
_FORM_KEYS = ("last5", "recent_scored_avg", "recent_trimmed_avg",
              "recent_avg_goals", "streak_scored", "streak_unbeaten",
              "streak_winless", "streak_clean_sheet", "rest_days")
#: 🔴 맞대결은 **요약만** — 경기 목록·URL 은 안 보낸다
_H2H_KEYS = ("count", "summary", "window_avg_goals", "sample_weight")


def _payload(ref: MatchRef, facts: Facts, basis: list[Variable],
             ctx: list[Variable]) -> str:
    """🔴 보내는 입력 — **근거와 맥락이 갈려 있다**(§4-1) · **얇게** 보낸다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **왜 추려 보내나** — 실측 2026-10-06(원장)
    ══════════════════════════════════════════════════════════════════

    | 입력 토큰 | 결과 |
    |---|---|
    | 4,233 | `stop` · 출력 5,345(추론 4,093) |
    | 3,845 | 🔴 **`length`** · 출력 8,000이 **전부 추론**(content 0자) |

    🔴 상한을 올려 고치는 것은 **§9 금지**다. ⚠️ 그리고 DeepSeek 은
       `reasoning_effort` 를 **무시한다**(실측: `''`·`minimal`·`low` 셋 다 같은
       추론량으로 상한을 다 썼다 — 사소한 질문에서도 그랬다).
    🔴 그래서 남은 지렛대는 **입력 크기**다. 폼 사실이 경기 목록(`sequence`)과
       맞대결 **URL 까지** 실어 보내고 있었다 — 가설에 쓰이지 않는 것들이다.
    """
    def row(v: Variable) -> dict:
        return {"id": v.id, "type": v.type, "subject": v.subject,
                "favors": v.favors, "claim": v.claim[:200], "weight": v.weight}

    def form(raw: object) -> dict:
        box = dict(raw) if isinstance(raw, dict) else {}
        return {k: box[k] for k in _FORM_KEYS if k in box}

    box = {
        "match": {"home": ref.home_name, "away": ref.away_name,
                  "home_key": ref.home, "away_key": ref.away,
                  "competition": ref.competition_short,
                  "match_format": facts.match_format, "sport": ref.sport},
        "variables": [row(v) for v in basis],
        "context_only": [row(v) for v in ctx],
        "facts": {"standings": facts.standings,
                  "recent": {k: form(v) for k, v in facts.recent.items()},
                  "h2h": {k: v for k, v in facts.h2h.items()
                          if k in _H2H_KEYS}},
        "required_types": sorted(_required_names(facts))}
    return json.dumps(box, ensure_ascii=False, default=str)


def _ask(ref: MatchRef, facts: Facts, basis: list[Variable],
         ctx: list[Variable], *, state: RunState) -> HypoOut | None:
    from app.core import llm
    if not basis:
        # 🔴 **근거 변수가 0개면 부르지 않는다** — 부르면 모델이 지어낸다(§4-1)
        state.note("s6 근거 변수 0개 — DeepSeek 를 부르지 않았다(필수형 보강만 "
                   "돈다 · 지어낸 가설보다 **없는 것**이 낫다)")
        return None
    said = llm.ask(provider="deepseek", purpose="hypo", out=HypoOut,
                   state=state,
                   messages=[llm.Message(role="system",
                                         content=system_prompt()),
                             llm.Message(role="user",
                                         content=_payload(ref, facts, basis,
                                                          ctx))])
    if isinstance(said, LlmFail):
        state.drop("s6/hypo", said.reason, said.detail[:120])
        return None
    state.note(f"s6 가설 {len(said.hypotheses)}팀 · 시나리오 "
               f"{len(said.scenarios)}개를 받았다")
    return said


def _clean_hypos(rows: list[Hypothesis], *, basis: list[Variable],
                 ctx: list[Variable], drops: list[Drop]) -> list[Hypothesis]:
    """🔴 §4-2 안전망 — **제외 번호를 인용한 문장은 버린다**(고쳐 쓰지 않는다)."""
    ok_ids = {v.id for v in basis}
    bad_ids = {v.id for v in ctx}
    out: list[Hypothesis] = []
    for row in rows:
        kept: dict[str, list[HypoLine]] = {"reasons": [], "breaks": []}
        for field_, lines in (("reasons", row.reasons), ("breaks", row.breaks)):
            for line in lines:
                cited = set(line.var_ids)
                hit = sorted(cited & bad_ids)
                if hit:
                    drops.append(Drop(what=f"s6/{row.team}/{field_}",
                                      reason=DropReason.CITED_EXCLUDED,
                                      detail=f"{','.join(hit)} — 버렸다: "
                                             f"{line.text[:60]}"))
                    continue
                unknown = sorted(cited - ok_ids)
                if unknown:
                    drops.append(Drop(what=f"s6/{row.team}/{field_}",
                                      reason=DropReason.UNKNOWN_VAR,
                                      detail=f"{','.join(unknown)} — 버렸다: "
                                             f"{line.text[:60]}"))
                    continue
                kept[field_].append(line)
        out.append(Hypothesis(team=row.team, reasons=kept["reasons"],
                              breaks=kept["breaks"]))
    return out


def _clean_scenarios(rows: list[ScenarioOut], *, basis: list[Variable],
                     ctx: list[Variable], drops: list[Drop],
                     variables: list[Variable]) -> list[Scenario]:
    """🔴 §4-2 — 시나리오는 **번호만 빼고**, 남은 driver 가 0개면 버린다."""
    ok_ids = {v.id for v in basis}
    bad_ids = {v.id for v in ctx}
    out: list[Scenario] = []
    for i, row in enumerate(rows):
        cited = list(row.driver_vars)
        kept = [x for x in cited if x in ok_ids]
        for x in cited:
            if x in bad_ids:
                drops.append(Drop(what=f"s6/scenario/{row.id}",
                                  reason=DropReason.CITED_EXCLUDED,
                                  detail=f"driver `{x}` 를 뺐다"))
            elif x not in ok_ids:
                drops.append(Drop(what=f"s6/scenario/{row.id}",
                                  reason=DropReason.UNKNOWN_VAR,
                                  detail=f"driver `{x}` 는 변수 목록에 없다"))
        outs = [(int(a), int(b)) for a, b in row.outcomes]
        if not kept or not outs:
            drops.append(Drop(
                what=f"s6/scenario/{row.id}",
                reason=(DropReason.UNKNOWN_VAR if not kept
                        else DropReason.NO_DOC),
                detail=("남은 driver 가 0개다" if not kept else "스코어가 없다")))
            continue
        out.append(Scenario(id=_LETTERS[i % len(_LETTERS)], outcomes=outs,
                            driver_vars=kept, mechanism=row.mechanism,
                            type=_kind_of(outs), added_by="deepseek"))
    return out


def _kind_of(outs: list[tuple[int, int]]) -> str:
    """🔴 스코어가 말하는 갈래 — 섞이면 `open`(한쪽으로 적지 않는다)."""
    marks = {("home_win" if h > a else "away_win" if a > h else "draw")
             for h, a in outs}
    return marks.pop() if len(marks) == 1 else "open"


# ══════════════════════════════════════════════════════════════════
# 필수형 보강 — 🔴 표는 `config/scenario_required.yaml` 하나다(#1)
# ══════════════════════════════════════════════════════════════════


def _required_names(facts: Facts) -> set[str]:
    """🔴 그 경기에 **조건이 맞는** 필수형 이름들 — 표가 원본이다."""
    from app import rules, scenarios
    out: set[str] = set()
    for name, row in rules.required_forms().items():
        if str(row.get("on_missing")) != "추가":
            continue
        if row.get("always"):
            out.add(name)
            continue
        if row.get("when_formats"):
            # 🔴 형식 목록은 `scenario_rules.draw_90` 하나가 든다(#1)
            if facts.match_format in scenarios.draw_formats():
                out.add(name)
            continue
        out.add(name)
    return out


def _required(ref: MatchRef, facts: Facts, scen: list[Scenario],
              variables: list[Variable], *, state: RunState) -> list[Scenario]:
    """🔴🔴 **필수형 보강** — 없으면 코드가 템플릿으로 넣는다(`added_by="code"`).

    ⚠️ 표의 `on_missing: 실패` 줄은 **만들지 않는다** — 근거 없는 시나리오는 우리가
       만든 이야기다(#4). 그 사실을 사유로 남기고 s7 이 등급을 거둔다.
    """
    from app import rules, scenarios as _sc
    out = list(scen)
    forms = rules.required_forms()
    names = _required_names(facts)
    # ── ⑦ 90분 무승부형 — **형식이 단판일 때만**(표의 `when_formats`)
    if "90분_무승부형" in names:
        want = [p for p in (_pair(x) for x in _sc.draw_scores())
                if p is not None]
        have = _all_scores(out)
        if want and not any(p in have for p in want):
            out.append(Scenario(
                id=_next_id(out), outcomes=want[:2],
                driver_vars=[], type="draw_90", added_by="code",
                mechanism=(f"🔴 필수형(90분 무승부) — 형식이 "
                           f"`{facts.match_format}` 다(단판). 90분 무승부는 "
                           f"**갈래**이고, 없으면 `언더`·`무승부` 가 공짜로 산다. "
                           f"⚠️ 마켓 대입은 **90분 기준**이다")))
            state.note(f"s6 필수형 보강 — 90분 무승부형({facts.match_format})")
    # ── ② 대량득점형 — 방아쇠는 표가 든다. ⚠️ 못 잰 방아쇠는 **이름으로** 남긴다
    if "대량득점형" in names:
        row = dict(forms.get("대량득점형") or {})
        got, why = _blowout(ref, facts, variables, row)
        if got and not any(sum(p) >= got for p in _all_scores(out)):
            out.append(Scenario(
                id=_next_id(out), outcomes=[(got - 1, 1)], driver_vars=[],
                type="blowout", added_by="code",
                mechanism=f"🔴 필수형(대량득점) — {why}"))
            state.note(f"s6 필수형 보강 — 대량득점형({why})")
        else:
            state.note(f"s6 필수형 대량득점 — 넣지 않았다: {why}")
    # ── ④ 핸디 대응형 — `±N.5` 의 반대는 상대가 **N+1 차**로 이기는 것
    for ln in _handicap_lines():
        need = int(ln) + 1
        if any(abs(h - a) >= need for h, a in _all_pairs(out)):
            continue
        out.append(Scenario(
            id=_next_id(out), outcomes=[(need, 0)], driver_vars=[],
            type="blowout", added_by="code",
            mechanism=(f"🔴 필수형(핸디 ±{ln} 대응) — 그 줄의 반대는 상대가 "
                       f"**{need}점 차**로 이기는 것이다. 없으면 `+{ln}` 가 죽을 "
                       f"자리가 없어 1.0 을 받는다")))
        state.note(f"s6 필수형 보강 — 핸디 ±{ln} 대응({need}점 차)")
    # ── ③ 회귀 반전형 — 🔴 `regression` 유형이 §4 표에 **없다**(실측)
    if any("regression" in str(k) for k in rules.unmapped_types()):
        state.note("s6 필수형 회귀_반전형 — 🔴 `regression` 유형이 §4 표에 **없다**"
                   "(`trigger_conditions.unmapped`) → 이 줄은 발동하지 않는다")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **① 우세팀 실점 동반형은 맨 끝이다** — 실측 2026-10-06
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음엔 맨 앞에 뒀다 — 그래서 **코드가 뒤에 더한 승리 갈래**(핸디 대응형의
    #     `2-0`·대량득점형)에는 실점 동반형이 **안 붙었다**. 표의 뜻은 *"우세팀 승
    #     시나리오가 있으면 그 승리가 **실점을 동반하는 꼴**도 있어야 한다"* 이고,
    #     그 승리가 누가 만든 것인지는 묻지 않는다.
    #  🔴 그래서 **다 더한 뒤에** 한 번 본다.
    # ── ① 우세팀 실점 동반형 — `2-0` → `2-1`(이긴 쪽 점수 유지 · 실점 1)
    if "우세팀_실점_동반형" in names:
        add: list[tuple[int, int]] = []
        for s in out:
            for h, a in s.outcomes:
                if h == a:
                    continue
                got = (h, 1) if h > a else (1, a)
                if got[0] != got[1] and got not in _all_scores(out):
                    add.append(got)
        if add:
            out.append(Scenario(
                id=_next_id(out), outcomes=sorted(set(add))[:2],
                driver_vars=[], type="conceding", added_by="code",
                mechanism=("🔴 필수형(우세팀 실점 동반) — 우세팀이 이기면서 한 점을 "
                           "준다. ⚠️ 이 갈래가 없으면 `언더`·`클린시트` 가 **공짜로** "
                           "1.0 을 받는다(표: 우세팀_실점_동반형)")))
            state.note(f"s6 필수형 보강 — 우세팀 실점 동반형 {sorted(set(add))[:2]}")
    # ── ⑤ 반대 방향 · ⑥ 양방향 변수 — `on_missing: 실패` 다(만들지 않는다)
    for name in ("반대_방향", "양방향_변수"):
        said = _fail_form(name, out, variables)
        if said:
            state.note(f"s6 필수형 `{name}` **실패** — {said}")
    low = rules.required_min()
    if len(out) < low:
        state.note(f"s6 시나리오 {len(out)}개 < 최소 {low}개(§6-2) — "
                   f"**지어내 채우지 않는다**(자료 부족이다)")
    return out


def _fail_form(name: str, scen: list[Scenario],
               variables: list[Variable]) -> str:
    """🔴 `on_missing: 실패` 인 두 줄 — **만들 수 없다**. 사유 글자만 낸다."""
    from app import rules
    row = dict(rules.required_forms().get(name) or {})
    if name == "반대_방향":
        kinds = {s.type for s in scen}
        if "home_win" in kinds and "away_win" in kinds:
            return ""
        return (f"두 팀이 각각 이기는 시나리오가 **둘 다** 있어야 한다"
                f"(있는 갈래 {sorted(kinds) or '없음'}) — 근거 없는 반대 방향은 "
                f"지어내지 않는다")
    want = {str(t) for t in (row.get("types") or ())}
    miss = []
    for v in variables:
        if v.type not in want:
            continue
        on = [s.id for s in scen if v.id in s.driver_vars]
        if len(on) < 2:
            miss.append(f"{v.id}({v.type}) → 붙은 시나리오 {on or '없음'}")
    return ("양방향 변수는 **두 시나리오에 모두** 붙어야 한다: "
            + "; ".join(miss)) if miss else ""


def _blowout(ref: MatchRef, facts: Facts, variables: list[Variable],
             row: dict) -> tuple[int, str]:
    """🔴 대량득점 방아쇠 — 표의 조건을 **잴 수 있는 것만** 재고 나머지는 이름으로.

    ⚠️ 못 잰 방아쇠를 `False` 로 적으면 *"조건이 아니다"* 와 *"재지 못했다"* 가
       같아진다(#3 조용한 0 금지).
    """
    goals = int((row.get("thresholds") or {}).get(ref.sport) or 0)
    if not goals:
        return 0, f"`{ref.sport}` 의 대량 기준이 표에 없다(지어내지 않는다)"
    trig = dict(row.get("triggers") or {})
    absent = [v for v in variables if str(v.type).startswith("absence")]
    need = int(trig.get("absence_count") or 0)
    if need and len(absent) >= need:
        return goals, (f"수비·공격 결장 변수 {len(absent)}개 ≥ {need}개 · 대량 "
                       f"기준 {goals}골")
    unmeasured = [k for k in ("rank_gap", "last_loss_margin",
                              "both_scoring_streak")
                  if k in trig and not _has_fact(k, facts)]
    return 0, (f"결장 변수 {len(absent)}개 < {need}개 · 못 잰 방아쇠 "
               f"{unmeasured or '없음'}(순위 {len(facts.standings)}칸 · 폼 "
               f"{len(facts.recent)}팀)")


def _has_fact(key: str, facts: Facts) -> bool:
    """🔴 그 방아쇠를 **잴 자료가 있나** — 없으면 못 쟀다고 적는다."""
    if key == "rank_gap":
        return bool(facts.standings)
    return bool(facts.recent)


def _handicap_lines() -> list[float]:
    """🔴 기준선 둘(`0.5`·`1.5`) — 수는 `survive.OUR_HANDICAP_LINES` 가 든다(#1)."""
    from app import survive
    return [float(x) for x in survive.OUR_HANDICAP_LINES]


def _all_scores(scen: list[Scenario]) -> list[tuple[int, int]]:
    return [p for s in scen for p in s.outcomes]


def _all_pairs(scen: list[Scenario]) -> list[tuple[int, int]]:
    return _all_scores(scen)


def _pair(said: object) -> tuple[int, int] | None:
    """🔴 `"1-1"` → `(1, 1)`. ⚠️ 못 읽으면 `(0, 0)` 이 아니라 **`None`** 이다.

    ⚠️ `(0, 0)` 으로 때우면 *"못 읽었다"* 가 **0-0 무승부**가 된다(조용한 0 금지).
    """
    bits = str(said or "").split("-")
    if len(bits) != 2 or not all(b.strip().isdigit() for b in bits):
        return None
    return (int(bits[0]), int(bits[1]))


def _next_id(scen: list[Scenario]) -> str:
    used = {s.id for s in scen}
    for ch in _LETTERS:
        if ch not in used:
            return ch
    return f"Z{len(scen)}"


def _strength(s: Scenario, variables: list[Variable]) -> float:
    """🔴🔴 `strength` = **유형별 최댓값 합**(§5 s6 · weights).

    ⚠️ 같은 유형 변수 셋이 같은 시나리오를 밀면 그것은 **세 배로 센 근거가
       아니다**(같은 종류의 말이다) — 그래서 유형마다 최댓값만 센다.
    🔴 근거 0개(코드 보강)는 **바닥**이다 — 0 이면 생존 계산에서 **사라진다**
       (실측 pn8: `strength 0` 인 갈래가 분모에서 빠져 언더가 1.0 이 됐다).
    """
    from app.survive import WEIGHT_FLOOR
    by_type: dict[str, float] = {}
    for v in variables:
        if v.id not in s.driver_vars:
            continue
        by_type[v.type] = max(by_type.get(v.type, 0.0), float(v.weight))
    got = round(sum(by_type.values()), 4)
    return got if got > 0 else float(WEIGHT_FLOOR)


# ══════════════════════════════════════════════════════════════════
# 단계 4 — 반증. 🔴 **추가만** 한다(생존율 상승 금지)
# ══════════════════════════════════════════════════════════════════


def _redteam(ref: MatchRef, scen: list[Scenario], basis: list[Variable], *,
             state: RunState) -> list[RedTeamLine]:
    """🔴 반증 — **줄만 더한다.** ⚠️ 시나리오를 지우거나 고치지 않는다(불변식 8).

    🔴 그래서 생존율은 **구조적으로 오를 수 없다** — 반증은 `MarketEval` 의 수에
       닿지 않고, 사람이 읽는 경고 줄로만 남는다.
    """
    from app.core import llm
    if not scen or not basis:
        # 🔴 **반증할 것이 없다** — 근거 변수가 0개면 코드 보강 시나리오뿐이고,
        #    그것을 반증해 달라고 물으면 모델이 **사실을 지어낸다**(§4-1 과 같은 길).
        state.note(f"s6 반증 — 부르지 않았다(시나리오 {len(scen)}개 · 근거 변수 "
                   f"{len(basis)}개)")
        return []
    box = {"match": {"home": ref.home_name, "away": ref.away_name},
           "scenarios": [{"id": s.id, "outcomes": s.outcomes,
                          "mechanism": s.mechanism,
                          "driver_vars": s.driver_vars} for s in scen],
           "variables": [{"id": v.id, "claim": v.claim} for v in basis]}
    said = llm.ask(
        provider="deepseek", purpose="redteam", out=RedTeamOut, state=state,
        messages=[
            llm.Message(role="system", content=(
                "너는 위 분석의 **반대편**을 쓴다. 각 줄은 어떤 마켓이 왜 위험한지 "
                "한 문장이다.\n"
                "🔴 시나리오를 **지우거나 고치지 않는다** — 네 말은 **추가**된다.\n"
                "🔴 등급·확률·추천 단어를 쓰지 않는다. 사실을 만들지 않는다.\n"
                "⚠️ `scenario_id` 는 위 목록의 글자이고, 해당 없으면 `null` 이다.")),
            llm.Message(role="user",
                        content=json.dumps(box, ensure_ascii=False))])
    if isinstance(said, LlmFail):
        state.drop("s6/redteam", said.reason, said.detail[:120])
        return []
    ids = {s.id for s in scen}
    out = [ln for ln in said.lines
           if ln.scenario_id is None or ln.scenario_id in ids]
    if len(out) != len(said.lines):
        state.note(f"s6 반증 — 모르는 시나리오를 가리킨 줄 "
                   f"{len(said.lines) - len(out)}개를 뺐다")
    state.note(f"s6 반증 {len(out)}줄(추가만 — 생존율에 닿지 않는다)")
    return out
