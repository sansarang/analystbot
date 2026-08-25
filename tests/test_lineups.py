"""[2] 라인업 확정 기반 2단계 픽 — 예상을 확정으로 취급하지 않는다.

실사고(2026-08-25 파드리스전): stats의 선발(레이/애쉬크래프트)과 research의 선발
(킹/스키넌스)이 달랐는데 그대로 최종 픽처럼 나갔다. 소스가 갈리면 예비 픽만 허용한다.
"""

import json

import pytest

from app.collectors.lineups import (
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_PREDICTED,
    MLBLineupClient,
    parse_boxscore,
    pick_state,
    refresh_mlb_lineup,
    resolve_starter,
)


def _boxscore(order_n: int = 9, home_starter="Jose Ureña", away_starter="Gavin Williams"):
    def team(starter, n):
        players = {f"ID{i}": {"person": {"fullName": f"Batter {i}"}} for i in range(1, n + 1)}
        players["ID900"] = {"person": {"fullName": starter}}
        return {"players": players,
                "battingOrder": [str(i) for i in range(1, n + 1)],
                "pitchers": ["900"],
                "info": [{"title": "NOT AVAILABLE", "fieldList": [{"value": "Mike Trout"}]}]}
    return {"teams": {"home": team(home_starter, order_n), "away": team(away_starter, order_n)}}


# ---------------------------------------------------------------- 파싱

def test_confirmed_requires_full_batting_order():
    """[2-2] 타순 9명이 채워져야 확정 — 그 전엔 예상 단계다."""
    assert parse_boxscore(_boxscore(9))["confirmed"] is True
    assert parse_boxscore(_boxscore(4))["confirmed"] is False
    assert parse_boxscore({})["confirmed"] is False


def test_parse_extracts_starter_order_and_scratches():
    p = parse_boxscore(_boxscore(9))
    assert p["home"]["starter"] == "Jose Ureña"
    assert len(p["home"]["batting_order"]) == 9
    assert "Mike Trout" in p["home"]["scratches"]


# ---------------------------------------------------------------- 소스 불일치

def test_statsapi_wins_and_conflict_is_flagged():
    """[2-4] StatsAPI 우선, 다르면 불일치로 표시한다."""
    chosen, clash = resolve_starter("Jose Ureña", "Michael King")
    assert chosen == "Jose Ureña" and clash is True
    chosen, clash = resolve_starter("Jose Ureña", "Jose Ureña")
    assert chosen == "Jose Ureña" and clash is False
    # 한쪽만 있으면 불일치가 아니다
    assert resolve_starter(None, "Michael King") == ("Michael King", False)
    assert resolve_starter("Jose Ureña", None) == ("Jose Ureña", False)


def test_conflict_has_no_final_pick_rights():
    """[2-4] 불일치 상태는 예비 픽만 허용 — 최종 픽 자격이 없다."""
    assert pick_state(STATUS_CONFLICT)[0] == "preliminary"
    assert "불일치" in pick_state(STATUS_CONFLICT)[1]
    assert pick_state(STATUS_CONFIRMED)[0] == "final"
    assert pick_state(STATUS_PREDICTED)[0] == "preliminary"
    assert pick_state(None)[0] == "preliminary"


def test_pick_state_labels():
    """[2-1] 라벨 문구 계약."""
    assert pick_state(STATUS_CONFIRMED)[1].startswith("✅ 최종")
    assert pick_state(STATUS_PREDICTED)[1].startswith("🕐 잠정")


# ---------------------------------------------------------------- DB 왕복

class _FakeClient(MLBLineupClient):
    def __init__(self, box):
        super().__init__(mock=False)
        self._box = box

    async def fetch_boxscore(self, game_pk):
        return self._box


async def _game(db_pool, **over):
    row = await db_pool.fetchrow(
        """
        INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                           home_pitcher, away_pitcher)
        VALUES ('mlb', 'MLB', $1, now() + interval '2 hours',
                'Los Angeles Angels', 'Cleveland Guardians', $2, $3)
        ON CONFLICT (sport, ext_id) DO UPDATE SET home_pitcher = EXCLUDED.home_pitcher
        RETURNING id, ext_id, sport, home, away, home_pitcher, away_pitcher, lineup_status
        """,
        over.get("ext_id", "test-lineup-1"),
        over.get("home_pitcher", "Jose Ureña"), over.get("away_pitcher", "Gavin Williams"),
    )
    return dict(row)


async def test_refresh_marks_confirmed_and_persists(db_pool):
    """[2-2] 확정 수신 시 games.lineup_status와 lineups 행이 남는다."""
    g = await _game(db_pool, ext_id="test-lineup-confirm")
    res = await refresh_mlb_lineup(db_pool, g, _FakeClient(_boxscore(9)))
    assert res["status"] == STATUS_CONFIRMED and res["changed"]

    status = await db_pool.fetchval("SELECT lineup_status FROM games WHERE id = $1", g["id"])
    assert status == STATUS_CONFIRMED
    rows = await db_pool.fetch(
        "SELECT side, status, starter, batting_order FROM lineups WHERE game_id = $1", g["id"])
    assert len(rows) == 2
    assert all(len(json.loads(r["batting_order"])) == 9 for r in rows)


async def test_refresh_flags_conflict_when_starter_differs(db_pool):
    """[2-4] 예고 선발과 statsapi 선발이 다르면 conflict로 남고 사유가 기록된다."""
    g = await _game(db_pool, ext_id="test-lineup-conflict", home_pitcher="Michael King")
    res = await refresh_mlb_lineup(db_pool, g, _FakeClient(_boxscore(9)))
    assert res["status"] == STATUS_CONFLICT
    assert any("불일치" in n for n in res["notes"])
    assert res["starters"]["home"] == "Jose Ureña"      # statsapi 우선
    status = await db_pool.fetchval("SELECT lineup_status FROM games WHERE id = $1", g["id"])
    assert status == STATUS_CONFLICT


async def test_partial_boxscore_stays_predicted(db_pool):
    """[2-2] 타순이 덜 찬 상태는 확정이 아니다."""
    g = await _game(db_pool, ext_id="test-lineup-partial")
    res = await refresh_mlb_lineup(db_pool, g, _FakeClient(_boxscore(4)))
    assert res["status"] == STATUS_PREDICTED


async def test_boxscore_failure_keeps_previous_status(db_pool):
    """[2-2] 수집 실패가 상태를 되돌리거나 크래시를 내지 않는다."""
    class Boom(MLBLineupClient):
        def __init__(self):
            super().__init__(mock=False)

        async def fetch_boxscore(self, game_pk):
            raise RuntimeError("statsapi down")

    g = await _game(db_pool, ext_id="test-lineup-fail")
    res = await refresh_mlb_lineup(db_pool, g, Boom())
    assert res["changed"] is False


def test_predictions_records_lineup_status_and_both_methods():
    """[2-1][6] 픽에 라인업 상태와 두 방식 확률이 함께 기록된다 (스키마 계약)."""
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS lineup_status" in sql
    assert "ADD COLUMN IF NOT EXISTS p_legacy" in sql
    assert "ADD COLUMN IF NOT EXISTS method" in sql


# ---------------------------------------------------------------- 부상자(IL) 수집

def test_injured_list_parsed_from_roster():
    """[검증 후속] boxscore info가 비어 있어 결장자를 못 얻던 문제 — roster에서 받는다."""
    from app.collectors.lineups import injury_sentences, parse_injured

    roster = {"roster": [
        {"person": {"fullName": "Shaun Anderson"}, "position": {"abbreviation": "P"},
         "status": {"code": "D15", "description": "Injured 15-Day"}},
        {"person": {"fullName": "Wade Meckler"}, "position": {"abbreviation": "CF"},
         "status": {"code": "D7", "description": "Injured 7-Day"}},
        {"person": {"fullName": "Mike Trout"}, "position": {"abbreviation": "RF"},
         "status": {"code": "A", "description": "Active"}},          # 정상 선수는 제외
        {"person": {"fullName": "Sam Aldegheri"}, "position": {"abbreviation": "P"},
         "status": {"code": "RM", "description": "Reassigned to Minors"}},  # 부상 아님
    ]}
    injured = parse_injured(roster)
    assert [p["name"] for p in injured] == ["Shaun Anderson", "Wade Meckler"]

    sentences = injury_sentences(injured, "Los Angeles Angels")
    assert "Los Angeles Angels의 Shaun Anderson(투수)" in sentences[0]
    assert "결장" in sentences[0]                  # performance.absences가 읽는 형식


def test_injury_sentences_carry_role_for_coefficient_mapping():
    """[1-2] 역할이 문장에 있어야 조정 계수(불펜/주전)가 제대로 잡힌다."""
    from app.collectors.lineups import injury_sentences
    from app.engine.performance import WinProbAdjuster

    sents = injury_sentences(
        [{"name": "Jason Adam", "position": "P", "status": "Injured 15-Day"},
         {"name": "Ha-Seong Kim", "position": "SS", "status": "Injured 10-Day"}],
        "San Diego Padres")
    total, notes = WinProbAdjuster().absences(sents, "San Diego Padres")
    assert total < 0
    assert any("Jason Adam" in n for n in notes)
