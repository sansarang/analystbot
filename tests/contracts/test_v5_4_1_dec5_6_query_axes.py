"""🔴🔴 **결정 ⑤ 라운드 이름은 데이터 · ⑥ 경기장은 조건부**.

사용자 결정 2026-10-04:

> **⑤** 라운드 이름(`NLDS`·`ALDS`·`Wild Card`·`CS`·`日本シリーズ`·`準決勝`·
> `결승`·`Final`)을 **대회 별칭 표에 데이터로** 넣는다. **코드 분기가 아니라
> 설정 한 칸이다.**
>
> **⑥** 허용하되 조건을 단다. 경기장은 **`venue_weather` 유형 검색어에서만**
> 요소로 세고, **경기장+날짜만 있는 질의는 여전히 bare** 다. 그래야
> `"Busch Stadium"` 하나짜리가 다시 쓰레기를 끌고 오지 않는다.
"""
from __future__ import annotations

import pytest

# 🔴 사용자가 **이름을 댄 그 라운드들**이다 — 내가 고른 것이 아니다
SAID = ("NLDS", "ALDS", "Wild Card", "CS", "日本シリーズ", "準決勝",
        "결승", "Final")




def test_dec5_코드에_분기로_박지_않았다():
    """🔴 *"코드 분기가 아니라 설정 한 칸"* — 파이썬에 글자가 없어야 한다."""
    import pathlib

    from tests._helpers import strip_docs
    root = pathlib.Path(__file__).resolve().parents[2]
    bad = []
    for p in (root / "app").rglob("*.py"):
        body = strip_docs(p.read_text(encoding="utf-8", errors="replace"))
        for w in ("NLDS", "ALDS", "日本シリーズ", "準決勝"):
            if w in body:
                bad.append(f"{p.relative_to(root)}: {w}")
    assert not bad, (
        f"🔴 라운드 이름을 **코드에** 박았다 — 설정에서 읽어라: {bad}")










