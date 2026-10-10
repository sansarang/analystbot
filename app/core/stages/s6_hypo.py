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
import string

from app.core.schema import (Drop, DropReason, Facts, Hypothesis, HypoLine,
                             HypoOut, HypoSet, LlmFail, MatchRef, RedTeamLine,
                             RedTeamOut, Scenario, ScenarioOut, Variable)
from app.core.state import RunState
#: 🔴 결장 계열 유형은 `compare` 가 든 **목록 하나**를 쓴다(사본 금지 · #1)
from app.core.compare import ABSENCE_TYPES

#: 🔴 시나리오 글자 — `A`, `B`, … ⚠️ 모델이 적은 id 는 **쓰지 않는다**(겹친다).
#  🔴 글자를 손으로 적지 않는다 — `.env` 계약이 **대문자 글자열을 환경변수 이름으로
#     읽어** 빨개졌다(실측 2026-10-06: `ABCDEFGHIJKLMNOPQRSTUVWXYZ` 를 키로 봤다).
_LETTERS = string.ascii_uppercase

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **입력을 더 줄인다**(사용자 지시 2026-10-07 재가중 ④)
# ══════════════════════════════════════════════════════════════════
#
# > 한국–우즈벡 `llm_truncated`: **상한을 올리지 말고 s6 입력을 줄인다** — 근거 변수
# > 상위 6개(무게 순)만, claim 은 80자로 자르고, 맥락 변수는 **이름만**.
#
# ⚠️ 실측 2026-10-07: 변수 10개(claim 200자)를 보내자 가설 호출이 **두 번 다**
#    `length` 로 잘렸다(출력이 전부 추론). 🔴 상한을 올리는 것은 §9 금지다.
#: 🔴 가설에 보낼 **근거 변수 상한** — 무게 순 상위 6개
BASIS_CAP = 6
#: 🔴 맥락 변수 상한 — **이름만** 보낸다(claim 을 안 보낸다)
CTX_CAP = 6
#: 🔴 claim 을 자르는 길이 — 80자
CLAIM_CUT = 80


#: 🔴🔴 **이 파일은 두 단계를 맡는다**(순서 재편 지시서 2026-10-10 다섯째):
#  `claims` = 단계 2(가설·신호 · **시뮬 전**) · `scenarios` = 단계 4-4(시나리오 ·
#  **시뮬 뒤**). ⚠️ 입구를 글자로 적어 둔다 — 계약이 이 선언을 본다.
STAGES = ("claims", "scenarios")


def claims(ref: MatchRef, facts: Facts, variables: list[Variable], *,
           state: RunState) -> HypoSet:
    """🔴🔴 **단계 2 — 가설만 세운다**(순서 재편 지시서 2026-10-10 다섯째).

    > 단계 2-2 가설(LLM 1회): 팀마다 *"이긴다면 왜"* 2~3개, *"무너지는 조건"*
    > 2~3개. 각 가설은 반드시 **시뮬레이션으로 확인할 수 있는 신호**를 단다.
    > 2-3 **시나리오는 여기서 만들지 않는다**(단계 4에서 시뮬 결과로 만든다).

    🔴 **입력에 확률이 없다** — 변수·사실뿐이다(`_payload`). 그것이 §계약
       *"단계 2 는 단계 3 결과를 입력으로 받지 않는다"* 다.
    ⚠️ 돌려주는 `HypoSet` 의 `scenarios` 는 **빈 목록**이다 — `scenarios()` 가
       시뮬 뒤에 채운다.
    """
    basis = [v for v in variables if v.usable_as_basis]
    ctx = [v for v in variables if not v.usable_as_basis]
    if ctx:
        state.note(f"s6 §4-1 — 근거 불가 변수 {len(ctx)}개를 `context_only` 로 "
                   f"보냈다({', '.join(v.id for v in ctx)}) · 그 번호를 인용한 "
                   f"줄은 **버려진다**")
    said = _ask(ref, facts, basis, ctx, state=state)
    drops: list[Drop] = []
    hypos: list[Hypothesis] = []
    if said is not None:
        hypos = _clean_hypos(said.hypotheses, basis=basis, ctx=ctx,
                             drops=drops)
        hypos = _clean_signals(hypos, drops=drops, state=state)
        if said.scenarios:
            # 🔴 §2-3 — 시나리오를 여기서 **안 쓴다**. ⚠️ 모델이 보내도 버리고
            #    그 사실을 적는다(#3 조용히 버리지 않는다).
            state.note(f"s6 §2-3 — 모델이 보낸 시나리오 {len(said.scenarios)}개를 "
                       f"**버렸다**(시나리오는 단계 4 에서 시뮬 분포로 만든다)")
    n_sig = sum(1 for h in hypos for line in [*h.reasons, *h.breaks]
                if line.signal is not None)
    state.note(f"s6 단계 2 — 가설 {len(hypos)}팀 · 신호 붙은 줄 {n_sig}개")
    return HypoSet(hypotheses=hypos, scenarios=[], redteam=[], drops=drops)


def _clean_signals(rows: list[Hypothesis], *, drops: list[Drop],
                   state: RunState) -> list[Hypothesis]:
    """🔴🔴 §2-2 계약 — **신호가 없거나 목록 밖 지표면 그 신호를 버린다**.

    🔴 줄 자체는 **남긴다** — 단계 4 가 `판단 불가` 로 세고 최종 평이 못 쓴다(§5).
       ⚠️ 줄을 지우면 *"가설이 없었다"* 와 *"검증 못 했다"* 가 섞인다(#3).
    """
    from app.core import signals as _sg
    out: list[Hypothesis] = []
    bad = 0
    for one in rows:
        box = {}
        for key in ("reasons", "breaks"):
            kept = []
            for line in (getattr(one, key, None) or []):
                said = _sg.bad_signal(line.signal)
                if said:
                    bad += 1
                    drops.append(Drop(where="s6/signal", reason="schema",
                                      detail=f"{said} · `{line.text[:40]}`"))
                    kept.append(line.model_copy(update={"signal": None}))
                else:
                    kept.append(line)
            box[key] = kept
        out.append(one.model_copy(update=box))
    if bad:
        state.note(f"s6 §2-2 — 신호가 **없거나 목록 밖**인 줄 {bad}개 — 그 줄은 "
                   f"단계 4 에서 `판단 불가` 다")
    return out


def scenarios(ref: MatchRef, facts: Facts, variables: list[Variable],
              hypo: HypoSet, sim: dict, *, state: RunState,
              supported: list | None = None) -> HypoSet:
    """🔴🔴 **단계 4-4 — 시나리오를 시뮬 분포에서 만든다**.

    > 시뮬레이션 **스코어 분포 상위 묶음**(승·무·패별로 1~2개)을 시나리오로 삼고,
    > 각 시나리오에 그 결과를 **지지하는 검증된 가설과 변수**를 붙인다(전개 문장은
    > LLM, 근거는 **지지된 가설·변수 id만**).

    🔴 판정 계산 로직은 **그대로** 둔다 — 아래 보강·검사·무게는 종전 함수들이다.
    ⚠️ 시뮬이 없으면 **빈 시나리오**로 보강만 돈다(카드는 나온다).
    """
    drops: list[Drop] = list(hypo.drops or [])
    scen = _from_sim(sim, hypo, supported or [], state=state)
    scen = _required(ref, facts, scen, variables, state=state)
    # 🔴 **없는 변수 인용을 떨군다**(불변식 5) — 변수 목록이 바뀐 뒤 남은 번호
    scen = _keep_drivers(scen, variables, state=state)
    # 🔴🔴 **득점 방향이 반대인 driver 를 뺀다**(사용자 지시 2026-10-07 §3)
    scen = _goal_fit(scen, variables, state=state)
    # 🔴🔴 **반등·회귀 주장은 해석 규칙을 요구한다**(지시 2026-10-09(6차) ②)
    scen = _regression_fit(scen, variables, state=state)
    scen = [s.model_copy(update={"strength": _strength(s, variables)})
            for s in scen]
    basis = [v for v in variables if v.usable_as_basis]
    red = _redteam(ref, scen, basis, state=state)
    state.set("scenarios", len(scen))
    return HypoSet(hypotheses=list(hypo.hypotheses), scenarios=scen,
                   redteam=red, drops=drops)


#: 🔴 §4-4 — 결과마다 몇 개를 시나리오로 삼나(지시서가 적은 1~2)
PER_OUTCOME = 2


def _from_sim(sim: dict, hypo: HypoSet, supported: list, *,
              state: RunState) -> list[Scenario]:
    """🔴🔴 §4-4 — **스코어 분포 상위 묶음**(승·무·패별 1~2개) → 시나리오.

    🔴 근거(`driver_vars`)는 **지지된 가설의 변수 id 만** 붙인다 — 그 결과를
       지지하는 가설(그 팀이 이기는 쪽)에서 가져온다.
    ⚠️ 전개 문장은 지금 **코드가** 적는다(무게·스코어·지지 가설). §4-4 가 말한
       LLM 전개는 `s8_comment`·최종 평이 이미 쓰고 있다 — 같은 말을 두 번 만들지
       않는다(사본 금지).
    """
    rows = dict(dict(sim or {}).get("scores") or {})
    if not rows:
        state.note("s6 §4-4 — 🔴 시뮬 스코어 분포가 없다 — 시나리오를 "
                   "**분포에서 못 만들었다**(필수형 보강만 돈다)")
        return []
    by: dict[str, list] = {"home": [], "draw": [], "away": []}
    for (h, a), p in sorted(rows.items(), key=lambda kv: -float(kv[1])):
        key = "home" if h > a else ("draw" if h == a else "away")
        if len(by[key]) < PER_OUTCOME:
            by[key].append(((int(h), int(a)), float(p)))
    out: list[Scenario] = []
    for key, got in by.items():
        for (h, a), p in got:
            ids = _ids_for(key, hypo, supported)
            out.append(Scenario(
                id=f"S{len(out) + 1}", outcomes=[(h, a)],
                driver_vars=ids, type=_kind_of([(h, a)]),
                added_by="deepseek",
                mechanism=(f"시뮬 분포 무게 {p:.1%} 의 {h}-{a} — "
                           + (f"지지된 가설의 근거 {ids}" if ids
                              else "🔴 지지된 가설이 없다(무게만 있다)"))))
    state.note("s6 §4-4 — 시나리오 "
               + " · ".join(f"{k} {len(v)}개" for k, v in by.items())
               + f" ← 시뮬 분포 상위(결과마다 {PER_OUTCOME}개까지)")
    return out


def _ids_for(key: str, hypo: HypoSet, supported: list) -> list[str]:
    """🔴 그 결과를 **지지하는 검증된 가설**의 변수 id 들(없으면 빈 목록).

    `supported` 는 단계 4 가 `지지` 로 판정한 줄들이다 —
    `[{"side": "home", "kind": "reasons", "var_ids": [...]}, …]`.
    """
    want = {"home": "home", "away": "away"}.get(key)
    out: list[str] = []
    for one in (supported or []):
        box = dict(one)
        if want is None:
            # 🔴 무승부 — *"무너지는 조건"* 이 지지된 쪽이 근거다
            if str(box.get("kind")) != "breaks":
                continue
        elif not (str(box.get("side")) == want
                  and str(box.get("kind")) == "reasons"):
            continue
        for x in (box.get("var_ids") or []):
            if str(x) not in out:
                out.append(str(x))
    return out[:6]


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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **시나리오 조항을 걷었다** — 순서 재편 지시서 §2-3
        # ══════════════════════════════════════════════════════════════
        #
        #  > 시나리오는 **여기서 만들지 않는다**(단계 4에서 시뮬레이션 결과로
        #  > 만든다).
        #
        #  🔴 대신 **예측 신호**를 요구한다(§2-2) — 지표 목록은 **코드가 준다**.
        "3. 🔴🔴 가설 줄마다 **예측 신호**(`signal`)를 단다 — 그 가설이 맞다면 "
        "시뮬레이션에서 **보여야 하는 것**이다. 칸은 `metric`(지표) · "
        "`direction`(방향) · `ref`(기준) · `side`(팀) · `arg`(인자)다.\n"
        "   🔴 **쓸 수 있는 지표는 아래 목록뿐**이다(목록 밖은 버려진다):\n"
        + _menu_block()
        + "\n4. 🔴 **시나리오를 쓰지 마라** — `scenarios` 는 **빈 목록**으로 둔다"
        "(시나리오는 코드가 시뮬레이션 분포에서 만든다).\n"
        "5. 팀마다 `reasons` **2~3개** · `breaks` **2~3개**다.\n"
        "6. 🔴 **등급·확률·승자·배당·추천 단어를 쓰지 않는다** — 그것은 코드가 "
        "수로 정한다.")


def _menu_block() -> str:
    """🔴 지표 목록 — `signals.menu()` **하나**가 든다(사본 금지)."""
    from app.core import signals as _sg
    return "\n".join(f"   {x}" for x in _sg.menu().splitlines())


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
        """🔴 근거 변수 한 줄 — claim 은 **80자**(재가중 ④)."""
        return {"id": v.id, "type": v.type, "subject": v.subject,
                "favors": v.favors, "claim": v.claim[:CLAIM_CUT],
                "weight": v.weight}

    def bare(v: Variable) -> dict:
        """🔴 맥락 변수 한 줄 — **이름만**이다(claim 을 안 보낸다 · 재가중 ④).

        ⚠️ 맥락은 근거가 못 된다 — 가설이 그것을 인용할 수 없으므로 글을 보낼 까닭이
           없다. 🔴 유형·주체만 보내 *"그런 종류의 말이 있다"* 만 알린다.
        """
        return {"id": v.id, "type": v.type, "subject": v.subject}

    def form(raw: object) -> dict:
        box = dict(raw) if isinstance(raw, dict) else {}
        return {k: box[k] for k in _FORM_KEYS if k in box}

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **보낼 변수 수를 묶는다** — 실측 2026-10-06(콜롬비아–페루)
    # ══════════════════════════════════════════════════════════════════
    #
    #  변수 32개를 보냈더니 입력 3,548 + 캐시 384 에 **출력 8,000이 전부 추론**이 되어
    #  `length` 로 잘렸다(가설 0팀). ⚠️ 상한을 올리는 것은 §9 금지다 — DeepSeek 은
    #  추론 강도도 무시한다(앞 실측). 🔴 남은 지렛대는 **입력 크기**다.
    #
    #  🔴 **무게가 큰 것부터** 자른다(hard → soft). ⚠️ 자른 수를 사유로 남긴다 —
    #     조용히 버리면 카드가 *"그 변수를 안 봤다"* 를 숨긴다(#3).
    keep_basis = sorted(basis, key=lambda v: (-float(v.weight), v.id))[:BASIS_CAP]
    keep_ctx = ctx[:CTX_CAP]
    box = {
        "match": {"home": ref.home_name, "away": ref.away_name,
                  "home_key": ref.home, "away_key": ref.away,
                  "competition": ref.competition_short,
                  "match_format": facts.match_format, "sport": ref.sport},
        "variables": [row(v) for v in keep_basis],
        "context_only": [bare(v) for v in keep_ctx],
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
    if len(basis) > BASIS_CAP or len(ctx) > CTX_CAP:
        state.note(f"s6 입력을 묶었다 — 근거 {len(basis)}→{min(len(basis), BASIS_CAP)}개"
                   f"(무게 큰 것부터) · 맥락 {len(ctx)}→{min(len(ctx), CTX_CAP)}개 "
                   f"(**이름만**) · claim {CLAIM_CUT}자 "
                   f"(실측 2026-10-07: 10개·200자면 `length` 로 잘린다)")
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
    # ── 🔴🔴 **축구 필수형 넷**(축구 완성 지시서 §3) — 문턱은 yaml 이 든다
    if ref.sport == "soccer":
        out = _soccer_forms(ref, facts, out, variables, state=state)
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



#: 🔴 §2 — *"반등·회귀·평균으로 돌아온다"* 류 낱말(우리 글의 검사어다)
REGRESSION_WORDS: tuple[str, ...] = (
    "반등", "회귀", "평균으로 돌아", "평균 회귀", "되돌아", "크게 벗어난 값",
    "제자리로", "원래 수준")
#: 🔴 §2 — 그 주장을 받쳐야 하는 **해석 규칙 id**(사용자가 적은 넷 그대로)
REGRESSION_RULES: tuple[str, ...] = ("IR04", "IR06", "IR10", "IR12")
#: 🔴 D-1 — 근거가 다 빠진 갈래의 **문장**(그 주장을 글로 남기지 않는다)
FLOOR_MECH = "[보강] 근거 없는 갈래 — 저무게"


def _regression_fit(scen: list, variables: list[Variable], *,
                    state: RunState) -> list:
    """🔴🔴 §2 — **반등 주장에는 규칙이 있어야 한다**(지시 2026-10-09(6차) ②).

    > 시나리오 `mechanism` 이 *"반등·회귀·평균으로 돌아온다"* 류를 말하면, 발동한
    > 해석 규칙(**IR04·IR06·IR10·IR12**) id 가 `driver` 에 있어야 한다. 없으면 그
    > driver 를 빼고, driver 가 다 빠지면 **바닥값**.
    > *"최근 폼 < 시즌 평균"* 만으로 반등 갈래를 만들지 않는다.

    🔴 왜 — 실사고 2026-10-09(강원–부천): `D 3-0·2-0`(무게 1.2158)의 까닭이
       *"0.6 은 시즌 득점 수준에서 크게 벗어난 값이라 홈에서 반등 여지"* 였다.
       ⚠️ 그 말의 **반대 해석**(지금 안 좋다)과 **같은 무게**다 — 어느 쪽도 자료가
       고르지 않는다. 🔴 규칙이 발동했을 때만 한쪽을 고른다.
    """
    from app import scenarios as _sc
    by_id = {v.id: v for v in variables}
    out = []
    for s_ in scen:
        said = str(getattr(s_, "mechanism", "") or "")
        hit = [w for w in REGRESSION_WORDS if w in said]
        if not hit:
            out.append(s_)
            continue
        keep, dropped = [], []
        for vid in (getattr(s_, "driver_vars", None) or []):
            v = by_id.get(str(vid))
            rule = str(getattr(v, "from_rule", "") or "").split("-")[0]
            if rule in REGRESSION_RULES:
                keep.append(str(vid))
            else:
                dropped.append(str(vid))
        if not dropped:
            out.append(s_)
            continue
        origin = ("required" if not keep
                  else str(getattr(s_, "added_by", "") or ""))
        state.note(
            f"s6 §2 반등 주장 — `{s_.id}` 가 {hit[:2]} 를 말하는데 근거 "
            f"{dropped} 에 해석 규칙({'·'.join(REGRESSION_RULES)})이 없다 → "
            + (f"그 근거를 뺀다(남은 {keep})" if keep
               else f"근거가 다 빠져 **바닥값**으로 둔다(`{origin}`)"))
        # 🔴🔴 **빠진 주장을 글로 남기지 않는다**(사용자 지시 2026-10-10 D-1)
        #    > 근거가 다 빠져 바닥값이 된 갈래는 mechanism 문장도 바꾼다:
        #    > "[보강] 근거 없는 갈래 — 저무게" 한 줄로.
        #    ⚠️ 실사고 2026-10-09(강원–부천): 무게는 0.2075 로 내렸는데 *"평균 쪽으로
        #       되돌아오는 반등"* 이라는 **문장은 카드에 그대로 남았다** — 읽는 사람은
        #       그 주장을 본다.
        mech_new = (FLOOR_MECH if not keep else said)
        out.append(s_.model_copy(update={
            "mechanism": mech_new,
            "driver_vars": keep,
            # 🔴 근거가 다 빠지면 **바닥 출처**로 바꾼다 — `_strength` 가 그때
            #    yaml 의 바닥값을 쓴다(우리가 수를 짓지 않는다)
            "added_by": (origin if origin in _sc.FLOOR_ORIGINS
                         else getattr(s_, "added_by", "deepseek"))}))
    return out


def _keep_drivers(scen: list[Scenario], variables: list[Variable], *,
                  state: RunState) -> list[Scenario]:
    """🔴🔴 **없는 변수 번호를 인용한 driver 를 떨군다**(실측 2026-10-07).

    ⚠️ 변수 목록이 바뀌면(맞대결 집계 불일치로 `S02` 가 빠지는 등) 모델이 적어 둔
       `driver_vars` 에 **없는 번호**가 남는다 — 카드가 그 번호를 적으면 *"무엇으로
       그렇게 봤나"* 가 거짓이 된다(불변식 5 가 그것을 잡는다).
    🔴 **근거로 못 쓰는 변수**(`usable_as_basis=False`)도 떨군다 — §4-1 은 그 번호를
       인용한 줄을 버리라고 했다. ⚠️ 실측 2026-10-07: 표본 무게가 낮은 `S02`(맞대결
       9경기)를 시나리오가 driver 로 적어 불변식 5 가 빨개졌다.
    🔴 떨군 번호는 **사유로 남긴다**(조용히 지우지 않는다 · #3).
    """
    ids = {v.id for v in variables if v.usable_as_basis}
    out: list[Scenario] = []
    for sc in scen:
        bad = [x for x in (sc.driver_vars or []) if x not in ids]
        if not bad:
            out.append(sc)
            continue
        state.note(f"s6 시나리오 `{sc.id}` — 인용 {bad} 를 떨궜다"
                   f"(없는 변수이거나 **근거 불가**다 · §4-1)")
        out.append(sc.model_copy(update={
            "driver_vars": [x for x in sc.driver_vars if x in ids]}))
    return out


def _goal_fit(scen: list[Scenario], variables: list[Variable], *,
              state: RunState) -> list[Scenario]:
    """🔴🔴 **스코어와 득점 방향이 반대인 driver 를 뺀다**(사용자 지시 2026-10-07 §3).

    > 총골 **3골 이상** 갈래에 `goals=down` 변수가 driver 면 그 driver 를 빼고,
    > **2골 이하** 갈래에 `goals=up` 이면 뺀다. driver 가 다 빠지면 **바닥값**.

    ⚠️ 실측 2026-10-07(멕시코–칠레): 두 팀 보정 득점이 0.667(`goals=down`)인데
       `3-2`·`2-3` 갈래가 그 폼 변수를 근거로 들고 무게 상위에 섰다 — 그 갈래의
       근거가 **반대 방향**이었다.
    🔴 갈래를 **지우지 않는다** — 근거만 뺀다(그 모양이 아예 못 나온다는 말은 아니다).
    """
    by_id = {v.id: v for v in variables}
    out: list[Scenario] = []
    for sc in scen:
        pairs = list(sc.outcomes or [])
        if not pairs:
            out.append(sc)
            continue
        tot = sum(h + a for h, a in pairs) / len(pairs)
        want = "up" if tot >= 3 else "down" if tot <= 2 else ""
        if not want:
            out.append(sc)
            continue
        bad = [i for i in sc.driver_vars
               if (v := by_id.get(i)) is not None
               and {str(v.goals), str(v.goals_against)} & {_OTHER[want]}
               and want not in {str(v.goals), str(v.goals_against)}]
        if not bad:
            out.append(sc)
            continue
        kept = [i for i in sc.driver_vars if i not in bad]
        state.note(f"s6 `{sc.id}`(평균 총골 {tot:.1f}) — 득점 방향이 반대인 driver "
                   f"{bad} 를 **뺐다**" + ("" if kept else " → 근거 0개(바닥값)"))
        out.append(sc.model_copy(update={"driver_vars": kept}))
    return out


_OTHER = {"up": "down", "down": "up"}


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **얇게 보낸다** — 실측 2026-10-06(원장)
    # ══════════════════════════════════════════════════════════════════
    #
    #   입력 1,135 → 출력 3,967(추론 2,645) · `stop`
    #   입력 2,027 → 출력 4,000이 **전부 추론** · 🔴 `length`(반증 0줄)
    #
    # 🔴 DeepSeek 은 추론 강도를 무시한다(위 `hypo` 의 실측) — 지렛대는 입력뿐이다.
    #    ⚠️ 그래서 메커니즘·주장을 **잘라** 보내고, 줄 수도 **상한을 적어** 묻는다.
    box = {"match": {"home": ref.home_name, "away": ref.away_name},
           "scenarios": [{"id": s.id, "outcomes": s.outcomes,
                          "mechanism": s.mechanism[:160]} for s in scen],
           "variables": [{"id": v.id, "claim": v.claim[:110]}
                         for v in basis[:10]]}
    said = llm.ask(
        provider="deepseek", purpose="redteam", out=RedTeamOut, state=state,
        messages=[
            llm.Message(role="system", content=(
                "너는 위 분석의 **반대편**을 쓴다. 각 줄은 어떤 마켓이 왜 위험한지 "
                "한 문장이다. 🔴 **여덟 줄을 넘기지 마라.**\n"
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

def _soccer_forms(ref: MatchRef, facts: Facts, scen: list[Scenario],
                  variables: list[Variable], *, state: RunState
                  ) -> list[Scenario]:
    """🔴🔴 **축구 필수형**(축구 완성 지시서 §3) — 대량득점·난타전·저득점·회귀반전.

    > 대량득점(양 팀 보정 평균 합 3+ 또는 한쪽 결장 hard 3+) · 난타전(보정 평균 합 4+)
    > · 저득점·0-0(IR01·IR04·IR07 발동 또는 친선 아님 & 한쪽이 비기면 충분한 동기)
    > · 회귀반전(IR06·IR12)

    🔴 문턱·스코어는 `config/scenario_required.yaml` 의 `soccer_forms` 가 든다 —
       여기 숫자를 적지 않는다(#1). ⚠️ 못 잰 조건은 **이름으로** 남긴다(#3).
    """
    from app import rules
    box = dict((rules._load("config/scenario_required.yaml")
                .get("soccer_forms") or {}))
    out = list(scen)
    trimmed = _trimmed_sum(facts)
    fired = {str(v.from_rule) for v in variables if v.from_rule}
    hard_miss = max(
        [sum(1 for v in variables
             if v.hardness == "hard" and v.subject == key
             and v.type in ("absence", "absence_att", "def_absence",
                            "suspension"))
         for key in (ref.home, ref.away)] or [0])

    def _add(name: str, scores: list[tuple[int, int]], why: str,
             kind: str, drivers: list[str] | None = None) -> None:
        """🔴🔴 보강 갈래 하나. **발동 조건에 쓴 변수를 driver 로 단다**(지시 1).

        ⚠️ 실측 2026-10-07: 저득점 갈래 `G` 가 근거(무실점 2연속 · 공격수 결장)를
           가지고도 `driver_vars=[]` 여서 **바닥값 0.1** 을 받았다 — 그래서 언더 3.5
           생존이 0.596 으로 눌렸다. 🔴 무게는 일반 갈래와 **같은 규칙**(유형별
           최댓값 합)이고, 근거가 **하나도 없을 때만** 바닥값이다.
        🔴 `mechanism` 도 그 driver 로 다시 쓴다 — 템플릿은 `_mech()` 하나다.
        """
        have = _all_scores(out)
        want = [p for p in scores if p not in have]
        if not want:
            state.note(f"s6 축구 필수형 `{name}` — 이미 그 갈래가 있다")
            return
        said = [x for x in (drivers or []) if x in {v.id for v in variables}]
        out.append(Scenario(id=_next_id(out), outcomes=want[:2],
                            driver_vars=said[:4], type=kind,  # type: ignore[arg-type]
                            added_by="code",
                            mechanism=_mech(name, want[:2], why, said,
                                            variables)))
        state.note(f"s6 축구 필수형 보강 — {name}({why}) · driver "
                   f"{said or '없음(바닥값)'}")

    # ── 대량득점
    row = dict(box.get("대량득점형") or {})
    at = float(row.get("trimmed_sum_at") or 0)
    need = int(row.get("absence_hard_at") or 0)
    if trimmed is None:
        state.note("s6 축구 필수형 대량득점 — 보정 평균을 **못 쟀다**(폼 없음)")
    elif (at and trimmed >= at) or (need and hard_miss >= need):
        _add("대량득점", [(3, 1), (1, 3)],
             f"보정 평균 합 {trimmed} · 결장 hard {hard_miss}개", "blowout",
             # 🔴 조건에 쓴 것: 폼(보정 평균)과 **결장 hard** 변수다
             drivers=[v.id for v in variables
                      if v.type == "recent_pattern"][:2]
             + [v.id for v in variables
                if v.hardness == "hard" and v.type in ABSENCE_TYPES][:2])
    else:
        state.note(f"s6 축구 필수형 대량득점 — 조건 미달(합 {trimmed} < {at} · "
                   f"결장 hard {hard_miss} < {need})")
    # ── 난타전
    row = dict(box.get("난타전") or {})
    at = float(row.get("trimmed_sum_at") or 0)
    if trimmed is not None and at and trimmed >= at:
        _add("난타전", [_pair(x) or (0, 0) for x in (row.get("scores") or [])],
             f"보정 평균 합 {trimmed} ≥ {at}", "open",
             drivers=[v.id for v in variables
                      if v.type == "recent_pattern"][:2])
    # ── 저득점·0-0
    row = dict(box.get("저득점") or {})
    want_rules = {str(x) for x in (row.get("when_rules") or [])}
    hit = sorted({r.split("-")[0] for r in fired} & want_rules)
    # 🔴🔴 **조건 둘을 더했다**(사용자 지시 2026-10-07 ②) — 무실점 연속·공격수 결장
    said_low, ids_low = _low_score_why(ref, facts, variables, row)
    hit += said_low
    if hit:
        # 🔴 규칙(IR01·IR04·IR07)으로 걸린 것도 **그 규칙이 만든 변수**를 driver 로
        ids_low += [v.id for v in variables
                    if str(v.from_rule or "").split("-")[0] in want_rules]
        _add("저득점", [p for p in (_pair(x) for x in (row.get("scores") or []))
                      if p is not None],
             f"{', '.join(hit)}", "lock", drivers=ids_low)
    else:
        state.note(f"s6 축구 필수형 저득점 — 걸린 조건이 없다"
                   f"(규칙 {sorted(want_rules)} · 무실점 연속 · 공격수 결장)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **무승부 필수**(사용자 지시 2026-10-06(5차) ①) — v4 `soccer_lock` 의 일
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 축구 시나리오 세트에 **무승부(0-0 또는 1-1) 갈래가 하나도 없으면** 코드가
    #  > 보강한다. 무게는 `[보강]` 기본값, **근거 변수가 있으면 그 무게.**
    #
    #  ⚠️ 실측 2026-10-06 온두라스–자메이카: 시나리오 셋이 전부 승/패여서 우리 열
    #     무승부가 **0%** 였고, `무`·`더블찬스` 가 그 0 을 그대로 받았다.
    row = dict(box.get("무승부") or {})
    want = [p for p in (_pair(x) for x in (row.get("scores") or [])) if p]
    if any(h == a for s in out for h, a in s.outcomes):
        state.note("s6 축구 필수형 무승부 — **이미 있다**(보강하지 않는다)")
    elif want:
        kinds = {str(x) for x in (row.get("basis_types") or [])}
        basis = [v for v in variables if v.type in kinds]
        got = Scenario(
            id=_next_id(out), outcomes=want[:2],
            # 🔴 근거 변수가 있으면 **그 변수들을 driver 로** 적는다 → `_strength` 가
            #    그 무게를 쓴다(없으면 바닥값 = `[보강]` 기본값)
            driver_vars=[v.id for v in basis[:3]], type="lock",
            added_by="code",
            mechanism=("🔴 축구 필수형(무승부) — 무승부 갈래가 **하나도 없었다** · "
                       + (f"근거 {', '.join(v.id for v in basis[:3])}"
                          if basis else "근거 없음 — 보강 기본값")))
        out.append(got)
        state.note(f"s6 축구 필수형 보강 — 무승부({want[:2]}) · 근거 "
                   f"{len(basis)}개{' (무게를 그 변수에서 가져온다)' if basis else ''}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **역습 갈래 필수**(7차 §4 · 8차 ③) — `must_win`·`margin_needed` 상대 쪽
    # ══════════════════════════════════════════════════════════════════
    out = _counter(ref, facts, out, variables, box, state=state)
    # ── 회귀반전
    row = dict(box.get("회귀반전") or {})
    want_rules = {str(x) for x in (row.get("when_rules") or [])}
    hit = sorted({r.split("-")[0] for r in fired} & want_rules)
    if hit:
        _add("회귀반전", [p for p in (_pair(x) for x in (row.get("scores") or []))
                        if p is not None],
             f"{', '.join(hit)} 발동 — 방향을 고르지 않는다(양쪽)", "regression",
             drivers=[v.id for v in variables
                      if str(v.from_rule or "").split("-")[0] in want_rules])
    else:
        state.note(f"s6 축구 필수형 회귀반전 — 걸린 규칙이 없다"
                   f"(필요 {sorted(want_rules)})")
    return out


def _trimmed_sum(facts: Facts) -> float | None:
    """🔴 양 팀 **보정 평균 합**. ⚠️ 한쪽이라도 없으면 `None`(0 으로 때우지 않는다)."""
    got: list[float] = []
    for raw in facts.recent.values():
        box = dict(raw) if isinstance(raw, dict) else {}
        val = box.get("recent_trimmed_avg", box.get("recent_scored_avg"))
        if val is None:
            return None
        got.append(float(val))
    return round(sum(got), 2) if len(got) >= 2 else None


def _counter(ref: MatchRef, facts: Facts, scen: list[Scenario],
             variables: list[Variable], box: dict, *,
             state: RunState) -> list[Scenario]:
    """🔴🔴 **이겨야 하는 팀의 상대에게 역습 갈래를 준다**(7차 §4 · 8차 ③).

    🔴 검수 기준(8차 ③): *"`must_win` 팀의 **상대 역습 갈래**가 시나리오에 생겼고
       **driver·전개 문장**이 맞나"* — 시장과의 거리로 재지 않는다.
    ⚠️ 상태는 `Facts` 에 없다(s2b 가 센다) — 그래서 **경우의 수 표**를 인자로 받지 않고
       `facts.standings["outlook_states"]` 를 본다. 🔴 그 칸이 없으면 **안 만든다**
       (상태를 모르면 역습을 지어낼 까닭이 없다).
    """
    row = dict(box.get("역습") or {})
    want = {str(x) for x in (row.get("when_states") or [])}
    said = dict(((facts.standings or {}).get("outlook_states") or {}))
    if not row or not want or not said:
        if want:
            state.note("s6 역습 필수형 — 경우의 수 상태가 없다(안 만든다)")
        return scen
    out = list(scen)
    for team, got in said.items():
        state_name = str(dict(got).get("state") or "")
        if state_name not in want:
            continue
        is_home = str(team).strip().lower() == ref.home_name.strip().lower()
        key = "scores_home_pusher" if is_home else "scores_away_pusher"
        pairs = [p for p in (_pair(x) for x in (row.get(key) or [])) if p]
        have = _all_scores(out)
        # 🔴 **그 상대가 이기는 갈래가 이미 있나** — 있으면 더하지 않는다
        other_wins = [(h, a) for h, a in have
                      if (a > h if is_home else h > a)]
        if other_wins:
            state.note(f"s6 역습 필수형 — `{team}`({state_name}) 의 상대가 이기는 "
                       f"갈래가 **이미 있다**{other_wins[:2]}")
            continue
        new = [p for p in pairs if p not in have]
        if not new:
            continue
        other = ref.away_name if is_home else ref.home_name
        why = (f"{dict(got).get('margin')}골 차가 필요해" if dict(got).get("margin")
               else "이기지 않으면 구역이 나빠져")
        mech = str(row.get("mechanism") or "").strip().replace("\n", " ")
        mech = " ".join(mech.format(pusher=team, other=other, why=why).split())
        # 🔴 driver — **그 상태를 만든 근거**를 적는다(동기 변수가 있으면 그것)
        drivers = [v.id for v in variables
                   if v.type in ("stakes", "match_format") and v.favors != "both"][:2]
        out.append(Scenario(id=_next_id(out), outcomes=new[:2], type="counter",
                            added_by="code", driver_vars=drivers,
                            mechanism=f"🔴 필수형(역습) — {mech}"))
        state.note(f"s6 역습 필수형 보강 — `{team}`({state_name}) → {other} 역습 "
                   f"{new[:2]} · driver {drivers or '근거 없음'}")
    return out


def _mech(name: str, scores: list[tuple[int, int]], why: str,
          drivers: list[str], variables: list[Variable]) -> str:
    """🔴 보강 갈래의 **전개 문장** — driver 로 다시 쓴다(지시 1 템플릿).

    꼴: *"{driver 요약}이 겹쳐 {스코어} 같은 저득점으로 끝난다"*.
    ⚠️ driver 가 없으면 **그 사실을 적는다**(근거 없이 그린 갈래다).
    """
    said = ", ".join(f"{v.claim[:46]}" for v in variables
                     if v.id in set(drivers))
    spot = " · ".join(f"{h}-{a}" for h, a in scores)
    tail = {"저득점": "저득점으로 끝난다", "대량득점": "다득점으로 벌어진다",
            "난타전": "서로 주고받는 난타전이 된다",
            "회귀반전": "평균 쪽으로 되돌아간다",
            "무승부": "무승부로 끝난다"}.get(name, "그렇게 끝난다")
    if not drivers:
        return (f"🔴 축구 필수형({name}) — {why} · ⚠️ **근거 변수 없음**(바닥값) — "
                f"{spot} 같은 꼴을 **자리만** 비워 둔다")
    return (f"🔴 축구 필수형({name}) — {said}이 겹쳐 {spot} 같은 {tail}"
            f"(조건: {why})")


def _low_score_why(ref: MatchRef, facts: Facts, variables: list[Variable],
                   row: dict) -> tuple[list[str], list[str]]:
    """🔴 저득점 갈래를 **넣을 까닭**(사용자 지시 2026-10-07 ②). 없으면 빈 목록.

    ① 한 팀이 최근 **n경기 이상 연속 무실점**(`recent.streak_clean_sheet`).
    ② **상대 팀 주전 공격수 결장** — ⚠️ 우리는 선수별 득점 이력을 안 받는다.
       🔴 그래서 `absence_att` 또는 **포지션이 `FW`** 인 결장 변수로 센다. 그 한계를
       사유에 적는다(*"최근 득점자"* 를 확인했다고 적지 않는다).
    """
    out: list[str] = []
    ids: list[str] = []
    need = int(row.get("when_clean_sheet") or 0)
    if need:
        for key, raw in (facts.recent or {}).items():
            got = int(dict(raw).get("streak_clean_sheet") or 0)
            if got >= need:
                out.append(f"{_who(ref, key)} 무실점 {got}경기 연속")
                # 🔴 그 사실을 든 변수는 **그 팀의 폼 변수**다(S01)
                ids += [v.id for v in variables
                        if v.type == "recent_pattern" and str(v.subject) == str(key)]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **올 시즌 맞대결이 저득점이면 필수**(사용자 지시 2026-10-09 ②)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 올 시즌 맞대결이 **2경기 이상**이고 **경기당 1골 이하**면 `0-0`/`1-0` 필수.
    #
    # 🔴 실측 2026-10-09(대전–전북): 올 시즌 `0-1`·`0-0` = 2경기 **총 1골**
    #    (경기당 0.5). ⚠️ 창 10경기 평균은 2.1골이라 그 신호를 **덮었다**.
    need_n = int(row.get("when_season_h2h_games") or 0)
    cap_gpg = row.get("when_season_h2h_goals_per_game")
    if need_n and cap_gpg is not None:
        season = list((facts.h2h or {}).get("season_matches") or [])
        scored = [m for m in season
                  if m.get("home_score") is not None
                  and m.get("away_score") is not None]
        if len(scored) >= need_n:
            tot = sum(int(m["home_score"]) + int(m["away_score"]) for m in scored)
            gpg = tot / len(scored)
            if gpg <= float(cap_gpg):
                out.append(f"올 시즌 맞대결 {len(scored)}경기 총 {tot}골"
                           f"(경기당 {gpg:.2f} ≤ {float(cap_gpg):g})")
                # 🔴 그 사실을 든 변수는 **맞대결 변수**다(S02)
                ids += [v.id for v in variables if v.type == "h2h_pattern"]
            # ⚠️ 넘으면 **안 센다** — 그 사실은 아래 `state.note` 가 아니라 이
            #    함수를 부른 자리가 적는다(이 함수는 사유만 모은다)
    if row.get("when_striker_absent"):
        pos = dict(facts.player_pos or {})
        for v in variables:
            if v.type not in ("absence_att", "absence", "def_absence",
                              "suspension"):
                continue
            spot = str(pos.get(str(v.target), "")).upper()
            if v.type == "absence_att" or spot == "FW":
                out.append(f"{_who(ref, str(v.subject))} 공격 자원 결장"
                           f"(`{v.id}` {v.target}"
                           + (f" · 포지션 {spot}" if spot else " · 포지션 미상")
                           + ") ⚠️ 최근 득점자인지는 **확인 못 했다**")
                ids.append(v.id)
    return out, ids


def _who(ref: MatchRef, key: str) -> str:
    """🔴 열쇠 → 보일 이름(사유에 열쇠를 적지 않는다)."""
    if str(key) == str(ref.home):
        return ref.home_name
    if str(key) == str(ref.away):
        return ref.away_name
    return str(key)
