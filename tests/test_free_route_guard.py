"""[4번 2026-09-04] "완전 무료"가 실제로 무료인지 잠근다.

🔴 실측 2026-09-04: `FREE_JUDGE_MODEL` 에 `openrouter/deepseek/deepseek-r1`
   이 들어 있었다. OpenRouter 는 같은 이름의 **유료·무료 두 변형**을 파는데
   무료판만 `:free` 로 끝난다. 키 조회 결과 `is_free_tier: true` 인데도
   `usage: 0.0002594` — 폴백이 탈 때마다 돈이 나가고 있었다.

   사용자 지시: "난 완전 돈이 안들어갔으면 해" (2026-09-04).
"""
import pytest

from app.llm.judge_route import chain, is_free


@pytest.mark.parametrize("provider,model,expected", [
    ("openrouter", "minimax/minimax-m3:free", True),
    ("openrouter", "google/gemma-4-31b-it:free", True),
    ("openrouter", "deepseek/deepseek-r1", False),      # 🔴 실제로 과금됐다
    ("openrouter", "deepseek/deepseek-r1:free", True),
    ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b", True),   # 계정이 무료 티어
    ("groq", "qwen/qwen3.8-27b", True),
])
def test_is_free(provider, model, expected):
    assert is_free(provider, model) is expected


def test_paid_openrouter_candidate_is_dropped_from_the_chain(monkeypatch):
    """유료 후보는 사슬에 앉지 못한다 — 조용히 통과시키지 않는다."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "nvidia")
    monkeypatch.setenv("FREE_JUDGE_MODEL",
                       "nvidia/nvidia/nemotron-3-ultra-550b-a55b,"
                       "openrouter/deepseek/deepseek-r1,"
                       "openrouter/minimax/minimax-m3:free")
    try:
        got = chain("matchup")
    finally:
        get_settings.cache_clear()
    assert ("openrouter", "deepseek/deepseek-r1") not in got
    assert ("openrouter", "minimax/minimax-m3:free") in got
    assert got[0] == ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b")
    # 비상 복귀는 사슬 **끝**에만 — 캡이 지킨다.
    assert got[-1][0] == "anthropic"


def test_groq_and_gemini_are_no_longer_disabled_by_default():
    """🔴 8/28 저녁의 '키 불량' 임시 조치가 굳어 무료 경로를 막고 있었다.

    `interpreter`(2단 해석봇)·`narrator`(서술)는 `judge_route` 가 아니라
    `provider.provider_chain` 을 탄다. 거기서 Groq·Gemini 가 disabled 면
    사슬이 크레딧 0 인 Anthropic 으로 떨어진다 — 자료6(라인업 의도)이
    통째로 비는 경로다.
    """
    from app.config import Settings

    # ⚠️ `conftest.py` 가 `DISABLED_PROVIDERS=""` 를 심어 테스트를 환경에서
    #    떼어놓는다. 그래서 인스턴스가 아니라 **기본값 자체**를 본다.
    default = Settings.model_fields["disabled_providers"].default
    names = {x.strip() for x in default.split(",") if x.strip()}
    assert "groq" not in names and "gemini" not in names, default
    # 사용자 결정(2026-08-28)은 그대로다 — 이 둘은 충전하지 않는다.
    assert names == {"grok", "perplexity"}, default
