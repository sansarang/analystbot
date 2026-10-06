"""🔴🔴 **§2 — 하위 과제 분할 표**(작업 지시서 2026-10-05).

> 경기 하나 = **하위 과제 8개**(유형군 4 × 홈/원정). `subtasks.py` 가 이 표를
> **데이터로** 갖고, 경기 입력(`MatchRef`·구조 사실·`langs`)에서 하위 과제
> 목록을 만든다. `recent_pattern`·`h2h` 는 구조 사실(어댑터)에서 오므로
> **하위 과제에 넣지 않는다.**

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — 실측 2026-10-04~05
══════════════════════════════════════════════════════════════════

```
①  한 에이전트가 경기 전체를 돌아 경기당 12분
②  한쪽 팀이 예산을 다 써서 다른 쪽 0개
③  결장·로테이션·감독·경기외 유형이 늦게·얇게 나옴
```

🔴 분할이 그 셋을 **동시에** 푼다: 병렬이라 시간이 줄고, 예산이 하위마다
   독립이라 한쪽이 다 쓰지 못하고, 유형군마다 담당이 있어 커버리지가 보장된다.
⚠️ 그래서 `done` 거부 루프를 **지웠다** — 커버리지를 거부로 짜내던 자리다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: 🔴 분할 표의 원본. ⚠️ **코드에 베끼지 않는다**(#1) — yaml 이 든다.
_TABLE = "config/subtask_groups.yaml"


def groups() -> list[dict]:
    """🔴 유형군 표 — `config/subtask_groups.yaml`.

    ⚠️ 함수다 — 설정을 **읽는 시점**에 가져와야 표를 고치면 코드가 따라간다.
    """
    from app import rules
    got = rules._load(_TABLE)
    rows = list((got or {}).get("groups") or [])
    if not rows:
        raise KeyError(f"🔴 `{_TABLE}` 에 `groups` 가 없다")
    return rows


@dataclass
class Budget:
    """🔴🔴 **하위 하나의 예산** — M59: 하위마다 **독립 객체**다.

    ⚠️ 실측 2026-10-04: 한 팀 에이전트가 예산을 다 써서 **다른 쪽이 0개**였다.
       🔴 공유 카운터를 쓰면 그 일이 다시 난다 — 그래서 하위마다 새로 만든다.
    """

    search_cap: int
    fetch_cap: int
    out_cap: int
    turns: int
    search_used: int = 0
    fetch_used: int = 0
    out_used: int = 0

    def can_call(self) -> bool:
        """🔴 아직 부를 수 있나 — 출력이 남았나로 본다."""
        return self.out_used < self.out_cap

    def spend_out(self, n: int) -> None:
        self.out_used += int(n)

    def may_search(self) -> bool:
        return self.search_used < self.search_cap

    def may_fetch(self) -> bool:
        return self.fetch_used < self.fetch_cap

    def left_out(self) -> int:
        return max(0, self.out_cap - self.out_used)


@dataclass
class Subtask:
    """🔴 하위 과제 하나 — 유형군 × 자리(홈/원정)."""

    name: str
    group: str
    label: str
    kinds: tuple[str, ...]
    side: str
    #: 🔴 **질의용 글자**(별칭표의 영어 짧은 표기) — 열쇠가 아니다
    team: str
    opp: str
    #: 🔴 출력 `team` 칸에 쓸 **열쇠**(M48)
    team_key: str
    opp_key: str
    seed: str
    rerank_query: str
    langs: tuple[str, ...] = ()
    #: 🔴🔴 **그 팀의 현지어** — 2차 질의가 쓴다(지시서 §4-2).
    #   ⚠️ 두 팀이 **다른 언어**다(인도네시아 `id` · 태국 `th`) — 같은 목록을
    #      주면 한쪽이 자기 매체를 못 본다.
    local_lang: str = ""
    #: 🔴 2차에서 **뺄 도메인** — 쏠린 곳을 또 보지 않는다(지시서 §4-2).
    avoid_host: str = ""
    budget: Budget = field(default_factory=lambda: Budget(0, 0, 0, 0))
    #: 🔴 2차 보충인가 — 리드가 `not_tried`·`empty` 칸만 다시 돌린다
    second: bool = False


def _budget(*, second: bool = False) -> Budget:
    """🔴 설정에서 예산을 만든다 — 수를 코드에 박지 않는다(지시서 §2)."""
    from app import solar
    box = dict(solar.budget_cfg().get("per_subtask") or {})
    if not box:
        raise KeyError("🔴 `budget.per_subtask` 가 `config/llm.yaml` 에 없다")
    turns = int(box["second_turns"] if second else box["turns"])
    return Budget(search_cap=int(box["search"]), fetch_cap=int(box["fetch"]),
                  out_cap=int(box["output_tokens"]), turns=turns)


#: 🔴 씨앗에 넣을 **대회 핵 낱말 수**. ⚠️ 정식명 전체(`UEFA Nations League A
#  Grp. 1`)를 넣으면 씨앗이 **9낱말**이 되어 §4 의 3~6낱말을 깬다(실측
#  2026-10-05). 🔴 핵 낱말은 `querygate.comp_words` 가 뽑는다 — 그 판정을 두
#  벌로 만들지 않는다(#1 사본 금지).
COMP_WORDS_IN_SEED = 2


def comp_short(comp: str) -> str:
    """🔴 대회명 → **핵 낱말 둘**(`UEFA Nations League A Grp. 1` → `uefa nations`).

    ⚠️ 조별 꼬리(`A`·`Grp.`·`1`)는 `comp_words` 가 이미 버린다.
    """
    from app import querygate
    return " ".join(querygate.comp_words(comp)[:COMP_WORDS_IN_SEED])


def _seed_of(row: dict, *, sport: str, team: str, opp: str, comp: str) -> str:
    """🔴 씨앗 질의 — 종목별 꼴이 있으면 그것이 이긴다(표가 그렇게 적었다).

    🔴 **3~6낱말**이어야 한다(§4) — 그래서 대회는 `comp_short` 로 줄인다.
    """
    tpl = str((row.get("seed_by_sport") or {}).get(str(sport))
              or row.get("seed") or "")
    said = tpl.format(team=team, opp=opp, comp=comp_short(comp))
    return " ".join(said.split())


def split(ref: Any) -> list[Subtask]:
    """🔴🔴 **경기 입력 → 하위 과제 8개**(지시서 §2).

    ⚠️ `ref` 는 사전이거나 같은 칸을 가진 객체다 — 호출부가 둘을 쓴다.
    🔴 `{팀}` 자리에는 **영어 짧은 표기**를 넣는다(열쇠가 아니다). 출력
       `team` 칸은 열쇠 그대로다(M48).
    """
    def _get(key: str, alt: object = "") -> Any:
        if isinstance(ref, dict):
            return ref.get(key, alt)
        return getattr(ref, key, alt)

    home, away = str(_get("home") or ""), str(_get("away") or "")
    # 🔴 **두 이름을 다 받는다** — 운영 `game` dict 는 `home_id`/`away_id` 이고
    #    계약·슬레이트 쪽은 `home_key`/`away_key` 를 쓴다.
    #    ⚠️ 실사고 2026-10-05: 하나만 봐서 `team_key` 가 **빈 문자열**이었고
    #       장부가 `A/` 처럼 열쇠 없는 칸을 적었다(M48 이 막는 꼴).
    hk = str(_get("home_key") or _get("home_id") or "")
    ak = str(_get("away_key") or _get("away_id") or "")
    sport, comp = str(_get("sport") or ""), str(_get("league") or "")
    langs = tuple(str(x) for x in (_get("langs") or ()))
    out: list[Subtask] = []
    for row in groups():
        key = str(row.get("key") or "")
        for side, team, opp, tk, ok in (("home", home, away, hk, ak),
                                        ("away", away, home, ak, hk)):
            out.append(Subtask(
                name=f"{key}-{'홈' if side == 'home' else '원정'}",
                group=key, label=str(row.get("label") or ""),
                kinds=tuple(str(k) for k in (row.get("kinds") or ())),
                side=side, team=team, opp=opp, team_key=tk, opp_key=ok,
                seed=_seed_of(row, sport=sport, team=team, opp=opp, comp=comp),
                rerank_query=str(row.get("rerank_query") or ""),
                langs=langs,
                # 🔴 **자기 팀의 현지어**를 든다(§4-2)
                local_lang=team_lang(team),
                # 🔴 **하위마다 새 객체**(M59) — 공유하면 한쪽이 다 쓴다
                budget=_budget()))
    logger.info("[subtasks] 하위 %d개 — %s", len(out),
                " · ".join(f"{s.name}({len(s.kinds)}유형)" for s in out))
    return out


#: 🔴 표 그대로 — 호출부·계약이 **데이터로** 읽는다(#1 사본 금지).
#  ⚠️ 모듈을 들일 때 한 번 읽는다. 표를 고치면 `groups()` 를 부르면 된다.
GROUPS: list[dict] = groups()


#: 🔴 1차부터 **현지어를 허용하는 리그** — 지시서 §4-4.
#  > KBO·K리그·한국 대표팀은 **1차부터 한국어 허용**.
#  ⚠️ 그 밖은 **영어가 1차**다(§4-4: *"1차 영어 → 2차에서 팀 현지어"*).
#  🔴 이름은 지시서가 **그대로 줬다** — 내가 고른 것이 아니다.
LOCAL_FIRST: tuple[str, ...] = ("KBO", "K리그1", "K리그", "대한민국", "한국")

#: 🔴 좁히기에서 **버리는 낱말** — 흔해서 좁히는 뜻이 없다.
#  ⚠️ 사전이지 사실이 아니다(늘릴 때도 실측으로).
_STOP: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "vs", "v", "at", "by", "from", "as", "is", "are", "was", "were", "be",
    "has", "have", "had", "will", "not", "no", "but", "that", "this",
    "news", "preview", "lineup", "lineups", "match", "game", "team", "ahead"})

#: 🔴 좁히기 질의에 **더할 낱말 수**. ⚠️ `querygate.MAX_WORDS` 를 넘지 않게
#   호출부가 자른다 — 여기 수를 박지 않고 그 상한에서 계산한다.
NARROW_WORDS = 3


def team_lang(team: object) -> str:
    """🔴🔴 **그 팀의 현지어** — 지시서 §4-2 (2026-10-05).

    > 국가대표 경기의 현지어는 **양 팀 각각의 언어**다(인도네시아어 `id`,
    > 태국어 `th`). Babel likely-subtag 로 구하고, 하위 과제 **2차 질의 언어를
    > 팀별로 다르게** 쓴다.

    ⚠️ 실사고 it4/it5: 두 팀에 **같은 언어 목록**(`en`·`id`)을 줘서 태국 쪽
       하위가 태국어로 안 물었다. 🔴 인도네시아어 매체(detik·kompas·bola.com)가
       XI·결장·감독 기자회견을 다 갖고 있었다(지시서 §4-2).
    🔴 **못 구하면 빈 글**이다 — 지어내지 않는다(#4). 그러면 그 각도만 건너뛴다.
    """
    said = str(team or "").strip()
    if not said:
        return ""
    # 🔴 **`resolve.nation_langs` 가 정본이다**(#1 사본 금지) — 그것이 이름표의
    #    나라 코드(`iso:ID`)를 Babel CLDR likely-subtag 로 푼다.
    #    ⚠️ 여기서 Babel 을 다시 부르면 두 벌이 되고 한쪽만 고쳐진다.
    from app import resolve
    got, _how = resolve.nation_langs(said)
    # ⚠️ 끝의 `en` 은 그 함수가 **보탠 것**이다 — 현지어가 먼저다
    local = [x for x in got if x and x != "en"]
    return local[0] if local else ""


def first_lang(*, league: str, langs: tuple | list = ()) -> str:
    """🔴 **1차 질의 언어**(§4-4). 기본은 영어, 한국 리그는 한국어.

    ⚠️ `langs` 에 그 언어가 없으면 **있는 것 중 첫 것**이다 — 없는 언어를
       지어내지 않는다(#4).
    """
    got = tuple(str(x) for x in (langs or ()))
    said = str(league or "")
    if any(w and w in said for w in LOCAL_FIRST):
        return "ko" if ("ko" in got or not got) else got[0]
    return "en" if ("en" in got or not got) else got[0]


def narrow_words(hits: list) -> list[str]:
    """🔴🔴 **좁히기 낱말** — 1차 결과의 제목·스니펫에서(§4-2).

    > 2차(좁히기): 1차 결과의 제목·스니펫에서 본 **구체 낱말**(선수명·감독명·
    > 현지어 표기·부상 부위)로 좁힌다.

    🔴 **지어내지 않는다**(#4) — 받은 글에 있는 낱말만 돌려준다.
    ⚠️ 대문자로 시작하는 낱말을 먼저 센다 — 사람 이름이 그 꼴이다. 흔한
       낱말(`_STOP`)은 버린다: 좁히는 뜻이 없다.
    """
    import re as _re
    tally: dict[str, int] = {}
    for h in (hits or []):
        box = h if isinstance(h, dict) else {}
        said = " ".join(str(box.get(k) or "")
                        for k in ("title", "snippet", "content"))
        for w in _re.findall(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'\-]{2,}|[가-힣]{2,}", said):
            if w.lower() in _STOP:
                continue
            tally[w] = tally.get(w, 0) + 1
    # 🔴 **여러 결과에 나온 것이 먼저다** — 한 번만 나온 것은 잡음일 수 있다
    return [w for w, _ in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))]


def narrow_query(seed: str, words: list) -> str:
    """🔴 좁히기 질의 — 씨앗에 **구체 낱말 몇 개**를 더한다(§4-2).

    🔴 `querygate.MAX_WORDS` 를 **넘지 않는다**(M61) — 상한을 코드에 박지
       않고 그 이름에서 읽는다(#1).
    """
    from app import querygate
    base = str(seed or "").split()
    room = max(0, querygate.MAX_WORDS - len(base))
    add = [str(w) for w in (words or [])][:min(NARROW_WORDS, room)]
    return " ".join([*add, *base]) if add else " ".join(base)


def prompt_tail(task: Subtask) -> str:
    """🔴🔴 **하위 프롬프트 꼬리**(§2·§4) — 담당과 검색어 규칙을 전한다.

    > 하위 프롬프트 = 기존 시스템 프롬프트(규칙·`done` 스키마·인용 의무) +
    > *"네 담당은 위 유형들뿐이다. 다른 유형의 사실을 보면 적어도 되지만
    > **담당 유형을 먼저 끝내라**"* + §4 검색어 규칙.
    """
    from app import querygate
    kinds = ", ".join(task.kinds)
    return (
        f"\n\n🔴 **네 담당은 `{task.label}` 유형들뿐이다**: {kinds}\n"
        f"다른 유형의 사실을 보면 적어도 되지만 **담당 유형을 먼저 끝내라.**\n"
        f"\n🔴 **첫 검색은 반드시 이 꼴이다**: `{task.seed}`\n"
        f"넓게 시작해 판을 본 뒤 좁힌다 — 1차 결과의 제목·스니펫에서 본 "
        f"구체 낱말(선수명·감독명·현지어 표기·부상 부위)로 2차를 좁혀라.\n"
        f"⚠️ 검색어는 **{querygate.MAX_WORDS}낱말을 넘기지 마라** — 긴 문장 "
        f"질의는 결과를 0건으로 만든다(실측).\n"
        f"🔴 검색은 **{task.budget.search_cap}번**뿐이다: 씨앗 1 + 좁히기 1 + "
        f"(현지어 또는 각도 전환) 1. 네 번째는 없다.\n"
        f"⚠️ 네가 맡은 쪽은 **{task.team}**(상대 {task.opp})이다.\n")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **하위 과제 하나 — 코드가 찾고, LLM 은 한 번 읽는다**
# ══════════════════════════════════════════════════════════════════
#
# 지시서 2026-10-06 §1:
#
# > 에이전트 루프(LLM 이 검색어를 정하고 → 검색 → 다시 생각 → fetch → 다시 생각
# > → done)는 턴마다 추론 토큰을 쓰고 **40~88초**가 걸린다. 하위 8개 × 7턴이
# > 26분과 `budget_cut` 의 원인이다. 찾는 일은 **코드가**, 읽고 뽑는 일만
# > **LLM 이 한 번에** 하게 바꾼다.
#
# 여섯 단계:
#   1. 질의 생성(코드) — 씨앗 2개(영어 1 + 팀 현지어 1). 한국 리그는 한국어 2.
#   2. 검색(코드) — 질의마다 SearXNG(week) 1회. 5건 미만이면 Bing 1회 추가.
#   3. 거르기·재정렬(코드) — 도메인 등급 → 날짜 힌트 → 재정렬 → 상위 3건 fetch.
#   4. 본문 문단(코드) — BM25 20 → 재정렬 6 → 최대 18문단 · `[D1-P3]` 머리표.
#   5. 추출(LLM 1회) — 도구 없음 · max_tokens 4,000 · reasoning_effort=low.
#   6. 좁히기 2차(조건부 1회) — 0개이고 예산이 남으면 고유명사로 한 번 더.
#
# 🔴 **에이전트 루프 코드는 삭제하지 않는다** — 오픈월드 ⑥단(경기 찾기)이 쓴다.
#    ⚠️ 하위 과제 경로에서는 **부르지 않는다**(M128).


def extract_prompt(task: Any, kinds: list) -> str:
    """🔴 추출 한 번에 보내는 **규칙 글**(지시서 §1-5).

    > "아래 문단에서 담당 유형(`{유형 목록}`)의 변수만 JSON 으로 뽑아라.
    > `quote` 는 문단의 글자 그대로, `source` 는 머리표로"
    """
    return (
        "너는 아래 문단들에서 **그 경기의 변수만** 뽑는다. 웹에 닿을 수 없다.\n"
        "\n"
        f"🔴 담당 유형: {', '.join(str(k) for k in kinds)} — **그 유형만** 뽑는다.\n"
        "🔴 `quote` 는 **문단의 글자 그대로**다(한 글자도 바꾸지 않는다). "
        "지어낸 인용은 검증층이 잡아 버린다.\n"
        "🔴 `source` 는 문단 머리표(`[D1-P3]`)를 그대로 적는다 — 그것으로 "
        "URL·발행일을 되찾는다.\n"
        "⚠️ 문단에 없는 사실은 **쓰지 않는다.** 없으면 `variables` 를 빈 배열로 "
        "둔다 — 빈 것이 지어낸 것보다 낫다.\n"
        "🔴 도구는 없다. **한 번에** JSON 으로만 답한다.\n")


def _seeds(task: Any, game: dict) -> list[tuple[str, str]]:
    """🔴 ① 씨앗 질의 **2개** — `(질의, 언어)`(지시서 §1-1).

    > 씨앗 질의 2개(영어 1 + 팀 현지어 1). KBO·K리그·한국 대표팀은 한국어 2개.
    """
    from app import queries
    team = str(game.get("home") or "")
    opp = str(game.get("away") or "")
    if str(task.team_key or "") == str(game.get("away_id") or ""):
        team, opp = opp, team
    comp = queries.competition_short(game.get("league"))
    words = [str(w) for w in (getattr(task, "kinds", None) or ())][:1]
    word = words[0] if words else ""
    base = f"{team} {comp}".strip()
    out: list[tuple[str, str]] = [(f"{base} {word}".strip(), "en")]
    lang = team_lang(team) or first_lang(league=str(game.get("league") or ""),
                                        langs=tuple(game.get("langs") or ()))
    if lang and lang != "en":
        out.append((f"{team} {word}".strip(), lang))
    else:
        out.append((f"{team} {opp} {word}".strip(), "en"))
    return [(queries.slot_value(q), lg) for q, lg in out if str(q).strip()]


async def _find(task: Any, game: dict, *, chain, seen, net, seeds=None
                ) -> tuple[list[dict], list[str]]:
    """🔴 ②③④ — 검색·거르기·본문 문단. `(문단 묶음, 사유들)`.

    ⚠️ 여기에 **LLM 이 없다** — 그것이 §1 의 요지다.
    """
    from app import cells, datehint, domains, readtext
    from app.research import lead, rerank
    cfg = dict(_sub_cfg())
    why: list[str] = []
    hits: list = []
    for q, lang in (seeds if seeds is not None else _seeds(task, game)):
        if not task.budget.may_search():
            why.append(f"검색 상한({task.budget.search_cap})에 닿았다")
            break
        task.budget.search_used += 1
        try:
            async with lead.gate("searx"):
                got = await chain.query(q, lang=lang)
        except Exception as exc:                            # noqa: BLE001
            why.append(f"검색 실패 {q!r}: {exc}")
            continue
        why.append(f"질의 {q!r}({lang}) → {len(got)}건")
        hits += list(got or [])
    # ── ③ 거르기: 도메인 등급 → 날짜 힌트
    kept: list = []
    for h in hits:
        url = str(getattr(h, "url", "") or "")
        if not url or any(url == str(getattr(k, "url", "")) for k in kept):
            continue
        ok_d, _tier, said = domains.verdict(url, sport=str(game.get("sport") or ""))
        if not ok_d:
            why.append(f"도메인 거부 {url[:50]} — {said[:40]}")
            continue
        old, said_old = datehint.too_old(url, str(getattr(h, "snippet", "") or ""))
        if old:
            why.append(f"②층 — 받지 않는다: {said_old[:40]}")
            continue
        kept.append(h)
    # ── ③ 재정렬 1단 → 상위 N 건
    top = int(cfg.get("fetch_top") or 3)
    if kept:
        pairs = [f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
                 for h in kept]
        order, said_r = rerank.paragraphs(
            " ".join(str(k) for k in (getattr(task, "kinds", None) or ())), pairs)
        why.append(f"재정렬 — {said_r}")
        rank = {t: i for i, t in enumerate(order)}
        kept.sort(key=lambda h: rank.get(
            f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}", 999))
    docs: list[dict] = []
    for i, h in enumerate(kept[:top], 1):
        if not task.budget.may_fetch():
            why.append(f"열기 상한({task.budget.fetch_cap})에 닿았다")
            break
        task.budget.fetch_used += 1
        url = str(getattr(h, "url", "") or "")
        body = (seen.bodies.get(url) if seen is not None else "") or ""
        when = cells.doc_date(seen, url) if seen is not None else None
        if not body.strip():
            try:
                async with lead.gate("fetch"):
                    got = await net.get(url)
            except Exception as exc:                        # noqa: BLE001
                why.append(f"열기 실패 {url[:50]}: {exc}")
                continue
            if not getattr(got, "ok", False):
                why.append(f"열기 실패 {url[:50]}: ok=False")
                continue
            body, when = readtext.extract(getattr(got, "text", "") or "",
                                          url=url)
            # 🔴 저장은 **한 함수**다(§3) — 본문과 날짜를 같이 넣는다
            cells.store_doc(seen, url, body, published_at=when,
                            date_source="본문(하위 fetch · htmldate)")
        if not str(body).strip():
            why.append(f"본문을 못 얻었다 {url[:50]}")
            continue
        docs.append({"tag": f"D{i}", "url": url, "body": str(body),
                     "published_at": when,
                     "publisher": str(getattr(h, "publisher", "") or "")})
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **받은 뒤 날짜로 다시 거른다** — 실측 2026-10-06
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ ②층(`datehint`)은 **URL·스니펫**만 본다 — 날짜 힌트가 없으면 받는다
    #     (fail-open). 🔴 그래서 받아 보니 `2004-09-24`(위키 연혁)·
    #     `2017-07-13`(옛 기사) 문단이 추출에 들어갔고, 모델이 그 사실로 변수를
    #     만들었다(실측: `2022 FIFA World Cup qualification` · 2017년 감독 발언).
    #  🔴 **받은 뒤에는 진짜 날짜를 안다** — 그때 거르는 것이 맞다.
    #  ⚠️ 날짜를 **모르는 문서는 남긴다** — 검증층이 그 뒤를 본다(§12-c-1 이
    #     `soft` 로만 남긴다). 모르는 것과 낡은 것은 다르다(#3).
    kick = game.get("kickoff")
    if kick is not None:
        from datetime import timedelta
        from app import timefmt, verifylayer
        floor = timefmt.aware(kick)
        if floor is not None:
            floor = floor - timedelta(days=verifylayer.DATE_WINDOW_DAYS)
            fresh = []
            for d in docs:
                got = timefmt.aware(d.get("published_at"))
                if got is not None and got < floor:
                    why.append(f"낡은 문서 버렸다 — {got:%Y-%m-%d} "
                               f"(창 {verifylayer.DATE_WINDOW_DAYS}일) "
                               f"{str(d.get('url'))[:50]}")
                    continue
                fresh.append(d)
            # 🔴 **번호를 다시 매긴다** — 머리표가 문단과 어긋나면 안 된다
            for j, d in enumerate(fresh, 1):
                d["tag"] = f"D{j}"
            docs = fresh
    return docs, why


def paragraph_block(docs: list, kinds: list, *, cap: int = 0) -> tuple[str, dict]:
    """🔴 ④ 문단 묶음 + **머리표 → 출처** 표(지시서 §1-4).

    > 문서마다 BM25 상위 20 → 재정렬 상위 6 → 하위당 최대 18문단. 문단마다
    > `[D1-P3] (도메인, 발행일)` 머리표를 붙인다.
    """
    from app import readtext
    from app.research import rerank
    cap = cap or int(_sub_cfg().get("paras_max") or 18)
    want = " ".join(str(k) for k in (kinds or ()))
    lines: list[str] = []
    where: dict[str, dict] = {}
    for d in (docs or []):
        paras = readtext.paragraphs(str(d.get("body") or ""))
        got, _said = rerank.paragraphs(want, paras)
        for j, para in enumerate(got[:6], 1):
            if len(lines) >= cap:
                break
            tag = f"[{d['tag']}-P{j}]"
            host = str(d.get("publisher") or "").strip() or _host(d.get("url"))
            when = d.get("published_at")
            lines.append(f"{tag} ({host}, {when or '발행일 없음'}) {para}")
            # 🔴 **문단 글자도 담는다** — 인용을 되맞춰 머리표를 찾는다
            where[tag] = {"url": d.get("url"), "published_at": when,
                          "text": para}
    return "\n".join(lines), where


def _where_of(row: dict, where: dict) -> dict | None:
    """🔴🔴 그 변수의 **인용이 어느 문단에 있나** — 머리표·URL·발행일을 돌려준다.

    ⚠️ 모델이 적은 `source`·`url` 을 **먼저 믿지 않는다**(실측 2026-10-06: 도메인을
       적었다). 🔴 인용으로 찾으면 §5-1(인용이 본문에 있나)이 **여기서** 같이
       통과하고, 그 뒤 검증층이 다시 본다(두 번 보는 것이 맞다).
    ⚠️ 못 찾으면 `None` — 문단에 없는 인용은 **지어낸 것**이다.
    """
    said = _norm_q(row.get("quote"))
    if said:
        for tag, box in where.items():
            if said in _norm_q(box.get("text")):
                return {**box, "tag": tag}
    # 🔴 **대체**: 모델이 머리표를 바르게 적었으면 그것도 받는다
    tag = str(row.get("source") or "").strip()
    for key in (tag, f"[{tag}]"):
        if key in where:
            return {**where[key], "tag": key}
    return None


def _norm_q(text: object) -> str:
    """🔴 인용 대조용 정규화 — 공백·따옴표만 걷는다(글자는 안 바꾼다)."""
    said = str(text or "")
    for ch in '"\u201c\u201d\u2018\u2019\'':
        said = said.replace(ch, "")
    return " ".join(said.split()).lower()


def _host(url: object) -> str:
    said = str(url or "")
    return said.split("/")[2] if said.count("/") >= 2 else said


def _sub_cfg() -> dict:
    from app import rules
    return dict((rules.llm_budget().get("per_subtask") or {}))


async def run_subtask(task: Any, *, seen, chain, net, game: dict,
                      match_key: str = "", budget: Any = None,
                      funnel: Any = None) -> tuple[list, str]:
    """🔴🔴 **하위 과제 하나** — 지시서 2026-10-06 §1. `(변수들, 사유)`.

    🔴 **LLM 은 ⑤ 추출 한 번**(조건부 ⑥ 에서 한 번 더) — 루프가 없다.
    ⚠️ `agentloop.run` 을 **부르지 않는다**(M128) — 그 코드는 오픈월드 ⑥단
       (경기 찾기)에만 남는다.
    """
    from app import agentloop, solar
    from app.reasons import Reason
    cfg = dict(_sub_cfg())
    kinds = [str(k) for k in (getattr(task, "kinds", None) or ())]
    notes: list[str] = []

    docs, why = await _find(task, game, chain=chain, seen=seen, net=net)
    notes += why
    if not docs:
        return [], f"{task.name}: 받은 문서 0건 · " + " | ".join(notes[-4:])

    block, where = paragraph_block(docs, kinds)
    if not block.strip():
        return [], f"{task.name}: 문단 0개(본문은 받았다) · " + " | ".join(notes[-3:])
    notes.append(f"문단 {len(block.splitlines())}개 · 문서 {len(docs)}건")

    # ── ⑤ 추출 — **LLM 한 번**. 🔴 도구 없음 · 스키마 강제.
    got, said = await _extract(task, kinds, block, where, game=game,
                              match_key=match_key, budget=budget, seen=seen)
    notes.append(said)

    # ── ⑥ 좁히기 2차(조건부 · 최대 1회) — 🔴 LLM 이 질의를 만들지 않는다
    if not got and task.budget.may_search():
        words = narrow_words([{"title": d.get("publisher"),
                               "snippet": d.get("body", "")[:200]}
                              for d in docs])
        if words:
            team = str(game.get("home") or "")
            if str(task.team_key or "") == str(game.get("away_id") or ""):
                team = str(game.get("away") or "")
            seeds = [(narrow_query(team, words), "en")]
            notes.append(f"⑥ 좁히기 2차 — 고유명사 {words[:2]} 로 한 번 더")
            more, why2 = await _find(task, game, chain=chain, seen=seen,
                                     net=net, seeds=seeds)
            notes += why2
            if more:
                blk2, where2 = paragraph_block(more, kinds)
                if blk2.strip():
                    got, said2 = await _extract(
                        task, kinds, blk2, where2, game=game,
                        match_key=match_key, budget=budget, seen=seen)
                    notes.append(f"2차 {said2}")
    if funnel is not None and not got:
        funnel.drop(Reason.AGENT_ZERO, "agent_vars")
    return got, f"{task.name}: " + " | ".join(notes[-6:])


async def _extract(task: Any, kinds: list, block: str, where: dict, *,
                   game: dict, match_key: str, budget: Any, seen
                   ) -> tuple[list, str]:
    """🔴 ⑤ 추출 **한 번** — 지시서 §1-5. `(변수들, 사유)`.

    > 출력은 `done` 스키마의 `variables` 배열과 같은 꼴(M47). **도구 없음.**
    > `max_tokens` 4,000 · `reasoning_effort=low` · 타임아웃 120초 · 재시도 1회.
    """
    import asyncio

    from app import agentloop, cells, solar
    cfg = dict(_sub_cfg())
    msgs = [{"role": "system", "content": extract_prompt(task, kinds)},
            {"role": "user", "content": block}]
    try:
        got = await asyncio.to_thread(
            solar.chat, msgs, schema=agentloop.output_schema(),
            budget=budget, match=match_key,
            max_tokens=int(cfg.get("extract_max_tokens") or 4_000),
            # 🔴🔴 **추론을 끈다** — 실측 2026-10-06: `low` 는 상한 4,000 을
            #    전부 추론에 쓰고 `content` 를 **0자** 냈다(하위 7/8 이 그래서
            #    빈 글이었다). ⚠️ 상한을 올리는 것은 §8 금지다.
            reasoning_effort=str(cfg.get("extract_reasoning_effort")
                                 or "minimal"),
            timeout=int(cfg.get("extract_timeout_sec") or 120),
            retries=int(cfg.get("extract_retries") or 1))
    except solar.SolarUnavailable as exc:
        return [], f"추출 실패 — {exc}"
    text = str(((got.get("choices") or [{}])[0].get("message") or {})
               .get("content") or "")
    box, said = agentloop._json_in(text)
    if box is None:
        return [], f"추출 JSON 을 못 읽었다 — {said}"
    # 🔴 **머리표로 URL·발행일을 되찾는다**(지시서 §1-4) — 모델이 URL 을 적지
    #    않으므로 `source` 가 그 길이다. ⚠️ 모르는 머리표는 **버린다**.
    rows, dropped = [], []
    for raw in (box.get("variables") or []):
        row = dict(raw or {})
        # ══════════════════════════════════════════════════════════
        # 🔴🔴 **머리표를 인용으로 되찾는다** — 실측 2026-10-06
        # ══════════════════════════════════════════════════════════
        #
        #  ⚠️ 모델이 `url` 칸에 **도메인**을 적었다(`en.wikipedia.org`) —
        #     머리표가 아니다. 🔴 그래서 후보 8개가 전부 버려졌다.
        #  🔴 **글자를 믿지 않는다**: 그 인용이 **어느 문단에 있나**를 코드가
        #     찾는다. 그러면 머리표·URL·발행일이 한꺼번에 정해지고, §5-1
        #     (인용이 본문에 있나)이 **그 자리에서** 같이 통과한다.
        #  ⚠️ 못 찾으면 **버린다** — 문단에 없는 인용은 지어낸 것이다.
        hit = _where_of(row, where)
        if hit is None:
            dropped.append(str(row.get("id") or "?"))
            continue
        row["url"] = hit.get("url")
        row["source"] = hit.get("tag")
        rows.append(row)
    dates = {str(v.get("url")): v.get("published_at")
             for v in where.values() if v.get("url")}
    out, why = agentloop._vars_from({"variables": rows}, dates=dates)
    said_all = (f"추출 — 후보 {len(out)}개"
                + (f" · 🔴 인용을 문단에서 못 찾아 {len(dropped)}개 버렸다"
                   f"({dropped[:3]})" if dropped else ""))
    return out, f"{said_all} · {why}" if why else said_all
