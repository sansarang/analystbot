"""확정 타순 유사 전적 — 점수 누수·소스 혼합·표본 부족을 막는다."""
from datetime import UTC, datetime, timedelta

from app.engine.lineup_diff import parse_order
from app.engine.lineup_intent import render as render_intent
from app.engine.lineup_record import (
    MIN_RATE_GAMES,
    build_matchup,
    format_record,
    overlap,
    similar_from_rows,
    strip_outcome_for_judge,
    team_result,
)
from app.engine.performance import FIELD_TO_COEFFICIENT, UNMAPPED_FIELDS, WinProbAdjuster
from app.config import Settings

USUAL = ["김도영(3루수)", "박찬호(유격수)", "최형우(지명타자)", "나성범(우익수)",
         "소크라테스(중견수)", "변우혁(1루수)", "김선빈(2루수)",
         "한준수(포수)", "이우성(좌익수)"]

T0 = datetime(2026, 8, 27, 9, 30, tzinfo=UTC)  # 경기 시작 (KST 18:30)


def _row(gid, order, hs, aws, *, start=None, source="boxscore", side="home"):
    return {
        "game_id": gid, "side": side, "batting_order": order, "source": source,
        "home_score": hs, "away_score": aws,
        "starts_at": start if start is not None else T0 - timedelta(days=gid),
    }


def test_name_drift_still_counts_as_same_lineup():
    today = parse_order([x.replace("김도영", "김도영.") for x in USUAL])
    past = parse_order(USUAL)
    ov = overlap(today, past)
    assert ov["n_shared"] == 9 and ov["qualifies"]


def test_seven_shared_names_qualify():
    today = parse_order(USUAL)
    past = parse_order(USUAL[:7] + ["백업A(포수)", "백업B(좌익수)"])
    assert overlap(today, past)["qualifies"]
    few = parse_order(USUAL[:4] + ["A(1루수)", "B(2루수)", "C(유격수)",
                                   "D(포수)", "E(좌익수)"])
    assert not overlap(today, few)["qualifies"]


def test_crawler_rows_are_not_used_as_results():
    """발표 라인업과 실제 출전 기록을 같은 전적으로 섞으면 안 된다."""
    today = parse_order(USUAL)
    rows = [_row(1, USUAL, 8, 2, source="crawler")]
    rec = similar_from_rows(today, rows, T0)
    assert rec["n"] == 0


def test_same_game_and_future_scores_are_excluded():
    """오늘 점수·이후 점수는 전적에 못 넣는다."""
    today = parse_order(USUAL)
    rows = [
        _row(99, USUAL, 10, 0, start=T0),                 # 이 경기
        _row(98, USUAL, 9, 1, start=T0 + timedelta(hours=1)),
        _row(1, USUAL, 3, 2, start=T0 - timedelta(days=2), side="home"),
    ]
    rec = similar_from_rows(today, rows, T0)
    assert rec["n"] == 1 and rec["w"] == 1 and rec["games"][0]["game_id"] == 1


def test_thin_sample_has_no_win_pct():
    today = parse_order(USUAL)
    rows = [_row(i, USUAL, 5, 1, start=T0 - timedelta(days=i))
            for i in range(1, MIN_RATE_GAMES)]
    rec = similar_from_rows(today, rows, T0)
    assert rec["n"] == MIN_RATE_GAMES - 1
    assert rec["win_pct"] is None
    line = format_record(rec)
    assert "표본 부족" in line and "미산출" in line
    assert "%" not in line  # 전적률 숫자를 붙이면 안 된다


def test_three_decided_games_get_a_rate():
    today = parse_order(USUAL)
    rows = [
        _row(1, USUAL, 5, 1, start=T0 - timedelta(days=1)),  # home W
        _row(2, USUAL, 1, 4, start=T0 - timedelta(days=2)),  # home L
        _row(3, USUAL, 2, 2, start=T0 - timedelta(days=3)),  # D — 분모에서 제외
        _row(4, USUAL, 6, 3, start=T0 - timedelta(days=4)),  # home W
    ]
    rec = similar_from_rows(today, rows, T0)
    assert rec["w"] == 2 and rec["l"] == 1 and rec["d"] == 1
    assert rec["win_pct"] == round(2 / 3, 4)


def test_kbo_draw_is_not_a_win():
    assert team_result("home", 3, 3) == "D"
    assert team_result("away", 3, 4) == "W"
    assert team_result("home", None, 1) is None


def test_duplicate_game_id_is_counted_once():
    today = parse_order(USUAL)
    rows = [_row(1, USUAL, 5, 1), _row(1, USUAL, 5, 1)]
    rec = similar_from_rows(today, rows, T0)
    assert rec["n"] == 1


def test_matchup_requires_both_nines_and_makes_no_probability():
    jg = {
        "home": "Kia Tigers", "away": "LG Twins",
        "research": {
            "home_lineup": {"order": "-".join(USUAL)},
            "away_lineup": {"order": ""},
            "lineup_record": {},
        },
        "lineup_intent": {"changes": {"home": [], "away": []}, "items": {}},
    }
    mu = build_matchup(jg)
    assert mu["comparable"] is False
    assert "favored" not in mu and "win_pct" not in mu and "p" not in mu

    jg["research"]["away_lineup"] = {"order": "-".join(USUAL[::-1])}
    jg["lineup_intent"]["changes"] = {
        "home": [{"type": "regular_out"}], "away": [],
    }
    mu = build_matchup(jg)
    assert mu["comparable"] is True
    assert "홈만 주전 이탈" in mu["gap"]
    assert "favored" not in mu


def test_strip_outcome_drops_scores():
    jg = {"game_id": 1, "home_score": 8, "away_score": 1,
          "status": "final", "verdict": "이미 끝남", "research": {"x": 1}}
    out = strip_outcome_for_judge(jg)
    assert out["status"] == "scheduled"
    assert "home_score" not in out and "away_score" not in out
    assert "verdict" not in out
    assert jg["home_score"] == 8  # 원본 보존


def test_lineup_record_is_unmapped_not_a_coefficient():
    assert "lineup_record" in UNMAPPED_FIELDS
    assert "lineup_matchup" in UNMAPPED_FIELDS
    assert "lineup_record" not in FIELD_TO_COEFFICIENT
    out = WinProbAdjuster(Settings(_env_file=None)).adjust(
        0.5, {"home": "H", "away": "A"},
        {"lineup_record": {"home": {"n": 5}},
         "lineup_matchup": {"comparable": True, "gap": "주전 이탈 없음"}},
        "kbo")
    assert "확정 타순 유사 전적" in out["unused"]
    assert "확정 타순 대결" in out["unused"]
    assert out["p"] == 0.5  # λ 조정 없음


def test_card_render_includes_record_line():
    jg = {
        "home": "KIA", "away": "LG",
        "lineup_intent": {
            "headline": {"home": "평소 라인업 그대로 (최근 8경기 대비 변경 없음)",
                         "away": "평소 라인업 그대로 (최근 8경기 대비 변경 없음)"},
            "items": {"home": [], "away": []},
        },
        "research": {
            "lineup_record": {
                "home": {"n": 5, "w": 3, "l": 2, "d": 0, "win_pct": 0.6,
                         "source_note": "실제 출전 기록"},
            },
        },
        "lineup_matchup": {"comparable": True, "gap": "주전 이탈 없음"},
    }
    lines = render_intent(jg)
    assert any("타순 전적" in x and "3승" in x for x in lines)
    assert any("타순 대결" in x for x in lines)
