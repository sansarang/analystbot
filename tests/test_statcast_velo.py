"""[SAT-8] 선발 최근 구속 추세 — 계약 테스트.

박스스코어에 없는 **투수 건강/폼 신호**다. 최근 등판들의 속구 평균 구속을 재고,
직전 대비 하락(피로·부상 신호)이나 상승을 잡는다. 대원칙(최근 3~5경기)에 맞는
고급정보 — Baseball Savant(무키·AWS 도달)에서 온다.
"""
from __future__ import annotations

from app.collectors import statcast_velo as sv


_CSV = (
    "pitch_type,game_date,release_speed,player_name\n"
    "FF,2026-08-20,95.4,Doe\n"
    "FF,2026-08-20,95.0,Doe\n"
    "SL,2026-08-20,84.0,Doe\n"          # 슬라이더는 속구 아님 — 제외
    "FF,2026-08-26,95.6,Doe\n"
    "FF,2026-08-26,95.2,Doe\n"
    "FF,2026-09-01,92.1,Doe\n"          # 직전 등판 — 뚝 떨어졌다
    "FF,2026-09-01,92.5,Doe\n"
)


def test_parse_statcast_csv():
    rows = sv.parse_statcast_csv(_CSV)
    assert len(rows) == 7
    assert rows[0]["pitch_type"] == "FF"
    assert rows[0]["game_date"] == "2026-08-20"


def test_parse_statcast_csv_strips_bom():
    """🔴 실측 2026-09-09: Savant CSV 는 앞에 BOM(\\ufeff)이 붙어 온다.
    그러면 첫 컬럼명이 '\\ufeffpitch_type' 이 돼 조회가 전부 실패, 371KB 인데
    0행이 파싱됐다. BOM 을 벗겨야 한다."""
    rows = sv.parse_statcast_csv("﻿" + _CSV)
    assert len(rows) == 7
    assert rows[0]["pitch_type"] == "FF"        # BOM 벗긴 뒤 컬럼명이 정상
    assert sv.velocity_by_game(rows)             # 집계도 된다


def test_velocity_by_game_uses_fastball_only():
    rows = sv.parse_statcast_csv(_CSV)
    byg = sv.velocity_by_game(rows)
    assert set(byg) == {"2026-08-20", "2026-08-26", "2026-09-01"}
    assert abs(byg["2026-08-20"] - 95.2) < 0.05   # SL 제외된 평균
    assert abs(byg["2026-09-01"] - 92.3) < 0.05


def test_velocity_trend_detects_decline():
    rows = sv.parse_statcast_csv(_CSV)
    trend = sv.velocity_trend(sv.velocity_by_game(rows))
    assert trend is not None
    assert trend["delta_mph"] < -2.0          # 95.4 → 92.3, 약 -3mph
    assert trend["games"] >= 3


def test_velocity_trend_none_when_flat():
    """구속이 안정적이면 신호 없음(None) — 소음을 만들지 않는다."""
    flat = "pitch_type,game_date,release_speed,player_name\n" + \
        "".join(f"FF,2026-08-2{i},95.0,Doe\n" for i in range(3))
    trend = sv.velocity_trend(sv.velocity_by_game(sv.parse_statcast_csv(flat)))
    assert trend is None


def test_velocity_trend_none_with_one_game():
    one = "pitch_type,game_date,release_speed,player_name\nFF,2026-09-01,95.0,Doe\n"
    assert sv.velocity_trend(sv.velocity_by_game(sv.parse_statcast_csv(one))) is None


def test_describe_mentions_numbers_and_name():
    rows = sv.parse_statcast_csv(_CSV)
    trend = sv.velocity_trend(sv.velocity_by_game(rows))
    text = sv.describe("Martín Pérez", trend)
    assert "Martín Pérez" in text
    assert "mph" in text
    assert "92" in text and "95" in text
