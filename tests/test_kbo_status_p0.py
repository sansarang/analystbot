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


def _rows(time_s: str, score: str, note: str = ""):
    """공식 페이지 행 모양 — 날짜·시각·매치업·점수·구장·비고."""
    return [["09.03(수)", time_s, f"LG{score}두산", "잠실", note]]


def test_future_game_with_placeholder_score_is_scheduled():
    """🔴 이 파일의 목적 — 시작 전 0-0 은 `scheduled` 다."""
    later = (datetime.now(KST) + timedelta(hours=3)).strftime("%H:%M")
    games, _ = parse_rows(_rows(later, "0vs0"), 2026)
    assert games, "행이 파싱되지 않았다"
    assert games[0]["status"] == "scheduled", games[0]


def test_started_game_with_score_is_still_live():
    """이미 시작했으면 종전대로 `live` — 완화가 아니라 시각 기준 추가다."""
    past = (datetime.now(KST) - timedelta(hours=1)).strftime("%H:%M")
    games, _ = parse_rows(_rows(past, "3vs2"), 2026)
    assert games[0]["status"] == "live", games[0]


def test_cancelled_still_wins():
    later = (datetime.now(KST) + timedelta(hours=3)).strftime("%H:%M")
    games, _ = parse_rows(_rows(later, "0vs0", "취소"), 2026)
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
