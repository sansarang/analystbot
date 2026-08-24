"""[A] 마켓별 판정 분리 회귀 테스트.

실사고: 승패(h2h)에 가치가 없으면 경기 전체를 🔴 패스로 처리해, 언더/핸디캡에
가치가 있는 경기까지 버렸다. 신호등·추천·조합은 모두 **마켓 단위**로 판정한다.
"""

from app.engine.markets import (
    GRADE_GREEN,
    GRADE_RED,
    GRADE_YELLOW,
    best_market,
    board_grade,
    build_candidates,
    grade_candidate,
    rejection_summary,
)


def _c(**over):
    c = {"market": "totals", "side": "Under", "line": 8.5, "desc": "언더 8.5",
         "odds": 1.87, "p": 0.58, "ev": 0.07, "axes_kr": "전문가+시장",
         "approved": True, "reject_reason": None}
    c.update(over)
    return c


def test_grade_reflects_market_not_game():
    assert grade_candidate(_c())[0] == GRADE_GREEN                       # 승인 + EV 충분
    assert grade_candidate(_c(ev=0.02))[0] == GRADE_YELLOW               # 이득 얇음
    assert grade_candidate(_c(ev=-0.08))[0] == GRADE_RED                 # 가치 없음
    assert grade_candidate(_c(approved=False, reject_reason="근거 부족"))[0] == GRADE_RED
    assert grade_candidate(_c(odds=None, ev=None))[0] == GRADE_RED       # 배당 미수집


def test_yellow_note_marks_low_variance_alternative():
    """[A-1] 저분산 마켓의 🟡은 '저분산 대안'으로 표기한다."""
    assert "저분산 대안" in grade_candidate(_c(ev=0.02))[1]
    assert "저분산 대안" in grade_candidate(_c(market="spreads", line=1.5, ev=0.02))[1]
    assert "저분산" not in grade_candidate(_c(market="spreads", line=-1.5, ev=0.02))[1]


def test_board_grade_takes_best_market():
    """[A-1] 승패 🔴 + 언더 🟢 → 경기 신호등은 🟢."""
    board = [_c(market="h2h", desc="홈 승", ev=-0.08), _c()]
    for c in board:
        c["grade"], c["grade_note"] = grade_candidate(c)
    assert board_grade(board) == GRADE_GREEN
    assert best_market(board)["desc"] == "언더 8.5"


def test_rejection_summary_lists_each_market_and_unpriced():
    """[A-1] 전 마켓 🔴이면 검토 목록과 사유를 한 줄로 밝힌다."""
    board = [_c(market="h2h", desc="승패 홈", ev=-0.12),
             _c(desc="언더 8.5", approved=False, reject_reason="근거 부족 — 2-소스 미달")]
    for c in board:
        c["grade"], c["grade_note"] = grade_candidate(c)
    s = rejection_summary(board, ["런라인"])
    assert "승패 홈" in s and "-12.0%" in s
    assert "언더 8.5" in s and "근거 부족" in s
    assert "런라인 배당 미수집" in s


def _jg(**over):
    jg = {
        "game_id": 1, "sport": "mlb", "home": "Detroit Tigers", "away": "Tampa Bay Rays",
        "league": "MLB", "status": "scheduled", "judge_confidence": "high",
        "market_probs": {"Detroit Tigers": 0.45, "Tampa Bay Rays": 0.55},
        "best_odds": {"Detroit Tigers": 2.22, "Tampa Bay Rays": 1.79},
        "alt_markets": [], "expert_picks": [], "stats": {},
    }
    jg.update(over)
    return jg


def test_totals_survive_when_h2h_odds_missing():
    """[A-2] h2h 배당이 없어도 토탈 배당이 있으면 그 마켓으로 판정한다."""
    jg = _jg(market_probs=None, best_odds={},
             alt_markets=[{"market": "totals", "side": "Under", "line": 7.5,
                           "odds": 1.98, "p": 0.56}])
    cands = build_candidates(jg, "mlb", {})           # p_final 없음 = h2h 평가 불가
    assert [c["market"] for c in cands] == ["totals"]
    assert "승패" in jg["markets_unpriced"]           # 없는 마켓만 미수집으로 기록
    assert "언더오버" not in jg["markets_unpriced"]


def test_unpriced_markets_are_listed_not_fatal():
    """[A-2] 배당 없는 마켓만 '미수집'으로 빠지고 경기는 살아 있다."""
    jg = _jg(alt_markets=[])
    cands = build_candidates(jg, "mlb", {"Detroit Tigers": 0.46, "Tampa Bay Rays": 0.56})
    assert [c["market"] for c in cands] == ["h2h", "h2h"]
    assert set(jg["markets_unpriced"]) == {"런라인", "언더오버"}


def test_stale_snapshot_is_labelled_opening_odds():
    """[A-3] 오래된 스냅샷으로 폴백하면 '(개장 배당)' 라벨을 붙인다."""
    jg = _jg(odds_stale=True)
    cands = build_candidates(jg, "mlb", {"Detroit Tigers": 0.46, "Tampa Bay Rays": 0.56})
    assert all("(개장 배당)" in c["desc"] for c in cands)


def test_every_candidate_carries_a_grade():
    """[A-4] 마켓 보드는 전 후보에 등급과 사유를 갖는다 (표로 항상 출력하기 위함)."""
    jg = _jg(alt_markets=[{"market": "totals", "side": "Under", "line": 7.5,
                           "odds": 1.98, "p": 0.56}])
    for c in build_candidates(jg, "mlb", {"Detroit Tigers": 0.46, "Tampa Bay Rays": 0.56}):
        assert c["grade"] in (GRADE_GREEN, GRADE_YELLOW, GRADE_RED)
        assert c["grade_note"]


# ---------------------------------------------------------------- [A-4][A-5] 렌더·추천

def _rendered_jg(**over):
    from app.engine.markets import grade_candidate

    jg = {
        "game_id": 9, "sport": "mlb", "home": "Chicago White Sox", "away": "Texas Rangers",
        "league": "MLB", "status": "scheduled", "status_label": "",
        "starts_at_kst": "08/25 10:38", "model_valid": True,
        "p_model": 0.44, "p_market": 0.45, "p_claude": 0.46,
        "market_probs": {"Chicago White Sox": 0.45, "Texas Rangers": 0.55},
        "best_odds": {"Chicago White Sox": 2.20, "Texas Rangers": 1.81},
        "judge_confidence": "high", "verdict": "테스트 판정", "expert_picks": [],
        "stats": {"home_pitcher": "Davis Martin", "away_pitcher": "Nathan Eovaldi"},
        "research": {"home_recent_form": {"form": "LLWLL"},
                     "absences": ["Texas Rangers의 Josh Jung 결장"]},
        "market_board": [
            {"market": "h2h", "side": "Chicago White Sox", "line": None, "desc": "승패 홈",
             "odds": 1.81, "p": 0.47, "ev": -0.08, "axes_kr": "시장",
             "approved": True, "reject_reason": None},
            {"market": "totals", "side": "Under", "line": 8.5, "desc": "언더 8.5",
             "odds": 1.87, "p": 0.58, "ev": 0.07, "axes_kr": "전문가+시장",
             "approved": True, "reject_reason": None},
            {"market": "spreads", "side": "Texas Rangers", "line": 1.5,
             "desc": "텍사스 레인저스 런라인 +1.5", "odds": 1.55, "p": 0.66, "ev": 0.023,
             "axes_kr": "시장", "approved": True, "reject_reason": None},
        ],
        "markets_unpriced": [],
    }
    jg.update(over)
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    return jg


def test_board_is_always_rendered_as_table():
    """[A-4] 상세에 마켓 보드를 항상 표로 출력한다 (마켓 배당 → 등급 EV 사유)."""
    from app.pipeline import render_game_section

    out = render_game_section(_rendered_jg())
    assert "⑧ 마켓 보드:" in out
    assert "승패 홈 1.81 → 🔴 EV -8.0%" in out
    assert "언더 8.5 1.87 → 🟢 EV +7.0%" in out
    assert "런라인 +1.5 1.55 → 🟡" in out and "저분산 대안" in out


def test_board_shows_unpriced_markets():
    """[A-4] 배당이 없어 평가 못 한 마켓도 보드에 남긴다."""
    from app.pipeline import render_game_section

    out = render_game_section(_rendered_jg(markets_unpriced=["런라인"]))
    assert "런라인 → ⚪ 배당 미수집" in out


def test_easy_layer_points_to_best_market_when_moneyline_dead():
    """[A-1] 승패가 🔴이면 기본층은 '승패는 볼 게 없지만 언더 8.5가 …'로 말한다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    easy = render_game_easy(_rendered_jg()).split(DETAIL_SEP)[0]
    assert "🟢" in easy
    assert "승패는 볼 게 없지만" in easy and "언더 8.5" in easy


def test_easy_layer_lists_reasons_when_all_markets_dead():
    """[A-1] 전 마켓 🔴일 때만 패스이고, 마켓별 사유를 밝힌다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    jg = _rendered_jg()
    for c in jg["market_board"]:
        c["ev"] = -0.05
    from app.engine.markets import grade_candidate
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    jg["markets_unpriced"] = ["언더오버"]
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "🔴" in easy
    assert "전 마켓" in easy and "승패 홈" in easy and "언더오버 배당 미수집" in easy


def test_recommendation_pool_includes_non_moneyline(db_pool=None):
    """[A-5] 추천 후보 풀은 전 마켓 승인 픽 — 승패가 없어도 토탈로 성립한다."""
    from app.pipeline import approved_market_legs

    jg = _rendered_jg()
    jg["market_board"][0].update(approved=False, reject_reason="근거 부족")
    legs = approved_market_legs([jg])
    assert legs and all(l["market"] != "h2h" for l in legs)
    assert {l["desc"] for l in legs} == {"언더 8.5", "텍사스 레인저스 런라인 +1.5"}
