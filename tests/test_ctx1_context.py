"""[CTX-1] 맥락 — 있는 재료로 계산되는 것을 비워 두고 있었다.

🔴 판정 캐시의 순위 자료 실측:
     home_standing = {"rank": 5, "w": 71, "l": 82, "d": 0,
                      "games_behind": 24.0, "win_pct": 0.464}
   `record` 는 `w-l` 이면 되는데 내보내기는 `standing.get("record")` 만 보고
   null 을 냈다. `playoff_status`·`travel` 도 "저장 없음"이었다.
🔴 진출 확정(`clinched`)은 **못 낸다** — 컷라인 아래 팀들의 순위표가 필요한데
   캐시에 없다. 탈락(`eliminated`)만 잔여경기로 증명된다.
   못 내는 것을 지어내지 않고 `null + 사유`로 남긴다.
"""
from __future__ import annotations


def test_record_는_승패에서_만든다():
    from app.export.for_fable import _context_block

    got = _context_block({"rank": 5, "w": 71, "l": 82, "games_behind": 24.0})
    assert got["record"] == "71-82", got


def test_디비전_탈락만_증명한다():
    from app.export.for_fable import division_status

    # 162경기 · 153 소화 · 잔여 9 · 디비전 게임차 24 → 디비전은 산술적으로 끝
    assert division_status(w=71, l=82, games_behind=24.0,
                           season_games=162) == "division_eliminated"
    assert division_status(w=85, l=68, games_behind=5.0,
                           season_games=162) == "division_alive"


def test_진출_탈락은_아예_내지_않는다():
    """🔴 `games_behind` 는 **디비전** 게임차다. 디비전에서 밀려도 와일드카드로
       진출한다 — 컷라인 아래 순위표 없이 '탈락'을 적으면 85승 팀에도 붙는다.
       실제 캐시 표본이 그 경우였다: 85-68 · 디비전 10게임차 · 잔여 9.
    """
    from app.export.for_fable import _context_block

    got = _context_block({"rank": 2, "w": 85, "l": 68, "games_behind": 10.0},
                         sport="mlb")
    assert got["playoff_status"] is None, got
    assert "와일드카드" in got["playoff_reason"], got
    assert got["division_status"] == "division_eliminated", got


def test_재료가_없으면_모른다():
    from app.export.for_fable import division_status

    assert division_status(w=None, l=None, games_behind=None, season_games=162) is None
    assert division_status(w=71, l=82, games_behind=None, season_games=162) is None


def test_이동은_직전_구장과_비교한다():
    from app.export.for_fable import travel_of

    last5 = [{"date_kst": "2026-09-18", "venue": "PNC Park", "ha": "H"},
             {"date_kst": "2026-09-17", "venue": "PNC Park", "ha": "H"}]
    assert travel_of("PNC Park", last5) == "홈스탠드 3일차"
    assert travel_of("Coors Field", last5) == "PNC Park → Coors Field 이동"


def test_구장을_모르면_이동도_모른다():
    from app.export.for_fable import travel_of

    assert travel_of(None, [{"venue": "PNC Park"}]) is None
    assert travel_of("PNC Park", []) is None
    assert travel_of("PNC Park", [{"venue": None}]) is None
