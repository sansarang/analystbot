"""🔴🔴 **s2d — 확정 라인업 전략 판정**. 사용자 지시 2026-10-10(둘째) §2-2·§2-3.

> 전략 판정(LLM **1회**, 구조화 출력 — 입력은 2-1 사실 + 동기 상태 + 감독 발언
> (새 사실) + 상대 XI 사실): 팀마다 strategy ∈ {…} + **근거 사실 id 2개 이상** +
> 한 줄 이유.
> 코드 검사: 판정이 **2-1 수치와 반대면 버린다**.

🔴 **예상 XI 로는 돌지 않는다**(§1) — 두 팀 중 하나라도 확정이 아니면
   `audit="확정 XI 전"` 으로 끝낸다. ⚠️ 예상 XI 는 우리가 **빈도로 지은 것**이라
   그것으로 전략을 읽으면 *"평소 그대로"* 가 늘 나온다(동어반복이다).
🔴 **확률을 움직이지 않는다** — 이 단계는 **판정**만 낸다. 이동량은
   `app/core/reweight.py`·`config/strategy_effects.yaml` 이 정한다(절대규칙 5).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.schema import Facts, MatchRef, StrategyLine, StrategyOut
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §2-2 — **근거 사실 id 몇 개 이상**(지시서가 적은 2)
MIN_REFS = 2


def run(ref: MatchRef, facts: Facts, *, state: RunState,
        news: list | None = None, turnover: dict | None = None) -> StrategyOut:
    """🔴🔴 §2-2 — 전략 판정 한 번. ⚠️ 못 하면 **사유를 담은 빈 산출**이다.

    🔴🔴 `turnover` 가 켜진 팀은 **`squad_turnover` 로 고정**한다(사용자 지시
       2026-10-10 지적 ③): *"전략 판정을 **로테이션으로 하지 않는다**(새 판정값:
       `squad_turnover`)"*. ⚠️ 그 팀은 LLM 에게 묻지 않는다 — 6자리가 바뀐 이유가
       **체력 관리가 아니라 그 선수들이 그 팀에 없어서**이기 때문이다.
    """
    from app.core import strategy as _st
    reads = {side: _st.read(ref, facts, side=side) for side in ("home", "away")}
    logger.info("[s2d] 전략 입력 — 확정 %s · 사실 %s",
                {s: g.confirmed for s, g in reads.items()},
                {s: len(g.facts) for s, g in reads.items()})
    box: dict[str, dict] = {}
    for side, got in reads.items():
        for f in got.facts:
            box[f.id if side == "home" else f"A{f.id[1:]}"] = {
                "side": side, "kind": f.kind, "text": f.text, "value": f.value}
    # 🔴 원정 쪽 id 를 `A*` 로 바꿨으므로 그 사실 목록도 같은 id 로 다시 든다
    reads["away"].facts = [type(f)(id=f"A{f.id[1:]}", kind=f.kind, text=f.text,
                                   value=f.value)
                           for f in reads["away"].facts]
    if not all(g.confirmed for g in reads.values()):
        said = " · ".join(f"{s}: {g.why}" for s, g in reads.items()
                          if not g.confirmed)
        state.note(f"s2d 전략 — {said}")
        logger.info("[s2d] **확정 XI 전** — %s", said[:160])
        return StrategyOut(audit="확정 XI 전",
                           violations=[said], facts=box)
    got = _ask(ref, facts, reads, box, state=state, news=news)
    if got is None:
        return StrategyOut(audit="안 돌았다", facts=box,
                           violations=["🔴 전략 판정 LLM 이 실패했다"])
    bad = check(got.lines, reads)
    if bad:
        # 🔴 §2-2 — **수치와 반대면 버린다**(다시 묻지 않는다 · 비용·결정성)
        state.note(f"s2d 전략 **버렸다** — {bad}")
        logger.info("[s2d] **버렸다** — %s", bad)
        return StrategyOut(audit="버렸다", violations=bad, facts=box)
    # 🔴🔴 지적 ③ — **선수단 교체는 로테이션이 아니다**. LLM 판정을 덮는다.
    lines = _turn_lines(got.lines, ref, turnover, state=state, box=box)
    got = got.model_copy(update={"lines": lines})
    shape = _st.shape_of(_side(got.lines, "home"), _side(got.lines, "away"),
                         home_name=ref.home_name, away_name=ref.away_name)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §3-2 **총골 기준에 λ 를 건다** — 전략 + ΔA·ΔD
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 기준은 `facts.standings["match_total_baseline"]` 하나다(새 기준선을
    #     만들지 않는다). ⚠️ `facts` 는 frozen 이므로 **여기서 고치지 않고**
    #     산출(`StrategyOut.facts`)에 담아 보낸다 — 카드와 `survive` 가 그것을
    #     읽는다(§7: 단계 사이는 타입 하나다).
    box["TOTAL"] = _total_fact(got, reads, facts)
    state.note(f"s2d 전략 — 홈 `{_side(got.lines, 'home')}` · 원정 "
               f"`{_side(got.lines, 'away')}` · 양상 `{shape}`")
    logger.info("[s2d] 전략 — 홈 `%s` · 원정 `%s` · 양상 `%s`",
                _side(got.lines, "home"), _side(got.lines, "away"), shape)
    return StrategyOut(lines=list(got.lines), shape=shape, audit="통과",
                       facts=box)


def _turn_lines(lines: list, ref: MatchRef, turnover: dict | None, *,
                state: RunState, box: dict) -> list:
    """🔴🔴 지적 ③ — 선수단이 교체된 팀의 판정을 **`squad_turnover` 로 바꾼다**.

    🔴 근거 id 는 LLM 이 댄 것을 **그대로 들고 간다**(새 id 를 짓지 않는다) —
       사실 묶음에 그 팀의 교체 사실이 이미 있다.
    ⚠️ `turnover` 가 없거나 꺼졌으면 **아무것도 바꾸지 않는다**.
    """
    from app.core import turnover as _turn
    box_t = dict(turnover or {})
    if not any(dict(v).get("on") for v in box_t.values()):
        return list(lines or [])
    out: list = []
    for one in (lines or []):
        side = str(getattr(one, "side", ""))
        got = dict(box_t.get(side) or {})
        if not got.get("on"):
            out.append(one)
            continue
        name = str(getattr(ref, f"{side}_name", "") or "")
        why = (f"{name} — **선수단 교체**({got.get('why')}). 바뀐 자리는 체력 "
               f"관리가 아니라 그 선수들이 **이 팀에 없어서**다 "
               f"(원래 판정 `{getattr(one, 'strategy', '')}` 을 덮었다)")
        out.append(one.model_copy(update={"strategy": _turn.VERDICT,
                                          "why": why}))
        state.note(f"s2d 전략 — {side} 판정을 **{_turn.VERDICT}** 로 바꿨다 · "
                   f"{got.get('why')}")
        box[f"TURN-{side}"] = {"side": side, "kind": "squad_turnover",
                               "text": why, "value": None}
    return out


def _total_fact(got, reads: dict, facts: Facts) -> dict:
    """🔴 §3-2 — **전략·ΔA·ΔD 로 움직인 총골 기준** 한 칸. 카드가 이것을 적는다."""
    from app.core import strategy as _st
    base = dict(getattr(facts, "standings", None) or {}).get(
        "match_total_baseline")
    said, why = _st.total_shift(got, facts)
    pct, why2 = _st.contrib_shift(reads.get("home"), reads.get("away"))
    if said is not None and pct:
        _cap_lo, cap_pct = _st.caps()
        # 🔴 **두 몫을 한 상한 안에서** 더한다(전략 + ΔA·ΔD · 새 상한 금지)
        base0 = float(base or said)
        now = (said / base0 - 1.0) * 100.0 if base0 else 0.0
        said, why = _st._apply(base0, now + pct, [why, why2], cap_pct)
    return {"side": "both", "kind": "total_lambda",
            "text": f"총골 기준 λ 이동 — {why}" + (f" / {why2}" if pct else ""),
            "value": said}


def _side(lines: list, side: str) -> str:
    for one in (lines or []):
        if str(getattr(one, "side", "")) == side:
            return str(getattr(one, "strategy", ""))
    return ""


def check(lines: list, reads: dict, *, turnover: dict | None = None,
          ) -> list[str]:
    """🔴🔴 §2-2 코드 검사 — **판정이 2-1 수치와 반대면 버린다**. 위반 목록.

    > 예: ΔA −15%·3백 전환인데 *"공격 위주"* → 위반. **근거 없는 판정 금지.**

    🔴 세는 것 다섯:
      ① 근거 사실 id **2개 이상**이고 그 id 가 **실제로 있다**
      ② `공격 위주` 인데 ΔA 가 크게 음수거나 수비 수가 늘었다 → 위반
      ③ `수비 위주` 인데 ΔA 가 크게 양수거나 수비 수가 줄었다 → 위반
      ④ `로테이션·체력 관리` 인데 **바뀐 자리가 0** → 위반
      ⑤ 🔴🔴 `squad_turnover` 는 **코드만 쓰는 값**이다 — 모델이 고르면 위반
    ⚠️ 못 잰 칸(`None`)은 **안 센다** — 없는 수로 판정을 버리면 그쪽이 더 나쁘다.
    """
    from app.core import turnover as _turn
    out: list[str] = []
    # ⑤ ⚠️ 실사고 2026-10-10: 열거값에 `squad_turnover` 를 더하자 **모델이 그것을
    #    골랐다**(FC 안양 — 전역 주기 팀이 아니다). 그 값은 깃발이 켜진 팀에만
    #    코드가 붙인다(`_turn_lines`). 🔴 주석으로 막은 줄 알았던 것을 계약으로 막는다.
    box_t = dict(turnover or {})
    for one in (lines or []):
        if str(getattr(one, "strategy", "")) != _turn.VERDICT:
            continue
        side = str(getattr(one, "side", ""))
        if not dict(box_t.get(side) or {}).get("on"):
            out.append(f"🔴 모델이 **코드만 쓰는 판정값**(`{_turn.VERDICT}`)을 "
                       f"골랐다({side}) — 그 팀은 선수단 교체 깃발이 **꺼져 있다**")
    for one in (lines or []):
        side = str(getattr(one, "side", ""))
        got = reads.get(side)
        if got is None:
            out.append(f"🔴 `{side}` 는 이 경기의 자리가 아니다")
            continue
        said = str(getattr(one, "strategy", ""))
        refs = [str(x) for x in (getattr(one, "fact_refs", None) or [])]
        known = set(got.ids())
        hit = [r for r in refs if r in known]
        if len(hit) < MIN_REFS:
            out.append(f"🔴 `{side}` {said} — 근거 사실이 {len(hit)}개다"
                       f"({MIN_REFS}개 이상이어야 한다 · 적은 것 {refs})")
        if said == "공격 위주":
            if got.da is not None and got.da <= -10.0:
                out.append(f"🔴 `{side}` **공격 위주**인데 공격 기여가 "
                           f"{got.da:+.0f}% 다(수치와 반대)")
            if _grew_back(got) or _to_three(got):
                out.append(f"🔴 `{side}` **공격 위주**인데 수비 "
                           f"{got.back_usual}백→{got.back_now}백 이다")
        if said == "수비 위주":
            if got.da is not None and got.da >= 10.0:
                out.append(f"🔴 `{side}` **수비 위주**인데 공격 기여가 "
                           f"{got.da:+.0f}% 다(수치와 반대)")
        if said == "로테이션·체력 관리" and got.changed == 0:
            out.append(f"🔴 `{side}` **로테이션**인데 바뀐 자리가 0 개다")
    return out


def _grew_back(got) -> bool:
    return (got.back_now is not None and got.back_usual is not None
            and got.back_now > got.back_usual)


def _to_three(got) -> bool:
    """🔴🔴 **3백 전환**인가 — 지시서가 그것을 **수비 신호**로 쓴다.

    ══════════════════════════════════════════════════════════════════
    ⚠️ **내가 거꾸로 짰다가 계약이 잡았다**(2026-10-10)
    ══════════════════════════════════════════════════════════════════

    처음에 *"수비 수가 줄었으면 `수비 위주` 와 모순"* 으로 짰다. 🔴 그런데 지시서가
    두 자리에서 **반대로** 말한다:
      · §2-2: *"ΔA −15%·**3백 전환**인데 '공격 위주' → **위반**"*
      · §5: 부천 *"**수비 위주** — **4백→3백**, 강릉 3-0 득점자 … 제외"*
    즉 3백 전환은 **수비 쪽 신호**다(윙백이 내려선다). 그래서 `공격 위주` 와
    모순이고 `수비 위주` 와는 모순이 **아니다**.
    🔴 수를 지어내지 않았다 — 지시서가 쓴 그대로다.
    """
    return (got.back_now is not None and got.back_usual is not None
            and got.back_now == 3 and got.back_usual > 3)


def _ask(ref: MatchRef, facts: Facts, reads: dict, box: dict, *,
         state: RunState, news: list | None) -> StrategyOut | None:
    """🔴 LLM **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    got = llm.ask(provider="deepseek", purpose="strategy",
                  messages=_prompt(ref, facts, reads, box, news=news),
                  out=StrategyOut, state=state)
    if isinstance(got, StrategyOut):
        return got
    state.note(f"s2d 전략 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    logger.info("[s2d] 🔴 LLM 실패 — %s · %s", getattr(got, "reason", "?"),
                str(getattr(got, "detail", ""))[:200])
    return None


def _prompt(ref: MatchRef, facts: Facts, reads: dict, box: dict, *,
            news: list | None) -> list:
    """🔴🔴 §2-2 — 지시서의 글을 프롬프트에 **그대로** 둔다(사본 금지).

    입력은 지시서가 적은 넷이다: **2-1 사실 · 동기 상태 · 감독 발언(새 사실) ·
    상대 XI 사실**.
    """
    from app.core import llm, strategy as _st
    said = "\n".join(f"- `{k}` [{v['kind']}] {v['text']}"
                     for k, v in box.items())
    look = dict(getattr(facts, "standings", None) or {}).get("group") or {}
    motive = (f"동기 상태: {look}" if look else "동기 상태: 자료 없음")
    quotes = "\n".join(f"- {str(getattr(v, 'claim', ''))[:120]}"
                       for v in (news or [])[:6]) or "- 없다"
    rule = (
        "🔴 **고를 수 있는 전략은 여섯뿐이다**(지시서 §2-2 원문): "
        + " · ".join(f"`{k}`" for k in _st.KINDS) + "\n"
        "🔴 팀마다 **근거 사실 id 2개 이상**을 `fact_refs` 에 적는다 — 위 목록의 "
        "`L*`(홈) · `A*`(원정) id 다. **없는 id 를 적지 않는다.**\n"
        "🔴 `why` 는 **한 줄**이다(근거 사실을 사람 말로 옮긴 것).\n"
        "⚠️ **수치와 반대인 판정을 내지 않는다** — 공격 기여가 크게 내려갔거나 "
        "수비 수가 늘었으면 `공격 위주` 가 아니다(코드가 그것을 검사해 **버린다**).\n"
        "⚠️ **교체 전문 선수의 벤치는 약화가 아니다** — `bench_regular` 로 적힌 "
        "선수가 벤치인 것은 *평소 운용*이다(그것을 근거로 `수비 위주` 라 하지 않는다).\n"
        "🔴 `shape`·`audit`·`violations`·`facts` 칸은 **비워 둔다** — 코드가 채운다.")
    return [
        llm.Message(role="system", content=(
            "너는 축구 경기의 **확정 라인업**을 보고 감독의 의도를 읽는다. "
            "주어진 사실만 쓰고, 없는 것을 지어내지 않는다. 확률·배당은 말하지 않는다.")),
        llm.Message(role="user", content=(
            f"경기: {ref.home_name}(홈) vs {ref.away_name}(원정) · "
            f"{ref.competition}\n"
            f"{motive}\n\n🔴 **오늘 명단에서 코드가 센 사실**(이것만 쓴다):\n"
            f"{said}\n\n🆕 **새 사실·감독 발언(72시간)**:\n{quotes}\n\n{rule}")),
    ]
