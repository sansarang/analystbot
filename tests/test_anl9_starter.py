"""ANL-9 계약 — **선발이 분석 입력에 들어간다.**

🔴 사용자가 준 목표 분석(2026-09-17): "**선발 축이 이 경기의 전부입니다.**"
   그런데 재료를 이미 갖고 있으면서(games.home_pitcher · pitcher_appearances
   8,203행 · attach_starter_recent) **모델이 본 적이 없었다.**
⚠️ **ERA 를 만들지 않는다** — `starter_recent.slim_start` 머리말이 못 박은 규칙.
"""
import inspect

import pytest

from app.engine import analyze as AN
from app.engine import pick_ledger as PL
from app.engine import starter_recent as SR

def code_of(fn) -> str:
    """🔴 **주석·머리말을 뺀 코드 줄만.** 오늘만 여섯 번째로 같은 함정에 걸렸다 —
    "ERA 를 만들지 않는다"고 적은 주석이 "ERA 를 쓴다"로 잡힌다."""
    src = inspect.getsource(fn)
    body = src.split('"""')
    body = body[0] + "".join(body[2:]) if len(body) > 2 else src
    return "\n".join(ln for ln in body.splitlines()
                      if ln.strip() and not ln.strip().startswith("#"))


REC = [{"opponent": "LG", "innings": 6.0, "r": 2, "hits": 4, "k": 7,
        "bb": 1, "run_support": 4, "date": "2026-09-11"}]
BLK = {"home": "NC", "away": "SSG", "league": "KBO", "p_market": 0.66,
       "gap_pp": -10.3, "gate": "시장 과대", "adj_pp": {}, "p_code": 0.66,
       "kickoff_kst": "x", "home_facts": {}, "away_facts": {},
       "home_starter": {"name": "라일리", "recent": REC},
       "away_starter": {"name": "이로운", "recent": []}}


def test_선발_이름이_들어간다():
    t = AN.build_input(BLK)
    assert "라일리" in t and "이로운" in t


def test_최근_등판이_들어간다():
    t = AN.build_input(BLK)
    for piece in ("6.0이닝", "2실점", "4피안타", "득점지원 4", "2026-09-11"):
        assert piece in t, piece


def test_ERA를_만들지_않는다():
    """🔴 `slim_start` 머리말: "ERA 키는 만들지 않는다"."""
    t = AN.build_input(BLK)
    assert "ERA" not in t and "방어율" not in t
    body = code_of(AN.build_input)
    assert "ERA" not in body and "방어율" not in body


def test_이름이_없으면_줄이_안_난다():
    """🔴 "없음"을 쓰면 없는 사실이 있어 보인다. 축구가 이 경우다."""
    t = AN.build_input({**BLK, "home_starter": {}, "away_starter": None})
    assert "선발" not in t


def test_등판이_없어도_이름은_난다():
    t = AN.build_input(BLK)
    assert "[원정 선발] 이로운" in t


def test_종전_줄이_안_바뀐다():
    """🔴 반대 위험 — 사실·숫자 줄은 그대로다."""
    t = AN.build_input({**BLK, "home_starter": {}, "away_starter": {}})
    assert t.splitlines()[0].startswith("[경기]")
    assert "[숫자 — 변경 불가]" in t
    assert t.strip().endswith("[missing] 없음")


# ── 사실 낱말

def test_fact_words가_선발을_안다():
    """🔴 l1 이 "라일리가 …" 를 인용으로 알아봐야 한다."""
    fw = AN.fact_words(BLK)
    assert "라일리" in fw and "이로운" in fw
    assert "lg" in fw          # 상대 팀도 사실이다


# ── 원장 경로

def test_원장이_예고_선발을_읽는다():
    src = inspect.getsource(PL.record_confirm_and_analysis)
    head = src.split("FROM games", 1)[0]
    assert "home_pitcher" in head and "away_pitcher" in head


def test_같은_함수를_재사용한다():
    """🔴 사본 금지 — pipeline 이 쓰는 그 함수다."""
    src = inspect.getsource(PL.record_confirm_and_analysis)
    assert "attach_starter_recent" in src
    assert "pitcher_appearances" not in src, "조회를 다시 구현했다"


def test_실패해도_분석을_막지_않는다():
    """🔴 선발 조회가 터지면 **선발 줄만** 없다 — 분석은 산다."""
    src = inspect.getsource(PL.record_confirm_and_analysis)
    blk = src.split("attach_starter_recent", 1)[-1].split("# ── S7", 1)[0]
    assert "except Exception" in blk, blk[:300]
    assert "선발 재료 없음" in blk


def test_상한을_손으로_안_적었다():
    """🔴 최근 몇 건인지는 `starter_recent.RECENT_STARTS` 가 원본이다."""
    blk = code_of(PL.record_confirm_and_analysis).split(
        "attach_starter_recent", 1)[-1][:600]
    assert "[:5]" not in blk and "[:3]" not in blk
    assert isinstance(SR.RECENT_STARTS, int)


@pytest.mark.parametrize("side", ["home", "away"])
def test_양쪽_다_실린다(side):
    t = AN.build_input(BLK)
    assert ("홈 선발" if side == "home" else "원정 선발") in t
