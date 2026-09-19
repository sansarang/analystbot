"""[STR-1] `season` 이라는 이름이 거짓말이었다.

🔴 실측 2026-09-19 내보내기 원문:
     "season": {"gs": 6, "ip": 32.3, "era": 3.06}
     "season_note": "우리 DB 의 선발 등판 집계다 — 공식 시즌 스탯 API 값이 아니다."
   `gs` 가 1~6 이다. 공식 시즌은 28선발인데 우리 값은 **우리가 본 등판 전부**다.
   주석으로 사과하면서 이름은 그대로 둔 자리 — 읽는 쪽은 이름을 믿는다.
🔴 CLAUDE.md §9: 표시용 필드는 이름에 `_official`·`_display` 를 붙인다.
   우리 집계는 표시용도 공식도 아닌 **최근 N등판**이므로 `recent6` 가 맞다.
🔴 공식 시즌값 경로는 **이미 있다** — `app/collectors/starter_season.py` 가
   `hydrate=stats(group=[pitching],type=[season])` 로 받고, 이름→id 는 공식
   로스터 지도(`_roster`)로 푼다. 그런데 `attach` 를 부르는 곳이 없다:
     $ rg -n "starter_season" app/pipeline.py   → 0건
   그래서 `research.{side}_starter_season` 이 캐시에 아예 없다(실측).
   "만들어 놓고 안 이음"이 또 한 건이다.
"""
from __future__ import annotations

def test_season_이라는_키가_사라졌다():
    from app.export.for_fable import empty_game

    g = empty_game({"id": 1, "home": "A", "away": "B"})
    s = g["starters"]["home"]
    assert "season" not in s, sorted(s)
    assert "recent6" in s, sorted(s)


def test_recent6_가_무엇인지_이름이_말한다():
    from app.export.for_fable import empty_game

    r = empty_game({"id": 1, "home": "A", "away": "B"})["starters"]["home"]["recent6"]
    assert set(r) >= {"gs", "ip", "era", "k9", "bb9", "hr9"}, sorted(r)


def test_공식_시즌_칸이_따로_있다():
    """🔴 `_official` 접미사 — 판정 입력이 아니라 표시용임을 이름이 말한다."""
    from app.export.for_fable import empty_game

    s = empty_game({"id": 1, "home": "A", "away": "B"})["starters"]["home"]
    assert "season_official" in s, sorted(s)
    assert set(s["season_official"]) >= {"gs", "ip", "era"}


def test_공식값이_비면_사유가_붙는다():
    """🔴 "아직 안 받았다"와 "그 투수가 0이닝을 던졌다"는 다르다."""
    from app.export.for_fable import empty_game

    s = empty_game({"id": 1, "home": "A", "away": "B"})["starters"]["home"]
    assert s["season_official"]["reason"], s["season_official"]


def test_공식값은_캐시에서_읽는다():
    """⚠️ 내보내기는 **새로 수집하지 않는다** — 파이프라인이 채운 것을 읽는다.
       지금 그 자리가 비어 있는 이유는 `starter_season.attach` 가 파이프라인에서
       호출되지 않기 때문이다(`rg starter_season app/pipeline.py` → 0건).
    """
    import inspect

    from app.export import for_fable as F

    src = inspect.getsource(F)
    assert "_starter_season" in src, "판정 캐시의 공식 시즌 칸을 읽지 않는다"
    assert "httpx" not in inspect.getsource(F._starter_block)


def test_공식값을_판정에_잇지_않는다():
    """🔴 v1.4 동결: 시즌 누적은 판정 입력 금지. 이름이 그것을 말해야 한다."""
    from app.export.for_fable import empty_game

    s = empty_game({"id": 1, "home": "A", "away": "B"})["starters"]["home"]
    assert any(k.endswith("_official") for k in s), sorted(s)
