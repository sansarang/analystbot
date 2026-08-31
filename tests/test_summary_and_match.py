"""[야간 관측 수정 2건] 축구 레저 매칭 · 요약 카드 조회 기준.

둘 다 2026-08-31 밤 실운영에서 드러난 결함이다:
  ① 축구 판정이 레저에 한 건도 기록되지 않았다 (팀명 완전 일치 실패)
  ② 해외판 요약이 매일 "픽 없음"만 보냈다 (판정보다 먼저 실행 + 날짜 불일치)
"""

import pytest

from app.collectors.football import match_team_name


# ---------------------------------------------------------------- ① 팀명 매칭

@pytest.mark.parametrize("fotmob,fd", [
    ("Lecce", "US Lecce"), ("Roma", "AS Roma"),
    ("Atalanta", "Atalanta BC"), ("Bologna", "Bologna FC 1909"),
    ("Osasuna", "CA Osasuna"), ("Getafe", "Getafe CF"),
    ("Aston Villa", "Aston Villa FC"), ("Arsenal", "Arsenal FC"),
    ("Benfica", "SL Benfica"), ("Estoril", "GD Estoril Praia"),
    ("Braga", "SC Braga"), ("Barcelona", "FC Barcelona"),
    ("Rayo Vallecano", "Rayo Vallecano de Madrid"),
])
def test_tonight_team_names_match(fotmob, fd):
    """실측 표기 차이 — 완전 일치로는 전건 실패했다."""
    assert match_team_name(fotmob, [fd, "무관한 팀 FC"]) == fd


def test_ambiguous_match_is_refused():
    """모호하면 붙이지 않는다 — 잘못 붙이면 남의 경기 결과로 채점된다."""
    assert match_team_name("United", ["Manchester United FC", "Leeds United FC"]) is None


async def test_ledger_finds_game_despite_name_difference(db_pool):
    from datetime import UTC, datetime, timedelta

    from app.engine.soccer_trial import _find_game_id

    ko = datetime.now(UTC) + timedelta(hours=3)
    gid = await db_pool.fetchval(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('soccer','Serie A','fd1',$1,'US Lecce','AS Roma','scheduled')"
        " RETURNING id", ko)
    found = await _find_game_id(db_pool, {"home": "Lecce", "away": "Roma",
                                          "kickoff": ko})
    assert found == gid, "팀명이 달라 레저 기록이 또 실패한다"


async def test_ledger_refuses_when_no_game_in_window(db_pool):
    from datetime import UTC, datetime, timedelta

    from app.engine.soccer_trial import _find_game_id

    ko = datetime.now(UTC) + timedelta(hours=3)
    assert await _find_game_id(db_pool, {"home": "Lecce", "away": "Roma",
                                         "kickoff": ko}) is None


# ---------------------------------------------------------------- ② 요약 조회

async def test_summary_selects_by_kickoff_not_by_date(db_pool):
    """🔴 레저 date 는 종목별 슬레이트 날짜다 — MLB는 KST 날짜와 어긋난다.

    실측 2026-08-31: 09/01 04:30에 생성된 MLB 판정의 date 가 2026-08-31 이라
    그날 요약(today_kst=09/01)에서 통째로 빠졌다.
    """
    from datetime import UTC, datetime, timedelta

    from app.engine.daily_summary import build
    from app.engine.pick_ledger import record_analysis

    ko = datetime.now(UTC) + timedelta(hours=4)
    gid = await db_pool.fetchval(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('mlb','MLB','m1',$1,'NYY','BOS','scheduled') RETURNING id", ko)
    # 레저 date 를 **일부러 다른 날짜**로 넣는다 (슬레이트 날짜 상황 재현)
    await record_analysis(db_pool, {
        "sport": "mlb", "date": "1999-01-01",
        "games": [{"game_id": gid, "sport": "mlb", "league": "MLB",
                   "p_claude": 0.66, "lineup_status": "confirmed",
                   "judge_pass": False, "judge_confidence": "high",
                   "matchup": {"p_home": 0.66, "우세": "home", "확신도": "상"}}],
        "picks": [{"game_id": gid, "market": "h2h", "recommended": True}]})
    text = await build(db_pool, ("mlb",), "제목", "무관한날짜")
    assert "픽 없음" not in text, "날짜 기준이 남아 있어 판정을 못 찾는다"
    assert "NYY" in text


async def test_summary_excludes_already_started_games(db_pool):
    """이미 시작한 경기는 뺀다 — 걸 수 없는 것을 목록에 올리지 않는다."""
    from datetime import UTC, datetime, timedelta

    from app.engine.daily_summary import build
    from app.engine.pick_ledger import record_analysis

    ko = datetime.now(UTC) - timedelta(hours=1)
    gid = await db_pool.fetchval(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('mlb','MLB','m2',$1,'NYY','BOS','live') RETURNING id", ko)
    await record_analysis(db_pool, {
        "sport": "mlb", "date": "2026-08-31",
        "games": [{"game_id": gid, "sport": "mlb", "p_claude": 0.66,
                   "lineup_status": "confirmed", "judge_pass": False,
                   "judge_confidence": "high",
                   "matchup": {"p_home": 0.66, "우세": "home", "확신도": "상"}}],
        "picks": [{"game_id": gid, "market": "h2h", "recommended": True}]})
    assert "픽 없음" in await build(db_pool, ("mlb",), "제목", "2026-08-31")


def test_overseas_summary_runs_after_judgement():
    """발송 시각이 판정보다 뒤여야 한다 — 앞서면 매일 '픽 없음'이다."""
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'CronTrigger(hour=5, minute=30' in src, "해외판이 MLB 판정(04:30) 뒤가 아니다"
    assert 'CronTrigger(hour=1, minute=45' in src, "축구 요약이 판정(22:30~) 뒤가 아니다"
