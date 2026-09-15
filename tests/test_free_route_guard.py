"""[4번 2026-09-04 · BUD-1 2026-09-11] 무엇이 유료인지 잠근다.

🔴 [BUD-1 2026-09-11] **정책이 바뀌었다.** 2026-09-04 의 "완전 무료" 지시는
   2026-09-11 유료 전면 전환(gemini 주전 · xai 폴백)으로 대체됐다.
   그래서 계약도 둘로 갈린다:
     · 무엇이 유료인가 — 판정은 그대로 잠근다(오히려 더 엄격해졌다)
     · 유료 후보를 어떻게 다루는가 — **배제가 아니라 토큰 상한**이다
   종전 구현은 독스트링이 "확실하지 않으면 False" 라고 적어 놓고 **모르는
   provider 를 전부 무료로 통과**시켰다. 그래서 gemini·xai 가 무료로 분류돼
   상한이 걸리는 경로가 Anthropic 하나뿐이었다.

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
    # 🔴 [BUD-1] 여기가 통째로 뒤집힌 자리다. 이 둘이 True 였다.
    # 🔴 [CHN-1 2026-09-15] gemini = AI Studio 무료 티어 키 → 무료로 분류.
    ("gemini", "gemini-3.5-flash-lite", True),
    ("처음보는provider", "m", False),          # 모르면 여전히 유료(BUD-1)
    ("xai", "grok-4.3-latest", False),
    # 모르는 provider 는 **유료로 본다** — 독스트링이 원래 약속한 방향이다.
    ("whoknows", "some-model", False),
])
def test_is_free(provider, model, expected):
    assert is_free(provider, model) is expected


@pytest.mark.parametrize("provider,paid", [
    ("gemini", False), ("xai", True), ("anthropic", True), ("deepseek", True),
    ("groq", False), ("nvidia", False), ("ollama", False), ("mock", False),
    ("", True), ("처음보는것", True),          # 모르면 유료
])
def test_is_paid_provider(provider, paid):
    """상한을 태울지 말지가 여기서 갈린다. **모르면 유료**다."""
    from app.llm.judge_route import is_paid_provider

    assert is_paid_provider(provider) is paid


def test_paid_candidate_stays_in_the_chain_and_is_capped(monkeypatch):
    """🔴 [BUD-1] 운영 사슬이 유료다 — 배제하면 판정이 통째로 0건이 된다.

    2026-09-11 운영값은 `gemini/…,xai/…` 였다. 종전 구현은 이 둘을 "무료"로
    착각해 통과시켰고, 지금은 **유료인 줄 알면서** 통과시킨다. 차이는 토큰
    상한이 붙는다는 것이다.
    🔴 [CHN-1 2026-09-15] gemini 가 무료 티어 키로 옮겨졌으므로(FREE_PROVIDERS)
       유료 예시를 `deepseek/xai` 로 바꾼다. **재는 것은 그대로다** —
       "유료라도 사슬에 남고, 남는 대신 상한이 붙는다".
    """
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "deepseek")
    monkeypatch.setenv("JUDGE_CHAIN",
                       "deepseek/deepseek-r1,xai/grok-4.3-latest")
    try:
        got = chain("matchup")
    finally:
        get_settings.cache_clear()
    assert got == [("deepseek", "deepseek-r1"), ("xai", "grok-4.3-latest")], got
    assert all(not is_free(p, m) for p, m in got), "유료인 줄 알고 태워야 한다"


def test_paid_candidate_is_dropped_in_free_only_mode(monkeypatch):
    """무료 전용으로 되돌리는 길 — 설정 한 줄이다 (2026-09-04 정책)."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "nvidia")
    monkeypatch.setenv("PAID_LLM_ALLOWED", "0")
    monkeypatch.setenv("JUDGE_CHAIN",
                       "nvidia/nvidia/nemotron-3-ultra-550b-a55b,"
                       "openrouter/deepseek/deepseek-r1,"
                       # 🔴 [CHN-1 2026-09-15] 유료 예시를 gemini → xai 로.
                       #    gemini 는 무료 티어 키로 옮겨졌다(FREE_PROVIDERS).
                       "xai/grok-4.3-latest,"
                       "openrouter/minimax/minimax-m3:free")
    try:
        got = chain("matchup")
    finally:
        get_settings.cache_clear()
    assert ("openrouter", "deepseek/deepseek-r1") not in got
    assert ("xai", "grok-4.3-latest") not in got
    assert ("openrouter", "minimax/minimax-m3:free") in got
    assert got[0] == ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b")
    # 🔴 [2026-09-04] 비상 꼬리를 **떼어냈다.** 잔액 0 이면 캡은 아무것도
    #    지키지 못하고, 그 400 이 종목 전체를 멈춘다(NPB 판정 0건).
    assert "anthropic" not in [p for p, _ in got]


def test_old_env_name_still_works(monkeypatch):
    """개명은 배포와 env 변경을 분리한다 — 옛 이름이 그대로 읽혀야 한다."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JUDGE_PROVIDER", "gemini")
    monkeypatch.delenv("JUDGE_CHAIN", raising=False)
    monkeypatch.setenv("FREE_JUDGE_MODEL", "gemini/gemini-3.7-flash")
    try:
        assert chain("matchup") == [("gemini", "gemini-3.7-flash")]
    finally:
        get_settings.cache_clear()


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
