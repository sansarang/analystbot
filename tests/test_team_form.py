"""3단계 — 팀 경기력 분석. 캐시 히트 시 재호출 금지, JSON 실패면 unavailable."""
import json

import pytest

from app.config import Settings
from app.engine.team_form import (
    CAUSE_CREDIT,
    CAUSE_PARSE,
    CAUSE_TIMEOUT,
    FORM_TTL,
    FORM_UNAVAILABLE_TTL,
    analyze_games,
    analyze_team,
    fail_cause,
    form_key,
    load_form,
    message_kwargs,
    packet_from_usage,
    parse_json_object,
    unavailable_form,
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
    mixed = 'thinking: 우세를 가린다.\n{"p_home": 0.55, "우세": "home"}\n끝.'
    assert parse_json_object(mixed)["p_home"] == 0.55
    nested = '서문 {"a": {"b": 1}, "p_home": 0.4} 후문'
    assert parse_json_object(nested)["p_home"] == 0.4


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
    assert cached["cause"] == CAUSE_PARSE
    assert r.ttls[form_key("kbo", "한화", "2026-08-29")] == FORM_UNAVAILABLE_TTL
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
    # [2026-09-06] 최종 판정은 Opus 가 한 번에 낸다 (fable → opus, 사용자 지시).
    assert kw2["model"] == "claude-opus-5"
    # ⚠️ [사본 제거 2026-09-07] 숫자를 여기 적어 두니 config 를 올릴 때마다
    #    이 테스트가 깨졌다. 이 테스트가 볼 것은 **값이 그대로 전달되는가**다.
    assert kw2["max_tokens"] == s.matchup_max_tokens
    assert "extra_body" not in kw2
    from app.engine.judge import JUDGE_MAX_TOKENS

    assert kw["max_tokens"] != JUDGE_MAX_TOKENS
    assert kw2["max_tokens"] != JUDGE_MAX_TOKENS


def test_fail_cause_maps_three_buckets():
    from app.collectors.base import ApiQuotaError

    assert fail_cause(ApiQuotaError("anthropic", "credit balance too low")) == CAUSE_CREDIT
    assert fail_cause(TimeoutError("timed out")) == CAUSE_TIMEOUT
    assert fail_cause(ValueError("bad json")) == CAUSE_PARSE
    assert fail_cause(None) == CAUSE_PARSE


@pytest.mark.asyncio
async def test_load_form_skips_unavailable():
    r = _MemRedis()
    key = form_key("kbo", "한화", "2026-08-29")
    r.store[key] = json.dumps(
        unavailable_form("한화", "claude-haiku-4-5-20251001", CAUSE_PARSE),
        ensure_ascii=False)
    assert await load_form(r, "kbo", "한화", "2026-08-29") is None
    r.store[key] = json.dumps({"team": "한화", "unavailable": False})
    assert (await load_form(r, "kbo", "한화", "2026-08-29"))["team"] == "한화"


@pytest.mark.asyncio
async def test_unavailable_cache_is_not_a_hit(monkeypatch):
    r = _MemRedis()
    key = form_key("kbo", "한화", "2026-08-29")
    r.store[key] = json.dumps(
        unavailable_form("한화", "old", CAUSE_PARSE), ensure_ascii=False)
    r.ttls[key] = FORM_TTL
    n = {"n": 0}

    async def ok(*a, **kw):
        n["n"] += 1
        return '{"team":"한화","흐름":"유지"}'

    monkeypatch.setattr("app.engine.team_form.complete_json", ok)
    out = await analyze_team(
        r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=False)
    assert n["n"] == 1
    assert out["unavailable"] is False
    assert r.ttls[key] == FORM_TTL


@pytest.mark.asyncio
async def test_analyze_team_timeout_writes_cause_and_short_ttl(monkeypatch):
    r = _MemRedis()

    async def boom(*a, **kw):
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.engine.team_form.complete_json", boom)
    out = await analyze_team(
        r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=False)
    assert out["unavailable"] is True
    assert out["cause"] == CAUSE_TIMEOUT
    assert r.ttls[form_key("kbo", "한화", "2026-08-29")] == FORM_UNAVAILABLE_TTL


@pytest.mark.asyncio
async def test_analyze_team_credit_400_does_not_retry(monkeypatch):
    from app.collectors.base import ApiQuotaError
    from app.engine.credit_guard import reset

    reset()
    r = _MemRedis()
    n = {"n": 0}

    async def quota(*a, **kw):
        n["n"] += 1
        raise ApiQuotaError("anthropic", "credit balance too low")

    monkeypatch.setattr("app.engine.team_form.complete_json", quota)
    with pytest.raises(ApiQuotaError):
        await analyze_team(
            r, "kbo", "한화", "2026-08-29", {"games": []}, [], mock=False)
    assert n["n"] == 1
    cached = json.loads(r.store[form_key("kbo", "한화", "2026-08-29")])
    assert cached["cause"] == CAUSE_CREDIT
    assert r.ttls[form_key("kbo", "한화", "2026-08-29")] == FORM_UNAVAILABLE_TTL
    reset()


@pytest.mark.asyncio
async def test_analyze_games_stops_on_quota(monkeypatch):
    from app.collectors.base import ApiQuotaError
    from app.engine.credit_guard import reset

    reset()
    r = _MemRedis()
    seen = []

    async def fake(redis, league, team, date, pkt, news, force=False, mock=None):
        seen.append(team)
        if team == "KIA":
            raise ApiQuotaError("anthropic", "credit balance too low")
        return {"team": team, "unavailable": False}

    monkeypatch.setattr("app.engine.team_form.analyze_team", fake)
    # 🔴 [CHN-1 2026-09-15] 이 테스트는 "**Anthropic 이 주전일 때만** 슬레이트를
    #    멈춘다"를 잰다(`_free_primary`). 종전에는 그 조건을 개발자 `.env` 에
    #    맡기고 있었다 — `.env` 에 FORM_CHAIN 이 생기자 조용히 깨졌다.
    #    환경이 아니라 **테스트가** 조건을 세운다.
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PAID_LLM_ALLOWED", "1")
    monkeypatch.setenv("FORM_CHAIN", "anthropic/claude-opus-5")
    monkeypatch.setenv("JUDGE_CHAIN", "anthropic/claude-opus-5")
    from app.llm.judge_route import chain
    from app.engine.team_form import FORM_ROLE
    assert chain(FORM_ROLE)[0][0] == "anthropic", chain(FORM_ROLE)

    games = [
        {"home": "한화", "away": "KIA", "research": {}},
        {"home": "롯데", "away": "SSG", "research": {}},
    ]
    with pytest.raises(ApiQuotaError):
        await analyze_games(r, "kbo", "2026-08-29", games, mock=False)
    assert seen == ["한화", "KIA"]
    reset()
    get_settings.cache_clear()
