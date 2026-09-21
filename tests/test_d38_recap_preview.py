"""[D38] `is_recap` 이 **예고 기사**를 경기 후 기사로 버린다.

🔴 실측 2026-09-21 (Bing 결과로 DS-3a 전 구간을 돌리다 발견):

    [AI프리뷰] 20일 잠실 LG-한화전, 한화 좌완 영건 황준서 선발 기회 살릴
       → 표지 `리뷰` 가 **`프리뷰`** 안에서 걸린다. 정확히 반대 뜻의 기사다.
    【中日スタメン速報】ドラ1ルーキー…7月15日以来の勝利目指し先発 岡林勇希が
       → 표지 `勝利` 가 **`勝利目指し`**(승리를 노린다·미래) 안에서 걸린다.

🔴 **우리가 가장 원하는 기사(스타멘 발표·프리뷰)를 버리는 방향의 오탐**이다.

⚠️ 지금 운영 규모는 0 이다 — 캐시 제목 137건 중 `is_recap` 폐기 40건(29%),
   그중 라인업·선발 낱말이 있고 점수 표기가 없는 오탐 후보 **0건**.
   그런데 **DS-3(검색 소스를 Bing 으로 바꾸는 배선)의 전제**다. 소스를 바꾸면
   위 두 제목이 실제로 들어오고, 그때 이 오탐이 살아난다.

⚠️ **반대 위험을 함께 잠근다**(신규 필터의 규칙): 진짜 경기 후 기사를
   통과시키면 그게 더 나쁘다. 아래 `_REAL_RECAP` 이 그것을 지킨다.
"""
from __future__ import annotations

import pytest

#: 🔴 버리면 안 되는 것 — 예고·프리뷰·발표
_PREVIEW = [
    ("kbo", "[AI프리뷰] 20일 잠실 LG-한화전, 한화 좌완 영건 황준서 선발 기회 살릴"),
    ("npb", "【中日スタメン速報】ドラ1ルーキー・中西聖輝が7月15日以来の勝利目指し先発 岡林勇希が2番"),
    ("npb", "【中日21日スタメン】1番福永＆2番村松 クリーンナップは細川 サノー"),
    ("soccer", "Brighton vs Arsenal: Confirmed starting lineups and team news"),
    ("kbo", "한화 이글스 프리뷰 — 오늘 선발 예고"),
]

#: 🔴 **반드시 버려야 하는 것** — 진짜 경기 후 기사.
#   신규 필터는 반대 위험(정상 폐기 대상을 통과시킴)을 함께 재야 한다.
_REAL_RECAP = [
    ("kbo", "포항스틸러스, FC서울 2-1 격파…6위와 승점 같은 7위 도약"),
    ("kbo", "한화 5-3 승리…문동주 7이닝 무실점"),
    ("npb", "中日が快勝 細川が2本塁打"),
    ("npb", "楽天、逆転勝ち サヨナラ打は浅村"),
    ("soccer", "Arsenal beat Brighton 2-0 as Saka scores twice"),
    ("soccer", "Liverpool 3-1 Chelsea: highlights and reaction"),
]


@pytest.mark.parametrize("sport,title", _PREVIEW)
def test_예고_기사는_버리지_않는다(sport, title):
    from app.engine.situation import is_recap

    assert is_recap(title, sport) is False, f"예고를 경기 후 기사로 버렸다: {title}"


@pytest.mark.parametrize("sport,title", _REAL_RECAP)
def test_진짜_경기후_기사는_그대로_버린다(sport, title):
    """⚠️ 반대 위험 — 느슨하게 고치면 이쪽이 샌다."""
    from app.engine.situation import is_recap

    assert is_recap(title, sport) is True, f"경기 후 기사가 통과했다: {title}"


def test_표지는_낱말_경계로_본다():
    """🔴 `리뷰` 가 `프리뷰` 안에서 걸리면 안 된다 — 이것이 D38 의 핵심이다."""
    from app.engine.situation import _recap_hits

    assert "리뷰" not in _recap_hits("프리뷰 기사입니다", "kbo")
    assert "리뷰" in _recap_hits("경기 리뷰", "kbo")


def test_일본어_미래형은_표지가_아니다():
    """⚠️ 일본어는 띄어쓰기가 없어 낱말 경계가 없다 — **뒤에 붙는 말**로 가린다.
    `勝利目指し`(승리를 노린다) · `勝利へ`(승리로) 는 아직 안 일어난 일이다."""
    from app.engine.situation import _recap_hits

    assert "勝利" not in _recap_hits("7月15日以来の勝利目指し先発", "npb")
    assert "勝利" not in _recap_hits("連勝を目指す", "npb")
    assert "勝利" in _recap_hits("中日が勝利 細川が2安打", "npb")


def test_팀이름_안의_표지는_세지_않는다():
    """🔴 실측 2026-09-21 — 운영 제목 137건 중 **5건이 `Twins` 안의 `wins `**
    로 걸리고 있었다. `리뷰`/`프리뷰` 와 같은 부류다.

        Minnesota Twins at Los Angeles Angels MLB Prediction, Picks and Odds
          구 규칙 → `wins ` 적중 → **경기 후 기사로 폐기**

    ⚠️ 그래도 `Angels wins 3-2` 처럼 **제대로 된 자리**에서는 걸려야 한다.
    """
    from app.engine.situation import _recap_hits

    assert _recap_hits("Minnesota Twins at Los Angeles Angels MLB Prediction",
                       "mlb") == []
    assert "wins " in _recap_hits("Angels wins 3 straight over Twins", "mlb")


def test_규칙을_코드에_박지_않았다():
    """🔴 표지 목록의 원본은 `registry.RECAP_MARKERS` 하나다(사본 금지)."""
    import inspect

    from app.engine import situation

    src = inspect.getsource(situation)
    for w in ("리뷰", "勝利", "beat", "sweep"):
        assert f'"{w}"' not in src, f"표지 {w} 를 situation.py 에 적었다"
