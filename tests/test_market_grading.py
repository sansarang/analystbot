"""[A] 마켓별 판정 분리 회귀 테스트.

실사고: 승패(h2h)에 가치가 없으면 경기 전체를 🔴 패스로 처리해, 언더/핸디캡에
가치가 있는 경기까지 버렸다. 신호등·추천·조합은 모두 **마켓 단위**로 판정한다.
"""

from app.engine.markets import (
    GRADE_BLANK,
    GRADE_GREEN,
    GRADE_RED,
    GRADE_YELLOW,
    best_market,
    board_grade,
    build_board,
    build_candidates,
    grade_candidate,
    rejection_summary,
)


def _c(**over):
    c = {"market": "totals", "side": "Under", "line": 8.5, "desc": "언더 8.5",
         "odds": 1.62, "p": 0.64, "ev": 0.037, "axes_kr": "전문가+실데이터",
         "approved": True, "reject_reason": None}
    c.update(over)
    return c


def test_grade_uses_win_prob_and_odds_floor_not_ev():
    """[3-2] 등급은 승률 + 배당 하한으로만 — EV는 판정에서 제외."""
    assert grade_candidate(_c())[0] == GRADE_GREEN                  # 64% + 1.87
    assert grade_candidate(_c(p=0.59))[0] == GRADE_YELLOW           # 58~62%
    assert grade_candidate(_c(p=0.55))[0] == GRADE_RED              # 승률 미달
    assert grade_candidate(_c(odds=1.45, p=0.60))[0] == GRADE_RED   # 배당 미달
    assert grade_candidate(_c(approved=False, reject_reason="근거 부족"))[0] == GRADE_RED
    assert grade_candidate(_c(odds=None, ev=None, p=None))[0] == GRADE_BLANK
    blank_p = grade_candidate(_c(p=None, ev=None))
    assert blank_p[0] == GRADE_RED and "근거" in blank_p[1]
    # EV가 아무리 커도 승률이 기준 미달이면 🔴
    assert grade_candidate(_c(p=0.50, ev=0.40))[0] == GRADE_RED


def test_grade_note_speaks_in_money():
    """[3-3] 등급 사유는 승률과 1만 원 기준 실수령액으로 말한다."""
    note = grade_candidate(_c())[1]
    assert "승률 64%" in note and "1만원당 6,200원" in note
    assert "EV" not in note and "이득" not in note
    miss = grade_candidate(_c(odds=1.45, p=0.60))[1]
    # [3] 탈락 사유는 실제 사유를 정확히 — "이상치" 같은 엉뚱한 문구 금지
    assert miss == "배당 1.45 < 하한 1.55"


def test_payout_and_breakeven_helpers():
    from app.engine.markets import breakeven_odds, payout_10k

    assert payout_10k(1.61) == 6100
    assert payout_10k(2.00) == 10000
    assert payout_10k(None) == 0
    assert breakeven_odds(0.58) == 1.724      # 승률 58%의 손익분기 배당
    assert breakeven_odds(None) is None


def test_board_grade_takes_best_market():
    """[A-1] 승패 🔴 + 언더 🟢 → 경기 신호등은 🟢."""
    board = [_c(market="h2h", desc="홈 승", p=0.50), _c()]
    for c in board:
        c["grade"], c["grade_note"] = grade_candidate(c)
    assert board_grade(board) == GRADE_GREEN
    assert best_market(board)["desc"] == "언더 8.5"


def test_rejection_summary_lists_each_market_and_unpriced():
    """[A-1] 전 마켓 🔴이면 검토 목록과 사유를 한 줄로 밝힌다."""
    board = [_c(market="h2h", desc="승패 홈", p=0.51),
             _c(desc="언더 8.5", approved=False, reject_reason="근거 부족 — 2-소스 미달")]
    for c in board:
        c["grade"], c["grade_note"] = grade_candidate(c)
    s = rejection_summary(board, ["런라인"])
    assert "승패 홈" in s and "승률 51%" in s
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
    board = build_board(jg, "mlb", {})                # p_final 없음 = h2h 평가 불가
    priced = [c for c in board if c.get("odds")]
    assert [c["market"] for c in priced] == ["totals"]
    # 배당 없는 마켓도 행으로 남는다 (지우지 않는다)
    assert any(c["market"] == "h2h" and c.get("placeholder") for c in board)


def test_board_always_contains_every_required_market():
    """[2] '평가 가능한 마켓 없음'은 금지 — 배당이 하나도 없어도 전 마켓이 행으로 나온다."""
    jg = _jg(market_probs=None, best_odds={}, alt_markets=[])
    board = build_board(jg, "mlb", {})
    kinds = {c["market"] for c in board}
    assert kinds == {"h2h", "spreads", "totals", "f5"}
    assert all(c["grade"] == GRADE_BLANK for c in board)
    assert len(board) == 7          # 승패2 + 런라인2 + 언더오버1 + F5 2


def test_soccer_board_covers_dc_and_btts():
    """[2] 축구 보드는 승·무·패 / 핸디 ±0.5·±1.5 / 언더오버 / 더블찬스 3종 / BTTS."""
    jg = _jg(sport="soccer", home="Fulham", away="Chelsea",
             market_probs={"Fulham": 0.30, "Draw": 0.30, "Chelsea": 0.40},
             best_odds={"Fulham": 3.30, "Draw": 3.40, "Chelsea": 2.20}, alt_markets=[])
    board = build_board(jg, "soccer", {"Fulham": 0.31, "Chelsea": 0.41})
    assert sum(1 for c in board if c["market"] == "h2h") == 3        # 승·무·패
    assert sum(1 for c in board if c["market"] == "dc") == 3         # 1X · X2 · 12
    assert any(c["market"] == "btts" for c in board)
    assert sum(1 for c in board if c["market"] == "spreads") == 4    # ±0.5 · ±1.5


def test_h2h_row_survives_without_judge():
    """[1] 판정을 못 받아도 배당이 있으면 승패 행은 '근거 부족'으로 남는다."""
    jg = _jg(judge_missing=True)
    board = build_board(jg, "mlb", {})
    h2h = [c for c in board if c["market"] == "h2h"]
    assert len(h2h) == 2
    assert all(c["odds"] for c in h2h)          # 배당은 그대로 표시
    assert all(c["p"] is None and c["grade"] == GRADE_RED for c in h2h)
    assert all("근거" in (c.get("grade_note") or "") for c in h2h)


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
             "odds": 1.81, "p": 0.47, "ev": -0.15, "axes_kr": "모델",
             "approved": True, "reject_reason": None},          # 승률 미달 → 🔴
            {"market": "totals", "side": "Under", "line": 8.5, "desc": "언더 8.5",
             "odds": 1.62, "p": 0.64, "ev": 0.037, "axes_kr": "전문가+실데이터",
             "approved": True, "reject_reason": None},          # 62%↑·1.60↑ → 🟢
            {"market": "spreads", "side": "Texas Rangers", "line": 1.5,
             "desc": "텍사스 레인저스 런라인 +1.5", "odds": 1.55, "p": 0.66, "ev": 0.023,
             "axes_kr": "실데이터", "approved": True, "reject_reason": None},  # 배당 미달 → 🔴
        ],
        "markets_unpriced": [],
    }
    jg.update(over)
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    return jg


def test_board_is_always_rendered_as_table():
    """[2] 마켓 | 배당 | 봇확률 | EV | 신호등 | 근거 | ★ 형식으로 전 행 출력."""
    from app.pipeline import render_game_section

    out = render_game_section(_rendered_jg())
    assert "⑧ 마켓 보드" in out
    # [3-3] 마켓 | 배당 | 승률 | 1만원 수익 | 신호등 | 근거 | ★
    assert "승패 홈 | 1.81 | 47% | 8,100원 | 🔴" in out
    assert "언더 8.5 | 1.62 | 64% | 6,200원 | 🟢" in out
    assert "텍사스 레인저스 런라인 +1.5 | 1.55 | 66% | 5,500원 | 🟢" in out   # 하한 1.55 통과
    assert "★" in out                                   # [3] 마켓별 신뢰도
    assert "평가 가능한 마켓 없음" not in out            # [2] 금지 출력


def test_board_shows_unpriced_markets_as_rows():
    """[2] 배당이 없는 마켓은 행을 지우지 말고 '배당 미수집'으로 남긴다."""
    from app.pipeline import board_row

    row = board_row({"desc": "언더 7.5", "odds": None, "p": 0.58, "ev": None,
                     "grade": "⚪", "grade_note": "배당 확보 시 재평가"})
    assert row.startswith("언더 7.5 | 배당 미수집 | 58% | — | ⚪ | 배당 확보 시 재평가")


def test_easy_layer_points_to_best_market_when_moneyline_dead():
    """[A-1] 승패가 🔴이면 기본층은 '승패는 볼 게 없지만 언더 8.5가 …'로 말한다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    easy = render_game_easy(_rendered_jg()).split(DETAIL_SEP)[0]
    assert "🟢" in easy
    assert "승패는 볼 게 없지만" in easy and "언더 8.5" in easy
    # [3-3] 돈으로 말한다
    assert "1만 원당 6,200원" in easy and "이기는 계산" in easy
    assert "EV" not in easy and "기대값" not in easy


def test_easy_layer_lists_reasons_when_all_markets_dead():
    """[A-1] 전 마켓 🔴일 때만 패스이고, 마켓별 사유를 밝힌다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    from app.engine.markets import grade_candidate

    jg = _rendered_jg()
    for c in jg["market_board"]:
        c["p"] = 0.50                       # 전 마켓 승률 기준 미달
        c["grade"], c["grade_note"] = grade_candidate(c)
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "🔴" in easy
    assert "전 마켓" in easy and "승패 홈" in easy
    assert "승률 58%·배당 1.55 기준" in easy


def test_recommendation_pool_includes_non_moneyline(db_pool=None):
    """[A-5] 추천 후보 풀은 전 마켓 승인 픽 — 승패가 없어도 토탈로 성립한다."""
    from app.pipeline import approved_market_legs

    jg = _rendered_jg()
    jg["market_board"][0].update(approved=False, reject_reason="근거 부족")
    legs = approved_market_legs([jg])
    # [3-5] 레그도 승률 58%↑·배당 1.60↑ 기준을 통과한 것만 (런라인 1.55는 배당 미달)
    assert legs and all(l["market"] != "h2h" for l in legs)
    assert {l["desc"] for l in legs} == {"언더 8.5", "텍사스 레인저스 런라인 +1.5"}


# ---------------------------------------------------------------- [1] 회귀: 배당↔보드 일관성

def test_header_odds_imply_non_empty_board():
    """[1] 회귀: 헤더에 배당이 찍히면 마켓 보드가 비어 있을 수 없다.

    실사고: 상세 헤더에 에인절스(2.47) vs 클리블랜드(1.63)가 표시되는데
    마켓 보드는 "(평가 가능한 마켓 없음)"이었다. 판정(p_claude) 미수신 시
    _compute_picks가 경기를 통째로 건너뛰어 board를 만들지 않은 탓이다.
    """
    from app.pipeline import _compute_picks
    from app.config import Settings

    jg = {
        "game_id": 410, "sport": "mlb", "status": "scheduled",
        "home": "Los Angeles Angels", "away": "Cleveland Guardians", "league": "MLB",
        "starts_at_kst": "08/25 10:38", "model_valid": True, "p_model": 0.42,
        "p_market": 0.40,
        "market_probs": {"Los Angeles Angels": 0.40, "Cleveland Guardians": 0.60},
        "best_odds": {"Los Angeles Angels": 2.47, "Cleveland Guardians": 1.63},
        "alt_markets": [{"market": "totals", "side": "Under", "line": 8.5,
                         "odds": 1.87, "p": 0.55}],
        "expert_picks": [], "stats": {},
        # p_claude 없음 = 판정 미수신
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb")
    board = jg["market_board"]
    assert board, "헤더에 배당이 있는데 보드가 비면 안 된다"
    priced = [c for c in board if c.get("odds")]
    assert {c["odds"] for c in priced} >= {2.47, 1.63, 1.87}   # 헤더와 같은 값이 보드에도
    assert all(not c.get("approved") for c in board)           # 판정 미수신 → 추천은 전부 제외


def test_display_and_calculation_share_one_odds_source():
    """[1] 표시용(best_odds)과 계산용(마켓 보드)이 같은 객체에서 나온다."""
    from app.config import Settings
    from app.pipeline import _compute_picks

    best = {"Los Angeles Angels": 2.47, "Cleveland Guardians": 1.63}
    jg = {
        "game_id": 410, "sport": "mlb", "status": "scheduled",
        "home": "Los Angeles Angels", "away": "Cleveland Guardians", "league": "MLB",
        "starts_at_kst": "08/25 10:38", "model_valid": True, "p_model": 0.42,
        "p_market": 0.40, "p_claude": 0.44,
        "market_probs": {"Los Angeles Angels": 0.40, "Cleveland Guardians": 0.60},
        "best_odds": best, "alt_markets": [], "expert_picks": [], "stats": {},
        "judge_confidence": "medium",
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb")
    h2h = {c["side"]: c["odds"] for c in jg["market_board"] if c["market"] == "h2h"}
    assert h2h == {k: round(v, 2) for k, v in best.items()}


def test_board_never_says_no_markets():
    """[2] '평가 가능한 마켓 없음' 문구는 어떤 경로로도 출력되지 않는다."""
    from app.config import Settings
    from app.pipeline import _compute_picks, render_game_section

    jg = {
        "game_id": 1, "sport": "mlb", "status": "scheduled", "status_label": "",
        "home": "Los Angeles Angels", "away": "Cleveland Guardians", "league": "MLB",
        "starts_at_kst": "08/25 10:38", "model_valid": False, "p_model": 0.5,
        "p_market": None, "market_probs": None, "best_odds": {}, "alt_markets": [],
        "expert_picks": [], "stats": {},
        "research": {"home_recent_form": {"form": "WLWLL"}},
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb")
    out = render_game_section(jg)
    assert "평가 가능한 마켓 없음" not in out
    assert out.count("배당 미수집") >= 5        # 전 마켓 행이 남아 있다
    assert "F5(5이닝)" in out                    # 야구 필수 마켓까지 행으로
