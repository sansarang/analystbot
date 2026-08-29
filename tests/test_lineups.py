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
        players = {
            f"ID{i}": {"person": {"id": i, "fullName": f"Batter {i}"}}
            for i in range(1, n + 1)
        }
        players["ID900"] = {"person": {"id": 900, "fullName": starter}}
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


def test_parse_boxscore_names_dict_maps_id_to_fullname():
    p = parse_boxscore(_boxscore(9))
    assert p["home"]["names"][1] == "Batter 1"
    assert p["home"]["names"][900] == "Jose Ureña"


def test_absence_uses_names_dict_not_hash_id():
    from app.collectors.absences import from_lineup

    sentences = from_lineup(
        "Cleveland Guardians",
        [{"id": 99, "pa": 40}, {"id": 1, "pa": 30}],
        [1, 2, 3, 4, 5, 6, 7, 8, 9],
        {99: "José Ramírez", 1: "Batter 1"},
    )
    assert len(sentences) == 1
    assert "José Ramírez" in sentences[0]
    assert "선수 #" not in sentences[0]


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


# ---------------------------------------------------------------- [§8-16] 딥서치 라인업

def test_research_lineup_requires_valid_status():
    """[§8-16] '확정'은 강한 단언 — 상태값이 정확할 때만 받는다."""
    from app.research.validate import sanitize_research

    ok, _ = sanitize_research(
        {"lineup": {"status": "confirmed", "home": "1번 홍창기(우익수) 2번 신민재(2루수)",
                    "source": "스포츠조선"}}, "kbo")
    assert ok["lineup"]["status"] == "confirmed"
    assert ok["lineup"]["source"] == "스포츠조선"

    bad, dropped = sanitize_research(
        {"lineup": {"status": "아마도 확정", "home": "1번 홍창기"}}, "kbo")
    assert "lineup" not in bad and "lineup" in dropped


def test_research_lineup_needs_actual_names():
    """상태만 'confirmed'라고 하고 명단이 없으면 근거가 없다 — 받지 않는다."""
    from app.research.validate import sanitize_research

    out, dropped = sanitize_research({"lineup": {"status": "confirmed"}}, "kbo")
    assert "lineup" not in out
    assert any("lineup" in d for d in dropped)


def test_research_lineup_drops_unavailable_prose():
    """'라인업을 찾을 수 없습니다'가 명단으로 들어가면 안 된다."""
    from app.research.validate import sanitize_research

    out, _ = sanitize_research(
        {"lineup": {"status": "confirmed", "home": "라인업 정보를 찾을 수 없습니다."}}, "kbo")
    assert "lineup" not in out


def test_projected_is_not_promoted_to_confirmed():
    """[§8-16] 예상을 확정으로 승격하지 않는다 — '최종 픽' 자격이 잘못 부여된다."""
    from app.collectors.lineups import STATUS_CONFIRMED, STATUS_PREDICTED, pick_state

    assert pick_state(STATUS_CONFIRMED)[0] == "final"
    assert pick_state(STATUS_PREDICTED)[0] == "preliminary"
    # 파이프라인이 쓰는 값이 실제 상수와 같아야 한다 (오타면 조용히 '잠정'이 된다)
    import re
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('_lu.get("status") == "projected"')
    assert "STATUS_PREDICTED" in src[i:i + 300], "예상 라인업이 미지의 문자열로 저장된다"


def test_lineup_stage_measured_for_all_sports():
    """[§8-16] KBO·NPB도 라인업을 계측한다 — 끄면 '못 받고 있다'는 사실이 안 보인다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("라인업"')
    guard = src[max(0, i - 700):i]
    assert 'sport in ("mlb", "soccer")' not in guard, "라인업 계측이 종목으로 막혀 있다"


def test_qualifies_blocks_baseball_until_lineup_confirmed():
    """잠정 픽은 보드에 남기고 추천에서 뺀다. MIN_WIN_PROB는 그대로다."""
    from app.config import Settings
    from app.pipeline import qualifies

    s = Settings(_env_file=None)
    assert s.min_win_prob == 0.58
    pick = {"p": 0.62, "odds": 1.70, "two_source": True, "sport": "kbo",
            "lineup_status": "predicted"}
    assert not qualifies(pick, s)
    pick["lineup_status"] = "confirmed"
    pick["pick_state"] = "final"
    assert qualifies(pick, s)


def test_qualifies_soccer_does_not_require_lineup():
    from app.config import Settings
    from app.pipeline import qualifies

    pick = {"p": 0.62, "odds": 1.70, "two_source": True, "sport": "soccer"}
    assert qualifies(pick, Settings(_env_file=None))


def test_starter_change_notes_from_merged_names():
    from app.pipeline import starter_change_notes

    notes = starter_change_notes(
        {"home_pitcher": {"name": "양현종"}, "away_pitcher": {"name": "박세웅"}},
        {"home": "황동하", "away": "박세웅"})
    assert notes == ["홈 선발 변경: 황동하 → 양현종"]
