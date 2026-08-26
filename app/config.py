"""pydantic-settings 기반 설정. 키 부재 → 해당 모듈 mock 플래그 True."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # API 키 — 없으면 해당 모듈은 mock_data/ 목 모드로 동작한다.
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None  # 쿼터 소진 등 운영 알림 수신 채팅
    anthropic_api_key: str | None = None
    pplx_api_key: str | None = None
    xai_api_key: str | None = None
    odds_api_key: str | None = None
    apifootball_key: str | None = None
    football_data_key: str | None = None  # football-data.org (메이저 12개 대회 무료)

    # Perplexity 엔드포인트/모델 — Sonar Chat Completions는 2026-09-27 종료.
    # Agent API 전환은 코드 수정 없이 .env만으로 가능하도록 config로 분리한다.
    # (chat) POST {base}{path} {"model": ..., "messages": [...]}
    # (agent) POST {base}{agent_path} {"preset": ..., "input": "..."}
    pplx_api_mode: str = "chat"                    # chat | agent
    pplx_base_url: str = "https://api.perplexity.ai"
    pplx_chat_path: str = "/chat/completions"
    pplx_agent_path: str = "/v1/agent"
    pplx_model: str = "sonar-pro"                  # chat 모드 모델명
    pplx_agent_preset: str = "medium"              # agent 모드 프리셋(fast|low|medium|high|xhigh)

    # Perplexity 레이트리밋 방어 — 동시 실행/최소 간격/429 백오프
    pplx_max_concurrency: int = 2
    pplx_min_interval: float = 1.5                 # 요청 간 최소 간격(초)

    # 모델 ID
    judge_model: str = "claude-opus-4-6"
    report_model: str = "claude-sonnet-5"
    intent_model: str = "claude-haiku-4-5"
    grok_model: str = "grok-4.3-latest"

    # 인프라
    database_url: str = "postgresql://analyst:analyst@localhost:5432/analystbot"
    redis_url: str = "redis://localhost:6379"

    # 전 모듈 강제 목 모드 (테스트/데모)
    force_mock: bool = False

    # ── 승률 판정 (2026-08-25 철학 교체: 시장 배제, 경기력만) ──────────────
    # p_final = w_model*p_model + w_claude*p_claude. **시장 가중치 0**.
    # 배당은 "이기면 얼마 받는가" 계산·표시에만 쓰고 승률 추정에 넣지 않는다.
    ensemble_w_model: float = 0.50
    ensemble_w_claude: float = 0.50
    ensemble_w_market: float = 0.00      # 판정 미사용 (참고 표기·병렬 채점용으로만 보존)

    # 병렬 채점용 기존(시장 반영) 앙상블 가중치 — 어느 방식이 맞히는지 비교한다
    legacy_w_model: float = 0.45
    legacy_w_market: float = 0.30
    legacy_w_claude: float = 0.25

    # 추천 자격: 승률 하한 AND 배당 하한 (EV 기준 폐기)
    # 주의: 0.58 × 1.60 = 0.928 → EV -7.2%. 승률 58%의 손익분기 배당은 1.724다.
    min_win_prob: float = 0.58
    min_odds: float = 1.55            # 1.60 → 1.55 (0.01 미달 탈락이 잦아 완화)
    # ── §0 시스템 상수 — 물리적 한계 (임의 완화 금지, docs/MODEL.md 참조) ──
    # 근거: 운의 비중 연구 MLB 27.8% / EPL 31.4%. 완벽한 정보를 가져도 MLB 단일 경기
    # 예측 상한은 약 72%이며, 학계 최고 모델 정확도는 61.77%(Wharton)다.
    # 우리 상한은 그보다 보수적으로 잡는다. 이를 넘는 값은 '강한 픽'이 아니라 계산 오류다.
    max_win_prob_mlb: float = 0.68
    min_win_prob_mlb: float = 0.32
    max_win_prob_soccer: float = 0.72
    min_win_prob_soccer: float = 0.10   # 3-way라 원정 승 확률은 낮게 나올 수 있다
    # 세계 최고 조직(Starlizard, 분석가 200명)의 시장 대비 엣지가 1~2%다.
    # 5% 초과는 우리가 더 똑똑한 게 아니라 데이터가 틀린 것이다.
    max_edge_vs_market: float = 0.05
    prob_cap_alert_n: int = 3         # 하루 이만큼 초과하면 "모델 점검 필요" 경고

    # 하위호환 별칭 (기존 호출부)
    @property
    def prob_cap_mlb(self) -> float:
        return self.max_win_prob_mlb

    @property
    def prob_cap_soccer(self) -> float:
        return self.max_win_prob_soccer

    # 원정 비대칭 ([4]) — 분데스리가 연구: 홈 승 ROI +10~15%, 원정 -17%
    away_prob_penalty: float = 0.05   # 원정 픽은 승률 임계를 이만큼 높게 적용

    # ── 기대득점(λ) 모델 계수 ([2][3]) ──────────────────────────────────
    league_runs_per_game: float = 4.40    # MLB 팀당 평균 득점
    league_woba: float = 0.320            # 리그 평균 wOBA
    league_obp: float = 0.318             # 리그 평균 OBP
    league_era: float = 4.20              # 리그 평균 ERA/FIP 계열
    league_iso: float = 0.160             # 리그 평균 ISO (장타력)
    exp_iso: float = 0.60                 # ISO 계수 지수 (OBP 보조)
    # [1-7] 결장의 λ 반영 — 핵심 타자 -2%, 최다 기여자 -4%, 마무리 결장 시 상대 λ +2%
    absence_hitter: float = 0.02
    absence_top_hitter: float = 0.04
    absence_reliever: float = 0.02
    absence_cap: float = 0.10             # 결장 누적 보정 상한
    # 계수 지수와 클램프 — 단일 요인이 λ를 지배하지 않도록 폭을 제한한다.
    # 선발 한 명이 팀 기대득점을 ±35% 흔든다는 계산은 현실과 맞지 않는다.
    exp_offense: float = 1.20             # 타선 계수 지수 (Wharton: 타선 영향이 크다)
    exp_pitcher: float = 0.50             # 선발 억제 계수 지수
    off_coef_min: float = 0.82
    off_coef_max: float = 1.22
    pit_coef_min: float = 0.85
    pit_coef_max: float = 1.18
    lam_min: float = 2.80                 # 팀 기대득점 하한 (MLB 현실 범위)
    lam_max: float = 6.20                 # 팀 기대득점 상한
    park_hitter: float = 1.06             # 타자친화 구장 (수치 미수집 시 폴백)
    park_pitcher: float = 0.94            # 투수친화 구장
    weather_temp_per_deg: float = 0.004   # 기온 1도당 득점 계수
    weather_wind: float = 0.03            # 맞바람/뒷바람 계수
    bullpen_short_start: float = 0.05     # 상대 선발 5이닝 미만 → 득점 기대 상향
    bullpen_overuse_runs: float = 0.04    # 상대 불펜 과소모 → 득점 기대 상향
    home_run_edge: float = 0.03           # 홈 득점 이점 (야구)
    f5_share: float = 0.55                # 5이닝까지의 득점 비중 (5/9 근사)
    league_goals_per_team: float = 1.40   # 축구 팀당 평균 득점
    home_goal_edge: float = 0.10          # 홈 득점 이점 (축구)
    score_dispersion: float | None = None # 과분산 관찰 시 음이항 r 값 (None=포아송)
    signal_green_prob: float = 0.62      # 🟢 승률 하한 (배당 하한은 min_odds 공용)

    # ── 경기력 승률 조정 계수 (%p 단위, [1-2]) ────────────────────────────
    adj_starter_era_per_run: float = 0.03    # 선발 최근 5경기 ERA 차 1.00당 ±3%p
    adj_starter_era_cap: float = 0.09        # 선발 매치업 보정 상한 ±9%p
    adj_short_start: float = 0.02            # 최근 평균 5이닝 미만 → -2%p
    adj_key_batter_out: float = 0.02         # 주전 타자 결장 1명당 -2%p
    adj_top_batter_out: float = 0.04         # 팀 최다 득점 기여자면 -4%p
    adj_key_reliever_out: float = 0.02       # 마무리·셋업 결장 1명당 -2%p
    adj_bullpen_overuse: float = 0.03        # 최근 3일 불펜 과소모 -3%p
    adj_form_hot: float = 0.02               # 최근 5경기 4승 이상 +2%p
    adj_form_cold: float = 0.02              # 최근 5경기 4패 이상 -2%p
    adj_home_mlb: float = 0.03               # 홈 이점 (야구)
    adj_home_soccer: float = 0.05            # 홈 이점 (축구)
    adj_absence_cap: float = 0.12            # 결장 관련 누적 보정 상한

    # 리포트 모드: live_conservative(운영 보수) | research(연구·전량 표시)
    report_mode: str = "live_conservative"
    bankroll_krw: int = 1_000_000   # 플랫 스테이크 원화 환산 기준 자금
    weekly_stop_loss_pct: float = 0.05  # 주간 손절선 (자금 대비)
    report_banner: str = ""         # 비상 배너 (예: EV 점검 중) — 비면 미표시

    ev_threshold: float = 0.05      # 이 이상 EV일 때만 추천 픽 (기준 EV +5%↑)
    kelly_fraction: float = 0.5     # 하프 켈리
    kelly_cap: float = 0.05         # 뱅크롤 5% 상한
    # 리포트 캐시. 프리페치가 만든 결과를 사용자가 물어볼 때까지 보관한다.
    # 30분이었을 때: 04:00 프리페치 → 04:30 소멸 → 06:48 요청이 전 과정을
    # 다시 돌아 53.9초가 걸렸다(실사고 2026-08-26). 38분과 API 비용을 들여
    # 만든 결과물이 사용자가 묻기 전에 사라지는 구조였다.
    # 신선도는 TTL이 아니라 신선도 게이트·라인업 폴링·속보 재판정이 담당한다.
    report_cache_ttl: int = 43200   # 12시간 (프리페치 2회 간격을 덮는다)

    # statsapi.mlb.com은 무키 API — 강제 목 모드일 때만 목으로 동작
    @property
    def mock_mlb(self) -> bool:
        return self.force_mock

    @property
    def mock_odds(self) -> bool:
        return self.force_mock or not self.odds_api_key

    @property
    def mock_football(self) -> bool:
        return self.force_mock or not self.apifootball_key

    @property
    def mock_perplexity(self) -> bool:
        return self.force_mock or not self.pplx_api_key

    @property
    def mock_grok(self) -> bool:
        return self.force_mock or not self.xai_api_key

    @property
    def mock_judge(self) -> bool:
        return self.force_mock or not self.anthropic_api_key

    def log_mock_status(self) -> None:
        for name in ("mlb", "odds", "football", "perplexity", "grok", "judge"):
            mode = "MOCK" if getattr(self, f"mock_{name}") else "LIVE"
            logger.info("module %-10s -> %s", name, mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()
