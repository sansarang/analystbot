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
