"""[§9-라인업 의도] **신호는 라인업이 아니라 평소와의 차이다.**

명단 자체는 정보가 얇다. "오늘 1번은 김현수"는 매일 같으면 아무것도 말하지 않는다.
"""
import pytest

from app.engine import lineup_intent as LI
from app.engine.lineup_diff import (MIN_HISTORY, TYPE_TO_CELL, diff_lineup,
                                    parse_order, summarize, usual_from)

USUAL_ORDER = ["김도영(3루수)", "박찬호(유격수)", "최형우(지명타자)", "나성범(우익수)",
               "소크라테스(중견수)", "변우혁(1루수)", "김선빈(2루수)",
               "한준수(포수)", "이우성(좌익수)"]


def _hist(n=8, order=None):
    return [parse_order(order or USUAL_ORDER) for _ in range(n)]


# ------------------------------------------------------------ 파싱

def test_position_is_parsed_not_dropped():
    """🔴 크롤러가 positionName을 버리고 있었다 — 지명타자·포지션 변경을
    영영 감지할 수 없었다."""
    got = parse_order("김도영(3루수)-최형우(지명타자)")
    assert got == [("김도영", "3루수"), ("최형우", "지명타자")]


def test_order_without_position_still_parses():
    assert parse_order("A-B-C") == [("A", ""), ("B", ""), ("C", "")]


def test_json_list_is_accepted():
    assert parse_order('["A(포수)"]') == [("A", "포수")]


# ------------------------------------------------------------ 평소 라인업

def test_thin_history_makes_no_baseline():
    """🔴 3경기로 '평소'를 말하면 그 3경기의 우연이 기준이 된다."""
    assert usual_from(_hist(MIN_HISTORY - 1)) == {}
    assert usual_from(_hist(MIN_HISTORY))


def test_regulars_need_to_appear_in_half_the_games():
    """대타 1회 출전을 주전으로 세면 안 된다."""
    hist = _hist(8)
    hist[0] = parse_order(["대타왕(좌익수)"] + USUAL_ORDER[1:])
    u = usual_from(hist)
    assert "대타왕" not in u["regulars"] and "김도영" in u["regulars"]


# ------------------------------------------------------------ 변경점 추출

def test_no_baseline_means_no_comparison_not_no_change():
    """🔴 첫 관측을 '변경 없음'으로 적으면 거짓이 된다."""
    s = summarize([], usual_from(_hist(2)))
    assert "비교 불가" in s["headline"] and "변경 없음" not in s["headline"]


def test_unchanged_lineup_is_recorded_as_information():
    """변화 없음도 정보다."""
    u = usual_from(_hist(8))
    s = summarize(diff_lineup(parse_order(USUAL_ORDER), u), u)
    assert "그대로" in s["headline"]


def test_regular_out_is_detected():
    u = usual_from(_hist(8))
    today = parse_order([x for x in USUAL_ORDER if not x.startswith("나성범")]
                        + ["백업(우익수)"])
    types = {c["type"] for c in diff_lineup(today, u)}
    assert "regular_out" in types and "new_starter" in types


def test_demotion_from_top_order_is_detected():
    u = usual_from(_hist(8))
    swapped = USUAL_ORDER[:]
    swapped.remove("최형우(지명타자)")
    swapped.append("최형우(지명타자)")          # 3번 → 9번
    c = [x for x in diff_lineup(parse_order(swapped), u)
         if x["type"] == "order_demote"]
    assert c and "최형우" in c[0]["detail"]


def test_dh_rest_is_told_apart_from_a_position_change():
    """주전이 수비 없이 타석만 서는 것은 **체력 관리 신호**다."""
    u = usual_from(_hist(8))
    today = parse_order([x.replace("나성범(우익수)", "나성범(지명타자)")
                         .replace("최형우(지명타자)", "최형우(1루수)")
                         for x in USUAL_ORDER])
    types = {c["type"]: c for c in diff_lineup(today, u)}
    assert "dh_rest" in types and "나성범" in types["dh_rest"]["detail"]


def test_every_change_type_maps_to_an_existing_cell():
    """🔴 새 칸을 만들지 않는다 — 기존 다섯 칸에 배분한다."""
    from app.engine.card import CELL_KEYS

    assert set(TYPE_TO_CELL.values()) <= set(CELL_KEYS)


def test_bullpen_entry_removal_needs_a_key_list():
    """누가 '핵심'인지 정하는 것은 이 층의 일이 아니다 — 호출부가 산출해 넘긴다."""
    from app.engine.lineup_diff import bullpen_absences

    assert bullpen_absences(["A", "C"], None) == []
    got = bullpen_absences(["A", "C"], ["A", "B"])
    assert len(got) == 1 and got[0]["who"] == "B" and got[0]["cell"] == "bullpen"


def test_missing_roster_is_not_read_as_everyone_out():
    """🔴 빈 명단을 '전원 말소'로 읽으면 매일 거짓 신호가 난다."""
    from app.engine.lineup_diff import bullpen_absences

    assert bullpen_absences(None, ["A", "B"]) == []
    assert bullpen_absences([], ["A", "B"]) == []


def test_key_relievers_come_from_observed_appearances():
    """🔴 누가 마무리인지 **지어내지 않는다** — 등판 횟수는 관측이다."""
    from app.collectors.kbo_usage import summarize

    def _game(i):
        pen = [{"name": f"불펜{j}", "is_starter": False, "innings": 1.0,
                "batters": 4, "pitches": 15}
               for j in range(1, 3 + (i % 2))]
        return {"date": f"2026-08-2{i}", "score": None,
                "pitchers": [{"name": "선발", "is_starter": True, "innings": 5.0,
                              "batters": 20, "pitches": 80}] + pen}

    games = [_game(i) for i in range(1, 6)]
    out = summarize(games)
    assert out["key_relievers"], "핵심 불펜이 비었다"
    # 자주 나온 순이어야 한다
    counts = out["relief_appearances"]
    assert list(counts.values()) == sorted(counts.values(), reverse=True)
    assert out["key_relievers"][0] == max(counts, key=lambda k: counts[k])


# ------------------------------------------------------------ 득점 방향 [7]

def test_opposite_directions_cancel_out():
    """🔴 한쪽만 보고 방향을 정하면 상대의 같은 크기 변화를 무시한다."""
    d = LI.scoring_direction(
        [{"change_type": "regular_out", "scoring_dir": "저득점"}],
        [{"change_type": "bullpen_out", "scoring_dir": "다득점"}])
    assert d["dir"] == "중립"


def test_no_judged_item_is_held_not_neutral():
    """'보류'와 '중립'은 다르다 — 판단 못 한 것과 판단해서 중립인 것."""
    assert LI.scoring_direction([], [])["dir"] == "보류"
    assert LI.scoring_direction(
        [{"change_type": "x", "scoring_dir": "보류"}], [])["dir"] == "보류"


def test_one_sided_absence_points_one_way():
    d = LI.scoring_direction(
        [{"change_type": "regular_out", "scoring_dir": "저득점"}], [])
    assert d["dir"] == "저득점"


# ------------------------------------------------------------ 핸디캡 [7]

def test_one_sided_absence_supports_a_handicap():
    n = LI.handicap_note([{"type": "regular_out"}], [])
    assert n["support"] == "away" and "점수차 확대" in n["detail"]


def test_both_sides_missing_regulars_cancels_the_handicap_basis():
    """🔴 양쪽 다 주전급 결장이면 상쇄 — 근거 없음."""
    n = LI.handicap_note([{"type": "regular_out"}], [{"type": "regular_out"}])
    assert n["support"] is None and "상쇄" in n["detail"]


def test_no_changes_means_no_handicap_note():
    assert LI.handicap_note([], [])["detail"] == ""


# ------------------------------------------------------------ 사실/해석 분리

def test_changes_enter_research_as_facts_not_verdicts():
    """🔴 사실은 코드가 쓰고 해석만 LLM이 쓴다."""
    r = {}
    LI.merge_changes_into_research(
        r, "home", [{"type": "regular_out", "cell": "batting",
                     "detail": "평소 4번 나성범 빠짐"}], "변경 1건")
    assert r["home_lineup_changes"]["batting"] == ["평소 4번 나성범 빠짐"]
    blob = str(r)
    for verdict in ("▲", "▼", "체력", "부상"):
        assert verdict not in blob, "사실 층에 해석이 섞였다"


def test_changes_land_in_the_right_cell_of_the_card():
    from app.engine.card import build_card

    r = {"home_usage": {"score_games": 3, "runs_per_game_l3": 5.0,
                        "relief_batters_l3": 40},
         "home_offense": {"ops": 0.75}}
    LI.merge_changes_into_research(
        r, "home", [{"type": "regular_out", "cell": "batting",
                     "detail": "평소 4번 나성범 빠짐"}], "변경 1건")
    card = build_card({"home": "H", "away": "A"}, r)
    assert any("나성범" in f for f in card["home"]["batting"]["facts"])
    assert not any("나성범" in f for f in card["home"]["bullpen"]["facts"])


def test_lineup_changes_also_reach_the_scoring_cell():
    """[7] 라인업 변경은 승패보다 총득점에 더 크게 영향을 준다."""
    from app.engine.card import build_card

    r = {"home_usage": {"score_games": 3, "runs_per_game_l3": 5.0},
         "away_usage": {"score_games": 3, "runs_per_game_l3": 4.0}}
    LI.merge_changes_into_research(
        r, "home", [{"type": "regular_out", "cell": "batting",
                     "detail": "평소 4번 나성범 빠짐"}], "변경 1건")
    card = build_card({"home": "H", "away": "A", "home_kr": "홈팀"}, r)
    assert any("나성범" in f for f in card["scoring"]["facts"])


# ------------------------------------------------------------ 30분 전 [2]

def test_final_window_is_the_last_30_minutes():
    from datetime import UTC, datetime, timedelta

    from app.pipeline import is_final_window

    now = datetime(2026, 8, 27, 9, 0, tzinfo=UTC)
    assert is_final_window(now + timedelta(minutes=20), now)
    assert not is_final_window(now + timedelta(minutes=90), now)
    assert not is_final_window(now - timedelta(minutes=5), now), "이미 시작한 경기"
    assert not is_final_window(None, now)


def test_market_delta_names_what_changed():
    """[8] 무엇이 바뀌어 어느 마켓 판정이 어떻게 달라졌는지."""
    from app.pipeline import _market_delta

    out = _market_delta({"승패": "home/보통", "득점": "보통", "핸디": None,
                         "언더오버": None},
                        {"승패": "home/낮음", "득점": "저득점 예상", "핸디": None,
                         "언더오버": "언더 쪽"})
    assert "승패" in out and "득점" in out and "언더오버" in out
    assert "핸디" not in out, "안 바뀐 마켓을 쓰면 안 된다"


# ------------------------------------------------- 백필 (실제 출전 기록)

def test_boxscore_takes_the_first_row_per_slot():
    """같은 타순의 **첫 행이 선발**이고 뒤는 교체다."""
    import json

    from app.collectors.kbo_boxscore import parse_starting_order

    rows = []
    for slot, pos, name in [("1", "중", "황성빈"), ("1", "타우", "윤동희"),
                            ("2", "지", "나승엽"), ("3", "좌", "레이예스"),
                            ("4", "三", "한동희"), ("5", "一", "고승민"),
                            ("6", "二", "한태양"), ("7", "유", "전민재"),
                            ("8", "포", "손성빈"), ("9", "우중", "장두성")]:
        rows.append({"row": [{"Text": slot}, {"Text": pos}, {"Text": name}]})
    got = parse_starting_order(json.dumps({"rows": rows}))
    assert got[0] == "황성빈(중견수)", got[0]
    assert "윤동희" not in " ".join(got), "교체 선수가 선발로 들어갔다"
    assert got[-1] == "장두성(우익수)", "수비 이동 표기의 첫 글자를 써야 한다"


def test_incomplete_boxscore_is_discarded():
    """🔴 9명이 안 되는 라인업으로 '평소'를 만들면 그 결손이 매번 '변경'으로 잡힌다."""
    import json

    from app.collectors.kbo_boxscore import parse_starting_order

    rows = [{"row": [{"Text": str(i)}, {"Text": "중"}, {"Text": f"선수{i}"}]}
            for i in range(1, 8)]
    assert parse_starting_order(json.dumps({"rows": rows})) == []


def test_substitute_markers_are_recognised():
    from app.collectors.kbo_boxscore import is_substitute, normalize_position

    assert is_substitute("타우") and is_substitute("주유")
    assert not is_substitute("중") and not is_substitute("지")
    assert normalize_position("유二") == "유격수", "수비 이동은 첫 위치를 쓴다"
    assert normalize_position("포수") == "포수", "정식 명칭도 그대로 통과"


def test_source_note_distinguishes_the_two_kinds():
    """🔴 실제 출전 기록과 발표 라인업은 **같은 것이 아니다.**"""
    from app.collectors.lineup_history import source_note

    assert source_note({"boxscore": 10}) == "실제 출전 기록 10경기"
    mixed = source_note({"boxscore": 7, "crawler": 3})
    assert "실제 출전 기록 7경기" in mixed and "발표 라인업 3경기" in mixed
    assert source_note({}) == ""
