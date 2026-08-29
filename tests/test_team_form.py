"""3단계 — 팀 경기력 분석. 캐시 히트 시 재호출 금지, JSON 실패면 unavailable."""
import json

import pytest

from app.config import Settings
from app.engine.team_form import (
    FORM_TTL,
    analyze_games,
    analyze_team,
    form_key,
    message_kwargs,
    packet_from_usage,
    parse_json_object,
)


class _MemRedis:
    def __init__(self):
        self.store = {}
        self.ttls = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v
        self.ttls[k] = ex


def test_parse_json_object_strips_fences():
    text = '```json\n{"team": "한화", "흐름": "상승"}\n```'
    assert parse_json_object(text)["team"] == "한화"
    assert parse_json_object("not json") is None
    assert parse_json_object("[1,2]") is None


def test_packet_from_usage_does_not_invent_season_era():
    pkt = packet_from_usage(
        "한화", "kbo", "2026-08-29",
        {"results_l3": "WWL", "games": [{"opponent": "KIA", "opponent_rank": 3}]})
    blob = json.dumps(pkt, ensure_ascii=False)
    assert "era" not in blob.lower()
    assert "xwoba" not in blob.lower()
    assert pkt["games"][0]["opponent_rank"] == 3


@pytest.mark.asyncio
async def test_analyze_team_caches_and_does_not_recall(monkeypatch):
    r = _MemRedis()
    calls = {"n": 0}

    async def boom(*a, **kw):
        calls["n"] += 1
        raise AssertionError("캐시 히트인데 Claude를 다시 불렀다")

    first = await analyze_team(
        r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=True)
    assert first["unavailable"] is False
    assert first["model"] == "mock"
    assert r.ttls[form_key("kbo", "한화", "2026-08-29")] == FORM_TTL
    monkeypatch.setattr("app.engine.team_form.complete_json", boom)
    second = await analyze_team(
        r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=False)
    assert second == first
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_analyze_team_marks_unavailable_after_two_parse_fails(monkeypatch):
    r = _MemRedis()

    async def garbage(*a, **kw):
        return "산문만 있고 JSON 없음"

    monkeypatch.setattr("app.engine.team_form.complete_json", garbage)
    out = await analyze_team(
        r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=False)
    assert out["unavailable"] is True
    cached = json.loads(r.store[form_key("kbo", "한화", "2026-08-29")])
    assert cached["unavailable"] is True
    from app.config import get_settings

    assert cached["model"] == get_settings().team_form_model


@pytest.mark.asyncio
async def test_analyze_games_once_per_team():
    r = _MemRedis()
    games = [
        {"home": "한화", "away": "KIA", "research": {}},
        {"home": "롯데", "away": "한화", "research": {}},
    ]
    forms = await analyze_games(r, "kbo", "2026-08-29", games, mock=True)
    assert set(forms) == {"한화", "KIA", "롯데"}
    assert games[0]["home_form"]["team"] == "한화"
    assert games[1]["away_form"]["team"] == "한화"


def test_message_kwargs_locks_temperature_zero_and_does_not_use_judge_tokens():
    s = Settings(_env_file=None)
    kw = message_kwargs(s.team_form_model, s.team_form_max_tokens, "hi")
    assert kw["model"] == "claude-haiku-4-5-20251001"
    assert kw["max_tokens"] == 1500
    assert kw["extra_body"]["temperature"] == 0
    kw2 = message_kwargs(s.matchup_model, s.matchup_max_tokens, "hi")
    assert kw2["model"] == "claude-sonnet-5"
    assert kw2["max_tokens"] == 1000
    from app.engine.judge import JUDGE_MAX_TOKENS

    assert kw["max_tokens"] != JUDGE_MAX_TOKENS
    assert kw2["max_tokens"] != JUDGE_MAX_TOKENS
