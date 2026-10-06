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




def test_L1_L2_L3_가_전부_부르는_곳이_있다():
    """🔴 만든 것은 부르는 곳이 있어야 한다 — `L3` 가 **0곳**이었다."""
    from app.extract import TASKS
    have = set(WANT.values())
    missing = sorted(set(TASKS) - have - {"ASK"})
    # ⚠️ `ASK:<유형>` 은 카탈로그 세포가 건다(여기 표에 없다) — 그것만 예외다
    assert not missing, f"부르는 곳이 없는 추출기: {missing}"












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
