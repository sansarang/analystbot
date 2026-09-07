"""NPB 일정 상태 — 시각이 없으면 '예정'이 아니다 (2026-09-07 실사고).

🔴 야후는 경기가 시작되면 시각 칸을 **스코어·이닝으로 바꾼다.**
   즉 시각 미상은 "18:00 예정"이 아니라 "이미 시작했다"는 뜻이다.
   종전에는 18:00 을 지어내 `scheduled` 로 넣었고, 그래서:

   · 2026-09-06(토) 13:00 에 끝난 롯데@오릭스·세이부@소프트뱅크가
     "오늘 18:00 예정"으로 슬레이트에 들어와 **판정·타순까지 만들어졌다.**
   · 같은 날 **우천취소**된 주니치@야쿠르트에 픽 카드가 발송됐다.

   주말·공휴일 편성(13:00·14:00)마다 재발하던 결함이다.

앵커 원문 실조회 2026-09-06:
  '神宮 ヤクルト 中日 - 試合中止'                     → cancelled
  '甲子園 阪神 DeNA 1 - 4 試合終了 …'                → 종료
  '楽天モバイル 楽天 日本ハム 3 - 6 試合終了 …'       → 종료
  '神宮 ヤクルト 巨人 18:00'                         → 예정
"""
from __future__ import annotations

import pytest

from app.collectors.yahoo_npb import parse_schedule

A = ('<a href="/npb/game/{gid}/top">{txt}</a>')


def _html(*rows):
    return "".join(A.format(gid=g, txt=t) for g, t in rows)


def _one(txt, gid="2021039999"):
    got = parse_schedule(_html((gid, txt)))
    assert got, f"파싱이 아예 안 됐다: {txt!r}"
    return got[0]


# ── 상태 판별 ───────────────────────────────────────────────────
def test_time_present_means_scheduled():
    g = _one("神宮 ヤクルト 巨人 18:00")
    assert g["start_hhmm"] == "18:00"
    assert g["state"] == "scheduled"


def test_score_instead_of_time_means_started():
    """실조회 2026-08-30: 'エスコンF ライブ配信中 日本ハム ロッテ 0 - 2 1回表'"""
    g = _one("エスコンF ライブ配信中 日本ハム ロッテ 0 - 2 1回表")
    assert g["start_hhmm"] is None
    assert g["state"] == "started", "시작한 경기를 예정으로 읽었다"


def test_finished_row_is_not_scheduled():
    g = _one("楽天モバイル 楽天 日本ハム 3 - 6 試合終了 (敗)瀧中 (勝)有原")
    assert g["state"] == "started"


def test_cancelled_row_is_detected():
    """🔴 우천취소된 경기에 픽 카드가 나갔다(2026-09-06 주니치@야쿠르트)."""
    g = _one("神宮 ヤクルト 中日 - 試合中止")
    assert g["start_hhmm"] is None
    assert g["state"] == "cancelled"


@pytest.mark.parametrize("txt,expect", [
    ("神宮 ヤクルト 巨人 14:00", "scheduled"),
    ("神宮 ヤクルト 巨人 13:00", "scheduled"),
    ("神宮 ヤクルト 中日 - 試合中止", "cancelled"),
    ("甲子園 阪神 DeNA 1 - 4 試合終了", "started"),
])
def test_state_matrix(txt, expect):
    assert _one(txt)["state"] == expect


# ── 상태 → DB status 로 옮기는 규칙 ─────────────────────────────
def test_upsert_never_marks_unknown_time_as_scheduled():
    """소스 코드 계약 — 시각 미상이 `scheduled` 로 새는 길이 없어야 한다."""
    import pathlib

    src = pathlib.Path("app/collectors/yahoo_npb.py").read_text(encoding="utf-8")
    body = src[src.index("async def upsert_schedule"):]
    assert 'status = "live"' in body
    assert 'status = "cancelled"' in body
    # 예정은 state 가 scheduled 일 때만 — else 가지가 그것이다
    seg = body[body.index("if done:"):body.index("starts = datetime")]
    assert seg.count('"scheduled"') == 1, seg


def test_timestamp_fallback_is_kept_for_matching():
    """🔴 타임스탬프 폴백은 **남긴다.** MATCH_WINDOW_HOURS=20 이라 같은 날
    어느 시각이든 기존 행을 찾는다 — 시각을 못 읽는다고 결과를 잃지 않는다.
    """
    import pathlib

    from app.collectors.game_match import MATCH_WINDOW_HOURS

    assert MATCH_WINDOW_HOURS >= 12, "폴백이 기존 행을 못 찾게 된다"
    src = pathlib.Path("app/collectors/yahoo_npb.py").read_text(encoding="utf-8")
    assert 'hhmm = "18:00"' in src


def test_parse_schedule_still_returns_the_old_fields():
    """기존 호출부(선발 확정 판별 등)를 깨지 않는다."""
    g = _one("神宮 ヤクルト 巨人 18:00 (先)")
    for k in ("game_id", "home", "away", "home_kr", "away_kr",
              "starters_confirmed", "start_hhmm", "state"):
        assert k in g
    assert g["starters_confirmed"] is True
