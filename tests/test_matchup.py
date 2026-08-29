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


@pytest.mark.asyncio
async def test_matchup_fails_closed_without_form_cache():
    jg = {"sport": "kbo", "home": "한화", "away": "KIA"}
    out = await judge_matchup(jg, _MemRedis(), "2026-08-29", mock=True)
    assert out is None
    assert jg["form_unavailable"] is True
    assert "p_claude" not in jg


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
