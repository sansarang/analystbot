"""🔴🔴 **v6 s3 — 문서 수집.** `MatchRef, Facts → list[Doc]`(§5).

지시서 §5 s3 — 하위 하나의 흐름:

> 1. 질의 **2개를 코드가** 만든다: `{team} {opp} {word}`(영어) + 같은 꼴 현지어.
>    `{word}` 는 `search_words.yaml` 의 개념 낱말(**유형 이름 금지**), `{team}` 은
>    영어 짧은 표기, 어깻점 등 문지기 금지 문자는 값에서 제거.
> 2. **문지기 하나**를 통과한 질의만 SearXNG(`time_range=week`), 결과 5건 미만이면
>    Bing RSS. GDELT 는 경기당 상한 안에서.
> 3. 도메인 등급 → 신원 선필터 → 날짜 힌트 → 재정렬 → **상위 3건** fetch →
>    htmldate → `Doc`. 발행일이 킥오프 **7일 밖**이면 `Doc` 을 만들지 않는다(`stale`).
> 4. 같은 URL 은 **경기 단위 캐시**에서 한 번만 받고, 캐시는 `Doc` **통째로**
>    저장한다(본문만 저장하는 경로 없음).

⚠️ 실사고 2026-10-06 이 여기 다 들어 있다: 유형 이름을 질의에 넣어 *"Overdrive
   라디오 프로그램"* 문단을 받았고, 상위 3건이 전부 못 열리면 **문서 0건**이 됐고,
   본문과 날짜를 따로 저장해 `date_missing` 20건이 났다.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

from app.core import adapt
from app.core.schema import Doc, DropReason, Facts, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **이 파일에는 `run` 이 없다** — 사용자 지시 2026-10-17 *"딥서치 삭제"*
# ══════════════════════════════════════════════════════════════════════
#
#  🔴 여기 남은 것은 **몸통과 검문**이다 — 던지고(`_candidates`) 받고(`_fetch`)
#     걸러낸다(`grade_ok`·`identity_ok`·`sport_ok`·`gate_ok`·`names_of`).
#     질의를 **만들지 않는다** — 그것은 `s4b_gapsearch.ask`(LLM) 하나다.
#  🔴 입구는 `gap_docs` 다(`s4b_gapsearch.harvest` 가 부른다).
#  ⚠️ 그래서 단계 계약(`run` 이 하나다)에게 **입구를 글자로** 알린다.
STAGES = ("gap_docs",)

#: 🔴 발행일 창 — 킥오프 **7일 전**까지. ⚠️ 수는 `s5_verify.DATE_WINDOW_DAYS` 가
#   원본이다(사본 금지) — 여기서 다시 정하지 않는다.
def _window_days() -> int:
    from app.core.stages import s5_verify
    return int(s5_verify.DATE_WINDOW_DAYS)


#: 🔴 그 실행의 **칸별 계수기**. ⚠️ 모듈 전역이지만 `run` 이 **끝에서 비운다** —
#   병렬 하위 8개가 같은 실행 안에 있으므로 실행 사이에 섞이지 않는다.
#   🔴 실행 상태는 `RunState` 가 든다(§2) — 이것은 그 칸을 **모으는 임시 자리**다.
_TALLY: dict[str, int] = {}


def _count(stage: str, n: int = 1) -> None:
    _TALLY[stage] = _TALLY.get(stage, 0) + int(n)


def _window_of(sub: Any) -> timedelta:
    """🔴🔴 그 하위의 **발행일 창** — 사용자 지시 2026-10-10(재작성) §3-1.

    > 하위 과제 **F** … 킥오프 기준 **72시간 안**.

    🔴 수는 `config/subtask_groups.yaml` 의 `window_hours:` 가 든다(사본 금지).
    ⚠️ 없으면 기본 창(`s5_verify.DATE_WINDOW_DAYS` 7일)이다 — 다른 하위는 그대로다.
    """
    said = int(getattr(sub, "window_hours", 0) or 0)
    return timedelta(hours=said) if said > 0 else timedelta(days=_window_days())


def _sub_cfg() -> dict:
    from app.core.llm import cfg
    return dict((cfg().get("budget") or {}).get("per_subtask") or {})


def _shorter(name: str) -> list[str]:
    """🔴 그 팀의 **현지·짧은 표기들** — 질의 글자에서 상대를 뺄 때 쓴다.

    ⚠️ 이름을 **짓지 않는다** — 이름표가 아는 것만(`discover.aliases_of`).
    """
    if not str(name or "").strip():
        return []
    try:
        from app.core import discover as _d
        got = [str(x) for x in _d.aliases_of(name) if str(x).strip()]
    except Exception:                                       # noqa: BLE001
        return []
    return sorted(got, key=lambda x: -len(x))


def _fit(out: list[tuple[str, str]], *, mine: str, other: str = "",
         ) -> list[tuple[str, str]]:
    """🔴🔴 **문지기(1~6낱말)를 넘는 질의는 한 팀 질의로 떨어뜨린다.**

    ══════════════════════════════════════════════════════════════════
    🔴 왜 — 실사고 2026-10-11 (뉴잉글랜드 vs 시애틀 사운더스)
    ══════════════════════════════════════════════════════════════════

    팀 이름이 `New England Revolution`(3낱말) · `Seattle Sounders FC`(3낱말)이라
    두 팀 + 개념어가 **7~8낱말**이 됐고, `gate_ok`(1~6낱말)가 **질의를 전부**
    막았다 → 검색 0회 · 문서 0건 · 새 사실 0건. ⚠️ 그런데 카드에는
    `queries None` 만 남아 *"안 쟀다"* 처럼 보였다(#3 조용한 0).

    🔴 이름을 **지어 줄이지 않는다** — 상대를 빼고 **내 팀 + 개념**으로 묻는다
    (`squad_turnover` 가 이미 쓰는 꼴이다 · 하위가 홈/원정 두 벌이라 두 팀이 다
    덮인다). ⚠️ 그래도 넘으면 그대로 두고 문지기가 사유를 적는다.
    """
    from app import queries
    got: list[tuple[str, str]] = []
    for q, lg in out:
        said = str(q).strip()
        if not said:
            continue
        if not gate_ok(said)[0]:
            # 🔴 **상대 이름만 뺀다** — 개념어는 두 낱말일 수 있다
            #    (`injury news`). ⚠️ 끝 낱말만 남기면 `news` 로 **잘린다**.
            solo = said
            for name in (str(other or ""), *_shorter(other)):
                if name and name in solo:
                    solo = solo.replace(name, " ")
                    break
            solo = " ".join(solo.split())
            if solo and solo != said and gate_ok(solo)[0]:
                said = solo
        got.append((queries.slot_value(said), lg))
    return got


def names_of(ref: MatchRef) -> tuple[list[str], list[str]]:
    """🔴 두 팀을 가리키는 **모든 이름** — 신원 선필터가 이것으로 본다.

    ⚠️ 인자는 **열쇠**다(§8-1) — 이름을 받으면 또 하나의 해석 지점이 된다.
    """
    # 🔴 **출처가 실제로 쓴 이름도 넣는다** — 열쇠의 이름만 보면 그 경기 페이지가
    #    쓴 표기를 버린다(⚠️ 열쇠가 어긋났을 때 그 사실이 조용히 묻힌다).
    home = [n for n in (*adapt.names_of_key(ref.home), ref.home_name) if n]
    away = [n for n in (*adapt.names_of_key(ref.away), ref.away_name) if n]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **한글 보탬**(사용자 지시 2026-10-11 ②) — 영어 표기만으로 판정 금지
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-11(광주–울산): 원정 열쇠가 **이름 없는 임시 열쇠**여서
    #     쓸 이름이 `Ulsan HD FC` 한 글자뿐이었다 — 한글 기사가 통과할 길이
    #     없었다(`identity_mismatch` 7건 · 문서 0건). 열쇠 갈림은 `teamref` 가
    #     고쳤고, 그래도 **표에 없는 약칭**은 이 표가 더한다.
    #  🔴 원본은 `config/names_ko.yaml` 하나다(`rules.ko_of` 가 읽는다).
    from app import rules as _rules
    for box, side in ((home, ref.home_name), (away, ref.away_name)):
        for nm in list(box):
            box.extend(_rules.ko_of(nm))
        box.extend(_rules.ko_of(str(side or "")))
    # ⚠️ 🔴 **짧은 이름은 여기서 더하지 않는다** — 이 목록은 본문 검사
    #    (`verify.ended_this_match`)도 쓴다. 실사고 2026-10-11: 짧은 토막을 여기
    #    넣자 그 검사가 멀쩡한 기사를 *"끝난 경기"* 로 읽어 **기사 변수가 0개**가
    #    됐다(e2e 불변식17 이 잡았다). 🔴 짧은 이름은 **신원 선필터만** 쓴다
    #    (`identity_ok` 가 그 자리에서 더한다).
    return (list(dict.fromkeys(x for x in home if x)),
            list(dict.fromkeys(x for x in away if x)))


#: 🔴🔴 **짧은 이름에 쓰지 않는 흔한 낱말**(사용자 지시 2026-10-11 1번)
#
#  ⚠️ `United`·`City`·`Real` 같은 토막을 넣으면 **남의 경기 기사**가 통과한다 —
#     그것이 *"남의 경기를 분석하는"* 길이다(§8-1 의 그 위험).
#  🔴 늘릴 때는 **실측으로 걸린 것만** 더한다(추측해 늘리지 않는다).
SHORT_SKIP: frozenset[str] = frozenset({
    "fc", "sc", "afc", "cf", "ac", "sk", "bk", "cd", "ud", "rc", "ss", "fk",
    "if", "sv", "club", "calcio", "united", "city", "town", "real", "royal",
    "sporting", "athletic", "atletico", "dynamo", "deportivo", "olympique",
    "new", "york", "los", "angeles", "san", "sankt", "saint", "west", "east",
    "north", "south", "fussball", "football", "soccer", "sports", "sport",
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대표팀 꼬리말과 나라 조각**(실사고 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 재생 고정물(South Korea vs Uzbekistan)에서 `South Korea` → **`Korea`**,
    #     한글 별칭에서 **`대표팀`** 이 나왔다. 그 둘이 남의 글을 들여보내 **기사
    #     변수가 0개**가 됐다(e2e 불변식17·2 가 잡았다).
    #  🔴 나라 이름의 **한 조각**(`Korea`)은 다른 나라 기사(북한·여자대표팀 …)와
    #     겹친다 — 짧은 이름으로 쓰지 않는다.
    "korea", "대표팀", "국가대표", "협회", "리그", "클럽", "축구",
    "republic", "islands", "island", "states", "arab", "emirates",
})
#: 🔴 라틴 토막은 이만큼은 돼야 쓴다(짧은 토막은 아무 글에나 걸린다)
SHORT_MIN = 4


def short_forms(names: list[str]) -> list[str]:
    """🔴🔴 1번 — 긴 이름에서 **짧은 이름**(도시 토막)을 뽑는다.

    ⚠️ 실측 2026-10-11(손실 표): `Kawasaki vs. Nagoya (Oct 11, 2026) Live Score
       - ESPN` 이 `identity_mismatch` 로 버려졌다 — **두 팀 이름이 다 있는데**
       우리가 아는 이름은 `Kawasaki Frontale`·`Nagoya Grampus` 뿐이었다.

    🔴 뽑는 것은 **여러 낱말 이름의 첫·끝 토막**이다(도시가 앞에도 뒤에도 온다:
       `Kawasaki Frontale` ↔ `Albirex Niigata`). ⚠️ `SHORT_SKIP` 의 흔한 낱말과
       `SHORT_MIN` 미만 토막은 **넣지 않는다**. 한 낱말 이름은 이미 그 자체로
       쓰이므로 더하지 않는다.
    """
    out: list[str] = []
    for nm in (names or []):
        toks = [t for t in re.split(r"[\s·.\-]+", str(nm or "")) if t]
        if len(toks) < 2:
            continue
        for tok in (toks[0], toks[-1]):
            low = tok.lower().strip(".")
            if low in SHORT_SKIP:
                continue
            if _CJK.search(tok):
                if len(tok) >= 2:
                    out.append(tok)
                continue
            if len(low) >= SHORT_MIN:
                out.append(tok)
    return list(dict.fromkeys(out))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **연령·성별 등급 검사** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Obolon Kyiv vs Veres Rivne · 시니어 리그): 문서
#     `Zhytomyr **U19** vs Veres Rivne **U19** Highlights` 가 신원 검사를
#     **통과했다**(이름이 품는다: `Veres Rivne` ⊂ `Veres Rivne U19`).
#     그 글에서 `R1 venue_weather`·`R2 event_match`·`R3 match_type`
#     ("The contest is a **U19 League** match") 가 나왔고, `R3` 은
#     **λ 상수 자리까지** 갔다. 두 평이 *"U19 로 잡혀 있어 전제와 안 맞는다"*
#     고 **스스로 지적**했다.
#  🔴 그래서 이름이 걸려도 **등급이 다르면 버린다** — 우리 경기에 그 표가
#     없는데 글에만 있으면 **다른 경기**다.
#  ⚠️ 반대쪽도 본다 — 우리 경기가 U19·여자면 **그 글만** 받는다.

#: 🔴 등급 표식 — **낱말 경계**로 본다(아래 머리말)
#   ⚠️ 실측 2026-10-16: 처음에 `" w "` 를 넣었더니 *"Korea Republic **w**
#      Uzbekistan preview"* 같은 **멀쩡한 제목**이 떨어졌다(재현에서 기사 변수가
#      5개 → 1개로 줄었다). 🔴 애매한 표식은 **안 쓴다** — 거짓 양성이 더 비싸다.
_GRADE = __import__("re").compile(
    r"\b(u-?1[5-9]|u-?2[0-3]|youth|junior|primavera|reserves?|women|female|"
    r"feminin[ae]?|femenin[oa]?|frauen)\b|유스|청소년|리저브|여자|여성|"
    r"(?<![가-힣])2군(?![가-힣])", __import__("re").I)


def _grade_of(said: str) -> set[str]:
    """🔴 그 글자가 든 **등급 표식**(없으면 빈 집합 = 시니어 남자).

    🔴 낱말 경계로 본다 — `U19`·`U-19`·`Women`·`여자`·`유스`·`2군`.
    ⚠️ 한 글자 표식(`w`)은 **쓰지 않는다**(위 머리말의 그 거짓 양성).
    """
    return {m.group(0).lower() for m in _GRADE.finditer(str(said or ""))}


def grade_ok(title: str, snippet: str, ref_words: str) -> tuple[bool, str]:
    """🔴🔴 **등급이 같나** — `(맞나, 사유)`. 우리 경기 글자와 대본다.

    ⚠️ **제목만** 본다 — 스니펫에는 사이트 차림표(`여자부`·`U-18`)가 섞여
       멀쩡한 기사가 떨어진다(실측 2026-10-16).
    """
    mine, theirs = _grade_of(ref_words), _grade_of(title)
    if mine == theirs:
        return True, ""
    if theirs - mine:
        return False, (f"🔴 **등급이 다르다** — 글은 "
                       f"{sorted(theirs - mine)} 인데 이 경기는 아니다")
    return False, (f"🔴 **등급이 다르다** — 이 경기는 {sorted(mine - theirs)} "
                   f"인데 글은 아니다")


def identity_ok(title: str, snippet: str, names: tuple[list[str], list[str]]
                ) -> tuple[bool, str]:
    """🔴🔴 **신원 선필터**(§5 s3-3) — 제목·스니펫이 **두 팀 중 하나라도** 말하나.

    ⚠️ 이 이름의 부품이 **한 함수로 존재하지 않았다**(실측 2026-10-06: `app/` 에
       `신원 선필터` 가 없다 — `findgame._mentions` 가 비슷한 일을 하지만 그쪽은
       경기 페이지 전용이다). 🔴 그래서 여기 짓고 그 사실을 적는다.
    🔴 **두 팀 다**가 아니라 **하나라도**다 — 결장 기사는 한 팀만 말한다.
    ⚠️ 그래도 이 검사가 실측에서 쓰레기를 걸렀다: `gulf-times.com/tag?query=AFC`
       (태그 목록) · `ch.atomy.com/...`(쇼핑) · `goal.com/kr/뉴스`(뉴스 목록).
    """
    said = f"{title} {snippet}".lower()
    if not said.strip():
        return False, "🔴 제목·스니펫이 비었다 — 신원을 볼 글이 없다"
    # 🔴 1번 — **짧은 이름을 여기서만 더한다**(도시 토막 · 흔한 낱말은 뺀다).
    #    ⚠️ 실측: `Kawasaki vs. Nagoya … - ESPN` 이 두 팀을 다 말하는데 버려졌다.
    names = tuple([*side, *short_forms(list(side))] for side in names)
    for side in names:
        for n in side:
            got = str(n or "").strip().lower()
            if len(got) >= _min_len(got) and got in said:
                return True, f"신원 ✅ `{n}`"
    return False, (f"🔴 제목·스니펫에 **두 팀 어느 이름도 없다** — "
                   f"{said[:60]!r}")


#: 🔴 한글·한자·가나는 **두 글자면 구체적**이다 — 로마자는 세 글자가 필요하다
_CJK = re.compile(r"[가-힣ぁ-んァ-ヴー一-龥]")


def _min_len(said: str) -> int:
    """🔴🔴 신원 검사의 **최소 글자 수** — 글자 종류에 따라 다르다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 실사고 2026-10-10 — **한국 기사가 전부 떨어졌다**
    ══════════════════════════════════════════════════════════════════

    강원–부천 실행에서 `identity_mismatch` **178건**이 났고 문서가 **1건**이었다.
    한국어 질의는 제대로 나갔는데(`강원 부천 결장` → 8건) 그 기사들이 전부
    신원 검사에서 떨어졌다 — 🔴 이름표가 `강원`·`부천` 을 **알고 있었는데**
    이 검사가 `len >= 3` 을 요구했고 그 둘은 **두 글자**다.

    🔴 그래서 **글자 종류로** 가른다: 한글·한자·가나는 2, 로마자는 3.
    ⚠️ 왜 로마자는 3인가 — 두 글자 로마자(`AC`·`FC`)는 아무 글에나 걸린다.
       한글 두 글자(`강원`)는 그렇지 않다(음절이 정보를 더 들고 있다).
    """
    return 2 if _CJK.search(str(said or "")) else 3


def sport_ok(sport: str, title: str, body: str, *,
             comp: tuple | list = ()) -> tuple[bool, str]:
    """🔴🔴 **종목 검사**(사용자 지시 2026-10-06 ②) — 그 종목 낱말이 본문에 있나.

    > `Doc` 단계에서 그 종목 낱말(축구/football/fútbol 등, `search_words.yaml`)이
    > 본문에 없으면 버린다.

    ⚠️ 실측 2026-10-06: 권순우 **테니스** 기사(아시안게임 단식)가 결장 변수 둘로
       들어왔다 — 기사에 `한국`·`우즈베키스탄`이 둘 다 있어 **신원 선필터를
       통과했다**. 🔴 신원은 *"누구 이야기인가"* 고 이것은 *"무슨 종목인가"* 다.
    🔴 낱말 목록은 `search_words.yaml` 의 `words.sport` 하나다(사본 금지).
    ⚠️ 목록이 **비면 거르지 않는다** — 선언이 없는 종목에서 전부 버리면 그 종목이
       통째로 0건이 된다(그 사실을 사유로 남긴다).
    """
    from app import rules
    words = rules.sport_words(sport)
    if not words:
        return True, f"🔴 `{sport}` 종목 낱말이 표에 없다 — 거르지 않았다"
    said = f"{title}\n{body}".lower()
    for w in words:
        if str(w).lower() in said:
            return True, f"종목 ✅ `{w}`"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대회 이름도 종목의 증거다**(실사고 2026-10-10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 강원–부천 실행에서 한국 기사 **18건**이 종목 검사에서 떨어졌다. 그
    #     기사들은 `축구` 를 안 쓰고 **`K리그1 31라운드`** 라고 적는다 — 매체는
    #     독자가 아는 것을 되풀이하지 않는다.
    #  🔴 그 글이 **그 대회**를 말하고 있으면 종목은 이미 정해진다. 그래서 대회
    #     이름(과 그 현지 표기)을 증거로 받는다.
    #  ⚠️ 두 글자 미만은 받지 않는다 — 아무 글에나 걸린다.
    for one in (comp or ()):
        got = str(one or "").strip().lower()
        if len(got) >= 2 and got in said:
            return True, f"종목 ✅ 대회 이름 `{one}`(종목 낱말은 없다)"
    return False, (f"🔴 본문에 **{sport} 낱말이 없다**({', '.join(words[:4])} …) — "
                   f"남의 종목 기사다")


def comp_names(ref: MatchRef) -> list[str]:
    """🔴 그 대회를 가리키는 **이름들**(현지 표기 포함) — 종목 검사의 둘째 증거.

    🔴 이름은 **표가 든다**(사본 금지): `config/competitions.yaml` 의 `names` 와
       `app/league_index.py` 의 리그 이름. ⚠️ 여기서 짓지 않는다.
    """
    out = [str(ref.competition or ""), str(ref.competition_short or "")]
    try:
        from app.core import competition as _c
        key, _why = _c.key_of(competition=str(ref.competition or ""))
        row = _c.row_of(key) if key else {}
        out += [str(x) for x in (row.get("names") or [])]
        out.append(_c.short_key(key))
    except Exception:                                       # noqa: BLE001
        pass
    return [x for x in dict.fromkeys(out) if str(x or "").strip()]


def gate_ok(said: str) -> tuple[bool, str]:
    """🔴 ② **문지기 하나.** ⚠️ 두 번째 정의를 만들지 않는다(§9).

    🔴 `llm.query_ok`(1~6낱말 · 연산자·연도 금지)가 **더 센 쪽**이고 카탈로그
       질의를 실제로 거르던 쪽이다 — §6 이 *"남길 쪽 기준: 오픈월드 ⑥-2 와 s3 질의
       모두 통과시키는 쪽"* 이라 했으므로 그 하나로 모은다.
    """
    from app import llm as _llm
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **`site:` 는 알맹이를 본다** — 실사고 2026-10-17(우라와 두 번째)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 매체 표를 붙이고 robots 까지 확인했는데 **`site:` 질의가 한 건도 안
    #     던져졌다**. §12-b 가 *"사이트 연산자 금지"* 라서 문지기가 **전부**
    #     버렸다(`site:soccer-king.jp 浦和レッズ 先発予想` → 막힘).
    #  🔴 그런데 ⑤-b3 2단은 **같은 꼴을 던지고 있었다** — 거기서는 문지기를
    #     **먼저** 통과시키고 `site:` 를 **그 뒤에** 붙인다
    #     (`branchjudge:591` → `:659`). 즉 §12-b 가 막으려던 것은 **모델이
    #     지어낸 연산자**이고, **확인된 매체로 좁히는 것**은 이미 허용된 길이다
    #     (사용자 지시 2026-10-17 ① *"현지어 매체를 `site:` 로 · robots 확인
    #     뒤에만"*).
    #  🔴 그래서 **규칙을 걷지 않고 순서만 맞춘다** — 접두 `site:<호스트>` 를
    #     떼고 **남은 알맹이**를 §12-b 로 잰다(낱말 수·따옴표·마이너스·연도는
    #     그대로 걸린다). ⚠️ 호스트 꼴은 `querywriter.hosts` 가 본다(사본 금지).
    said_in = str(said or "").strip()
    head, _sp, rest = said_in.partition(" ")
    if head.lower().startswith("site:") and rest.strip():
        from app.core import querywriter as _qw
        got, _bad = _qw.hosts([head.split(":", 1)[1]])
        if len(got) == 1:
            ok, why = gate_ok(rest)
            return ok, (f"{why} · `site:{got[0]}` 로 좁혔다" if ok else why)
    n = len(str(said or "").split())
    if _llm.query_ok(said):
        return True, f"낱말 {n}개"
    return False, (f"🔴 문지기가 막는다(낱말 {n}개 · 1~6 · 연산자·연도 금지): "
                   f"{said!r}")


#: 🔴🔴 **그 실행 안에서 던진 질의** — `{(낱말 집합, 언어): Future[결과]}`.
#
#  🔴 **결과가 아니라 약속을 담는다** — 하위가 동시에 돌아 둘이 같은 순간에
#     캐시를 보기 때문이다(결과만 담으면 둘 다 놓치고 두 번 던진다 · 실측).
#  ⚠️ 실행마다 비운다(`run` 이 비운다) — 남겨 두면 어제 결과가 오늘 카드에 섞인다.
_SEEN: dict[tuple, asyncio.Future] = {}


async def gap_docs(ref: MatchRef, *, state: RunState, chain: Any, net: Any,
                   cache: dict | None, queries: list[tuple[str, str]],
                   sub: Any, tag: str = "gap") -> list[Doc]:
    """🔴🔴 **LLM 표적 질의 → 문서** — 사용자 지시 2026-10-14.

    > 경기 정보를 **llm 서치**하고 llm 결과를 **변수에 넣어야 한다**

    🔴 `run` 이 쓰는 그 둘(`_candidates`·`_fetch`)을 **그대로** 부른다 — 도메인
       등급·신원·날짜·재정렬·본문 받기가 전부 같은 길을 지난다(사본 금지).
    ⚠️ 그래서 표적 검색 문서도 **1차와 같은 검문**을 받는다: 남의 경기 글은
       신원에서 떨어지고, 7일 밖은 날짜에서 떨어진다.
    🔴 `queries` 는 `[(질의, 언어)]` 다 — 언어를 **질의마다** 준다(현지어 우선).
    ⚠️ `sub` 는 **부르는 쪽이 만든다** — 어느 하위 묶음의 유형으로 추출할지가
       그 객체에 들어 있다(그 유형이 변수의 `type` 이 된다).
    """
    rows = await _candidates(sub, ref, state=state, chain=chain,
                             queries=list(queries or []), tag=tag)
    if not rows:
        state.note(f"s3/{tag} — 표적 질의가 **지나간 문서 0건**"
                   "(신원·날짜·도메인에서 다 떨어졌다)")
        return []
    # 🔴🔴 **상위 몇 건을 열까 — 표가 정한다**(사용자 지시 2026-10-17)
    #    ⚠️ 종전엔 **질의 수**였다(질의 1개당 1건). 질의가 3개면 받기도 3건이라
    #       날짜를 통과한 **42건 중 4건**만 열었다(실측: 울산 HD vs 부천 4차).
    #    🔴 수는 `config/llm.yaml` 의 `budget.harvest.fetch_per_side` 다.
    from app.core.stages.s4b_gapsearch import fetch_per_side as _fps
    got = await _fetch(sub, ref, rows, state=state, net=net,
                       cache=dict(cache if cache is not None else {}),
                       claimed=set(cache or {}), tag=tag,
                       top=max(1, _fps()))
    state.note(f"s3/{tag} — 표적 질의 {len(queries)}개 → 후보 {len(rows)} → "
               f"문서 **{len(got)}건**")
    return got


def _sid(sub: Any) -> str:
    """🔴 `A-홈` → `A-home` — `SubtaskId` 열거값이 원본이다."""
    name = str(getattr(sub, "name", ""))
    group = name.split("-")[0] if "-" in name else name
    side = "home" if name.endswith("홈") else "away"
    return f"{group}-{side}"


async def _candidates(sub: Any, ref: MatchRef, *, state: RunState,
                      chain: Any,
                      queries: list[tuple[str, str]],
                      tag: str = "") -> list[tuple[Any, str]]:
    """🔴 ①~③ **찾기만** — 검색 → 도메인 등급 → 신원 → 날짜 힌트 → 재정렬.

    ⚠️ 여기서는 **아무것도 받지 않는다**(fetch 0회) — 받기는 `_fetch` 가 한다.
    🔴🔴 **`queries` 는 이제 반드시 받는다** — 사용자 지시 2026-10-17
       (*"딥서치 삭제"*). 종전에는 비우면 `queries_for`(코드 질의 다발)로
       떨어졌고 그것이 딥서치였다. ⚠️ 질의를 만드는 곳은 **LLM 뿐**이다
       (`s4b_gapsearch.ask`) — 기본값을 두면 지운 길이 조용히 되살아난다.
    """
    from app import datehint, domains
    from app.core import rank
    from app.research import lead
    name = (tag or str(getattr(sub, "name", "?")))
    hits: list[Any] = []
    if not queries:
        state.note(f"s3/{name} — ⬜ **질의 0개**(LLM 서치가 안 냈다 · 딥서치는 "
                   "지웠다)")
        return []
    for q, lang in queries:
        if not sub.budget.may_search():
            state.note(f"s3/{name} 검색 상한({sub.budget.search_cap})에 닿았다")
            break
        ok, why = gate_ok(q)
        if not ok:
            state.note(f"s3/{name} {why}")
            continue
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **같은 질의를 두 번 던지지 않는다** — 실사고 2026-10-10
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 하위가 **홈/원정 두 벌**이라 질의가 **거울로 겹친다**:
        #     `김천 안양 복귀` ↔ `안양 김천 복귀` — 같은 검색이다.
        #  🔴 김천–안양 실행에서 26회 중 **한국어 질의 11회가 0건**이었고, 그 0은
        #     엔진이 죽은 것이 아니라 **우리 버스트가 만든 일시 정지**였다
        #     (`naver: access denied` — 직후 다시 재니 15건이었다).
        #  🔴 그래서 **낱말 집합이 같은 질의는 한 번만** 던지고 결과를 나눠 쓴다.
        #     ⚠️ 예산(`search_used`)도 그만큼 안 쓴다 — 아낀 몫이 다음 질의로 간다.
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **재생에서는 합치지 않는다** — 실사고 2026-10-10
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 합치면 **검색 예산이 남아** 전에 상한에 걸려 못 돌던 질의가 돈다 —
        #     라이브에는 이득이지만(수확이 늘어난다) **녹음은 그 질의를 모른다**.
        #     ⚠️ 실측: 고정물이 문서 8→6 · 변수 11→9 로 깎였다. 녹음은 지난
        #        경기라 다시 만들 수 없다.
        #  🔴 그래서 **재생일 때만 끈다** — 라이브 동작은 그대로 둔다.
        key = (" ".join(sorted(str(q).lower().split())), str(lang))
        if _replaying():
            key = (key[0], key[1], str(getattr(sub, "name", "")))
        waiting = _SEEN.get(key)
        if waiting is not None:
            # 🔴🔴 **진행 중이면 기다린다** — 하위가 **동시에** 돌기 때문이다.
            #    ⚠️ 실사고 2026-10-10: 결과만 캐시했더니 둘이 **동시에 캐시를
            #       보고** 둘 다 놓쳐 거울 질의가 그대로 두 번 나갔다(걸린 수 0).
            #    🔴 그래서 **약속(Future)을 캐시**한다 — 둘째는 첫째를 기다린다.
            try:
                got = list(await waiting)
            except Exception:                               # noqa: BLE001
                got = []
            state.note(f"s3/{name} 질의 {q!r} — **같은 검색을 이미 했다**"
                       f"(결과 {len(got)}건을 나눠 쓴다 · 호출 0)")
            logger.info("[s3] 같은 검색을 나눠 썼다 — %r → %d건", q, len(got))
            hits += got
            continue
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        _SEEN[key] = fut
        sub.budget.search_used += 1
        _count("queries")
        try:
            async with lead.gate("searx"):
                got = await chain.query(q, lang=lang)
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s3/{name} 검색 실패 {q!r}: {exc}")
            if not fut.done():
                fut.set_result([])
            continue
        if not fut.done():
            fut.set_result(list(got or []))
        state.note(f"s3/{name} 질의 {q!r}({lang}) → {len(got or [])}건")
        _count("hits", len(got or []))
        hits += list(got or [])
    # ── ③ 거르기: 도메인 등급 → 날짜 힌트
    who = names_of(ref)
    kept: list[Any] = []
    seen_url: set[str] = set()
    for h in hits:
        url = str(getattr(h, "url", "") or "")
        if not url or url in seen_url:
            continue
        seen_url.add(url)
        ok_d, tier, said = domains.verdict(url, sport=ref.sport)
        if not ok_d:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.TYPE_OFF_CATALOG,
                       f"도메인 등급 — {said[:70]}", stage="s3/도메인",
                       title=str(getattr(h, "title", "") or "")[:70])
            continue
        # 🔴 **신원 선필터**(§5 s3-3) — 두 팀 어느 이름도 없으면 남의 글이다
        said_t = str(getattr(h, "title", "") or "")
        ok_i, said_i = identity_ok(said_t,
                                   str(getattr(h, "snippet", "") or ""), who)
        if not ok_i:
            # 🔴 ② — **제목을 함께 남긴다**(손실 감사가 그 글이 무엇이었나를 본다)
            state.drop(f"s3/{name}/{url[:40]}", DropReason.IDENTITY_MISMATCH,
                       said_i[:90], stage="s3/신원", title=said_t[:70])
            continue
        # 🔴🔴 **등급 검사**(`grade_ok` 머리말 · 사용자 지시 2026-10-16) —
        #    이름이 걸려도 **U19·여자 글이면 다른 경기**다.
        ok_g, said_g = grade_ok(
            said_t, str(getattr(h, "snippet", "") or ""),
            f"{ref.home_name} {ref.away_name} {ref.competition}")
        if not ok_g:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.IDENTITY_MISMATCH,
                       said_g[:90], stage="s3/등급", title=said_t[:70])
            continue
        old, said_old = datehint.too_old(url, str(getattr(h, "snippet", "")
                                                 or ""))
        if old:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.STALE,
                       said_old[:80], stage="s3/날짜", title=said_t[:70])
            continue
        _count("kept_date")
        kept.append((h, str(tier)))
    # ── ③ 재정렬 1단. 🔴 **녹음·재생을 거친다**(`rank`) — 재생에 모델이 없다
    if kept:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **재정렬 질의에 자연어와 현지어를 넣는다**(실사고 2026-10-10)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전 질의는 **카탈로그 유형 이름**뿐이었다(`returning
        #     national_duty_return absence …`). 🔴 그것으로 **한국어·일본어 제목**을
        #     점수 내면 늘 낮다 — 좋은 미리보기가 상위 3건에 못 들어 받히지
        #     않았다(FC서울–제주: 문서 2건 · 🆕 0건).
        #  ⚠️ 그리고 `config/subtask_groups.yaml` 의 **`rerank_query`**(자연어)는
        #     **아무 데서도 안 쓰이고 있었다**(#2 안 이어진 설정).
        #  🔴 그래서 셋을 합친다: 유형 이름 + 표의 자연어 + **그 언어의 개념 낱말**.
        want = " ".join(adapt.catalog_type(str(k)) or str(k)
                        for k in (getattr(sub, "kinds", None) or ()))
        # 🔴 **`words:` 를 선언한 하위에만** 더한다(지금은 F 뿐이다).
        #    ⚠️ A~D 에도 더해 봤더니 **고정물의 순서가 바뀌어** 받는 문서가
        #       달라졌고 녹음이 빗나가 기사 변수가 0개가 됐다(2026-10-10).
        #       🔴 녹음은 지난 경기라 다시 만들 수 없다 — 그래서 **선언한 쪽만**
        #          바꾼다. A~D 는 §9 5단계에서 같은 모양으로 넓힌다.
        if getattr(sub, "words", None):
            want = " ".join(x for x in (
                want, str(getattr(sub, "rerank_query", "") or ""),
                " ".join(_concept_words(sub, ref))) if x)
        kept, said_r = rank.order_of(
            kept, lambda row: f"{getattr(row[0], 'title', '')} "
                              f"{getattr(row[0], 'snippet', '')}", want)
        state.note(f"s3/{name} 재정렬 — {said_r}")
    return kept


def _concept_words(sub: Any, ref: MatchRef) -> list[str]:
    """🔴 그 하위의 개념 낱말을 **그 경기 언어들로** — 재정렬이 현지 제목을 본다.

    🔴 언어는 `local_lang_of`(이름표·자동 등록·CLDR)가 정하고 낱말은
       `search_words.yaml` 이 든다(사본 금지). ⚠️ 여기서 짓지 않는다.
    """
    from app import rules
    from app.research import subtasks as _st
    lang = _st.local_lang_of(league=str(ref.competition or ""),
                             teams=(ref.home_name, ref.away_name))
    out: list[str] = []
    for one in (lang, "en"):
        if not one:
            continue
        for concept in (getattr(sub, "words", None) or ()):
            out += [str(x) for x in (rules.local_words(str(concept), one) or [])]
    return list(dict.fromkeys(out))[:12]


async def _fetch(sub: Any, ref: MatchRef, kept: list[tuple[Any, str]], *,
                 state: RunState, net: Any, cache: dict[str, Doc],
                 claimed: set[str] | None = None, tag: str = "",
                 start: int = 0, top: int | None = None) -> list[Doc]:
    """🔴 ③ **자리 잡고 상위 N건 받기.** 실패는 **다음 후보로 대체한다**.

    ⚠️ 이 함수는 `run` 이 **하위 순서대로** 부른다 — 그래야 같은 URL 을 누가
       가져가는지가 **타이밍으로 갈리지 않는다**(재생 조건).
    """
    from app import readtext
    from app.research import lead
    sid, name = _sid(sub), (tag or str(getattr(sub, "name", "?")))
    # 🔴 **자리를 잡은 URL** — 캐시와 따로 든다(캐시는 `Doc` 을, 이쪽은 **의도**를)
    claimed = claimed if claimed is not None else set(cache)
    # 🔴🔴 **상위 몇 건을 받나** — 기본은 설정이고, 부르는 쪽이 줄 수 있다.
    #    ⚠️ 설정값(3)은 하위가 **여덟**일 때의 값이다(8 × 3 = 24건). 딥서치를
    #       지워 하위가 **둘**이 되자 총량이 ¼ 이 됐고, e2e 고정물에서 문서가
    #       **5 → 1건**으로 줄었다(그래서 기사 변수가 0이 됐다).
    #    🔴 옛 구조는 **질의 1개당 받기 1건**이었다(질의 24 = 받기 24) —
    #       그 비율을 그대로 쓴다(수를 새로 고르는 것이 아니다).
    top = int(top if top is not None else (_sub_cfg().get("fetch_top") or 3))
    floor = ref.kickoff_utc - _window_of(sub)
    out: list[Doc] = []
    for h, tier in kept:
        if len(out) >= top:
            break
        url = str(getattr(h, "url", "") or "")
        if url in claimed:
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **같은 URL 은 목록에 한 번만** — §8 2단계 합격 조건
            # ══════════════════════════════════════════════════════
            #
            #  > Doc 마다 발행일 또는 사유, **같은 URL 중복 0**
            #
            #  ⚠️ 처음엔 캐시에서 **사본을 떠서** 하위마다 넣었다 — 그러면 같은
            #     URL 이 목록에 여러 번 들어간다(실측 2026-10-06: 2건).
            #  🔴 **건너뛰고 다음 후보로 간다.** 그 URL 의 내용은 이미 다른
            #     하위가 들고 있고, 이쪽은 **다른 문서**를 받는 것이 낫다
            #     (덮는 범위가 넓어진다). ⚠️ 그 사실을 사유로 남긴다(#3).
            state.note(f"s3/{name} 다른 하위가 이미 들고 있다 — 건너뛴다: "
                       f"{url[:60]}")
            continue
        if not sub.budget.may_fetch():
            state.note(f"s3/{name} 열기 상한({sub.budget.fetch_cap})에 닿았다 — "
                       f"받은 문서 {len(out)}건")
            break
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **받기 전에 자리를 잡는다** — 실측 2026-10-06(병렬 경합)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 하위 8개가 `asyncio.gather` 로 **동시에** 돈다. 캐시를 `await` 뒤에
        #     쓰면 둘이 같은 URL 을 **동시에 통과**해 목록에 두 번 들어간다
        #     (실측: 중복 2건 — §8 2단계 합격 조건은 0).
        #  🔴 `claimed.add` 를 **`await` 앞**에 둔다 — asyncio 는 한 스레드라
        #     그 사이에 다른 하위가 끼어들 수 없다.
        claimed.add(url)
        sub.budget.fetch_used += 1
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§6-3 본문 확보 — 칸 넷**(지시서 2026-10-13 밤 셋째)
        # ══════════════════════════════════════════════════════════════
        #
        #  원문 → **AMP** → **RSS** → **대체 경로**. 🔴 칸마다 사유를 적는다
        #  (**FT1**: 실패를 조용히 버리면 계약 실패). ⚠️ 종전에는 원문 하나로
        #  끝냈고, 4xx·자바스크립트 렌더 문서가 **통째로 사라졌다**.
        from app.core.search import fetch as _ft
        async with lead.gate("fetch"):
            body, when, said_rungs = await _ft.body_of(
                net, url, league=str(getattr(ref, "league", "") or ""),
                extract=readtext.extract)
        if not str(body or "").strip():
            state.drop(f"s3/{name}/{url[:40]}", DropReason.BODY_MISSING,
                       _ft.why_of(said_rungs)[:300])
            continue
        # 🔴 **어느 칸에서 왔나**를 남긴다(원문이 아니면 그 사실이 중요하다)
        said_won = next((r for r in said_rungs if r.get("ok")), {})
        if str(said_won.get("rung") or "원문") != "원문":
            state.note(f"s3/{name} 본문을 **{said_won.get('rung')}** 칸에서 "
                       f"받았다 — {said_won.get('why')}")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **포털 첫 화면은 문서로 안 센다** — 사용자 지시 2026-10-17
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-17(울산 HD vs 부천): 받아 온 본문 22건 중 **11건**이
        #     경로 없는 첫 화면이었다. 당일 날짜라 날짜를 통과하고 팀 이름이 떠
        #     있어 신원도 통과한 뒤, 추출에서 *"건진 것이 없다"* 가 됐다.
        #  🔴 판정은 **주소 꼴 하나**다 — 경로가 없거나(`host/`) 목록 화면
        #     (`/`, `/kr`, `/news` 같은 한 토막)이면 그 경기 글이 아니다.
        #     ⚠️ 글자(제목·본문)로 판정하지 않는다 — 첫 화면에도 팀 이름이 뜬다.
        ok_fp, said_fp = front_page(url)
        if ok_fp:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.FRONT_PAGE, said_fp)
            continue
        # 🔴 **종목 검사**(사용자 지시 2026-10-06 ②) — 받은 뒤 본문으로 본다
        #    ⚠️ 제목·스니펫만으로는 모자랐다(테니스 기사가 통과했다).
        ok_s, said_s = sport_ok(ref.sport, str(getattr(h, "title", "") or ""),
                                str(body), comp=comp_names(ref))
        if not ok_s:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.SPORT_MISMATCH,
                       said_s[:100])
            continue
        src = "htmldate" if when else "none"
        # 🔴 **문서 id 는 경기 안에서 하나다** — 하위마다 `D1` 로 겹치면
        #    `doc_ids` 로 본문을 되찾을 수 없다(불변식 2가 그것을 센다).
        #    ⚠️ 2차(좁히기)도 **이어서 번호를 붙인다** — `start` 가 없으면 2차가
        #       `D1` 부터 다시 매겨 1차와 **같은 id 두 개**가 생긴다.
        doc = adapt.doc_of(doc_id=f"{sid}-D{start + len(out) + 1}", url=url,
                           body=str(body),
                           subtask=sid,
                           title=str(getattr(h, "title", "") or ""),
                           lang=str(getattr(h, "lang", "") or "en"),
                           tier=tier, published_at=when, date_source=src)
        # 🔴 **킥오프 7일 밖이면 `Doc` 을 만들지 않는다**(§5 s3-3 · 사유 `stale`)
        if doc.published_at is not None and doc.published_at < floor:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.STALE,
                       f"발행일 {doc.published_at:%Y-%m-%d} · 창 "
                       f"{_window_days()}일")
            continue
        # 🔴🔴 **킥오프 전인데 최종 스코어를 적는 글은 버린다**(§6 · 2026-10-10)
        bad_r, said_r = premature_result(str(body), ref)
        if bad_r:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.PREMATURE_RESULT,
                       said_r[:120])
            continue
        cache[url] = doc
        out.append(doc)
    return out


#: 🔴 **끝난 경기를 말하는 낱말**과 "이 경기가 끝났다" 판정은 `app/verify.py` 가
#   원본이다(사본 금지) — s3 와 s5 가 **같은 규칙**을 써야 한다.
#   ⚠️ 종전엔 여기 `RESULT_WORDS` 가 따로 있어 s5 의 `POST_GAME_MARKS` 와 갈렸다.
def premature_result(body: str, ref: MatchRef) -> tuple[bool, str]:
    """🔴🔴 §3-3 — **킥오프 전인데 이 경기 결과를 적는 글인가**. `(버리나, 왜)`.

    > 기사 시각 < 킥오프인데 **최종 스코어를 말하면** 버린다(소후 가짜 결과 기사).

    🔴 판정 규칙은 `verify.ended_this_match` **하나**다(사본 금지) — s5 의
       경기 후 검사도 같은 함수를 쓴다. ⚠️ 종전엔 이 파일에 낱말표가 따로 있어
       s5 의 `POST_GAME_MARKS` 와 갈렸다.
    🔴 셋이 **한 문장에** 있어야 버린다: **두 팀** · **스코어** · **종료 낱말**.
       ⚠️ 실사고 2026-10-10: 두 팀 검사가 없을 때 *"Korea drew 0-0 … against
          **Venezuela**"*(지난 경기)로 멀쩡한 미리보기 3건이 날아갔다.
    ⚠️ 킥오프가 **이미 지난** 경기에는 검사하지 않는다 — 그때는 결과 기사가
       정상이다(그 경기는 채점 쪽 일이다).
    """
    from app import verify
    from app import window as _w
    when = ref.kickoff_utc
    if when is None or _w.now_utc() >= when:
        return False, ""
    got, said = verify.ended_this_match(str(body or ""), names_of(ref))
    if not got:
        return False, ""
    return True, f"킥오프 전인데 **이 경기** 최종 스코어를 적는다 — {said}"


def _replaying() -> bool:
    """🔴 카세트 재생 중인가 — 재생에서는 질의를 합치지 않는다(위 까닭)."""
    from app import cassette
    return cassette.mode() == cassette.REPLAY


def tally_to(state: RunState, docs: list) -> None:
    """🔴🔴 **센 칸을 카드에 적는다** — 종전엔 `run` 이 하던 일이다.

    🔴 딥서치를 지우면서(2026-10-17) `run` 이 사라졌고, 그와 함께 이 적기도
       사라져 깔때기가 *"질의 못 쟀다 · 문서 못 쟀다"* 가 됐다(실측: e2e 고정물).
    🔴 **0 도 적는다** — ⚠️ 실사고 2026-10-11: `if n:` 이 0 을 빼먹어
       `queries None` 으로 남았고 *"안 쟀다"* 와 *"재 보니 0"* 이 섞였다(#3).
    ⚠️ 칸 이름은 **깔때기 계약**이 정한다(`state.STAGES`) — 지어내지 않는다.
    """
    for stage in ("queries", "hits", "kept_date"):
        state.set(stage, int(_TALLY.get(stage) or 0))
    for stage, n in sorted(_TALLY.items()):
        if n:
            state.set(stage, n)
    _TALLY.clear()
    # 🔴 같은 URL 은 **한 번만** — 캐시가 그것을 보장한다(§5 s3-4)
    state.set("docs", len(docs or []))


#: 🔴 기사 주소가 **아닌** 한 토막 경로 — 목록·섹션 화면이다(실측으로만 늘린다).
#   ⚠️ 낱말을 지어내지 않는다: 아래는 2026-10-17 실행에서 **실제로 받은** 것들이다.
SECTION_PATHS: frozenset[str] = frozenset({
    "kr", "ko", "news", "sports", "sport", "football", "soccer", "home",
    "index", "main", "hub", "list", "latest", "articles", "article"})


def front_page(url: object) -> tuple[bool, str]:
    """🔴🔴 **포털 첫 화면·목록 화면인가** — `(버린다, 사유)`.

    > 사용자 지시 2026-10-17 — 광범위 검색으로 결과가 늘자 첫 화면이 같이 늘었다.

    🔴 **주소 꼴로만** 본다 — 첫 화면에도 팀 이름과 오늘 날짜가 떠 있어서
       글자로는 못 가린다(그래서 날짜·신원 검문을 통과했다).
    ⚠️ 질의 문자열(`?id=…`)이 있으면 **기사일 수 있다** — 버리지 않는다
       (`gall.dcinside.com/…/view/?id=…` · `asiatoday.co.kr/kn/view.php?key=…`).
    """
    said = str(url or "").strip()
    if not said:
        return False, ""
    from urllib.parse import urlparse
    try:
        got = urlparse(said)
    except ValueError:
        return False, ""
    if got.query:
        return False, ""
    parts = [x for x in str(got.path or "").split("/") if x.strip()]
    if not parts:
        return True, f"🔴 **첫 화면이다**(경로가 없다) — `{got.netloc}` · 그 경기 글이 아니다"
    if len(parts) == 1 and parts[0].lower() in SECTION_PATHS:
        return True, (f"🔴 **목록 화면이다**(`/{parts[0]}`) — `{got.netloc}` · "
                      "그 경기 글이 아니다")
    return False, ""
