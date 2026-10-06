"""🔴🔴 **검색어 문지기** — v5 §4-1. 세 요소 미만은 거부한다. [#1]

> 검색어는 반드시 `{팀 또는 별칭} {상대} {대회명} {종목 낱말} {날짜 또는
> 'preview/lineup/injury'}` **중 세 요소 이상**을 가진다. 팀·나라 이름
> 하나짜리는 search 가 **거부하고 `query_too_bare` 사유를 돌려준다.**
> … 코드도 **같은 검색어 반복을 거부한다**(동일 2회 이상 → `duplicate_query`).

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04(북마케도니아 vs 스코틀랜드)
══════════════════════════════════════════════════════════════════

```
Scotland lineup Oct 3   → rottentomatoes **드라마 출연진** ×8 · rugby ×15
North Macedonia lineup  → 위키 경제·국기 · SMS 판매 · 법률 사무소
→ hits 1302 중 **1115 건이 쓰레기**(86%)
```
⚠️ 그 쓰레기가 LLM 예산을 먹어 **진짜 프리뷰에 0초**가 남았다.
🔴 §4-1 은 **질의 자체를 막는다** — 받고 나서 거르는 것보다 앞이다.

⚠️ *"요소"* 를 글자 수로 세지 않는다 — **무엇이 들어 있나**를 센다. 그래서
   호출부가 조각을 **이름으로** 넘길 수도 있고(`parts=`), 안 넘기면 글에서 짐작한다.
"""
from __future__ import annotations

import re

from app.reasons import Reason

#: 🔴 §4-1 이 이름 댄 **다섯 요소**. ⚠️ 셋 이상이어야 한다.
PARTS: tuple[str, ...] = ("team", "opponent", "competition", "sport", "when")

#: 🔴 §4-1 의 `'preview/lineup/injury'` — **날짜 대신** 쓸 수 있는 말들.
#   ⚠️ 여기 적는 것은 **검색 핵심어**이지 사실이 아니다(번역·관례다).
WHEN_WORDS: tuple[str, ...] = (
    "preview", "lineup", "line-up", "injury", "team news", "starting",
    "predicted", "prediction", "xi",
    "선발", "라인업", "결장", "부상", "프리뷰", "예상",
    "スタメン", "先発", "欠場", "予想",
    "alineación", "once", "lesión", "previa",
    "首发", "阵容",
)

#: 🔴 날짜 꼴 — 숫자 + 월 이름·월일. ⚠️ 연도는 §12-b 가 금지한다
_DATE = re.compile(
    r"\b\d{1,2}\s*[月월]\s*\d{1,2}|\b\d{1,2}\s*[日일]\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{1,2}\b|"
    r"\b\d{1,2}\s*(?:окт|нов|дек|сеп|авг)|"
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **달+연도도 날짜다**(실측 2026-10-04)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전은 **달+일**(`Oct 4`·`10月4`)만 봤다. 🔴 모델은
    #     `October 2026`·`2026 October` 처럼 **달+연도**로도 쓴다 — 그것도
    #     창을 좁힌다(§4-1 이 요구하는 것이 그것이다).
    #  🔴 그 한 줄이 에이전트 질의를 **전부 거부**하게 만들었다(게이트 2 첫 판).
    #  ⚠️ **연도만**은 아니다 — `2026` 하나는 창을 안 좁힌다.
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*"
    r"(?:19|20)\d{2}\b|"
    r"\b(?:19|20)\d{2}\s*(?:년\s*)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|"
    r"oct|nov|dec)[a-z]*|"
    # 🔴 `2026年10月`·`2026년 10월` — 연+달
    r"\b(?:19|20)\d{2}\s*[年년]\s*\d{1,2}\s*[月월]|"
    # 🔴 ISO 꼴 `2026-10-04`·`2026/10/04`
    r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b", re.I)

#: 🔴 **낱말 수의 최소** — 요소를 글에서 짐작할 때의 바닥이다.
#   ⚠️ 이름 하나(`North Macedonia`)는 두 낱말이지만 **요소는 하나**다.
MIN_PARTS = 3


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


#: 🔴 §4-1 이 이름 댄 **다섯 요소** + 결정 ⑥ 의 **조건부 경기장**.
#   ⚠️ `venue` 는 `PARTS` 에 **안 넣는다** — 다섯은 그대로다(아래 `kind` 조건).
VENUE_KINDS: tuple[str, ...] = ("venue_weather",)


def kind_of(query: str) -> str:
    """🔴 그 질의가 **어느 유형**인가(지금은 `venue_weather` 만 가른다).

    ⚠️ 유형 낱말을 **여기 적지 않는다** — `config/variable_types.yaml` 의
       `venue_weather.match` 정규식이 원본이다(사본 금지). 🔴 그 표는 날씨
       낱말을 세 언어로 이미 들고 있다(`rain|wind|heat` · `우천|강수 확률` ·
       `雨天|荒天|強風`).
    🔴 못 가리면 **빈 문자열**이다 — 그러면 경기장을 안 센다(기본값이 안전하다).
    """
    from app import rules
    low = _norm(query)
    if not low:
        return ""
    for kind in VENUE_KINDS:
        box = rules.variable_types().get(kind) or {}
        # 🔴 **질의용 칸이 먼저**다 — 기사 낱말과 질의 낱말이 다르다(실측).
        #    ⚠️ 없으면 `match` 로 떨어진다(새 유형을 더할 때 안 끊긴다).
        for pat in (box.get("query_match") or box.get("match") or []):
            try:
                if re.search(str(pat), low, re.I):
                    return kind
            except re.error:                            # pragma: no cover
                continue
    return ""


#: 🔴 대회명에서 **버리는 조각** — 조별 꼬리는 대회를 가리키지 않는다.
#  ⚠️ `A`·`1` 은 한 글자라 어느 글에나 섞인다. `grp`·`group`·`round` 는 아무
#     대회에나 붙어 **다른 대회를 같다고** 말한다.
#  🔴 **`league`·`cup`·`series` 는 버리지 않는다** — 그것은 **대회 이름의
#     일부**다(`Nations League`·`日本シリーズ`). ⚠️ 한 번 버려 봤더니
#     `Nations League` 가 핵 낱말 하나(`nations`)로만 세어져 계약이 빨개졌다.
#     흔한 낱말이 혼자 통과하는 것은 `COMP_MIN_WORDS` 가 막는다.
COMP_DROP: frozenset[str] = frozenset({
    "grp", "group", "grupo", "round", "phase", "stage", "season",
    "div", "matchday"})

#: 🔴 대회로 인정할 **최소 핵 낱말 수**. ⚠️ 하나로는 안 된다 — `league` 처럼
#   흔한 낱말 하나가 `France league table shop` 을 대회로 만든다(실측 2026-10-05).
COMP_MIN_WORDS = 2


def comp_words(comp: str) -> list[str]:
    """🔴 대회명 → **핵 낱말들**. ⚠️ 조각·흔한 낱말은 버린다(`COMP_DROP`).

    `UEFA Nations League A Grp. 1` → `['uefa', 'nations']`
    """
    out: list[str] = []
    for raw in _norm(comp).replace(".", " ").split():
        w = raw.strip()
        if len(w) < 3 or w in COMP_DROP or w.isdigit():
            continue
        if w not in out:
            out.append(w)
    return out






#: 🔴🔴 **낱말 상한** — 딥서치 재구축 §4-3 (M61).
#
#  > 10단어 초과 → `query_too_long` 거부. 실측: **긴 문장 질의가 0건을 만들었다.**
#
#  ⚠️ `query_too_bare`(3요소 미만)와 **반대 방향**이다 — 하나는 너무 넓고
#     하나는 너무 좁다. 🔴 둘을 한 사유로 묶으면 고칠 곳을 못 가린다.
MAX_WORDS = 10








class QueryLog:
    """🔴 §4-1 — **같은 검색어를 두 번 던지지 않는다.**

    ⚠️ 글자만 다른 것은 **같은 질의**다(공백·대소문자) — 각도를 바꾼 척하는 것을
       막는다. 🔴 각도를 바꾸는 것은 **요소를 바꾸는 것**이다.
    """

    def __init__(self):
        self.seen: dict[str, int] = {}

    def check(self, query: str, *, parts: dict | None = None,
              kind: str = "", seed: bool = False) -> tuple[bool, Reason, str]:
        """🔴 `seed=True` 는 §2 표의 **씨앗 템플릿**이다(§4-3 자동 통과).

        ⚠️ 중복 검사는 **면제되지 않는다** — 같은 씨앗을 두 번 던지면 그것은
           각도를 안 바꾼 것이다.
        """
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **문지기는 하나다** — 사용자 지시 2026-10-06 ⑧
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 이 파일의 `gate`(10낱말)가 둘째 문지기였다. 🔴 v6 §6 이
        #     *"둘 중 하나만 남긴다 — 오픈월드 ⑥-2 와 s3 질의 모두 통과시키는 쪽"*
        #     이라 적었고 그 쪽이 `llm.query_ok` 다. 그래서 `gate` 를 지우고 **그
        #     하나**를 부른다. ⚠️ 중복 검사(아래)는 그대로다 — 그것은 문지기가
        #     아니라 *"각도를 바꿨나"* 를 보는 것이다.
        from app import llm as _llm
        if not _llm.query_ok(query):
            n = len(str(query).split())
            return (False, Reason.QUERY_TOO_BARE,
                    f"🔴 §12-b(`llm.query_ok`) 가 막는다 — 낱말 {n}개"
                    f"(1~6 · 연산자·연도 금지)")
        ok, reason, why = True, Reason.OK, f"문지기 통과(낱말 {len(str(query).split())}개)"
        if not ok:
            return ok, reason, why
        key = _norm(query)
        n = self.seen.get(key, 0)
        self.seen[key] = n + 1
        if n:
            return False, Reason.DUPLICATE_QUERY, (
                f"🔴 `{Reason.DUPLICATE_QUERY.value}` — 같은 검색어를 "
                f"**{n + 1}번째**로 던졌다(`{key[:60]}`). §4-1: 각도를 바꿔야 한다")
        return True, Reason.OK, why
