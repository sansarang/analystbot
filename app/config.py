"""설정. 🔴 **유료 API 키가 없다**(§14-13).

Anthropic · Gemini 유료 · Perplexity · API-Football 은 이 표에 자리가 없다.
키를 지우는 것은 사용자 몫이지만, 코드가 그 키를 **읽지 않으면** 호출이 0건이다.
"""
from __future__ import annotations

import logging
import os
import pathlib
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger(__name__)

#: 🔴 `.env` 를 **읽는다.** 파일이 있어도 부르는 곳이 없으면 안 읽힌다 —
#   실측 2026-09-27: `.env` 에 `GOOGLE_CSE_CX` 를 넣었는데 봇이 못 봤다.
#   `.env.example` 이 그것을 설정하라고 하는데 읽는 코드가 0곳이었다.
#   ⚠️ **이미 있는 환경변수를 덮지 않는다** — 컨테이너·`railway run` 이 주입한
#      값이 파일보다 세다(그쪽이 운영이다).
_ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"


def load_env(path: pathlib.Path | None = None) -> int:
    """`.env` → 환경변수. 반환은 **새로 넣은 개수**다(0이면 그렇게 보인다)."""
    path = path or _ENV
    if not path.is_file():
        return 0
    try:
        from dotenv import dotenv_values
    except ImportError:                       # 의존이 없어도 크래시하지 않는다
        logger.warning("[config] python-dotenv 가 없다 — .env 를 못 읽는다")
        return 0
    n = 0
    for k, v in (dotenv_values(path) or {}).items():
        if v is not None and k not in os.environ:
            os.environ[k] = v
            n += 1
    logger.info("[config] .env 에서 %d개 읽었다", n)
    return n


load_env()

#: v3 §13 소스 지도가 다루는 리그. 🔴 요청받은 리그·날짜만 슬레이트에 넣는다(§14-9).
#
#  ⚠️ **사용자 지시 2026-10-01** 로 종목이 늘었다(야구·축구·하키). §9 단계 9 는
#     `KBO·NPB·MLB·K리그·해외축구` 만 이름을 댔다 — 하키는 v4 에 없는 확장이다.
#     → `docs/fable/questions/2026-10-01_five_sports.md`
#  🔴 **농구·배구는 없다.** 무료 일정 소스를 못 찾았다(실측 2026-10-01):
#     NBA 두 경로 ReadTimeout · 배구는 일정 API 자체가 없다. 있는 척하지 않는다.
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **축구 하나만 한다** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > **종목은 축구 하나로 한다 ... 불필요한거 다 지워라** · **지워라** ·
#  > **축구외에는 전부 삭제**
#
#  ⚠️ 종전 — `("KBO", "NPB", "MLB", "해외축구", "NHL")`(사용자 지시 2026-10-01
#     *"야구 축구 하키 농구 배구"*). 🔴 그 지시는 **오늘 지시가 덮는다.**
#  🔴 어댑터도 지웠다(`collect/mlb·npb·nhl·kbo.py` 2,598줄) — 설정이
#     *"모은다"* 고 적고 코드가 없는 꼴(CLAUDE.md #2)을 만들지 않는다.
LEAGUES_AUTO = ("해외축구",)

#: 🔴 **슬레이트를 며칠치 쌓나.** 사용자 지시 2026-10-01: *"당일 날짜 및 그다음
#   날짜 터울은 하루"* — 오늘과 내일을 저장해 두어야 질문에 **바로** 답한다.
SLATE_DAYS = 2
#: 🔴 **축구만**(2026-10-18) — 종전엔 야구 `CPBL` 이 섞여 있었다
LEAGUES_ON_REQUEST = ("K리그1", "EPL", "라리가", "세리에A", "분데스")


@dataclass(frozen=True)
class Settings:
    #: 🔴 기본값이 **존재하지 않는 DB**(`analyst`)를 가리키고 있었다 —
    #   compose 가 만드는 것은 `analystbot` 이다(실측 2026-09-29). 기본값으로
    #   돌린 적이 없어 아무도 몰랐다.
    #   ⚠️ `analystbot_legacy_v14` 는 v1.4 잔재이고 **코드가 읽지 않는다**
    #      (배당 research 격리 · 계약이 그 이름 0건을 잠근다).
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL",
        "postgresql://analyst:analyst@localhost:5432/analystbot"))
    redis_url: str | None = field(default_factory=lambda: os.getenv("REDIS_URL"))

    telegram_bot_token: str | None = field(default_factory=lambda: os.getenv(
        "TELEGRAM_BOT_TOKEN"))
    telegram_admin_chat_id: str | None = field(default_factory=lambda: os.getenv(
        "TELEGRAM_ADMIN_CHAT_ID"))

    # 🔴 LLM 은 여기 하나다 (§17-a)
    ollama_base_url: str = field(default_factory=lambda: os.getenv(
        "OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv(
        "OLLAMA_MODEL", "qwen3:8b"))

    # 무료 티어만 (§14-13 예외: football-data.org 는 무료다)
    football_data_key: str | None = field(default_factory=lambda: os.getenv(
        "FOOTBALL_DATA_KEY"))

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **Solar(Upstage)** — v5 §0 이 유료 0건 규칙을 **하나만** 열었다
    # ══════════════════════════════════════════════════════════════════
    #
    #  v5 §0: *"「유료 API·MCP·커넥터 0건」은 **Upstage Solar API 하나만** 예외로
    #  바꾼다. 다른 유료 서비스는 여전히 0건이다."*
    #
    #  🔴 §2: *"키는 로컬 `.env` 에만 둔다. 이름은 `.env.example` 에만(값 금지)."*
    #  ⚠️ **없으면 목 모드다** — 키 부재로 크래시하지 않는다(이 파일의 규율).
    #  🔴 한도·단가·모델은 **여기 없다** — `config/llm.yaml` 이다(§2 *"값은 거기
    #     두고 사용자만 바꾼다"*). 같은 수를 두 곳에 적으면 한쪽이 늘 늦는다.
    upstage_api_key: str | None = field(default_factory=lambda: os.getenv(
        "UPSTAGE_API_KEY"))

    #: 🔴 v5-A §2 — DeepSeek 키. ⚠️ 없으면 `deepseek_unavailable` 이고
    #   **크래시하지 않는다**(M45).
    deepseek_api_key: str = field(default_factory=lambda: os.getenv(
        "DEEPSEEK_API_KEY", ""))

    #: 🔴 발송 스위치는 **사용자만** 켠다. 기본은 꺼짐이다.
    send_enabled: bool = field(default_factory=lambda: os.getenv(
        "SEND_ENABLED", "").lower() in ("1", "true", "yes"))

    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 게이트 2 — §3 에이전트 스위치**
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 켜면 **Solar 비용이 발생한다**(§2 예산: 경기당 입력 150k·출력 20k ·
    #     하루 $3 · 월 $40). 🔴 그래서 **코드가 혼자 켜지 않는다.**
    #  🔴 사용자 지시 2026-10-04: *"게이트2 켜라 에이전트 돌려봐라"* →
    #     `.env` 에 `AGENT_ENABLED=true` 를 넣었다.
    #  ⚠️ 키가 없으면 켜도 안 돈다(`solar_ready` 가 먼저 막는다) — 그때
    #     크래시하지 않고 사유만 남긴다.
    agent_enabled: bool = field(default_factory=lambda: os.getenv(
        "AGENT_ENABLED", "").lower() in ("1", "true", "yes"))

    slate_leagues: tuple[str, ...] = LEAGUES_AUTO

    @property
    def mock_mode(self) -> bool:
        """키가 없으면 목 모드다 — **키 부재로 크래시하지 않는다.**"""
        return not self.telegram_bot_token

    @property
    def deepseek_ready(self) -> bool:
        """🔴 v5-A §2 — DeepSeek 키가 있나. ⚠️ **스위치와 다르다**.

        🔴 키가 있어도 `llm.yaml` 의 `deepseek.enabled` 가 꺼져 있으면 **안
           돈다** — 켜는 것은 §5 측정 뒤 사용자 승인이다.
        """
        return bool((self.deepseek_api_key or "").strip())

    @property
    def solar_ready(self) -> bool:
        """🔴 Solar 에이전트를 돌릴 수 있나(v5 §2). ⚠️ 없으면 `llm_unavailable`."""
        return bool((self.upstage_api_key or "").strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
