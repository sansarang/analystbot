"""🔴🔴 **s2f — 전술 전문가 예측**. 사용자 지시 2026-10-10(셋째) §6.

> 입력: **세 축 수치·발동 규칙·오늘 XI 변화·감독 발언·최종 확률**.
> 출력: 팀별 예상 운영, 예상 흐름(전반/후반), **승부처 1개**, **문장마다 근거 id**.
> 검열: **수치·규칙과 반대 문장 · 없는 수치 인용 · 최종 확률과 반대 결론 → 위반**.

🔴 **이야기는 확률을 움직이지 못한다**(§4 마지막 줄) — 이 단계는 **글만** 낸다.
   ⚠️ 그래서 파이프라인에서 **확률을 다 센 뒤**에 돈다(입력에 최종 확률이 든다).
🔴 LLM **1회**. 검열에 걸리면 **한 번 재작성**하고, 또 걸리면 **버린다**
   (고리를 길게 두면 모델이 검사를 통과할 말을 찾는다 — 그것은 예측이 아니다).
"""
from __future__ import annotations

import logging
import re

from app.core.schema import Card, TacticOut
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §6 — 내야 하는 칸 다섯(팀별 운영 2 · 흐름 2 · 승부처 1)
SLOTS = ("운영:home", "운영:away", "흐름:전반", "흐름:후반", "승부처")


def run(card: Card, *, state: RunState) -> TacticOut:
    """🔴🔴 §6 — 전술 예측 한 번(+재작성 한 번). ⚠️ 못 하면 사유를 담은 빈 산출."""
    facts = _facts(card)
    if not facts:
        said = "🔴 전술 예측 입력이 비었다 — 세 축 수치가 하나도 없다"
        state.note(f"s2f {said}")
        return TacticOut(audit="안 돌았다", violations=[said])
    got = _ask(card, facts, state=state, bad=None)
    if got is None:
        return TacticOut(audit="안 돌았다",
                         violations=["🔴 전술 예측 LLM 이 실패했다"])
    bad = check(got.lines, card=card, facts=facts)
    if bad:
        state.note(f"s2f 전술 예측 **재작성** — 위반 {len(bad)}건")
        again = _ask(card, facts, state=state, bad=bad)
        if again is None:
            return TacticOut(audit="버렸다", violations=bad)
        bad2 = check(again.lines, card=card, facts=facts)
        if bad2:
            state.note(f"s2f 전술 예측 **버렸다** — {bad2}")
            logger.info("[s2f] 버렸다 — %s", bad2)
            return TacticOut(audit="버렸다", violations=bad2)
        state.note("s2f 전술 예측 — 재작성 후 통과")
        return TacticOut(lines=list(again.lines), audit="재작성 후 통과")
    state.note(f"s2f 전술 예측 — 통과({len(got.lines)}줄)")
    logger.info("[s2f] 전술 예측 통과 — %d줄", len(got.lines))
    return TacticOut(lines=list(got.lines), audit="통과")


def _facts(card: Card) -> dict:
    """🔴 §6 입력 — **세 축 수치 + 발동 규칙 + XI 변화 + 최종 확률**을 id 로 묶는다.

    🔴 id 는 **그 규칙 이름**(`T1`·`T10`)과 전략 사실 id(`L*`·`A*`)다 — 모델이
       그것을 `refs` 에 적고, 검열이 **없는 id 를 잡는다**.
    """
    out: dict = {}
    box = dict(getattr(card, "matchup", None) or {})
    for side, one in dict(box.get("form") or {}).items():
        said = one.index()
        if said is not None:
            out[f"폼:{side}"] = {"kind": "form", "value": said,
                                 "text": f"{side} 보정 폼 지수 {said:+.2f}"}
    for side, one in dict(box.get("style") or {}).items():
        for name, val in dict(getattr(one, "axis", None) or {}).items():
            out[f"축2:{side}:{name}"] = {
                "kind": "style", "value": val,
                "text": f"{side} {name} {val:.3f}"}
    for f in [*(box.get("fired") or []), *(box.get("fired2") or [])]:
        out[str(f.rule)] = {
            "kind": "rule", "value": None,
            "text": (f"[{f.rule}] {f.side} {f.text}"
                     + (" (관찰만 — 확률 미반영)" if f.watch_only else ""))}
    plan = getattr(card, "strategy", None)
    for k, v in dict(getattr(plan, "facts", None) or {}).items():
        out[str(k)] = dict(v)
    sim = dict(box.get("sim") or {})
    if sim.get("home") is not None:
        out["시뮬"] = {"kind": "sim", "value": None,
                       "text": (f"분 단위 시뮬 승무패 {sim['home']:.0%}/"
                                f"{sim['draw']:.0%}/{sim['away']:.0%} · "
                                f"선제골 팀 승 {sim.get('first_wins')}")}
    if card.our_prob is not None:
        out["최종확률"] = {
            "kind": "prob", "value": None,
            "text": (f"최종 확률 홈 {card.our_prob.home:.0%} · 무 "
                     f"{card.our_prob.draw:.0%} · 원정 {card.our_prob.away:.0%}")}
    return out


def check(rows: list, *, card: Card, facts: dict) -> list[str]:
    """🔴🔴 §6 검열 — 세 가지를 센다.

    | 무엇 | 왜 |
    |---|---|
    | **없는 id 인용** | 근거를 지어낸 것이다 |
    | **없는 수치 인용** | 글에 적은 수가 입력에 없으면 지어낸 것이다 |
    | **최종 확률과 반대 결론** | 이야기가 판정과 다른 말을 한다 |

    ⚠️ 칸이 모자라도 위반이다(§6 이 다섯 칸을 요구한다).
    """
    from app.core import layer1
    out: list[str] = []
    if not rows:
        return ["🔴 전술 예측이 비었다"]
    got = {str(getattr(r, "slot", "")) for r in rows}
    miss = [s for s in SLOTS if s not in got]
    if miss:
        out.append(f"🔴 빠진 칸 {miss} — §6 은 다섯 칸을 요구한다")
    known = set(facts)
    nums = _numbers(facts)
    for r in rows:
        refs = [str(x) for x in (getattr(r, "refs", None) or [])]
        unknown = [x for x in refs if x not in known]
        if unknown:
            out.append(f"🔴 없는 근거 id {unknown[:3]} — `{str(getattr(r, 'text', ''))[:40]}`")
        if not refs:
            out.append(f"🔴 근거 id 가 없다 — `{str(getattr(r, 'text', ''))[:40]}`")
        for said in _numbers_in(str(getattr(r, "text", "") or "")):
            if not any(abs(said - x) <= max(0.051, abs(x) * 0.05)
                       for x in nums):
                out.append(f"🔴 **없는 수치**를 적었다({said}) — "
                           f"`{str(getattr(r, 'text', ''))[:40]}`")
                break
    # 🔴 **최종 확률과 반대 결론** — `승부처`·`흐름:후반` 이 반대 팀만 앞세우면 위반
    side = layer1.dir_side(card)
    if side:
        who = (card.match.home_name if side == "home"
               else card.match.away_name)
        other = (card.match.away_name if side == "home"
                 else card.match.home_name)
        for r in rows:
            if str(getattr(r, "slot", "")) not in ("승부처", "흐름:후반"):
                continue
            said = str(getattr(r, "text", "") or "")
            if other in said and who not in said:
                out.append(f"🔴 **최종 확률({who})과 반대 결론** — {said[:50]}")
    return out


#: 🔴 글에서 수를 뽑는다 — ⚠️ 백분율·소수를 함께 본다
_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%?")


def _numbers_in(said: str) -> list[float]:
    """🔴 그 문장이 **인용한 수들**. ⚠️ 분(`60분`)·연도는 뺀다(수치가 아니다)."""
    out: list[float] = []
    for m in _NUM.finditer(str(said or "")):
        tail = said[m.end():m.end() + 2]
        if tail.startswith("분") or tail.startswith("년"):
            continue
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _numbers(facts: dict) -> list[float]:
    """🔴 입력에 **있는 수들** — 검열이 이 목록과 대조한다."""
    out: list[float] = []
    for v in facts.values():
        box = dict(v)
        if box.get("value") is not None:
            try:
                out.append(float(box["value"]))
            except (TypeError, ValueError):
                pass
        out += _numbers_in(str(box.get("text") or ""))
    return out


def _ask(card: Card, facts: dict, *, state: RunState,
         bad: list[str] | None) -> TacticOut | None:
    """🔴 LLM **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    msgs = _prompt(card, facts)
    if bad:
        msgs = msgs + [llm.Message(role="user", content=(
            "🔴 아래가 **검열에서 어긋났다** — 그 자리만 고쳐 다시 내라:\n"
            + "\n".join(f"- {x}" for x in bad[:10])))]
    got = llm.ask(provider="deepseek", purpose="tactic", messages=msgs,
                  out=TacticOut, state=state)
    if isinstance(got, TacticOut):
        return got
    state.note(f"s2f 전술 예측 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    logger.info("[s2f] 🔴 LLM 실패 — %s", getattr(got, "reason", "?"))
    return None


def _prompt(card: Card, facts: dict) -> list:
    """🔴🔴 §6 — 지시서의 글을 프롬프트에 **그대로** 둔다(사본 금지)."""
    from app.core import llm
    m = card.match
    said = "\n".join(f"- `{k}` [{dict(v).get('kind')}] {dict(v).get('text')}"
                     for k, v in facts.items())
    rule = (
        "🔴 **내야 하는 칸 다섯**(지시서 §6 원문): 팀별 예상 운영(`운영:home`·"
        "`운영:away`) · 예상 흐름(`흐름:전반`·`흐름:후반`) · **승부처 1개**"
        "(`승부처` — 예: \"60분 이후 교체 구간\").\n"
        "🔴 **문장마다 `refs` 에 근거 id 를 적는다** — 위 목록의 id 뿐이다. "
        "**없는 id 를 적지 않는다.**\n"
        "🔴 **위에 없는 수를 글에 적지 않는다** — 검열이 그것을 잡아 버린다.\n"
        "⚠️ **최종 확률과 반대 결론을 내지 않는다**(§6 검열).\n"
        "⚠️ `관찰만` 이라고 적힌 규칙은 **확률에 안 들어간 것**이다 — 근거로 쓸 수 "
        "있지만 *\"그래서 확률이 움직였다\"* 고 쓰지 않는다.\n"
        "🔴 `audit`·`violations` 칸은 **비워 둔다**(코드가 채운다).")
    return [
        llm.Message(role="system", content=(
            "너는 축구 전술 분석가다. 주어진 수치와 규칙만 쓰고, 없는 것을 "
            "지어내지 않는다. 배당·기대값·금액은 말하지 않는다.")),
        llm.Message(role="user", content=(
            f"경기: {m.home_name}(홈) vs {m.away_name}(원정) · {m.competition}\n\n"
            f"🔴 **입력**(이것만 쓴다):\n{said}\n\n{rule}")),
    ]
