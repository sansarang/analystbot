"""SOC-10 — 위성이 서치한 것을 DB에 넣고, 제미나이가 DB에서 보게 한다.

사용자 지시 2026-09-13: "인공지능이 서치한거를 db에 저장해라..제미나이가
그거를 보고 판단하게 해라..이애기를 몇번씩 하냐?"

🔴 **실측 2026-09-13 00:2x (운영 파이프라인 12경기).** 제미나이 12글 중 11글이
   "최근 경기 지표를 확인하지 못했다 / 확정 선발 라인업을 확인하지 못했다"로
   끝났다. 원인은 `dbref.ITEMS` 가 **9종 전부 야구**라는 것이다:
     최근 3경기 박스스코어 · 오늘 타순 · 선발 최근 등판 · 불펜 · 실력 레이팅 …
   축구는 이 메뉴에서 받을 게 하나도 없어 DB 칸이 매번 비었다.

   그런데 재료는 있었다 — 위성이 경기당 14~26건을 긁었고 Transfermarkt
   부상표와 Flashscore 선발이 실제로 왔다(AC밀란 글이 "모드리치, 라비오,
   메냥"을 인용했다). **캐시에만 있고 DB 메뉴에 없었을 뿐이다.**

⚠️ 새 테이블을 만들지 않는다. `lineups` 를 쓴다 — `scratches` 가 결장자 자리다.
"""
import json

import pytest

from app.engine import dbref, matchup as MU


def test_DB_메뉴에_축구_두_칸이_있다():
    """🔴 메뉴에 없으면 제미나이는 요청할 수조차 없다."""
    names = [n for n, _ in dbref.ITEMS]
    assert "축구 선발 라인업" in names, names
    assert "축구 부상·결장자" in names, names


def test_축구_칸은_야구를_밀어내지_않는다():
    """⚠️ 반대 위험 — 야구 9종이 그대로 있어야 한다."""
    names = [n for n, _ in dbref.ITEMS]
    for base in ("최근 3경기 박스스코어", "오늘 타순", "선발 최근 등판",
                 "불펜 최근 폼과 가용성", "실력 레이팅", "분기점 조사",
                 "일정·이동·환경", "라인업 의도", "변수 대장"):
        assert base in names, base


def test_선발_라인업_칸이_DB에서_온_값을_낸다():
    jg = {"sport": "soccer", "home": "SS Lazio", "away": "AC Milan",
          "soccer_lineup": {"home": {"포메이션": "1-4-3-3",
                                     "선발": ["Mandas C.", "Zaccagni M."]},
                            "away": {"포메이션": "1-4-2-3-1",
                                     "선발": ["Maignan M.", "Modric L."]}}}
    out = MU.soccer_lineup_payload(jg)
    assert out, out
    blob = json.dumps(out, ensure_ascii=False)
    assert "Modric" in blob and "Mandas" in blob
    assert "SS Lazio" in blob and "AC Milan" in blob


def test_부상자_칸이_DB에서_온_값을_낸다():
    jg = {"sport": "soccer", "home": "SS Lazio", "away": "AC Milan",
          "soccer_injuries": {"home": ["Patric — Muscle strain"],
                              "away": []}}
    out = MU.soccer_injury_payload(jg)
    blob = json.dumps(out, ensure_ascii=False)
    assert "Patric" in blob and "SS Lazio" in blob


def test_야구는_두_칸이_비어_없음으로_간다():
    """🔴 빈 값은 행을 만들지 않는다 — 있으면 판정이 '있다'로 읽는다."""
    jg = {"sport": "kbo", "home": "한화 이글스", "away": "LG 트윈스"}
    assert not MU.soccer_lineup_payload(jg)
    assert not MU.soccer_injury_payload(jg)


def test_자료가_없으면_빈손이다():
    jg = {"sport": "soccer", "home": "A", "away": "B"}
    assert not MU.soccer_lineup_payload(jg)
    assert not MU.soccer_injury_payload(jg)


@pytest.mark.asyncio
async def test_DB에서_읽어_jg에_붙인다():
    """🔴 이 배선이 없으면 위 칸들은 영원히 빈다."""
    from app.engine import soccer_db as SDB

    class _Pool:
        async def fetch(self, sql, *a):
            assert "lineups" in sql, sql
            return [{"side": "home", "source": "flashscore", "status": "predicted",
                     "starter": "1-4-3-3",
                     "batting_order": json.dumps(["Mandas C."]),
                     "scratches": json.dumps([])},
                    {"side": "away", "source": "transfermarkt", "status": "injury",
                     "starter": None, "batting_order": json.dumps([]),
                     "scratches": json.dumps(["Rafael Leao — Muscle"])}]

    jg = {"sport": "soccer", "game_id": 1, "home": "SS Lazio", "away": "AC Milan"}
    await SDB.attach(_Pool(), jg)
    assert jg["soccer_lineup"]["home"]["선발"] == ["Mandas C."]
    assert jg["soccer_injuries"]["away"] == ["Rafael Leao — Muscle"]


@pytest.mark.asyncio
async def test_DB가_없어도_판정은_계속된다():
    from app.engine import soccer_db as SDB

    jg = {"sport": "soccer", "game_id": 1, "home": "A", "away": "B"}
    await SDB.attach(None, jg)          # pool 없음
    assert "soccer_lineup" not in jg or not jg["soccer_lineup"]


def test_판정_경로가_붙이기를_부른다():
    import inspect

    from app.engine import matchup

    assert "soccer_db" in inspect.getsource(matchup._judge_v3)
