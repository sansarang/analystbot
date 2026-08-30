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


def test_grade_uses_win_prob_only():
    """[§8-18] 등급은 **승률만으로** 판정한다.

    제거: 배당 하한(시장 기준) · 시장 괴리 상한 · EV.
    남은 질문은 "이길 확률이 얼마인가" 하나다.
    """
    assert grade_candidate(_c())[0] == GRADE_GREEN                  # 64%
    assert grade_candidate(_c(p=0.59))[0] == GRADE_YELLOW           # 58~62%
    assert grade_candidate(_c(p=0.55))[0] == GRADE_RED              # 승률 미달
    # 배당이 낮아도 승률이 되면 등급이 유지된다 (시장 기준을 쓰지 않는다)
    assert grade_candidate(_c(odds=1.05, p=0.64))[0] == GRADE_GREEN
    assert grade_candidate(_c(approved=False, reject_reason="근거 부족"))[0] == GRADE_RED
    # 확률이 없으면 등급을 매길 수 없다
    assert grade_candidate(_c(p=None, ev=None))[0] == GRADE_BLANK
    # EV가 아무리 커도 승률이 기준 미달이면 🔴
    assert grade_candidate(_c(p=0.50, ev=0.40))[0] == GRADE_RED


def test_grade_note_speaks_in_probability_not_money():
    """[§8-18] 등급 사유는 **승률로만** 말한다 — 돈 얘기를 하지 않는다."""
    note = grade_candidate(_c())[1]
    assert "승률 64%" in note
    for banned in ("원", "1만", "배당", "손익분기"):
        assert banned not in note, f"등급 사유에 '{banned}'가 남아 있다"


def test_money_helpers_are_removed():
    """[§8-18] 돈 계산 헬퍼를 삭제했다 — 봇은 얼마를 걸라고도, 얼마 번다고도 말하지 않는다."""
    import app.engine.markets as mk

    assert not hasattr(mk, "payout_10k")
    assert not hasattr(mk, "breakeven_odds")

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
    """야구 보드는 승패만. 런라인 alt는 무시한다."""
    jg = _jg(market_probs=None, best_odds={},
             alt_markets=[{"market": "spreads", "side": "Away Nine", "line": 1.5,
                           "odds": 1.98, "p": 0.56}])
    board = build_board(jg, "mlb", {})
    assert {c["market"] for c in board} == {"h2h"}
    assert not any(c["market"] == "spreads" for c in board)
    assert not any(c["market"] == "totals" for c in board)


def test_board_works_without_any_odds():
    """야구는 배당·분포 없이 승패 두 행만 남긴다."""
    jg = _jg(market_probs=None, best_odds={}, alt_markets=[])
    jg["sport"] = "mlb"
    board = build_board(jg, "mlb", {"Detroit Tigers": 0.55, "Tampa Bay Rays": 0.45})
    kinds = {c["market"] for c in board}
    assert kinds == {"h2h"}
    assert not any(c["market"] in ("spreads", "f5", "totals") for c in board)


def test_generated_total_lines_are_half_points_only():
    """[§8-27] ⚠️ 정수 라인은 만들지 않는다.

    ① 총득점이 정확히 그 값이면 **푸시**인데 현재 산출은 언더에 합산한다
       (실측: 라인 9.0 언더 41.3%로 나왔으나 실제 언더 29.3% · 푸시 12.0%).
    ② 오버 확률은 9.0과 9.5가 완전히 같다 — 중복 행만 늘어난다.
    """
    from app.engine.scoring import _default_total_lines

    for expected in (9.80, 10.37, 6.23, 8.92):
        lines = _default_total_lines(expected)
        assert all(abs(x % 1 - 0.5) < 1e-9 for x in lines), f"정수 라인 포함: {lines}"
        assert len(set(lines)) == len(lines)


def test_board_always_contains_every_required_market():
    """[2] '평가 가능한 마켓 없음'은 금지 — 배당이 하나도 없어도 전 마켓이 행으로 나온다."""
    jg = _jg(market_probs=None, best_odds={}, alt_markets=[])
    board = build_board(jg, "mlb", {})
    kinds = {c["market"] for c in board}
    assert kinds == {"h2h"}
    assert len(board) == 2
    assert all(c["grade"] == GRADE_BLANK for c in board)


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
    assert all(c["odds"] for c in h2h)          # 라인·배당 자체는 수집돼 있다
    # [§8-18] 확률이 없으면 등급을 매길 수 없다 → ⚪ (🔴은 '기준 미달'이라는 뜻이다)
    assert all(c["p"] is None and c["grade"] == GRADE_BLANK for c in h2h)
    assert all(c.get("grade_note") for c in h2h)


def test_stale_snapshot_is_labelled_opening_odds():
    """[A-3] 오래된 스냅샷으로 폴백하면 '(개장 배당)' 라벨을 붙인다."""
    jg = _jg(odds_stale=True)
    cands = build_candidates(jg, "mlb", {"Detroit Tigers": 0.46, "Tampa Bay Rays": 0.56})
    assert all("(개장 배당)" in c["desc"] for c in cands)


def test_every_candidate_carries_a_grade():
    """[A-4] 마켓 보드는 전 후보에 등급과 사유를 갖는다 (표로 항상 출력하기 위함)."""
    jg = _jg(alt_markets=[{"market": "spreads", "side": "Tampa Bay Rays",
                           "line": 1.5, "odds": 1.98, "p": 0.56}])
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
            {"market": "spreads", "side": "Texas Rangers", "line": 1.5,
             "desc": "텍사스 레인저스 런라인 +1.5", "odds": 1.55, "p": 0.66, "ev": 0.023,
             "axes_kr": "전문가+실데이터", "approved": True, "reject_reason": None},
        ],
        "markets_unpriced": [],
    }
    jg.update(over)
    for c in jg["market_board"]:
        c["grade"], c["grade_note"] = grade_candidate(c)
    return jg


def test_board_is_always_rendered_as_table():
    """[§8-18] 마켓 | 승률 | 신호등 | 근거 | ★ — 배당·돈 열은 뺐다."""
    from app.pipeline import render_game_section

    out = render_game_section(_rendered_jg())
    assert "⑧ 마켓 보드" in out
    assert "승패 홈 | 47% | 🔴" in out
    assert "텍사스 레인저스 런라인 +1.5 | 66% | 🟢" in out
    for banned in ("| 1.81 |", "8,100원", "6,200원"):
        assert banned not in out, f"보드에 '{banned}'가 남아 있다"
    assert "★" in out                                   # [3] 마켓별 신뢰도
    assert "평가 가능한 마켓 없음" not in out            # [2] 금지 출력


def test_board_shows_unpriced_markets_as_rows():
    """[2] 배당이 없는 마켓은 행을 지우지 말고 '확률 미산출'으로 남긴다."""
    from app.pipeline import board_row

    row = board_row({"desc": "언더 7.5", "odds": None, "p": 0.58, "ev": None,
                     "grade": "⚪", "grade_note": "배당 확보 시 재평가"})
    assert row.startswith("언더 7.5 | 58% | ")


def test_easy_layer_points_to_best_market_when_moneyline_dead():
    """[A-1] 승패가 🔴이면 기본층은 '승패는 볼 게 없지만 런라인이 …'로 말한다."""
    from app.pipeline import DETAIL_SEP, render_game_easy

    easy = render_game_easy(_rendered_jg()).split(DETAIL_SEP)[0]
    assert "🟢" in easy
    assert "승패는 볼 게 없지만" in easy and "런라인 +1.5" in easy
    # [3-3] 돈으로 말한다
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
    assert "승률 58% 기준" in easy


def test_recommendation_pool_includes_non_moneyline(db_pool=None):
    """[A-5] 추천 후보 풀은 전 마켓 승인 픽 — 승패가 없어도 런라인으로 성립한다."""
    from app.pipeline import approved_market_legs

    jg = _rendered_jg()
    jg["lineup_status"] = "confirmed"   # 야구는 확정 전 추천 제외
    jg["market_board"][0].update(approved=False, reject_reason="근거 부족")
    legs = approved_market_legs([jg])
    # [§8-18] 배당 하한은 제거됐다. 승률 58%↑·라인업 확정·승인만 본다.
    assert legs and all(l["market"] != "h2h" for l in legs)
    assert {l["desc"] for l in legs} == {"텍사스 레인저스 런라인 +1.5"}


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
        "alt_markets": [{"market": "spreads", "side": "Cleveland Guardians",
                         "line": 1.5, "odds": 1.87, "p": 0.55}],
        "expert_picks": [], "stats": {},
        # p_claude 없음 = 판정 미수신
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb")
    board = jg["market_board"]
    assert board, "헤더에 배당이 있는데 보드가 비면 안 된다"
    priced = [c for c in board if c.get("odds")]
    assert {c["odds"] for c in priced} >= {2.47, 1.63}   # 야구 승패 배당만 (알트 무시)
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
    assert {c["market"] for c in jg["market_board"]} == {"h2h"}
