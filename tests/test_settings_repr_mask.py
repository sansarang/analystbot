"""[SEC-2] `Settings` 를 찍으면 **모든 비밀이 평문으로** 나온다.

🔴 **실사고 2026-09-09 (내가 냈다).** 운영 설정을 확인하려고
       for k in (...): print(k, getattr(s, k))
   를 돌렸는데 그중 `deepsearch_enabled` 가 **메서드**였다. 바운드 메서드의
   repr 에 `Settings(...)` 전체가 딸려 나왔고, 세션 출력에 이것이 평문으로 찍혔다:
       TELEGRAM_BOT_TOKEN · ANTHROPIC_API_KEY · PPLX_API_KEY · XAI_API_KEY
       ODDS_API_KEY · GROQ_API_KEY · GEMINI_API_KEY · APIFOOTBALL_KEY
       FOOTBALL_DATA_KEY · DATABASE_URL(비번) · REDIS_URL(비번)
   **오늘 회전하고 옛 키를 폐기한 그 키들이 다시 노출됐다.**

⚠️ **내 프로브만의 문제가 아니다.** 예외 문자열·디버그 로그·`repr(s)` 어디든
   이 객체가 찍히면 전부 샌다. FINDINGS `S-1`·`LLM-2`(키가 평문으로 Redis 에
   남는다)와 같은 뿌리다 — 가리는 장치(`app/secrets_mask.py`)는 이미 있는데
   **설정 객체 자신에는 물려 있지 않았다.**

⚠️ **가리되 진단은 남긴다** (`secrets_mask` 의 설계 원칙 그대로).
   모델명·provider·상한 같은 운영값은 그대로 보여야 한다 — 다 가리면
   아무도 이 repr 을 안 쓰게 되고, 그러면 다시 `getattr` 로 훑는다.
"""
from __future__ import annotations

import re

SECRET_FIELDS = ("telegram_bot_token", "anthropic_api_key", "pplx_api_key",
                 "xai_api_key", "odds_api_key", "groq_api_key", "gemini_api_key",
                 "football_data_key", "database_url", "redis_url")

#: ⚠️ **자격증명이 있는 URL만** 비밀이다. 로컬 `redis://localhost:6379` 는
#   가릴 것이 없고, 그것까지 가리면 `pplx_base_url` 같은 진단값도 사라진다.
#   그래서 값 자체가 비밀인지 `secrets_mask` 에 물어보고 판단한다(사본 금지).
def _is_secret(name, value):
    from app.secrets_mask import is_secret_field

    return is_secret_field(name, value)


def _s():
    from app.config import get_settings

    return get_settings()


def test_repr_에_비밀이_평문으로_없다():
    s = _s()
    blob = repr(s)
    for f in SECRET_FIELDS:
        v = getattr(s, f, None)
        if not v or len(str(v)) < 8 or not _is_secret(f, v):
            continue
        assert str(v) not in blob, f"{f} 가 repr 에 평문으로 있다"


def test_str_도_마찬가지다():
    s = _s()
    blob = str(s)
    for f in SECRET_FIELDS:
        v = getattr(s, f, None)
        if v and len(str(v)) >= 8 and _is_secret(f, v):
            assert str(v) not in blob, f"{f} 가 str 에 평문으로 있다"


def test_메서드_repr_로도_새지_않는다():
    """🔴 실제 사고 경로 — 바운드 메서드의 repr 이 self 를 통째로 찍는다."""
    s = _s()
    blob = repr(s.deepsearch_enabled)
    for f in SECRET_FIELDS:
        v = getattr(s, f, None)
        if v and len(str(v)) >= 8 and _is_secret(f, v):
            assert str(v) not in blob, f"{f} 가 메서드 repr 로 샌다"


def test_운영값은_그대로_보인다():
    """⚠️ 다 가리면 아무도 안 쓴다 — 진단에 필요한 것은 남는다."""
    blob = repr(_s())
    for keep in ("gemini-3.7-flash", "min_win_prob", "deepsearch_sports"):
        assert keep in blob, f"{keep} 까지 가렸다 — 마스킹이 너무 넓다"


def test_비밀_필드는_길이만_남긴다():
    """가린 자리에 '무엇이 있었는지'는 남아야 진단이 된다."""
    s = _s()
    blob = repr(s)
    if getattr(s, "groq_api_key", None):
        assert "groq_api_key" in blob, "필드 이름까지 지우면 안 된다"
        assert re.search(r"groq_api_key=[^,)]*가림", blob), \
            f"가림 표기가 없다: {blob[blob.find('groq_api_key'):][:60]}"


def test_자격증명이_있는_URL은_가린다():
    """⚠️ 로컬은 `redis://localhost:6379` 라 가릴 것이 없다 — 운영 형태로 잠근다."""
    from app.secrets_mask import is_secret_field, mask_field

    prod = "redis://default:pqLEfWJhUzi@redis.railway.internal:6379"
    assert is_secret_field("redis_url", prod)
    assert "pqLEfWJhUzi" not in mask_field("redis_url", prod)
    # 자격증명이 없으면 그대로 — 진단값을 지우지 않는다
    assert mask_field("redis_url", "redis://localhost:6379") == "redis://localhost:6379"
    assert mask_field("pplx_base_url", "https://api.perplexity.ai") == "https://api.perplexity.ai"
