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
    jobs = [_one(s, ref, state=state, chain=chain, net=net, cache=cache)
            for s in subs]
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
               net: Any, cache: dict[str, Doc]) -> list[Doc]:
    """🔴 하위 하나 — 검색 → 거르기 → 재정렬 → 상위 N건 fetch → `Doc`."""
    from app import datehint, domains, readtext
    from app.research import lead, rerank
    sid, name = _sid(sub), str(getattr(sub, "name", "?"))
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
    kept: list[Any] = []
    seen_url: set[str] = set()
    for h in hits:
        url = str(getattr(h, "url", "") or "")
        if not url or url in seen_url:
            continue
        seen_url.add(url)
        ok_d, tier, said = domains.verdict(url, sport=ref.sport)
        if not ok_d:
            state.drop(f"s3/{name}/{url[:40]}", DropReason.IDENTITY_MISMATCH,
                       said[:80])
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
        if url in cache:
            # 🔴 **경기 단위 캐시** — 같은 URL 은 한 번만 받는다(§5 s3-4)
            got = cache[url]
            out.append(got.model_copy(update={"subtask": sid,
                                              "id": f"D{len(out) + 1}"}))
            continue
        if not sub.budget.may_fetch():
            state.note(f"s3/{name} 열기 상한({sub.budget.fetch_cap})에 닿았다 — "
                       f"받은 문서 {len(out)}건")
            break
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
