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
from typing import Any

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
        state: RunState, board_source: str = "none",
        bad: list[str] | None = None) -> Commentary | None:
    """🔴🔴 **작성자(DeepSeek) 1회** — 논평 하나(못 받으면 `None`).

    🔴 **검사하지 않는다** — 검열은 `s9_audit` 이 한다(사용자 지시 2026-10-07 §4).
       ⚠️ 작성자와 검열자를 한 함수에 두면 *"자기 글을 자기가 통과시키는"* 자리가
          생긴다. 🔴 그래서 이 함수는 **쓰기만** 한다.
    🔴 `bad` 가 있으면 **재작성**이다(§4-3) — 위반 목록을 붙여 다시 묻는다.
    """
    if not shape or not hypo or not hypo.scenarios:
        state.note("s8 논평 — 양상·시나리오가 없다(안 부른다)")
        return None
    basis = _basis(variables)
    scen = top_scen(hypo)
    prompt = _prompt(ref, shape, basis, scen, said, board_source,
                     spots=spots5(hypo))
    if bad:
        from app.core import llm as _llm
        prompt = prompt + [_llm.Message(
            role="user",
            content=("🔴 아래가 **검열에서 어긋났다** — 그 칸만 고쳐 다시 내라:\n"
                     + "\n".join(f"- {x}" for x in bad[:10])))]
        state.note(f"s8 논평 **재작성** — 위반 {len(bad)}건을 붙여 다시 묻는다")
    got = _ask(prompt, state=state)
    if got is not None:
        state.note(f"s8 논평 받았다 — `{got.title[:40]}` · 근거 {len(got.reasons)}줄")
    return got


def top_scen(hypo: HypoSet | None) -> list:
    """🔴 무게 상위 시나리오 — 작성자와 검열자가 **같은 목록**을 본다."""
    rows = list(getattr(hypo, "scenarios", None) or [])
    return sorted(rows, key=lambda s: -float(s.strength or 0.0))[:TOP_SCEN]


def template(ref: MatchRef, shape: dict, variables: list[Variable],
             hypo: HypoSet | None, said: Judgement) -> Commentary:
    """🔴 **코드 템플릿** — 검열이 두 번 어긋났을 때 쓰는 논평(§4-3)."""
    return _template(ref, shape, _basis(variables), top_scen(hypo), said)


def _basis(variables: list[Variable]) -> list[Variable]:
    """🔴 **근거 가능 변수 상위 4개**(무게 순) — 근거 불가는 **넣지 않는다**."""
    said = [v for v in variables if v.usable_as_basis]
    said.sort(key=lambda v: (-float(v.weight or 0.0), v.id))
    return said[:TOP_VARS]


def _scores_of(scen) -> list[str]:
    return [f"{h}-{a}" for s in scen for h, a in (s.outcomes or [])]


def dir_side(said: Judgement, ref: MatchRef | None) -> str:
    """🔴 방향 판정이 **어느 쪽**인가 — `home`·`away`·`""`(반반·없음).

    ⚠️ 방향 줄은 사람 글이다(*"방향: **Mexico** (세 열 중 2열이…)"*) — 그 글에 팀
       이름이 있으면 그 쪽이다. 🔴 *"반반"* 이면 빈 글자(제한 없음)다.
    """
    low = str(getattr(said, "direction", "") or "")
    if not low or ref is None or "반반" in low:
        return ""
    for key, name in (("home", ref.home_name), ("away", ref.away_name)):
        if name and name in low:
            return key
    return ""


def _winner(spot: str) -> str:
    """🔴 `2-1` → `home`. ⚠️ 판정은 `reweight.side_of` **하나**다(사본 금지)."""
    from app.core import reweight
    bits = str(spot).split("-")
    if len(bits) != 2 or not (bits[0].strip().isdigit()
                              and bits[1].strip().isdigit()):
        return ""
    return reweight.side_of(int(bits[0]), int(bits[1]))


def win_words() -> list[str]:
    """🔴 *"이 팀이 이긴다"* 를 뜻하는 낱말 — 표는 config 하나다(사본 금지)."""
    from app import rules
    said = (rules._load("config/interpret_rules.yaml")
            .get("commentary_win_words") or [])
    return [str(x) for x in said]


def flow_conflict(flow: str, side: str, ref: MatchRef | None) -> str:
    """🔴🔴 **예상 흐름의 승자가 방향과 어긋나나** — 어긋나면 사유 글(아니면 "").

    ⚠️ 실측 2026-10-07(멕시코–칠레): 방향은 **Mexico** 인데 흐름이 *"원정팀 Chile가
       한 골 차 승부로 가져간다"* 였다. 🔴 같은 카드가 두 말을 했다.
    🔴 센다 — 흐름을 **구절로 쪼개** 그 구절에 **반대 팀 이름 + 이김 낱말**이 같이
       있고 우리 쪽 이름이 없으면 어긋남이다(글자 검사의 한계는 그 구절 안으로 묶는다).
    """
    if not side or ref is None:
        return ""
    other = ref.away_name if side == "home" else ref.home_name
    mine = ref.home_name if side == "home" else ref.away_name
    if not other:
        return ""
    for part in re.split(r"[,.;·]|그러나|하지만|다만", str(flow or "")):
        if other not in part or (mine and mine in part):
            continue
        hit = [w for w in win_words() if w in part]
        if hit:
            return (f"예상 흐름이 **{other}** 가 이긴다고 말한다({hit[:2]}) — "
                    f"방향 판정은 **{mine}** 다")
    return ""


def check(got: Commentary, *, shape: dict, basis: list[Variable], scen,
          said: Judgement, ref: MatchRef | None = None) -> tuple[bool, list[str]]:
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
        # 🔴🔴 **보드가 없으면 기울기도 없다**(지시 ①: 등급은 걸 수 있는 줄에만)
        #    ⚠️ 실측 2026-10-07(온두라스–자메이카): 보드가 없어 전부 `보류` 인데
        #       논평이 `handicap Honduras -0.5` 를 가리켰다 — 걸 수 없는 줄이다.
        if {e.grade for e in said.evals} == {"보류"}:
            bad.append("보드가 없다(전부 `보류`) — lean 은 **빈 문자열**이어야 한다")
        elif got.lean.strip() not in lines:
            bad.append(f"lean `{got.lean}` 이 보드에 없는 줄이다({sorted(lines)[:4]}…)")
        graded = {e.grade for e in said.evals}
        if graded <= {"없음", "자료부족", "보류"} and "추천" in str(got.lean):
            bad.append("등급이 없는데 lean 이 **추천**이라고 말한다(기울기만 써라)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **흐름·스코어의 승자 = 방향 판정 팀**(사용자 지시 2026-10-07 재가중 ②)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 예상 흐름·예상 스코어의 승자 = 방향 판정 팀(방향이 "반반"이면 제한 없음).
    #
    #  ⚠️ 무승부 스코어는 **어느 쪽도 아니다** — 막지 않는다(방향이 승자를 고른 것이고
    #     무승부를 배제한 것은 아니다).
    side = dir_side(said, ref)
    if side:
        other = "away" if side == "home" else "home"
        who = (ref.away_name if side == "home" else ref.home_name) if ref else ""
        bad += [f"예상 스코어 `{x}` 의 승자가 **{who}** 다 — 방향 판정과 반대다"
                for x in got.score_range if _winner(str(x).strip()) == other]
        got_flow = flow_conflict(got.flow, side, ref)
        if got_flow:
            bad.append(got_flow)
    low = " ".join([got.title, got.flow, *[x.text for x in got.reasons]]).lower()
    for w in banned():
        if w in low:
            bad.append(f"금지어 `{w.strip()}` — 기대값·금액·시장 확률은 근거가 못 된다")
    return (not bad), bad


def _prompt(ref: MatchRef, shape: dict, basis: list[Variable], scen,
            said: Judgement, board_source: str,
            spots: set[str] | None = None) -> list[Any]:
    """🔴 입력은 **이미 센 수**다 — 시장 확률은 넣지 않는다(참고용 원칙).

    ⚠️ 경계에 **사전을 넘기지 않는다**(§9) — `llm.Message` 로 싼다.
    """
    from app.core import llm
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
    return [llm.Message(role="system", content=(
             "너는 축구 분석 카드의 **종합 논평**을 쓴다. 한국어로 쓴다.\n"
             "🔴 **숫자를 바꾸지 않는다** — 아래 수는 이미 센 것이고, 너는 그것을 "
             "**사람 말로** 설명한다.\n"
             "🔴 `title` 한 줄은 **양상을 말한다** — 주어진 양상 글자를 그대로 넣어라.\n"
             "🔴 `reasons` 는 3~4문장이고 **문장마다 근거 변수 번호**(`var_ids`)를 "
             "든다. 아래 목록에 **없는 번호는 쓰지 마라**.\n"
             "🔴 번호는 `var_ids` **칸에만** 넣는다 — `text` 안에 "
             "`(var_ids: …)` 처럼 적지 마라(카드에 그 글자가 그대로 나온다).\n"
             "🔴 `flow` 는 경기 흐름 한 줄이다 — 전반/후반 · 누가 주도 · 어떻게 끝나나.\n"
             "🔴 **흐름과 스코어의 승자는 아래 `방향 판정` 팀이다** — 그 팀이 아닌 "
             "쪽이 이긴다고 쓰지 마라(무승부는 괜찮다). 방향이 *반반*이면 자유다.\n"
             "🔴 `score_range` 는 **아래 `고를 수 있는 스코어`** 에서 1~3개를 "
             "고른다(그 밖은 검열에서 걸린다).\n"
             "🔴 `lean` 은 **아래 보드 줄 중** 논평과 같은 방향 하나이고, 없으면 "
             "**빈 문자열**이다. ⚠️ 등급이 없으면 *추천*이라고 쓰지 마라(기울기만).\n"
             "🔴 보드가 **없음**(등급이 전부 `보류`)이면 `lean` 은 반드시 "
             "**빈 문자열**이다 — 걸 수 없는 줄을 가리키지 마라.\n"
             "🔴 **금지**: 기대값·손익분기·켈리·금액·시장 확률(배당)을 근거로 쓰는 문장.\n"
             "🔴 도구는 없다. **한 번에** JSON 으로만 답한다.")),
            llm.Message(role="user", content=(
             f"경기: {ref.home_name}(홈) vs {ref.away_name}(원정) · "
             f"{ref.competition}\n"
             f"양상 판정: **{shape.get('shape')}** — {shape.get('why')}\n"
             f"비중: 2골 이하 {shape.get('low', 0):.0%} · 4골 이상 "
             f"{shape.get('high', 0):.0%} · 2골 차 이상 "
             f"{shape.get('one_sided', 0):.0%} · 한 골 안 "
             f"{shape.get('close', 0):.0%}\n"
             f"가장 무거운 스코어: "
             + " · ".join(f"{a}({b})" for a, b in shape.get("top_scores") or [])
             + "\n고를 수 있는 스코어(무게 상위 5): "
             + " · ".join(sorted(spots or set()))
             + f"\n\n근거 변수(이 번호만 쓸 수 있다):\n{rows or '- 없다'}\n\n"
             f"무게 상위 시나리오:\n{spots or '- 없다'}\n\n"
             f"보드 줄과 등급({board_source}): {grades or '없다'}\n"
             f"방향 판정: {said.direction}\n"))]


def spots5(hypo: HypoSet | None) -> set[str]:
    """🔴 **무게 상위 5 스코어** — 검열 (g) 가 보는 그 목록이다(사본 금지).

    ⚠️ 작성자에게 **같은 목록**을 줘야 한다 — 안 주면 매번 (g) 로 걸리고 논평이
       템플릿으로 떨어진다(실측 2026-10-07 미국–캐나다).
    🔴 **갈래 전부**를 센다(상위 3개가 아니다) — 검열과 같은 입력이어야 한다.
    """
    from app.core.stages.s9_audit import _top_spots
    return _top_spots(hypo, 5)


def _ask(messages: list[Any], *, state: RunState) -> Commentary | None:
    """🔴 DeepSeek **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    got = llm.ask(provider="deepseek", purpose="commentary",
                  messages=messages, out=Commentary, state=state)
    if isinstance(got, Commentary):
        return got
    state.note(f"s8 논평 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    return None


def _cut(said: str, n: int = 90) -> str:
    """🔴 글을 **낱말 경계에서** 자른다 — 가운데서 끊긴 글은 카드에 못 쓴다."""
    text = " ".join(str(said or "").split())
    if len(text) <= n:
        return text
    head = text[:n]
    if " " in head[n // 2:]:
        head = head[:head.rfind(" ")]
    return head.rstrip(" ,·") + "…"


def _template(ref: MatchRef, shape: dict, basis: list[Variable], scen,
              said: Judgement) -> Commentary:
    """🔴🔴 **코드 템플릿** — LLM 이 두 번 어긋났을 때. ⚠️ 수를 **그대로** 적는다.

    🔴 지어내지 않는다 — 양상·비중·변수 claim·스코어를 **이어 붙이는 것**뿐이다.
    ⚠️ 템플릿도 **검사를 지나야** 한다 — 방향과 반대인 스코어는 넣지 않고(재가중 ②),
       글은 **낱말 경계**에서 자른다(실측 2026-10-07: *"for a sec"* 로 끊겼다).
    """
    side = dir_side(said, ref)
    other = ("away" if side == "home" else "home") if side else ""
    who = ("" if not side else
           (ref.home_name if side == "home" else ref.away_name))
    spots = [f"{h}-{a}" for s in scen[:3] for h, a in (s.outcomes or [])
             if not other or _winner(f"{h}-{a}") != other][:3]
    tops = [str(a) for a, _ in (shape.get("top_scores") or [])
            if not other or _winner(str(a)) != other][:2]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **템플릿은 완결 문장이다**(사용자 지시 2026-10-09(6차) ④)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 템플릿은 *"양상 + 근거 셋을 **고정 문장 틀**에 넣은 **완결 문장**"* 만.
    # > 이어 붙인 나열(`·` 구분 3개 이상, 말줄임표)이 1겹에 나가면 **계약 실패**.
    #
    # ⚠️ 종전엔 `v.claim` 을 **그대로** 썼다 — claim 은 카드 블록용 나열이라
    #    (`최근 5경기 D L D D D · 득점 평균 0.6(보정 0.25) · 기준 팀당 …`)
    #    문장이 되지 않았다. 🔴 네 번 같은 꼴로 나갔다(가와사키·FC도쿄·토론토·강원).
    # 🔴 그래서 claim 을 **틀에 담는다** — 나열 기호와 말줄임표를 걷고, 유형별
    #    한 문장으로 맺는다. ⚠️ 수는 claim 에 있는 것만 쓴다(지어내지 않는다).
    lines = [CommentLine(text=_sentence(v, ref), var_ids=[v.id])
             for v in basis[:3]]
    kind = str(shape.get("shape") or "")
    flow = (f"무게가 가장 두꺼운 스코어는 {' · '.join(tops) or '못 쟀다'} 이고, "
            + (f"{who} 쪽이 앞서는 " if who else "어느 쪽도 앞세우지 못한 ")
            + f"{kind} 모양이다")
    return Commentary(
        title=(f"{kind} — " + (f"{who} 쪽에 무게가 실린다" if who
                               else "어느 쪽도 앞세우지 못한다")),
        reasons=lines, flow=flow, score_range=spots, lean="")


#: 🔴 §4 — 유형별 **고정 문장 틀**. ⚠️ 글은 여기 한 곳이다(사본 금지)
SENTENCE_FRAME: dict[str, str] = {
    "recent_pattern": "{who}의 최근 흐름은 {body}로 잡힌다.",
    "h2h_pattern": "두 팀 맞대결은 {body}다.",
    "home_field": "홈 이점은 {body}로 잡힌다.",
    "def_absence": "{who}는 {body}.",
    "absence": "{who}는 {body}.",
    "team_stats": "{who}는 {body}.",
    "fatigue": "{who}의 일정은 {body}.",
}
#: 🔴 나열 기호를 **문장 하나**로 줄일 때 쓰는 이음말
_JOIN = "이고 "


def _sentence(v: Variable, ref: MatchRef) -> str:
    """🔴🔴 §4 — 변수 claim 하나 → **완결 문장 하나**.

    🔴 claim 의 나열(`A · B · C`)에서 **앞 두 토막만** 쓰고 문장으로 맺는다.
       ⚠️ 세 토막 이상을 그대로 이으면 그것이 바로 지시가 금지한 나열이다.
    """
    said = " ".join(str(v.claim or "").split())
    # 🔴 **말줄임표를 걷는다** — 잘린 글은 문장이 아니다
    said = said.replace("…", "").strip()
    bits = [x.strip(" ,") for x in said.split("·") if x.strip(" ,")]
    body = _JOIN.join(bits[:2]) if len(bits) > 1 else (bits[0] if bits else "")
    body = body.rstrip(" .")
    who = (ref.home_name if str(v.subject) == str(ref.home)
           else ref.away_name if str(v.subject) == str(ref.away) else "")
    frame = SENTENCE_FRAME.get(str(v.type), "{who} {body}.")
    out = frame.format(who=who or "이 경기", body=body or "수치를 못 쟀다")
    return " ".join(out.replace("  ", " ").split())


def listy(said: str) -> bool:
    """🔴🔴 §4 — **나열인가**(`·` 3개 이상 또는 말줄임표). 계약이 이것을 본다."""
    low = str(said or "")
    return low.count("·") >= 3 or "…" in low



def plain(said: Commentary) -> str:
    """🔴 카드에 들어가는 **사람 말 한 문단** — 변수 번호·코드를 **지운다**(지시 ④)."""
    body = " ".join(x.text.strip() for x in said.reasons)
    body = re.sub(r"`[^`]+`", "", body)
    # 🔴 `(IR11-home)` 같은 번호 괄호 — ⚠️ `IR01-away` 처럼 **꼬리가 붙은** 번호도
    #    같이 지운다(실측 2026-10-07 카자흐–페로: 본문에 그 글자가 그대로 나왔다).
    body = re.sub(r"\(\s*(?:var_ids?\s*[:：]\s*)?"
                  r"[A-Z]{1,3}\d{1,2}[A-Za-z0-9_\-]*"
                  r"(?:\s*[,·]\s*[A-Z]{1,3}\d{1,2}[A-Za-z0-9_\-]*)*\s*\)",
                  "", body)
    body = re.sub(r"\(\s*var_ids?\s*[:：][^)]*\)", "", body)
    return " ".join(body.split())
