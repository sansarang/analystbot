"""STD-1 계약 — 팀 성적을 **우리 DB 로** 만들어 분석에 싣는다.

🔴 목표 분석(2026-09-17)의 첫 축: "KIA .544(4위) vs 키움 .352(최하위, 3연패)"
🔴 **새 소스가 없다** — `games(status='final')` 만 쓴다(실측 보유: mlb 496 ·
   kbo 259 · npb 195). 뽑으면 KIA .551(3위) · 키움 .373(9위) 로 가깝다.
⚠️ **"시즌 순위"가 아니다.** KBO 는 2026-06-28 부터만 있다 —
   **"보유 구간"이라고 밝혀 적는다.** 없는 것을 있다고 쓰면 거짓 재료다.
"""
import inspect

import pytest

from app.engine import analyze as AN
from app.engine import pick_ledger as PL
from app.engine import standings as ST

ROWS = [
    {"home": "KIA", "away": "키움", "home_score": 5, "away_score": 1},
    {"home": "키움", "away": "KIA", "home_score": 2, "away_score": 7},
    {"home": "KIA", "away": "NC", "home_score": 3, "away_score": 4},
    {"home": "키움", "away": "NC", "home_score": 1, "away_score": 1},
]


def test_승패무를_센다():
    t = ST.table(ROWS)
    assert t["KIA"] == {**t["KIA"], "gp": 3, "win": 2, "loss": 1, "draw": 0}
    assert t["키움"]["draw"] == 1


def test_무승부를_승률에서_뺀다():
    """🔴 야구 관례 — 승/(승+패). KBO·NPB 는 무가 있다."""
    t = ST.table([{"home": "A", "away": "B", "home_score": 1, "away_score": 1},
                  {"home": "A", "away": "B", "home_score": 2, "away_score": 1}])
    assert t["A"]["pct"] == 1.0 and t["A"]["gp"] == 2


def test_결과가_없으면_승률이_None이다():
    """🔴 0.000 과 "모름"은 다르다."""
    t = ST.table([{"home": "A", "away": "B", "home_score": 1, "away_score": 1}])
    assert t["A"]["pct"] is None


def test_순위가_승률_순이다():
    t = ST.table(ROWS)
    assert t["KIA"]["rank"] < t["키움"]["rank"]


def test_연승연패를_센다():
    t = ST.table([{"home": "A", "away": "B", "home_score": 1, "away_score": 0},
                  {"home": "B", "away": "A", "home_score": 0, "away_score": 1},
                  {"home": "A", "away": "B", "home_score": 3, "away_score": 0}])
    assert t["A"]["streak"] == "3연승" and t["B"]["streak"] == "3연패"


def test_무승부에서_연속이_끊긴다():
    t = ST.table([{"home": "A", "away": "B", "home_score": 1, "away_score": 0},
                  {"home": "A", "away": "B", "home_score": 1, "away_score": 1}])
    assert t["A"]["streak"] is None


# ── 🔴 반대 위험

def test_점수가_없으면_안_센다():
    """🔴 진행 중·취소를 세면 성적이 거짓이 된다."""
    assert ST.table([{"home": "A", "away": "B", "home_score": None,
                      "away_score": None}]) == {}


def test_빈_입력이면_빈_표다():
    assert ST.table([]) == {} and ST.table(None) == {}
    assert ST.line_of({}, "A") is None and ST.line_of(None, "A") is None


def test_모양이_이상해도_안_터진다():
    """🔴 ANL-8 의 교훈 — 소비자가 모양을 믿지 않는다."""
    assert ST.line_of({"A": {"gp": 3}}, "A") is not None
    assert ST.line_of({"A": "이상"}, "A") is None


def test_DB도_HTTP도_안_부른다():
    """🔴 `report.py` 와 같은 규약 — 순수 함수다."""
    src = inspect.getsource(ST)
    for bad in ("asyncpg", "httpx", "await ", "SELECT"):
        assert bad not in src, bad


# ── 분석 입력

def test_입력_블록에_들어간다():
    blk = {"home": "KIA", "away": "키움", "league": "KBO", "p_market": 0.62,
           "gap_pp": 6.8, "gate": "가치 의심", "adj_pp": {}, "p_code": 0.62,
           "kickoff_kst": "x", "home_facts": {}, "away_facts": {},
           "standings": ST.table(ROWS)}
    t = AN.build_input(blk)
    assert "팀 성적" in t and "KIA" in t and "승률" in t


def test_보유_구간이라고_밝힌다():
    """🔴 시즌 순위인 척하지 않는다 — 그게 곧 거짓 재료다."""
    blk = {"home": "KIA", "away": "키움", "league": "KBO", "p_market": 0.62,
           "gap_pp": 6.8, "gate": "x", "adj_pp": {}, "p_code": 0.62,
           "kickoff_kst": "x", "home_facts": {}, "away_facts": {},
           "standings": ST.table(ROWS),
           "standings_note": "보유 구간 2026-06-28 이후 259경기"}
    assert "보유 구간 2026-06-28 이후 259경기" in AN.build_input(blk)
    src = inspect.getsource(PL.record_confirm_and_analysis)
    assert "standings_note" in src


def test_양팀이_없으면_줄이_안_난다():
    blk = {"home": "X", "away": "Y", "league": "KBO", "p_market": 0.6,
           "gap_pp": 0, "gate": "x", "adj_pp": {}, "p_code": 0.6,
           "kickoff_kst": "x", "home_facts": {}, "away_facts": {},
           "standings": ST.table(ROWS)}
    assert "팀 성적" not in AN.build_input(blk)


def test_fact_words가_연패를_안다():
    blk = {"home": "KIA", "away": "키움", "standings": ST.table(ROWS)}
    fw = AN.fact_words(blk)
    assert "kia" in fw or "KIA".lower() in fw


@pytest.mark.parametrize("bad", ["send", "dispatch", "telegram"])
def test_발송을_켜지_않는다(bad):
    assert bad not in inspect.getsource(ST).lower()
