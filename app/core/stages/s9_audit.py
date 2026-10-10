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
    #  🔴 1겹은 `top_scores(…, 3)` 로 **코드가 고른다**(지시 2026-10-09(6차) ①) —
    #     검열은 그보다 **넓은 5개**를 허용한다(작성자가 쓴 글을 보는 자리다).
    #     ⚠️ 두 목록은 같은 함수에서 나온다(사본 금지).
    spots = {k for k, _w in top_scores(hypo, 5)}
    for x in got.score_range:
        if spots and str(x).strip() not in spots:
            bad.append(f"(g) 예상 스코어 `{x}` 가 무게 상위 5개 {sorted(spots)} "
                       f"밖이다")
    bad += h2h_direction_check(got, ref=ref, facts=facts)
    return bad


#: 🔴 "대등·좁다" 류 — 맞대결이 한쪽으로 기울었는데 쓰면 **위반**(지시 2026-10-09 ④)
#
#  ⚠️ 글자 목록을 코드에 두는 까닭: 이것은 **우리 글의 금지어**이지 자료가 아니다
#     (자료 쪽 표는 yaml 이 든다). 🔴 늘어나면 여기 한 곳이다.
H2H_EVEN_WORDS = ("대등", "비슷", "팽팽", "좁게", "좁은", "좁다", "호각",
                  "우열을 가리기", "격차가 좁", "크게 벌어지지", "밀리지 않")


def h2h_direction_check(got: Commentary, *, ref: MatchRef,
                        facts: Facts) -> list[str]:
    """🔴🔴 **(m) 맞대결 해석 방향**(사용자 지시 2026-10-09 ④).

    ⚠️ **번호가 (i) 에서 (m) 으로 바뀌었다** — 2026-10-09(3차) §4 가 (i)~(l) 을
       구체성·범용 문장·단정·선수 사실로 **못 박았다.** 🔴 번호는 사용자 지시가
       든다(그 글자로 사람이 말한다).

    > 총평 검열에 "맞대결 해석 방향" 검사 추가 — 한쪽 승이 다른 쪽의 **2배 이상**
    > 이면 "대등·좁다" 류 표현은 **위반**.

    🔴 왜 — 실측 2026-10-09(대전–전북): 맞대결이 대전 **1승 4무 5패**(상대 5승 =
       5배)인데 총평이 *"좀처럼 크게 벌어지지 않아 양 팀 간 격차가 좁게 유지돼
       왔다"* 고 적었다. ⚠️ 무승부가 많은 것과 **대등한 것**은 다르다 — 이기는
       쪽이 한쪽뿐이면 그 상성은 기울어 있다.
    ⚠️ 전적을 못 세면 **검사하지 않는다**(없는 것으로 위반을 만들지 않는다).
    """
    box = dict(facts.h2h or {})
    again = dict(box.get("recounted") or {})
    if again.get("n"):
        w, lose = int(again.get("w") or 0), int(again.get("l") or 0)
    else:
        said = box.get("summary")
        n = int(box.get("count") or 0)
        if not (isinstance(said, (list, tuple)) and len(said) == 3 and n
                and sum(int(x) for x in said) == n):
            return []
        w, lose = int(said[0]), int(said[2])
    hi, lo = max(w, lose), min(w, lose)
    # 🔴 **2배 이상**이 문턱이다. ⚠️ 적은 쪽이 0 이면(한쪽이 한 번도 못 이겼다)
    #    그것은 2배보다 더 기운 것이다 — 0 으로 나누지 않고 그 자리를 따로 센다.
    tilted = hi >= 2 * lo if lo else hi > 0
    if not tilted:
        return []
    lead = ref.home_name if w > lose else ref.away_name
    bad: list[str] = []
    for line in [*[x.text for x in got.reasons], got.flow, got.title]:
        said_line = str(line or "")
        hit = [x for x in H2H_EVEN_WORDS if x in said_line]
        if hit:
            bad.append(f"(m) 맞대결 해석 방향 — 전적이 {w}승 {lose}패로 "
                       f"**{lead} 쪽으로 기울었다**(한쪽이 다른 쪽의 "
                       f"{'∞' if not lo else f'{hi / lo:.1f}'}배)인데 문장이 "
                       f"{hit[:2]} 라고 적었다 — {said_line[:50]}")
    return bad


def top_scores(hypo: HypoSet | None, n: int = 3) -> list[tuple[str, float]]:
    """🔴🔴 **무게 상위 스코어 n개**(사용자 지시 2026-10-09(6차) ①) — 순서 그대로.

    > 예상 스코어: **재가중된 스코어 무게 상위 3개를 그대로 쓴다**(지금은 무게 1위
    > 갈래를 빼고 고른다).

    ⚠️ 실사고 2026-10-09(강원–부천): 무게 1위가 `C 1-2·0-1`(away 1.3525)인데 예상
       스코어가 `3-0 · 2-0 · 0-0` 이었다 — **1위 갈래가 빠졌다**(작성자가 골랐다).
    🔴 그래서 **코드가 고른다** — 작성자는 그 목록을 받아서 글만 쓴다.
    """
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return sorted(box.items(), key=lambda kv: (-kv[1], kv[0]))[:max(0, int(n))]


def score_drivers(hypo: HypoSet | None, spot: str) -> list[str]:
    """🔴 그 스코어를 그린 갈래들의 **근거 변수 id**(지시 ① 마지막 줄).

    > `0-0` 이 들어가면 **근거 변수 id 를 옆에 적는다**.
    """
    out: list[str] = []
    for sc in (hypo.scenarios if hypo else []):
        if spot not in {f"{h}-{a}" for h, a in (sc.outcomes or [])}:
            continue
        # 🔴 칸 이름은 `driver_vars` 다(`drivers` 가 아니다 — 추측하면 조용히 빈다)
        for vid in (getattr(sc, "driver_vars", None) or []):
            if str(vid) not in out:
                out.append(str(vid))
    return out


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
    # 🔴🔴 **흐름 줄은 예측이다** — 실측 2026-10-07: 검열자가 네 경기 **전부**에서
    #    *"전반 점유·후반 체력 저하는 사실에 없다"* 로 `unsupported` 를 매겨 논평이
    #    통째로 템플릿으로 떨어졌다. ⚠️ 그것은 검열자가 **예측을 사실로 본** 것이다.
    #    🔴 그래서 그 줄에 **표를 달아** 보낸다(검열 기준을 바꾸는 것이 아니라,
    #       그 줄이 무엇인지 말해 주는 것이다 — 반대면 여전히 `contradicts` 다).
    rows.append(f"{len(got.reasons)}. [예상 흐름 · **예측**] {got.flow}")
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
                "⚠️ 문장 수만큼 줄을 낸다. 다른 말을 덧붙이지 않는다.\n"
                "🔴 **`[예상 흐름 · 예측]` 줄은 예측이다** — 그 문장이 사실 목록에 "
                "그대로 없다고 `unsupported` 라 하지 마라. 사실·방향·양상과 "
                "**반대일 때만** `contradicts` 다(아니면 `ok`).")),
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
    # 🔴 **위반 줄만** 남긴다 — 메모(양상 낮춤·경고)는 종류 셈을 흐린다(#3: 그래도
    #    카드 `/디버그` 에는 전부 남는다).
    auditlog.add(match=str(ref.id), audit=audit,
                 violations=[x for x in violations
                             if "위반" in x or x == "작성 실패"],
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **1겹 이유 문단 검열 (i)~(l)** — 사용자 지시 2026-10-09(3차) §4
# ══════════════════════════════════════════════════════════════════
#
#  > 기존 총평 검열 4-1 에 **붙인다**. 위반 시 기존처럼 재작성 1회 → 실패하면
#  > 코드 템플릿 문단.
#
#  🔴 검열은 **코드**다(모델 아님) — 같은 문단이면 같은 판정이다.
#  ⚠️ (i)~(l) 은 이 문단에만 쓴다. 총평은 (a)~(h)·(m) 이 본다(다른 글이다).

#: 🔴 §4(i) — **종류가 다른 셋**. ⚠️ 같은 종류 셋은 하나로 센다
#  🔴 목록은 `layer1.SPECIFIC_KINDS` **하나**다(사본 금지 · #1) — 줄일 때도 같은
#     종류를 지켜야 하므로 두 곳이 같은 값을 봐야 한다.
from app.core.layer1 import SPECIFIC_KINDS  # noqa: E402
#: 🔴 §4(i) — 최소 개수
NEED_KINDS = 3


def reason_check(said, *, card) -> list[str]:
    """🔴🔴 **(i)~(l)** — 1겹 이유 문단의 코드 검열. 위반 목록(비면 통과).

    | 번호 | 무엇 |
    |---|---|
    | (i) | **구체성** — 이 경기 고유 사실이 **종류가 다른 셋** 이상 |
    | (j) | **범용 문장** — 문장마다 고유 사실이 하나 이상 |
    | (k) | **단정** — 단정어 금지 · 마지막 문장 방향 = 헤드라인 방향 |
    | (l) | **선수 사실** — 글에 나온 선수가 XI·결장·변수 대상에 있어야 한다 |
    """
    import re as _re

    from app.core import layer1
    if said is None or not getattr(said, "sentences", None):
        return ["(i) 이유 문단이 없다"]
    rows = list(said.sentences)
    bad: list[str] = []
    box = layer1.facts_catalog(card)
    # ── 문장 수(§3) — 3~5개
    from app.core.stages import s8b_reason as s8b
    if not (s8b.MIN_SENT <= len(rows) <= s8b.MAX_SENT):
        bad.append(f"(i) 문장이 {len(rows)}개다 — "
                   f"{s8b.MIN_SENT}~{s8b.MAX_SENT}개여야 한다")
    # ── (i) 구체성 — `fact_refs` 가 가리킨 사실의 **종류**를 센다
    kinds: set[str] = set()
    for line in rows:
        for fid in (line.fact_refs or []):
            kind = str((box.get(str(fid)) or {}).get("kind") or "")
            if kind in SPECIFIC_KINDS:
                kinds.add(kind)
    if len(kinds) < NEED_KINDS:
        bad.append(f"(i) 구체성 — 고유 사실 종류가 {sorted(kinds) or '없음'} "
                   f"({len(kinds)}종)뿐이다 · {NEED_KINDS}종 이상이어야 한다")
    # ── (j) 범용 문장 — 팀 이름 말고 고유 사실이 하나도 없으면 위반
    pool = layer1.player_pool(card)
    teams = {card.match.home_name, card.match.away_name}
    for line in rows:
        low = str(line.text or "")
        said_no_team = low
        for t in teams:
            said_no_team = said_no_team.replace(t, "")
        has_num = bool(_re.search(r"\d", said_no_team))
        has_player = any(nm and nm in low for nm in pool)
        has_ref = bool([f for f in (line.fact_refs or [])
                        if str(f) in box
                        and box[str(f)]["kind"] in SPECIFIC_KINDS])
        if not (has_num or has_player or has_ref):
            bad.append(f"(j) 범용 문장 — 이 경기 고유 사실이 없다: {low[:50]}")
    # ── (k) 단정어 · 마지막 문장 방향
    for line in rows:
        low = str(line.text or "")
        hit = [w for w in layer1.SURE_WORDS if w in low]
        if hit:
            bad.append(f"(k) 단정어 {hit[:2]} — {low[:40]}")
    side = layer1.dir_side(card)
    tail = str(rows[-1].text or "")
    if side:
        who = (card.match.home_name if side == "home"
               else card.match.away_name)
        other = (card.match.away_name if side == "home"
                 else card.match.home_name)
        # 🔴 **마지막 문장이 반대 팀만** 앞세우면 위반이다(방향이 어긋난다)
        if other in tail and who not in tail:
            bad.append(f"(k) 마지막 문장이 방향({who})과 다른 쪽을 말한다 — "
                       f"{tail[:50]}")
    elif not any(w in tail for w in ("어느 쪽도", "반반", "확신할 근거",
                                     "가리기 어렵", "단정할 수 없")):
        bad.append(f"(k) 방향이 **반반**인데 마지막 문장이 그 말을 안 한다 — "
                   f"{tail[:50]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(n) `must_win` 은 조건을 만족했을 때만**(지시 2026-10-09(5차) ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `must_win` 문장이 이유 문단에 들어가면 **그 조건을 만족했는지** 검열에서
    #  > 확인.
    #
    #  🔴 게이트가 닫혀 있으면(시즌 초) 그 글자는 **거짓**이다 — 실사고
    #     2026-10-09(가시마–감바 8라운드)에서 그 문장이 이유 문단에 들어갔다.
    look = dict(getattr(card, "outlook", None) or {})
    if not look.get("gate_open", True):
        for line in rows:
            low = str(line.text or "")
            hit = [w for w in ("must_win", "이겨야", "반드시 이겨", "승점이 급한",
                               "경우의 수") if w in low]
            if hit:
                bad.append(f"(n) 경우의 수 문장 — 게이트가 닫혔다"
                           f"({look.get('gate_why')})인데 {hit[:2]} 라고 적었다 — "
                           f"{low[:50]}")
    # ── (l) 선수 사실 — 사실 목록의 선수 id 로 대조한다
    known = {str(k)[2:] for k in box if str(k).startswith("P:")}
    known |= {str(k)[4:] for k in box if str(k).startswith("ABS:")}
    known |= pool
    for line in rows:
        for nm in _names_in(str(line.text or "")):
            if nm in teams:
                continue
            if not any(nm in k or k in nm for k in known if k):
                bad.append(f"(l) 선수 사실 — `{nm}` 은 XI·결장 명단·변수 대상에 "
                           f"없다(없는 선수 언급)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(o) 새 사실이 있으면 한 문장은 그것을 쓴다**(§3-5 · 2026-10-10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 카드 이유 문단에 새 사실이 하나라도 있으면 **최소 한 문장은 새 사실을
    #  > 쓴다**(검열 항목 추가).
    #
    #  🔴 세는 규칙은 `render.new_facts` 하나다(사본 금지).
    #  ⚠️ 새 사실이 **0건이면 이 항목은 아무것도 세지 않는다** — 없는 것을
    #     쓰라고 할 수는 없다(그 0건은 §3-4 가 카드에 적는다).
    bad += new_fact_check(rows, card=card)
    return bad


def new_fact_check(rows: list, *, card) -> list[str]:
    """🔴🔴 **(o) §3-5** — 새 사실이 있으면 **한 문장 이상**이 그것을 써야 한다.

    🔴 어떻게 세나: 새 사실 변수의 **id**(`R3`)가 그 문장의 `fact_refs` 에 있거나,
       그 변수의 **대상**(선수·팀 이름)이 문장 글자에 있으면 쓴 것으로 본다.
    ⚠️ `fact_refs` 만 보면 모델이 번호를 안 적었을 때 **멀쩡한 문장을 위반으로**
       센다(실측: 모델이 번호를 자주 빼먹는다). 🔴 그래서 글자도 본다.
    """
    from app.core import render
    got = render.new_facts(card)
    if not got:
        return []
    ids = {str(v.id) for v in got}
    words: set[str] = set()
    for v in got:
        for said in (str(v.target or ""), str(v.subject or "")):
            # ⚠️ `absence:손흥민` 처럼 **유형:대상** 꼴이다 — 뒤쪽만 쓴다
            one = said.split(":")[-1].strip()
            if len(one) >= 2:
                words.add(one)
    for line in (rows or []):
        if ids & {str(f) for f in (getattr(line, "fact_refs", None) or [])}:
            return []
        low = str(getattr(line, "text", "") or "")
        if any(w in low for w in words):
            return []
    return [f"(o) 새 사실 {len(got)}건이 있는데 이유 문단이 **하나도 안 썼다** — "
            f"§3-5(새 뉴스는 판단에 반드시 들어간다) · 새 사실 {sorted(ids)}"]



#: 🔴 사람 이름으로 **볼 수 있는** 조각 — 라틴 문자 두 낱말 이상이거나 한글 2~4자
#  ⚠️ 이것은 **느슨한 그물**이다 — 느슨해야 (l) 이 거짓 통과를 안 만든다. 그래서
#     잡힌 조각이 사실 목록에 있으면 통과이고, 없으면 사람이 보고 판단할 위반 글이다.
_LATIN_NAME = __import__("re").compile(
    r"\b[A-Z][a-zA-ZÀ-ɏ'’\-]+(?:\s+[A-Z][a-zA-ZÀ-ɏ'’\-]+)+")


def _names_in(said: str) -> list[str]:
    """🔴 문장에서 **선수 이름일 수 있는 조각**을 뽑는다.

    ⚠️ 한글 이름은 조사가 붙어(`안톤이`) 글자만으로는 못 가른다 — 🔴 그래서
       라틴 문자 이름만 뽑고, 한글은 (l) 대신 (j)·(i) 가 사실 id 로 센다.
       그 한계를 여기 적어 둔다(#3 · 지어내지 않는다).
    """
    return [m.group(0).strip() for m in _LATIN_NAME.finditer(str(said or ""))]
