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


#: 🔴 경기당 **새 질의**를 이만큼만 쓴다(원천 표의 상한은 질의 생성기가 본다 —
#   여기서는 하위 질문마다 같은 목록을 쓰므로 **앞 몇 개**만 자른다)
TABLE_CAP = 8


def _table_queries(ref: MatchRef, *, state: Any = None
                   ) -> list[tuple[str, str]]:
    """🔴🔴 §6-2 표 기반 질의 → `(질의, 언어)` 목록. 표가 없으면 **빈 목록**.

    🔴 만드는 곳은 `search.query.build` 하나다(사본 금지) — 여기서는 **꼴만**
       바꾼다. ⚠️ 상한을 넘기면 **원천 지정(S·A)이 앞**이므로 앞에서 자른다.
    """
    try:
        from app.core import probmodel as _pm
        from app.core.schema import Facts as _F
        from app.core.search import query as _qy
        kind = str(_pm._kind(ref, _F()) or "")
        got, why = _qy.build(league=kind,
                             home=str(getattr(ref, "home_name", "") or ""),
                             away=str(getattr(ref, "away_name", "") or ""),
                             players=[], coach="",
                             kinds=("absence", "expected_xi"))
        out = [(str(q["q"]), str(q["lang"])) for q in got[:TABLE_CAP]]
        if state is not None:
            state.note(f"s3 표 질의 — {why} → **{len(out)}개** 썼다"
                       f"(상한 {TABLE_CAP})" if out
                       else f"s3 표 질의 — ⬜ 없다({why[:60]})")
        return out
    except Exception as exc:                                # noqa: BLE001
        if state is not None:
            state.note(f"s3 표 질의 — 🔴 못 만들었다: {exc!r:.60}")
        return []


def queries_for(sub: Any, ref: MatchRef) -> list[tuple[str, str]]:
    """🔴 ① **질의 2개를 코드가 만든다**(§5 s3-1). `(질의, 언어)`.

    🔴 `{word}` 는 `search_words.yaml` 의 **개념 낱말**이다 — 유형 이름을 넣으면
       기사에 없는 글자가 되고, 받은 문단이 엉뚱해진다(실측 2026-10-06).
    ⚠️ 문지기 금지 문자(어깻점·따옴표·괄호)는 **값에서** 제거한다 — 문지기를
       완화하지 않는다(§8 금지).
    """
    from app import queries, rules
    from app.research import subtasks as _st
    mine, other = ((ref.home_name, ref.away_name)
                   if str(getattr(sub, "team_key", "")) == ref.home
                   else (ref.away_name, ref.home_name))

    def declared(lang: str) -> list[str]:
        """🔴🔴 §3-1 — 그 하위가 **표에 적어 둔** 개념 낱말들(그 언어로).

        ⚠️ 실측 2026-10-10(FC서울–제주): 같은 경기에서 `결장` 은 **3건**인데
           `복귀` 는 **18건** · `선발 명단` 은 16건이었다 — 개념에 따라 수확이
           다섯 배 갈린다. 🔴 그래서 F 는 쓸 개념을 **표에 적고** 그 순서로 돈다.
        ⚠️ 이 칸이 비면 아래 `word()` 가 `kinds` 에서 유도한다(A~D 가 그렇다).
        """
        out: list[str] = []
        for concept in (getattr(sub, "words", None) or ()):
            got = rules.local_words(str(concept), lang)
            if got and str(got[0]) not in out:
                out.append(str(got[0]))
        return out

    def word(lang: str) -> str:
        # 🔴🔴 **카탈로그 이름으로 묻는다** — 실측 2026-10-06: 유형군 이름
        #    (`absence_def`)은 카탈로그에 없어서 개념 낱말이 **빈 글자**였고,
        #    그래서 A 군의 영어 질의가 야구 유형(`pitcher_state` → `xi`)의 낱말을
        #    집었다(축구 경기인데). 옮기면 `injury` 가 나온다.
        for raw in (getattr(sub, "kinds", None) or ()):
            kind = adapt.catalog_type(str(raw)) or str(raw)
            concept = rules.word_concept(str(kind))
            if not concept:
                continue
            got = rules.local_words(concept, lang)
            if got:
                return str(got[0])
        return ""

    # 🔴 **1차는 영어다**(§4-4: *"1차 영어 → 2차에서 팀 현지어"*).
    #    ⚠️ 1차를 현지어로 바꿔 봤다가 **되돌렸다**(2026-10-10): 고정물의 질의가
    #       달라져 녹음이 전부 빗나갔다(기사 변수 0개). 🔴 §4-4 의 *"한국 리그는
    #       한국어 허용"* 은 **2차 현지어 질의**가 이미 지킨다.
    one = "en"
    # 🔴 표에 적힌 개념이 있으면 **1차(영어)도 그 개념**으로 묻는다(§3-1)
    #    ⚠️ 없으면 `kinds` 에서 유도한다(A~D 가 그렇다 · 그 길은 그대로다)
    said_one = (declared(one) or [word(one)])[0] if True else word(one)
    out: list[tuple[str, str]] = [
        (" ".join(x for x in (mine, other, said_one) if x), one)]
    # 🔴 **현지어 질의의 언어**다(§4-4 의 1차 언어가 아니다 · §3-1 "현지어+영어").
    #    ⚠️ 실사고 2026-10-10: `first_lang` 을 썼더니 `K-League 1` 이 손 목록에
    #       없어 한국어 질의가 **안 나갔다**(새 사실 0건의 원인이었다).
    lang = _st.team_lang(mine) or _st.local_lang_of(
        league=ref.competition, teams=(mine, other))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **표에 적힌 개념이 있으면 그것들로 돈다**(§3-1 · 하위 F)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 현지어로 **개념마다 한 줄** — 상한(하위당 검색 3회)까지.
    #  ⚠️ 상한을 넘기지 않는다: 1차 영어 + 현지어 둘 = 3회.
    said_cap = int(_sub_cfg().get("search") or 3)
    if lang and declared(lang):
        # 🔴🔴 **선수단 교체 개념은 한 팀 질의**다(사용자 결정 2026-10-10(3):
        #    *"`{팀} 전역`·`{팀} 신병 합류`"*). ⚠️ 두 팀 이름을 같이 넣으면 구단
        #    공지가 안 걸린다(그 글에는 상대 팀 이름이 없다).
        solo = (str((getattr(sub, "words", None) or ("",))[0])
                == "squad_turnover")
        for i, one_word in enumerate(declared(lang)[:max(0,
                                                         said_cap - len(out))]):
            a, b = _st.local_name(mine, lang), _st.local_name(other, lang)
            if solo and i == 0:
                out.append((" ".join(x for x in (a, one_word) if x), lang))
                continue
            out.append((" ".join(x for x in (a, b, one_word) if x), lang))
        return out[:said_cap]
    if lang and lang != one and word(lang):
        out.append((" ".join(x for x in (mine, other, word(lang)) if x), lang))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **현지 이름으로 한 번 더**(§3-1 "현지어") — 지우지 않고 **더한다**
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고 2026-10-10 ①: 한국어 질의를 **로마자 이름**으로 던져
        #     `Gangwon FC Bucheon FC 1995 결장` 이 됐다 — 한국 매체는 `강원`·
        #     `부천`이라 쓴다. 그래서 한국어로 묻고도 한국 기사를 못 집었다.
        #  ⚠️ 실사고 2026-10-10 ②: 그래서 위 질의의 **이름을 바꿔** 봤더니
        #     고정물의 녹음이 빗나가 **변수 10→7 · 기사 변수 4→1** 로 깎였다.
        #     🔴 녹음은 지난 경기라 다시 만들 수 없다 — 그래서 **바꾸지 않고
        #        한 줄 더한다**(하위당 검색 상한 3 안이다 · §4-5).
        a, b = _st.local_name(mine, lang), _st.local_name(other, lang)
        said = " ".join(x for x in (a, b, word(lang)) if x)
        if said and said != out[-1][0]:
            out.append((said, lang))
    return _fit(out, mine=mine, other=other)


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


async def run(ref: MatchRef, facts: Facts, *, state: RunState, chain: Any,
              net: Any, cache: dict[str, Doc] | None = None,
              extra_words: dict | None = None) -> list[Doc]:
    """🔴 하위 과제 여덟 — **찾기는 동시에, 자리 잡기는 차례로**(§5 s3 · §7 재생).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **왜 두 단으로 갈랐나** — 실측 2026-10-06(재생이 안 맞았다)
    ══════════════════════════════════════════════════════════════════

    ⚠️ 하위 8개가 **받기까지** 동시에 돌면, 같은 URL 을 먼저 집는 하위가 **그때그때
       다르다**(망이 느릴 때와 카세트에서 즉시 읽을 때가 다르다). 실측: 라이브에서
       `C-홈` 이 1건, 재생에서 3건을 받아 **추출 요청이 달라졌고** LLM 카세트가 전부
       빗나갔다(변수 14개 → 0개).
    🔴 그래서 **찾기(검색·거르기·재정렬)는 동시에**, **자리 잡기와 받기는 하위
       순서대로 차례로** 한다 — 그러면 같은 입력에 같은 배분이 나온다(재생이 재생이
       되는 조건이다).
    ⚠️ 느려지는 것은 받기뿐이다(검색이 느린 쪽이고, 그쪽은 그대로 동시다).
    """
    # 🔴 **실행마다 비운다** — 질의 캐시가 실행을 넘으면 어제 결과가 섞인다
    _SEEN.clear()
    from app.research import subtasks as _st
    cache = cache if cache is not None else {}
    subs = _st.split(_RefShim(ref))
    # 🔴🔴 **의심될 때만 개념을 더한다**(사용자 지시 2026-10-10 지적 ③) —
    #    `{"F": ("squad_turnover",)}` 꼴. ⚠️ 늘 넣으면 다른 경기의 질의가
    #    묽어진다(실측 2026-10-10: 개념에 따라 수확이 다섯 배 갈린다).
    if extra_words:
        import dataclasses as _dc
        box = {str(k): tuple(str(x) for x in v)
               for k, v in dict(extra_words).items()}
        # 🔴🔴 **맨 앞에** 넣는다 — ⚠️ 실사고 2026-10-10: 뒤에 붙였더니 질의
        #    계획이 개념을 **둘까지만** 쓰므로(하위당 검색 3회 상한) 여섯째였던
        #    `squad_turnover` 가 **한 번도 안 나갔다**(김천 새 사실 0건의 원인).
        subs = [(_dc.replace(sub, words=box[str(sub.group)] + tuple(sub.words))
                 if str(getattr(sub, "group", "")) in box else sub)
                for sub in subs]
        state.note(f"s3 개념 추가 — {box}(선수단 교체 의심)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ②③ **LLM 이 질의를 쓰고 매체를 고른다**(사용자 지시 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-11(네 경기): 수확이 전부 0이었고 상류 원인이 *"그 경기
    #     기사를 애초에 못 집어 온다"* 였다 — 질의가 **영어 한 꼴뿐**이어서다
    #     (`리그 미상`이면 코드가 영어만 던진다). 일본어 매체에 소식이 있는데
    #     `Shonan Bellmare injury news` 를 던졌다.
    #  🔴 LLM 은 **글자만** 낸다(질의·도메인) — 사실·숫자·판정에 닿지 않는다.
    #     던지는 통로는 **기존 사슬**이고, 매체는 `site:` 질의로 들어간다.
    #  ⚠️ 실패하면 빈 목록이고 **코드 질의가 그대로 돈다**(퇴로가 있다).
    said_extra = await _llm_queries(ref, state=state, net=net)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **표 기반 새 질의**(지시 2026-10-13 밤 넷째 3번 · §6-2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 현지어 + 영어 · **팀 별칭 전부** · **원천 지정(`site:`)이 먼저** ·
    #     낱말은 `config/search_terms/<언어>.yaml` · 원천은
    #     `config/sources/<리그>.yaml`(robots 확인한 것만).
    #  🔴 **왜** — 기준선(2026-10-13): 결장 재현율 **16.3%** 이고 버린 문서의
    #     절반이 신원인데 **잘못 버림은 1%** 였다 → *"맞는 기사를 애초에 못
    #     찾는다"* 가 병이다. 실측: 광주–울산이 **24질의 → 결과 489건**.
    #  ⚠️ 표가 없는 리그는 **빈 목록**이다(QY1) — 그러면 옛 질의만 돈다.
    said_table = _table_queries(ref, state=state)
    # ── ① 찾기 — **동시에**(순서가 결과를 바꾸지 않는다)
    found = await asyncio.gather(
        *[_candidates(sub, ref, state=state, chain=chain,
                      queries=[*said_table, *queries_for(sub, ref),
                               *said_extra])
          for sub in subs],
        return_exceptions=True)
    # ── ② 자리 잡고 받기 — 🔴 **하위 순서대로**(배분이 결정적이어야 한다)
    claimed: set[str] = set(cache)
    out: list[Doc] = []
    for sub, row in zip(subs, found, strict=False):
        name = str(getattr(sub, "name", "?"))
        if isinstance(row, BaseException):
            state.drop(f"s3/{name}", DropReason.NO_DOC, f"터졌다: {row!r}")
            state.book[_sid(sub)] = "not_tried"
            continue
        got = await _fetch(sub, ref, row, state=state, net=net, cache=cache,
                           claimed=claimed)
        out += got
        state.book[_sid(sub)] = "found" if got else "empty"
    # 🔴 **센 칸을 적는다** — 실측 2026-10-06: `queries`·`hits`·`kept_date` 가
    #    `null` 로 남아 깔때기가 *"안 쟀다"* 라고 말했다(#3 은 그것을 허용하지만,
    #    **잴 수 있는데 안 잰 것**은 게으름이다). 수는 `_tally` 가 모은다.
    # 🔴 **0 도 적는다** — ⚠️ 실사고 2026-10-11: `if n:` 이 0 을 빼먹어 카드에
    #    `queries None` 으로 남았고, *"안 쟀다"* 와 *"재 보니 0"* 이 섞였다(#3).
    # ⚠️ 칸 이름은 **깔때기 계약**이 정한다(`state.STAGES`) — 새 칸을 지어내지
    #    않는다. 막힌 질의 수는 `state.note` 로 보고에 남는다(위 `gate_ok` 자리).
    for stage in ("queries", "hits", "kept_date"):
        state.set(stage, int(_TALLY.get(stage) or 0))
    for stage, n in sorted(_TALLY.items()):
        if n:
            state.set(stage, n)
    _TALLY.clear()
    # 🔴 같은 URL 은 **한 번만** — 캐시가 그것을 보장한다(§5 s3-4)
    state.set("docs", len(out))
    return out


def _sid(sub: Any) -> str:
    """🔴 `A-홈` → `A-home` — `SubtaskId` 열거값이 원본이다."""
    name = str(getattr(sub, "name", ""))
    group = name.split("-")[0] if "-" in name else name
    side = "home" if name.endswith("홈") else "away"
    return f"{group}-{side}"


class _RefShim:
    """🔴 `subtasks.split` 이 기대하는 꼴 — 변환은 `adapt` 밖에 두지 않는다.

    ⚠️ 그 함수는 `app/research` 의 기존 부품이고 **내부를 건드리지 않는다**(§2).
       🔴 그래서 **읽기 전용 그림자**를 여기 둔다 — dict 를 넘기지 않는다.
    """

    __slots__ = ("home", "away", "home_id", "away_id", "competition",
                 "sport", "langs")

    def __init__(self, ref: MatchRef) -> None:
        self.home, self.away = ref.home_name, ref.away_name
        self.home_id, self.away_id = ref.home, ref.away
        self.competition, self.sport = ref.competition, ref.sport
        self.langs = tuple(ref.langs)


async def _llm_queries(ref: MatchRef, *, state: RunState, net: Any
                       ) -> list[tuple[str, str]]:
    """🔴🔴 ②③ — LLM 질의 + 확인된 매체의 `site:` 질의. `[(질의, 언어)]`.

    🔴 언어 꼬리표는 **`und`**(모름)로 붙인다 — 현지어가 섞여 있어 한 언어로
       말할 수 없다. ⚠️ 사슬은 그 꼬리표를 엔진 선택에만 쓴다.
    ⚠️ 재생(카세트)에서는 **안 부른다** — 녹음이 그 질의를 모른다(실사고
       2026-10-10 과 같은 병: 라이브에만 이득인 질의가 고정물을 깎는다).
    """
    if _replaying():
        state.note("②③ 질의 쓰기 — ⬜ 재생이라 **안 돌렸다**(녹음이 모른다)")
        return []
    from app.core import discover as _d
    from app.core import querywriter as _qw
    aliases = [*_d.aliases_of(str(getattr(ref, "home_name", "") or "")),
               *_d.aliases_of(str(getattr(ref, "away_name", "") or ""))]
    langs = list(getattr(ref, "langs", None) or ["en"])
    rows, sites, _why = _qw.ask(ref, state=state, aliases=aliases,
                                langs=langs)
    ok: list[str] = []
    if sites:
        ok, _said = await _qw.check_hosts(net, sites, state=state)
    said = [*rows, *_qw.site_queries(ok, rows)]
    return [(q, "und") for q in said[:_qw.MAX_QUERIES]]


async def _candidates(sub: Any, ref: MatchRef, *, state: RunState,
                      chain: Any,
                      queries: list[tuple[str, str]] | None = None,
                      tag: str = "") -> list[tuple[Any, str]]:
    """🔴 ①~③ **찾기만** — 검색 → 도메인 등급 → 신원 → 날짜 힌트 → 재정렬.

    ⚠️ 여기서는 **아무것도 받지 않는다**(fetch 0회) — 받기는 `_fetch` 가 차례로
       한다(위 `run` 의 까닭). 🔴 `queries` 를 주면 그 질의로 돈다(좁히기 2차).
    """
    from app import datehint, domains
    from app.core import rank
    from app.research import lead
    name = (tag or str(getattr(sub, "name", "?")))
    hits: list[Any] = []
    for q, lang in (queries if queries is not None else queries_for(sub, ref)):
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
                 start: int = 0) -> list[Doc]:
    """🔴 ③ **자리 잡고 상위 N건 받기.** 실패는 **다음 후보로 대체한다**.

    ⚠️ 이 함수는 `run` 이 **하위 순서대로** 부른다 — 그래야 같은 URL 을 누가
       가져가는지가 **타이밍으로 갈리지 않는다**(재생 조건).
    """
    from app import readtext
    from app.research import lead
    sid, name = _sid(sub), (tag or str(getattr(sub, "name", "?")))
    # 🔴 **자리를 잡은 URL** — 캐시와 따로 든다(캐시는 `Doc` 을, 이쪽은 **의도**를)
    claimed = claimed if claimed is not None else set(cache)
    top = int(_sub_cfg().get("fetch_top") or 3)
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


async def regather(ref: MatchRef, sid: str, words: list[str], *,
                   state: RunState, chain: Any, net: Any,
                   cache: dict[str, Doc] | None = None,
                   start: int = 0) -> list[Doc]:
    """🔴🔴 **좁힌 질의로 ①~③ 을 한 번 더**(§5 s4). ⚠️ 한 번뿐이다.

    🔴 낱말은 **s4 가 1차 제목에서 뽑아** 넘긴다(지어내지 않는다 · #4).
    ⚠️ 질의 상한(`querygate.MAX_WORDS`)은 `subtasks.narrow_query` 가 지킨다 —
       여기서 다시 세지 않는다(#1 사본 금지).
    """
    from app.research import subtasks as _st
    cache = cache if cache is not None else {}
    for sub in _st.split(_RefShim(ref)):
        if _sid(sub) != str(sid):
            continue
        if not sub.budget.may_search():
            state.note(f"s3/{sid} 2차 — 검색 상한에 닿아 돌리지 않았다")
            return []
        qs = [(_st.narrow_query(q, words), lang)
              for q, lang in queries_for(sub, ref)]
        tag = f"{sub.name}(2차)"
        kept = await _candidates(sub, ref, state=state, chain=chain,
                                 queries=qs, tag=tag)
        return await _fetch(sub, ref, kept, state=state, net=net, cache=cache,
                            claimed=set(cache), tag=tag, start=start)
    state.note(f"s3 2차 — `{sid}` 하위를 못 찾았다")
    return []


def _replaying() -> bool:
    """🔴 카세트 재생 중인가 — 재생에서는 질의를 합치지 않는다(위 까닭)."""
    from app import cassette
    return cassette.mode() == cassette.REPLAY
