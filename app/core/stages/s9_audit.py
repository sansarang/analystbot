"""🔴🔴 **총평 검열**(사용자 지시 2026-10-07 §4) — 논평 생성 뒤, 카드 렌더 **전**.

> 두 겹으로 검사한다. **앞 겹은 코드, 뒤 겹은 다른 모델**이다. 작성자와 검열자를
> 같은 모델로 두지 않는다.

```
작성자  DeepSeek  (s8_comment.write)
검열자  Solar     (이 파일 · purpose="audit" · 출력 상한 600)
```

🔴 처리(§4-3): 위반 0 → 통과 · 위반 있음 → **재작성 1회** → 또 위반이면 **코드
   템플릿**. ⚠️ 사용자 카드(1겹)에는 **통과한 논평만** 나간다.
🔴 **검열을 통과시키려고 판정 수치·양상 문턱을 고치지 않는다**(지시 금지) — 유일한
   예외는 §4-1 (d) 가 말한 *"양상 근거 충돌 → shape 를 접전으로 낮춘다"* 이고,
   그것은 **문턱을 바꾸는 것이 아니라 그 경기의 판정을 내리는 것**이다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.schema import (AuditOut, Commentary, CommentOut, Facts, HypoSet,
                             Judgement, MatchRef, Variable)
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 검열자 — **작성자와 달라야 한다**(§4-2). 계약이 그 둘을 비교한다.
AUDITOR = "solar"
WRITER = "deepseek"
#: 🔴 모델 검열이 위반으로 세는 판정(§4-2) — `overclaim` 은 **경고**다(로그만)
HARD = ("contradicts", "unsupported")


def goal_words() -> dict:
    """🔴 득점 낱말표 — `config/interpret_rules.yaml` 하나가 원본이다(사본 금지)."""
    from app import rules
    box = (rules._load("config/interpret_rules.yaml")
           .get("commentary_goal_words") or {})
    return {k: [str(x) for x in (box.get(k) or [])] for k in ("up", "down")}


def goal_vote(variables: list[Variable]) -> tuple[str, str]:
    """🔴🔴 **득점 방향 다수결**(§4-1 (d)) — `(방향, 셈 글)`.

    > 득점 방향을 가진 근거 변수(폼 `goals`·실점·IR 규칙 `goals`)의 **다수결**.
    > 맞대결(S02)은 득점 방향 판단에서 최근 폼보다 약하다: 무게표 그대로(약 0.5),
    > **hard 여도 득점 방향은 soft 로** 센다.

    🔴 돌려주는 방향은 `up`·`down`·`""`(갈리거나 없다)다.
    """
    from app.types import WEIGHT_OF
    tally = {"up": 0.0, "down": 0.0}
    said: list[str] = []
    for v in variables:
        if not v.usable_as_basis:
            continue
        for got in (str(v.goals or "none"), str(getattr(v, "goals_against", "none"))):
            if got not in tally:
                continue
            # 🔴 맞대결은 **soft 로** 센다(hard 보너스를 주지 않는다)
            w = (float(WEIGHT_OF["soft"]) if v.type == "h2h_pattern"
                 else float(v.weight or 0.0))
            tally[got] += w
            said.append(f"{v.id}:{got}({w:.1f})")
    if not said:
        return "", "득점 방향을 가진 근거 변수가 없다"
    gap = tally["up"] - tally["down"]
    where = ("up" if gap > 0.01 else "down" if gap < -0.01 else "")
    return where, (f"up {tally['up']:.1f} · down {tally['down']:.1f} → "
                   f"{where or '갈렸다'} · {' '.join(said[:6])}")


def _nums(said: str) -> list[str]:
    """🔴 글에서 **숫자**를 뽑는다(§4-1 (f)) — 골·경기 수·%·날짜."""
    return re.findall(r"\d+(?:[.,]\d+)?", str(said or ""))


def facts_text(ref: MatchRef, facts: Facts, variables: list[Variable],
               hypo: HypoSet | None, shape: dict, said: Judgement,
               ours: Any = None) -> str:
    """🔴 **카드 사실 요약** — 검열자 입력이고 (f) 숫자 검사의 대조표다.

    ⚠️ 시장 확률은 **넣지 않는다**(시장은 논평 근거가 못 된다 · 금지).
    """
    rows = [f"[M] {ref.home_name}(홈) vs {ref.away_name}(원정) · {ref.competition}"]
    for key, who in ((ref.home, ref.home_name), (ref.away, ref.away_name)):
        box = dict((facts.recent or {}).get(key) or {})
        if box:
            rows.append(
                f"[F:{who}] 최근 {box.get('form', '')} · 득점 평균 "
                f"{box.get('scored_avg', '?')} · 보정 {box.get('trimmed', '?')} · "
                f"실점 평균 {box.get('conceded_avg', '?')}")
        miss = [m.name for m in (facts.missing or {}).get(key) or []]
        if miss:
            rows.append(f"[A:{who}] 결장 {', '.join(miss[:6])}")
        xi = (facts.xi or {}).get(key)
        if xi is not None:
            rows.append(f"[X:{who}] {xi.state} XI {xi.formation or '포메이션 미상'}")
    if facts.h2h:
        rows.append(f"[H] 맞대결 {json.dumps(facts.h2h, ensure_ascii=False)[:160]}")
    for v in variables:
        if not v.usable_as_basis:
            continue
        rows.append(f"[V:{v.id}] {v.type} · 승패 {v.favors} · 득점 {v.goals} · "
                    f"실점 {getattr(v, 'goals_against', 'none')} · "
                    f"무게 {v.weight} · {v.claim[:120]}")
    if shape:
        rows.append(f"[S] 양상 {shape.get('shape')} — 2골 이하 "
                    f"{shape.get('low', 0):.0%} · 4골 이상 {shape.get('high', 0):.0%} · "
                    f"2골 차 이상 {shape.get('one_sided', 0):.0%} · 한 골 안 "
                    f"{shape.get('close', 0):.0%}")
    if ours is not None:
        rows.append(f"[P] 우리 확률 홈 {ours.home:.0%} · 무 {ours.draw:.0%} · "
                    f"원정 {ours.away:.0%}")
    rows.append(f"[D] 방향 판정 {said.direction[:80]}")
    for sc in (hypo.scenarios if hypo else [])[:8]:
        rows.append(f"[Q:{sc.id}] {' · '.join(f'{h}-{a}' for h, a in sc.outcomes)} "
                    f"무게 {sc.strength}")
    return "\n".join(rows)


def code_check(got: Commentary, *, ref: MatchRef, facts: Facts,
               variables: list[Variable], hypo: HypoSet | None, shape: dict,
               said: Judgement) -> list[str]:
    """🔴🔴 **코드 검사 (a)~(h)** — 결정적이고 매번 돈다(§4-1). 위반 목록."""
    from app.core.stages import s8_comment as s8
    basis = s8._basis(variables)
    bad: list[str] = []
    # (a)(b)(c)(h) — 이미 한 검사(근거·승자·양상 글자·금지어)
    _ok, said_bad = s8.check(got, shape=shape, basis=basis,
                             scen=list(hypo.scenarios if hypo else []),
                             said=said, ref=ref)
    bad += said_bad
    by_id = {v.id: v for v in variables}
    # (d) 양상 근거 — 난타전·저득점은 **득점 방향 다수결**과 같아야 한다
    kind = str(shape.get("shape") or "")
    want = {"난타전": "up", "저득점": "down"}.get(kind, "")
    if want:
        where, why = goal_vote(variables)
        if where and where != want:
            bad.append(f"(d) 양상 근거 충돌 — 양상은 `{kind}` 인데 득점 방향 "
                       f"다수결은 `{where}` 다({why})")
    # (e) 인용 내용 방향 — 문장의 말과 그 문장이 든 변수의 득점 방향
    box = goal_words()
    for line in got.reasons:
        low = str(line.text or "")
        up_hit = [w for w in box["up"] if w in low]
        down_hit = [w for w in box["down"] if w in low]
        for vid in line.var_ids:
            v = by_id.get(vid)
            if v is None:
                continue
            got_dir = {str(v.goals or "none"),
                       str(getattr(v, "goals_against", "none"))}
            if up_hit and "down" in got_dir and "up" not in got_dir:
                bad.append(f"(e) `{vid}` 는 **득점↓** 인데 문장이 다득점을 "
                           f"말한다({up_hit[:2]})")
            if down_hit and "up" in got_dir and "down" not in got_dir:
                bad.append(f"(e) `{vid}` 는 **득점↑** 인데 문장이 저득점을 "
                           f"말한다({down_hit[:2]})")
    # (f) 숫자 — 카드 사실·변수 claim 에 그대로 있나
    pool = set(_nums(facts_text(ref, facts, variables, hypo, shape, said)))
    for v in variables:
        pool |= set(_nums(v.claim))
    pool |= {str(x) for x in range(0, 11)}      # ⚠️ 스코어 숫자는 사실이다
    for line in [*[x.text for x in got.reasons], got.flow, got.title]:
        for n in _nums(line):
            if n not in pool:
                bad.append(f"(f) 카드에 없는 숫자 `{n}` 를 적었다 — {str(line)[:40]}")
    # (g) 예상 스코어 — **재가중된 무게 상위 5개** 안
    spots = _top_spots(hypo, 5)
    for x in got.score_range:
        if spots and str(x).strip() not in spots:
            bad.append(f"(g) 예상 스코어 `{x}` 가 무게 상위 5개 {sorted(spots)} "
                       f"밖이다")
    return bad


def _top_spots(hypo: HypoSet | None, n: int) -> set[str]:
    """🔴 **스코어 무게 상위 n개** — 갈래 무게를 스코어 수로 나눠 센다."""
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return {k for k, _v in sorted(box.items(), key=lambda kv: -kv[1])[:n]}


def model_check(got: Commentary, *, ref: MatchRef, facts: Facts,
                variables: list[Variable], hypo: HypoSet | None, shape: dict,
                said: Judgement, state: RunState, ours: Any = None
                ) -> tuple[list[str], list[str]]:
    """🔴🔴 **모델 검열**(§4-2 · Solar 1회) — `(위반, 경고)`.

    🔴 검열자는 **판정만** 한다 — *"새 사실·새 예측을 만들지 마라"*.
    ⚠️ 못 불렀으면 **빈 목록**이다(그 사실은 `state` 에 남는다) — 검열이 없다고
       통과를 막지 않는다(카드는 나와야 한다 · §5).
    """
    from app.core import llm
    rows = [f"{i}. {x.text}" for i, x in enumerate(got.reasons)]
    rows.append(f"{len(got.reasons)}. [예상 흐름] {got.flow}")
    text = facts_text(ref, facts, variables, hypo, shape, said, ours=ours)
    out = llm.ask(
        provider=AUDITOR, purpose="audit", out=AuditOut, state=state,
        messages=[
            llm.Message(role="system", content=(
                "너는 **검열자**다. 아래 사실 목록과 논평 문장을 받아, 각 문장이 그 "
                "사실과 맞는지 **판정만** 한다.\n"
                "🔴 **새 사실·새 예측을 만들지 마라** — 분석하지 않는다.\n"
                "🔴 판정은 넷이다: `ok`(사실과 맞는다) · `contradicts`(사실과 "
                "반대다) · `unsupported`(사실에 없는 말이다) · `overclaim`(사실보다 "
                "세게 말한다).\n"
                "🔴 `index` 는 문장 번호, `fact_ref` 는 근거가 된 사실의 대괄호 "
                "id(`[V:R1]` 처럼) 또는 빈 글자, `note` 는 **20자 이내**다.\n"
                "⚠️ 문장 수만큼 줄을 낸다. 다른 말을 덧붙이지 않는다.")),
            llm.Message(role="user", content=(
                f"## 사실\n{text}\n\n## 논평 문장\n" + "\n".join(rows)))])
    if not isinstance(out, AuditOut):
        state.note(f"s9 모델 검열 **못 돌았다** — {getattr(out, 'reason', '?')}")
        return [], []
    bad: list[str] = []
    warn: list[str] = []
    for line in out.lines:
        n = int(line.index)
        who = rows[n][:40] if 0 <= n < len(rows) else f"문장 {n}"
        tag = f"{line.verdict}({line.fact_ref or '근거 없음'}·{line.note[:20]})"
        if line.verdict in HARD:
            bad.append(f"(모델) {tag} — {who}")
        elif line.verdict == "overclaim":
            warn.append(f"(모델 경고) {tag} — {who}")
    state.note(f"s9 모델 검열 — 위반 {len(bad)}건 · 경고 {len(warn)}건 "
               f"(검열자 `{AUDITOR}`)")
    return bad, warn


def _record(ref: MatchRef, audit: str, violations: list[str],
            shape: dict) -> None:
    """🔴 §4-4 — 경기마다 **결과와 위반 종류**를 남긴다(`/상태` 가 센다)."""
    from app import auditlog
    auditlog.add(match=str(ref.id), audit=audit,
                 violations=[x for x in violations if "위반" in x or audit
                             == "템플릿"],
                 shape=str(shape.get("shape") or ""))


def run(ref: MatchRef, facts: Facts, variables: list[Variable],
        hypo: HypoSet | None, said: Judgement, shape: dict, *,
        state: RunState, board_source: str = "none", ours: Any = None,
        write=None) -> CommentOut:
    """🔴🔴 **검열까지 끝낸 논평**(§4-3). 작성 → 코드 검사 → 모델 검열 → (재작성 1회).

    🔴 `write` 는 작성자다(기본 `s8_comment.run`) — **주입**으로 받는다. ⚠️ 계약이
       *"작성자와 검열자가 같은 모델이면 실패"* 를 그 둘의 이름으로 센다.
    """
    from app.core.stages import s8_comment as s8
    writer = write or s8.run
    notes: list[str] = []
    got = writer(ref, facts, variables, hypo, said, shape, state=state,
                 board_source=board_source)
    if got is None:
        notes.append("논평 없음 — 작성자가 답을 못 줬다 → 템플릿")
        _record(ref, "템플릿", ["작성 실패"], shape)
        return CommentOut(said=s8.template(ref, shape, variables, hypo, said),
                          notes=notes, audit="템플릿",
                          violations=["작성 실패"])
    kept = shape
    for turn in (1, 2):
        bad = code_check(got, ref=ref, facts=facts, variables=variables,
                         hypo=hypo, shape=kept, said=said)
        # 🔴 (d) 양상 근거 충돌 — **양상을 접전으로 낮추고** 다시 받는다(§4-1 (d))
        if any(x.startswith("(d)") for x in bad) and kept.get("shape") != "접전":
            kept = {**kept, "shape": "접전",
                    "why": (f"양상 근거 충돌로 낮췄다(본래 "
                            f"{kept.get('shape')} · {goal_vote(variables)[1]})")}
            state.note(f"s9 (d) 양상 근거 충돌 → **접전으로 낮췄다** "
                       f"(본래 {shape.get('shape')})")
            notes.append(f"양상을 접전으로 낮췄다(본래 {shape.get('shape')})")
        mbad, warn = model_check(got, ref=ref, facts=facts, variables=variables,
                                 hypo=hypo, shape=kept, said=said, state=state,
                                 ours=ours)
        notes += warn
        every = bad + mbad
        if not every:
            state.note(f"s9 검열 ✅ 통과({turn}회차)")
            said_audit = "통과" if turn == 1 else "재작성 후 통과"
            _record(ref, said_audit, notes, kept)
            return CommentOut(said=got, notes=notes, shape_used=kept,
                              audit=said_audit)
        notes += [f"{turn}차 위반: {x}" for x in every]
        state.note(f"s9 검열 {turn}차 **위반 {len(every)}건** — {every[:3]}")
        if turn == 2:
            break
        got2 = writer(ref, facts, variables, hypo, said, kept, state=state,
                      board_source=board_source, bad=every)
        if got2 is None:
            break
        got = got2
    state.note("s9 검열 **실패** → 코드 템플릿으로 바꾼다")
    notes.append("총평 검열 실패 — 템플릿 사용")
    bad_all = [x for x in notes if "위반" in x]
    _record(ref, "템플릿", bad_all, kept)
    return CommentOut(said=s8.template(ref, kept, variables, hypo, said),
                      notes=notes, shape_used=kept, audit="템플릿",
                      violations=bad_all)
