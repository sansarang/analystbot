"""[무과금 전환 1] 무료 배당 3원 체계.

The Odds API 가 크레딧 소진으로 2026-08-27T22:46 부터 차단됐고, `api_guard`
차단은 TTL 이 없어 시간으로 안 풀린다. 146.8시간 동안 배당이 한 행도 안 쌓였다.
유료 키 하나에 가치 게이트 전체가 매달려 있던 구조를 무료 소스로 바꾼다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.collectors.espn_odds import is_live_book, parse_odds, started

#: 실측 응답 (SD @ CIN, 2026-09-02)
REAL = {
    "provider": {"id": "100", "name": "DraftKings", "priority": 1},
    "details": "SD -149", "overUnder": 9.5,
    "awayTeamOdds": {"favorite": True, "moneyLine": -149,
                     "open": {"moneyLine": {"decimal": 1.71}},
                     "current": {"moneyLine": {"decimal": 1.67,
                                               "american": "-149"}}},
    "homeTeamOdds": {"favorite": False, "moneyLine": 123,
                     "current": {"moneyLine": {"decimal": 2.23,
                                               "american": "+123"}}},
}


def test_parses_both_sides_from_real_response():
    rows = parse_odds(REAL, "Cincinnati Reds", "San Diego Padres")
    by = {r["side"]: r for r in rows}
    assert by["San Diego Padres"]["odds"] == 1.67
    assert by["Cincinnati Reds"]["odds"] == 2.23
    assert all(r["market"] == "h2h" and r["line"] is None for r in rows)


def test_uses_current_not_open():
    """`open` 은 개장가다 — 지금 시장이 아니다. 실측 응답에 둘 다 들어 있다."""
    rows = parse_odds(REAL, "H", "A")
    assert {r["odds"] for r in rows} == {1.67, 2.23}
    assert 1.71 not in {r["odds"] for r in rows}, "개장가를 쓰면 안 된다"


def test_live_book_is_rejected():
    """🔴 실측 2026-09-02: ESPN 이 `DraftKings - Live Odds` 를 같은 목록에 섞는다.

    STL 이 7:0 으로 앞선 경기의 라이브 배당이 `STL 1.02 / LAD 11.4` 로 들어왔다.
    경기 전 판정과 견주면 괴리가 통째로 거짓이 된다.
    """
    assert is_live_book("DraftKings - Live Odds")
    assert is_live_book("betmgm in-play")
    assert not is_live_book("DraftKings")
    live = {**REAL, "provider": {"name": "DraftKings - Live Odds"}}
    assert parse_odds(live, "H", "A") == []


def test_started_games_are_skipped():
    """이미 시작한 경기는 pregame 라인 자체가 낡았다."""
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    assert started("2026-09-02T11:40Z", now) is True
    assert started("2026-09-02T16:40Z", now) is False
    # 시각을 못 읽으면 수집을 막지 않는다 — 없는 이유로 버리지 않는다
    assert started(None) is False and started("쓰레기") is False


def test_missing_price_is_not_invented():
    """가격이 없으면 만들지 않는다. O/U 라인만 있으면 적재하지 않는다."""
    only_line = {"provider": {"name": "dk"}, "overUnder": 9.5,
                 "homeTeamOdds": {}, "awayTeamOdds": {}}
    assert parse_odds(only_line, "H", "A") == []


def test_decimal_below_one_is_rejected():
    """소수배당은 1보다 커야 한다 — 미국식 값이 섞이면 조용히 틀린다."""
    bad = {"provider": {"name": "dk"},
           "homeTeamOdds": {"current": {"moneyLine": {"decimal": -149}}},
           "awayTeamOdds": {"current": {"moneyLine": {"decimal": 0.5}}}}
    assert parse_odds(bad, "H", "A") == []


# ─────────────────── SharpAPI 폴백 ───────────────────

def test_sharp_is_silent_without_a_key():
    """키 발급은 사람이 하는 일이다. 없으면 조용히 비활성 — 수집이 죽지 않는다."""
    import asyncio

    from app.collectors.sharp_odds import enabled, fetch_slate

    assert enabled() is False
    assert asyncio.run(fetch_slate("2026-09-02")) == {}


def test_sharp_parse_rejects_unknown_shape():
    """실응답으로 검증하지 못했다 — 형태가 어긋나면 지어내지 말고 0건."""
    from app.collectors.sharp_odds import parse

    assert parse({"unexpected": 1}) == {}
    assert parse("문자열") == {}


# ─────────────────── 배트맨 ───────────────────

def test_betman_rows_never_invent_the_other_side():
    """한쪽 배당만 있으면 그 한쪽만. 공제율을 모르니 역산하지 않는다."""
    from app.collectors.betman import to_rows

    rows = to_rows({"home": "LG Twins", "away": "Doosan Bears",
                    "home_odds": 1.85, "away_odds": None})
    assert len(rows) == 1 and rows[0]["side"] == "LG Twins"


def test_betman_snapshot_absent_is_none_not_empty():
    """없는 것과 빈 것을 구분한다 — 빈 dict 를 만들면 '수집됨'으로 읽힌다."""
    import asyncio

    from app.collectors.betman import load_snapshot

    assert asyncio.run(load_snapshot(None, "kbo", "2026-09-02")) is None


# ─────────────────── 격리 경계 ───────────────────

def test_odds_never_reach_the_judgement_path():
    """🔴 배당은 판정·폼·서술 입력에 절대 흐르지 않는다 (CLAUDE.md 금지선)."""
    from pathlib import Path

    for mod in ("app/engine/matchup.py", "app/engine/team_form.py",
                "app/engine/prompts.py"):
        src = Path(mod).read_text(encoding="utf-8")
        for banned in ("espn_odds", "odds_free", "sharp_odds", "betman"):
            assert banned not in src, f"{mod} 가 {banned} 를 import 하면 안 된다"


def test_paid_path_is_preserved_not_deleted():
    """유료 복귀 옵션을 남긴다 — 코드를 지우지 않고 env 로 끈다."""
    from pathlib import Path

    from app.config import Settings

    assert Path("app/collectors/odds.py").exists(), "유료 수집기를 지우지 않았다"
    assert Settings(_env_file=None).odds_provider == "free"
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'odds_provider' in src and '"theodds"' in src


def test_provider_column_separates_sources():
    """세 소스를 provider 로 구분 적재한다 — 가치 게이트는 소스를 안 본다."""
    from pathlib import Path

    schema = Path("db/schema.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS provider" in schema
    src = Path("app/collectors/odds_free.py").read_text(encoding="utf-8")
    assert "provider)" in src and "$7" in src
