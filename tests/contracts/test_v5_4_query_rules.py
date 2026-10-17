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

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import ast
import inspect
def test_좁히기_2차가_사라졌다() -> None:
    """🔴🔴 **딥서치 삭제**(사용자 지시 2026-10-17) — 종전 두 계약이 있던 자리다.

    `test_r4_좁히기_낱말을_결과에서_뽑는다`·`…2차_질의를_만든다` 는
    `subtasks.narrow_words`·`narrow_query` 가 **코드로 2차 질의를 짜는** 것을
    지켰다. 🔴 그 길(= `s4_extract._narrow` → `s3_docs.regather`)을 지웠으므로
    **되살아나지 않는 것**을 지킨다. 질의는 `s4b_gapsearch.ask`(LLM) 하나가 쓴다.
    """
    from app.research import subtasks
    for one in ("narrow_words", "narrow_query", "local_name"):
        assert not hasattr(subtasks, one), f"🔴 `subtasks.{one}` 가 되살아났다"
    raw = (ROOT / "app/core/stages/s4_extract.py").read_text(encoding="utf-8")
    # 🔴 **D46** — 독스트링·주석을 뺀 **코드만** 본다(지운 까닭을 글로 남기는
    #    것과 그것을 **부르는** 것은 다르다).
    tree = ast.parse(raw)
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and ast.get_docstring(n):
            n.body = n.body[1:]
    assert "_narrow" not in ast.unparse(tree), "🔴 좁히기 2차가 되살아났다"
    assert "좁히기 2차는 없다" in raw, "🔴 그 사실을 수첩에 안 적는다(#3)"




def test_r4_현지어_질의가_그_리그_언어로_나간다():
    """🔴 §4-4(*"1차 영어 → 2차에서 팀 현지어"*) + §3-1(*"현지어+영어"*).

    ⚠️ 종전엔 `first_lang` 으로 *"KBO·K리그는 1차부터 한국어"* 만 셌다. 🔴 그
       함수는 **아무 데서도 안 불렸다**(1차가 `"en"` 으로 박혀 있었다) — 안 이어진
       코드라 **지웠다**(CLAUDE.md #2).
    🔴🔴 실사고 2026-10-10: 현지어를 손으로 적은 목록(`LOCAL_FIRST`)으로만 골라
       fotmob 표기 **`K-League 1`** 이 안 걸렸다 → 강원–부천 검색이 **영어뿐**이고
       한국어 매체의 새 사실을 **한 건도** 못 집었다. 그래서 `local_lang_of` 가
       `queries.langs_for`(이름표·자동 등록·CLDR)에 묻는다.
    """
    from app.research import subtasks
    # 🔴 fotmob·ESPN 표기로도 현지어가 서야 한다(그게 실사고의 핵이다)
    assert subtasks.local_lang_of(league="K-League 1",
                                  teams=("Gangwon FC", "Bucheon FC 1995")) == "ko"
    assert subtasks.local_lang_of(league="K리그1") == "ko"
    assert subtasks.local_lang_of(league="KBO") == "ko"
    assert subtasks.local_lang_of(league="J. League",
                                  teams=("Kashiwa Reysol",)) == "ja"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§4-4 "1차는 영어"는 코드 질의의 규칙이었다** — 딥서치 삭제(사용자 지시 2026-10-17)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 그 규칙은 `s3_docs.queries_for`(코드가 만드는 질의 다발)에 있었고
    #     그 함수를 지웠다. 🔴 질의를 쓰는 곳은 이제 **LLM 하나**이고, 언어는
    #     `s4b_gapsearch.langs_of()` 가 정한다 — **현지어가 먼저**다(사용자
    #     지시 2026-10-14 이후 그 순서다). 그래서 글자 검사를 **그쪽**으로 옮긴다.
    said = (ROOT / "app" / "core" / "stages"
            / "s4b_gapsearch.py").read_text(encoding="utf-8")
    assert "현지어를 먼저" in said, "🔴 질의 프롬프트가 현지어를 먼저 안 쓴다"
    assert "두 팀의 나라 말로도" in said, "🔴 두 팀 나라 말을 안 요구한다"


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


