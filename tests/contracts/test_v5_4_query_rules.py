"""🔴🔴 **§4 — 검색어 규칙: 넓게 → 좁게**(지시서 2026-10-05 딥서치 재구축).

> Anthropic 다중 에이전트 실측의 결론을 그대로 적용한다: 에이전트는 처음부터
> **너무 구체적인 검색어를 던져 결과를 죽인다.** 넓게 시작해 판을 본 뒤 좁힌다.
>
> 1. **1차(씨앗)**: §2 표의 템플릿 그대로 — `{팀} {상대} {유형 핵심어 1개}`,
>    **3~6단어**. 하위 프롬프트에 *"첫 검색은 반드시 이 꼴"* 로 박는다.
> 2. **2차(좁히기)**: 1차 결과의 제목·스니펫에서 본 **구체 낱말**(선수명·감독명·
>    현지어 표기·부상 부위)로 좁힌다.
> 3. **거부 규칙**(코드, search 도구 안):
>    · **10단어 초과 → `query_too_long` 거부**(M61). 실측: 긴 문장 질의가 0건.
>    · 3요소 미만(기존 `query_too_bare`) 유지 — **씨앗 템플릿은 자동 통과**.
>    · 같은 하위 안 동일 질의 → `duplicate_query`(기존 유지).
> 4. **언어 순서**: 1차 영어 → 2차에서 팀 현지어. KBO·K리그·한국 대표팀은
>    **1차부터 한국어 허용**.
> 5. **질의 수**: 하위당 `search 3` = 씨앗 1 + 좁히기 1 + (현지어 또는 각도 전환) 1.
>    세 번 모두 빈손이면 그 유형군은 `empty` — **네 번째 검색은 없다.**
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# M61 — 10단어 초과는 `query_too_long`
# ══════════════════════════════════════════════════════════════════
def test_M61_열_낱말_초과는_거부된다():
    from app import querygate
    from app.reasons import Reason
    assert hasattr(Reason, "QUERY_TOO_LONG"), (
        "🔴 `query_too_long` 사유가 없다 — 긴 질의가 0건을 만들었다(실측)")
    assert hasattr(querygate, "MAX_WORDS") and querygate.MAX_WORDS == 10, (
        "🔴 `querygate.MAX_WORDS = 10` 이 이름으로 없다")
    long_q = ("France Belgium UEFA Nations League October 2026 preview "
              "lineups prediction team news injury")
    ok, reason, why = querygate.gate(long_q, parts={"team": "France"})
    assert not ok and reason is Reason.QUERY_TOO_LONG, (ok, reason, why)
    assert "10" in why and "낱말" in why, why


def test_M61_씨앗_템플릿은_자동_통과한다():
    """🔴 3~6낱말 씨앗은 요소가 2개여도 통과한다(지시서 §4-3)."""
    from app.research import subtasks
    from app import querygate
    ref = {"home": "France", "away": "Belgium", "home_key": "team:000081",
           "away_key": "team:000021", "sport": "soccer",
           "league": "UEFA Nations League A Grp. 1", "langs": ("en", "fr")}
    for s in subtasks.split(ref):
        ok, reason, why = querygate.gate(s.seed, parts={"team": s.team},
                                         seed=True)
        assert ok, f"🔴 씨앗 `{s.seed}` 가 거부됐다: {why}"


def test_M61_씨앗이_아니면_세_요소를_요구한다():
    """🔴 기존 `query_too_bare` 는 **그대로 산다** — 씨앗만 면제다."""
    from app import querygate
    from app.reasons import Reason
    ok, reason, _ = querygate.gate("France news", parts={"team": "France"})
    assert not ok and reason is Reason.QUERY_TOO_BARE, (ok, reason)


def test_M61_길이_검사가_요소_검사보다_먼저다():
    """🔴 긴 질의는 요소가 많아도 **길이로** 떨어진다(사유가 고칠 곳을 가린다)."""
    from app import querygate
    from app.reasons import Reason
    q = ("France Belgium UEFA Nations League standings stakes preview "
         "October 5 2026 Stade de France weather")
    ok, reason, _ = querygate.gate(
        q, parts={"team": "France", "opponent": "Belgium",
                  "competition": "UEFA Nations League A Grp. 1"})
    assert not ok and reason is Reason.QUERY_TOO_LONG, (ok, reason)


# ══════════════════════════════════════════════════════════════════
# 넓게 → 좁게 · 언어 순서 · 질의 수
# ══════════════════════════════════════════════════════════════════
def test_r4_좁히기_낱말을_결과에서_뽑는다():
    """🔴 2차는 **1차 결과의 제목·스니펫**에서 구체 낱말을 가져온다."""
    from app.research import subtasks
    assert hasattr(subtasks, "narrow_words"), (
        "🔴 `subtasks.narrow_words(결과들)` 이 없다 — 2차를 지어내게 된다")
    hits = [{"title": "Ronaldo leaves Portugal camp",
             "snippet": "Cristiano Ronaldo has left the national team camp"},
            {"title": "Nothing useful", "snippet": "the the the"}]
    got = subtasks.narrow_words(hits)
    assert "Ronaldo" in got, got
    # 🔴 흔한 낱말은 **안 뽑는다** — 좁히는 뜻이 없다
    assert "the" not in [w.lower() for w in got], got


def test_r4_좁히기_질의도_낱말_상한을_지킨다():
    from app.research import subtasks
    from app import querygate
    got = subtasks.narrow_query("France Belgium injury news",
                                ["Ronaldo", "Mbappe", "Hernandez", "Dembele"])
    assert len(got.split()) <= querygate.MAX_WORDS, got
    assert "Ronaldo" in got, got


def test_r4_한국_리그는_1차부터_한국어를_허용한다():
    """🔴 §4-4: *"KBO·K리그·한국 대표팀은 1차부터 한국어 허용."*"""
    from app.research import subtasks
    assert subtasks.first_lang(league="KBO", langs=("ko", "en")) == "ko"
    assert subtasks.first_lang(league="K리그1", langs=("ko",)) == "ko"
    # 🔴 그 밖은 **영어가 1차**다
    assert subtasks.first_lang(league="UEFA Nations League",
                               langs=("fr", "en")) == "en"
    assert subtasks.first_lang(league="NPB", langs=("ja", "en")) == "en"


def test_r4_네_번째_검색은_없다():
    """🔴 §4-5: *"하위당 search 3 … **네 번째 검색은 없다**."*"""
    from app.research import subtasks
    ref = {"home": "France", "away": "Belgium", "home_key": "team:000081",
           "away_key": "team:000021", "sport": "soccer",
           "league": "UEFA Nations League A Grp. 1", "langs": ("en", "fr")}
    s = subtasks.split(ref)[0]
    for _ in range(3):
        assert s.budget.may_search()
        s.budget.search_used += 1
    assert not s.budget.may_search(), "🔴 네 번째 검색이 허용된다"


def test_r4_프롬프트가_첫_검색_꼴을_박는다():
    """🔴 **배선**(#2) — 하위 프롬프트가 씨앗 꼴을 요구한다."""
    from app.research import subtasks
    assert hasattr(subtasks, "prompt_tail"), (
        "🔴 `subtasks.prompt_tail(하위)` 가 없다 — 담당·검색어 규칙을 전할 곳")
    ref = {"home": "France", "away": "Belgium", "home_key": "team:000081",
           "away_key": "team:000021", "sport": "soccer",
           "league": "UEFA Nations League A Grp. 1", "langs": ("en", "fr")}
    s = subtasks.split(ref)[0]
    said = subtasks.prompt_tail(s)
    assert s.seed in said, "🔴 씨앗 질의가 프롬프트에 없다"
    assert "담당" in said and s.kinds[0] in said, said
    assert "10" in said, "🔴 낱말 상한을 안 알려 준다"
