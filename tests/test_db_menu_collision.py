"""DBM-1 — 축구 칸 이름이 야구 칸을 가렸다. 선발·타순이 전달되지 않았다.

🔴 **실측 2026-09-13 (운영, Seattle Mariners @ Athletics, game 6003).**
   DB에는 다 있었다:
     games.home_pitcher = Gage Jump · away_pitcher = Bryan Woo
     games.lineup_status = confirmed (22:02Z 확정)
     lineups 4행 — 양 팀 타순 9명 + 선발 이름
   그런데 제미니는 "양 팀 모두 선발 투수와 확정 라인업이 공개되지 않아"라고 썼다.

   로그가 어긋난 자리를 가리킨다:
     [triage] DB요청 2
     [dbref] DB로 못 채운 요청 1개: ['오늘 선발 라인업']
     DB있음: ['오늘 타순', '선발 최근 등판', '불펜 최근 폼과 가용성', '일정·이동·환경']

   야구 값이 든 칸 이름은 `오늘 타순` 인데, SOC-10 에서 내가 추가한 축구 칸
   이름이 `오늘 선발 라인업` 이라 **같은 것을 가리키는 이름이 둘**이 됐다.
   제미니가 축구 이름을 골랐고, 야구 경기라 빈손이 됐다.

⚠️ 야구 9종 이름은 프롬프트·원장이 그대로 쓴다 — **건드리지 않는다.**
   고치는 것은 내가 나중에 붙인 축구 칸 이름이다.
"""
from app.engine import dbref


def test_축구_칸이_야구_칸을_가리지_않는다():
    """🔴 `오늘 타순`(야구)과 `오늘 선발 라인업`(축구)이 같은 것을 가리켰다."""
    names = [n for n, _ in dbref.ITEMS]
    assert "오늘 선발 라인업" not in names, names
    assert "축구 선발 라인업" in names, names
    assert "축구 부상·결장자" in names, names


def test_야구_아홉_칸은_그대로다():
    """⚠️ 반대 위험 — 야구 이름이 바뀌면 프롬프트·원장 대조가 깨진다."""
    names = [n for n, _ in dbref.ITEMS]
    for base in ("최근 3경기 박스스코어", "오늘 타순", "선발 최근 등판",
                 "불펜 최근 폼과 가용성", "실력 레이팅", "분기점 조사",
                 "일정·이동·환경", "라인업 의도", "변수 대장"):
        assert base in names, base


def test_이름이_겹치지_않는다():
    """🔴 두 칸이 같은 말로 읽히면 제미니가 둘 중 하나를 잘못 고른다."""
    names = [n for n, _ in dbref.ITEMS]
    assert len(names) == len(set(names)), names
    # '라인업'을 이름에 쓰는 칸은 종목이 붙어 있어야 한다
    for n in names:
        if "라인업" in n and n != "라인업 의도":
            assert n.startswith("축구"), n
