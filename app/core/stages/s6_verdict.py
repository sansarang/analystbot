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
#  ⚠️ 실측 2026-10-15: 위반 54건 중 **27건이 길이 초과**였다(227~279자) —
#     220 자는 두 모델이 실제로 쓰는 길이와 안 맞았다.
#  🔴 **300 자로 올린다**(사용자 결정 2026-10-15: *"상한을 그에 맞게 올려라"*).
SENT_MAX = 300

#: 🔴 최근 폼 글자 — `W`·`D`·`L` 만 든 토막은 **사람 이름이 아니다**
_FORM_WORD = re.compile(r"[WDL]{2,8}")
#: 🔴 대회 이름에 흔한 낱말 — 사람 이름으로 세지 않는다(위 (다) 머리말)
_COMP_WORDS = ("champions league afc uefa cup liga league elite two "
               "challenge 챔피언스리그 리그 컵")
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
#  ⚠️ 실측 2026-10-15(오늘 실행 전부 · 위반 54건을 깠다): (라) 19건이 **전부
#     거짓 양성**이었다 — `S01-home은`·`S01-home의`·`S01-away가`·`S01-home이`·
#     `S01-home과`(17건)는 **조사가 붙은 것**이고 `S01`(2건)은 **집안 접두**다.
#     🔴 까닭은 꼬리를 `\w+` 로 받아 **한글 조사를 먹었기** 때문이다
#     (파이썬 `\w` 는 한글을 포함한다).
#  🔴 그래서 꼬리는 **로마자·숫자만** 받는다.
_RULEID = re.compile(r"\b(?:IR\d{1,2}(?:-[A-Za-z0-9]+)?|T\d{1,2}|R\d{1,2}"
                     r"|S\d{2}(?:-[A-Za-z0-9]+)?|SL\d{1,2}|TURN(?:-[A-Za-z]+)?"
                     r"|axis[0-3])\b")
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **각자 예측한다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 확률을 보여주고 **변수 경기 관련으로 예측을 각각** 하라고 해라 · 단
    #  > 이제까지 **모은 자료만** 가지고 **거짓없이** · 평을 쓸 때는 확률 경기
    #  > 점수 예측 점수 **외에는 서술형**으로 분석글을 쓰라고 해라
    #
    #  🔴 예측은 **글자 둘**이다 — 승패 한 쪽과 스코어 하나. 확률·등급 칸은
    #     여기 없다(그 수는 코드가 정했다 · 절대규칙 5).
    #: 🔴 승패 예측 — `home`·`draw`·`away` 중 하나
    pick: str = ""
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **점수까지 예상한다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 기대득점은 삭제했어도 **마지막에는 솔라와 딥시크가 점수까지 예상**하게
    #  > 해야 한다
    #
    #  🔴 격자(λ·스코어)가 없으니 **묶음에 없어도 된다** — 이것은 *사실*이 아니라
    #     **그 모델의 예측**이다. 그래서 (나) 스코어 검열에서 **이 점수는 뺀다**.
    #  ⚠️ 그래도 **빈 칸은 위반**이다 — 예측을 안 낸 것이다.
    #: 🔴 점수 예측 — `2-1` 꼴(모델 판단 · 격자 없음)
    score: str = ""


def chain_of(ref: MatchRef, prob, mr, varset, *,
             docs: list | None = None, plan=None, strat=()) -> list[str]:
    """🔴🔴 *"변수가 이래케 저렇게 되서 이렇게 나온다"* — **코드가 짠다**.

    돌려주는 것은 묶음 줄 목록이다(모델 입력의 전부). 🔴 모델이 만든 글자가
    **하나도 없다**(사용자 지시 2026-10-15: *"코드 만으로"*).
    ⚠️ 못 센 칸은 ⬜ 로 남긴다(#3 조용한 0 금지).
    """
    rows: list[str] = []
    # ── ① 확률 먼저(지시: *"확률 먼저"*)
    rows.append(f"확률 — 홈 {float(prob.home):.1%} · 무 {float(prob.draw):.1%} "
                f"· 원정 {float(prob.away):.1%}")
    # 🔴🔴 **λ·오버·스코어는 묶음에서 뺐다** — 사용자 결정 2026-10-15(3번).
    #    ⚠️ 그 수가 없으니 모델은 **점수를 고를 수 없다** — 그래서 `score` 칸도
    #       뺐다(없는 격자에서 점수를 지어내면 거짓이다).
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **딥서치가 건진 것을 평이 쓰게 한다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 딥서치, llm 서치 자료들을 파악해서 ⑯ 평이 **그 자료를 쓰게** 하려면
    #
    #  ⚠️ 그때까지 묶음에는 **확률·축·확률에 닿는 변수**뿐이었다. 기사 변수는
    #     확률에서 안 세니(개수 금지) **묶음에도 없었고**, 문서 자체(제목·원천)는
    #     애초에 없었다. 🔴 그래서 검열이 *"묶음에 없는 글자"* 로 잡아 모델은
    #     기사 내용을 **쓰고 싶어도 못 썼다**.
    #  🔴 여기 두 칸을 더한다 — 확률엔 안 닿지만 **평에는 쓰라고** 주는 것이다.
    #  ⚠️ 비면 **⬜ 로 적는다**(#3) — 그러면 평이 *"기사에서 나온 것이 없다"* 고
    #     쓸 수 있다(그게 정직한 상태다).
    said_doc = [one for one in got_rows
                if bool(getattr(one, "from_doc", False))]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **포메이션·전략 칸** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > **포메이션 전략 등을 동반하여** 예측글을 작성하라
    #
    #  ⚠️ 실측 2026-10-15(Atalanta vs Pafos): 묶음에는 확률·변수·축·기사뿐이고
    #     ⑤-b(포메이션 판정)·⑤-b2(전략 전문가) 산출이 **한 줄도 없었다** —
    #     그래서 평이 전략을 말할 재료가 아예 없었다.
    #  🔴 그 둘을 묶음에 싣는다. ⚠️ 비면 **⬜ 로 남긴다**(#3) — 다만 평은 그
    #     없음을 **글로 쓰지 않는다**(아래 프롬프트 규칙).
    said_shape = str(getattr(plan, "shape", "") or "")
    said_lines = list(getattr(plan, "lines", None) or [])
    if said_shape or said_lines:
        rows.append(f"포메이션·전략 — 양상 {said_shape or '⬜'}"
                    + (f" · 판정 {str(getattr(plan, 'audit', '') or '')}"
                       if getattr(plan, "audit", "") else ""))
        for one in said_lines:
            side = str(getattr(one, "side", "") or "")
            rows.append(f"  {side} 전략 `{getattr(one, 'strategy', '') or '?'}`"
                        f" — {str(getattr(one, 'why', '') or '')[:200]}")
    else:
        rows.append("포메이션·전략 — ⬜ **없다**(확정 XI 전이거나 포메이션 미확보)")
    said_sl = list(strat or [])
    if said_sl:
        rows.append(f"전략 변수 {len(said_sl)}개(부등호는 **홈 기준**):")
        for one in said_sl[:8]:
            rows.append(f"  전략 `{getattr(one, 'id', '?')}` "
                        f"[{getattr(one, 'type', '') or ''}] — "
                        f"{str(getattr(one, 'claim', '') or '')[:220]}")
    if said_doc:
        rows.append(f"기사에서 나온 사실 {len(said_doc)}개 "
                    "— **확률에는 안 셌다**(개수로 세지 않는다 · 내용으로 읽는다):")
        for one in said_doc[:10]:
            rows.append(f"  기사 `{one.id}` [{one.type}] — "
                        f"{str(getattr(one, 'claim', '') or '')[:200]}")
    else:
        rows.append("기사에서 나온 사실 — ⬜ **없다**(딥서치·표적 검색이 그 경기 "
                    "기사를 못 건졌다)")
    said_src = []
    for one in list(docs or [])[:8]:
        title = str(getattr(one, "title", "") or "")[:70]
        url = str(getattr(one, "url", "") or "")
        host = url.split("/")[2] if "//" in url else url[:40]
        when = str(getattr(one, "published_at", "") or "")[:16]
        # ⚠️ 실측 2026-10-15: `doc_id` 로 읽어 **`?` 로 찍혔다** — `Doc` 의 칸은
        #    **`id`** 다(만드는 함수 인자 이름이 `doc_id` 라 헷갈린다).
        said_src.append(f"  문서 `{getattr(one, 'id', None) or '?'}` {title} · "
                        f"{host}" + (f" · {when}" if when else " · 발행 ⬜"))
    if said_src:
        rows.append(f"문서 출처 {len(said_src)}건(딥서치·표적 검색이 연 것):")
        rows += said_src
    else:
        rows.append("문서 출처 — ⬜ **없다**")
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
        docs: list | None = None,
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
    box = list(box) if box else chain_of(ref, prob, mr, varset, docs=docs)
    said = "\n".join(box)
    names = [str(getattr(ref, f"{s}_name", "") or "")
             or str(getattr(ref, s, "") or "") for s in ("home", "away")]
    msgs = [
        llm.Message(role="system", content=(
            "너는 축구 분석 평을 쓰는 사람이다. 🔴 **아래 묶음에 있는 것만** "
            "쓴다 — 묶음에 없는 숫자·스코어·선수 이름을 **만들지 마라**.\n"
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **확률로 예측하지 않는다** — 사용자 지시 2026-10-15
            # ══════════════════════════════════════════════════════
            #
            #  > llm 평은 **확률에 근거하여 예측하지 말고 변수를 기반으로**
            #  > 예측하라 … 확률은 변수를 기반하지만 … **포메이션 전략 등을
            #  > 동반하여** 예측글을 작성하라
            #
            #  ⚠️ 실측 2026-10-15: 확률이 33.3/33.3/33.3 로 균등하게 나온
            #     경기에서 두 평이 *"균등하니까 무"*·*"균등하지만 홈"* 처럼
            #     **그 수를 출발점**으로 삼았다. 🔴 확률은 변수에서 나온
            #     **결과**다 — 그것을 다시 예측의 근거로 쓰면 같은 재료를 두
            #     번 세는 것이고, 변수가 말하는 것을 못 본다.
            "🔴🔴 **예측은 변수로 한다 — 확률 수로 하지 마라.** 확률은 변수에서 "
            "나온 **결과**이므로, 그 퍼센트를 근거로 *\"확률이 이러니 이쪽\"* "
            "이라고 쓰지 않는다. 네가 볼 것은 **폼(최근 5경기 득점·실점) · "
            "결장 · 포메이션 · 전략 갈래 · 일정·이동 · 순위 동기**다.\n"
            "🔴 그리고 **포메이션과 전략을 반드시 동반**해 쓴다 — 묶음의 "
            "`포메이션·전략`·`전략 변수` 칸을 읽고 두 팀이 어떤 모양으로 "
            "맞붙는지, 그것이 득점·실점에 어떻게 작용하는지 적는다.")),
        llm.Message(role="user", content=(
            f"경기: {names[0]} (홈) vs {names[1]} (원정)\n"
            f"대회: {getattr(ref, 'competition', '')}\n"
            # 🔴 **그 경기에 맞게 읽는다**(지시 2026-10-15 · 사본 금지)
            + __import__("app.core.querywriter",
                         fromlist=["x"]).comp_hint(ref) + "\n"
            f"=== 묶음(코드가 만든 것 · 이것이 전부다) ===\n{said}\n\n"
            f"🔴 `sentences` — **{MIN_SENT}~{MAX_SENT}개** 문장. 각 "
            f"{SENT_MAX}자 안.\n"
            "   ① **변수가 말하는 것**(폼·득실점·결장·일정·동기) ② "
            "**포메이션과 전략 갈래**가 이 경기를 어떻게 만드나 ③ 두 팀의 "
            "강점·약점이 어디서 부딪히나 ④ 그래서 **네 예측과 그 까닭** "
            "⑤ 무엇을 조심하나\n"
            "   ⚠️ 확률은 **변수에서 나온 결과**다 — 적어도 되지만 **예측의 "
            "근거로 쓰지 마라**(그 수를 출발점으로 삼은 문장은 버려진다).\n"
            "🔴 `refs` — 문장마다 근거 **한 줄의 머리말**(예 `확률`·`axis1`·"
            "`변수 IR13-away`). 문장 수와 같게.\n"
            "🔴🔴 **네 예측을 직접 낸다**(사용자 지시 2026-10-15)\n"
            "   · `pick` — `home`·`draw`·`away` 중 **하나**. 🔴 **확률 수를 "
            "따라가지 마라** — 변수(폼·득실점·결장)와 **포메이션·전략**, 경기 "
            "사정을 보고 **네가** 고른다(확률과 달라도 된다 · 같아도 된다 — "
            "어느 쪽이든 **변수로** 까닭을 적어라).\n"
            "   · `score` — **예상 점수 하나**(`2-1` 꼴). 기대 득점·스코어 "
            "격자는 **없다** — **득점·실점 평균과 포메이션·전략**을 보고 "
            "**네가** 판단해 낸다(그 까닭을 문장에 적어라).\n"
            "   🔴🔴 점수는 **홈-원정 순서**다(`2-1` = 홈 2 · 원정 1) — "
            "**`pick` 과 어긋나면 안 된다**: `home` 이면 홈이 더 많고, `away` "
            "면 원정이 더 많고, `draw` 면 **동점**이어야 한다.\n"
            "🔴 문장은 **서술형 분석글**이다 — 쓸 수 있는 수는 **확률 · 네 "
            "예상 점수 · 묶음의 득점·실점 평균**뿐이다(그 밖의 퍼센트·배율·"
            "계수 금지). 그 외는 변수와 선수 이름으로 설명한다.\n"
            "🔴🔴 **수비 불안과 공격력을 득실점으로 말한다**(사용자 지시 "
            "2026-10-15) — 묶음의 `최근 5경기 … 득점 평균 … 실점 평균` 을 들어 "
            "**어느 쪽 수비가 불안하고 어느 쪽 공격이 센지** 적는다. ⚠️ 결장·"
            "이탈만으로 수비를 판단하지 마라(실제로 얼마나 먹혔나가 더 세다).\n"
            "🔴 **이제까지 모은 자료(묶음)만** 쓴다 — 네 기억으로 사실을 보태면 "
            "거짓이다. 모르는 것은 **모른다고 적는다**.\n"
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **없는 폼을 지어내지 마라** — 사용자 지시 2026-10-16
            # ══════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-16(Sydney FC · A리그 개막 전): 컵·친선을 빼자
            #     리그 경기가 0건이 되어 묶음에 **폼이 한 줄도 없었다**. 그런데
            #     solar 가 *"최근 5경기 득점 평균 1.7골, 실점 1.4골 …"* 이라고
            #     **네 수를 지어냈다**(deepseek 는 *"폼·결장·XI 가 모두 없다"* 고
            #     정직하게 썼다).
            #  🔴 그래서 **없을 때 쓰지 말라고 못 박는다** — 일반 규칙("모르면
            #     모른다고 적어라")만으로는 안 막혔다.
            "🔴🔴 **묶음에 최근 경기 득점·실점 평균이 없으면 그 수를 쓰지 "
            "마라** — *\"최근 5경기 득점 평균 …\"* 같은 문장을 **지어내지 "
            "않는다**(코드가 묶음과 대조해 버린다). 폼이 없으면 **있는 변수**"
            "(홈 이점·포메이션·전략·일정)로만 분석한다.\n"
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **기사 유무는 적지 않는다** — 사용자 지시 2026-10-15
            # ══════════════════════════════════════════════════════
            #
            #  > 평을 낼 때 **기사에서 나온 사실이 없다는 표기하지 않아도 된다**
            #  > … 기사에서 나온 내용은 **평문으로 안 써도 된다**
            #
            #  ⚠️ 종전 규칙은 *"기사에서 나온 사실을 반드시 한 번은 쓰고, 없으면
            #     없다고 적어라"* 였다 — 그래서 다섯 문장 중 한 자리를
            #     **"기사에서 나온 것이 없다 · 문서 출처는 BeSoccer·ESPN…"**
            #     같은 **살림 보고**가 먹었다(실측 2026-10-15 BG Pathum).
            #  🔴 이제 **강제하지 않는다** — 기사에 알맹이가 있으면 쓰고, 없으면
            #     그 자리를 **경기 분석으로 채운다**(없다는 말은 쓰지 않는다).
            "🔴 묶음의 `기사에서 나온 사실` 칸에 쓸 것이 있으면 분석에 녹인다. "
            "⚠️ 그 칸이 **⬜ 없다** 면 **그 사실을 적지 마라** — *\"기사에서 "
            "나온 것이 없다\"* · *\"문서 출처는 …뿐이다\"* 같은 **자료 살림 "
            "이야기를 평문에 쓰지 않는다**. 그 자리는 **경기 분석**으로 채운다.\n"
            "⚠️ 묶음에 없는 수를 쓰면 **버려진다** — 코드가 대조한다.")),
    ]
    got = llm.ask(provider=provider, purpose="commentary", messages=msgs,
                  out=Verdict, state=state)
    if not isinstance(got, Verdict):
        # 🔴🔴 **사유를 그대로 적는다** — 사용자 지시 2026-10-15: *"평이 왜 안
        #    나오는 이유부터 찾아라"*. ⚠️ `LLM_TIMEOUT` 하나로는 **공급자가 안
        #    준 것**과 **카드 상한이 호출을 막은 것**(`deadline.call_cap_sec`)을
        #    가를 수 없었다 — `detail` 이 그 둘을 가른다.
        why = (f"🔴 {provider} 실패({getattr(got, 'reason', '?')}) — 평이 없다 "
               f"· 사유 {str(getattr(got, 'detail', '') or '⬜ 없다')[:160]}")
        state.note(f"s6v 종합 평 — {why}")
        return None, box, why
    n = len(list(got.sentences or []))
    state.note(f"s6v 종합 평 — {provider} 문장 {n}개")
    return got, box, f"{provider} 문장 {n}개"


def _nums(said: str) -> list[float]:
    """🔴 (가) — 글 속 수. 분·년·나이는 **안 센다**. ⚠️ 옛 호출부를 위해 남긴다."""
    return [float(x) for x, _pc in _num_tokens(said)]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(가) 수 검사를 둘로 가른다** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Sydney FC): 묶음에 **폼이 한 줄도 없는데** solar 가
#     *"최근 5경기 득점 평균 **1.7**골, 실점 **1.4**골 … 원정 **1.3**/**1.5**"*
#     이라고 썼다. 🔴 검열은 그 넷을 **놓치고** 엉뚱하게 `5`(최근 **5**경기)를
#     잡았다 — 두 방향 다 틀렸다.
#  🔴 까닭: 비교가 **상대 오차 5%**였다. 묶음의 `1.6444` 와 지어낸 `1.7` 은
#     차이 0.056 인데 허용치가 ±0.082 라 **통과**했다. 반대로 `5` 는 묶음에
#     그 수가 없어 걸렸다(그런데 그건 *"다섯 경기"* 라는 **낱말**이다).
#  🔴 그래서:
#     · **소수**(`1.7`·`88.8`)는 **글자 그대로** 묶음에 있어야 한다(오차 없음)
#     · **퍼센트**(`42%`·`33.3%`)는 수로 대조한다(±0.05 · 반올림 표기를 받아준다)
#     · **맨 정수**(`최근 5경기`·`11명`·`3연승`)는 **세지 않는다** — 셀 수 없는
#       낱말이고, 세면 멀쩡한 문장이 빨개진다(실측).

def _num_tokens(said: str) -> list[tuple[str, bool]]:
    """🔴 글 속 수 토막 — `(글자, 퍼센트인가)`. 분·년·나이는 뺀다."""
    out: list[tuple[str, bool]] = []
    text = str(said or "")
    for m in _NUM.finditer(text):
        tail = text[m.end():m.end() + 1]
        if tail in NUM_SKIP:
            continue
        got = m.group(0)
        out.append((m.group(1), "%" in got))
    return out


def num_bad(one: str, box: str) -> str:
    """🔴 (가) — 그 문장이 **묶음에 없는 수**를 썼나. 없으면 빈 글자."""
    ok_pc = [float(x) for x, pc in _num_tokens(box) if pc]
    for said, pc in _num_tokens(one):
        if pc:
            # 🔴 퍼센트는 수로 본다(반올림 표기를 받아준다)
            try:
                got = float(said)
            except ValueError:
                continue
            if not any(abs(got - x) <= 0.05 for x in ok_pc):
                return f"🔴 (가) **없는 수**({said}%) — `{one[:50]}`"
            continue
        if "." not in said:
            continue          # 🔴 맨 정수는 안 센다(위 머리말)
        # 🔴 소수는 **글자 그대로** 있어야 한다
        if said not in box:
            return f"🔴 (가) **없는 수**({said}) — `{one[:50]}`"
    return ""


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
    # 🔴 **그 모델이 예측한 점수의 수도 허용한다**(지시 2026-10-15) — 격자를
    #    지웠으니 `2-1` 의 `2`·`1` 이 묶음에 없다. ⚠️ 실측: (가) 가 그 `2` 를
    #    *"없는 수"* 로 잡아 멀쩡한 평이 **지어냈다**로 떨어졌다.
    ok_nums = [*ok_nums, *_nums(str(getattr(got, "score", "") or ""))]
    ok_scores = set(_scores(said_box))
    # 🔴 **그 모델이 예측한 점수는 거짓이 아니다**(지시 2026-10-15) — 격자를
    #    지웠으니 묶음에 있을 수 없다. 문장에 그 점수를 써도 (나) 가 안 잡는다.
    ok_scores |= set(_scores(str(getattr(got, "score", "") or "")))
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
        # (가) 숫자 — 소수는 글자 그대로 · 퍼센트는 수로 · 맨 정수는 안 센다
        said_num = num_bad(one, said_box)
        if said_num:
            bad.append(said_num)
        # (나) 스코어 — 꼴 그대로 대조한다
        for sc in _scores(one):
            if sc not in ok_scores:
                bad.append(f"🔴 (나) **없는 스코어**({sc}) — `{one[:50]}`")
                break
        # (다) 이름
        # 🔴 **묶음 원문도 넘긴다**(사용자 지시 2026-10-16) — 한 낱말 이름과
        #    자리 글자 접두(`CB Waston`)가 거짓 위반이 되던 자리다(`s9_say`
        #    머리말의 그 실사고).
        for nm in _say._names_in(one, ok_names, text=said_box):
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **사람 이름이 아닌 것을 빼낸다** — 실측 2026-10-15
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ (다) 5건 중 4건이 거짓 양성이었다 —
            #     `Afc Champions League Two`·`UEFA Champions League`(대회 이름) ·
            #     `WW DD`(최근 폼 글자 `W W D D` 를 모델이 붙여 쓴 것).
            #  🔴 둘 다 **사람 이름이 아니다**. 대회 이름은 묶음의 대회 줄로
            #     가리고, 폼 글자는 꼴로 가린다(`W`·`D`·`L` 만 든 토막).
            if _FORM_WORD.fullmatch(str(nm).replace(" ", "")):
                continue
            if any(str(nm).lower() in str(x).lower()
                   for x in (_COMP_WORDS, said_box.lower())):
                continue
            bad.append(f"🔴 (다) **없는 이름**({nm}) — `{one[:50]}`")
            break
        # 🔴🔴 (라) **규칙·변수 번호** — 묶음에 그 글자가 있어야 한다
        for rid in _ruleids(one):
            # 🔴 **집안 접두도 센다**(위 머리말) — 묶음에 `S01-home` 이 있으면
            #    글의 `S01` 은 그 집안을 가리킨 것이다(거짓이 아니다).
            if rid not in ok_ids and not any(
                    str(x).startswith(f"{rid}-") for x in ok_ids):
                bad.append(f"🔴 (라) **없는 규칙·변수 번호**({rid}) — 묶음에 그 "
                           f"글자가 없다 · `{one[:50]}`")
                break
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예측도 검열한다** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 `pick` 은 셋 중 하나여야 하고, `score` 는 **묶음의 스코어 상위에 있는
    #     것**이어야 한다(없는 점수를 지어내면 거짓이다).
    said_pick = str(getattr(got, "pick", "") or "")
    if said_pick not in ("home", "draw", "away"):
        bad.append(f"🔴 (마) **예측이 없다·틀렸다**(`pick`={said_pick!r}) — "
                   "`home`·`draw`·`away` 중 하나여야 한다")
    said_sc = str(getattr(got, "score", "") or "").strip()
    if not said_sc:
        bad.append("🔴 (마) **점수 예측이 없다**(`score`)")
    else:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **승패와 점수가 어긋나면 위반** — 사용자 지시 2026-10-15
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-15(Svay Rieng vs Shanghai Shenhua): solar 가
        #     `pick=away` 인데 점수를 **`1-0`**(홈 승 스코어)으로 적었다.
        #     검열은 `pick` 이 셋 중 하나인지와 빈 칸만 봤고 **둘의 일치는
        #     안 봤다**.
        #  🔴 점수는 **홈-원정 순서**다 — 그 둘이 어긋나면 평 자체가 모순이다.
        got_sc = _SCORE.search(said_sc)
        if got_sc:
            gh, ga = int(got_sc.group(1)), int(got_sc.group(2))
            want = ("home" if gh > ga else "away" if ga > gh else "draw")
            if said_pick in ("home", "draw", "away") and want != said_pick:
                said_k = {"home": "홈 승", "draw": "무", "away": "원정 승"}
                bad.append(
                    f"🔴 (마) **예측과 점수가 어긋난다** — `pick` 은 "
                    f"{said_k.get(said_pick)} 인데 점수 {said_sc} 는 "
                    f"{said_k.get(want)} 다(점수는 **홈-원정 순서**다)")
    # 🔴 근거 — 문장 수와 같아야 한다
    refs = [str(x) for x in (got.refs or [])]
    if len(refs) < len(rows):
        bad.append(f"🔴 근거 {len(refs)}개 < 문장 {len(rows)}개")
    return ("지어냈다" if bad else "안 지어냈다"), bad


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **근거는 서술형으로 적는다** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 근거는 ???? **서술형으로 바꿔라**
#
#  ⚠️ 전에는 모델이 돌려준 꼬리표를 그대로 찍었다(`근거 \`axis1·S01\``) —
#     읽는 사람은 그 번호가 **묶음의 어느 줄**인지 알 수 없었다.
#  🔴 그래서 꼬리표마다 **묶음에서 그 글자를 품은 줄을 찾아** 그 줄의 글자로
#     풀어 쓴다. 🔴 **새 글자를 짓지 않는다**(묶음이 원본이다 · 사본 금지).
#  🔴 묶음에 없는 꼬리표는 **그렇게 적는다**(#3 조용한 0 금지) — 그것이
#     (라) 검열이 잡는 그 자리다.
_REF_CUT = 46          #: 🔴 풀어 쓴 한 토막의 글자 상한


def _ref_one(piece: str, box: list[str]) -> str:
    """🔴 꼬리표 하나 → **묶음 줄의 글자**로 풀어 쓴 한 토막."""
    key = str(piece or "").strip().strip("`")
    if not key:
        return ""
    # 🔴🔴 **줄을 고르는 순서가 있다** — ⚠️ 실측 2026-10-15: 그냥 품은 줄을
    #    먼저 집으니 `axis1` 이 *변수* 줄(자리 `['axis1','hypo']`)에 걸려
    #    **축 줄 대신 변수 줄**로 풀렸다. 머리 일치를 먼저 본다.
    line = ""
    for how in ("머리", "변수 이름", "변수 집안", "품은 줄"):
        for one in box:
            said = str(one).strip()
            if how == "머리" and said.startswith(key):
                line = said
            elif how == "변수 이름" and f"변수 `{key}`" in said:
                line = said
            elif how == "변수 집안" and f"변수 `{key}" in said:
                line = said
            elif how == "품은 줄" and key in said:
                line = said
            if line:
                break
        if line:
            break
    if not line:
        return f"🔴 묶음에 없는 근거(`{key}`)"
    # ── 변수 줄 — `변수 \`R1\` [absence] 자리 [...] — 글`
    got = re.match(r"변수 `([^`]+)` \[([^\]]*)\] 자리 [^—]*—\s*(.*)", line)
    if got:
        said = got.group(3).strip()[:_REF_CUT]
        return f"변수 {got.group(1)}({got.group(2)}) — {said}"
    # ── 축 줄 — `axis1 — 홈 … · 차 …`
    got = re.match(r"(axis([0-3]))\s*—.*?차\s*([+-]?[\d.]+)", line)
    if got:
        return f"축{got.group(2)}(차 {got.group(3)})"
    # ── 그 밖(확률·λ·오버·스코어 상위·λ 유도·기여) — 머리와 꼬리를 그대로
    head, _, tail = line.partition("—")
    said = tail.strip()[:_REF_CUT] if tail.strip() else ""
    return f"{head.strip()} 줄" + (f"({said})" if said else "")


#: 🔴 서술형 근거에 넣는 토막 수 상한(넘치면 글이 평보다 길어진다)
_REF_MAX = 3


def _ref_keys(box: list[str]) -> list[str]:
    """🔴 묶음이 가진 **열쇠 목록** — 변수·축 번호와 줄 머리말. 긴 것이 먼저다.

    ⚠️ 실측 2026-10-15(노리치 2차): solar 는 근거를 꼬리표가 아니라 **문장
       통째**로 돌려줬다(`확률 — 홈 44.1% 무 26.1% … λ 합 2.602`). 그래서
       `·` 로 토막내는 방식은 전부 *"묶음에 없는 근거"* 가 됐다.
    🔴 그래서 토막내지 않고 **근거 글 안에서 이 열쇠들을 긁는다**.
    """
    keys: list[str] = list(_ruleids("\n".join(box)))
    for one in box:
        head = str(one).strip().partition("—")[0].strip()
        if not head or head.startswith("변수"):
            continue            # 🔴 `변수 11개` 머리말은 너무 흔하다
        keys.append(head)
        bare = head.partition("(")[0].strip()
        if bare and bare != head:
            keys.append(bare)   # `λ(기대 득점)` → `λ` · `λ 유도(코드 글자)` → `λ 유도`
    # 🔴 긴 열쇠가 먼저여야 한다 — `S01` 이 `S01-home` 을 가로채면 안 된다
    # ⚠️ 한 글자 열쇠(`λ`)를 빼면 안 된다 — 실측 2026-10-15: `len>=2` 로 걸러
    #    `확률·λ` 의 λ 가 조용히 사라졌다.
    return sorted(dict.fromkeys(k for k in keys if k.strip()), key=len,
                  reverse=True)


def ref_said(said_r: str, box: list[str]) -> str:
    """🔴🔴 **서술형 근거** — 근거 글이 가리킨 묶음 줄을 글자로 풀어 쓴다."""
    raw = str(said_r or "").strip()
    if not raw or raw.startswith("⬜"):
        return "⬜ 근거 없음"
    seen: set = set()
    rows: list[tuple[int, str]] = []
    for key in _ref_keys(box):          # 🔴 긴 열쇠부터(가로채기 막는다)
        if key not in raw or key in seen:
            continue
        seen.add(key)
        said = _ref_one(key, box)
        if not said or any(said == x for _, x in rows):
            continue
        # 🔴 **읽는 순서는 묶음 순서다** — 열쇠 길이 순이 아니다
        at = next((i for i, one in enumerate(box) if key in str(one)), len(box))
        rows.append((at, said))
    if not rows:
        # 🔴 조용히 넘기지 않는다 — 근거 글이 묶음의 아무것도 안 가리켰다
        return f"🔴 묶음의 어느 줄도 안 가리킨다(`{raw[:40]}`)"
    rows.sort(key=lambda kv: kv[0])
    said_all = [x for _, x in rows]
    # ⚠️ 상한을 넘겨 자를 때는 **몇 개를 뺐는지 적는다**(#3 조용한 0 금지)
    cut = len(said_all) - _REF_MAX
    return (", ".join(said_all[:_REF_MAX])
            + (f", 외 {cut}개" if cut > 0 else "") + " 에서 왔다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **두 평의 공통점 ↔ 확률** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > **2 평문의 공통점과 확률이 일치했을때 더 정확해진다**
#
#  🔴 그래서 코드가 그것을 **세어 적는다** — 두 모델이 같은 쪽을 골랐나, 같은
#     점수를 댔나, 그리고 그것이 **확률이 가리키는 쪽**과 같나.
#  ⚠️ 판정이 아니라 **표시**다 — 등급·확률을 이 줄이 바꾸지 않는다.


def agree_of(cards: dict, prob) -> str:
    """🔴 두 평의 공통점과 확률 일치 — 한 줄. `cards` 는 `{공급자: Verdict}`."""
    rows = {k: v for k, v in dict(cards or {}).items() if v is not None}
    if len(rows) < 2:
        return ("🤝 **공통점 — ⬜ 못 쟀다**(평이 "
                f"{len(rows)}개다 · 둘이 있어야 견준다)")
    picks = {k: str(getattr(v, "pick", "") or "") for k, v in rows.items()}
    scores = {k: str(getattr(v, "score", "") or "") for k, v in rows.items()}
    want = ""
    if prob is not None:
        box = {"home": float(getattr(prob, "home", 0.0) or 0.0),
               "draw": float(getattr(prob, "draw", 0.0) or 0.0),
               "away": float(getattr(prob, "away", 0.0) or 0.0)}
        want = max(box, key=lambda k: box[k])
    said_k = {"home": "홈 승", "draw": "무", "away": "원정 승"}
    same_p = len(set(picks.values())) == 1 and all(picks.values())
    out = []
    if same_p:
        one = list(picks.values())[0]
        out.append(f"두 평이 **같은 쪽**({said_k.get(one, one)})")
        if want:
            out.append("확률과 **일치한다** 🟢" if one == want
                       else f"그런데 확률은 **{said_k.get(want, want)}** 쪽이다 🔴")
    else:
        out.append("두 평이 **갈렸다** — "
                   + " · ".join(f"{k} {said_k.get(v, v or '⬜')}"
                                for k, v in picks.items()))
    same_s = len(set(scores.values())) == 1 and all(scores.values())
    out.append(f"점수 {'**같다**' if same_s else '다르다'}("
               + " · ".join(f"{k} {v or '⬜'}" for k, v in scores.items()) + ")")
    return "🤝 **공통점** — " + " · ".join(out)


def said_of(got: Verdict | None, box: list[str], *,
            provider: str = "solar") -> str:
    """🔴 카드·보고에 찍는 글 — 평 + **지어냈나 결론**."""
    verdict, bad = judge(got, box)
    head = f"🧭 **종합 평**({provider}) — 지어냄 판정 **{verdict}**"
    if got is None:
        return head + "\n" + "\n".join(f"- {x}" for x in bad)
    rows = [head]
    # 🔴 **예측을 머리에 적는다**(사용자 지시 2026-10-15) — 모델이 고른 것이다
    said_pick = {"home": "홈 승", "draw": "무", "away": "원정 승"}.get(
        str(getattr(got, "pick", "") or ""), "⬜ 없음")
    rows.append(f"- 🎯 **{provider} 예측 — {said_pick} · 점수 "
                f"{str(getattr(got, 'score', '') or '⬜ 없음')}**")
    refs = [str(x) for x in (got.refs or [])]
    for i, one in enumerate(list(got.sentences or [])):
        said_r = refs[i] if i < len(refs) else "⬜ 근거 없음"
        rows.append(f"- {one}\n    · 근거 — {ref_said(said_r, box)}")
    for x in bad:
        rows.append(f"  {x}")
    return "\n".join(rows)
