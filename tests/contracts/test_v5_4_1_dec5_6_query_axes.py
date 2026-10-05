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


def test_dec5_라운드_이름이_설정에_있다():
    """🔴 **데이터 한 칸** — 코드에 분기로 박지 않는다."""
    from app import rules
    assert hasattr(rules, "round_words"), (
        "🔴 라운드 이름을 읽는 자리가 없다 — `rules.round_words()`")
    got = {str(x).lower() for x in rules.round_words()}
    for w in SAID:
        assert w.lower() in got, f"🔴 `{w}` 가 설정에 없다 — 사용자가 이름을 댔다"


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


@pytest.mark.parametrize("query", [
    "Brewers NLDS Game 1 win Oct 3 2026 Jacob Misiorowski",
    "Milwaukee Brewers NLDS Game 2 2026 preview Robbie Ray",
    "Milwaukee Brewers Game 2 NLDS starting pitcher 2026 playoffs",
])
def test_dec5_라운드가_있으면_대회로_센다(query):
    """🔴🔴 **효과를 잰다** — 게이트2 가 거부한 그 셋이 서야 한다."""
    from app import querygate
    n, got = querygate.count_parts(query)
    assert "competition" in got, (
        f"🔴 `{query[:46]}` 에 라운드가 있는데 **대회로 안 센다**: {got}")
    assert n >= querygate.MIN_PARTS, (n, got)


def test_dec6_경기장은_venue_weather_에서만_요소다():
    """🔴 유형이 `venue_weather` 일 때만 센다."""
    from app import querygate
    q = "American Family Field weather forecast October 4 2026 MLB"
    n_on, got_on = querygate.count_parts(
        q, parts={"venue": "American Family Field"}, kind="venue_weather")
    assert "venue" in got_on, got_on
    assert n_on >= querygate.MIN_PARTS, (n_on, got_on)
    # 🔴 다른 유형에서는 **안 센다**
    n_off, got_off = querygate.count_parts(
        q, parts={"venue": "American Family Field"}, kind="lineup")
    assert "venue" not in got_off, got_off


def test_dec6_경기장과_날짜만이면_여전히_bare():
    """🔴🔴 *"`Busch Stadium` 하나짜리가 다시 쓰레기를 끌고 오지 않는다"*.

    ⚠️ 경기장 + 날짜 **둘뿐**이면 통과하면 안 된다 — 그것이 사용자가 단 조건이다.
    """
    from app import querygate
    n, got = querygate.count_parts(
        "Busch Stadium October 4 2026",
        parts={"venue": "Busch Stadium"}, kind="venue_weather")
    assert n < querygate.MIN_PARTS, (
        f"🔴 **경기장+날짜만**인데 통과했다({n}개 {got}) — `Busch Stadium` "
        f"하나짜리가 쓰레기를 끌고 온다")


def test_dec6_경기장_하나짜리는_bare():
    """🔴 경기장만 있는 질의는 **당연히** 거부다."""
    from app import querygate
    n, _ = querygate.count_parts("Busch Stadium",
                                 parts={"venue": "Busch Stadium"},
                                 kind="venue_weather")
    assert n < querygate.MIN_PARTS, n


def test_dec6_유형을_안_주면_종전대로다():
    """⚠️ 고치면서 **부르는 곳 전부를 고치게** 만들지 않는다(기본값이 안전하다)."""
    from app import querygate
    n, got = querygate.count_parts("Busch Stadium October 4 2026",
                                   parts={"venue": "Busch Stadium"})
    assert "venue" not in got, got
