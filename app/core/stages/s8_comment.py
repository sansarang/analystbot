"""🔴🔴 **s8 — 종합 논평**. 사용자 지시 2026-10-07 ③. DeepSeek **1회** · 구조화 출력.

```
Card.shape + 근거 변수 상위 4 + 시나리오 상위 3 + 보드 판정 + 방향 → Commentary
```

🔴 **먼저 숫자를 고치고, 그 숫자에서 논평을 만든다**(지시 머리글) — 그래서 이 단계는
   **아무 수도 바꾸지 않는다**. 입력은 이미 센 값이고, 출력은 글뿐이다.
🔴 **근거 불가·`context_only` 변수는 넣지 않는다**(§4-1 과 같은 규율).
🔴 **시장 확률은 입력에 없다** — 시장은 참고용이다(2026-10-06(8차) 원칙).
⚠️ 코드 검사에 어긋나면 그 칸을 버리고 **1회 재요청**, 또 어긋나면 **코드 템플릿**이다.
"""
from __future__ import annotations

import logging
import re

from app.core.schema import (CommentOut, Commentary, CommentLine, Facts,
                             HypoSet, Judgement, MatchRef, Variable)
from app.core.state import RunState

logger = logging.getLogger(__name__)

def banned() -> list[str]:
    """🔴 논평 근거로 **쓸 수 없는 말** — 표는 `config/interpret_rules.yaml` 하나다.

    ⚠️ 낱말을 **코드에 적지 않는다** — `app/` 에 그 글자가 있으면 *"기대값 계산이
       없다"* 계약이 빨개진다(그 계약은 `app/**` 만 본다).
    """
    from app import rules
    said = (rules._load("config/interpret_rules.yaml")
            .get("commentary_banned") or [])
    return [str(x).lower() for x in said]
#: 🔴 논평에 넣는 변수 수·시나리오 수(지시 ③ 원문)
TOP_VARS = 4
TOP_SCEN = 3


def run(ref: MatchRef, facts: Facts, variables: list[Variable],
        hypo: HypoSet | None, said: Judgement, shape: dict, *,
        state: RunState, board_source: str = "none") -> CommentOut:
    """🔴 논평과 **버린 칸 사유들**(`CommentOut`). ⚠️ 못 만들면 `said=None` — 카드는 나온다.

    🔴 **느슨한 꼴을 안 돌려준다**(§7 정적 검사) — 단계 사이는 타입 하나다.
    """
    notes: list[str] = []
    if not shape or not hypo or not hypo.scenarios:
        notes.append("논평 없음 — 양상이나 시나리오가 없다")
        state.note("s8 논평 — 양상·시나리오가 없다(안 부른다)")
        return CommentOut(said=None, notes=notes)
    basis = _basis(variables)
    scen = sorted(hypo.scenarios, key=lambda s: -float(s.strength or 0.0))[:TOP_SCEN]
    prompt = _prompt(ref, shape, basis, scen, said, board_source)
    got = _ask(prompt, state=state)
    if got is None:
        notes.append("논평 없음 — LLM 이 답을 못 줬다")
        return CommentOut(said=_template(ref, shape, basis, scen, said),
                          notes=notes)
    ok, bad = check(got, shape=shape, basis=basis, scen=scen, said=said)
    if ok:
        state.note(f"s8 논평 ✅ `{got.title[:40]}` · 근거 {len(got.reasons)}줄")
        return CommentOut(said=got, notes=notes)
    # 🔴 **1회 재요청** — 어긋난 칸을 말해 주고 다시 받는다
    notes += [f"1차 어긋남: {x}" for x in bad]
    state.note(f"s8 논평 1차 어긋남 {bad} → **한 번만** 다시 묻는다")
    again = _ask(prompt + [{"role": "user", "content":
                            "🔴 아래가 어긋났다 — 그 칸만 고쳐 **다시** 내라:\n"
                            + "\n".join(f"- {x}" for x in bad)}], state=state)
    if again is not None:
        ok2, bad2 = check(again, shape=shape, basis=basis, scen=scen, said=said)
        if ok2:
            state.note("s8 논평 ✅ 2차에서 맞았다")
            return CommentOut(said=again, notes=notes)
        notes += [f"2차 어긋남: {x}" for x in bad2]
    state.note("s8 논평 — 두 번 어긋났다 → **코드 템플릿**으로 쓴다")
    notes.append("코드 템플릿으로 썼다(LLM 두 번 어긋남)")
    return CommentOut(said=_template(ref, shape, basis, scen, said),
                      notes=notes)


def _basis(variables: list[Variable]) -> list[Variable]:
    """🔴 **근거 가능 변수 상위 4개**(무게 순) — 근거 불가는 **넣지 않는다**."""
    said = [v for v in variables if v.usable_as_basis]
    said.sort(key=lambda v: (-float(v.weight or 0.0), v.id))
    return said[:TOP_VARS]


def _scores_of(scen) -> list[str]:
    return [f"{h}-{a}" for s in scen for h, a in (s.outcomes or [])]


def check(got: Commentary, *, shape: dict, basis: list[Variable], scen,
          said: Judgement) -> tuple[bool, list[str]]:
    """🔴🔴 **코드 검사**(지시 ③) — `(맞았나, 어긋난 것들)`.

    ⚠️ 글자 검사가 아니라 **값 대조**다: 양상 글자·스코어 목록·변수 번호·보드 줄.
    """
    bad: list[str] = []
    want = str(shape.get("shape") or "")
    if want and want not in str(got.title):
        bad.append(f"title 에 양상 `{want}` 이 없다(숫자와 반대로 말하면 안 된다)")
    spots = set(_scores_of(scen))
    for x in got.score_range:
        if str(x).strip() not in spots:
            bad.append(f"score_range `{x}` 가 상위 시나리오 스코어 {sorted(spots)} "
                       f"밖이다")
    ids = {v.id for v in basis}
    for line in got.reasons:
        for i in line.var_ids:
            if i not in ids:
                bad.append(f"reasons 가 근거 불가/없는 변수 `{i}` 를 들었다")
    # 🔴 보드 줄 — 등급이 없으면 *"추천"* 을 못 쓴다(기울기 표현만)
    lines = {f"{e.line.market} {e.line.side}"
             + (f" {e.line.point:g}" if e.line.point is not None else "")
             for e in said.evals}
    if got.lean:
        if got.lean.strip() not in lines:
            bad.append(f"lean `{got.lean}` 이 보드에 없는 줄이다({sorted(lines)[:4]}…)")
        graded = {e.grade for e in said.evals}
        if graded <= {"없음", "자료부족", "보류"} and "추천" in str(got.lean):
            bad.append("등급이 없는데 lean 이 **추천**이라고 말한다(기울기만 써라)")
    low = " ".join([got.title, got.flow, *[x.text for x in got.reasons]]).lower()
    for w in banned():
        if w in low:
            bad.append(f"금지어 `{w.strip()}` — 기대값·금액·시장 확률은 근거가 못 된다")
    return (not bad), bad


def _prompt(ref: MatchRef, shape: dict, basis: list[Variable], scen,
            said: Judgement, board_source: str) -> list[dict]:
    """🔴 입력은 **이미 센 수**다 — 시장 확률은 넣지 않는다(참고용 원칙)."""
    rows = "\n".join(
        f"- `{v.id}`({v.type} · 무게 {v.weight} · {v.hardness}) {v.claim[:150]}"
        for v in basis)
    spots = "\n".join(
        f"- `{s.id}` 무게 {s.strength} · 스코어 "
        + " · ".join(f"{h}-{a}" for h, a in s.outcomes)
        + f" — {s.mechanism[:170]}" for s in scen)
    grades = " · ".join(
        f"{e.line.market} {e.line.side}"
        + (f" {e.line.point:g}" if e.line.point is not None else "")
        + f" 생존 {e.survival:.3f} 등급 {e.grade}" for e in said.evals[:8])
    return [{"role": "system", "content":
             "너는 축구 분석 카드의 **종합 논평**을 쓴다. 한국어로 쓴다.\n"
             "🔴 **숫자를 바꾸지 않는다** — 아래 수는 이미 센 것이고, 너는 그것을 "
             "**사람 말로** 설명한다.\n"
             "🔴 `title` 한 줄은 **양상을 말한다** — 주어진 양상 글자를 그대로 넣어라.\n"
             "🔴 `reasons` 는 3~4문장이고 **문장마다 근거 변수 번호**(`var_ids`)를 "
             "든다. 아래 목록에 **없는 번호는 쓰지 마라**.\n"
             "🔴 `flow` 는 경기 흐름 한 줄이다 — 전반/후반 · 누가 주도 · 어떻게 끝나나.\n"
             "🔴 `score_range` 는 **아래 시나리오 스코어 중에서** 1~3개를 고른다.\n"
             "🔴 `lean` 은 **아래 보드 줄 중** 논평과 같은 방향 하나이고, 없으면 "
             "**빈 문자열**이다. ⚠️ 등급이 없으면 *추천*이라고 쓰지 마라(기울기만).\n"
             "🔴 **금지**: 기대값·손익분기·켈리·금액·시장 확률(배당)을 근거로 쓰는 문장.\n"
             "🔴 도구는 없다. **한 번에** JSON 으로만 답한다."},
            {"role": "user", "content":
             f"경기: {ref.home_name}(홈) vs {ref.away_name}(원정) · "
             f"{ref.competition}\n"
             f"양상 판정: **{shape.get('shape')}** — {shape.get('why')}\n"
             f"비중: 2골 이하 {shape.get('low', 0):.0%} · 4골 이상 "
             f"{shape.get('high', 0):.0%} · 2골 차 이상 "
             f"{shape.get('one_sided', 0):.0%} · 한 골 안 "
             f"{shape.get('close', 0):.0%}\n"
             f"가장 무거운 스코어: "
             + " · ".join(f"{a}({b})" for a, b in shape.get("top_scores") or [])
             + f"\n\n근거 변수(이 번호만 쓸 수 있다):\n{rows or '- 없다'}\n\n"
             f"무게 상위 시나리오:\n{spots or '- 없다'}\n\n"
             f"보드 줄과 등급({board_source}): {grades or '없다'}\n"
             f"방향 판정: {said.direction}\n"}]


def _ask(messages: list[dict], *, state: RunState) -> Commentary | None:
    """🔴 DeepSeek **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    got = llm.ask(provider="deepseek", purpose="commentary",
                  messages=messages,                      # type: ignore[arg-type]
                  out=Commentary, state=state)
    if isinstance(got, Commentary):
        return got
    state.note(f"s8 논평 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    return None


def _template(ref: MatchRef, shape: dict, basis: list[Variable], scen,
              said: Judgement) -> Commentary:
    """🔴🔴 **코드 템플릿** — LLM 이 두 번 어긋났을 때. ⚠️ 수를 **그대로** 적는다.

    🔴 지어내지 않는다 — 양상·비중·변수 claim·스코어를 **이어 붙이는 것**뿐이다.
    """
    spots = [f"{h}-{a}" for s in scen[:2] for h, a in (s.outcomes or [])][:3]
    lines = [CommentLine(text=f"{v.claim[:110]}", var_ids=[v.id])
             for v in basis[:3]]
    flow = (f"가장 무거운 갈래는 "
            + " · ".join(f"{a}" for a, _ in (shape.get("top_scores") or [])[:2])
            + f" 이고, 양상은 {shape.get('shape')} 다")
    return Commentary(
        title=f"{shape.get('shape')} — {ref.home_name} vs {ref.away_name}",
        reasons=lines, flow=flow, score_range=spots, lean="")


def same_input(before: dict, now: dict, before_vars: list[Variable],
               now_vars: list[Variable]) -> bool:
    """🔴 재분석에서 **다시 부를지** — 양상·근거 변수가 그대로면 **안 부른다**(지시 ③).

    > 비용: 경기당 1회, 재분석 때는 **shape 이나 근거 변수가 바뀐 경우에만** 다시.
    """
    if str(before.get("shape") or "") != str(now.get("shape") or ""):
        return False
    a = [(v.id, v.weight) for v in _basis(before_vars)]
    b = [(v.id, v.weight) for v in _basis(now_vars)]
    return a == b


def plain(said: Commentary) -> str:
    """🔴 카드에 들어가는 **사람 말 한 문단** — 변수 번호·코드를 **지운다**(지시 ④)."""
    body = " ".join(x.text.strip() for x in said.reasons)
    body = re.sub(r"`[^`]+`", "", body)
    body = re.sub(r"\(([A-Z]{1,3}\d{1,2}[^)]*)\)", "", body)
    return " ".join(body.split())
