"""[감시] 프롬프트 금지문의 부작용(지어내기·채움률 급락)을 잡기 위한 계측 검증.

1차 프롬프트에 "못 찾은 이유를 설명하지 말고 null을 써라"를 넣으면 설명 산문은
사라지지만 모델이 빈칸을 지어낼 유인이 생긴다. 채움률 계측과 API 교차검증이
그 신호를 잡는 장치이며, 이 파일은 그 장치 자체를 검증한다.
"""

import random

from app.research.crosscheck import (
    _form_win_rate,
    compare_game,
    crosscheck_report,
    crosscheck_sample,
    sample_games,
)
from app.research.deep import PROMPT, fill_report, record_fill_stats


# ---------------------------------------------------------------- 프롬프트 계약

def test_first_prompt_keeps_both_safeguards_with_prohibition():
    """[1] 금지문을 넣되 'never invent numbers'와 'use null/empty'를 함께 유지한다."""
    assert "Do NOT restate the question or explain what you could not find" in PROMPT
    assert "never invent numbers" in PROMPT          # 지어내기 금지 유지
    assert "use null/empty" in PROMPT                # 빈 값 허용 유지


# ---------------------------------------------------------------- 채움률 계측

async def test_fill_report_tracks_rates_and_invalid(redis_client):
    """[감시] 필드별 채움률과 무효율이 일자별로 누적된다."""
    date = "2026-02-02"
    await redis_client.delete(f"research_fill:{date}")
    full = {
        "home_recent_form": {"form": "WWLWL", "home_split": "홈 12승 5패"},
        "away_recent_form": {},
        "absences": ["Trevor Story 결장"],
        "bullpen": "최근 3일 8.2이닝",
        "form_reversal": ["시즌 ERA 3.86 vs 최근5 5.40"],
    }
    sparse = {"home_recent_form": {"form": "LLWLW"}, "away_recent_form": {},
              "absences": [], "form_reversal": []}
    await record_fill_stats(redis_client, full, date=date)
    await record_fill_stats(redis_client, sparse, date=date)
    await record_fill_stats(redis_client, None, invalid=True, date=date)

    rep = await fill_report(redis_client, date)
    assert rep["games"] == 3 and rep["invalid"] == 1
    assert rep["invalid_rate"] == round(1 / 3, 3)
    assert rep["form_rate"] == 1.0            # 유효 2건 모두 form 있음
    assert rep["absences_rate"] == 0.5        # 1/2
    assert rep["bullpen_rate"] == 0.5
    assert rep["splits_rate"] == 0.5


async def test_fill_report_empty_day_is_safe(redis_client):
    """[감시] 기록이 없는 날도 크래시 없이 None 비율을 반환한다."""
    rep = await fill_report(redis_client, "1999-01-01")
    assert rep["games"] == 0 and rep["invalid_rate"] is None
    assert rep["form_rate"] is None


# ---------------------------------------------------------------- 교차검증

def test_form_win_rate_counts_draw_as_half():
    assert _form_win_rate("WWLWL") == 0.6
    assert _form_win_rate("WWDLW") == 0.7
    assert _form_win_rate(None) is None
    assert _form_win_rate("") is None


def test_compare_game_flags_fabricated_era():
    """[감시] 리서치가 낸 선발 ERA가 statsapi와 크게 어긋나면 불일치로 표시한다."""
    game = {"home": "Detroit Tigers", "away": "Tampa Bay Rays"}
    research = {
        "home_pitcher": {"name": "Framber Valdez", "era_season": 2.10},   # 지어낸 값
        "away_pitcher": {"name": "Drew Rasmussen", "era_season": 3.05},   # 실제와 근사
    }
    stats = {"era": {"Framber Valdez": 4.35, "Drew Rasmussen": 3.01}, "win_pct": {}}
    rows = compare_game(game, research, stats)
    by_field = {r["field"]: r for r in rows}
    assert by_field["home_pitcher.era_season"]["mismatch"] is True
    assert by_field["away_pitcher.era_season"]["mismatch"] is False


def test_compare_game_skips_unknown_players():
    """[감시] API에 없는 선수는 대조 대상에서 조용히 제외한다 (거짓 불일치 방지)."""
    rows = compare_game({"home": "H", "away": "A"},
                        {"home_pitcher": {"name": "Nobody", "era_season": 1.0}},
                        {"era": {}, "win_pct": {}})
    assert rows == []


def test_compare_game_checks_recent_form_against_win_pct():
    game = {"home": "Detroit Tigers", "away": "Tampa Bay Rays"}
    research = {"home_recent_form": {"form": "WWWWW"}}       # 5전 전승 주장
    stats = {"era": {}, "win_pct": {"Detroit Tigers": 0.469}}
    row = compare_game(game, research, stats)[0]
    assert row["field"] == "home_recent_form.form"
    assert row["mismatch"] is True                           # 괴리 0.53 > 0.40


def test_sample_games_excludes_finished_games():
    games = [{"id": 1, "status": "scheduled"}, {"id": 2, "status": "final"},
             {"id": 3, "status": "scheduled"}]
    picked = sample_games(games, n=3, rng=random.Random(0))
    assert {g["id"] for g in picked} == {1, 3}


async def test_crosscheck_sample_records_mismatch(redis_client):
    """[감시] 표본 검증 결과가 일자별 카운터에 쌓인다."""
    date = "2026-02-03"
    await redis_client.delete(f"research_crosscheck:{date}")
    games = [{"id": 1, "home": "Detroit Tigers", "away": "Tampa Bay Rays",
              "status": "scheduled"}]
    research_map = {1: {"home_pitcher": {"name": "Framber Valdez", "era_season": 2.10}}}
    stats = {"era": {"Framber Valdez": 4.35}, "win_pct": {}}
    rows = await crosscheck_sample(redis_client, games, research_map, stats, "mlb",
                                   rng=random.Random(0), date=date)
    assert len(rows) == 1 and rows[0]["mismatch"]
    rep = await crosscheck_report(redis_client, date)
    assert rep == {"checked": 1, "mismatch": 1, "rate": 1.0}


async def test_crosscheck_skips_soccer(redis_client):
    """[감시] 축구는 대조 가능한 실데이터 소스가 없어 현재 대상이 아니다."""
    rows = await crosscheck_sample(redis_client, [{"id": 1, "status": "scheduled"}],
                                   {}, {"era": {}, "win_pct": {}}, "soccer")
    assert rows == []
