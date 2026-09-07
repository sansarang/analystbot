"""자료12 — 팀 실력 레이팅 계약 (v1.4 2026-09-07).

대원칙 개정으로 열린 **유일한 예외**다. 이 파일이 그 예외의 경계를 지킨다:
팀당 숫자 하나 · 경기마다 갱신 · 최근 가중 · 표본 하한.
경계가 무너지면(집계표가 섞이면) 대원칙 위반이므로 여기서 운다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc


# ── 커널 공유 (사본 금지) ───────────────────────────────────────
def test_elo_kernel_is_shared_not_copied():
    """축구와 야구가 **같은 함수**를 쓴다. 식이 두 벌이면 조용히 갈린다."""
    from app.models import elo_core, soccer_elo, team_elo

    assert soccer_elo.replay is elo_core.replay
    assert team_elo.replay is elo_core.replay
    src = (__import__("pathlib").Path("app/models/team_elo.py")
           .read_text(encoding="utf-8"))
    assert "def replay(" not in src, "커널을 복제했다"


def test_kernel_is_standard_elo():
    from app.models.elo_core import BASE_RATING, expected_home

    assert BASE_RATING == 1500.0
    assert expected_home(0) == pytest.approx(0.5)
    # 400점 차 = 10배 승산 → 약 90.9%
    assert expected_home(400) == pytest.approx(10 / 11, abs=1e-3)


# ── 최근 가중 ───────────────────────────────────────────────────
def test_decay_comes_from_config_and_defaults_to_09():
    from app.config import Settings

    assert Settings(_env_file=None).elo_decay == 0.9


def test_recent_games_weigh_more_than_old_ones():
    """같은 결과라도 **최근**일수록 레이팅을 크게 움직여야 한다."""
    from app.models.team_elo import compute

    now = datetime(2026, 9, 7, tzinfo=UTC)

    def series(gap_days):
        rows = []
        for i in range(12, 0, -1):
            rows.append({"home": "A", "away": "B", "home_score": 5, "away_score": 1,
                         "starts_at": now - timedelta(days=i * gap_days)})
            rows.append({"home": "C", "away": "D", "home_score": 3, "away_score": 2,
                         "starts_at": now - timedelta(days=i * gap_days)})
        return rows

    near = compute(series(1), decay=0.9)["A"]["레이팅"]
    far = compute(series(10), decay=0.9)["A"]["레이팅"]
    assert near > far, "오래된 경기가 최근 경기와 같은 무게를 갖는다"


def test_decay_1_means_no_forgetting():
    from app.models.team_elo import _decay_weight

    assert _decay_weight(1.0, datetime(2026, 9, 7, tzinfo=UTC),
                         datetime(2026, 1, 1, tzinfo=UTC)) == 1.0
    assert _decay_weight(0.9, datetime(2026, 9, 7, tzinfo=UTC),
                         datetime(2026, 9, 6, tzinfo=UTC)) == pytest.approx(0.9)


# ── 표본 하한 ───────────────────────────────────────────────────
def test_thin_sample_teams_are_dropped():
    """10경기 미만은 1500 근처 잡음이다 — 실력으로 읽게 하지 않는다."""
    from app.models.team_elo import MIN_GAMES, compute

    assert MIN_GAMES == 10
    now = datetime(2026, 9, 7, tzinfo=UTC)
    rows = [{"home": "A", "away": "B", "home_score": 4, "away_score": 1,
             "starts_at": now - timedelta(days=i)} for i in range(12)]
    rows += [{"home": "C", "away": "D", "home_score": 2, "away_score": 1,
              "starts_at": now - timedelta(days=1)}]
    out = compute(rows, decay=0.9)
    assert set(out) == {"A", "B"}, "표본 1경기 팀이 섞였다"
    assert out["A"]["경기수"] == 12


def test_empty_input_is_empty_output():
    from app.models.team_elo import compute

    assert compute([]) == {}
    assert compute([{"home": "A", "away": "B",
                     "home_score": None, "away_score": None}]) == {}


# ── 실측 방향 ───────────────────────────────────────────────────
def test_stronger_team_rates_higher():
    from app.models.team_elo import compute

    now = datetime(2026, 9, 7, tzinfo=UTC)
    rows = []
    for i in range(20, 0, -1):
        rows.append({"home": "강", "away": "약", "home_score": 7, "away_score": 2,
                     "starts_at": now - timedelta(days=i)})
    out = compute(rows, decay=0.9)
    assert out["강"]["레이팅"] > out["약"]["레이팅"]
    assert out["강"]["리그평균대비"] > 0 > out["약"]["리그평균대비"]


def test_draws_are_handled():
    """KBO·NPB 는 무승부가 있다 — 커널이 D 를 받아야 한다."""
    from app.models.team_elo import _rows_to_matches

    m = _rows_to_matches([{"home": "A", "away": "B",
                           "home_score": 3, "away_score": 3}])
    assert m[0]["res"] == "D"
