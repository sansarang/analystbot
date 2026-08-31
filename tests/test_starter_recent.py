"""오늘 선발 최근 등판. 시즌 ERA는 넣지 않는다."""
from datetime import UTC, datetime

from app.engine.starter_recent import pitcher_name, slim_start


def test_slim_start_omits_era():
    row = {
        "opponent": "KIA", "innings": 6.0, "r": 2, "hits": 5,
        "k": 7, "bb": 1, "er": 2, "era": 3.00,
        "starts_at": datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
    }
    got = slim_start(row)
    assert got["opponent"] == "KIA"
    assert got["innings"] == 6.0
    assert got["r"] == 2
    assert got["date"] == "2026-08-20"
    assert "era" not in got
    assert "er" not in got


def test_pitcher_name_falls_back_to_game_column_when_research_empty():
    jg = {"home_pitcher": "Carlos Rodón", "away_pitcher": "Blake Snell",
          "research": {}}
    assert pitcher_name(jg, "home") == "Carlos Rodón"
    assert pitcher_name(jg, "away") == "Blake Snell"


def test_pitcher_name_prefers_research_dict():
    jg = {
        "home_pitcher": "wrong",
        "research": {"home_pitcher": {"name": "페덱"}},
    }
    assert pitcher_name(jg, "home") == "페덱"


# ---------------------------------------------------------------- [v1.1 1단계] run_support
#
# W-L 액면에 속지 않기 위한 값이다. 실측 사례: 바즈 4승14패 — 실질은
# ERA 4.04에 타선 지원 부족. 승패만 보면 오판한다.

def test_slim_start_carries_run_support():
    row = {"opponent": "LG", "innings": 6.0, "r": 2, "hits": 5, "k": 7, "bb": 1,
           "run_support": 1, "starts_at": None}
    out = slim_start(row)
    assert out["run_support"] == 1


def test_slim_start_omits_run_support_when_unknown():
    """점수가 없는 경기(취소·미종료)는 키를 만들지 않는다 — 0으로 지어내지 않는다."""
    row = {"opponent": "LG", "innings": 6.0, "r": 2, "run_support": None,
           "starts_at": None}
    assert "run_support" not in slim_start(row)


def test_fetch_query_derives_run_support_without_new_crawl():
    """기존 표만으로 계산한다 — 신규 수집 없음(지시문 조건)."""
    from app.engine.starter_recent import _FETCH

    assert "run_support" in _FETCH
    assert "a.team = g.home" in _FETCH and "a.team = g.away" in _FETCH
    assert "pitcher_appearances" in _FETCH


def test_prompts_forbid_win_loss_as_evidence():
    """프롬프트 1·2가 W-L을 근거로 쓰지 못하게 한다."""
    from app.engine.prompts import MATCHUP, TEAM_FORM

    assert "run_support" in MATCHUP
    assert "승패(W-L)는 판정 근거로 쓰지 않는다" in MATCHUP
    assert "승패(W-L)는 평가 근거로 쓰지 않는다" in TEAM_FORM
