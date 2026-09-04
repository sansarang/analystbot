"""[변수체계 C2·C5 2026-09-04] 자료11 — 이동·연전·날씨 · BvP 금지.

🔴 대원칙: 판정 입력은 최근 3~5경기(불펜 최근 3일)만. 시즌 누적·통산·
   상대전적 금지. 이 자료의 세 값이 그 선 안에 있는지 잠근다.
     연전  최근 경기 **날짜 배열**에서 센다
     이동  최근 경기의 **홈/원정 전환**에서 본다 (거리 아님 — 구장 좌표 없음)
     날씨  **오늘** 예보

⚠️ 플래툰 "성적"(좌투 상대 타율 등)은 **넣지 않았다.** 그것은 시즌 스플릿이라
   대원칙이 막고, 최근 3~5경기로는 좌/우 표본이 각 1~2경기라 신호가 안 나온다.
   대신 오늘 선발의 **투구 손**만 싣는다 — 오늘의 사실이지 누적이 아니다.
"""
from datetime import date

import pytest

from app.engine.context_recent import (
    attach, build, consecutive_days, travel,
)


# ─────────────────── 연전 ───────────────────

def test_consecutive_counts_today_and_stops_at_a_rest_day():
    today = date(2026, 9, 4)
    assert consecutive_days(["2026-09-03", "2026-09-02"], today) == 3
    assert consecutive_days(["2026-09-03"], today) == 2
    assert consecutive_days(["2026-09-01"], today) == 1, "휴식일에서 끊긴다"


def test_unknown_dates_are_none_not_zero():
    """🔴 "휴식 충분"과 "모른다"를 같은 값으로 적으면 없는 사실을 읽는다."""
    assert consecutive_days([], date(2026, 9, 4)) is None
    assert consecutive_days(["알 수 없음"], date(2026, 9, 4)) is None
    assert consecutive_days(["2026-09-03"], None) is None


def test_duplicate_dates_do_not_inflate_the_streak():
    assert consecutive_days(["2026-09-03", "2026-09-03", "2026-09-02"],
                            date(2026, 9, 4)) == 3


# ─────────────────── 이동 ───────────────────

@pytest.mark.parametrize("flags,today_home,expected", [
    ([False, False], True, "원정→홈"),
    ([True, True], False, "홈→원정"),
    ([True], True, "홈 연속"),
    ([False], False, "원정 연속"),
    ([], True, None),
    ([True], None, None),
])
def test_travel_reports_the_switch_only(flags, today_home, expected):
    assert travel(flags, today_home) == expected


def test_travel_never_claims_a_distance():
    """🔴 구장 좌표가 없다. 모르는 것을 추정해 넣으면 그 추정이 변수 근거가 된다."""
    from pathlib import Path

    src = Path("app/engine/context_recent.py").read_text(encoding="utf-8")
    for banned in ("km", "distance", "위도", "경도", "latitude", "haversine"):
        assert banned not in src, banned


# ─────────────────── 조립 ───────────────────

def _jg():
    return {"sport": "kbo", "starts_at": "2026-09-04T09:30:00+00:00",
            "research": {
                "home_usage": {"games": [{"date": "2026-09-03", "home": False}]},
                "away_usage": {"games": [{"date": "2026-09-03", "home": True}]},
                "weather": {"요약": "맑음 24도"},
                "home_starter": {"throws": "L"}}}


def test_build_collects_all_three_axes():
    out = build(_jg())
    assert out["home"]["연전"] == 2 and out["home"]["이동"] == "원정→홈"
    assert out["away"]["이동"] == "홈→원정"
    assert out["날씨"] == {"요약": "맑음 24도"}
    assert out["선발손"] == {"home": "L"}


def test_empty_research_produces_an_empty_block():
    """재료가 없으면 프롬프트에 아무것도 안 붙는다 — 빈 칸을 만들지 않는다."""
    assert build({"sport": "kbo", "research": {}}) == {}
    jg = {"sport": "kbo", "research": {}}
    assert attach(jg) is False
    assert jg["material11_status"] == "해당없음"


def test_module_collects_nothing_new():
    """🔴 새 수집 금지 — 이미 research 에 있는 것만 읽는다."""
    from pathlib import Path

    src = Path("app/engine/context_recent.py").read_text(encoding="utf-8")
    for banned in ("httpx", "PoliteClient", "await ", "async def", "fetch"):
        assert banned not in src, banned


# ─────────────────── 프롬프트 ───────────────────

def test_material11_reaches_the_prompt_only_when_present():
    from app.engine.matchup import render_matchup_prompt

    jg = _jg()
    plain = render_matchup_prompt(jg, boxes={}, news={}, prev=None)
    assert "11. 최근 맥락" not in plain, "안 붙였는데 블록이 있다"

    attach(jg)
    out = render_matchup_prompt(jg, boxes={}, news={}, prev=None)
    assert "11. 최근 맥락" in out
    assert "원정→홈" in out and "맑음 24도" in out
    assert "{{" not in out


def test_material11_says_it_is_a_reference_not_a_verdict():
    from app.engine.matchup import _M11_BLOCK

    assert "변수의 크기를 뒷받침하는 참조" in _M11_BLOCK
    assert "우세를 정하지 마라" in _M11_BLOCK
    assert "거리가 아니다" in _M11_BLOCK


# ─────────────────── C5 BvP 금지 ───────────────────

def test_bvp_and_head_to_head_are_banned_in_the_prompt():
    from app.engine.prompts import MATCHUP

    assert "타자 대 투수 상대 전적(BvP)을 쓰지 마라" in MATCHUP
    assert "팀 간 상대 전적" in MATCHUP
    assert "스플릿 성적" in MATCHUP


def test_starter_hand_is_a_fact_not_a_split():
    """`선발손` 을 주는 이유를 프롬프트가 스스로 말한다."""
    from app.engine.matchup import _M11_BLOCK

    assert "사실이지 스플릿이 아니다" in _M11_BLOCK


# ─────────────────── C6 동결 ───────────────────

def test_freeze_was_not_restarted_again():
    """🔴 재시작은 이미 최종이다 — 재료를 바꿀 때마다 미루면 50건에 못 간다."""
    from app.engine.daily_summary import (
        FREEZE_RESTART_IS_FINAL, FREEZE_RESTART_REASON, freeze_start,
    )

    assert FREEZE_RESTART_IS_FINAL is True
    assert freeze_start("kbo") == "2026-09-04"
    assert "대원칙" in FREEZE_RESTART_REASON
