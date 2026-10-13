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

import datetime as _dt

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
    #: 🔴🔴 **그 하위가 쓸 개념 낱말들**(`search_words.yaml` 의 열쇠) — §3-1
    #
    #  ⚠️ 비면 `kinds` 에서 유도한다(A~D 가 그렇다). 🔴 F 는 표에 적어 둔다 —
    #     실측 2026-10-10: `결장` 은 3건인데 `복귀` 는 18건 · `선발 명단` 은
    #     16건이었다(개념에 따라 **수확이 다섯 배** 갈린다).
    words: tuple[str, ...] = ()
    #: 🔴🔴 **그 하위의 발행일 창(시간)** — 사용자 지시 2026-10-10(재작성) §3-1
    #
    #  > 하위 과제 F … 킥오프 기준 **72시간 안**.
    #
    #  🔴 `0` 이면 **기본 창**(`s5_verify.DATE_WINDOW_DAYS` 7일)을 쓴다.
    #  ⚠️ 창을 코드에 적지 않는다 — `config/subtask_groups.yaml` 의
    #     `window_hours:` 가 원본이다(사본 금지).
    window_hours: int = 0


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
                # 🔴 §3-1 — 그 하위의 발행일 창(F 는 72시간)과 개념 낱말
                window_hours=int(row.get("window_hours") or 0),
                words=tuple(str(x) for x in (row.get("words") or ())),
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
    if local:
        return local[0]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **P4 — 구단은 나라 코드가 없다**(수정 지시 2026-10-13 밤 P4)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-13: ACL 구단 **일곱 팀 전부** `team_lang` 이 빈 글자였다
    #     (이름표의 나라 코드는 **대표팀**에만 있다). 그래서 꽁안 하노이에
    #     베트남어 질의가 **한 번도** 안 나갔다(문서 1건).
    #  🔴 그 팀의 **국내 리그**는 안다(자동 등록 · P1) — 그 리그의 `langs` 가
    #     CLDR 로 푼 현지어다. 그것을 쓴다(지어내지 않는다 · 표가 든다).
    from app.core import autoleague as _al
    from app.core import offsets as _off
    key, _why = _off.league_of(said)
    if not key:
        return ""
    rows = [str(x) for x in (dict(_al.load(key) or {}).get("langs") or [])
            if str(x) and str(x) != "en"]
    if rows:
        return rows[0]
    # 🔴 손 표(`config/sources/<리그>.yaml`)의 `lang` 도 본다 — J1·K1 처럼
    #    자동 등록이 아니라 손으로 적어 둔 리그가 거기 있다.
    from app.core.search import sources as _sr
    said_tab = dict(_sr.table(key) or {})
    rows2 = [str(x) for x in (said_tab.get("lang") or [])
             if str(x) and str(x) != "en"]
    return rows2[0] if rows2 else ""


def local_lang_of(*, league: str, teams: tuple | list = ()) -> str:
    """🔴🔴 **그 경기의 현지어** — 없으면 빈 글자. 사용자 지시 2026-10-10 §3-1.

    > 하위 과제 F … 팀마다, 킥오프 기준 72시간 안, **현지어+영어**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **언어는 `queries.langs_for` 가 안다 — 손 목록을 보지 않는다**
    ══════════════════════════════════════════════════════════════════

    ⚠️ 실사고 2026-10-10: 현지어를 `LOCAL_FIRST`(손으로 적은 한글 이름 다섯)로만
       골랐다. 그런데 fotmob 은 대회를 **`K-League 1`** 이라고 적는다 — 그 글자가
       목록에 없어서 강원–부천 검색이 **영어뿐**이었고, 한국어 매체에만 있는
       새 사실(황문기 병역 복귀 등)을 **한 건도 못 집었다**.
    🔴 `queries.langs_for` 는 이미 안다: `K-League 1`→`ko`(팀으로 되물어) ·
       인도네시아 수퍼리그→`id`(자동 등록) · 일본→`ja` · 이탈리아→`it`.

    ⚠️ **1차 질의는 영어다**(§4-4) — 이 함수는 **2차 현지어 질의**의 언어다.
       🔴 §4-4 의 *"한국 리그는 1차부터 한국어 허용"* 은 그 2차가 지킨다(1차를
          현지어로 바꿨더니 고정물의 녹음이 전부 빗나갔다 · 2026-10-10).
       ⚠️ 그래서 `first_lang` 은 **지웠다** — 부르는 곳이 없는 함수는 없는 코드
          보다 나쁘다(CLAUDE.md #2).
    """
    try:
        from app import queries
        rows, _why = queries.langs_for(str(league or ""),
                                       *[str(x) for x in (teams or ())])
        got = next((x for x in rows if x and x != "en"), "")
    except Exception:                                       # noqa: BLE001
        got = ""
    if got:
        return got
    # 🔴 손 목록은 **퇴로**로만 남긴다(그 다섯은 오래 측정된 이름이다)
    return "ko" if any(w and w in str(league or "") for w in LOCAL_FIRST) else ""


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






















def _sub_cfg() -> dict:
    from app import rules
    return dict((rules.llm_budget().get("per_subtask") or {}))





# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **옛 하위 과제 경로를 지웠다** — 사용자 지시 2026-10-06 ⑧
# ══════════════════════════════════════════════════════════════════
#
# 지운 것: `run_subtask`(에이전트 루프 호출)·`_find`·`_seeds`·`paragraph_block`·
# `extract_prompt`·`prompt_tail`·`_agent_inp`·`_where_of`.
# 🔴 그 일을 v6 가 한다: 찾기 `s3_docs`, 문단·추출 `s4_extract`(루프 없음).
# ⚠️ **남긴 것**은 v6 가 부르는 부품뿐이다: `groups`·`split`·`Subtask`·`Budget`·
#    `comp_short`·`team_lang`·`first_lang`·`narrow_words`·`narrow_query`.


def local_name(name: str, lang: str) -> str:
    """🔴🔴 그 언어로 쓴 **팀 이름**. 없으면 받은 이름 그대로(§3-1 "현지어").

    ⚠️ 실사고 2026-10-10: 한국어 질의를 **로마자 이름**으로 던졌다
       (`Gangwon FC Bucheon FC 1995 결장`). 한국 매체는 `강원`·`부천`이라 쓴다 —
       그래서 한국어 질의가 나갔는데도 **한국 기사를 못 집었다**.
    🔴 이름은 **이름표**(`teamref`)가 든다(사본 금지) — 여기서 짓지 않는다.
    🔴 **짧은 표기를 고른다** — 매체는 정식명보다 약칭을 쓴다(`강원 FC` 보다 `강원`).
    """
    said = str(name or "").strip()
    one = str(lang or "").strip()
    if not said or not one:
        return said
    try:
        from app import teamref
        key, _why = teamref.key_of(said)
        ref = teamref.registry().teams.get(key) if key else None
    except Exception:                                       # noqa: BLE001
        return said
    rows = [str(x) for x in ((getattr(ref, "names", None) or {}).get(one) or [])
            if ":" not in str(x)]
    # 🔴 짧은 것부터 — ⚠️ 너무 짧으면(한 글자) 엉뚱한 결과가 쏟아진다
    rows = sorted((x for x in rows if len(x) >= 2), key=len)
    return rows[0] if rows else said
