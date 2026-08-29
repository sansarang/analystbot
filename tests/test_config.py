"""키 유무에 따라 mock 플래그가 올바르게 세팅되는지 검증."""

import pytest

from app.config import Settings

KEY_ENVS = [
    "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY", "PPLX_API_KEY",
    "XAI_API_KEY", "ODDS_API_KEY", "APIFOOTBALL_KEY", "FORCE_MOCK",
    "DISABLED_PROVIDERS", "MODEL_TEAM_FORM", "MODEL_MATCHUP",
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


def test_grok_and_perplexity_are_disabled_by_default():
    """의도적 미사용. 키 유무와 무관하다 — 키가 있어도 부르지 않는다."""
    s = make(xai_api_key="k", pplx_api_key="k")
    assert s.is_disabled("grok") and s.is_disabled("perplexity")
    assert s.is_disabled("groq") and s.is_disabled("gemini")
    assert not s.is_disabled("odds")
    assert not s.mock_grok and not s.mock_perplexity
    assert s.disabled_providers == "grok,perplexity,groq,gemini"


def test_disabled_can_be_cleared():
    s = make(disabled_providers="")
    assert not s.is_disabled("grok") and not s.is_disabled("perplexity")


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
    assert s.signal_green_prob == 0.62
    # 58% × 1.55 = 0.899 → EV -10.1%. 손익분기 배당은 1/0.58 ≈ 1.724다.
    # §0 승률 상한 — 운 비중 MLB 27.8%, 완벽 정보 상한 72%보다 보수적으로
    assert (s.max_win_prob_mlb, s.min_win_prob_mlb) == (0.68, 0.32)
    assert (s.max_win_prob_soccer, s.min_win_prob_soccer) == (0.72, 0.10)
    # §0 시장 대비 엣지 상한 — Starlizard(분석가 200명)도 1~2%다
    assert s.prob_cap_alert_n == 3            # 하루 3건 초과 시 모델 점검 경고
    # [4] 원정 비대칭 — 분데스리가 연구: 원정 베팅 ROI -17%
    assert s.away_prob_penalty == 0.05
    assert s.min_win_prob == 0.58
    assert s.npb_last3_verified is True
    assert s.lambda_h2h_min_edge == 0.05
    assert s.team_form_model == "claude-haiku-4-5-20251001"
    assert s.matchup_model == "claude-sonnet-5"
    assert s.team_form_max_tokens == 1500
    assert s.matchup_max_tokens == 1000
    assert s.judge_model == "claude-opus-4-6"


def test_form_matchup_models_from_env(monkeypatch):
    monkeypatch.setenv("MODEL_TEAM_FORM", "haiku-from-env")
    monkeypatch.setenv("MODEL_MATCHUP", "sonnet-from-env")
    s = Settings(_env_file=None)
    assert s.team_form_model == "haiku-from-env"
    assert s.matchup_model == "sonnet-from-env"
