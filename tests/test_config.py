"""키 유무에 따라 mock 플래그가 올바르게 세팅되는지 검증."""

import pytest

from app.config import Settings

KEY_ENVS = [
    "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "PPLX_API_KEY",
    "XAI_API_KEY", "ODDS_API_KEY", "APIFOOTBALL_KEY", "FORCE_MOCK",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in KEY_ENVS:
        monkeypatch.delenv(name, raising=False)


def make(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_no_keys_means_all_mock():
    s = make()
    assert s.mock_odds and s.mock_football
    assert s.mock_perplexity and s.mock_grok and s.mock_judge


def test_key_present_means_live():
    s = make(
        odds_api_key="k", apifootball_key="k", pplx_api_key="k",
        xai_api_key="k", anthropic_api_key="k",
    )
    assert not s.mock_odds and not s.mock_football
    assert not s.mock_perplexity and not s.mock_grok and not s.mock_judge


def test_mlb_needs_no_key():
    assert make().mock_mlb is False


def test_force_mock_overrides_keys():
    s = make(force_mock=True, odds_api_key="k", anthropic_api_key="k")
    assert s.mock_mlb and s.mock_odds and s.mock_judge


def test_ensemble_weights_exclude_market():
    """[1-1] 승률 판정에서 시장 가중치는 0 — 배당은 수익 계산·표시에만 쓴다."""
    s = make()
    assert s.ensemble_w_market == 0.0
    assert (s.ensemble_w_model, s.ensemble_w_claude) == (0.50, 0.50)
    assert abs(s.ensemble_w_model + s.ensemble_w_claude - 1.0) < 1e-9


def test_legacy_weights_kept_for_parallel_scoring():
    """[6] 기존 시장 반영 앙상블은 병렬 채점용으로 보존한다."""
    s = make()
    assert (s.legacy_w_model, s.legacy_w_market, s.legacy_w_claude) == (0.45, 0.30, 0.25)
    assert abs(sum((s.legacy_w_model, s.legacy_w_market, s.legacy_w_claude)) - 1.0) < 1e-9


def test_recommendation_thresholds_are_config_driven():
    """[3-1] 추천 자격은 승률·배당 하한 두 값으로만 결정된다."""
    s = make()
    assert s.min_win_prob == 0.58 and s.min_odds == 1.60
    assert s.signal_green_prob == 0.62
    # 58% × 1.60 = 0.928 → EV -7.2%. 손익분기 배당은 1/0.58 ≈ 1.724다.
    assert s.min_win_prob * s.min_odds < 1.0
