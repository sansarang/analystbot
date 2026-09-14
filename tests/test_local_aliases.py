"""ALI-1 — 검색 질의는 **현지 표기**를 쓴다 (사용자 지시).

🔴 실측 2026-09-14 (운영):
     q="Como 1907 infortunati oggi"         → 0건
     q="Parma Calcio 1913 infortunati oggi" → 0건
   현지 매체는 `Como`·`Parma` 로 쓴다. 법인격(FC·AC·US·SSC)과 창단연도
   (1907·1913)는 이름이 아니라 형식이다.

⚠️ 한국어 별칭표(`SOCCER_ALIAS`)는 **용도가 다르다** — 한국어 매체 검색·
   카드 표시용이다. 이 계약이 그 분리를 잠근다.
"""
import inspect

from app.collectors import satellite_soccer as SOC
from app.engine import scout_config as SC


def test_사용자가_준_세리에A_초기값_그대로다():
    want = {"Como 1907": "Como", "Parma Calcio 1913": "Parma",
            "Torino FC": "Torino", "AS Roma": "Roma",
            "FC Internazionale Milano": "Inter", "Udinese Calcio": "Udinese",
            "US Lecce": "Lecce", "AC Monza": "Monza", "SSC Napoli": "Napoli",
            "Bologna FC 1909": "Bologna", "US Sassuolo Calcio": "Sassuolo",
            "Juventus FC": "Juventus"}
    for db, local in want.items():
        assert SC.local_name("serie_a", db) == local, db


def test_표에_없으면_원래_이름_그대로다():
    """🔴 지어내지 않는다 — 모르면 있는 이름을 쓴다."""
    assert SC.local_name("serie_a", "없는팀 FC") == "없는팀 FC"
    assert SC.local_name("없는리그", "Como 1907") == "Como 1907"


def test_법인격과_창단연도만_지운다():
    """자동 생성 규칙 — 숫자만 있는 토큰과 법인격은 이름이 아니다."""
    assert SC.local_name("bundesliga", "1. FC Köln") == "Köln"
    assert SC.local_name("bundesliga", "1. FSV Mainz 05") == "Mainz"
    assert SC.local_name("bundesliga", "Bayer 04 Leverkusen") == "Bayer Leverkusen"
    # ⚠️ 구두점만 다른 것은 별칭이 아니다 — 표에 넣지 않는다.
    assert "St. Louis Cardinals" not in (SC.LOCAL_ALIASES.get("mlb") or {})


def test_한국어_별칭표와_분리돼_있다():
    """🔴 둘을 섞으면 이탈리아어 질의에 '코모'가 들어간다."""
    assert SOC.soccer_query("Como 1907") == "코모"          # 한국어 매체용
    assert SC.local_name("serie_a", "Como 1907") == "Como"  # 현지어 질의용


def test_수집이_질의에만_현지_표기를_쓴다():
    """⚠️ 기사 귀속·추출은 DB 표기 그대로여야 나중에 경기와 맞출 수 있다."""
    src = inspect.getsource(SOC.gather_soccer)
    assert src.count("SC.local_name(") >= 3, "대진 2 + 팀 1"
    # 질의 조립 줄에만 쓰이고, _qs 의 **키**는 DB 표기(team)다.
    assert '_qs.append((team,' in src
