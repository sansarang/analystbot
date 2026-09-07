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
                # ⚠️ 실제 모양은 **문자열**이다 (weather.py:215 —
                #    `research["weather"] = info["text"]`).
                "weather": "기온 24도, 풍속 2.0m/s",
                "home_pitcher": {"throws": "L"}}}


def test_build_collects_all_three_axes():
    out = build(_jg())
    assert out["home"]["연전"] == 2 and out["home"]["이동"] == "원정→홈"
    assert out["away"]["이동"] == "홈→원정"
    # [C2 2026-09-05] 날씨는 라벨+수치 블록이 됐다. 라벨은 새 임계가 아니라
    #   `scoring._weather_factor` 의 계수에서 나온다.
    assert out["날씨"]["수치"] == "기온 24도, 풍속 2.0m/s"
    assert out["날씨"]["라벨"] in ("타자 유리", "투수 유리", "중립")
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
    # [C4 2026-09-05] 자료11 은 대장의 [맥락] 축이 됐다.
    assert "[맥락]" not in plain, "안 붙였는데 블록이 있다"

    attach(jg)
    out = render_matchup_prompt(jg, boxes={}, news={}, prev=None)
    assert "[맥락]" in out and "10. 변수 대장" in out
    assert "원정→홈" in out and "기온 24도" in out
    assert "타자 유리" in out or "투수 유리" in out or "중립" in out
    assert "{{" not in out


def test_material11_says_it_is_a_reference_not_a_verdict():
    from app.engine.matchup import _LEDGER_CTX, _LEDGER_TAIL

    assert "변수의 크기를 뒷받침하는 참조" in _LEDGER_TAIL
    assert "우세를 정하지 마라" in _LEDGER_TAIL
    assert "거리가 아니다" in _LEDGER_CTX


# ─────────────────── C5 BvP 금지 ───────────────────

def test_bvp_and_head_to_head_are_banned_in_the_prompt():
    from app.engine.prompts import MATCHUP

    assert "타자 대 투수 상대 전적(BvP)을 쓰지 마라" in MATCHUP
    assert "팀 간 상대 전적" in MATCHUP
    assert "스플릿 성적" in MATCHUP


def test_starter_hand_is_a_fact_not_a_split():
    """`선발손` 을 주는 이유를 프롬프트가 스스로 말한다."""
    from app.engine.matchup import _LEDGER_CTX, _LEDGER_TAIL

    assert "사실이지 스플릿이 아니다" in _LEDGER_CTX


# ─────────────────── C6 동결 ───────────────────

def test_freeze_was_not_restarted_again():
    """🔴 재시작은 최종이다 — 재료를 바꿀 때마다 미루면 50건에 못 간다.

    ⚠️ [v1.4 2026-09-07] **이 잠금을 한 번 넘었다.** 사용자 지시로 재시작했다 —
       자료12(실력 레이팅)가 판정 입력에 들어갔고 추천 게이트에 시장 동의
       조건이 붙었다. 09-06 까지와 같은 시스템이 아니다.
       근거: 2026-09-06 620행 분석(확신 역전 4중 확인 · 실력 축 부재).
       이 테스트는 이제 **날짜를 베끼지 않고** 원본을 읽는다 — 다음에 또
       날짜가 바뀌면 사유가 함께 바뀌었는지를 본다.
    """
    from app.engine.daily_summary import (
        FREEZE_RESTART_IS_FINAL, FREEZE_RESTART_REASON, FREEZE_START_DEFAULT,
        freeze_start,
    )

    assert FREEZE_RESTART_IS_FINAL is True
    assert freeze_start("kbo") == FREEZE_START_DEFAULT
    assert FREEZE_RESTART_REASON.strip(), "재시작 사유가 비어 있다"


# ─────────────────── C2 확장 (2026-09-05) ───────────────────

def test_away_streak_counts_until_the_first_home_game():
    """연속 원정 차수. 🔴 못 읽으면 None — 0 과 다르다."""
    from app.engine.context_recent import away_streak

    assert away_streak([False, False, True]) == 2     # 최신순
    assert away_streak([True, False]) == 0
    assert away_streak([]) is None
    assert away_streak([None]) is None


def test_venue_change_says_none_when_it_cannot_know():
    """🔴 `games` 에 구장이 없다. 아는 것만 말하고 모르면 None 이다."""
    from app.engine.context_recent import venue_changed

    # 어제 원정 → 오늘 홈: 구장이 바뀌었다(우리 구장으로 왔다)
    assert venue_changed([{"home": False, "opponent": "NC"}], True) is True
    # 어제 홈 → 오늘 홈: 안 바뀌었다
    assert venue_changed([{"home": True}], True) is False
    # 어제 원정 → 오늘 원정: **상대가 같은지 알 수 없다** → None
    assert venue_changed([{"home": False, "opponent": "NC"}], False) is None
    assert venue_changed([], True) is None


def test_weather_label_comes_from_the_scoring_factor_not_new_thresholds():
    """🔴 사본 금지 — 임계를 새로 만들지 않고 `_weather_factor` 를 읽는다."""
    import inspect

    from app.engine.context_recent import BATTER, PITCHER, weather_label
    from app.engine import context_recent as cr

    src = inspect.getsource(cr.weather_label)
    assert "_weather_factor" in src
    assert "20" not in src and "도" not in src, "임계를 손으로 적었다"

    hot = weather_label({"weather": "기온 30도"})
    cold = weather_label({"weather": "기온 10도"})
    assert hot and hot[0] == BATTER and hot[1] > 1.0
    assert cold and cold[0] == PITCHER and cold[1] < 1.0
    # 계수를 못 내면 라벨을 붙이지 않는다
    assert weather_label({"weather": "흐림"}) is None
    assert weather_label({}) is None


def test_extra_innings_is_absent_with_the_reason_recorded():
    """🔴 이닝 수가 데이터에 없다 — 추정해 넣지 않았다는 사실을 코드가 말한다."""
    import inspect

    from app.engine import context_recent as cr

    src = inspect.getsource(cr._side_block)
    assert "연장" in src and "이닝 수가 없다" in src
    out = cr.build({"sport": "kbo", "starts_at": "2026-09-05T09:30:00+00:00",
                    "research": {"home_usage": {"games": [{"date": "2026-09-04",
                                                           "home": True}]}}})
    assert "연장" not in str(out)
