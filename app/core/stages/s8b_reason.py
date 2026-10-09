"""🔴🔴 **s8b — 1겹 【이유】 문단**. 사용자 지시 2026-10-09(3차) §3.

> 작성자 DeepSeek **1회**, 구조화 출력.
> 출력: `{sentences: 3~5개, 각 문장 fact_refs(사실 id 1개 이상)}`

🔴 **아무 수도 바꾸지 않는다** — 입력은 이미 센 `Card` 의 사실 목록이고 출력은 글뿐이다
   (지시 머리글: *"판정·확률 계산은 건드리지 않는다 — 보여 주는 방식만 바꾼다"*).
🔴 **검사하지 않는다** — 검열은 `s9_audit.reason_check` 가 한다(작성자와 검열자를 한
   함수에 두면 자기 글을 자기가 통과시킨다 · §4 와 같은 규율).
⚠️ 시장 확률은 입력에 **없다**(금지: *"시장 확률을 이유로 쓰기"*).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.schema import Card, ReasonPara
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §3 — 문장 수. ⚠️ 넘거나 모자라면 검열이 잡는다
MIN_SENT = 3
MAX_SENT = 5


def run(card: Card, *, state: RunState,
        bad: list[str] | None = None) -> ReasonPara | None:
    """🔴 작성자 1회. `bad` 가 있으면 **재작성**이다(§4 마지막 줄 · 1회)."""
    from app.core import layer1
    box = layer1.facts_catalog(card)
    if not box:
        state.note("s8b 이유 문단 — 카드에 고유 사실이 없다(안 부른다)")
        return None
    prompt = _prompt(card, box)
    if bad:
        from app.core import llm as _llm
        prompt = prompt + [_llm.Message(
            role="user",
            content=("🔴 아래가 **검열에서 어긋났다** — 그 자리만 고쳐 다시 내라:\n"
                     + "\n".join(f"- {x}" for x in bad[:10])))]
        state.note(f"s8b 이유 문단 **재작성** — 위반 {len(bad)}건")
    got = _ask(prompt, state=state)
    if got is not None:
        state.note(f"s8b 이유 문단 받았다 — 문장 {len(got.sentences)}개")
    return got


def _ask(messages: list[Any], *, state: RunState) -> ReasonPara | None:
    """🔴 DeepSeek **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    got = llm.ask(provider="deepseek", purpose="reason",
                  messages=messages, out=ReasonPara, state=state)
    if isinstance(got, ReasonPara):
        return got
    state.note(f"s8b 이유 문단 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    return None


def _prompt(card: Card, box: dict[str, dict]) -> list:
    """🔴🔴 §3 **쓰는 법** — 지시문의 글을 프롬프트에 **그대로** 둔다.

    ⚠️ 규칙을 내 말로 줄여 적으면 그 순간 **사본**이 된다(CLAUDE.md #1) — 지시가
       바뀌면 여기가 따라가지 못한다. 🔴 그래서 원문을 인용한다.
    """
    from app.core import layer1, llm
    m = card.match
    facts = "\n".join(f"- `{k}` [{v['kind']}] {v['text']}"
                      for k, v in box.items())
    rule = (
        "🔴 **쓰는 법**(사용자 지시 2026-10-09(3차) §3 원문):\n"
        "- 축구 말을 써도 되지만(측면 전환·역습·세컨드볼·하프스페이스 등) 반드시 "
        "이 경기의 **선수·결장·수치와 묶어** 쓴다.\n"
        "  예) \"안톤이 빠진 대전 중앙을 전북이 이동준 쪽 측면 전환으로 노린다\" (O)"
        " / \"측면 전환이 살아나면 유리하다\" (X)\n"
        "- **마지막 문장**은 우리 결론(방향·걸지 여부)과 **같은 방향**으로 맺는다. "
        "반반이면 \"어느 쪽도 확신할 근거가 없다\"류.\n"
        "🔴 **금지**: 단정어(확실·반드시·필승·승리할 것이다 …) · 시장 확률을 이유로 "
        "쓰기 · 사실 목록에 **없는 선수** 언급 · 이 경기 사실이 빠진 일반론"
        "(어느 경기에나 붙는 문장).\n"
        f"🔴 문장은 **{MIN_SENT}~{MAX_SENT}개**, 문단 전체 "
        f"**{layer1.CAP_REASON}자 안**. 문장마다 `fact_refs` 에 위 사실 id 를 "
        "**하나 이상** 적는다(id 를 글에 적지는 말고 칸에만).\n"
        "🔴 문단에는 **서로 다른 종류**의 고유 사실이 최소 셋 들어가야 한다"
        "(선수 이름 · 결장·징계 · 순위·동기 · 맞대결 수치 · 폼 수치 중 셋).")
    return [
        llm.Message(role="system",
                    content=("너는 축구 분석 카드의 **이유 문단**을 쓴다. "
                             "주어진 사실만 쓰고, 없는 것을 지어내지 않는다.")),
        llm.Message(role="user", content=(
            f"경기: {m.home_name} vs {m.away_name} · {m.competition}\n"
            f"우리 결론: 방향 **{layer1.direction_words(card)}** · "
            f"걸지 여부 **{layer1.bet_words(card)}**\n\n"
            f"🔴 **카드 사실**(이것만 쓴다):\n{facts}\n\n{rule}")),
    ]


def template(card: Card) -> ReasonPara:
    """🔴 **코드 템플릿 문단**(§4 마지막 줄) — 검열이 두 번 어긋났을 때.

    🔴 글은 `layer1.template_reason` **하나**가 짓는다(사본 금지) — 여기서는 그
       글을 한 문장으로 담고 `fact_refs` 에 쓴 사실 id 를 적는다.
    """
    from app.core import layer1
    from app.core.schema import ReasonLine
    box = layer1.facts_catalog(card)
    want = ("absence", "rank", "h2h", "form", "player")
    refs: list[str] = []
    seen: set[str] = set()
    for kind in want:
        for fid, row in box.items():
            if row["kind"] == kind and kind not in seen:
                refs.append(fid)
                seen.add(kind)
                break
        if len(refs) >= 3:
            break
    return ReasonPara(sentences=[
        ReasonLine(text=layer1.template_reason(card), fact_refs=refs)])
