"""🔴🔴 **⑯ 종합 평** — 사용자 지시 2026-10-15.

> **16단계가 마지막이다** · llm **solar** 가 종합 평을 낸다 · deepseek…
> **확률 먼저** · 그리고 **변수가 이래케 저렇게 되서 이렇게 나온다** ·
> **코드 만으로** · solar **지어냈는지 안지어냈는지 결론내다**

## 🔴🔴 공급자가 자리마다 다르다 — 그 사실을 적어 둔다
```
deepseek   ①~⑮  질의 쓰기 · 사실 추출 · 리그 정보 분석
solar      ⑯     **종합 평 한 편**        ← 이 파일
```
⚠️ 작성자와 검열자를 같은 모델로 두지 않는 그 규율(옛 `s9_audit` §4-2)과 같은
   뜻이다 — 앞 단계를 쓴 모델이 제 글을 평하지 않는다.

## 🔴🔴 **입력은 코드만으로 만든다**
사용자 지시의 *"코드 만으로"* 가 이것이다 — LLM 에 넘기는 묶음에 **모델이 만든
글자가 하나도 없다**:
```
① 확률 먼저        prob.home/draw/away · lam · over · 스코어 상위
② 변수 사슬        변수 → 자리 → 축 값 → 축 종합 → β → λ 이동 → λ 보정
③ 기여            prob.share(리그 평균 대비 축별 %p) · share_refs
```
🔴 ② 가 *"변수가 이래케 저렇게 되서 이렇게 나온다"* 다. 그 글을 **코드가** 짠다
   (`chain_of`) — 모델은 그것을 **읽고 평만** 쓴다.

## 🔴🔴 **지어냈는지 코드가 결론 낸다**
`judge()` 가 **넷**을 센다. 묶음에 없는 것이 글에 있으면 **지어낸 것**이다:
```
(가) 숫자    글의 수가 묶음의 수와 **맞나**(±5% 허용 · 분·년·세는 뺀다)
(나) 스코어  `4-3` 꼴은 묶음 글에 **그 글자**가 있어야 한다
(다) 이름    사람·팀 이름이 묶음에 있나
(라) 번호    `IR14`·`T3`·`R1`·`axis0` 같은 **id** 가 묶음에 있나
```
⚠️ (나)가 중요하다 — 이 단계를 전에 지운 까닭이 *"근거에 없는 4-3 을 적었다"*
   였고, 수치 검사(가)는 `4`·`3` 낱개로 쪼개져 **못 잡았다**(실측 2026-10-14).
🔴 결론은 `지어냈다` · `안 지어냈다` · `못 쟀다` 셋이다 — 애매하게 두지 않는다.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.core.schema import MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **입구가 둘이다** — 계약 §5 가 요구하는 선언(2026-10-10 순서 재편)
# ══════════════════════════════════════════════════════════════════
#
#  이 파일은 `run` 하나가 아니라 **두 일**을 맡는다:
#    `ask`   — solar 가 종합 평을 쓴다
#    `judge` — 🔴 **코드가** 지어냈는지 결론 낸다(사용자 지시 2026-10-15)
#  🔴 그 둘을 한 함수로 묶지 않는다 — 작성과 검열이 **같은 자리**가 되면
#     검열이 작성을 통과시키는 쪽으로 움직인다(옛 `s9_audit` §4-2 의 규율).
STAGES = ("ask", "judge")

#: 🔴 종합 평 — 문장 **3~5개**
MIN_SENT, MAX_SENT = 3, 5
#: 🔴 한 문장 글자 상한
SENT_MAX = 220
#: 🔴 숫자 대조 허용 오차(비율) — 반올림을 받아 준다
NUM_TOL = 0.05

#: 🔴 (가) 숫자 — `_NUM` 뒤에 이 글자가 오면 **센 수가 아니다**(분·년·나이)
NUM_SKIP = ("분", "년", "세", "월", "일", "호")
_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%?")
#: 🔴 (나) 스코어 꼴 — `4-3` · `2 : 1`
_SCORE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:]\s*(\d{1,2})(?!\d)")
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(라) 규칙·변수 번호** — 사용자 지시 2026-10-15 (가)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-15(코모): solar 가 *"**[IR14]**로 원정 λ가 0.95배로
#     깎여"* 라고 썼다. 🔴 묶음에 `IR14` 글자가 **0건**이었다(그 변수는 자리가
#     `['V2','hypo']` 라 묶음에 안 들어갔고 λ 보정도 안 걸렸다). 즉 **없는 규칙
#     효과를 지어냈다** — 그런데 검열 (가)(나)(다)는 숫자·스코어·이름만 보므로
#     **통과시켰다**.
#  🔴 그래서 **번호 꼴**을 따로 센다: `IR13`·`IR14`·`T3`·`R1`·`S01-home`·
#     `axis0` 처럼 우리가 id 로 쓰는 글자가 글에 있으면 묶음에 **그 글자**가
#     있어야 한다.
#  ⚠️ 대괄호 안이든 아니든 센다(모델이 `[IR14]` · `IR14` 둘 다 쓴다).
_RULEID = re.compile(r"\b(?:IR\d{1,2}|T\d{1,2}|R\d{1,2}|S\d{2}(?:-\w+)?"
                     r"|axis[0-3]|IR\d{1,2}-\w+)\b")
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(다) 이름은 `s9_say._names_in` 이 센다** — 사본 금지
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 내가 처음엔 정규식을 다시 짰고 **거짓 위반**이 났다: `홈이`·`가장` 같은
#     흔한 한글 낱말을 사람 이름으로 잡았다(실측 2026-10-15).
#  🔴 그 함수는 그 함정을 **이미 둘** 막아 뒀다:
#     ① *"한글 토막은 보통 명사와 섞여 거짓 위반을 만든다 → **로마자만** 센다"*
#     ② 포지션 글자가 붙은 이름(`LB Min-Seo Park`)을 **묶음 이름을 품으면
#        통과**시킨다(실측 2026-10-10 그 거짓 위반으로 좋은 평이 버려졌다).
#  🔴 그래서 여기서 다시 짜지 않고 **그 함수를 부른다**.


class Verdict(BaseModel):
    """🔴 solar 가 내는 것 — **문장과 근거 이름뿐**이다.

    ⚠️ 확률·등급 칸이 **없다** — 그 수는 코드가 정했고 모델이 바꿀 길이 없다.
    """

    sentences: list[str] = Field(default_factory=list)
    #: 🔴 각 문장이 든 근거 — 묶음의 **줄 머리말**(`확률`·`축1`·`IR13-away` …)
    refs: list[str] = Field(default_factory=list)


def chain_of(ref: MatchRef, prob, mr, varset) -> list[str]:
    """🔴🔴 *"변수가 이래케 저렇게 되서 이렇게 나온다"* — **코드가 짠다**.

    돌려주는 것은 묶음 줄 목록이다(모델 입력의 전부). 🔴 모델이 만든 글자가
    **하나도 없다**(사용자 지시 2026-10-15: *"코드 만으로"*).
    ⚠️ 못 센 칸은 ⬜ 로 남긴다(#3 조용한 0 금지).
    """
    rows: list[str] = []
    # ── ① 확률 먼저(지시: *"확률 먼저"*)
    rows.append(f"확률 — 홈 {float(prob.home):.1%} · 무 {float(prob.draw):.1%} "
                f"· 원정 {float(prob.away):.1%}")
    lam = dict(getattr(prob, "lam", None) or {})
    if lam:
        rows.append(f"λ(기대 득점) — 홈 {float(lam.get('home') or 0):.3f} · "
                    f"원정 {float(lam.get('away') or 0):.3f} · 합 "
                    f"{float(lam.get('home') or 0) + float(lam.get('away') or 0):.3f}")
    over = dict(getattr(prob, "over", None) or {})
    if over:
        rows.append("오버 — " + " · ".join(
            f"{k} {float(v):.1%}" for k, v in list(over.items())[:5]))
    top = sorted(dict(getattr(prob, "scores", None) or {}).items(),
                 key=lambda kv: -float(kv[1]))[:5]
    if top:
        rows.append("스코어 상위 — " + " · ".join(
            f"{k if isinstance(k, str) else f'{k[0]}-{k[1]}'} {float(v):.1%}"
            for k, v in top))
    # ── ② 변수 → 자리
    got_rows = list(getattr(varset, "rows", None) or [])
    if got_rows:
        rows.append(f"변수 {len(got_rows)}개 — 확률에 닿는 자리(축·λ상수)에 든 것만:")
        AX = {"axis0", "axis1", "axis2", "axis3", "lambda_const"}
        for one in got_rows:
            places = [str(x) for x in (getattr(one, "places", None) or [])]
            if not (set(places) & AX):
                continue
            rows.append(f"  변수 `{one.id}` [{one.type}] 자리 {places} — "
                        f"{str(getattr(one, 'claim', '') or '')[:120]}")
    else:
        rows.append("변수 — ⬜ 배치표가 비었다")
    # ── ③ 축 값 → 종합
    if mr is not None:
        for key in ("axis0", "axis1", "axis2", "axis3"):
            ax = mr.axis(key) if hasattr(mr, "axis") else None
            if ax is None:
                continue
            h, a = getattr(ax, "home", None), getattr(ax, "away", None)
            if h is None or a is None:
                rows.append(f"  {key} — ⬜ 못 셌다 · "
                            f"{str(getattr(ax, 'why', '') or '')[:90]}")
                continue
            rows.append(f"  {key} — 홈 {float(h):.4f} · 원정 {float(a):.4f} · "
                        f"차 {float(h) - float(a):+.4f} · 근거 변수 "
                        f"{list(getattr(ax, 'refs', None) or []) or '없다'}")
        said_t = getattr(mr, "total", None)
        if said_t is not None:
            rows.append(f"  축 종합 — {float(said_t):+.4f}")
    # ── ④ λ 유도·보정(코드가 적은 글자 그대로)
    said_why = str(getattr(prob, "why", "") or "")
    if said_why:
        rows.append("λ 유도(코드 글자) — " + said_why[:600])
    # ── ⑤ 기여
    share = dict(getattr(prob, "share", None) or {})
    if share:
        rows.append("기여(리그 평균 대비) — " + " · ".join(
            f"{k} {float(v) * 100:+.1f}%p" for k, v in share.items()))
    return rows


def ask(ref: MatchRef, prob, mr, varset, *, state: RunState,
        provider: str = "solar", box: list[str] | None = None
        ) -> tuple[Verdict | None, list[str], str]:
    """🔴🔴 **solar 가 종합 평을 쓴다**. `(평, 묶음, 사유)`.

    🔴 공급자는 **solar** 가 기본이다(지시 2026-10-15) — 앞 단계의 deepseek 와
       다르다. ⚠️ `provider` 로 바꿔 **두 모델을 같은 묶음으로** 비교할 수 있다
       (사용자 지시 2026-10-15: *"solar 서술형 카드와 deepseek 서술형 카드
       동시에 보여주라"*).
    🔴 `box` 를 주면 **그 묶음을 그대로** 쓴다 — 두 모델이 **같은 입력**을 받아야
       비교가 뜻을 갖는다(다시 만들면 미세하게 달라질 수 있다).
    ⚠️ 실패하면 `(None, 묶음, 사유)` 다 — 코드가 만든 묶음은 **그대로 남는다**.
    """
    from app.core import llm
    box = list(box) if box else chain_of(ref, prob, mr, varset)
    said = "\n".join(box)
    names = [str(getattr(ref, f"{s}_name", "") or "")
             or str(getattr(ref, s, "") or "") for s in ("home", "away")]
    msgs = [
        llm.Message(role="system", content=(
            "너는 축구 분석 평을 쓰는 사람이다. 🔴 **아래 묶음에 있는 것만** "
            "쓴다 — 묶음에 없는 숫자·스코어·선수 이름을 **만들지 마라**. "
            "확률은 이미 정해졌다(네가 바꿀 수 없다). 그 수가 **왜 그렇게 "
            "나왔는지**를 변수와 축으로 설명한다.")),
        llm.Message(role="user", content=(
            f"경기: {names[0]} (홈) vs {names[1]} (원정)\n"
            f"대회: {getattr(ref, 'competition', '')}\n\n"
            f"=== 묶음(코드가 만든 것 · 이것이 전부다) ===\n{said}\n\n"
            f"🔴 `sentences` — **{MIN_SENT}~{MAX_SENT}개** 문장. 각 "
            f"{SENT_MAX}자 안.\n"
            "   ① 확률이 어떻게 나왔나 ② 어느 변수·축이 그것을 밀었나 "
            "③ 그래서 무엇을 조심하나\n"
            "🔴 `refs` — 문장마다 근거 **한 줄의 머리말**(예 `확률`·`axis1`·"
            "`변수 IR13-away`). 문장 수와 같게.\n"
            "⚠️ 묶음에 없는 수를 쓰면 **버려진다** — 코드가 대조한다.")),
    ]
    got = llm.ask(provider=provider, purpose="commentary", messages=msgs,
                  out=Verdict, state=state)
    if not isinstance(got, Verdict):
        why = f"🔴 {provider} 실패({getattr(got, 'reason', '?')}) — 평이 없다"
        state.note(f"s6v 종합 평 — {why}")
        return None, box, why
    n = len(list(got.sentences or []))
    state.note(f"s6v 종합 평 — {provider} 문장 {n}개")
    return got, box, f"{provider} 문장 {n}개"


def _nums(said: str) -> list[float]:
    """🔴 (가) — 글 속 수. 분·년·나이는 **안 센다**."""
    out: list[float] = []
    for m in _NUM.finditer(str(said or "")):
        tail = said[m.end():m.end() + 1]
        if tail in NUM_SKIP:
            continue
        try:
            out.append(float(m.group(1)))
        except ValueError:
            continue
    return out


def _scores(said: str) -> list[str]:
    """🔴 (나) — 글 속 **스코어 꼴**."""
    return [f"{m.group(1)}-{m.group(2)}"
            for m in _SCORE.finditer(str(said or ""))]


def _ruleids(said: str) -> list[str]:
    """🔴 (라) — 글 속 **규칙·변수 번호**(`IR14`·`T3`·`R1`·`axis0` …)."""
    return list(dict.fromkeys(_RULEID.findall(str(said or ""))))


def judge(got: Verdict | None, box: list[str]) -> tuple[str, list[str]]:
    """🔴🔴 **지어냈나** — `(결론, 위반 목록)`. 사용자 지시 2026-10-15.

    결론은 `지어냈다` · `안 지어냈다` · `못 쟀다` 셋뿐이다.
    🔴 묶음(`box`)이 **참이고** 글이 거기서만 나와야 한다.
    """
    if got is None or not list(got.sentences or []):
        return "못 쟀다", ["⬜ 평이 없다 — solar 가 문장을 안 냈다"]
    said_box = "\n".join(box)
    ok_nums = _nums(said_box)
    ok_scores = set(_scores(said_box))
    #: 🔴 (라) 묶음에 **글자로** 있는 규칙·변수 번호
    ok_ids = set(_ruleids(said_box))
    # 🔴 이름 대조는 `s9_say` 의 그 함수 하나다(사본 금지 · 위 머리말)
    from app.core.stages import s9_say as _say
    ok_names = _say._names_of_text(said_box) if hasattr(
        _say, "_names_of_text") else set(_say._NAME.findall(said_box))
    bad: list[str] = []
    rows = [str(x) for x in (got.sentences or [])]
    if not (MIN_SENT <= len(rows) <= MAX_SENT):
        bad.append(f"🔴 문장 {len(rows)}개 — {MIN_SENT}~{MAX_SENT}개여야 한다")
    for one in rows:
        if len(one) > SENT_MAX:
            bad.append(f"🔴 문장이 {len(one)}자다(>{SENT_MAX}) — `{one[:40]}…`")
        # (가) 숫자
        for v in _nums(one):
            if not any(abs(v - x) <= max(0.051, abs(x) * NUM_TOL)
                       for x in ok_nums):
                bad.append(f"🔴 (가) **없는 수**({v:g}) — `{one[:50]}`")
                break
        # (나) 스코어 — 꼴 그대로 대조한다
        for sc in _scores(one):
            if sc not in ok_scores:
                bad.append(f"🔴 (나) **없는 스코어**({sc}) — `{one[:50]}`")
                break
        # (다) 이름
        for nm in _say._names_in(one, ok_names):
            bad.append(f"🔴 (다) **없는 이름**({nm}) — `{one[:50]}`")
            break
        # 🔴🔴 (라) **규칙·변수 번호** — 묶음에 그 글자가 있어야 한다
        for rid in _ruleids(one):
            if rid not in ok_ids:
                bad.append(f"🔴 (라) **없는 규칙·변수 번호**({rid}) — 묶음에 그 "
                           f"글자가 없다 · `{one[:50]}`")
                break
    # 🔴 근거 — 문장 수와 같아야 한다
    refs = [str(x) for x in (got.refs or [])]
    if len(refs) < len(rows):
        bad.append(f"🔴 근거 {len(refs)}개 < 문장 {len(rows)}개")
    return ("지어냈다" if bad else "안 지어냈다"), bad


def said_of(got: Verdict | None, box: list[str], *,
            provider: str = "solar") -> str:
    """🔴 카드·보고에 찍는 글 — 평 + **지어냈나 결론**."""
    verdict, bad = judge(got, box)
    head = f"🧭 **종합 평**({provider}) — 지어냄 판정 **{verdict}**"
    if got is None:
        return head + "\n" + "\n".join(f"- {x}" for x in bad)
    rows = [head]
    refs = [str(x) for x in (got.refs or [])]
    for i, one in enumerate(list(got.sentences or [])):
        said_r = refs[i] if i < len(refs) else "⬜ 근거 없음"
        rows.append(f"- {one}  · 근거 `{said_r}`")
    for x in bad:
        rows.append(f"  {x}")
    return "\n".join(rows)
