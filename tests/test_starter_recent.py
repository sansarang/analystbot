"""오늘 선발 최근 등판. 시즌 ERA는 넣지 않는다."""
import pytest
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


# ── [SR-1 2026-09-10] "표본 2경기 이하면 0.50 쪽으로" 를 코드가 강제한다 ────
#   🔴 이 규칙은 `app/engine/CLAUDE.md` 대원칙에 이미 있었다 —
#      "최근 등판이 2경기 이하면 시즌으로 메우지 말고 **0.50 쪽으로 당기고
#       확신도를 낮춘다.** 표본이 적다는 사실 자체가 정보다."
#      그런데 코드는 `MIN_STARTS = 1`(추천 자동 탈락)만 강제하고, **당기는
#      쪽은 프롬프트 문장으로만** 있었다. 그래서 안 지켜졌다.
#
#   실사고 2026-09-09 LAA@Boston (우리 홈 54% → 원정 6:4 승):
#      근거2 = "홈 선발 Jake Bennett은 **최근 2경기** 12.0이닝 3실점 14탈삼진
#               0볼넷으로 뛰어난 제구 안정감"   실제: 5.1이닝 6자책
#
#   실측(운영 195경기, 선발 30일 등판 수로 재구성):
#      ≤2경기(얇음) 36/78 = 46.2% · 브라이어 0.2644  ← 0.25보다 나쁘다
#      ≥3경기(정상) 61/110 = 55.5% · 브라이어 0.2487
#      평균 |p-0.5| 는 7.7 vs 7.6%p — **얇을 때도 같은 확신으로 찍고 있었다**
#      축소 계수 λ 를 훑으면 얇음 브라이어는 λ=0 에서 최소(0.2500)다.
#      λ=0.5 면 0.2640 → 0.2552. 확률 하한을 넘던 얇은 픽 29건(적중 14/29
#      = 48%)이 전부 하한 아래로 내려간다.
#   ⚠️ 축소는 **방향을 바꾸지 않는다** — 적중률은 그대로고 보정만 좋아진다.
#   ⚠️ 확신도는 **상→중 까지만** 낮춘다. `하` 는 단순한 낮은 확신이 아니라
#      **거부권**이라(CLAUDE.md), 한 단계씩 기계적으로 내리면 얇은 표본 경기가
#      전부 "판정 패스"로 바뀐다. 회귀 테스트가 실제로 그것을 잡았다.

def test_thin_sample_shrinks_toward_half():
    from app.engine.matchup import apply_matchup

    jg = {"research": {"home_starter_recent": [{"g": 1}, {"g": 2}],
                       "away_starter_recent": [{"g": i} for i in range(5)],
                       "home_pitcher": {"name": "H"}, "away_pitcher": {"name": "A"}},
          "home": "H팀", "away": "A팀"}
    apply_matchup(jg, {"p_home": 0.62, "우세": "home", "확신도": "상"})
    assert jg["p_claude"] == pytest.approx(0.56), f"안 당겨졌다: {jg['p_claude']}"
    assert jg["matchup"]["p_home"] == pytest.approx(0.56)
    assert jg["matchup"]["확신도"] == "중", "확신도가 안 낮아졌다"
    assert jg["matchup"].get("표본축소"), "축소 사실이 기록되지 않았다"


def test_thick_sample_untouched():
    """⚠️ 반대 위험 — 표본이 충분하면 손대지 않는다."""
    from app.engine.matchup import apply_matchup

    jg = {"research": {"home_starter_recent": [{"g": i} for i in range(4)],
                       "away_starter_recent": [{"g": i} for i in range(5)],
                       "home_pitcher": {"name": "H"}, "away_pitcher": {"name": "A"}},
          "home": "H팀", "away": "A팀"}
    apply_matchup(jg, {"p_home": 0.62, "우세": "home", "확신도": "상"})
    assert jg["p_claude"] == pytest.approx(0.62)
    assert jg["matchup"]["확신도"] == "상"
    assert not jg["matchup"].get("표본축소")


def test_shrink_never_flips_direction():
    """⚠️ 0.50 쪽으로 당기는 것이지 넘기는 것이 아니다."""
    from app.engine.matchup import apply_matchup

    jg = {"research": {"home_starter_recent": [], "away_starter_recent": [],
                       "home_pitcher": {"name": "H"}, "away_pitcher": {"name": "A"}},
          "home": "H팀", "away": "A팀"}
    apply_matchup(jg, {"p_home": 0.40, "우세": "away", "확신도": "중"})
    assert 0.40 < jg["p_claude"] <= 0.50, f"방향이 넘어갔다: {jg['p_claude']}"


def test_shrink_never_creates_veto():
    """⚠️ 반대 위험 — `하` 는 거부권이다. 축소가 픽을 죽이면 안 된다."""
    from app.engine.matchup import apply_matchup

    jg = {"research": {"home_starter_recent": [], "away_starter_recent": [],
                       "home_pitcher": {"name": "H"}, "away_pitcher": {"name": "A"}},
          "home": "H팀", "away": "A팀"}
    apply_matchup(jg, {"p_home": 0.60, "우세": "home", "확신도": "중"})
    assert jg["matchup"]["확신도"] == "중", "중을 하로 내려 거부권을 만들었다"
