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
from datetime import timedelta
from typing import Any

from app.core import adapt
from app.core.schema import Doc, DropReason, Facts, MatchRef
from app.core.state import RunState

#: 🔴 발행일 창 — 킥오프 **7일 전**까지. ⚠️ 수는 `verifylayer.DATE_WINDOW_DAYS` 가
#   원본이다(사본 금지) — 여기서 다시 정하지 않는다.
def _window_days() -> int:
    from app import verifylayer
    return int(verifylayer.DATE_WINDOW_DAYS)


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
        for kind in (getattr(sub, "kinds", None) or ()):
            concept = rules.word_concept(str(kind))
            if not concept:
                continue
            got = rules.local_words(concept, lang)
            if got:
                return str(got[0])
        return ""

    out: list[tuple[str, str]] = [
        (" ".join(x for x in (mine, other, word("en")) if x), "en")]
    lang = _st.team_lang(mine) or _st.first_lang(
        league=ref.competition, langs=tuple(ref.langs))
    if lang and lang != "en" and word(lang):
        out.append((" ".join(x for x in (mine, other, word(lang)) if x), lang))
    return [(queries.slot_value(q), lg) for q, lg in out if str(q).strip()]


def names_of(ref: MatchRef) -> tuple[list[str], list[str]]:
    """🔴 두 팀을 가리키는 **모든 이름** — 신원 선필터가 이것으로 본다.

    ⚠️ 인자는 **열쇠**다(§8-1) — 이름을 받으면 또 하나의 해석 지점이 된다.
    """
    from app import analyze
    home = [n for n in analyze._names_of_key(ref.home) if n] or [ref.home_name]
    away = [n for n in analyze._names_of_key(ref.away) if n] or [ref.away_name]
    return home, away


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
            if len(got) >= 3 and got in said:
                return True, f"신원 ✅ `{n}`"
    return False, (f"🔴 제목·스니펫에 **두 팀 어느 이름도 없다** — "
                   f"{said[:60]!r}")


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
    """🔴 하위 과제 **8개를 병렬로** 돌려 `Doc` 목록을 만든다(§5 s3)."""
    from app.research import subtasks as _st
    cache = cache if cache is not None else {}
    subs = _st.split(_RefShim(ref))
    claimed: set[str] = set(cache)
    jobs = [_one(s, ref, state=state, chain=chain, net=net, cache=cache,
                 claimed=claimed) for s in subs]
    got = await asyncio.gather(*jobs, return_exceptions=True)
    out: list[Doc] = []
    for sub, row in zip(subs, got, strict=False):
        name = str(getattr(sub, "name", "?"))
        if isinstance(row, BaseException):
            state.drop(f"s3/{name}", DropReason.NO_DOC, f"터졌다: {row!r}")
            state.book[_sid(sub)] = "not_tried"
            continue
        out += row
        state.book[_sid(sub)] = "found" if row else "empty"
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


async def _one(sub: Any, ref: MatchRef, *, state: RunState, chain: Any,
               net: Any, cache: dict[str, Doc],
               claimed: set[str] | None = None) -> list[Doc]:
    """🔴 하위 하나 — 검색 → 거르기 → 재정렬 → 상위 N건 fetch → `Doc`."""
    from app import datehint, domains, readtext
    from app.research import lead, rerank
    sid, name = _sid(sub), str(getattr(sub, "name", "?"))
    # 🔴 **자리를 잡은 URL** — 캐시와 따로 든다(캐시는 `Doc` 을, 이쪽은 **의도**를)
    claimed = claimed if claimed is not None else set(cache)
    cfg = _sub_cfg()
    top = int(cfg.get("fetch_top") or 3)
    hits: list[Any] = []
    for q, lang in queries_for(sub, ref):
        if not sub.budget.may_search():
            state.note(f"s3/{name} 검색 상한({sub.budget.search_cap})에 닿았다")
            break
        ok, why = gate_ok(q)
        if not ok:
            state.note(f"s3/{name} {why}")
            continue
        sub.budget.search_used += 1
        try:
            async with lead.gate("searx"):
                got = await chain.query(q, lang=lang)
        except Exception as exc:                            # noqa: BLE001
            state.note(f"s3/{name} 검색 실패 {q!r}: {exc}")
            continue
        state.note(f"s3/{name} 질의 {q!r}({lang}) → {len(got or [])}건")
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
        kept.append((h, str(tier)))
    # ── ③ 재정렬 1단
    if kept:
        want = " ".join(str(k) for k in (getattr(sub, "kinds", None) or ()))
        pairs = [f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
                 for h, _t in kept]
        order, said_r = rerank.paragraphs(want, pairs)
        state.note(f"s3/{name} 재정렬 — {said_r}")
        rank = {t: i for i, t in enumerate(order)}
        kept.sort(key=lambda row: rank.get(
            f"{getattr(row[0], 'title', '')} {getattr(row[0], 'snippet', '')}",
            999))
    # ── ③ 상위 N건 fetch. 🔴 **실패는 다음 후보로 대체한다**(실측 2026-10-06)
    floor = ref.kickoff_utc - timedelta(days=_window_days())
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
        src = "htmldate" if when else "none"
        doc = adapt.doc_of(doc_id=f"D{len(out) + 1}", url=url, body=str(body),
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
        cache[url] = doc
        out.append(doc)
    return out
