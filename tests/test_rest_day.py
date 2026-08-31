"""[휴식일] "경기가 없는 날"과 "경기가 있는데 못 모은 날"을 가른다.

🔴 실사고 2026-08-31 14:01: KBO·NPB 경기가 없는 월요일에 프리페치가
   7건을 🔴로 내보내고 "전량 실패 — 리포트 신뢰도가 낮습니다"로 끝냈다.
   장애와 휴식일이 화면에서 같아 보이면, 휴식일마다 나가는 오경보에
   **진짜 장애가 묻힌다.** 이 구분이 이 수정의 전부다.
"""

import pytest

from app.alerts import StageResult, overall_verdict


def _st(name, **kw):
    return StageResult(name=name, **kw)


# ---------------------------------------------------------------- 상태 구분

def test_no_games_is_not_a_failure():
    st = _st("[KBO] 경기 적재", ok=0, total=1, unit="건", no_games=True)
    assert st.severity == "경기없음"
    assert not st.failed
    assert st.icon == "⚪"


def test_no_games_line_says_rest_day_not_missing_data():
    st = _st("[KBO] 네이버 수집", ok=0, total=1, no_games=True)
    line = st.line()
    assert "경기 없음(휴식일)" in line
    assert "데이터 없음" not in line
    assert "🔴" not in line


def test_real_collection_failure_still_reads_as_failure():
    """반대 방향 — 경기가 있는데 0건이면 여전히 실패다.

    이 테스트가 없으면 no_games를 상시로 켜도 아무도 모른다.
    """
    st = _st("[KBO] 네이버 수집", ok=0, total=5, cause="missing")
    assert st.severity == "실패" and st.failed
    assert "🔴" in st.line()


def test_no_games_flag_beats_cause():
    """휴식일 판정은 cause보다 먼저다 — 0경기에 missing이 붙어도 실패가 아니다."""
    st = _st("[NPB] 경기 적재", ok=0, total=1, cause="missing", no_games=True)
    assert st.severity == "경기없음"


# ---------------------------------------------------------------- 요약 문구

def test_verdict_reports_rest_day_instead_of_low_confidence():
    stages = [_st("[KBO] 경기 적재", ok=0, total=1, no_games=True),
              _st("[KBO] 날씨", ok=0, total=1, no_games=True),
              _st("[NPB] 경기 적재", ok=0, total=1, no_games=True),
              _st("[KBO] 투수 소모", ok=10, total=10, unit="팀")]
    v = overall_verdict(stages)
    assert "경기 없음 확인" in v
    assert "KBO" in v and "NPB" in v
    assert "신뢰도가 낮" not in v


def test_verdict_still_warns_when_a_real_failure_is_mixed_in():
    """휴식일 옆에 진짜 실패가 있으면 휴식일이라고 덮지 않는다."""
    stages = [_st("[KBO] 경기 적재", ok=0, total=1, no_games=True),
              _st("[NPB] Yahoo 수집", ok=0, total=6, cause="parse")]
    v = overall_verdict(stages)
    assert "경기 없음 확인" not in v
    assert "실패" in v


# ---------------------------------------------------------------- 판별 근거

async def test_rest_day_needs_a_loaded_schedule_around_today(db_pool):
    """오늘 0경기라도 **주변에 경기가 있어야** 휴식일이라고 말한다.

    창 전체가 비어 있으면 일정 자체가 안 들어온 것이다 — 모르는 것을
    정상의 근거로 쓰지 않는다.
    """
    from app.pipeline import is_rest_day

    # 일정이 아예 없는 상태
    assert await is_rest_day(db_pool, "kbo", "2026-08-31") is False

    # 주변 날짜에 경기가 실려 있으면 오늘 0경기는 휴식일
    await db_pool.execute(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('kbo','KBO','r1','2026-09-01 09:00+00','A','B','scheduled')")
    assert await is_rest_day(db_pool, "kbo", "2026-08-31") is True

    # 오늘 경기가 생기면 더 이상 휴식일이 아니다
    await db_pool.execute(
        "INSERT INTO games (sport,league,ext_id,starts_at,home,away,status)"
        " VALUES ('kbo','KBO','r2','2026-08-31 09:00+00','A','B','scheduled')")
    assert await is_rest_day(db_pool, "kbo", "2026-08-31") is False


async def test_next_slate_hint_says_undecided_when_unknown(db_pool):
    from app.pipeline import next_slate_hint

    assert await next_slate_hint(db_pool, ["kbo"]) == "미정"
