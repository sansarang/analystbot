"""KBO 승률 경로 — 크롤링 숫자가 stats가 아니라 research에 있다.

실사고 구조:
  1) has_season_data가 MLB 승률 필드만 봐서 매 경기를 '실데이터 0건'으로 강등
  2) 앙상블·WinProbAdjuster가 h2h 배당이 있어야만 돌아 KBO 승률이 비거나 λ만 남음
  3) 실데이터 축이 같은 빈 stats를 봐 2-소스가 영원히 안 섬
"""

import pytest

from app.config import Settings
from app.engine.markets import (
    _axis_data,
    _season_edge,
    build_candidates,
    has_season_data,
)
from app.pipeline import _compute_picks, _enforce_data_rules


def _kbo_jg(**over):
    jg = {
        "game_id": 901, "sport": "kbo", "status": "scheduled",
        "home": "LG Twins", "away": "NC Dinos", "league": "KBO",
        "starts_at_kst": "08/27 18:30",
        "model_valid": False, "p_model": 0.5,
        "p_claude": 0.62, "judge_confidence": "medium",
        "market_probs": {}, "best_odds": {}, "alt_markets": [],
        "expert_picks": [], "stats": {},
        "research": {
            "home_standing": {"rank": 2, "w": 70, "l": 50, "d": 2, "played": 122},
            "away_standing": {"rank": 6, "w": 58, "l": 62, "d": 2, "played": 122},
            "home_offense": {"obp_30d": 0.357, "runs_per_game": 5.2},
            "away_offense": {"obp_30d": 0.331, "runs_per_game": 4.6},
            "home_pitcher": {"name": "임찬규", "era_season": 3.40},
            "away_pitcher": {"name": "신민혁", "era_season": 4.20},
            "league_baselines": {"obp": 0.3478, "ops": 0.7521, "slg": 0.4043},
        },
    }
    jg.update(over)
    if "research" in over:
        jg["research"] = over["research"]
    return jg


def test_kbo_season_data_comes_from_crawled_standings():
    """KBO는 stats.win_pct가 비어도 크롤링 순위표가 있으면 실데이터다."""
    jg = _kbo_jg()
    assert has_season_data(jg)
    edge = _season_edge(jg)
    assert edge is not None and edge > 0.5   # LG가 NC보다 우위


def test_kbo_empty_research_still_data_zero():
    jg = _kbo_jg(research={}, p_claude=0.55, verdict="테스트",
                 judge_confidence="high")
    assert not has_season_data(jg)
    _enforce_data_rules([jg])
    assert jg["judge_confidence"] == "low" and jg.get("data_zero")


def test_kbo_crawled_numbers_do_not_force_low_confidence():
    jg = _kbo_jg(verdict="테스트")
    _enforce_data_rules([jg])
    assert not jg.get("data_zero")
    assert jg["judge_confidence"] == "medium"


def test_mlb_stats_path_unchanged():
    """MLB 승률 필드는 종전 공식 그대로다 — 크롤링 분기가 덮지 않는다."""
    jg = {
        "home": "A", "away": "B", "sport": "mlb",
        "stats": {"home_win_pct": 0.60, "away_win_pct": 0.45,
                  "home_pitcher_era": 3.50, "away_pitcher_era": 4.10},
        "research": {
            "home_standing": {"w": 40, "l": 80},   # 반대 방향 — 쓰면 안 된다
            "away_standing": {"w": 80, "l": 40},
        },
    }
    edge = _season_edge(jg)
    # (0.60-0.45)*10 + (4.10-3.50) = 1.5 + 0.6 = 2.1
    assert abs(edge - 2.1) < 1e-9


def test_kbo_data_axis_follows_standings_not_empty_stats():
    jg = _kbo_jg()
    assert _axis_data(jg, "h2h", "LG Twins", None)
    assert not _axis_data(jg, "h2h", "NC Dinos", None)


def test_kbo_h2h_blends_lambda_and_claude_without_odds():
    """배당이 없어도 p_final = 0.5*λ + 0.5*Claude 가 보드에 찍힌다."""
    jg = _kbo_jg()
    _compute_picks(Settings(_env_file=None), [jg], "kbo")
    home = next(c for c in jg["market_board"]
                if c["market"] == "h2h" and c["side"] == "LG Twins")
    dist_p = jg["p_heuristic"]["LG Twins"]
    blended = 0.5 * dist_p + 0.5 * 0.62
    assert home["p"] is not None
    assert abs(home["p"] - blended) < 0.02, (
        f"보드 승률 {home['p']} 이 앙상블 {blended:.4f}(λ {dist_p:.4f}+Claude 0.62)와 다름")
    assert home["basis"] == "앙상블"
    assert home["axes"]["data"] and home["axes"]["model"]
    assert home.get("two_source")
    assert not jg.get("data_zero")


def test_kbo_unpriced_h2h_can_be_approved_on_probability():
    """배당 없음 ≠ 근거 부족. 승률·2-소스가 서면 보드에서 승인된다."""
    jg = _kbo_jg()
    _compute_picks(Settings(_env_file=None), [jg], "kbo")
    home = next(c for c in jg["market_board"]
                if c["market"] == "h2h" and c["side"] == "LG Twins")
    assert home["odds"] is None
    if home["p"] >= 0.58 and home.get("two_source"):
        assert home.get("approved"), home.get("reject_reason")


def test_h2h_keeps_ensemble_when_distribution_present():
    """토탈은 분포, 승패는 앙상블 — 분포로 승패를 덮지 않는다."""
    from app.engine.scoring import game_distribution

    jg = _kbo_jg()
    jg["distribution"] = game_distribution(
        jg, jg["research"], "kbo", Settings(_env_file=None))
    board = build_candidates(jg, "kbo", {"LG Twins": 0.60, "NC Dinos": 0.40})
    home = next(c for c in board if c["market"] == "h2h" and c["side"] == "LG Twins")
    assert abs(home["p"] - 0.60) < 1e-6
    under = next(c for c in board if c["market"] == "totals" and c["side"] == "Under")
    assert under["basis"] == "기대득점 분포"


@pytest.mark.asyncio
async def test_ensure_analysis_cache_skips_when_judged():
    from app.pipeline import ensure_analysis_cache
    import json

    body = json.dumps({"games": [{
        "game_id": 1, "status": "scheduled", "starts_at_kst": "08/28 18:30",
        "p_claude": 0.61,
    }]})

    class R:
        def __init__(self):
            self.store = {"analysis:kbo:2026-08-28": body}

        async def get(self, k):
            return self.store.get(k)

    assert await ensure_analysis_cache(None, R(), "kbo", "2026-08-28") is True


@pytest.mark.asyncio
async def test_ensure_analysis_cache_rebuilds_when_judge_missing(monkeypatch):
    """키만 있고 p_claude가 없으면 파이프라인을 다시 돈다."""
    from app import pipeline as P
    import json

    hollow = json.dumps({"games": [{
        "game_id": 1, "status": "scheduled", "starts_at_kst": "08/28 18:30",
        "p_claude": None, "judge_missing": True,
    }]})

    class R:
        def __init__(self):
            self.store = {"analysis:kbo:2026-08-28": hollow}

        async def get(self, k):
            return self.store.get(k)

    r = R()
    calls = []

    async def fake_run(*_a, **k):
        calls.append(k)
        r.store["analysis:kbo:2026-08-28"] = json.dumps({"games": [{
            "game_id": 1, "status": "scheduled", "starts_at_kst": "08/28 18:30",
            "p_claude": 0.60,
        }]})

    monkeypatch.setattr(P, "run_pipeline", fake_run)
    assert await P.ensure_analysis_cache(None, r, "kbo", "2026-08-28") is True
    assert calls and calls[0]["force_refresh"] is True


@pytest.mark.asyncio
async def test_ensure_analysis_cache_builds_when_missing(monkeypatch):
    from app import pipeline as P
    import json

    class R:
        def __init__(self):
            self.store = {}

        async def get(self, k):
            return self.store.get(k)

    r = R()
    calls = []

    async def fake_run(*_a, **k):
        calls.append(k)
        r.store["analysis:kbo:2026-08-28"] = json.dumps({"games": [{
            "game_id": 1, "status": "scheduled", "starts_at_kst": "08/28 18:30",
            "p_claude": 0.60,
        }]})

    monkeypatch.setattr(P, "run_pipeline", fake_run)
    assert await P.ensure_analysis_cache(None, r, "kbo", "2026-08-28") is True
    assert calls[0]["sport"] == "kbo" and calls[0]["force_refresh"] is True


@pytest.mark.asyncio
async def test_ensure_analysis_cache_false_if_rebuild_still_unjudged(monkeypatch):
    """파이프라인이 돌아도 p_claude가 없으면 발송 준비됨이 아니다."""
    from app import pipeline as P

    class R:
        def __init__(self):
            self.store = {}

        async def get(self, k):
            return self.store.get(k)

    r = R()

    async def fake_run(*_a, **k):
        r.store["analysis:kbo:2026-08-28"] = "{}"

    monkeypatch.setattr(P, "run_pipeline", fake_run)
    assert await P.ensure_analysis_cache(None, r, "kbo", "2026-08-28") is False


def test_asia_prefetch_covers_kbo_and_npb():
    import inspect

    from app.scheduler import prefetch_asia_job

    src = inspect.getsource(prefetch_asia_job)
    assert "kbo" in src and "npb" in src


def test_analysis_cache_ready_ignores_other_days():
    import json

    from app.pipeline import analysis_cache_ready

    raw = json.dumps({"games": [
        {"status": "scheduled", "starts_at_kst": "08/28 18:30", "p_claude": 0.61},
        {"status": "scheduled", "starts_at_kst": "08/29 18:00", "p_claude": None},
    ]})
    assert analysis_cache_ready(raw, "2026-08-28") is True
    hollow = json.dumps({"games": [
        {"status": "scheduled", "starts_at_kst": "08/28 18:30", "p_claude": None},
        {"status": "scheduled", "starts_at_kst": "08/29 18:00", "p_claude": 0.70},
    ]})
    assert analysis_cache_ready(hollow, "2026-08-28") is False
    assert analysis_cache_ready("{}", "2026-08-28") is False


def test_pipeline_scheduled_query_is_date_scoped():
    import inspect

    from app import pipeline as P

    src = inspect.getsource(P.build_analysis)
    assert "date_cls.fromisoformat(date)" in src
    assert "starts_at >= now() - interval '12 hours'" in src
    assert "::date = $2::date" not in src

