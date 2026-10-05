"""🔴🔴 **추출기 배선** — §17-b L1~L3 가 **부르는 곳**이 있나(CLAUDE.md #2).

사용자 기술 지시 2026-10-03:
> ③ 추출기 배선 — qwen3:8b로 ①만, 인용 검증 포함.
> *"추출기(L1~L3)가 미배선이라 '43전 4승', '준결승 0-2 패', '감독 반드시
>   이긴다'가 문장으로만 남고 유형이 안 붙는다."*

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-03 — 그 지적이 맞았다
══════════════════════════════════════════════════════════════════

```
L1: extract_tasks 에 걸린 자리 1곳
L2: extract_tasks 에 걸린 자리 1곳
L3: extract_tasks 에 걸린 자리 **0곳**        ← 만들어 두고 안 썼다

lineup           본문열기 6 · 추출기 ['L1']
intent           본문열기 4 · 추출기 ['L2']
coach            본문열기 0 · 추출기 🔴 없다     ← 규칙 파서 하나뿐
starter_recent   본문열기 0 · 추출기 🔴 없다     ← 규칙 파서 하나뿐
```

⚠️ 규칙 파서의 정규식이 안 맞으면 그 세포는 **영영 0** 이었다. 실측(KBO):
   문서 147건을 열었는데 사실이 **4건**이었다.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app import llm, searchcells

_KW = dict(team="LG Twins", league="KBO", day=date(2026, 10, 3), game_id=1,
           starts=datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc))

#: 🔴 세포마다 **어떤 추출기**가 걸려야 하나. ⚠️ 목록을 손으로 늘리지 않게,
#   `CELL_PLAN` 이 원본이고 여기는 **기대값**만 적는다.
WANT = {"lineup": "L1", "intent": "L2", "coach": "L2",
        "starter_recent": "L1", "standings": "L3"}


@pytest.mark.parametrize("name,task", sorted(WANT.items()))
def test_세포마다_추출기가_걸려_있다(name, task):
    """🔴 **본문을 열고** 추출기를 건다 — 둘 다 있어야 뜻이 있다.

    ⚠️ `open_body=False` 면 추출기를 걸어도 **본문이 없어** 안 돈다.
    """
    kw = dict(_KW)
    if name == "lineup":
        kw["now"] = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)
    cell, _ = getattr(searchcells, f"{name}_cell")(**kw)
    tasks = {t for s in cell.sources for t in (s.extract_tasks or ())}
    assert task in tasks, f"{name} 세포에 `{task}` 추출기가 없다 (있는 것: {tasks})"
    opened = [s for s in cell.sources if s.open_body]
    assert opened, f"{name} 세포가 **본문을 안 연다** — 추출기가 돌 자료가 없다"


def test_L1_L2_L3_가_전부_부르는_곳이_있다():
    """🔴 만든 것은 부르는 곳이 있어야 한다 — `L3` 가 **0곳**이었다."""
    from app.extract import TASKS
    have = set(WANT.values())
    missing = sorted(set(TASKS) - have - {"ASK"})
    # ⚠️ `ASK:<유형>` 은 카탈로그 세포가 건다(여기 표에 없다) — 그것만 예외다
    assert not missing, f"부르는 곳이 없는 추출기: {missing}"


def test_CELL_PLAN_이_함수를_직접_든다():
    """🔴 문자열로 부르면 **배선 계약이 호출부를 못 본다**(실측 2026-10-03).

    ⚠️ 종전 `getattr(searchcells, f"{name}_cell")` 로는 새 세포가 *"부르는 곳이
       없다"* 로 빨개졌다 — 옳은 지적이다. 문자열 간접 호출은 사람도 기계도 흐름을
       못 따라간다.
    """
    from app.analyze import CELL_PLAN
    for row in CELL_PLAN:
        # 🔴 다섯째 칸은 `opp_in_query`(질의에 상대를 넣나) — 2026-10-04
        assert len(row) == 5, row
        assert callable(row[3]), row
        assert isinstance(row[4], bool), row


def test_순위_세포는_공식_깊이가_있으면_안_돈다():
    """🔴 §19-b-4 — 검색은 **대체**다. 공식 순위표가 더 정확하다.

    ⚠️ 둘 다 돌리면 같은 사실을 두 번 세고(§12-c-4) 예산도 두 배다.
    """
    from types import SimpleNamespace as N

    from app.analyze import _has_official_standings
    f = N(question_id="standings:KBO:LG Twins", team="LG Twins", value={})
    assert _has_official_standings([f], "LG Twins")
    # 🔴 **다른 팀 것은 안 센다**
    g = N(question_id="standings:KBO:Kia", team="Kia Tigers", value={})
    assert not _has_official_standings([g], "LG Twins")
    # 🔴 팀 칸이 비면 **리그 전체 표**다 — 그것도 공식 순위다
    h = N(question_id="standings:KBO", team=None, value={})
    assert _has_official_standings([h], "LG Twins")
    assert not _has_official_standings([], "LG Twins")


def test_질의가_언어마다_제_낱말을_쓴다():
    """🔴🔴 실측 2026-10-03: **영어 질의에 한국어 낱말**이 들어갔다.

    ```
    [lang:en] LG Twins 선발 라인업 Oct 3      🔴 영어 매체는 이 글자를 안 쓴다
    ```
    ⚠️ 이 저장소는 **팀 이름**에서 같은 병을 이미 고쳤다(*"현지 약칭은 그 나라
       언어 질의에 붙는다"*). 핵심어는 그때 안 고쳤다 — 같은 줄에 있는데도.
    """
    kw = dict(_KW, now=datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc))
    cell, _ = searchcells.lineup_cell(**kw)
    for s in cell.sources:
        if s.lang == "en":
            assert "선발" not in (s.query or ""), s.query
            assert "lineup" in (s.query or ""), s.query
        if s.lang == "ko":
            assert "선발" in (s.query or ""), s.query


def test_질의가_6낱말_상한을_지킨다():
    """🔴 §12-b — 질의는 **1~6낱말**이다(`llm.query_ok`).

    ⚠️ 실측 2026-10-03: 순위 핵심어를 `순위 매직넘버 잔여경기` 로 썼더니 팀명·날짜가
       붙어 7낱말이 되어 변형 여섯 중 **셋이 통째로 버려졌다.** 상한은 규칙이고
       핵심어가 그 상한에 맞춰야 한다.
    """
    for name in WANT:
        kw = dict(_KW)
        if name == "lineup":
            kw["now"] = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)
        cell, _ = getattr(searchcells, f"{name}_cell")(**kw)
        assert cell.sources, f"{name}: 쓸 검색어가 0건이다"
        for s in cell.sources:
            assert llm.query_ok(s.query or ""), (name, s.query)


def test_인용이_Fact_에_있으면_규칙이_찾는다():
    """🔴🔴 **그릇 때문에 사실을 잃었다**(실측 2026-10-03).

    카드가 *"감독 발언 원문이 없다 — 낱말을 대조할 수 없다"* 를 **일곱 번** 적었다.
    🔴 그런데 인용은 **있었다**:

    ```
    [bb] intent:KBO:LG Twins ← We can't avoid getting hit. So we have to take
                               control and attack first.
    ```
    ⚠️ `parse_intent_body` 는 `Fact(value=<인용 문자열>, quote=<인용>)` 로 넣는데
       `classify_fact` 는 `value` 가 dict 가 아니면 **빈 dict** 로 뒀다. 자료가
       아니라 **그릇이 문제였다** — 같은 사실의 다른 주머니를 안 열어 본 것이다.
    """
    from types import SimpleNamespace as N

    from app import classify
    g = classify.Game(home="LG Twins", away="Kia Tigers",
                      sport="baseball", league="KBO")
    q = "We can't avoid getting hit. So we have to take control and attack first."
    f = N(question_id="intent:KBO:LG Twins:2026-10-03", value=q, quote=q,
          team="LG Twins", hardness="likely", published_at=None,
          source="http://x", player_name=None)
    got = classify.classify_fact(f, g)
    assert any(c.direction for c in got), [c.undecided for c in got]


def test_감독_발언_낱말표가_전_언어다():
    """🔴🔴 사용자 지시 2026-10-03: *"야구뿐만 아니라 **전경기**다."*

    ⚠️ 실측: 영어 낱말이 `best lineup`·`full strength` 둘뿐이라 영어 인용이
       **어느 갈래도 안 맞아** 미결정이 됐다. 인용은 있었고 **표가 좁았다.**
    🔴 한 갈래에 한국어 밖 낱말이 **셋 이상** 있어야 한다 — 하나로는 못 걸린다.
    """
    import re as _re

    from app import rules
    words = (rules.variable_types().get("lineup_intent") or {})["intent_words"]
    hangul = _re.compile(r"[가-힣]")
    for side in ("best", "rest"):
        non_ko = [w for w in words[side] if not hangul.search(str(w))]
        assert len(non_ko) >= 3, (side, non_ko)
