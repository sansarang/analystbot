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

from app.core import crosscheck as _cc
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

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **문장 3~6** — 사용자 지시 2026-10-18(가설 전부 삭제)
# ══════════════════════════════════════════════════════════════════
#
#  > **가설 전부다 삭제** · llm 평은 **변수가지고만 승무패를 예측한다**
#
#  ⚠️ 종전은 `13~19` 였다 — 가설 다섯 + 검증 다섯 + 예측·조심·감시 자리였다.
#  🔴 그 자리들이 전부 사라졌으므로 **변수 분석 + 예측**만 남는다.
MIN_SENT, MAX_SENT = 3, 6
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
    pick: str = Field(default="", description=(
        "승패 예측: home·draw·away 중 하나. 아래 score 와 **반드시 맞아야** "
        "한다(home 이면 앞 수가 크고, away 면 뒤 수가 크다)."))
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **점수는 홈-원정 순서다** — 사용자 지시 2026-10-16
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-16(City Club vs Bashundhara · 그 전 PSIM 도 같다):
    #     solar 가 `pick=away` 인데 `score="2-1"` 을 냈다. 글에는 *"원정이
    #     이기고 홈이 한 골"* 이라고 썼으니 **1-2 를 뜻한 것**인데 **순서를
    #     거꾸로** 적었다. 🔴 프롬프트에만 적어 둔 규칙이 두 번 안 지켜졌다.
    #  🔴 그래서 **칸 설명(스키마)** 에도 박는다 — 모델이 출력 직전에 보는 글이다.
    #: 🔴 점수 예측 — `2-1` 꼴(모델 판단 · 격자 없음) · **앞이 홈, 뒤가 원정**
    score: str = Field(default="", description=(
        "예상 점수 `홈-원정` 순서. **앞이 홈 득점, 뒤가 원정 득점**이다. "
        "보기 — 원정이 2골 넣고 홈이 1골이면 `1-2` 다(`2-1` 이 아니다). "
        "pick 이 away 면 뒤 수가 더 커야 하고, home 이면 앞 수가 더 커야 "
        "하며, draw 면 두 수가 같아야 한다."))


def chain_of(ref: MatchRef, prob, mr, varset, *,
             docs: list | None = None, plan=None, strat=()) -> list[str]:
    """🔴🔴 **변수만** 싣는다 — 사용자 지시 2026-10-18.

    > llm 은 **서치용**으로 사용한다 .. **전략 분석 삭제** .. llm 평은
    > **변수가지고만 승무패를 예측한다** .. **변수만 제공** .. 그외 프론프트 삭제
    > **가설 전부다 삭제**

    ⚠️ 종전 묶음은 **216줄**이었다 — 확률 줄 · 포메이션·전략 칸 · 전략 변수
       (`SL*`) · 기사 사실 · 문서 출처 · 축 분해 · λ 유도 · 🔎 파이프라인 줄.
    🔴 **전부 걷었다.** 지금 싣는 것은 변수 두 묶음뿐이다:
       ① 확률에 닿는 자리(축·λ상수)에 든 변수 ② 맥락 전용 변수.
    🔴 `prob`·`mr`·`docs`·`plan`·`strat` 은 **받지만 안 읽는다** — 부르는 쪽
       (카드·러너·계약)이 같은 꼴로 부른다. 그 사실을 여기 적는다(#3).
    ⚠️ 모델이 만든 글자는 **하나도 없다**(사용자 지시 2026-10-15 *"코드 만으로"*).
    """
    from app.core import routing as _rt
    rows: list[str] = []
    got_rows = list(getattr(varset, "rows", None) or [])
    AX = {*_rt.AXES, _rt.CONST}

    def _said(one) -> str:
        head = str(getattr(one, "claim", "") or getattr(one, "quote", "") or "")
        return head.strip()

    said_hit = [x for x in got_rows
                if set(str(p) for p in (getattr(x, "places", None) or [])) & AX
                and not bool(getattr(x, "context_only", False))]
    said_ctx = [x for x in got_rows if x not in said_hit]
    if said_hit:
        rows.append(f"변수 {len(said_hit)}개 — 확률에 닿는 자리에 든 것:")
        for one in said_hit:
            rows.append(f"  `{one.id}` [{one.type}] — {_said(one)}")
    else:
        rows.append("변수 — ⬜ **없다**(확률 자리에 든 변수가 하나도 없다)")
    if said_ctx:
        rows.append(f"맥락 전용 변수 {len(said_ctx)}개 — **확률에는 안 닿는다**"
                    "(표본이 적거나 안전장치가 걸렸다 · 사실은 사실이다):")
        for one in said_ctx:
            rows.append(f"  `{one.id}` [{one.type}] — {_said(one)}")
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **변수만 보고 승무패를 낸다** — 사용자 지시 2026-10-18
        # ══════════════════════════════════════════════════════════════
        #
        #  > llm 은 **서치용**으로 사용한다 .. **전략 분석 삭제** .. llm 평은
        #  > **변수가지고만 승무패를 예측한다** .. **변수만 제공** .. 그외
        #  > 프론프트 삭제 · **가설 전부다 삭제**
        #
        #  ⚠️ 종전 프롬프트는 **354줄**짜리였다 — 가설 다섯·검증 다섯·경기력
        #     패턴·줄 되돌아옴·확률 금지·포메이션 동반·기사 처리·감시 문장.
        #  🔴 **전부 걷었다.** 남은 것은 두 줄이다: *변수만 본다* · *승무패와
        #     점수를 낸다*. 묶음도 변수뿐이다(`chain_of`).
        llm.Message(role="system", content=(
            "너는 축구 경기를 예측하는 사람이다. 🔴 **아래 변수 목록만** 보고 "
            "승무패를 고른다 — 변수 밖의 것(네 기억·팀 명성·일반론·확률)은 "
            "쓰지 않는다. 묶음에 없는 숫자·스코어·선수 이름을 **만들지 "
            "마라**.")),
        llm.Message(role="user", content=(
            f"경기: {names[0]} (홈) vs {names[1]} (원정)\n"
            f"대회: {getattr(ref, 'competition', '')}\n"
            f"=== 변수(코드가 만든 것 · 이것이 전부다) ===\n{said}\n\n"
            f"🔴 `sentences` — **{MIN_SENT}~{MAX_SENT}개** 문장. 각 "
            f"{SENT_MAX}자 안. 변수가 말하는 것과 **그래서 어느 쪽인지**를 "
            "적는다.\n"
            "🔴 `refs` — 문장마다 근거 **변수 이름**(예 `변수 IR12-home`). "
            "문장 수와 같게.\n"
            "🔴 `pick` — `home`·`draw`·`away` 중 **하나**.\n"
            "🔴 `score` — 예상 점수 하나(`2-1` 꼴). 🔴 **홈-원정 순서**다 — "
            "`home` 이면 앞 수가 크고, `away` 면 뒤 수가 크고, `draw` 면 "
            "**동점**이어야 한다(`pick` 과 어긋나면 버려진다).\n"
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


def _is_team_short(said: str, ref) -> bool:
    """🔴🔴 그 글자가 **이 경기 두 팀의 약칭**인가(사용자 지시 2026-10-18).

    🔴 가리는 법 — 두 팀 이름을 낱말로 쪼개고, 글자의 낱말이 **전부** 그
       묶음에 들어 있거나 **머리글자**(`KC` ⊂ `Kansas City`)이면 약칭이다.
    ⚠️ 두 팀 이름은 `ref` 가 든다 — 여기서 표를 만들지 않는다(사본 금지).
    ⚠️ `ref` 가 없으면 **거짓**이다(지어내지 않는다).
    """
    if ref is None:
        return False
    words: set[str] = set()
    heads: set[str] = set()
    for side in ("home", "away"):
        nm = str(getattr(ref, f"{side}_name", "") or
                 getattr(ref, side, "") or "")
        said_w = [w for w in nm.replace(".", " ").split() if w]
        words |= {w.lower() for w in said_w}
        heads.add("".join(w[0] for w in said_w).lower())
        # 🔴 뒤 낱말들의 머리글자도 센다(`Kansas City` → `KC`)
        for i in range(len(said_w)):
            heads.add("".join(w[0] for w in said_w[i:]).lower())
    mine = [w for w in str(said or "").replace(".", " ").split() if w]
    if not mine:
        return False
    for w in mine:
        low = w.lower()
        if low in words or low in heads:
            continue
        return False
    return True


def judge(got: Verdict | None, box: list[str], *,
          provider: str = "", ref=None) -> tuple[str, list[str]]:
    """🔴🔴 **지어냈나** — `(결론, 위반 목록)`. 사용자 지시 2026-10-15.

    결론은 `지어냈다` · `안 지어냈다` · `못 쟀다` 셋뿐이다.
    🔴 묶음(`box`)이 **참이고** 글이 거기서만 나와야 한다.
    🔴 `provider` 는 **사유에 적는 이름**이다(사용자 지시 2026-10-17) —
       ⚠️ 실측 2026-10-17(베네치아 2차): deepseek 이 잘려 평이 없었는데
       사유가 *"**solar** 가 문장을 안 냈다"* 고 적었다(글자가 박혀 있었다).
       🔴 **못 낸 쪽을 틀리게 적으면 그것이 거짓 사유다**(#3).
    """
    if got is None or not list(got.sentences or []):
        return "못 쟀다", [f"⬜ 평이 없다 — {provider or '그 모델'} 가 "
                          "문장을 안 냈다"]
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
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **팀 약칭은 이름이 아니다** — 사용자 지시 2026-10-18
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고 2026-10-18(캔자스): 정식명이 `Sporting Kansas City`
            #     인데 모델이 **약칭 `Sporting KC`** 를 써서 (다)가 *"없는
            #     이름"* 으로 **3건** 잡았다 — 멀쩡한 평이 `지어냈다` 로
            #     떨어졌다.
            #  🔴 그 경기 **두 팀 이름의 낱말**로 가린다 — 약칭은 그 낱말들의
            #     부분집합이다(`Sporting KC` ⊂ {Sporting, Kansas, City} 의
            #     첫 글자). ⚠️ 두 팀 이름은 `ref` 가 든다(사본 금지).
            if _is_team_short(nm, ref):
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **문장에 점수를 거꾸로 적었나** — 사용자 지시 2026-10-16
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-16(PSIM): `score="0-1"`(원정 승)인데 문장에는
    #     *"원정 1골, 홈 0골로 원정 **1-0**"* 이라고 적었다 — 뜻은 맞고
    #     **표기만 뒤집혔다**. 그 줄만 보고 읽는 사람은 홈 승으로 읽는다.
    #  🔴 **뒤집힌 꼴만** 잡는다 — 다른 점수(예 *"1-1 로 접힐 여지"*)는
    #     **대안 시나리오**라 잡지 않는다(그것까지 막으면 평이 얕아진다).
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **묶음에 있는 스코어는 넘긴다** — 사용자 지시 2026-10-18
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-18(살케·리버풀·캔자스): 평이 **지난 경기 스코어**를
    #     인용했는데((마)가 그것을 *"예측을 거꾸로 적었다"* 로 잡았다:
    #     *"직전 경기에서 졌다(**1-2** 패)"* · *"**1-1·1-2** 로 뒤집히고"*).
    #     🔴 **패턴 분석을 제대로 한 평일수록 떨어졌다.**
    #  🔴 그래서 **묶음에 있는 스코어**(`ok_scores` — 코드가 실은 지난 경기
    #     점수)는 (마)에서 넘긴다. ⚠️ 모델이 **지어낸** 뒤집힌 스코어는 그대로
    #     잡는다(그것이 이 검사의 본래 일이다 · 캔자스 solar 가 그 꼴이었다).
    if said_sc and "-" in said_sc:
        rev = "-".join(reversed(said_sc.split("-", 1)))
        if rev != said_sc and rev not in ok_scores:
            for one in rows:
                if rev in _scores(one):
                    bad.append(
                        f"🔴 (마) **문장에 점수를 거꾸로 적었다** — 네 예측은 "
                        f"`{said_sc}`(홈-원정)인데 문장은 `{rev}` 다 · "
                        f"`{one[:40]}…`")
                    break
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
            provider: str = "solar", ref=None) -> str:
    """🔴 카드·보고에 찍는 글 — 평 + **지어냈나 결론**."""
    # 🔴 이름을 **넘긴다** — 사유가 못 낸 쪽을 바로 적는다(위 `judge` 머리말)
    # 🔴 `ref` 를 넘긴다 — (다)가 **팀 약칭**을 가리는 데 쓴다
    verdict, bad = judge(got, box, provider=provider, ref=ref)
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
