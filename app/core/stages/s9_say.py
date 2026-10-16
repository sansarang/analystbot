"""🔴🔴 **s9say — 최종 평**. 사용자 지시 2026-10-10(넷째).

> 카드의 **마지막 단계**. 코드가 만든 사실 묶음만 보고 LLM이 한 편의 평을 쓴다 —
> *"누가 빠지고 누가 들어와서 → 어느 자리·측면이 강해지고 약해졌고 → 그래서 골이
> 어디서 나고 어디서 막히고 → 그래서 어느 팀이 이긴다"*.
> LLM은 **새 사실·새 숫자를 만들지 않는다. 확률도 바꾸지 않는다.**

🔴 입력은 `saybundle.build` 가 만든 **사실 묶음 하나뿐**이다(§1 마지막 줄).
🔴 검열 (q)~(v) 는 아래 `check` 하나가 든다. **위반 → 재작성 1회 → 또 위반이면
   코드 템플릿 평**(§3 마지막 줄) — 고리를 길게 두지 않는다.
"""
from __future__ import annotations

import logging
import re

from app.core.saybundle import APPROX, Bundle
from app.core.schema import Card, KeyPoint, SayOut
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §2 — `key_points` 는 **3~5개**다
MIN_POINTS, MAX_POINTS = 3, 5
#: 🔴 §3 (q) — 근거 id **2개 이상**
MIN_REFS = 2
#: 🔴 §3 (s) — 측면·자리 주장으로 세는 말(이 말이 나오면 측면 id 가 있어야 한다)
FLANK_WORDS = ("왼쪽", "오른쪽", "왼", "오른", "측면", "좌측", "우측")
#: 🔴 §3 (t) — 골 경로 주장으로 세는 말(1-3 사실 id 가 있어야 한다)
PATH_WORDS = ("필드골", "세트피스", "코너", "프리킥", "역습", "PK", "페널티",
              "자책골", "헤더")
#: 🔴 §3 (v) — 운 요소 득점을 **득점력의 근거로 쓰지 않는다**
LUCK_WORDS = ("PK", "페널티", "자책골")
POWER_WORDS = ("득점력", "결정력", "화력", "공격력")
#: 🔴 §3 (s) — **자리·측면 사실의 종류**(§1-1·1-2 에서 온 것). `s2d` 의 `L*`·`A*`
#  도 여기 든다 — 그것이 §1-1 *"자리별 교체"* 사실이다.
SPOT_KINDS = ("xi", "rotation", "swap", "flank_share", "flank_duel",
              "formation", "backline", "front", "key_player", "bench_regular")
#: 🔴 §3 (v) — **부정 표지**. 이 말이 있으면 그 문장은 운 요소를 **배제**한 것이다
DENY_WORDS = ("쓰지 않", "삼지 않", "아니", "없", "제외", "빼고", "빼면",
              "안 쓴", "말고")
#: 🔴 §2 — 근거 없는 감성어(사실 id 가 없으면 쓰지 않는다 · 금지 조항)
MOOD_WORDS = ("기세", "정신력", "투혼", "집중력", "자신감", "분위기", "사기")


def run(card: Card, *, state: RunState) -> SayOut:
    """🔴🔴 최종 평 한 번(+재작성 한 번, 그 뒤 템플릿)."""
    from app.core import saybundle
    box = saybundle.build(card)
    if not box.items:
        said = "🔴 사실 묶음이 비었다 — 평을 쓸 재료가 없다"
        state.note(f"s9say {said}")
        return SayOut(audit="안 돌았다", violations=[said])
    got = _ask(card, box, state=state, bad=None)
    if got is None:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **잘리면 축약판**(사용자 지시 2026-10-11 ⑦)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 잘리면 템플릿 대신 **"잘림 — 핵심 3줄만"** 축약판.
        #
        #  ⚠️ 실사고: LAFC·스포팅KC·상파울루가 **전부** `llm_truncated` 로 템플릿에
        #     떨어졌다. 템플릿은 *"코드가 고른 근거"* 를 그대로 읽어 사람이 읽을
        #     글이 아니다 — 잘린 것과 **못 쓴 것**은 다르다.
        why = str(getattr(state, "last_llm_reason", "") or "")
        if "truncat" in why.lower():
            said = template(card, box, why="🔴 **잘림 — 핵심 3줄만**")
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **잘렸으면 짧게 핵심만 다시 받는다**(2026-10-11)
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 축약판은 **코드 템플릿 글**이다 — *"코드가 고른 근거"* 를 그대로
            #     읽어 사람이 읽을 평이 아니다. 🔴 짧은 질문(칸 둘)은 잘리지
            #     않으므로 **한 줄·이유 문단**만 받아 그 자리에 넣는다.
            #  🔴 판정(방향)은 **코드가 고른 것**을 그대로 둔다(검열 (u)).
            core = _ask_core(card, box, state=state)
            audit = "잘림 — 핵심 3줄만"
            if core is not None and str(core.reason or "").strip():
                said = said.model_copy(update={
                    "one_line": (str(core.one_line or "").strip()
                                 or said.one_line),
                    "reason": str(core.reason or "").strip()})
                audit = "잘림 — 핵심만 다시 받았다"
                state.note("s9say 최종 평 — 🔴 잘렸다 → **핵심만 다시 받았다**"
                           "(한 줄·이유 문단)")
            else:
                state.note("s9say 최종 평 — 🔴 잘렸다 → **축약판**(핵심 3줄)")
            return said.model_copy(update={
                "audit": audit,
                "key_points": list(said.key_points)[:3],
                "flow_first": "⬜ 잘림 — 흐름은 적지 않는다",
                "flow_second": "⬜ 잘림 — 흐름은 적지 않는다"})
        state.note("s9say 최종 평 — LLM 실패 → **템플릿 평**")
        return template(card, box, why="LLM 이 실패했다")
    bad = check(got, card=card, box=box)
    if not bad:
        state.note(f"s9say 최종 평 — 통과({len(got.key_points)}개 주장)")
        logger.info("[s9say] 통과 — %s · %d개", got.verdict,
                    len(got.key_points))
        return got.model_copy(update={"audit": "통과", "used": _used(got, box)})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이유 문단만 어긋났으면 그 문단만 다시 묻는다**(2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-11(LAFC): 주장 다섯 줄은 멀쩡했는데 이유 문단이 비어
    #     있었고, **전체 재작성**이 `llm_truncated` 로 끊겨(출력 10991 중 추론
    #     7822) 그 멀쩡한 글까지 버려졌다. 🔴 짧은 질문은 잘리지 않는다.
    if _reason_only(bad):
        said = _ask_reason(card, box, state=state, bad=bad)
        logger.info("[s9say] 이유 문단 수선 — %d자 · 위반 %s",
                    len(said), bad[:2])
        if said:
            fixed = got.model_copy(update={"reason": said})
            bad2 = check(fixed, card=card, box=box)
            if not bad2:
                state.note("s9say 최종 평 — **이유 문단만 다시 받아** 통과")
                return fixed.model_copy(update={
                    "audit": "이유 문단 수선 후 통과",
                    "used": _used(fixed, box)})
            state.note(f"s9say 이유 문단 수선 — 아직 위반 {len(bad2)}건")
            logger.info("[s9say] 수선 뒤에도 위반 — %s", bad2[:3])
            bad = bad2
    state.note(f"s9say 최종 평 **재작성** — 위반 {len(bad)}건")
    again = _ask(card, box, state=state, bad=bad)
    if again is not None:
        bad2 = check(again, card=card, box=box)
        if not bad2:
            state.note("s9say 최종 평 — 재작성 후 통과")
            return again.model_copy(update={"audit": "재작성 후 통과",
                                            "used": _used(again, box)})
        bad = bad2
    state.note(f"s9say 최종 평 — **템플릿으로 내린다** · {bad[:3]}")
    logger.info("[s9say] 템플릿 — %s", bad[:3])
    # 🔴 **버린 평을 버리지 않는다** — 긴 카드가 그 글과 위반을 같이 보인다.
    #    ⚠️ 그러지 않으면 *"왜 템플릿이 됐나"* 를 사람이 추적할 길이 없다(#3).
    drop = again if again is not None else got
    return template(card, box, why="검열 두 번 위반", violations=bad,
                    dropped=_drop_of(drop))


def _drop_of(got: SayOut | None) -> list[str]:
    """🔴 버린 평을 **글자로** 남긴다(긴 카드가 적는다)."""
    if got is None:
        return []
    out = [f"결론 `{got.verdict}` · 한 줄 {got.one_line}"]
    out += [f"주장 — {kp.claim} / {kp.mechanism} · 근거 {list(kp.refs or [])}"
            for kp in (got.key_points or [])]
    return out


def _used(got: SayOut, box: Bundle) -> dict:
    """🔴 §4 긴 카드 — 글이 **쓴 id 의 원 사실**을 같이 싣는다."""
    out: dict = {}
    for kp in (got.key_points or []):
        for r in (kp.refs or []):
            one = box.items.get(str(r))
            if one is not None:
                out[str(r)] = one.text
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3 — **검열 (q)~(v)**
# ══════════════════════════════════════════════════════════════════

def check(got: SayOut, *, card: Card, box: Bundle) -> list[str]:
    """🔴🔴 §3 — **일곱** 가지를 센다. 돌려주는 것은 **위반 글 목록**이다.

    | 글자 | 무엇 |
    |---|---|
    | (q) | 근거 id 2개 이상 · 전부 묶음에 있는 id |
    | (r) | 문장 속 **숫자·선수 이름**이 근거 항목과 글자 그대로 맞는다 |
    | (s) | 측면·자리 주장은 측면 판정 id 가 있어야 한다(근사면 `근사` 표시) |
    | (t) | 골 경로 주장은 1-3(`G*`) id 필수 |
    | (u) | `verdict`·`one_line`·`flow` 가 **최종 확률 방향**과 같다 |
    | (v) | 자책골·PK 득점을 **득점력의 근거**로 쓰지 않는다 |
    | (w) | 🔴 **스코어 꼴**(`4-3`)은 묶음 글에 그 글자가 있어야 한다 |
    """
    from app.core import saybundle
    out: list[str] = []
    rows = list(got.key_points or [])
    if not (MIN_POINTS <= len(rows) <= MAX_POINTS):
        out.append(f"🔴 주장 수 {len(rows)}개 — §2 는 "
                   f"{MIN_POINTS}~{MAX_POINTS}개를 요구한다")
    for one in (got.one_line, got.flow_first, got.flow_second,
                got.decisive_moment, got.flip_condition, got.reason):
        if not str(one or "").strip():
            out.append("🔴 빈 칸이 있다 — §2 는 한 줄 요약·**이유 문단**·흐름 둘·"
                       "승부처·뒤집히는 조건을 **다** 요구한다")
            break
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **F7 — 옛 논평·이유 문단 검열이 여기로 들어왔다**(지시서 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  글을 한 편으로 합치면서 그 두 검열이 **갈 곳을 잃을 뻔했다**. 🔴 보장을
    #  지우지 않는다 — 같은 함수를 여기서 부른다(사본 금지).
    #    · `new_fact_check` — 새 사실(F 하위)이 **이유 문단에 쓰였나**(v6 §3)
    #    · `strategy_check` — 전략 문장이 **최종 확률과 같은 방향인가**(v6 §4)
    from app.core.stages.s9_audit import (new_fact_check,
                                          reason_check,
                                          strategy_check)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **검열이 읽는 꼴로 넘긴다** — 사용자 지시 2026-10-11
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: `reason_check` 는 **`.sentences` 를 가진 문단 객체**를 읽는데
    #     여기서 **리스트**를 넘겼다 — 그래서 *"(i) 이유 문단이 없다"* 가 내용과
    #     무관하게 **늘** 떴다(1039자 문단에도 떴다 · 실측 재현 5회차).
    #  🔴 `new_fact_check`·`strategy_check` 는 **줄 목록**을 읽는다(그대로 넘긴다).
    para = _para_of(got, card=card)
    said_reason = list(para.sentences)
    out += list(new_fact_check(said_reason, card=card) or [])
    out += list(strategy_check(said_reason, card=card) or [])
    #    · `reason_check` — 일반론·단정·없는 선수(v6 §3 1겹 검열)
    out += list(reason_check(para, card=card) or [])
    #    · `h2h_direction_check` — **맞대결 해석 방향**(v6 §4 (m)). ⚠️ 그 검열은
    #      옛 `Commentary` 꼴을 읽는다(`reasons`·`flow`·`title`) — 평의 글을 **그
    #      꼴로 싸서** 넘긴다(보장을 버리지 않는다 · 사본도 아니다).
    from app.core.stages.s9_audit import h2h_direction_check

    class _AsComment:
        def __init__(self, said: SayOut) -> None:
            self.reasons = [type("L", (), {"text": x})()
                            for x in (said.reason, said.flow_first,
                                      said.flow_second, said.decisive_moment)
                            if str(x or "").strip()]
            self.flow = str(said.flow_first or "")
            self.title = str(said.one_line or "")

    out += list(h2h_direction_check(_AsComment(got), ref=card.match,
                                    facts=card.facts) or [])
    known = box.ids()
    nums = _numbers_of(box)
    names = _names_of(box)
    #: 🔴 (w) — 묶음 글에 **글자로** 있는 스코어 꼴(지시 2026-10-14)
    scores = _scores_of(box)
    for kp in rows:
        said = f"{kp.claim} {kp.mechanism}"
        refs = [str(x) for x in (kp.refs or [])]
        # (q) 근거
        if len(refs) < MIN_REFS:
            out.append(f"🔴 (q) 근거 id {len(refs)}개 — 2개 이상이다: "
                       f"`{kp.claim[:30]}`")
        unknown = [x for x in refs if x not in known]
        if unknown:
            out.append(f"🔴 (q) **없는 근거 id** {unknown[:3]} — `{kp.claim[:30]}`")
        # (r) 수치·이름
        for val in _numbers_in(said):
            if not any(abs(val - x) <= max(0.051, abs(x) * 0.05) for x in nums):
                out.append(f"🔴 (r) **없는 수치**({val}) — `{said[:40]}`")
                break
        for nm in _names_in(said, names):
            if nm not in names:
                out.append(f"🔴 (r) **없는 선수 이름**({nm}) — `{said[:40]}`")
                break
        # 🔴🔴 (w) **스코어 꼴** — 묶음에 그 글자가 없으면 지어낸 것이다
        for sc in _scores_in(said):
            if sc not in scores:
                out.append(f"🔴 (w) **없는 스코어**({sc}) — 묶음에 그 꼴이 없다 · "
                           f"`{said[:40]}`")
                break
        # (s) 측면·자리 — 🔴 **id 앞글자가 아니라 사실의 종류**로 센다
        #
        #  ⚠️ 실측 2026-10-10(강원–부천): 평이 자리 근거로 **전략 사실**(`A6`·
        #     `A9` — `swap`·`key_player`)을 댔는데, 검열이 `X*`·`F*` 앞글자만
        #     받아 **거짓 위반**을 냈다. 🔴 `s2d` 의 `L*`·`A*` 도 §1-1 사실이다.
        if any(w in said for w in FLANK_WORDS):
            flanks = [r for r in refs
                      if box.items.get(str(r)) is not None
                      and box.items[str(r)].kind in SPOT_KINDS]
            if not flanks:
                out.append(f"🔴 (s) 측면·자리 주장에 **1-1·1-2 근거가 없다** — "
                           f"근거 {refs} · `{said[:60]}`")
            elif any(bool(box.items[str(r)].approx) for r in flanks) \
                    and APPROX not in said:
                out.append(f"🔴 (s) **근사 지표인데 `{APPROX}` 라고 안 썼다** — "
                           f"`{said[:40]}`")
        # (t) 골 경로
        if any(w in said for w in PATH_WORDS) \
                and not [r for r in refs if str(r).startswith("G")]:
            out.append(f"🔴 (t) 골 경로 주장에 **1-3 근거(`G*`)가 없다** — "
                       f"근거 {refs} · `{said[:60]}`")
        # (v) 운 요소 — 🔴 **"그 득점력"의 근거가 PK·자책골인** 모양만 센다
        #
        #  두 모양이다:
        #    ① 주장에 `득점력` 류가 있고 **그 메커니즘이** PK·자책골이다
        #       (지시서가 금지한 바로 그 꼴: *"PK로 만든 득점을 득점력의 근거로"*)
        #    ② 메커니즘 **한 문장 안**에 둘이 같이 있다
        #
        #  ⚠️ 실측 2026-10-10(강원–부천): 한 주장 안에서 앞은 *"강원 득점 유형은
        #     세트피스"*, 뒤는 *"부천 실점에 PK 비중"* 이었는데 **거짓 위반**으로
        #     걸려 좋은 평이 템플릿으로 떨어졌다 — 글 전체를 한 덩이로 봤기 때문이다.
        #    🔴 **부정문은 위반이 아니다** — ⚠️ 실측 2026-10-10(강원–부천): 평이
        #       *"운 요소라 **득점력 근거로 쓰지 않고** 경로·시간대만 근거로
        #       삼는다"* 고 적었는데 검열이 그것을 위반으로 잡았다. 그 문장은
        #       지시서가 **요구하는** 바로 그 태도다.
        hit = (any(w in kp.claim for w in POWER_WORDS)
               and any(w in said for w in LUCK_WORDS)
               and not _denied(kp.claim))
        if not hit:
            hit = any(any(w in one for w in LUCK_WORDS)
                      and any(w in one for w in POWER_WORDS)
                      and not _denied(one)
                      for one in _sentences(kp.mechanism))
        if hit:
            out.append(f"🔴 (v) **운 요소 득점을 득점력의 근거로 썼다** — "
                       f"`{said[:60]}`")
        # 🔴 근거 없는 감성어(§2 프롬프트 원칙 · 금지 조항)
        for w in MOOD_WORDS:
            if w in said:
                out.append(f"🔴 **근거 없는 감성어**(`{w}`) — `{said[:40]}`")
                break
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **단계 5 계약** — *"최종 평의 근거 id ⊂ 지지된 가설·변수"*
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 주장의 근거가 **반박된 가설(`R*`)** 이면 위반이다 — 그것은 `뒤집히는
    #     조건` 자리의 재료다. ⚠️ 검증표가 아예 없으면(가설 0건) 이 검사는 아무
    #     것도 세지 않는다(그 사실은 묶음의 `없음` 항목이 말한다).
    for kp in rows:
        bad_ref = [r for r in (kp.refs or []) if str(r).startswith("R")]
        if bad_ref:
            out.append(f"🔴 **반박된 가설을 근거로 썼다**({bad_ref[:3]}) — "
                       f"그것은 뒤집히는 조건 자리다: `{kp.claim[:30]}`")
    # 🔴🔴 S7 — **상성 사각이 있으면 반드시 한 문장**
    blind = [k for k in box.items if str(k).startswith("B")]
    if blind:
        said_all2 = " ".join([str(got.one_line or "")]
                             + [f"{kp.claim} {kp.mechanism}" for kp in rows])
        if not any(str(k) in said_all2 or "상성 사각" in said_all2
                   for k in blind):
            out.append(f"🔴 **상성 사각이 있는데 평이 그 말을 안 했다**({blind}) "
                       "— S7 은 그것을 **반드시 한 문장**으로 요구한다")
    # 🔴 S7 — 첫 줄에 **상성 판정**이 든다
    if box.items.get("M0") is not None:
        head = str(got.one_line or "")
        if "상성" not in head:
            out.append("🔴 **첫 줄에 상성 판정이 없다**(S7) — 우위 팀·강도를 적는다")
    # 🔴 §5 — 기준 낡음은 **첫 줄에** 적는다
    if box.items.get("H0") is not None and "기준 낡음" not in str(
            got.one_line or ""):
        out.append("🔴 **기준 낡음 의심인데 한 줄 요약이 그것을 안 적었다**(§5)")
    # (u) 방향
    want = saybundle.direction_of(card)
    said_all = " ".join(str(x or "") for x in
                        (got.verdict, got.one_line, got.flow_first,
                         got.flow_second))
    if want in ("반반", "무승부 쪽"):
        if str(got.verdict or "").strip() not in ("반반", "무승부 쪽"):
            out.append(f"🔴 (u) 확률 방향은 **{want}** 인데 평은 "
                       f"`{got.verdict}` 라고 단정했다")
        other = [x for x in (card.match.home_name, card.match.away_name)
                 if _wins_said(said_all, str(x or ""))]
        if other:
            out.append(f"🔴 (u) **{want}** 인데 `{other[0]}` 승리를 단정했다")
    else:
        if str(got.verdict or "").strip() != want:
            out.append(f"🔴 (u) `verdict` 가 확률 방향과 다르다 — "
                       f"평 `{got.verdict}` · 확률 **{want}**")
        lost = [x for x in (card.match.home_name, card.match.away_name)
                if str(x or "") != want and _wins_said(said_all, str(x or ""))]
        if lost:
            out.append(f"🔴 (u) 확률은 **{want}** 인데 평이 "
                       f"`{lost[0]}` 승리를 말한다")
    return out


#: 🔴 문장 끝 — 한국어 종결·마침표·중점으로 가른다
_SENT = re.compile(r"[.!?。]\s*|(?<=다)\s+|,\s*")


def _denied(said: str) -> bool:
    """🔴 (v) — 그 문장이 운 요소를 **배제**했나(그러면 위반이 아니다)."""
    return any(w in str(said or "") for w in DENY_WORDS)


def _sentences(said: str) -> list[str]:
    """🔴 (v) 가 **문장 안**에서만 세도록 가른다. ⚠️ 빈 토막은 버린다."""
    return [x.strip() for x in _SENT.split(str(said or "")) if x and x.strip()]


#: 🔴 *"{팀}이 이긴다"* 꼴 — ⚠️ 팀 이름이 그냥 나온 것과 가른다
_WIN = ("이긴다", "승리한다", "잡는다", "가져간다", "승리", "우세", "앞선다")


def _wins_said(said: str, team: str) -> bool:
    """🔴 (u) — 그 글이 **그 팀의 승리를 단정**했나."""
    if not team or team not in said:
        return False
    i = said.find(team)
    tail = said[i:i + len(team) + 24]
    return any(w in tail for w in _WIN)


#: 🔴 글에서 수를 뽑는다 — ⚠️ 분·연도는 수치가 아니다(`s2f_tactic` 과 같은 규칙)
_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%?")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(w) 스코어 꼴 금지** — 지시 2026-10-14 *"자료로만 · 지어내지 않는다"*
# ══════════════════════════════════════════════════════════════════
#
#  🔴 **이 단계를 지웠던 까닭이 이것이다**(커밋 `a7448733`): 광주 재현에서 평이
#     근거에 없는 **`4-3`** 을 적었고 그 수가 실제 결과와 같았다 — 누설로 읽힐
#     수 있는 서술이다.
#  ⚠️ 검열 (r) 은 그것을 **못 잡는다**: `_NUM` 이 `4` 와 `3` 을 낱개로 쪼개고,
#     묶음에 4 와 3 은 거의 늘 있다(골 수·경기 수). 🔴 그래서 **꼴 그대로**
#     대조하는 검사를 따로 둔다 — 묶음 글에 `4-3` 이라는 **글자**가 없으면 위반.
#  🔴 되살리면서 이 구멍을 **먼저** 막았다(지시 2026-10-14).
_SCORE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)")


def _scores_in(said: str) -> list[str]:
    """🔴 문장 속 **스코어 꼴** — `4-3`·`2 : 1` 을 `"4-3"` 으로 고른다."""
    return [f"{m.group(1)}-{m.group(2)}" for m in _SCORE.finditer(str(said or ""))]


def _scores_of(box: Bundle) -> set[str]:
    """🔴 묶음 글에 **글자로 있는** 스코어 꼴 전부."""
    out: set[str] = set()
    for one in box.items.values():
        out |= set(_scores_in(str(one.text or "")))
    return out


def _numbers_in(said: str) -> list[float]:
    out: list[float] = []
    for m in _NUM.finditer(str(said or "")):
        tail = said[m.end():m.end() + 2]
        if tail.startswith(("분", "년", "세")):
            continue
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _numbers_of(box: Bundle) -> list[float]:
    """🔴 묶음에 **있는 수들** — (r) 이 이 목록과 대조한다."""
    out: list[float] = []
    for one in box.items.values():
        if one.value is not None:
            out.append(float(one.value))
        out += _numbers_in(str(one.text or ""))
    return out


#: 🔴 선수 이름처럼 보이는 토막 — 로마자 이름(`Jae-Hyun Go`)과 한글 이름 둘 다
_NAME = re.compile(r"[A-Z][A-Za-zÀ-ÿ'’\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'’\-]+)+"
                   r"|[가-힣]{2,4}(?=(?:이|가|은|는|을|를|의|도|와|과)?\s)")


def _names_of(box: Bundle) -> set[str]:
    """🔴 묶음에 **있는 이름들**. ⚠️ 팀·대회 이름도 넣는다(그것도 사실이다)."""
    out: set[str] = set()
    for one in box.items.values():
        out |= set(_NAME.findall(str(one.text or "")))
    return {x.strip() for x in out if x.strip()}


#: 🔴🔴 **자리 글자**(포지션 접두) — 이름 앞에 붙는다. 사람 이름의 일부가 아니다.
#   ⚠️ 실사고 2026-10-16(코스타리카): 평이 *"CB **Waston**"*·*"CM **Soto**"*·
#      *"DM **López**"* 라고 썼고 검열이 셋 다 **없는 이름**이라 했다 — 묶음에는
#      `Waston`·`Soto`·`Alexander López` 가 **그대로 있었다**(실측).
#   🔴 까닭 둘: ① `_NAME` 이 **두 낱말 이상**만 이름으로 보므로 묶음의 한 낱말
#      이름(`Waston`)을 **아예 모으지 못했다** ② 문장 쪽은 접두가 붙어 두 낱말이
#      되어 후보로 잡혔다 — **비대칭**이다.
_POS = re.compile(r"^(?:GK|DF|MF|FW|CB|LCB|RCB|LB|RB|FB|WB|FB/WB|CDM|DM|CM|"
                  r"LM|RM|AM|CAM|LW|RW|ST|CF|SS)\s+", re.I)


def strip_pos(said: str) -> str:
    """🔴 이름 앞의 **자리 글자**를 떼낸다(`CB Waston` → `Waston`)."""
    got = str(said or "").strip()
    for _ in range(3):
        cut = _POS.sub("", got).strip()
        if cut == got:
            break
        got = cut
    return got


def _names_in(said: str, known: set[str], *, text: str = "") -> list[str]:
    """🔴 (r) — 글이 **인용한, 묶음에 없는** 이름들. ⚠️ 로마자 이름만 센다.

    ⚠️ 한글 토막은 보통 명사(*"오른쪽"*·*"수비"*)와 섞여 거짓 위반을 만든다 —
       실측 없이 그 둘을 가를 길이 없으므로 **로마자만** 센다(#4 추측 금지).
    🔴🔴 **자리 글자가 이름에 붙는다** — ⚠️ 실측 2026-10-10(재현): 평이
       *"새로 들어온 **LB Min-Seo Park**"* 이라고 적었고 검열이 그 다섯 글자를
       통째로 **없는 이름**이라 했다(묶음에는 `Min-Seo Park` 이 있다). 그 거짓
       위반 하나로 좋은 평이 템플릿으로 떨어졌다.
    🔴 그래서 **묶음의 이름을 품고 있으면 통과**시킨다(지어낸 이름은 어떤 이름도
       품지 않는다).
    """
    got = [x for x in _NAME.findall(str(said or ""))
           if re.match(r"^[A-Z]", x)]
    said_text = str(text or "")
    out: list[str] = []
    for nm in got:
        if any(k and (k in nm or nm in k) for k in known):
            continue
        # 🔴 ① **자리 글자를 떼고** 다시 본다(위 머리말 `CB Waston`)
        bare = strip_pos(nm)
        if bare != nm and any(k and (k in bare or bare in k) for k in known):
            continue
        # 🔴 ② **묶음 원문에 그 낱말들이 있으면** 지어낸 것이 아니다 —
        #    묶음의 한 낱말 이름(`Waston`)이나 성만 쓴 축약(`López` ←
        #    `Alexander López`)이 이 길로 통과한다. ⚠️ `text` 를 안 주면
        #    종전과 **똑같이** 동작한다(옛 호출부를 안 깨뜨린다).
        if said_text:
            words = [w for w in re.split(r"[\s·]+", bare) if w]
            if words and all(w in said_text for w in words):
                continue
        out.append(nm)
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3 마지막 줄 — **코드 템플릿 평**(사실 묶음 상위 근거 셋 + 확률 방향)
# ══════════════════════════════════════════════════════════════════

def template(card: Card, box: Bundle, *, why: str,
             violations: list[str] | None = None,
             dropped: list[str] | None = None) -> SayOut:
    """🔴 §3 — LLM 이 두 번 어긋났을 때의 평. **코드가 쓴다**(모델이 아니다).

    🔴 *"사실 묶음 **상위 근거 셋** + 확률 방향"* — 상위는 **발동 규칙 → 라인업
       변화 → 골 내용** 순이다(확률을 움직인 것이 먼저다).
    """
    from app.core import saybundle
    want = saybundle.direction_of(card)
    pick: list = []
    for which in ("T", "X", "G", "L", "A", "S"):
        for one in box.of(which):
            if one.kind in ("xi", "direction") or one.text in {
                    x.text for x in pick}:
                continue
            pick.append(one)
            if len(pick) >= 3:
                break
        if len(pick) >= 3:
            break
    rows = [KeyPoint(claim=f"코드가 고른 근거 — {one.text[:70]}",
                     mechanism=str(one.text), refs=[one.id])
            for one in pick]
    return SayOut(
        verdict=want, one_line=f"확률 방향은 **{want}** 다(평은 템플릿이다 — {why})",
        key_points=rows,
        flow_first="⬜ 템플릿 — 흐름은 적지 않는다",
        flow_second="⬜ 템플릿 — 흐름은 적지 않는다",
        decisive_moment="⬜ 템플릿 — 승부처는 적지 않는다",
        flip_condition="⬜ 템플릿 — 뒤집히는 조건은 적지 않는다",
        audit="템플릿", violations=list(violations or [f"🔴 {why}"]),
        dropped=list(dropped or []),
        used={one.id: one.text for one in pick})


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §2 — **LLM 1회**(구조화 출력)
# ══════════════════════════════════════════════════════════════════

def _ask(card: Card, box: Bundle, *, state: RunState,
         bad: list[str] | None) -> SayOut | None:
    """🔴 LLM **1회**. ⚠️ 실패하면 `None`(사유는 `state` 에 남는다)."""
    from app.core import llm
    msgs = _prompt(card, box)
    if bad:
        msgs = msgs + [llm.Message(role="user", content=(
            "🔴 아래가 **검열에서 어긋났다** — 그 자리만 고쳐 다시 내라:\n"
            + "\n".join(f"- {x}" for x in bad[:10])))]
    # 🔴 **solar 우선**(지시 2026-10-15) — 차례를 도는 곳은 `llm.ask_first` 하나다
    got, _said_pv = llm.ask_first(
        purpose="say", messages=msgs, out=SayOut, state=state)
    if isinstance(got, SayOut):
        return got
    # 🔴 ⑦ — **왜 실패했는지**를 호출부가 읽는다(잘림이면 축약판으로 간다)
    state.last_llm_reason = str(getattr(got, "reason", "") or "")
    state.note(f"s9say 최종 평 — LLM 실패({getattr(got, 'reason', '?')} · "
               f"{getattr(got, 'detail', '')[:80]})")
    logger.info("[s9say] 🔴 LLM 실패 — %s", getattr(got, "reason", "?"))
    return None


#: 🔴 A — 이름으로 맞출 때의 **최소 글자**(한글·가나·한자는 2, 라틴은 3)
_NAME_MIN_CJK, _NAME_MIN_LATIN = 2, 3
_CJK_RE = __import__("re").compile(r"[가-힣ぁ-んァ-ヴー一-龥]")


def _refs_in(said: str, box: dict) -> list[str]:
    """🔴🔴 **A 안** — 문장 글자에서 **카탈로그에 있는 근거**를 읽는다.

    > 선례: `new_fact_check` 는 *"`fact_refs` 만 보면 모델이 번호를 안 적었을 때
    > 멀쩡한 문장을 위반으로 센다 — 그래서 **글자도 본다**"*.

    두 가지를 본다:
      ① **id 를 글자 그대로** 쓴 것 — `S01-home`·`IR02-home`·`H2H`·`XI:home`·`TOTAL`
      ② `PREFIX:이름` 꼴 id 의 **이름 쪽** — `P:Marcinho` ↔ 글에 `Marcinho`

    🔴 **카탈로그에 있는 것만** 돌려준다 — 없는 id 를 짓지 않는다(#4).
    ⚠️ 짧은 글자가 남의 낱말 안에서 걸리지 않게 **경계**를 본다(라틴 3자·CJK 2자).
    """
    import re as _re
    said = str(said or "")
    if not said.strip():
        return []
    out: list[str] = []
    for fid in sorted(box or {}, key=lambda x: -len(str(x))):
        key = str(fid)
        if not key:
            continue
        # ① id 를 그대로 썼나 — 앞뒤가 글자·숫자·`-`·`:` 가 아니어야 한다
        if _re.search(r"(?<![0-9A-Za-z:\-])" + _re.escape(key)
                      + r"(?![0-9A-Za-z:\-])", said):
            out.append(key)
            continue
        # ② `PREFIX:이름` 의 이름 쪽
        tail = key.split(":", 1)[-1].strip() if ":" in key else ""
        if not tail or tail == key:
            continue
        need = (_NAME_MIN_CJK if _CJK_RE.search(tail) else _NAME_MIN_LATIN)
        if len(tail) < need:
            continue
        if _CJK_RE.search(tail):
            if tail in said:
                out.append(key)
        elif _re.search(r"(?<![0-9A-Za-z])" + _re.escape(tail)
                        + r"(?![0-9A-Za-z])", said):
            out.append(key)
    return list(dict.fromkeys(out))


def _para_of(got, *, card=None):
    """🔴🔴 평의 이유 문단을 **검열이 읽는 꼴**(`ReasonPara`)로.

    🔴 모델이 `reason_lines`(문장 + 근거 id)를 줬으면 그것을 쓴다 — 검열 (i)·(j)
       가 그 꼴을 센다. ⚠️ 글자만 왔으면 **문장으로 쪼개고 근거는 비운다** —
       그러면 (j) 가 *"근거 없는 문장"* 으로 잡는다(없는 근거를 지어내지 않는다).
    """
    from app.core.schema import ReasonLine, ReasonPara
    rows = list(getattr(got, "reason_lines", None) or [])
    if rows:
        return ReasonPara(sentences=rows)
    said = str(getattr(got, "reason", "") or "").strip()
    if not said:
        return ReasonPara(sentences=[])
    import re as _re
    parts = [x.strip() for x in _re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*",
                                          said) if x.strip()]
    # 🔴🔴 **A 안**(사용자 결정 2026-10-11) — 글자에 쓴 근거를 읽어 채운다.
    #    ⚠️ 종전엔 `fact_refs=[]` 로 비웠다 — 그래서 검열 (i) 의 *"고유 사실 종류"*
    #       가 **언제나 0종**이었고 글이 아무리 좋아도 통과할 수 없었다(실측
    #       2026-10-11 가와사키: 552자 문단도 `(i) 0종`으로 떨어졌다).
    box = {}
    if card is not None:
        from app.core import layer1 as _l1
        box = dict(_l1.facts_catalog(card) or {})
    return ReasonPara(sentences=[
        ReasonLine(text=x, fact_refs=_refs_in(x, box)) for x in parts])


#: 🔴 이유 문단 검열의 글자 — 이 머리글만 걸렸으면 **그 문단만** 다시 묻는다
#
#  ⚠️ 실측 2026-10-11(재현 3회차): `(p)`(전략 문장)를 빼 뒀더니 위반이
#     `(o)·(p)·(i)` 로 와서 수선을 **건너뛰고** 전체 재작성으로 갔고, 그 평이
#     통째로 버려졌다. 🔴 `(p)` 도 **이유 문단 검열**이다(§4 — 이유 문단에 전략
#     문장 최소 1개).
REASON_TAGS = ("(i)", "(j)", "(k)", "(l)", "(o)", "(p)", "이유 문단")


def _reason_only(bad: list[str]) -> bool:
    """🔴 위반이 **이유 문단 것뿐인가**. 비었으면 `False`(수선할 것이 없다)."""
    rows = [str(x) for x in (bad or [])]
    if not rows:
        return False
    return all(any(t in one for t in REASON_TAGS) for one in rows)


def _ask_core(card: Card, box: Bundle, *, state: RunState):
    """🔴🔴 **잘렸을 때의 핵심** — 한 줄 + 이유 문단만(칸 둘이라 잘리지 않는다).

    ⚠️ 못 받으면 `None` 이고 호출부가 **축약판**(코드 템플릿)으로 간다 — 그 사실이
       판정 글자에 남는다(`잘림 — 핵심 3줄만` vs `잘림 — 핵심만 다시 받았다`).
    """
    from app.core import llm
    from app.core.schema import SayCore
    msgs = _prompt(card, box) + [llm.Message(role="user", content=(
        "🔴 **앞 요청이 잘렸다.** 이번에는 칸 **둘만** 내라 — `one_line`(한 줄 "
        "요약)과 `reason`(이유 문단). 주장·흐름·승부처는 **쓰지 않는다**."))]
    # 🔴 **solar 우선**(지시 2026-10-15) — 차례를 도는 곳은 `llm.ask_first` 하나다
    got, _said_pv = llm.ask_first(
        purpose="say", messages=msgs, out=SayCore, state=state)
    if isinstance(got, SayCore):
        return got
    state.note(f"s9say 핵심 다시 받기 실패 — {getattr(got, 'reason', '?')}")
    return None


def _ask_reason(card: Card, box: Bundle, *, state: RunState,
                bad: list[str]) -> str:
    """🔴🔴 **이유 문단 하나만** 다시 묻는다(짧은 질문은 잘리지 않는다).

    ⚠️ 돌려주는 것은 **글자**다 — 못 받으면 빈 글자이고 호출부가 전체 재작성으로
       간다(그 사실이 상태 기록에 남는다 · #3).
    """
    from app.core import llm
    from app.core.schema import ReasonOnly
    msgs = _prompt(card, box) + [llm.Message(role="user", content=(
        "🔴 **이 번만은 `reason`(이유 문단) 하나만** 내라 — 다른 칸은 쓰지 "
        "않는다. 아래가 검열에서 어긋난 자리다:\n"
        + "\n".join(f"- {x}" for x in (bad or [])[:6])))]
    # 🔴 **solar 우선**(지시 2026-10-15) — 차례를 도는 곳은 `llm.ask_first` 하나다
    got, _said_pv = llm.ask_first(
        purpose="say", messages=msgs, out=ReasonOnly, state=state)
    if isinstance(got, ReasonOnly):
        return str(got.reason or "").strip()
    state.note(f"s9say 이유 문단 수선 실패 — {getattr(got, 'reason', '?')}")
    return ""


def _prompt(card: Card, box: Bundle) -> list:
    """🔴🔴 §2 — 지시서의 글을 프롬프트에 **그대로** 둔다(사본 금지)."""
    from app.core import llm, saybundle
    m = card.match
    said = "\n".join(
        f"- `{one.id}` [{one.kind}] {one.text}"
        + (f" · ⚠️ {APPROX} 지표다" if one.approx else "")
        for one in box.items.values())
    empty = "\n".join(f"- {x}" for x in box.empty) or "- (없음)"
    want = saybundle.direction_of(card)
    # 🔴 **새 사실 id** — `new_fact_check` 가 보는 그 목록이다(사본 금지)
    from app.core import render as _render
    news = [str(v.id) for v in (_render.new_facts(card) or [])]
    # 🔴 문장 수·종류 수는 **검열의 그 수**다(사본 금지 · #1)
    from app.core.stages import s9_audit as _au
    reason_rule = (
        f"🔴🔴 **`reason`(이유 문단)을 반드시 쓴다** — 문장 "
        f"**{_au.MIN_SENT}~{_au.MAX_SENT}개**를 한 문단으로. 그 문단은 *왜 이 "
        f"방향인가*를 **이 경기 고유 사실로만** 말하고, 서로 **종류가 다른 고유 "
        f"사실 {_au.NEED_KINDS}가지 이상**을 담는다(일반론·단정어 금지 · 문장마다 "
        f"고유 사실이 하나 이상).\n"
        f"🔴🔴 **`reason_lines` 도 같은 문단을 문장별로** 낸다 — 각 줄은 "
        f"`{{\"text\": 문장, \"fact_refs\": [위 목록의 id …]}}` 이고 **근거 id 를 "
        f"문장마다 하나 이상** 적는다. ⚠️ 검열은 이 꼴을 센다 — 비우면 평이 "
        f"버려진다. `reason` 은 그 문장들을 한 글자로 이은 것이다.\n"
        + (f"🔴🔴 **새 사실 {news} 를 이유 문단에 쓴다** — 쓰지 않으면 검열이 "
           f"평을 버린다(§3-5 새 뉴스는 판단에 반드시 들어간다).\n"
           if news else "")
        + "🔴 `ops_home`·`ops_away` — 두 팀이 각각 **무엇을 하려 하는가**를 한 "
          "줄씩(확정 XI·자리 변화로).\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 ④ **전술 줄에도 근거 id**(사용자 지시 2026-10-11 ④)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 근거 풀에 MatchupReport id(축 우위·발동 규칙·꺼진 무기·시간대 득실)를
        #  > 포함한다 — **기사가 0이어도 쓸 수 있어야 한다.**
        #  ⚠️ 실사고 2026-10-11(광주–울산): 전술 다섯 줄이 **근거 [] 로** 나갔다.
        + "🔴🔴 **`tactic_refs` 를 채운다** — 칸 이름(`운영:home`·`운영:away`·"
          "`흐름:전반`·`흐름:후반`·`승부처`)마다 위 목록의 id 를 **하나 이상**. "
          "기사가 없어도 **상성 id** 로 쓸 수 있다 — 축 우위·발동 규칙(`T*`)·"
          "꺼진 무기(`W*`)·시간대 득실(`G*` 의 `시간대`)·상성 종합(`M*`).\n")
    rule = (
        f"🔴 **확률 방향은 코드가 정했다 — `{want}`**. `verdict` 는 그 글자와 "
        "**같아야** 한다. 반반이면 한쪽 승리를 단정하지 않는다.\n"
        f"🔴 `key_points` 는 **{MIN_POINTS}~{MAX_POINTS}개**이고, 각각 "
        f"`refs` 에 **위 목록의 id 를 {MIN_REFS}개 이상** 적는다.\n"
        "🔴 **위에 없는 선수·숫자·사건을 쓰지 않는다** — 검열이 잡아 버린다.\n"
        f"🔴 측면(왼쪽·오른쪽) 주장은 `X*`·`F*` 근거가 있어야 하고, 그 근거가 "
        f"`{APPROX}` 지표면 글에도 **`{APPROX}`** 라고 쓴다.\n"
        "🔴 골 경로(필드골·세트피스·코너·프리킥·역습·PK·자책골·헤더) 를 **주장에든 "
        "메커니즘에든 한 글자라도 적으면** 그 주장의 `refs` 에 `G*` 를 **반드시** "
        "넣는다. 측면(왼쪽·오른쪽·측면)을 적으면 같은 식으로 `X*` 또는 `F*` 를 "
        "넣는다 — 둘 다 적었으면 **둘 다** 넣는다.\n"
        "🔴 **자책골·PK 로 만든 득점을 '득점력'의 근거로 쓰지 않는다.**\n"
        "🔴 `기세`·`정신력` 같은 말은 **쓰지 않는다**(사실 id 가 없다).\n"
        "🔴 **팀·선수 이름은 위에 적힌 글자 그대로** 쓴다 — 한국어 음역을 "
        "지어내지 않는다(`P0` 항목이 쓸 수 있는 표기를 든다).\n"
        "🔴 `audit`·`violations`·`used` 칸은 **비워 둔다**(코드가 채운다).\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **단계 5**(순서 재편 지시서 2026-10-10 다섯째)
        # ══════════════════════════════════════════════════════════════
        "🔴🔴 **지지된 가설(`H*`)과 그 근거만** 주장으로 쓴다. 반박된 가설(`R*`)은 "
        "`flip_condition`(뒤집히는 조건)에만 쓸 수 있다. 판단 불가 가설은 "
        "**묶음에 없다**(그러니 쓸 수 없다).\n"
        "🔴 `H0`(기준 낡음 의심)이 있으면 **`one_line` 첫머리에** 그 사실을 적는다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **S7**(상성 엔진 지시서 2026-10-10 여섯째)
        # ══════════════════════════════════════════════════════════════
        "🔴🔴 **첫 줄(`one_line`)에 상성 판정(`M0`)과 검증 요약(`M00`)을** 함께 "
        "적는다 — *우위 팀·강도*와 *같은 방향 n · 반대 n*.\n"
        "🔴🔴 **`B*`(상성 사각)이 있으면 주장 중 한 줄을 그 얘기로** 쓴다 — "
        "그 정보는 확률에 **안 들어갔다**(상성 밖이다).\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **이유 문단(`reason`)을 요구한다** — 사용자 지시 2026-10-11
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고 2026-10-11(LAFC): 검열은 *"(o) 새 사실이 있는데 이유 문단이
        #     하나도 안 썼다 · (i) 이유 문단이 없다"* 로 두 번 걸렸는데 **프롬프트는
        #     그 칸을 한 번도 요구하지 않았다**. 모델은 요구받지 않은 칸을 비워
        #     뒀고(그 뒤 재작성이 `llm_truncated` 로 끊겨) 템플릿으로 떨어졌다.
        #  🔴 검열이 요구하는 것을 **프롬프트도 요구한다** — 새 사실 목록은
        #     `render.new_facts`(검열이 보는 그 함수)에서 든다(사본 금지).
        + reason_rule
        + "⚠️ 아래 **`없음` 칸은 말하지 않는다**:\n" + empty)
    return [
        llm.Message(role="system", content=(
            "너는 축구 전술 분석가다. 주어진 사실 묶음만 쓰고, 없는 것을 "
            "지어내지 않는다. 측면·자리·골 경로를 구체적으로 말한다. "
            "배당·기대값·금액은 말하지 않는다. 확률을 바꾸지 않는다.\n"
            # 🔴🔴 **이유 문단은 여기서도 요구한다**(2026-10-11) — ⚠️ 긴 규칙
            #    끝에만 적었더니 모델이 그 칸을 **비워 보냈다**(실측 3회차).
            "🔴 가장 중요한 칸은 `reason`(이유 문단)이다 — **절대 비우지 "
            "않는다.** 그 문단이 비면 평 전체가 버려진다.")),
        llm.Message(role="user", content=(
            f"경기: {m.home_name}(홈) vs {m.away_name}(원정) · {m.competition}\n\n"
            "🔴 **사실 묶음**(이것이 입력의 전부다):\n"
            f"{said}\n\n{rule}\n\n"
            "🔴 쓸 글의 뼈대: *\"누가 빠지고 누가 들어와서 → 어느 자리·측면이 "
            "강해지고 약해졌고 → 그래서 골이 어디서 나고 어디서 막히고 → "
            "그래서 어느 팀이 이긴다\"*.")),
    ]
