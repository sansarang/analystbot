"""[P0 2026-09-03] 시작 전 `0-0` 플레이스홀더를 `live` 로 읽어 카드가 0장이 됐다.

🔴 실사고 17:43 KST — KBO 5경기 전부 판정 없음:
     [kbo] 2026-09-03 일정 5경기 적재 (예정 0 / 종료 0)
     [pipeline] 단계 실패 — 🔴 경기 적재 0/1건 — 데이터 없음
     [scheduler] kbo 캐시 없음·구제 실패 — 생략 game=1700/1701/1702/1704
   공식 페이지가 **경기 전** 경기에 `0-0` 을 싣는데, 파서가 "점수가 있다"로
   읽어 `live` 로 굳혔다. `upsert_schedule` 의 예정 카운트가 0 이 되고
   파이프라인이 대상 0건으로 죽었다.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.collectors.kbo import _has_started, parse_rows

KST = ZoneInfo("Asia/Seoul")


def _rows(time_s: str, score: str, note: str = "", when=None):
    """공식 페이지 행 모양 — 날짜·시각·매치업·점수·구장·비고.

    ⚠️ **날짜를 인자로 받는다.** 종전에는 `09.03` 을 박아 두고 시각만
       `now+3h` 로 만들었는데, 21:42 에 돌리면 그게 **같은 날 00:42** 가 돼
       "미래"가 아니라 과거였다. 시간에 따라 결과가 바뀌는 테스트는
       테스트가 아니다 (2026-09-03 실측 — 같은 실수를 두 번 했다).
    """
    d = when or datetime.now(KST)
    return [[f"{d.month:02d}.{d.day:02d}(수)", time_s, f"LG{score}두산",
             "잠실", note]]


def test_future_game_with_placeholder_score_is_scheduled():
    """🔴 이 파일의 목적 — 시작 전 0-0 은 `scheduled` 다."""
    fut = datetime.now(KST) + timedelta(days=1)      # 내일이면 시각과 무관하다
    games, _ = parse_rows(_rows("18:30", "0vs0", when=fut), fut.year)
    assert games, "행이 파싱되지 않았다"
    assert games[0]["status"] == "scheduled", games[0]


def test_started_game_with_score_is_still_live():
    """이미 시작했으면 종전대로 `live` — 완화가 아니라 시각 기준 추가다."""
    past = datetime.now(KST) - timedelta(days=1)     # 어제면 시각과 무관하다
    games, _ = parse_rows(_rows("18:30", "3vs2", when=past), past.year)
    assert games[0]["status"] == "live", games[0]


def test_cancelled_still_wins():
    fut = datetime.now(KST) + timedelta(days=1)
    games, _ = parse_rows(_rows("18:30", "0vs0", "취소", when=fut), fut.year)
    assert games[0]["status"] == "cancelled"


def test_unknown_time_is_not_treated_as_started():
    """모를 때는 **시작 안 한 것으로** 본다 — 그래야 판정 대상에서 안 빠진다."""
    assert _has_started("", "18:30") is False
    assert _has_started("2026-09-03", "") is False
    assert _has_started("2026-09-03", "없음") is False


def test_has_started_boundary():
    now = datetime.now(KST)
    assert _has_started(now.strftime("%Y-%m-%d"),
                        (now - timedelta(minutes=1)).strftime("%H:%M")) is True
    assert _has_started(now.strftime("%Y-%m-%d"),
                        (now + timedelta(minutes=1)).strftime("%H:%M")) is False


def test_boot_repairs_impossible_live_rows():
    """🔴 파서를 고쳐도 **이미 들어간 행**은 스스로 낫지 않는다.

    아시아 폴링은 `status='scheduled'` 만 조회한다. 오염된 행은 조회에서
    빠지고, 그 행을 고칠 유일한 경로(`upsert_schedule`)도 그 행을 못 찾는다 —
    교착이다. 기동 시 불변식으로 끊는다.
    """
    from pathlib import Path

    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert "_repair_impossible_live" in src
    i = src.index("async def _repair_impossible_live")
    seg = src[i:src.index("\nasync def ", i + 10)]
    assert "status = 'live' AND starts_at > now()" in seg
    assert "SET status = 'scheduled'" in seg
    # 기동 경로에서 **포렌식보다 먼저** 돈다 — 포렌식이 고쳐진 상태를 보게
    assert src.index("await _repair_impossible_live(pool)") < \
        src.index("await _startup_forensics(pool, redis)")
