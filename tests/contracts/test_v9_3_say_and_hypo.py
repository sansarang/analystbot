"""🔴🔴 **최종 평 이유 문단 · 가설 반박 원인** — 사용자 지시 2026-10-11(둘 다 고쳐라).

카드가 스스로 적은 두 결함이다:

① **최종 평 `템플릿`** — 검열이 *"(o) 새 사실 1건이 있는데 이유 문단이 하나도 안
   썼다 · (i) 이유 문단이 없다"* 로 두 번 걸렸다.
   🔴 까닭(코드를 읽어 확인): **프롬프트가 `reason`(이유 문단)을 한 번도 요구하지
   않는다.** 검열만 요구한다 — 모델은 요구받지 않은 칸을 비워 뒀고, 재작성은
   `llm_truncated` 로 끊겨 템플릿으로 떨어졌다.

② **가설 반박 6건이 전부 `기준 낡음`** — 두 고장이 겹쳐 있다:
   (a) `_cause` 가 **경기 단위** `stale`(어느 쪽이든 결장 ≥3명)을 보고 그 경기의
       **모든** 반박에 (b) 를 붙인다 — 폼 가설(`S01-home`)까지 *"기준 낡음"* 이
       됐다. 그 가설은 결장과 아무 관계가 없다.
   (b) 🔴🔴 `리그평균` 기준이 **양 쪽에 같은 수**(한 팀 몫)다. 홈 λ 는 홈 이점
       (×1.139)을 머금고 있어 *거의 언제나* 그 수를 넘는다 — 그래서 홈 폼 가설은
       **구조적으로 반박**된다. 실측(LAFC): 한 팀 몫 1.476 · 홈 기준 1.681 ·
       원정 기준 1.271 → 홈 λ 1.549 는 **홈 기준보다 낮다**(지지가 맞다).
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 코드만."""
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════
# ① 최종 평 — 프롬프트가 이유 문단을 **요구한다**
# ══════════════════════════════════════════════════════════════════

def _card():
    """🔴 최소 카드 — 새 사실 한 건(`R1`)이 있는 꼴."""
    from app.core import render
    from app.core.schema import (Card, Facts, MatchRef, ProbTriple, Variable)
    ref = MatchRef(id="m", sport="soccer", competition="Major League Soccer",
                   competition_short="MLS", home="team:000584",
                   away="team:000585", home_name="Los Angeles FC",
                   away_name="Vancouver Whitecaps",
                   kickoff_utc="2026-10-11T02:30:00Z")
    v = Variable(id="R1", type="absence", subject="team:000585",
                 target="absence:Thomas Muller", favors="home",
                 hardness="hard", weight=0.7, usable_as_basis=True,
                 claim="Thomas Muller will be absent", quote="q",
                 doc_ids=["d1"],
                 #: 🔴 새 사실은 **F 하위**가 나른 것이다(`render.NEW_SUBS`)
                 subtask=sorted(render.NEW_SUBS)[0])
    return Card(match=ref, facts=Facts(), variables=[v],
                our_prob=ProbTriple(home=0.37, draw=0.24, away=0.39))


def test_prompt_asks_for_the_reason_paragraph() -> None:
    """🔴🔴 ① — 프롬프트에 **이유 문단** 요구가 있어야 한다."""
    from app.core import saybundle
    from app.core.stages import s9_say
    card = _card()
    msgs = s9_say._prompt(card, saybundle.build(card))
    said = "\n".join(str(getattr(m, "content", "")) for m in msgs)
    assert "reason" in said and "이유 문단" in said, said[-400:]
    #: 🔴 시스템 메시지에서도 요구한다(긴 규칙 끝에만 적으면 모델이 비운다)
    assert "reason" in str(getattr(msgs[0], "content", ""))
    #: 🔴 새 사실 id 를 **그 자리에서** 든다(검열이 요구하는 그 id 다)
    assert "R1" in said
    #: 🔴 문장 수 요구(검열 (i) 가 세는 그 수)도 적는다
    assert "문장" in said


def test_prompt_names_the_new_facts_from_one_source() -> None:
    """🔴 새 사실 목록은 **검열이 보는 그 함수**에서 온다(사본 금지)."""
    from app.core.stages import s9_say
    assert "new_facts" in _src(s9_say._prompt)


def test_reason_only_repair_exists_and_is_wired() -> None:
    """🔴 ① — 이유 문단만 어긋났으면 **그 문단만** 다시 묻는다(짧게).

    ⚠️ 실측: 전체 재작성은 `llm_truncated` 로 끊긴다(출력 10991 중 추론 7822).
    """
    from app.core.stages import s9_say
    assert hasattr(s9_say, "_ask_reason")
    assert "_ask_reason" in _src(s9_say.run)
    #: 🔴 이유 문단 위반만 골라내는 자리
    assert s9_say._reason_only(["(i) 이유 문단이 없다",
                                "(o) 새 사실 1건이 있는데 이유 문단이 …"])
    #: ⚠️ 실측 3회차 — `(p)`(전략 문장)도 **이유 문단 검열**이다
    assert s9_say._reason_only(["(p) 전략 판정이 있는데 이유 문단이 …",
                                "(o) 새 사실 …", "(i) 이유 문단이 없다"])
    assert not s9_say._reason_only(["🔴 (q) 근거 id 1개 — 2개 이상이다"])
    assert not s9_say._reason_only([])


# ══════════════════════════════════════════════════════════════════
# ② 가설 — 반박 원인과 측별 기준
# ══════════════════════════════════════════════════════════════════

def test_stale_cause_needs_a_stale_side_variable() -> None:
    """🔴🔴 ②-a — (b) `기준 낡음` 은 **그 가설의 근거**가 낡은 쪽일 때만."""
    from app.core.schema import Variable
    from app.core.stages import s6c_check as s6c
    row = s6c.Row(text="x", var_ids=["S01-home"], verdict="반박")
    v = [Variable(id="S01-home", type="recent_pattern", subject="team:000584",
                  favors="home", hardness="soft", weight=0.7,
                  usable_as_basis=True, claim="최근 5경기", quote="q")]
    kind, why = s6c._cause(row, variables=v, stale="🔴 결장 3명",
                           why="w", stale_sides={"home", "away"})
    assert kind == s6c.WRONG, (kind, why)
    #: 🔴 결장 변수면 (b) 가 맞다
    row2 = s6c.Row(text="y", var_ids=["R1"], verdict="반박")
    v2 = [Variable(id="R1", type="absence", subject="team:000585",
                   favors="home", hardness="hard", weight=0.7,
                   usable_as_basis=True, claim="결장", quote="q")]
    #: ⚠️ `R*`(기사 변수)는 id 꼬리가 없다 — **`subject` + `ref`** 로 쪽을 가린다
    kind2, why2 = s6c._cause(row2, variables=v2, stale="🔴 결장 5명",
                             why="w", stale_sides={"away"},
                             ref=_card().match)
    assert kind2 == s6c.STALE, (kind2, why2)
    assert "R1" in why2


def test_stale_cause_ignores_the_other_side() -> None:
    """🔴 ②-a — 결장 변수라도 **낡지 않은 쪽**이면 (b) 가 아니다."""
    from app.core.schema import Variable
    from app.core.stages import s6c_check as s6c
    row = s6c.Row(text="y", var_ids=["R1"], verdict="반박")
    v = [Variable(id="R1", type="absence", subject="team:000585",
                  favors="home", hardness="hard", weight=0.7,
                  usable_as_basis=True, claim="결장", quote="q")]
    kind, why = s6c._cause(row, variables=v, stale="🔴 결장 3명", why="w",
                           stale_sides={"home"}, ref=_card().match)
    assert kind == s6c.WRONG, kind
    #: 🔴 #3 — 그래도 **경기에는 낡음 의심이 있다**는 사실을 적는다
    assert "기준 낡음 의심" in why


def test_league_mean_is_side_aware() -> None:
    """🔴🔴 ②-b — `리그평균` 은 **측별**이다(홈은 홈 이점을 머금는다).

    실측(LAFC · `league:MLS`): 한 팀 몫 1.476 · 홈 배율 ×1.139
    → 홈 기준 1.681 · 원정 기준 1.271(합은 총골 기준 2.952 그대로다).
    """
    from app.core import signals
    from app.core.schema import Signal
    box = {"per_team": 1.476, "total": 2.952, "home_mul": 1.139,
           "per_home": 1.681, "per_away": 1.271, "why": "x"}
    one = Signal(metric="기대득점", side="home", ref="리그평균",
                 direction="<")
    got, why = signals.ref_of(one, {}, league=box)
    assert got is not None and abs(got - 1.681) < 0.01, (got, why)
    two = Signal(metric="기대득점", side="away", ref="리그평균",
                 direction="<")
    got2, _ = signals.ref_of(two, {}, league=box)
    assert got2 is not None and abs(got2 - 1.271) < 0.01, got2
    #: 🔴 측별 수가 없으면 **한 팀 몫**으로 돌아가고 그 사실을 사유에 적는다
    got3, why3 = signals.ref_of(one, {}, league={"per_team": 1.476})
    assert got3 is not None and abs(got3 - 1.476) < 1e-9
    assert "한 팀 몫" in why3 or "측별" in why3


def test_league_of_builds_both_sides() -> None:
    """🔴 ②-b 배선 — `league_of` 가 측별 기준을 만든다(홈 배율은 S3 의 그 함수)."""
    from app.core import signals
    #: 🔴 측별 기준을 만드는 자리는 `_sides_of` 다 — `league_of` 가 그것을 부른다
    assert "_sides_of" in _src(signals.league_of)
    src = _src(signals._sides_of)
    assert "per_home" in src and "per_away" in src
    assert "home_mul" in src, "홈 배율을 제 손으로 세고 있다(사본 금지)"


# ══════════════════════════════════════════════════════════════════
# ①-b 잘림 — **템플릿이 아니라 짧게 다시 받는다**
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-11(재현 2회차): 첫 호출이 `llm_truncated` 로 끊겼다
#     (`say` 상한 8000 · 추론이 7822). 축약판은 **코드 템플릿 글**이라 사람이
#     읽을 평이 아니다 — 잘렸으면 **짧은 질문으로 핵심만** 받는다.

def test_say_cap_is_above_the_measured_thinking() -> None:
    """🔴 `say` 출력 상한이 **실측 추론량(8000)** 보다 커야 한다."""
    from app import rules
    got = rules.llm_purpose("say") if hasattr(rules, "llm_purpose") else None
    if got is None:
        import yaml
        box = yaml.safe_load(open("config/llm.yaml", encoding="utf-8"))
        got = _find_say(box)
    assert int(got["max_tokens"]) >= 16000, got


def _find_say(box):
    """🔴 설정 나무에서 `say` 칸을 찾는다(경로를 베껴 적지 않는다)."""
    if isinstance(box, dict):
        if "say" in box and isinstance(box["say"], dict) \
                and "max_tokens" in box["say"]:
            return box["say"]
        for v in box.values():
            got = _find_say(v)
            if got:
                return got
    return None


def test_truncated_asks_for_the_core_instead_of_a_template() -> None:
    """🔴 잘리면 **`_ask_core`** 로 한 줄·이유 문단만 받는다."""
    from app.core.stages import s9_say
    assert hasattr(s9_say, "_ask_core")
    src = _src(s9_say.run)
    assert "_ask_core" in src
    #: 🔴 판정은 **코드가 고른 방향**을 쓴다 — 모델의 판정으로 덮지 않는다(검열 u)
    assert "verdict" not in _src(s9_say._ask_core).split("model_copy")[-1]


def test_empty_reason_is_rejected_by_the_schema() -> None:
    """🔴🔴 ①-c — **빈 이유 문단은 스키마가 거부한다**.

    ⚠️ 실사고 2026-10-11(재현 3·4회차): strict 스키마는 모든 칸을 `required` 로
       만들지만 **빈 글자는 통과한다** — 모델이 `"reason": ""` 를 세 번 보냈고
       검열이 평을 버렸다. 🔴 길이를 요구하면 `llm.ask` 가 오류를 붙여 다시 묻는다.
    """
    import pydantic
    import pytest
    from app.core.schema import MIN_REASON_CHARS, ReasonOnly, SayCore
    assert MIN_REASON_CHARS >= 50
    for cls in (ReasonOnly, SayCore):
        with pytest.raises(pydantic.ValidationError):
            cls(reason="")
        with pytest.raises(pydantic.ValidationError):
            cls(reason="짧다")
    got = ReasonOnly(reason="가" * MIN_REASON_CHARS)
    assert len(got.reason) == MIN_REASON_CHARS


def test_reason_check_gets_a_paragraph_not_a_list() -> None:
    """🔴🔴 ①-e — `reason_check` 는 **`.sentences` 를 가진 문단**을 받아야 한다.

    ⚠️ 실사고 2026-10-11(재현 5회차): `check()` 가 **리스트**를 넘겨
       *"(i) 이유 문단이 없다"* 가 **내용과 무관하게 늘** 떴다 — 1039자 문단에도
       떴다. 그래서 평이 네 번 버려졌다.
    """
    from app.core.schema import ReasonLine
    from app.core.stages import s9_say
    src = _src(s9_say.check)
    assert "_para_of" in src and "reason_check(para" in src
    got = s9_say._para_of(type("G", (), {
        "reason_lines": [], "reason": "첫 문장이다. 둘째 문장이다. 셋째다."})())
    assert len(got.sentences) == 3, got
    #: 🔴 모델이 문장별 근거를 줬으면 **그것을** 쓴다
    rows = [ReasonLine(text="x", fact_refs=["S02"])]
    got2 = s9_say._para_of(type("G", (), {"reason_lines": rows,
                                          "reason": "y"})())
    assert got2.sentences[0].fact_refs == ["S02"]


def test_prompt_asks_for_sentence_level_refs() -> None:
    """🔴 검열이 세는 꼴(`reason_lines`)을 프롬프트가 요구한다."""
    from app.core import saybundle
    from app.core.stages import s9_say
    card = _card()
    said = "\n".join(str(getattr(m, "content", ""))
                     for m in s9_say._prompt(card, saybundle.build(card)))
    assert "reason_lines" in said and "fact_refs" in said


# ══════════════════════════════════════════════════════════════════
# ①-f 글자에 쓴 근거를 읽는다(A 안 · 사용자 결정 2026-10-11)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 2026-10-11(가와사키 확정 XI): 마지막 문이 `(i) 구체성 — 고유 사실
#     종류가 **0종**`이었다. 까닭은 글이 나빠서가 아니다 — `_para_of` 가
#     `fact_refs` 를 **비운 채** 넘겨서, 종류를 셀 재료가 아예 없었다.
#  🔴 선례: `new_fact_check` 는 *"`fact_refs` 만 보면 모델이 번호를 안 적었을 때
#     멀쩡한 문장을 위반으로 센다 — 그래서 **글자도 본다**"*.

def _card_with_catalog():
    """🔴 카탈로그에 player·absence·form 셋이 있는 카드."""
    from app.core.schema import (Card, Facts, MatchRef, Missing, Player,
                                 ProbTriple, Variable, XI)
    ref = MatchRef(id="m", sport="soccer", competition="K League 1",
                   competition_short="KL1", home="team:000001",
                   away="team:000002", home_name="Gwangju FC",
                   away_name="Ulsan HD", kickoff_utc="2026-10-11T05:00:00Z")
    facts = Facts(
        xi={"team:000001": XI(team="team:000001", state="confirmed",
                              formation="4-4-2",
                              lineup=[Player(name="Marcinho", pos="FW")],
                              players=["Marcinho"])},
        missing={"team:000002": [Missing(name="Pedrinho", pos="FW",
                                         reason="injury")]})
    v = [Variable(id="S01-home", type="recent_pattern", subject="team:000001",
                  favors="home", hardness="soft", weight=0.7,
                  usable_as_basis=True, claim="최근 5경기", quote="q"),
         Variable(id="IR02-home", type="absence", subject="team:000001",
                  favors="away", hardness="soft", weight=0.7,
                  usable_as_basis=True, claim="결장", quote="q")]
    return Card(match=ref, facts=facts, variables=v,
                our_prob=ProbTriple(home=0.4, draw=0.3, away=0.3))


def test_para_reads_the_ids_the_model_wrote() -> None:
    """🔴🔴 A — 문장에 **적힌 id**를 `fact_refs` 로 읽는다."""
    from app.core.stages import s9_say
    card = _card_with_catalog()
    got = s9_say._para_of(type("G", (), {
        "reason_lines": [],
        "reason": ("홈은 S01-home 으로 최근 흐름이 살아 있다. "
                   "원정은 IR02-home 결장이 걸려 있다. "
                   "Marcinho 가 선발로 나온다.")})(), card=card)
    refs = [list(x.fact_refs) for x in got.sentences]
    assert len(got.sentences) == 3, refs
    assert "S01-home" in refs[0], refs
    assert "IR02-home" in refs[1], refs
    #: 🔴 선수 **이름**도 읽는다(`P:{이름}` 꼬리 · `new_fact_check` 와 같은 수법)
    assert any("Marcinho" in x for x in refs[2]), refs


def test_para_never_invents_an_id() -> None:
    """🔴 카탈로그에 **없는** 글자는 근거로 세지 않는다(#4)."""
    from app.core.stages import s9_say
    card = _card_with_catalog()
    got = s9_say._para_of(type("G", (), {
        "reason_lines": [],
        "reason": ("ZZ9 가 어쩌고 한다. Ronaldo 가 뛴다. 그래서 홈이 낫다.")})(),
        card=card)
    flat = [x for one in got.sentences for x in (one.fact_refs or [])]
    assert flat == [], flat


def test_i_censor_passes_with_three_kinds() -> None:
    """🔴🔴 그 결과로 `(i) 구체성` 이 **열린다**(종류 셋이면 통과)."""
    from app.core.stages import s9_audit, s9_say
    card = _card_with_catalog()
    para = s9_say._para_of(type("G", (), {
        "reason_lines": [],
        "reason": ("홈은 S01-home 으로 최근 흐름이 살아 있다. "
                   "원정은 IR02-home 결장이 걸려 있다. "
                   "Marcinho 가 선발로 나온다.")})(), card=card)
    bad = [x for x in (s9_audit.reason_check(para, card=card) or [])
           if "(i)" in x]
    assert not bad, bad


def test_check_passes_the_card_to_para() -> None:
    """🔴 배선 — `check` 가 카드를 넘긴다(카탈로그가 거기서 나온다)."""
    from app.core.stages import s9_say
    assert "_para_of(got, card=card)" in _src(s9_say.check)
