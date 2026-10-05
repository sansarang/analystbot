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


def comp_in(comp: str, query: str) -> bool:
    """🔴🔴 **그 질의가 이 대회를 가리키나** — 실측 2026-10-05 (프랑스–벨기에).

    ⚠️ 실사고: 종전엔 호출부가 `comp.lower() in query.lower()` 로 **정식명 한
       덩어리**를 봤다. 그래서 대회가 `UEFA Nations League A Grp. 1` 인 경기에서
       질의 `… 2026 Nations League` 가 대회를 **0개**로 셌고, 에이전트 검색
       22건 중 **15건이 거부**됐다(그중 10건이 `Nations League` 를 들고 있었다).
       `Grp.` ↔ `Group` **한 글자** 차이로도 실패했다.
    🔴 파라과이 별칭 `Albirroja`·`NLDS` 와 **같은 병**이다 — 정식명만 본다.

    🔴 그래서 **핵 낱말로** 본다: `COMP_MIN_WORDS` 개 이상 겹치면 그 대회다.
    ⚠️ 핵 낱말이 애초에 하나뿐인 대회(`MLB`·`KBO`)는 **그 하나**로 본다 —
       없는 낱말을 요구하면 그 리그가 통째로 막힌다.
    """
    words = comp_words(comp)
    if not words:
        return False
    low = _norm(query)
    hit = [w for w in words if w in low]
    need = min(COMP_MIN_WORDS, len(words))
    return len(hit) >= need


def count_parts(query: str, *, parts: dict | None = None,
                kind: str = "") -> tuple[int, list[str]]:
    """🔴 그 질의에 **몇 요소**가 들어 있나. `(수, 이름들)`.

    🔴 호출부가 `parts` 를 주면 **그것이 이긴다** — 짐작보다 선언이 낫다.
    ⚠️ 안 주면 글에서 짐작한다: 날짜·종목 낱말·핵심어는 글자로 보이고,
       팀·상대는 **보이지 않는다**(이름을 모르니까). 🔴 그래서 짐작은 늘
       **적게** 센다 — 그쪽이 안전하다(거짓 통과보다 거짓 거부가 낫다).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **선언은 짐작을 *덮어쓰지* 않는다 — 칸마다 더한다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04(게이트 2 첫 판): 에이전트 질의가 **전부 거부**됐다.
    #
    #      'Milwaukee Brewers last 5 games results October 2026 MLB'
    #        → 🔴 요소가 **2개**다(['team', 'competition'])
    #
    #     그 질의에는 **날짜(October 2026)** 가 있다. 🔴 그런데 호출부가
    #     `team`·`opponent`·`competition` 셋만 선언했고 종전 코드가
    #     **선언만** 세어 날짜·종목 낱말을 **잃었다.**
    #  🔴 *"선언이 짐작을 이긴다"* 는 **칸마다**여야 한다 — 통째로 덮으면 아는
    #     것을 선언하는 쪽이 **벌을 받는다**(아무것도 안 넘기면 더 많이 센다).
    said = [k for k in PARTS if str((parts or {}).get(k) or "").strip()]
    low = _norm(query)
    got: list[str] = []
    if low:
        got.append("team")                 # ⚠️ 질의가 있으면 팀은 들었다고 본다
    if _DATE.search(low):
        got.append("when")
    if any(w in low for w in WHEN_WORDS):
        if "when" not in got:
            got.append("when")
        else:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **이름을 바로잡았다** — 실측 2026-10-05 (프랑스–벨기에)
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 종전엔 이 한 요소를 `competition` 이라 불렀다. 🔴 그래서
            #     대회가 **한 번도 안 세어진 경기**에서 카드·로그가
            #     `['team','opponent','competition','when']` 이라 적었다 —
            #     네 번 다 거짓이었고, *"왜 통과했나"* 를 되짚을 수 없었다.
            #  🔴 수를 늘리는 판단은 그대로 둔다(핵심어가 둘이면 구체적이다).
            #     **부르는 이름만** 사실에 맞춘다.
            got.append("keyword")          # 🔴 핵심어가 또 있으면 한 요소 더
    from app import rules
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **라운드 이름은 대회다** — 결정 ⑤ (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 대회를 `game["league"]`(= `MLB`) **한 글자**로만 봤다. 🔴 그래서
    #     게이트2 2판에서 `NLDS` 를 든 질의 셋이 전부 거부됐다.
    #  🔴 목록은 **설정이 든다**(`config/search_words.yaml` `words.round`) —
    #     코드 분기가 아니다(결정 ⑤의 문구가 그것이다).
    if "competition" not in got:
        # 🔴 라운드 이름 + **리그가 선언한 이름들**. ⚠️ 둘 다 **선언된 자료**다.
        #
        #  ⚠️ 리그 이름을 더한 까닭: 결정 ⑥ 이 *"경기장+날짜만 있는 질의는
        #     여전히 bare"* 를 요구한다. 🔴 그러려면 `American Family Field
        #     weather forecast October 4 2026 **MLB**` 와 `Busch Stadium
        #     October 4 2026` 이 **갈려야** 하고, 그 차이는 `MLB` **하나**다.
        #  🔴 `config/leagues.yaml` 이 `names: [MLB, 메이저리그, 메이저]` 를
        #     **이미 들고 있었다** — 문지기가 `game["league"]` 한 글자만 봐서
        #     그 선언이 **안 쓰이고 있었다**(파라과이 별칭 `Albirroja` 와 같은 병).
        #  ⚠️ 두 글자 이하는 **안 쓴다** — `CS`·`J1` 같은 짧은 글자가 아무
        #     낱말 안에 섞여 거짓으로 센다.
        from app import league_index as _LI
        words = list(rules.round_words())
        for lg in _LI.leagues():
            words += [str(x) for x in (lg.get("names") or [])]
        for w in words:
            nw = _norm(w)
            if len(nw) > 2 and nw in low:
                got.append("competition")
                break
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **경기장은 조건부** — 결정 ⑥ (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 허용하되 조건을 단다. 경기장은 **`venue_weather` 유형 검색어에서만**
    #  > 요소로 세고, **경기장+날짜만 있는 질의는 여전히 bare** 다. 그래야
    #  > `"Busch Stadium"` 하나짜리가 다시 쓰레기를 끌고 오지 않는다.
    #
    #  ⚠️ 그래서 **`PARTS` 를 늘리지 않았다** — 다섯은 그대로고 `venue` 는
    #     그 유형에서만 센다. 🔴 유형을 **안 주면 안 센다**(기본값이 안전하다).
    venue = str((parts or {}).get("venue") or "").strip()
    if venue and str(kind or "") in VENUE_KINDS and _norm(venue) in low:
        got.append("venue")
        # 🔴🔴 **유령 `team` 을 거둔다** — 결정 ⑥ 의 조건이 그것을 요구한다.
        #
        #  ⚠️ 짐작이 *"질의가 있으면 팀은 들었다"* 로 `team` 을 늘 센다. 그대로
        #     두면 `Busch Stadium October 4 2026` 이 **team+when+venue = 3** 으로
        #     통과한다 — 🔴 사용자가 막으라고 한 바로 그 질의다
        #     (*"`Busch Stadium` 하나짜리가 다시 쓰레기를 끌고 오지 않는다"*).
        #  🔴 그래서 경기장을 셀 때는 **팀 이름이 실제로 보일 때만** 팀을 센다.
        said_team = [k for k in ("team", "opponent")
                     if str((parts or {}).get(k) or "").strip()
                     and _norm(str((parts or {}).get(k))) in low]
        if not said_team and "team" in got:
            got.remove("team")
    for sp in ("soccer", "baseball", "hockey"):
        words = [w for lang in ("en", "ko", "ja", "es", "zh", "mk", "hr", "sr")
                 if (w := rules.sport_word(sp, lang))]
        if any(_norm(w) in low for w in words):
            got.append("sport")
            break
    # 🔴 **선언을 더한다**(중복은 한 번만) — 칸마다 선언이 이긴다
    for k in said:
        if k not in got:
            got.append(k)
    # ⚠️ 짐작이 *"질의가 있으면 팀은 들었다"* 로 `team` 을 넣는다 — 선언이
    #    `team` 을 말하지 않아도 그것은 그대로 둔다(종전 동작이다).
    # ⚠️ `venue` 는 `PARTS` 에 없다(다섯을 안 늘렸다) — 뒤에 붙여 돌려준다
    names = [k for k in PARTS if k in got]
    # 🔴 `PARTS` 밖 이름도 **센다** — 수는 종전과 같고 이름만 정직해진다
    for extra in ("keyword", "venue"):
        if extra in got:
            names.append(extra)
    return len(names), names


#: 🔴🔴 **낱말 상한** — 딥서치 재구축 §4-3 (M61).
#
#  > 10단어 초과 → `query_too_long` 거부. 실측: **긴 문장 질의가 0건을 만들었다.**
#
#  ⚠️ `query_too_bare`(3요소 미만)와 **반대 방향**이다 — 하나는 너무 넓고
#     하나는 너무 좁다. 🔴 둘을 한 사유로 묶으면 고칠 곳을 못 가린다.
MAX_WORDS = 10


def too_long(query: str) -> tuple[bool, str]:
    """🔴 그 질의가 **너무 긴가**. `(길다, 사유)`."""
    n = len(str(query or "").split())
    if n <= MAX_WORDS:
        return False, f"낱말 {n}개 — 상한 {MAX_WORDS} 안이다"
    return True, (f"🔴 `{Reason.QUERY_TOO_LONG.value}` — 낱말이 **{n}개**다"
                  f"(상한 {MAX_WORDS}). 긴 문장 질의는 결과를 0건으로 만든다"
                  f"(실측 2026-10-05). ⚠️ 넓게 시작해 판을 본 뒤 좁혀라")


def enough_parts(query: str, *, parts: dict | None = None,
                 kind: str = "") -> tuple[bool, str]:
    """🔴 §4-1 — 세 요소 이상인가. `(통과, 사유)`.

    ⚠️ `kind` 는 결정 ⑥ 의 **조건**이다 — 경기장은 그 유형에서만 센다.
    """
    n, got = count_parts(query, parts=parts, kind=kind)
    if n >= MIN_PARTS:
        return True, f"요소 {n}개({got})"
    return False, (
        f"🔴 `{Reason.QUERY_TOO_BARE.value}` — 요소가 **{n}개**다({got}). "
        f"§4-1 은 {MIN_PARTS}개 이상을 요구한다(팀·상대·대회·종목 낱말·날짜 중). "
        f"이름 하나짜리 질의는 드라마 출연진과 럭비를 끌어온다"
        f"(실측 2026-10-04: 쓰레기 86%)")


def gate(query: str, *, parts: dict | None = None, kind: str = "",
         seed: bool = False) -> tuple[bool, Reason, str]:
    """🔴 §4-1 문지기. `(통과, 사유 enum, 설명)`.

    🔴 **길이를 먼저 본다**(M61) — 요소가 많아도 길면 0건이다. 그 순서가
       사유를 정하고, 사유가 **고칠 곳**을 가리킨다.
    ⚠️ `seed=True` 는 §2 표의 **씨앗 템플릿**이다 — 3~6낱말로 넓게 시작하는
       것이 목적이므로 **요소 검사를 면제**한다(지시서 §4-3: *"씨앗 템플릿은
       자동 통과"*). 🔴 길이 검사는 **면제되지 않는다**(씨앗은 애초에 짧다).
    """
    long_, why_long = too_long(query)
    if long_:
        return False, Reason.QUERY_TOO_LONG, why_long
    if seed:
        n = len(str(query or "").split())
        return True, Reason.OK, (f"씨앗 템플릿({n}낱말) — §2 표 그대로이므로 "
                                 f"요소 검사를 면제한다(§4-3)")
    ok, why = enough_parts(query, parts=parts, kind=kind)
    return (True, Reason.OK, why) if ok else (False, Reason.QUERY_TOO_BARE, why)


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
        ok, reason, why = gate(query, parts=parts, kind=kind, seed=seed)
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
