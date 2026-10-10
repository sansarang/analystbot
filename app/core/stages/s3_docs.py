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
import re
from datetime import timedelta
from typing import Any

from app.core import adapt
from app.core.schema import Doc, DropReason, Facts, MatchRef
from app.core.state import RunState

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
    out: list[tuple[str, str]] = [
        (" ".join(x for x in (mine, other, word(one)) if x), one)]
    # 🔴 **현지어 질의의 언어**다(§4-4 의 1차 언어가 아니다 · §3-1 "현지어+영어").
    #    ⚠️ 실사고 2026-10-10: `first_lang` 을 썼더니 `K-League 1` 이 손 목록에
    #       없어 한국어 질의가 **안 나갔다**(새 사실 0건의 원인이었다).
    lang = _st.team_lang(mine) or _st.local_lang_of(
        league=ref.competition, teams=(mine, other))
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
    return [(queries.slot_value(q), lg) for q, lg in out if str(q).strip()]


def names_of(ref: MatchRef) -> tuple[list[str], list[str]]:
    """🔴 두 팀을 가리키는 **모든 이름** — 신원 선필터가 이것으로 본다.

    ⚠️ 인자는 **열쇠**다(§8-1) — 이름을 받으면 또 하나의 해석 지점이 된다.
    """
    # 🔴 **출처가 실제로 쓴 이름도 넣는다** — 열쇠의 이름만 보면 그 경기 페이지가
    #    쓴 표기를 버린다(⚠️ 열쇠가 어긋났을 때 그 사실이 조용히 묻힌다).
    home = [n for n in (*adapt.names_of_key(ref.home), ref.home_name) if n]
    away = [n for n in (*adapt.names_of_key(ref.away), ref.away_name) if n]
    return list(dict.fromkeys(home)), list(dict.fromkeys(away))


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


async def run(ref: MatchRef, facts: Facts, *, state: RunState, chain: Any,
              net: Any, cache: dict[str, Doc] | None = None) -> list[Doc]:
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
    from app.research import subtasks as _st
    cache = cache if cache is not None else {}
    subs = _st.split(_RefShim(ref))
    # ── ① 찾기 — **동시에**(순서가 결과를 바꾸지 않는다)
    found = await asyncio.gather(
        *[_candidates(sub, ref, state=state, chain=chain) for sub in subs],
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
        sub.budget.search_used += 1
        _count("queries")
        try:
            async with lead.gate("searx"):
                got = await chain.query(q, lang=lang)
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s3/{name} 검색 실패 {q!r}: {exc}")
            continue
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
                       f"도메인 등급 — {said[:70]}")
            continue
        # 🔴 **신원 선필터**(§5 s3-3) — 두 팀 어느 이름도 없으면 남의 글이다
        ok_i, said_i = identity_ok(str(getattr(h, "title", "") or ""),
                                   str(getattr(h, "snippet", "") or ""), who)
        if not ok_i:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.IDENTITY_MISMATCH,
                       said_i[:90])
            continue
        old, said_old = datehint.too_old(url, str(getattr(h, "snippet", "")
                                                 or ""))
        if old:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.STALE, said_old[:80])
            continue
        _count("kept_date")
        kept.append((h, str(tier)))
    # ── ③ 재정렬 1단. 🔴 **녹음·재생을 거친다**(`rank`) — 재생에 모델이 없다
    if kept:
        want = " ".join(adapt.catalog_type(str(k)) or str(k)
                        for k in (getattr(sub, "kinds", None) or ()))
        kept, said_r = rank.order_of(
            kept, lambda row: f"{getattr(row[0], 'title', '')} "
                              f"{getattr(row[0], 'snippet', '')}", want)
        state.note(f"s3/{name} 재정렬 — {said_r}")
    return kept


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
        try:
            async with lead.gate("fetch"):
                raw = await net.get(url)
        except Exception as exc:                            # noqa: BLE001
            state.drop(f"s3/{name}/{url[:40]}", DropReason.BODY_MISSING,
                       f"열기 실패: {exc}")
            continue
        if not getattr(raw, "ok", False):
            state.drop(f"s3/{name}/{url[:40]}", DropReason.BODY_MISSING,
                       f"열기 실패: 상태 {getattr(raw, 'status', '?')}")
            continue
        body, when = readtext.extract(getattr(raw, "text", "") or "", url=url)
        if not str(body or "").strip():
            state.drop(f"s3/{name}/{url[:40]}", DropReason.BODY_MISSING,
                       "본문을 못 뽑았다")
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


#: 🔴 **끝난 경기를 말하는 낱말** — 스코어 숫자 하나로는 모자란다(배당·시각·
#   순위도 `2-1` 꼴로 적힌다). 🔴 그래서 **스코어 + 종료 낱말**을 함께 본다.
RESULT_WORDS = (
    "최종 스코어", "경기 종료", "풀타임", "승리를 거뒀", "패배를 안", "무승부로",
    # 🔴🔴 **실측으로 늘렸다**(2026-10-10 · 강원–부천 실행에서 받은 실제 기사)
    #
    #  ⚠️ `news.jkn.co.kr/post/1014517` — *"강원, 후반 두 골로 부천 제압 … 부천FC를
    #     **2-0으로 꺾었다**"*. 🔴 위 낱말 어느 것도 안 걸렸다 — 한국 매체는
    #     *"꺾었다·제압·승리했다·무릎 꿇"* 으로 쓴다.
    #  🔴 **기억으로 적지 않았다** — 받은 글에 있던 꼴만 넣고, 늘릴 때도 실측으로
    #     한다(그 사실을 여기 적는다).
    "꺾었", "제압", "승리했", "패했", "무승부를 기록", "역전승", "완승", "신승",
    "final score", "full-time", "full time", "ft:", "beat ", "defeated ",
    "won ", "drew ", "試合終了", "勝利", "敗れ", "引き分け",
    "resultado final", "venció", "empató", "derrotó",
)
#: 🔴 스코어 꼴 — `2-1`·`2 : 1`·`2–1`(en dash). ⚠️ 앞뒤가 숫자면 안 센다(날짜·시각)
_SCORE = re.compile(r"(?<![\d:.])([0-9])\s*[-–:]\s*([0-9])(?![\d:.])")


def premature_result(body: str, ref: MatchRef) -> tuple[bool, str]:
    """🔴🔴 §6 — **킥오프 전인데 최종 스코어를 적는 글인가**. `(버리나, 왜)`.

    > 경기 전 기사에 **결과 스코어가 적혀 있으면** 그 문서는 버린다.

    🔴 **스코어 숫자만으로는 안 버린다** — `2-1` 꼴은 배당·시각·순위에도 나온다.
       종료를 말하는 낱말(`RESULT_WORDS`)이 **같은 문장**에 있어야 버린다.
    ⚠️ 킥오프가 **이미 지난** 경기에는 이 검사를 안 쓴다 — 그때는 결과 기사가
       정상이다(그 경기는 채점 쪽 일이다).
    🔴 왜(사용자 결정 2026-10-10 §6): 그런 글은 **다른 경기**의 결과이거나 예측
       사이트의 모의 스코어다. 사실로 읽으면 카드가 이미 끝난 경기를 분석한다.
    """
    # 🔴 "지금"은 `app/window.now_utc` 하나다(사본 금지 — 고정물 재생도 그것을 본다)
    from app import window as _w
    when = ref.kickoff_utc
    if when is None or _w.now_utc() >= when:
        return False, ""
    for line in re.split(r"(?<=[.!?。])\s+|\n+", str(body or "")):
        hit = _SCORE.search(line)
        if not hit:
            continue
        low = line.lower()
        said = next((w for w in RESULT_WORDS if w.lower() in low), "")
        if not said:
            continue
        # 🔴🔴 **이 경기 두 팀이 그 문장에 다 있어야** 버린다
        #
        #  ⚠️ 실사고 2026-10-10: 이 검사를 넣자 고정물(한국–우즈벡)에서 멀쩡한
        #     **미리보기 기사 3건**이 날아갔다 — *"Korea drew 0-0 … against
        #     **Venezuela**"* 는 **지난 경기** 얘기다. 그것은 가짜 결과가 아니다.
        #  🔴 사용자가 든 예시는 *"선전 1-0 허난"* — **이 경기 두 팀**을 적는다.
        #     그래서 두 팀이 다 있을 때만 *"이 경기의 결과를 말한다"* 로 읽는다.
        if not _both_teams(line, ref):
            continue
        return True, (f"킥오프 전인데 **이 경기** 최종 스코어를 적는다 — "
                      f"`{hit.group(0)}` + `{said}` · \"{line.strip()[:70]}\"")
    return False, ""


def _both_teams(line: str, ref: MatchRef) -> bool:
    """🔴 그 문장에 **이 경기 두 팀**이 다 있나.

    🔴 이름은 **이름표가 든 별칭 전부**다(`names_of`) — 로마자만 보면 한국·일본
       기사를 못 읽는다. ⚠️ 실사고 2026-10-10: 한국 결과 기사(*"부천FC를 2-0으로
       꺾었다"*)가 `Gangwon FC`·`Bucheon FC 1995` 로만 대조돼 **안 걸렸다**.
    🔴 최소 글자 수는 `_min_len` 하나다(한글 2 · 로마자 3 · 사본 금지).
    """
    low = str(line or "").lower()
    for side in names_of(ref):
        if not any(str(n or "").strip().lower() in low
                   and len(str(n).strip()) >= _min_len(str(n))
                   for n in side):
            return False
    return True


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
