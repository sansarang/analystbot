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


def test_ensemble_weights_default():
    s = make()
    assert (s.ensemble_w_model, s.ensemble_w_market, s.ensemble_w_claude) == (
        0.45, 0.30, 0.25,
    )
    assert abs(s.ensemble_w_model + s.ensemble_w_market + s.ensemble_w_claude - 1.0) < 1e-9
