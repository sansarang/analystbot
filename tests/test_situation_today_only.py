"""상황은 **오늘 경기 전** 것만 — 2026-09-06 사용자 지시.

  "은퇴경기는 지난 경기다. 오늘 경기 전 오늘 날짜 서치를 해야 한다."

실사고 2026-09-06 KBO game=1718 (두산@SSG):
  '21년 원클럽맨 SSG 김성현, 은퇴식 특별 엔트리 등록…2루수 선발 출전'
  (뉴시스, 09-05 16:11 발행 = **어제 경기** 기사)이 `확인=공식` 상황 태그로
  오늘 카드에 실렸다. 종전 필터는 `발행 < 경기시작` 상한만 봐서 사흘 전
  기사도 통과했다.

실데이터 전후 측정(운영 219건): 상황 태그 11건 → 7건.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
START = datetime(2026, 9, 6, 17, 0, tzinfo=KST)      # 오늘 경기 17:00 KST


def _item(dt: datetime, title="테스트"):
    return {"title": title, "published": format_datetime(dt)}


# ── 발행 창 ────────────────────────────────────────────────────
@pytest.mark.parametrize("delta,keep,why", [
    (timedelta(hours=-2), True, "경기 2시간 전 — 오늘의 재료"),
    (timedelta(hours=-17), True, "어제 자정 직후 — 창 안"),
    (timedelta(hours=-23, minutes=-59), True, "창 경계 직전"),
    (timedelta(hours=-24, minutes=-49), False, "어제 16:11 — 김성현 은퇴식 기사"),
    (timedelta(hours=-48), False, "그저께"),
    (timedelta(hours=+1), False, "경기 시작 뒤 — 종전에도 걸렀다"),
])
def test_publish_window(delta, keep, why):
    from app.engine.situation import published_before

    assert published_before(_item(START + delta), START) is keep, why


def test_window_is_a_named_constant_not_a_magic_number():
    from app.engine.situation import SITUATION_WINDOW_HOURS

    assert SITUATION_WINDOW_HOURS == 24


# ── [2026-09-07 실측] MLB 만 창이 넓다 ──────────────────────────
def test_mlb_window_is_wider_because_its_day_straddles_kst():
    """🔴 24h 는 KBO·NPB 기준이었다 — MLB 는 현지 하루가 KST 로 걸쳐 있다.

    실측 2026-09-06 슬레이트(MLB 기사 332건) 창별 통과 태그:
      12h=5 · 24h=32 · **36h=34** · 48h=34 · 72h=34
    36h 위로는 늘지 않는다 — 잘려나가던 것은 T-24~36h 의 2건뿐이었다.
    """
    from app.engine.situation import window_hours

    assert window_hours("mlb") == 36
    assert window_hours("kbo") == window_hours("npb") == 24
    assert window_hours(None) == 24, "모르는 종목은 좁은 쪽이 안전하다"


def test_mlb_morning_game_keeps_the_day_before_report():
    """KST 오전 경기 — 미국 현지 '경기 당일 아침' 기사가 살아야 한다."""
    from app.engine.situation import published_before

    start = datetime(2026, 9, 7, 11, 10, tzinfo=KST)      # 실제 #3725
    it = _item(datetime(2026, 9, 6, 10, 4, tzinfo=KST),   # T-25.1h
               "Ohtani out for 3rd straight day as Dodgers weigh potential IL stint")
    assert published_before(it, start, "mlb") is True
    assert published_before(it, start, "kbo") is False, "KBO 창까지 넓히면 안 된다"


def test_kbo_window_still_drops_the_retirement_article():
    """🔴 넓히기가 김성현 은퇴식(T-24.8h)을 되살리면 안 된다."""
    from app.engine.situation import published_before

    start = datetime(2026, 9, 6, 17, 0, tzinfo=KST)
    it = _item(datetime(2026, 9, 5, 16, 11, tzinfo=KST),
               "'21년 원클럽맨' SSG 김성현, 은퇴식 특별 엔트리 등록…2루수 선발 출전")
    assert published_before(it, start, "kbo") is False
    assert published_before(it, start) is False, "종목 미지정도 좁은 쪽"


def test_unknown_publish_time_is_kept():
    """모르는 것을 버리지 않는다 — pubDate 를 안 주는 매체가 통째로 사라진다."""
    from app.engine.situation import published_before

    assert published_before({"title": "x"}, START) is True
    assert published_before({"title": "x", "published": "쓰레기"}, START) is True
    assert published_before(_item(START - timedelta(hours=2)), None) is True


def test_the_actual_incident_article_is_dropped():
    """실사고 그 기사 — 뉴시스 09-05 16:11, 오늘 경기 17:00."""
    from app.engine.situation import published_before

    it = _item(datetime(2026, 9, 5, 16, 11, tzinfo=KST),
               "'21년 원클럽맨' SSG 김성현, 은퇴식 특별 엔트리 등록…2루수 선발 출전")
    assert published_before(it, START) is False


# ── 수집 쿼리 ──────────────────────────────────────────────────
def test_situation_query_is_scoped_to_recent():
    from app.collectors.news_rss import SITUATION_RECENCY, situation_query

    q = situation_query("kbo", "SSG Landers")
    assert SITUATION_RECENCY in q, "상황 쿼리가 시간 창 없이 나간다"
    assert SITUATION_RECENCY == "when:1d"


def test_general_team_query_is_not_scoped():
    """일반 뉴스는 종전 창을 유지한다 — 이번 지시는 **상황** 검색 얘기다."""
    from app.collectors.news_rss import SITUATION_RECENCY, qualified

    assert SITUATION_RECENCY not in qualified("kbo", "SSG Landers")


# ── 평의회: 표식과 결과를 함께 둔다 ────────────────────────────
def test_council_record_survives_a_cache_rebuild():
    """🔴 실사고 2026-09-06 15:34 — 캐시 재생성으로 심의록이 통째로 사라졌고,
    `council:done` 플래그만 남아 그 뒤 전부 '이미 심의함'으로 막혔다.
    아침에 고친 최종 판정 락과 같은 결함이다.
    """
    src = (ROOT / "app/engine/council.py").read_text(encoding="utf-8")
    assert "REC_KEY" in src and "_save_record" in src
    assert "load_record" in src
    # 저장된 심의록이 있으면 캡·1회표식보다 **먼저** 복원해야 한다.
    body = src[src.index("async def run("):]
    assert body.index("load_record") < body.index("_cap_ok")
    assert body.index("load_record") < body.index("_once_ok")


def test_council_returns_the_permit_when_investigation_fails():
    src = (ROOT / "app/engine/council.py").read_text(encoding="utf-8")
    body = src[src.index("async def run("):]
    seg = body[body.index("if findings is None"):]
    assert "_release_once" in seg[:400], "조사 실패인데 1회 표식을 붙잡고 있다"
