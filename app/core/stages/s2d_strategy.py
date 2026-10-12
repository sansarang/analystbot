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
        news: list | None = None, turnover: dict | None = None,
        priority: dict | None = None) -> StrategyOut:
    """🔴🔴 §2-2 — 전략 판정 한 번. ⚠️ 못 하면 **사유를 담은 빈 산출**이다.

    🔴🔴 `turnover` 가 켜진 팀은 **`squad_turnover` 로 고정**한다(사용자 지시
       2026-10-10 지적 ③): *"전략 판정을 **로테이션으로 하지 않는다**(새 판정값:
       `squad_turnover`)"*. ⚠️ 그 팀은 LLM 에게 묻지 않는다 — 6자리가 바뀐 이유가
       **체력 관리가 아니라 그 선수들이 그 팀에 없어서**이기 때문이다.
    """
    from app.core import strategy as _st
    reads = {side: _st.read(ref, facts, side=side) for side in ("home", "away")}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **[1b] 경기 우선순위 지수**(수정 지시서 2026-10-12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > ⑦ 전략 판정, 판정 함수 **앞**. 지수 = 오늘 XI 가치 ÷ 최강 XI 가치.
    #  > 전략 판정 입력에 넣는다 … **LLM 판정이 지수와 반대면 버리고 코드 판정.**
    #
    #  🔴 수를 만드는 곳은 `app/core/priority.py` 하나다(사본 금지).
    #  ⚠️ 지수가 없으면(가치·선발 빈도 부족) **아무것도 바꾸지 않는다**.
    said_pri = dict(priority or {})
    if said_pri:
        state.note("s2d [1b] 우선순위 지수 — "
                   + " · ".join(f"{s} {said_pri.get(s) if said_pri.get(s) is not None else '⬜'}"
                                for s in ("home", "away")))
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 ③ **버리고 끝내지 않는다 — 코드 판정으로 대체한다**(2026-10-11)
        # ══════════════════════════════════════════════════════════════
        #
        #  > ④에 걸려 버리면 → 코드 판정(바뀐 자리 수·ΔA·ΔD·핵심 선발 여부)으로
        #  > 대체해서 낸다. **빈칸 금지.**
        #
        #  ⚠️ 종전엔 `audit="버렸다"` 로 **줄이 0개**였고, 그 뒤 전술 예측·축2
        #     조정이 전부 재료를 잃었다(실측 2026-10-11 광주–울산 · LAFC).
        state.note(f"s2d 전략 **버렸다 → 코드 판정** — {bad}")
        logger.info("[s2d] 버렸다 → 코드 판정 — %s", bad)
        got = got.model_copy(update={"lines": _code_lines(reads, box)})
        return _settle(got, ref, facts, reads, turnover, box, state=state,
                       audit="코드 판정(LLM 버림)", violations=bad,
                       priority=said_pri)
    return _settle(got, ref, facts, reads, turnover, box, state=state,
                   audit="통과", violations=[], priority=said_pri)


def _pri_lines(lines: list, *, priority: dict | None,
               state: RunState) -> list:
    """🔴 [1b] — 지수와 **반대 판정을 버린다**. 사유를 줄에 남긴다."""
    from app.core import priority as _pr
    said = dict(priority or {})
    if not said:
        return list(lines or [])
    out = []
    for one in (lines or []):
        got = said.get(str(getattr(one, "side", "") or ""))
        now, why = _pr.verdict_check(str(getattr(one, "strategy", "") or ""),
                                     index=got)
        if now != str(getattr(one, "strategy", "") or ""):
            state.note(f"s2d [1b] {one.side} — {why}")
            out.append(one.model_copy(update={
                "strategy": now, "why": f"{one.why} · {why}".strip(" ·")}))
        else:
            out.append(one.model_copy(update={
                "why": f"{one.why} · {why}".strip(" ·")}))
    return out


def _settle(got, ref: MatchRef, facts: Facts, reads: dict,
            turnover: dict | None, box: dict, *, state: RunState,
            audit: str, violations: list,
            priority: dict | None = None) -> "StrategyOut":
    """🔴 전략 줄 → **산출**. 🔴 LLM 줄과 **코드 판정 줄이 같은 길**을 지난다.

    ⚠️ 종전엔 이 뒷단(교체 덮기·양상·총골 사실)이 `run` 안에만 있어서 **코드
       판정으로 갈아타면 그 전부를 잃었다**(사용자 지시 2026-10-11 ③).
    """
    from app.core import strategy as _st
    # 🔴🔴 지적 ③ — **선수단 교체는 로테이션이 아니다**. LLM 판정을 덮는다.
    lines = _turn_lines(got.lines, ref, turnover, state=state, box=box,
                        reads=reads)
    # 🔴🔴 **[1b] 지수가 LLM 판정을 덮는다**(수정 지시서 2026-10-12) —
    #    *"LLM 판정이 지수와 반대면 ④ 검사처럼 버리고 코드 판정"*.
    #    ⚠️ 지수가 없으면 아무것도 바꾸지 않는다(`priority.verdict_check`).
    lines = _pri_lines(lines, priority=priority, state=state)
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
    return StrategyOut(lines=list(got.lines), shape=shape, audit=audit,
                       violations=list(violations or []), facts=box)


#: 🔴🔴 ③ **코드 판정의 문턱** — ⚠️ **임시값**(적합 전)이고 그 사실을 사유에 적는다
#
#  > ④에 걸려 버리면 → **코드 판정**(바뀐 자리 수·ΔA·ΔD·핵심 선발 여부)으로
#  > 대체해서 낸다. **빈칸 금지.** — 사용자 지시 2026-10-11 ③
#
#  ⚠️ 실사고 2026-10-11(광주–울산 · LAFC): LLM 판정이 ④(핵심 공격 선발)에 걸려
#     **버려졌고**, 전략 블록이 *"버렸다"* 한 줄로 끝났다 — 그 뒤 전술 예측도
#     근거를 잃었다. 🔴 버리는 것과 **못 내는 것**은 다르다.
DA_BIG = 15.0        #: ΔA(공격 기여 변화율 %)가 이만큼이면 방향을 읽는다
CHANGED_ROT = 4      #: 바뀐 자리가 이만큼이면 로테이션으로 본다
PROVISIONAL = "🔴 **임시값**(적합 전)"


def _att_lines(reads: dict) -> str:
    """🔴🔴 ③ — **선발 선수별 공격 기여**와 바뀐 자리를 글로(프롬프트 입력).

    🔴 포메이션 글자를 대신하는 재료다 — *"누가 뛰는지"* 로 센다.
    ⚠️ 기여표가 비면 **그 사실을 적는다**(0 으로 메우지 않는다 · #3).
    """
    out: list[str] = []
    for side in ("home", "away"):
        read = reads.get(side)
        if read is None:
            continue
        att = dict(getattr(read, "att_table", None) or {})
        tot = sum(float(v) for v in att.values()) or 0.0
        said = dict(getattr(read, "key_state", None) or {})
        rows = [f"{nm} {float(v):.0f}"
                + (f"({float(v) / tot:.0%})" if tot else "")
                for nm, v in sorted(att.items(), key=lambda x: -float(x[1]))[:8]]
        out.append(
            f"- **{side}** 바뀐 자리 "
            f"{getattr(read, 'changed', None) if getattr(read, 'changed', None) is not None else '못 쟀다'}개"
            + (f" · ΔA {read.da:+.1f}%" if getattr(read, "da", None) is not None
               else " · ΔA 못 쟀다")
            + (f" · ΔD {read.dd:+.1f}%" if getattr(read, "dd", None) is not None
               else " · ΔD 못 쟀다")
            + (f" · 핵심 상태 {said}" if said else " · 핵심 선수 표 없음"))
        out.append("    기여 — " + (" · ".join(rows) if rows
                                   else "⬜ 기여표가 비었다"))
    return "\n".join(out) or "- ⬜ 자료 없음"


def code_verdict(read) -> tuple[str, str]:
    """🔴🔴 ③ — **코드가 내는 전략 판정**. `(판정, 까닭)`.

    재료 넷(지시서가 준 그것): **바뀐 자리 수 · ΔA · ΔD · 핵심 선발 여부**.
    🔴 값은 `strategy.KINDS` 안에서만 고른다(새 말을 만들지 않는다).
    ⚠️ 못 잰 칸(`None`)은 **읽지 않는다** — 0 으로 보지 않는다(#3).
    """
    from app.core import strategy as _st
    changed = getattr(read, "changed", None)
    da, dd = getattr(read, "da", None), getattr(read, "dd", None)
    said = dict(getattr(read, "key_state", None) or {})
    out_key = [nm for nm, v in said.items() if v in ("명단 제외", "벤치")]
    bits = [f"바뀐 자리 {changed if changed is not None else '못 쟀다'}",
            f"ΔA {da:+.1f}%" if da is not None else "ΔA 못 쟀다",
            f"ΔD {dd:+.1f}%" if dd is not None else "ΔD 못 쟀다",
            f"핵심 빠짐 {len(out_key)}명" if said else "핵심 선수 표 없음"]
    why = " · ".join(bits) + f" · {PROVISIONAL}"
    if da is not None and float(da) <= -DA_BIG:
        return "수비 위주", f"공격 기여가 크게 내려갔다 — {why}"
    if da is not None and float(da) >= DA_BIG:
        return "공격 위주", f"공격 기여가 크게 올라갔다 — {why}"
    if changed is not None and int(changed) >= CHANGED_ROT:
        return "로테이션·체력 관리", f"자리가 많이 바뀌었다 — {why}"
    assert "평소 그대로" in _st.KINDS
    return "평소 그대로", f"방향을 읽을 신호가 없다 — {why}"


def _code_lines(reads: dict, box: dict) -> list:
    """🔴 ③ — 두 팀의 **코드 판정 줄**(LLM 줄과 같은 꼴)."""
    out = []
    for side in ("home", "away"):
        read = reads.get(side)
        if read is None:
            continue
        got, why = code_verdict(read)
        refs = [k for k, v in dict(box or {}).items()
                if str(v.get("side") or "") == side][:3]
        out.append(StrategyLine(side=side, strategy=got, fact_refs=refs,
                                why=f"🔴 **코드 판정**(LLM 판정을 버렸다) — {why}"))
    return out


def _turn_lines(lines: list, ref: MatchRef, turnover: dict | None, *,
                state: RunState, box: dict, reads: dict | None = None) -> list:
    """🔴🔴 지적 ③ — 선수단이 교체된 팀의 판정을 **`squad_turnover` 로 바꾼다**.

    🔴 근거 id 는 LLM 이 댄 것을 **그대로 들고 간다**(새 id 를 짓지 않는다) —
       사실 묶음에 그 팀의 교체 사실이 이미 있다.
    ⚠️ `turnover` 가 없거나 꺼졌으면 **아무것도 바꾸지 않는다**.
    """
    from app.core import turnover as _turn
    box_t = dict(turnover or {})
    # 🔴 **깃발이 다 꺼져도 돈다** — (b) 가 *"모델이 코드 전용 값을 골랐으면 그 줄을
    #    덮으라"* 고 했고, 그 일은 깃발이 꺼진 팀에서 일어난다(실측 2026-10-10).
    out: list = []
    for one in (lines or []):
        side = str(getattr(one, "side", ""))
        got = dict(box_t.get(side) or {})
        if not got.get("on"):
            # 🔴 (b) — 깃발이 **꺼진** 팀이 코드 전용 값을 들고 있으면 그 줄만
            #    **덮는다**(버리는 것이 아니다 · 다른 팀 판정은 그대로).
            if str(getattr(one, "strategy", "")) == _turn.VERDICT:
                out.append(one.model_copy(update={
                    "strategy": "평소 그대로",
                    "why": (f"🔴 모델이 코드 전용 값(`{_turn.VERDICT}`)을 "
                            f"골랐다 — 깃발이 **꺼져 있어** `평소 그대로` 로 "
                            f"덮었다(원래 이유: "
                            f"{str(getattr(one, 'why', ''))[:60]})")}))
                state.note(f"s2d (b) — {side} 의 코드 전용 판정값을 "
                           f"`평소 그대로` 로 **덮었다**(깃발 꺼짐)")
                continue
            out.append(one)
            continue
        name = str(getattr(ref, f"{side}_name", "") or "")
        # 🔴🔴 **바뀐 자리가 0 개면 "바뀐 자리는…" 이라고 쓰지 않는다**
        #    ⚠️ 실사고 2026-10-11(올랜도): 같은 카드가 `L2 평소 XI 대비 바뀐 자리
        #       0개` 라고 적고 바로 아래서 *"바뀐 자리는 체력 관리가 아니라…"* 라고
        #       했다 — **가리키는 자리가 없는 문장**이다(모순).
        #    🔴 둘은 같이 성립한다: 최근 선발 5명이 명단에 없고, **평소 XI 자체가
        #       그 선수들이 빠진 뒤의 것**이면 오늘 XI 는 평소와 같다. 그 말을 쓴다.
        chg = getattr(dict(reads or {}).get(side), "changed", None)
        gone = len(list(got.get("off_squad") or []))
        tail = (f"바뀐 자리는 체력 관리가 아니라 그 선수들이 **이 팀에 없어서**다"
                if chg else
                f"오늘 XI 는 **평소와 같다**(바뀐 자리 {0 if chg == 0 else '미상'}개)"
                f" — 그런데 최근 선발 {gone}명이 오늘 명단에 없다. 즉 **평소 XI "
                f"자체가 그 선수들이 빠진 뒤의 것**이다")
        why = (f"{name} — **선수단 교체**({got.get('why')}). {tail} "
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
    # 🔴🔴 **(b) 안전장치**(사용자 결정 2026-10-10): *"LLM 이 코드 전용 값을
    #    고르면 **그 팀 줄만 버리고** 코드 깃발 값으로 덮는다. **다른 팀 판정은
    #    살린다**"*. 🔴 그래서 이것은 **위반이 아니다** — 아래 `_turn_lines` 가
    #    그 줄을 덮는다. ⚠️ 종전에는 위반으로 세서 **양 팀 판정이 다 버려졌다**
    #    (실측 2026-10-10: 카드에 *"판정을 버렸다"* 만 남았다).
    box_t = dict(turnover or {})
    for one in (lines or []):
        if str(getattr(one, "strategy", "")) != _turn.VERDICT:
            continue
        side = str(getattr(one, "side", ""))
        if not dict(box_t.get(side) or {}).get("on"):
            logger.info("[s2d] 모델이 `%s` 를 골랐다(%s) — 깃발이 꺼졌으니 "
                        "**그 줄만** 덮는다(다른 팀은 살린다)",
                        _turn.VERDICT, side)
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
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **포메이션 글자로 판정하지 않는다**(사용자 지시 2026-10-11 ④)
            # ══════════════════════════════════════════════════════════
            #
            #  > 포메이션 글자(최전방 몇 명)로 공격/수비를 판정하지 않는다.
            #  > **선수별 주 역할·시즌 공격 기여**로 센다.
            #
            #  ⚠️ 실사고 2026-10-11(LAFC): **손흥민·부앙가가 둘 다 선발**인데
            #     모델이 *"4-3-3→4-2-3-1 · 최전방 3→1명"* 이라는 **글자**만 보고
            #     `수비 위주` 라고 했다. 🔴 핵심 공격 자원이 그대로 서 있으면
            #     그것은 수비 위주가 아니다.
            on = _key_att_on(got)
            if on >= KEY_ATT_MIN:
                out.append(f"🔴 `{side}` **수비 위주**인데 핵심 공격 선수 "
                           f"{on}명이 **선발**이다 — 포메이션 글자가 아니라 "
                           f"**누가 뛰는지**로 센다(④)")
        if said == "로테이션·체력 관리" and got.changed == 0:
            out.append(f"🔴 `{side}` **로테이션**인데 바뀐 자리가 0 개다")
    return out


#: 🔴 핵심 공격 선수가 이만큼 선발이면 `수비 위주` 라고 부르지 않는다(지시 ④)
KEY_ATT_MIN = 2


def _key_att_on(got) -> int:
    """🔴 그 팀의 **핵심 공격 선수 중 선발**이 몇 명인가.

    🔴 `key_state` 는 득점+도움 상위를 든다(`strategy._key_state`) — 그 표가
       *"주 역할·시즌 공격 기여"* 다. ⚠️ 표가 비면 **0** 이고, 그러면 이 검사는
       아무 말도 하지 않는다(없는 근거로 판정을 버리지 않는다).
    """
    said = dict(getattr(got, "key_state", None) or {})
    return sum(1 for st in said.values() if str(st) == "선발")


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ③ **포메이션 대신 선수**(사용자 지시 2026-10-11 ③)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > LLM 입력에 포메이션 대신 **선발 선수별 시즌 공격 기여**·평소 XI 대비
    #  > **바뀐 자리**를 준다.
    #
    #  ⚠️ 실사고 2026-10-11: 모델이 포메이션 글자(`4-4-2`)로 *"수비 위주"* 를 골랐고
    #     ④ 검사(핵심 공격 선수가 선발이다)에 걸려 **버려졌다** — 두 번 다.
    #  🔴 표는 `strategy.TeamRead.att_table` 하나다(사본 금지) — 그 팀 선수단의
    #     시즌 득점+도움이고, 비중은 그 팀 합으로 나눈다.
    who = _att_lines(reads)
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
            f"{said}\n\n🧍 **선발 선수별 시즌 공격 기여(득점+도움) · 평소 XI 대비 "
            f"바뀐 자리**:\n{who}\n\n🆕 **새 사실·감독 발언(72시간)**:"
            f"\n{quotes}\n\n{rule}")),
    ]
