"""4단계 — 매치업. p_home은 코드에서 0.32–0.68 절사. 폼은 재호출하지 않는다."""
import json

import pytest

from app.config import Settings
from app.engine.matchup import apply_matchup, clip_p_home, judge_matchup
from app.engine.team_form import form_key


class _MemRedis:
    def __init__(self, store=None):
        self.store = store or {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v


def test_clip_p_home_uses_mlb_bounds():
    s = Settings(_env_file=None)
    assert clip_p_home(0.90, s) == s.max_win_prob_mlb == 0.68
    assert clip_p_home(0.10, s) == s.min_win_prob_mlb == 0.32
    assert clip_p_home(0.55, s) == 0.55
    assert clip_p_home("bad", s) == 0.5


def test_apply_matchup_maps_confidence_low_as_veto():
    jg = {}
    apply_matchup(jg, {
        "p_home": 0.80,
        "확신도": "하",
        "근거": ["홈 3경기 흐름", "원정 선발 최근 등판", "오늘 타순"],
    }, Settings(_env_file=None))
    assert jg["p_claude"] == 0.68
    assert jg["judge_confidence"] == "low"
    assert jg["judge_pass"] is True
    assert jg["form_unavailable"] is False
    assert jg["model"] == Settings(_env_file=None).matchup_model
    assert jg["matchup"]["model"] == jg["model"]


@pytest.mark.asyncio
async def test_matchup_analyzes_on_cache_miss(monkeypatch):
    r = _MemRedis()
    calls = {"n": 0}
    orig = None
    from app.engine import team_form as tf

    orig = tf.analyze_team

    async def counted(*a, **kw):
        calls["n"] += 1
        return await orig(*a, **kw)

    monkeypatch.setattr("app.engine.team_form.analyze_team", counted)
    jg = {"sport": "kbo", "home": "한화", "away": "KIA", "research": {}}
    verdict = await judge_matchup(jg, r, "2026-08-29", mock=True)
    assert verdict["p_home"] == 0.55
    assert calls["n"] == 2
    assert jg["form_unavailable"] is False


@pytest.mark.asyncio
async def test_matchup_reads_form_cache_and_does_not_reanalyze(monkeypatch):
    date = "2026-08-29"
    home, away = "한화", "KIA"
    r = _MemRedis({
        form_key("kbo", home, date): json.dumps(
            {"team": home, "unavailable": False, "흐름": "상승"}),
        form_key("kbo", away, date): json.dumps(
            {"team": away, "unavailable": False, "흐름": "유지"}),
    })
    calls = {"n": 0}

    async def boom(*a, **kw):
        calls["n"] += 1
        raise AssertionError("매치업이 팀 폼을 재호출했다")

    monkeypatch.setattr("app.engine.team_form.analyze_team", boom)
    jg = {"sport": "kbo", "home": home, "away": away, "research": {}}
    verdict = await judge_matchup(jg, r, date, mock=True)
    assert verdict["p_home"] == 0.55
    assert jg["p_claude"] == 0.55
    assert jg["judge_confidence"] == "medium"
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_matchup_records_analysis_game_key():
    r = _MemRedis()
    jg = {"sport": "kbo", "game_id": 99, "home": "한화", "away": "KIA",
          "research": {}}
    await judge_matchup(jg, r, "2026-08-29", mock=True)
    raw = r.store[form_key("kbo", "한화", "2026-08-29")]  # form also written
    assert json.loads(raw)["model"] == "mock"
    from app.engine.team_form import analysis_game_key

    rec = json.loads(r.store[analysis_game_key("kbo", 99, "2026-08-29")])
    assert rec["model"] == "mock"
    assert rec["p_home"] == 0.55


@pytest.mark.asyncio
async def test_matchup_retries_when_form_cache_unavailable(monkeypatch):
    date = "2026-08-29"
    home, away = "한화", "KIA"
    r = _MemRedis({
        form_key("kbo", home, date): json.dumps(
            {"team": home, "unavailable": True, "cause": "credit_400"}),
        form_key("kbo", away, date): json.dumps(
            {"team": away, "unavailable": False, "흐름": "유지"}),
    })
    calls = {"n": 0}
    from app.engine import team_form as tf

    orig = tf.analyze_team

    async def counted(*a, **kw):
        calls["n"] += 1
        return await orig(*a, **kw)

    monkeypatch.setattr("app.engine.team_form.analyze_team", counted)
    jg = {"sport": "kbo", "home": home, "away": away, "research": {}}
    await judge_matchup(jg, r, date, mock=True)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_matchup_quota_does_not_retry(monkeypatch):
    from app.collectors.base import ApiQuotaError
    from app.engine.credit_guard import reset

    reset()
    date = "2026-08-29"
    home, away = "한화", "KIA"
    r = _MemRedis({
        form_key("kbo", home, date): json.dumps(
            {"team": home, "unavailable": False, "흐름": "상승"}),
        form_key("kbo", away, date): json.dumps(
            {"team": away, "unavailable": False, "흐름": "유지"}),
    })
    n = {"n": 0}

    async def quota(*a, **kw):
        n["n"] += 1
        raise ApiQuotaError("anthropic", "credit balance too low")

    monkeypatch.setattr("app.engine.matchup.complete_json", quota)
    jg = {"sport": "kbo", "home": home, "away": away, "research": {}}
    with pytest.raises(ApiQuotaError):
        await judge_matchup(jg, r, date, mock=False)
    assert n["n"] == 1
    reset()


def test_old_judge_still_uses_judge_model_not_matchup_model():
    from pathlib import Path

    src = Path("app/engine/judge.py").read_text(encoding="utf-8")
    assert "JUDGE_MAX_TOKENS = 16000" in src
    assert "self.settings.judge_model" in src
    assert "team_form_model" not in src
    assert "matchup_model" not in src


@pytest.mark.parametrize("sport", ["mlb", "kbo", "npb"])
async def test_old_judge_refuses_baseball_payloads(sport, monkeypatch):
    """야구는 구 Judge(Opus)를 타지 않는다 — 호출부가 아니라 Judge 안에서 막는다.

    실측 2026-08-29: 개편이 미배포인 상태에서 KBO 5 + NPB 6경기가 구 Judge로
    나가 크레딧이 소진됐다. 호출부 분기 6곳 중 하나만 빠져도 같은 일이 난다.
    """
    from app.engine.judge import Judge

    called = []

    async def boom(self, payload):
        called.append(payload)
        raise AssertionError("야구가 구 Judge HTTP 경로에 도달했다")

    monkeypatch.setattr(Judge, "_judge_once", boom)
    payload = {"date": "2026-08-30", "sport": sport,
               "games": [{"game_id": i, "home": "A", "away": "B"} for i in range(6)]}
    assert await Judge(mock=False).judge(payload) == {"games": []}
    assert called == []


async def test_old_judge_still_reaches_soccer(monkeypatch):
    """가드가 과잉 적용되면 축구 판정이 통째로 사라진다 — 그 회귀를 막는다."""
    from app.engine.judge import Judge

    seen = []

    async def ok(self, payload):
        seen.append(payload["sport"])
        return {"games": [{"game_id": 1, "p_claude": 0.6, "verdict": "v"}]}

    monkeypatch.setattr(Judge, "_judge_once", ok)
    out = await Judge(mock=False).judge(
        {"date": "2026-08-30", "sport": "soccer",
         "games": [{"game_id": 1, "home": "A", "away": "B"}]})
    assert seen == ["soccer"]
    assert out["games"][0]["p_claude"] == 0.6


def test_pipeline_runs_form_before_matchup_and_skips_form_on_rejudge():
    """배선: 프리페치는 폼→매치업. 라인업 재판정은 매치업만 (폼 재호출 금지)."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i_form = src.index("await _run_baseball_forms(")
    i_mu = src.index("await _run_baseball_matchups(")
    assert i_form < i_mu
    start = src.index("async def rejudge_after_lineup")
    end = src.index("async def ensure_game_fresh")
    body = src[start:end]
    assert "_run_baseball_forms" not in body
    assert "_run_baseball_matchups" in body
