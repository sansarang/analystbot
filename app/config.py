"""pydantic-settings 기반 설정. 키 부재 → 해당 모듈 mock 플래그 True."""

import logging
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        populate_by_name=True,
    )

    # ── [SEC-2 2026-09-09] **찍어도 비밀이 안 새게 한다** ─────────────────
    #   🔴 실사고: `getattr(s, "deepsearch_enabled")` 가 메서드라 바운드 메서드
    #      repr 에 `Settings(...)` 전체가 딸려 나왔고 키 11종이 평문 노출됐다.
    #      예외 문자열·디버그 로그·프로브 어디로든 이 객체는 흘러간다.
    #   ⚠️ **값 접근은 그대로다** — 가리는 것은 표시뿐이고 동작은 안 바뀐다.
    #   ⚠️ 규칙은 `app/secrets_mask.py` 가 원본이다(사본 금지). 여기서는
    #      필드를 훑어 그 함수에 넘기기만 한다.
    def __repr__(self) -> str:
        from app.secrets_mask import mask_field

        parts = []
        for name in type(self).model_fields:
            try:
                v = getattr(self, name)
            except Exception:
                continue
            parts.append(f"{name}={mask_field(name, v)!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    __str__ = __repr__

    # API 키 — 없으면 해당 모듈은 mock_data/ 목 모드로 동작한다.
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None  # 쿼터 소진 등 운영 알림 수신 채팅
    anthropic_api_key: str | None = None
    pplx_api_key: str | None = None
    xai_api_key: str | None = None
    odds_api_key: str | None = None
    # [B-2] 추가 LLM provider — 없으면 그 provider는 쓰지 않는다(크래시 금지).
    #  ⚠️ `gemini_api_key` 는 아래 감시 절에 AliasChoices 와 함께 선언돼 있다.
    #     여기에 또 적으면 **뒤가 이겨** 앞은 죽은 줄이 된다(실측). 적지 않는다.
    groq_api_key: str | None = None
    deepseek_api_key: str | None = None
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
    #: [ORD-19 2026-09-12] chat 모드 모델. 🔴 **`sonar` 다.**
    #   실측(운영, 조사 질문 4종 × 2회):
    #     sonar     호출당 $0.00511
    #     sonar-pro 호출당 $0.00724   ← 42% 비싸다
    #   답 품질 차이는 **찾지 못했다** — 8/8 둘 다 실질적으로 답했다(선발 예고
    #   "두산 잭 로그, NC 구창모" · 부상 "4월 전완건염·6월 허리 경련" ·
    #   지붕 "Closed" 전부 양쪽 동일). 비용의 대부분은 토큰이 아니라
    #   **요청료**다(sonar $0.005 · pro $0.006).
    #   ⚠️ 표본 8건이고 내 정답 검사기가 오분류했다("맥스 슈어저"를 "Scherzer"
    #      로 못 찾음). 되돌리려면 `PPLX_MODEL=sonar-pro` 한 줄이다.
    #   ⚠️ 절감액 자체는 작다 — 월 약 $1.7. x_search 가 호출당 $0.16 이라
    #      32배 차이다. 큰 절감은 경기당 1콜 캡(5단계 배선)이다.
    pplx_model: str = "sonar"
    pplx_agent_preset: str = "medium"              # agent 모드 프리셋(fast|low|medium|high|xhigh)

    # Perplexity 레이트리밋 방어 — 동시 실행/최소 간격/429 백오프
    pplx_max_concurrency: int = 2
    pplx_min_interval: float = 1.5                 # 요청 간 최소 간격(초)

    # 모델 ID
    judge_model: str = "claude-opus-4-6"
    report_model: str = "claude-sonnet-5"
    intent_model: str = "claude-haiku-4-5"
    grok_model: str = "grok-4.3-latest"
    # 야구 폼·매치업. Judge(--old)는 judge_model을 그대로 쓴다.
    # 팀 분석 = 요약·태그 분류 → Haiku. 매치업 = 4자료 교차·규칙 준수 → Sonnet.
    team_form_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("MODEL_TEAM_FORM", "team_form_model"),
    )
    # ─────────────── 감시 3층 (v1.3-monitor) ───────────────
    #: 🔴 **감시는 판정을 건드리지 않는다.** 전부 판정 산출물이 저장된 뒤에
    #   읽는 별도 경로다. 여기 상수는 감시층만 쓴다.
    #: L1 사실 감시 활성. 끄면 훅이 즉시 반환한다(카드 바이트 불변).
    fact_audit_enabled: bool = Field(default=True, validation_alias=AliasChoices(
        "FACT_AUDIT_ENABLED", "fact_audit_enabled"))
    #: 계산값(평균 등) 재계산 허용 오차. 이보다 크면 mismatch 후보.
    fact_audit_tolerance: float = 0.05
    #: L2·L3 그림자 패널 — 슬레이트당 대상 상한.
    shadow_max_per_slate: int = Field(default=5, validation_alias=AliasChoices(
        "SHADOW_MAX_PER_SLATE", "shadow_max_per_slate"))
    #: 주심 대비 편차가 이 이상이면 W-PANEL-DIVERGE.
    shadow_diverge_pp: float = 0.08
    #: Gemini — 키가 없으면 L2·L3 전체 휴면.
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices(
        "GEMINI_API_KEY", "gemini_api_key"))
    #: 🔴 `gemini-2.5-flash` 는 **신규 키에 404** 다 (실측 2026-09-03:
    #   "no longer available to new users"). 살아 있는 모델이어야 한다.
    gemini_model: str = Field(default="gemini-3.7-flash",
                              validation_alias=AliasChoices("GEMINI_MODEL",
                                                            "gemini_model"))
    #: 무료 티어 분당 10요청 — 호출 간 최소 간격(초).
    gemini_min_interval_sec: float = 7.0
    # ⚠️ **Gemini 는 사고 토큰이 `maxOutputTokens` 를 잠식한다.** 실측
    #   2026-09-03, L2 검사역 프롬프트(2711자):
    #     2048 → 사고 1964 + 출력 80 = 2044, finish=MAX_TOKENS, **JSON 아닌
    #            잘린 산문**이 나왔다
    #     8192 → 사고 985 + 출력 59, finish=STOP, 정상 JSON
    #   L3(독립 판정)도 사고만 420~1327 이라 종전 512 로는 답이 안 나온다.
    shadow_review_max_tokens: int = 8192
    shadow_judge_max_tokens: int = 4096
    # ── [자료10] 변수 정량화 참조 데이터 (2026-09-03) ──────────────
    #: 1-a 이닝 분포를 볼 등판 수 (구원 포함). 있는 만큼 쓰고 n 을 명기한다.
    var_ref_appearances: int = 10
    #: 선발 등판이 이 수 **미만**이면 "표본 부재형" — 이닝 분포를 붙인다.
    #  ⚠️ `starter_recent.MIN_STARTS`(추천 탈락선)와 **다른 값이다.** 저건
    #     "믿을 수 있나", 이건 "무엇으로 대신 보여줄까"다. 섞지 않는다.
    var_ref_low_start_max: int = 3
    #: 1-b 발동 임계 — 최근 3경기 환산 실점률이 시즌 ERA 와 이만큼 벌어질 때만
    #  계산한다. 전 투수 계산은 프롬프트만 비대하게 만든다.
    var_ref_era_gap: float = 2.00
    #: 1-b 최소 표본. 미만이면 "참조 불충분, n=X" 로 붙이고 **단정하지 않는다.**
    var_ref_min_sample: int = 30
    #: 1-b 리그별 캐시 수명(초). 하루 1회 계산이면 충분하다.
    var_ref_cache_sec: int = 26 * 3600

    # ── [표본 하한 2026-09-07] 얇은 숫자가 결정 변수의 크기를 정하는 것을 막는다 ──
    #
    # 🔴 실측 2026-09-07 (WSH@LAD 리허설): 판정이 결정 변수의 크기를
    #    `자료10 이닝분포 p25(2.0이닝)` 에서 가져왔는데 그 분위수의 표본은
    #    **등판 2건**이었다(`이닝 분포 n=2 선발1 p50=6.0 최장=6.0`).
    #    판정은 "표본 2뿐"이라고 단서까지 달았지만, 표본 2에서 나온 분위수는
    #    어떻게 추론해도 표본 2다.
    #
    #: 분위수(p25/p50/p75)를 낼 최소 등판 수. **미만이면 분위수를 빼고
    #  원시 `이닝` 배열만 남긴다** — 배열은 사실이고 분위수는 추정이다.
    #  값 5의 근거: `quantiles` 는 보간하지 않고 실제 값 하나를 고르므로
    #  n<5 에서는 p50 과 p75 가 **같은 값으로 퇴화**한다(n=2·4 실측).
    #  n=5 에서 처음으로 세 분위수가 서로 다른 순서통계량이 된다.
    var_ref_min_quantile_n: int = 5
    #: 얇은 선발에 붙일 **리그 기준선**의 관측 창(일). 시즌이 아니라 최근 창이다.
    var_ref_league_days: int = 21
    #: 그 기준선의 최소 표본. 미만이면 붙이지 않는다 — 없느니만 못하다.
    var_ref_league_min_n: int = 30

    # ── [자료1 상대 보정 2026-09-07] 누구를 상대로 낸 득점인가 ─────────
    #
    # 🔴 판정은 이미 상대 수준을 **서술로** 보고 있다(실측: "경기당 4.67득점,
    #    상대순위 3~4위"). 없는 것은 그것을 **숫자로 만든 값**이다.
    # ⚠️ 시즌 집계가 아니라 `games` 의 **최근 창**만 쓴다 — 대원칙(집계표 금지).
    #: 상대의 최근 실점률을 볼 경기 수.
    m1_opp_window: int = 5
    #: 상대 표본이 이 수 미만이면 그 경기는 보정에서 뺀다.
    m1_opp_min_games: int = 3

    # ── [자료14 분기점 해결 2026-09-07] 질문을 맞는 해결사에게 보낸다 ────
    #
    # 🔴 실측: deepsearch 기록 6건이 전부 **미확인**이었다. 전부 기록으로
    #    답할 질문("투구수 한도"·"이닝 소화 계획")을 뉴스 검색기에 보낸 탓이다.
    #    같은 질문을 DB 에 물으니 리그 표본 232건짜리 답이 즉시 나왔다.
    #: "깊게 간다"의 기준 이닝. 분기점 대부분이 "선발이 5이닝을 넘기는가"다.
    branch_deep_innings: float = 5.0
    #: 소속팀 선발 관측 창(일).
    branch_team_days: int = 30
    #: 해결사 답의 최소 표본. 미만이면 그 갈래를 싣지 않는다 —
    #  얇은 답으로 얇은 표본을 메우면 자료13 이 무너진 자리로 돌아간다.
    branch_min_n: int = 20
    #: 한 경기에서 풀 분기점 수 상한. 프롬프트를 비대하게 만들지 않는다.
    #: 분기점 + 변수 + 추가확인을 다 받으므로 상한을 조금 올린다.
    branch_max_questions: int = 4

    # ── [C4 변수 대장 2026-09-05] prior 헤더 ─────────────────────────
    #: 🔴 **고정 텍스트다.** 대장 맨 앞에 붙어 "이 숫자들이 무엇인지"를
    #   판정에게 한 번 설명한다. 매 경기 모델이 다시 해석하게 두면 해석이
    #   경기마다 달라지고, 그러면 변수 크기를 비교할 수 없다.
    #   ⚠️ 여기 임계·상한을 적지 않는다 — 그 값들은 각자의 원본이 있다.
    variable_ledger_prior: str = (
        "이 대장의 수치는 **리그 전체에서 관측된 참조값(prior)** 이다. "
        "특정 팀·선수의 누적 성적이 아니라 '이런 상황에서 보통 어떻게 되는가' "
        "이므로 최근 폼 전용 원칙의 예외로 허용된다. "
        "변수의 ±N%p 는 **이 범위 안에서** 고르고, 인용한 항목 이름을 근거에 적어라. "
        "대장에 없는 크기를 지어내지 마라 — 없으면 '근거 없음 — 보수 반영'이다.")

    # ── [시장 기준선] 우리 판정 vs 시장, 사후 전용 (2026-09-04) ──────
    #: 카드 표기용 스냅샷 나이 상한(분). 넘으면 시장 줄을 **안 낸다** —
    #  오래된 배당은 지금 시장이 아니다.
    market_snapshot_max_age_min: int = 90
    #: 시장 동의/이견 라벨 임계(%p). |우리 − 시장| 이 이 값 미만이면 "동의".
    market_divergence_pp: float = 4.0

    # ── [크롤 위생] 공통 클라이언트 (2026-09-04) ─────────────────────
    #: 요청 타임아웃(초)·재시도 횟수·백오프 기준(초).
    crawl_timeout_sec: float = 20.0
    crawl_retries: int = 3
    crawl_backoff_sec: float = 1.5
    #: 조건부 요청 캐시(ETag/Last-Modified) 수명. 소스가 안 바뀌면 304 를
    #  받고 본문을 안 받는다 — 우리도 가볍고 상대 서버도 가볍다.
    crawl_cond_cache_sec: int = 6 * 3600

    # ── [무료 전환 2026-09-04] 판정·폼 provider 라우팅 ───────────────
    #: 판정·폼을 어디로 보낼 것인가. `anthropic` 이면 종전 경로 그대로다.
    #  🔴 **Anthropic 경로를 지우지 않았다.** 이 값 하나로 되돌아온다.
    judge_provider: str = Field(default="anthropic", validation_alias=AliasChoices(
        "JUDGE_PROVIDER", "judge_provider"))
    #: 판정·폼 사슬 (앞이 주전). 형식 "provider/model,provider/model".
    #  🔴 [BUD-1 2026-09-11] `FREE_JUDGE_MODEL` → **`JUDGE_CHAIN`** 으로 개명.
    #     2026-09-11 유료 전환으로 이 사슬은 더 이상 무료가 아니다
    #     (gemini · xai). 이름이 "FREE" 인 채로 두면 다음 사람이 "여긴 공짜"로
    #     읽는다 — 실제로 그 오해가 상한 부재의 뿌리였다.
    #  ⚠️ **옛 이름을 alias 로 남긴다.** 운영 env 를 바꾸지 않아도 그대로
    #     읽히므로, 배포와 env 변경을 분리할 수 있다.
    judge_chain: str = Field(default="", validation_alias=AliasChoices(
        "JUDGE_CHAIN", "judge_chain", "FREE_JUDGE_MODEL", "free_judge_model"))
    form_chain: str = Field(default="", validation_alias=AliasChoices(
        "FORM_CHAIN", "form_chain", "FREE_FORM_MODEL", "free_form_model"))

    #: 🔴 [BUD-1] **유료 후보를 사슬에 허용할 것인가.** 2026-09-11 전환으로
    #   기본 켜짐이다. 끄면 2026-09-04~09-10 의 "무료 전용" 정책으로 한 줄
    #   되돌아간다(유료 후보는 사슬에서 빠진다).
    paid_llm_allowed: bool = Field(default=True, validation_alias=AliasChoices(
        "PAID_LLM_ALLOWED", "paid_llm_allowed"))

    #: 🔴 [BUD-1] 유료 provider 의 **일일 토큰 상한**(provider 당). 넘으면
    #   호출을 막고 `W-LLM-PAID` 로 알린다.
    #   ⚠️ **기본값 0 = 관측만.** 하루치 실측이 없어 숫자를 정할 근거가 아직
    #      없다(추측 금지). 0 인 동안 이 가드는 **세고 보고할 뿐 막지 않는다** —
    #      로그에 "상한 미설정"이 그대로 찍힌다.
    #   ⚠️ 축이 콜이 아니라 토큰인 이유: 역할마다 콜 하나의 크기가 10배 넘게
    #      다르다(판정 15k자 프롬프트 vs 의도 해석 몇 줄).
    token_cap_daily: int = Field(default=0, validation_alias=AliasChoices(
        "TOKEN_CAP_DAILY", "token_cap_daily"))
    #: 🔴 **비상용이 일상용으로 새는 것을 막는 캡.** 하루 이 수를 넘으면
    #   Anthropic 을 부르지 않는다. 폴백 사슬의 마지막이지 기본값이 아니다.
    anthropic_daily_cap: int = Field(default=10, validation_alias=AliasChoices(
        "ANTHROPIC_DAILY_CAP", "anthropic_daily_cap"))
    # [P0 안정성 2026-09-05] 판정 호출에 싣는 고정 seed. 0 이면 보내지 않는다.
    #   ⚠️ `temperature=0` 만으로는 결정적이지 않다 — 대형 MoE 서빙은 배치
    #      구성에 따라 누산 순서가 달라진다. seed 는 최선 노력 장치이고,
    #      실제 효과는 `tools/stability_audition.py` 실측으로 판단한다.
    #      수용 실측(2026-09-05): nvidia·groq·openrouter 전부 200.
    llm_seed: int = Field(default=20260905, validation_alias=AliasChoices(
        "LLM_SEED", "llm_seed"))
    # [상황 변수 2026-09-06] Gemini 검색 그라운딩 — 구글 검색 전체를 눈으로 쓴다.
    #   경기당 1회 고정이고, 하루 총량을 이 캡이 막는다.
    #   기본 60: KBO 5 + NPB 6 + MLB 15 = 26경기 × 1회에 재판정 여유를 더한 값.
    #   ⚠️ Redis 로 센다. 셀 수 없으면(Redis 없음) **부르지 않는다** —
    #      캡 없는 AI 호출을 만들지 않는다.
    grounding_enabled: bool = Field(default=True, validation_alias=AliasChoices(
        "GROUNDING_ENABLED", "grounding_enabled"))
    grounding_daily_cap: int = Field(default=60, validation_alias=AliasChoices(
        "GROUNDING_DAILY_CAP", "grounding_daily_cap"))
    # [변수 평의회 2026-09-06] 상황 태그가 있는 경기만 심의한다.
    #   판정 **앞**에 서므로 시간 예산이 곧 발송 마감선이다 — 슬레이트 상한을
    #   작게 잡는다. 경기당 조사 1 + 심의 1 = 2콜.
    council_enabled: bool = Field(default=True, validation_alias=AliasChoices(
        "COUNCIL_ENABLED", "council_enabled"))
    council_slate_cap: int = Field(default=5, validation_alias=AliasChoices(
        "COUNCIL_SLATE_CAP", "council_slate_cap"))
    council_daily_cap: int = Field(default=20, validation_alias=AliasChoices(
        "COUNCIL_DAILY_CAP", "council_daily_cap"))

    # ── [C1 불펜 가용성] 최근 3일 소모 임계 (2026-09-04) ──────────────
    #: ⚠️ **투구수가 DB 에 없다.** `pitcher_appearances` 는 `batters`(TBF) 만
    #   갖고 있어 이를 대리값으로 쓴다. 통상 타자당 ~4구이므로
    #   30구≈8타자 · 50구≈13타자로 환산했다. 이 환산을 프롬프트에도 적는다.
    bullpen_fatigue_tbf: int = 8       # 이 이상이면 '피로'
    bullpen_spent_tbf: int = 13        # 이 이상이면 '소진'
    bullpen_fatigue_apps: int = 2      # 최근 3일 등판 이 수 이상이면 '피로'
    bullpen_spent_apps: int = 3        # 3연투면 '소진'
    #: 주력 불펜 선정 창(일)과 인원. **선정만** 이 창을 쓰고, 판정 입력은
    #  최근 3일 수치다 — 대원칙(최근 폼 전용)과 충돌하지 않는다.
    bullpen_core_days: int = 14
    bullpen_core_size: int = 5
    #: 불펜 최근 실점을 볼 경기 수.
    bullpen_recent_games: int = 3

    #: 판정 프롬프트 원문 보관 TTL(초). 사실 감시가 **판정 시점의** 원문을
    #  읽어야 한다 — 재렌더하면 그 사이 바뀐 재료를 보게 된다.
    prompt_keep_ttl_sec: int = 24 * 3600

    #: [무과금 전환] SharpAPI 무료 티어 키. **비면 폴백이 조용히 꺼진다.**
    #   계정 발급은 사람이 하는 일이라 코드가 만들 수 없다 — 키가 들어오면
    #   ESPN 실패 시 자동으로 2순위가 붙는다.
    sharpapi_key: str = Field(default="", validation_alias=AliasChoices(
        "SHARPAPI_KEY", "sharpapi_key"))
    #: 배당 소스. `free` = ESPN·SharpAPI·배트맨. `theodds` = 유료 복귀.
    #   ⚠️ The Odds API 코드는 지우지 않았다 — 값만 바꾸면 되돌아간다.
    odds_provider: str = Field(default="free", validation_alias=AliasChoices(
        "ODDS_PROVIDER", "odds_provider"))

    # 🔴 [2026-09-06 사용자 지시] 최종 판정은 **Anthropic Fable** 이 한 번에 낸다.
    #    "마지막 판정은 단 한 번으로 제한하고 안트로픽 fable 로 정해라."
    #    ⚠️ 재시도 없음 — `team_form.complete_json` 이 role="matchup" 이면
    #       1회만 부른다. 같은 재료를 여러 번 물으면 회차마다 답이 달라진다.
    #    🔴 [2026-09-06 사용자 지시] fable → **opus**. "모델을 페이블이 아닌
    #       opus 로 한다." 최종 판정 전용이므로 호출 수는 라인업이 확정된
    #       경기 수(하루 최대 슬레이트 규모)로 묶이고, `ANTHROPIC_DAILY_CAP`
    #       이 그 위에 상한을 건다. 단가는 확인하지 않았다 — 첫 사이클에서
    #       실제 호출 수와 `stop_reason` 을 재고 보고한다.
    matchup_model: str = Field(
        default="claude-opus-5",
        validation_alias=AliasChoices("MODEL_MATCHUP", "matchup_model"),
    )
    team_form_max_tokens: int = 1500
    # 실측 2026-08-29: claude-sonnet-5 adaptive thinking 기본.
    # matchup_max_tokens=1000 이면 사고에 토큰을 다 쓰고 본문 JSON이 잘린다
    # (NPB 4 + MLB 9, parse_fail). 4000은 사고+JSON을 한 응답에 담기 위한 값.
    # 팀 폼(Haiku) 1500은 실패 0이라 유지. 프롬프트·클리핑·게이트는 바꾸지 않는다.
    #: [v1.3 A-3] 4000 → **6000**. **실측 근거**(2026-09-02 KBO 재판정):
    #     output=3789 stop=end_turn   prompt_chars=11692  ✅
    #     output=3661 stop=end_turn   prompt_chars=11805  ✅
    #     output=4000 stop=max_tokens prompt_chars=12068  ❌ 절단 → JSON 파싱
    #                                                        실패 2회 → 판정 탈락
    #   성공이 3661~3789 인데 상한이 4000이라 여유가 200토큰뿐이었다.
    #   자료8(타선 시즌)·자료9(불펜)가 들어오며 근거가 길어져 경계를 넘었다.
    #   ⚠️ 과거 사고: `max_tokens` 16000→32000 임의 상향이 SDK 비스트리밍
    #      거부를 유발해 전 슬레이트 판정이 0건이 됐다. 그래서 **필요한 최소만**
    #      올린다: 실측 최대 성공이 3789 이므로 6000 이면 58% 여유이고,
    #      `deepsearch_max_tokens`(8000) > matchup 불변식도 지킨다 —
    #      딥서치는 기사 본문이 얹혀 출력 여유가 더 필요하다.
    #   절단이 또 나면 `matchup.py` 가 그 호출만 한도를 2배로 올려 1회 재시도한다.
    # 🔴 [2026-09-07] 6000 → 12000. **전개 추가로 출력이 길어졌다.**
    #    실측 — 같은 프롬프트(17,741자)에서 예비 판정이 잘렸다:
    #      [matchup_prelim] gemini 응답이 JSON 이 아니다 (1482자)
    #        앞='{ "전개": { "홈승리경로": "선발 소형준이 최근 5경기…'
    #      → 시작은 정상인데 JSON 이 안 닫혔다. 사고 토큰이 예산을 먹는다
    #        (2026-09-04 폼에서 겪은 것과 같은 유형).
    #    ⚠️ 상한을 올리는 것 자체가 사고였던 적이 있다(SDK 제한에 걸려
    #       전 슬레이트 판정 0건). 그래서 **실측 출력값**으로 정한다:
    #         opus  전개 포함 출력 2,995~3,522 토큰 (4회)
    #         grok  735 · pplx 1,728 · gemini 916~1,024 (max 12000 에서 성공)
    #       Claude 5·grok 모두 출력 상한이 이보다 훨씬 크므로 12000 은
    #       SDK 제한에 닿지 않는다.
    # 🔴 [CHN-1 2026-09-15 사용자 지시] 12000 → **1500**.
    #    "matchup_max_tokens·triage·dbref max_tokens → 1500".
    #    ⚠️ 위 실측들과 **정면으로 부딪친다** — 2000 에서 4/4 파싱 실패였다.
    #       그래서 내린 직후 실제 판정 크기로 재고, 절단이 나면 그 수치를 들고
    #       되돌린다(그 측정이 이 값의 근거다).
    matchup_max_tokens: int = 1500

    # ── [A-5단계] 리그별 딥서치 스위치 ─────────────────────────────────────
    # 콤마 구분 종목 목록. 여기 없는 종목은 **딥서치를 부르지 않는다.**
    #   KBO·NPB는 크롤링으로 완전 대체됐다(2026-08-27): 공식 기록실·네이버·
    #   Yahoo·1군 공시·경기 전 기사. 딥서치 콜이 5 → 0이 됐다.
    #   MLB도 같다(2026-08-28): statsapi·Statcast. 전문가 픽·Odds 없음.
    #   유럽축구는 전문가 픽이 웹에 흩어져 있어 검색이 필요하다.
    # ⚠️ 이 값을 비우면 전 종목에서 딥서치가 꺼진다 — 의도한 경우에만 그렇게 하라.
    deepsearch_sports: str = "soccer"
    #: [v1.1 6단계] 하루 딥서치 발동 상한 = 슬레이트의 이 비율.
    #   비용·외부 의존이 걸린 단계라 상한을 코드가 아니라 설정으로 둔다.
    deepsearch_daily_cap: float = 0.30
    #: 경기당 검색 횟수 상한. API의 max_uses 로도 강제한다.
    deepsearch_max_searches: int = 5
    #: 한 경기 조사에 허용하는 시간(초). 넘으면 폴백(조사 없이 원판정 유지).
    #   ⚠️ 검색 결과가 입력에 얹혀 프롬프트가 커진다 — 실측 2026-08-31:
    #      검색 2회에 입력 25,308토큰. 90초는 빠듯해 120초로 둔다.
    deepsearch_timeout_sec: int = 120
    #: 조사 응답의 출력 예산. **판정(4000)보다 커야 한다.**
    #   web_search 는 한 번의 API 호출 안에서 검색-읽기를 여러 턴 돌고, 그
    #   중간 서술이 전부 출력 토큰을 먹는다. 마지막에 나오는 JSON까지 가기
    #   전에 예산이 끝나면 본문이 문장 중간에서 잘린다.
    #   실측 2026-09-01: 2000 → stop_reason="max_tokens", output 5804토큰,
    #   JSON이 743자에서 절단. 4/4 파싱 실패의 원인이었다.
    # [2026-09-07] matchup 12000 상향에 맞춰 불변식 유지 —
    #   딥서치는 기사 본문이 얹혀 **매치업보다 커야 한다**(실측 소진 5,804).
    # 🔴 [CHN-1 2026-09-15] 16000 → 1500 (같은 지시).
    deepsearch_max_tokens: int = 1500
    #: [무과금 전환 2c] 유료 `web_search` 폴백의 **하루 총량**.
    #   RSS 에 기사가 0건일 때만 쓴다. 0 이면 유료 검색을 아예 안 한다.
    #   ⚠️ 경기당 상한(`deepsearch_max_searches`)과 다른 축이다 —
    #      이건 하루 전체를 잠근다.
    deepsearch_paid_cap: int = Field(default=3, validation_alias=AliasChoices(
        "DEEPSEARCH_PAID_CAP", "deepsearch_paid_cap"))
    #: [v1.1 6단계] **조사 호출** 켜기. 기본 꺼짐(False).
    #   트리거 판별·상한·기록·폴백은 이 값과 무관하게 항상 돈다 —
    #   실전에서 "어떤 경기가 조사 대상이 되는가"를 먼저 관찰하기 위해서다.
    #   web_search 서버 도구가 이 API 키에서 확인되면 그때 켠다
    #   (실측 2026-08-31: 모델이 "검색 도구 접근 불가"로 응답, 90초 타임아웃).
    deepsearch_investigate: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEEPSEARCH_ENABLED", "deepsearch_investigate"))

    #: [DS-7 2026-09-10] 슬레이트 딥서치 동시 실행 수. 조사는 대부분 외부 I/O
    #   대기라 순차로 돌면 프리페치가 길어져 발송 창(T-30)을 침범한다
    #   (실측: 전 경기 조사로 13분 32초 → W-SEND-PENDING 경보).
    #   ⚠️ 무한정 올리지 않는다 — 무료 LLM 은 레이트리밋(groq TPD)이 있고
    #      한꺼번에 쏟으면 그 한도에 더 빨리 닿는다.
    deepsearch_concurrency: int = Field(default=4, validation_alias=AliasChoices(
        "DEEPSEARCH_CONCURRENCY", "deepsearch_concurrency"))

    #: 🔴 [SCT-1 2026-09-11 사용자 지시] **순서를 뒤집는다** — 딥서치가 변수를
    #   정하고, 최종 판정이 그것을 받아 승패를 낸다.
    #   🔴 **기본 켜짐** — 사용자 지시 2026-09-11 16:4x KST:
    #      "스위치 기본 켜라 … 오늘 이 시간 이후부터 모든 경기에 전부 적용해라."
    #      같은 지시로 **슬레이트 성역(마지막 경기 시작 후 배포)을 이번만 면제**했다
    #      (KBO 18:30 시작 1시간 49분 전 배포).
    #   ⚠️ 끄면 종전 경로(판정이 변수를 만든다)로 한 줄에 돌아간다 —
    #      `DEEPSEARCH_FIRST=0`. 전후 비교가 필요하면 그 값을 쓴다.
    #   ⚠️ 경기당 LLM 호출이 **1회 는다**(정찰). 토큰은 BUD-1 이 센다.
    deepsearch_first: bool = Field(default=True, validation_alias=AliasChoices(
        "DEEPSEARCH_FIRST", "deepsearch_first"))

    #: [ORD-20 2026-09-12] **새 순서(1~4단계).** 수집 → 선별 → 판정 → DB 참조.
    #   🔴 **기본 꺼짐.** 세 순서가 공존한다 — 구경로(자료1~14) · ORDER_V2
    #      (갈림길 먼저) · ORDER_V3(신규). 우선순위는 v3 > v2 > 구경로.
    #      앞의 둘을 지우지 않는다: 오늘 하루에만 순서를 세 번 바꿨고, 되돌릴
    #      길이 없으면 다음 사고 때 멈출 수단이 사라진다.
    #   ⚠️ 이 스위치는 **검색을 켜지 않는다.** x_search 는
    #      `SCOUT_XSEARCH_ENABLED`, 퍼플렉시티는 `DEEPSEARCH_PPLX_ENABLED` 가
    #      따로 잠근다(지금 둘 다 꺼져 있다 — 비용 차단 2026-09-12).
    order_v3: bool = Field(default=False, validation_alias=AliasChoices(
        "ORDER_V3", "order_v3"))

    #: [SRCH-2 2026-09-12 사용자 지시] **Anthropic 웹 검색.**
    #   "x seach 삭제....그자리에 안트로픽 서치로" · "퍼플릭스와 안트로픽"
    #   🔴 **기본 꺼짐.** 유료다 — 경기당 약 $0.102 (실측 2026-09-12:
    #      입력 31,069 · 출력 625 · 검색 3회). 켜는 것은 사람이 한다.
    #   ⚠️ 이 스위치만으로는 아무 일도 안 난다. 부르는 쪽(2단계 선별이
    #      "없는 것"을 지목했을 때)이 있어야 돈다.
    websearch_enabled: bool = Field(default=False, validation_alias=AliasChoices(
        "WEBSEARCH_ENABLED", "websearch_enabled"))
    #: 검색 모델. 🔴 Opus 가 아니라 **Sonnet** 이다 — 실측에서 질문 3개에
    #   $0.102 로 정답 3/3 이었다(grok-4.20 은 $1.082 에 1.5/3).
    #   ⚠️ `matchup_model` 과 **별개**다. 판정은 제미니가 한다(SRCH-1).
    websearch_model: str = Field(default="claude-sonnet-5",
                                 validation_alias=AliasChoices(
                                     "WEBSEARCH_MODEL", "websearch_model"))

    #: 🔴 [ORD-1 2026-09-11 사용자 지시] **순서를 바꾼다.**
    #     "경기가 나왔어 → AI 가 먼저 변수 및 갈림길을 찾는다 → 그 후에 인공위성·
    #      퍼플렉시티·X 가 보강자료를 찾는다 → 결론 → 애매한 것은 우리 DB 참조."
    #   켜면 판정이 **자료1~14 없이** 시작한다. 갈림길 → 보강 → 결론이고,
    #   결론이 `자료필요` 를 내면 그때만 DB 를 붙여 한 번 더 묻는다.
    #   ⚠️ **기본 꺼짐이다.** 이 스위치는 판정 입력을 통째로 바꾼다 —
    #      실측 전에 전 슬레이트에 켜면 무엇이 달라졌는지 대조할 기준이 없다.
    #      `ORDER_V2=1` 로 켠다. `DEEPSEARCH_FIRST` 와는 배타다(켜지면 이쪽이 이긴다).
    #   ⚠️ 경기당 LLM 호출이 **2~3회**가 된다(갈림길·결론·애매할 때 재질의).
    order_v2: bool = Field(default=False, validation_alias=AliasChoices(
        "ORDER_V2", "order_v2"))

    #: [DS-3 2026-09-10 사용자 지시] 딥서치에 Perplexity 병행. **기본 켜짐.**
    #   위성/RSS 가 못 물어온 사실을 PPLX 가 직접 웹에서 찾아 재료로 얹는다.
    #   ⚠️ 유료다 — 전 경기 병행 시 MLB15+KBO5+NPB5 ≈ 25건/일 × $0.01 ≈ 월 $7.5.
    #      끄려면 이 값을 false 로. PPLX 실패는 조용한 폴백이라 회귀는 없다.
    deepsearch_pplx_enabled: bool = Field(default=True, validation_alias=AliasChoices(
        "DEEPSEARCH_PPLX_ENABLED", "deepsearch_pplx_enabled"))

    # ── 위성 수집기 (Phase1 직접 경로) ──────────────────────────────────
    #: [SAT] DB에 없는 경기 정보를 미리 긁어 satellite:{sport}:{game_id} 캐시에
    #   쌓는 백그라운드 잡. **기본 꺼짐** — 켜기 전엔 잡이 즉시 반환해 무해하다.
    #   딥서치가 이 캐시를 읽는 것은 별개 배선(증분2)이라, 이 토글만으로는
    #   판정 경로가 바뀌지 않는다.
    satellite_enabled: bool = Field(default=False, validation_alias=AliasChoices(
        "SATELLITE_ENABLED", "satellite_enabled"))
    #: 위성이 수집하는 종목(콤마 구분). **어댑터가 있는 종목만 실제로 돈다.**
    #  🔴 [SAT-S1 2026-09-12] `soccer` 를 더했다 — K리그1(다음)·J1(야후).
    #     유럽 5리그는 소스가 없어 빈손이고 그 사실을 로그로 밝힌다.
    #  ⚠️ 이 값은 운영 env(`SATELLITE_SPORTS`)가 덮는다 — 실제로 켜려면
    #     거기에도 넣어야 한다(실측 2026-09-12 운영값 `mlb,kbo,npb`).
    satellite_sports: str = "mlb,kbo,npb,soccer"
    #: 수집 정지선 — 시작 T-N분 안이면 그 경기는 더 긁지 않는다(위성이 정지).
    satellite_cutoff_min: int = 10
    #: 대상 경기 탐색 창(시간). status='scheduled' 이고 이 안에 시작하는 경기.
    satellite_lookahead_h: int = 24
    #: [SAT-7] 토르 보강 검색 켜기. **기본 켜짐**(2026-09-09 사용자 지시) —
    #   DDG 로 추가 발굴한다. 한국 소스에는 쓰지 않는다(tor_search 가 한국어 거부).
    satellite_tor_enabled: bool = Field(default=True, validation_alias=AliasChoices(
        "SATELLITE_TOR_ENABLED", "satellite_tor_enabled"))

    # ── 프로바이더 의도적 미사용 ────────────────────────────────────────
    # mock(키 없음)도 오류도 아니다. 여기 있는 이름은 HTTP를 나가지 않고
    # 알림도 내지 않는다. 콤마 구분.
    # 2026-08-28 사용자 지시: AI API는 Anthropic만 충전. Grok·Perplexity 충전 안 함.
    # 🔴 [2026-09-04] Groq·Gemini 를 목록에서 뺀다. 8/28 저녁에 "키 불량"으로
    #    넣은 임시 조치가 그대로 굳어, **무료 전환 뒤에도** 2단 해석봇과 서술이
    #    Groq·Gemini 를 건너뛰고 크레딧 0 인 Anthropic 으로 떨어졌다.
    #    오늘 실호출로 두 키 모두 확인했다(Groq `openai/gpt-oss-120b` 200 ·
    #    Gemini `gemini-3.6-flash` 200). Grok·Perplexity 는 사용자 결정대로 유지.
    disabled_providers: str = "grok,perplexity"

    # ── [§9 카드 ④칸] 순위 경쟁권 판정 ────────────────────────────────────
    # 두 팀이 **모두** 경쟁권 밖이면 순위 차이가 동기 차이를 뜻하지 않는다.
    #   실사고 예방(2026-08-27): 한화 7위(선두와 16.5G) vs SSG 9위(20G).
    #   순위만 보면 한화가 위지만 **둘 다 가을야구와 무관**하다. 여기서
    #   한화에 ▲를 주면 없는 동기 차이를 만들어내는 것이다.
    # ⚠️ 이 값들은 **아직 실측되지 않았다.** 채점 데이터가 쌓이면
    #   "경쟁권 밖 팀이 실제로 더 졌는가"를 재서 교체한다(#77과 같은 원칙).
    # [라인업 발표 시각] 종목별 **관행**. 킥오프 이만큼 전부터 라인업이 있어야
    #   한다고 본다. 그 전에 0건인 것은 정상이고, 그 후에도 0건이면 수집 실패다.
    #   ⚠️ **관행이지 실측이 아니다.** `lineup_lead_observed`가 경기별 실제
    #      (첫 수집 시각 ↔ 킥오프) 차이를 쌓고 있다 — 2주 뒤 그 분포로 교체한다.
    #      그 전까지 이 숫자로 "수집이 늦다"고 결론짓지 마라.
    # 경기 이 분 전의 라인업을 "최종"으로 확정한다. 이후 변경은 별도 알림.
    #   MLB 기본 30분. KBO·NPB는 사용자 지시(2026-08-28) 공시 시각:
    #   KBO 1시간 전, NPB 30분 전.
    lineup_final_minutes: int = 30
    lineup_final_minutes_kbo: int = 60
    lineup_final_minutes_npb: int = 30

    # [핵심 불펜] 관측 창에서 구원 등판이 잦은 상위 몇 명을 '핵심'으로 볼 것인가.
    #   ⚠️ 운용값이지 실측이 아니다 — `lineup_type_ledger`에 bullpen_out 적중률이
    #      쌓이면 몇 명이 적당한지 재서 교체한다.
    key_reliever_top: int = 4

    # [비상 스위치] 라인업 의도 회로 전체를 끈다. false면 기존 5칸 판정만 나간다.
    #   ⚠️ 새 회로가 오늘 밤 사고를 내면 **이것 하나로 되돌린다.**
    lineup_intent_enabled: bool = True

    lineup_lead_mlb: float = 3.0       # MLB 통상 2~4시간 전 발표 → 3시간
    lineup_lead_kbo: float = 1.0       # KBO 경기 1시간 전 공시 (사용자 지시 2026-08-28)
    lineup_lead_npb: float = 0.5       # NPB 경기 30분 전 공시 (사용자 지시 2026-08-28)
    lineup_lead_soccer: float = 1.0    # 축구 통상 킥오프 1시간 전 공식 발표

    contention_gb: float = 10.0        # 선두·컷과 이만큼 벌어지면 경쟁권 밖
    contention_cut_rank: int = 5       # 가을야구 진출선 (KBO 5위)

    # ── [B-2] 단계별 provider 라우팅 ──────────────────────────────────────
    # **코드를 고치지 않고 .env만 바꿔 Anthropic ↔ Gemini ↔ 자체호스팅 전환**이
    # 되어야 한다. 그것이 이 설정의 존재 이유다.
    #   provider 종류: anthropic | gemini | groq | deepseek | ollama | xai | mock
    #   빈 문자열 = 그 역할 비활성 (예: judge_b를 안 쓰는 경우)
    #   *_fallback: "gemini,groq:llama-3.3-70b" 처럼 콤마 구분. `종류:모델` 형식도 가능.
    # ⚠️ 폴백이 일어나면 **어느 provider가 답했는지 리포트·DB에 남는다.**
    #    조용히 다른 모델이 판정하면 품질 변화를 아무도 알 수 없다.
    # ⚠️ 모델을 비우면 **provider의 기본 모델**이 쓰인다(벤더마다 다르다).
    #   역할 폴백(judge_model 등)은 그다음이다 — 안 그러면 provider만 바꿨을 때
    #   Claude 모델명이 Gemini로 가서 404가 난다(실측 2026-08-27).
    # ⚠️ **3중 폴백이 기본이다.** 하나가 막혀도 봇이 멈추지 않아야 한다.
    #   Gemini(무료·분당제한) → Groq(무료·빠름) → Anthropic(유료·품질)
    #   어느 provider가 답했는지는 `LLMResult.label`로 리포트까지 따라간다.
    # ⚠️ 순서는 **측정으로 정했다**(2026-08-27):
    #   Gemini 무료 티어는 분당 제한이 빡빡해 4~5콜이면 429가 난다. 2단은
    #   경기당 2콜(팀별) × 슬레이트라 호출량이 가장 많다 → **Groq가 1순위**다.
    #   Gemini는 폴백으로 두고, 품질이 필요한 3단만 Anthropic을 앞에 둔다.
    # 🔴 [2026-09-06 사용자 지시] **이 역할들의 기본값에서 anthropic 을 뺐다.**
    #    "안트로픽은 2차 판정만 한다." 종전에는 운영 env 네 줄
    #    (INTERPRETER_PROVIDER·INTERPRETER_FALLBACK·JUDGE_A_PROVIDER·
    #     NARRATOR_FALLBACK·INTENT_FALLBACK)이 anthropic 기본값을 덮어써서
    #    닫혀 있었다. env 는 원본이 아니라 **덮개**였고, 덮개가 없는 환경에서는
    #    그대로 열렸다 — 실측 2026-09-06 로컬 실행: `interpreter` 가
    #    claude-haiku 를 부르러 갔고, 400(credit) 이 `trip_credit` 으로 번져
    #    **NC 최종 판정이 호출도 못 해보고 막혔다**(아침 MLB 0/85 와 같은 구조).
    #    이제 코드가 보장한다. 되살리려면 env 로 명시해야 한다.
    #
    # ⚠️ 위 주석에 "groq 은 disabled_providers 기본값에 들어 있다"고 적혀
    #    있었으나 **틀렸다.** 기본값은 `grok,perplexity` 이고 `grok`(xAI)은
    #    `groq` 과 다른 provider 다. 한 글자 차이가 사본으로 굳어 있었다.
    interpreter_provider: str = "groq"      # 2단 해석봇 — 칸 단위 판정 (호출량 최다)
    # 🔴 **비워 둔다.** `resolve_model` 은 명시값 → provider 기본값 → 역할
    #    폴백 순이라, 비우면 provider 의 기본 모델(groq: gpt-oss-120b)이 온다.
    #    비우지 않으면 provider 를 바꿔도 **claude 모델명이 groq 으로 넘어간다.**
    #    (종전 주석은 "비면 judge_model=Opus 가 온다"고 했는데, provider 기본이
    #     역할 폴백보다 앞선 지금은 해당하지 않는다.)
    interpreter_model: str = ""
    interpreter_fallback: str = "gemini"
    judge_a_provider: str = "gemini"        # 3단 대조봇 A — 축구 전용 (야구는 건너뜀)
    judge_a_model: str = ""                 # 비우면 provider 기본 모델
    judge_a_fallback: str = "groq"
    judge_b_provider: str = ""              # 3단 대조봇 B (병렬 비교군) — 기본 꺼짐
    judge_b_model: str = ""
    judge_b_fallback: str = ""
    narrator_provider: str = "gemini"       # 서술
    narrator_model: str = ""
    narrator_fallback: str = "groq"         # 서술은 슬레이트당 1~3콜이라 Gemini로 충분
    intent_provider: str = "groq"           # 의도 파싱 — 질문마다 1콜이라 빠른 쪽
    intent_model: str = ""
    intent_fallback: str = "gemini"
    # 자체호스팅·프록시 주소 (Ollama·사내 게이트웨이 등)
    # ── 사고 예산 (역할별) ────────────────────────────────────────────────
    # ⚠️ **사고 토큰은 출력 예산(max_tokens)을 잠식한다.** 사고형 모델에서
    #   사고가 예산을 다 먹으면 `finishReason=MAX_TOKENS`에 content가 비어서 온다.
    #   실사고 2건 — 같은 계열이다:
    #     · Anthropic max_tokens 16000→32000 임의 상향 → SDK 비스트리밍 거부,
    #       judge 전 배치 실패 (2026-08-26)
    #     · gemini-3.6-flash: 300 예산 중 **285를 사고가 소모**, 답 0토큰 (2026-08-27)
    #   → 사고 예산과 출력 예산을 **분리해서** 잡는다.
    #     -1 = 모델이 알아서 · 0 = 끔 · 양수 = 그만큼 허용
    # provider가 자기 방식으로 매핑한다:
    #     Gemini    generationConfig.thinkingConfig.thinkingBudget
    #     Anthropic thinking.budget_tokens (0이면 thinking 자체를 안 붙인다)
    #     OpenAI호환 무시 (해당 개념이 없다)
    interpreter_thinking: int = 0    # 2단 — 칸 하나 판정. 깊은 추론이 필요 없다
    narrator_thinking: int = 0       # 서술 — 주어진 결론을 문장으로 옮길 뿐
    intent_thinking: int = 0         # 의도 파싱 — 분류 작업
    judge_a_thinking: int = 4000     # 3단 대조 — **여기만 켠다**
    judge_b_thinking: int = 4000     # 3단 대조군

    # ⚠️ **일부 Gemini 모델은 사고를 끌 수 없다.** `thinkingBudget: 0`을 보내면
    #   400 INVALID_ARGUMENT가 난다(실측 2026-08-27, gemini-3.6-flash).
    #   그렇다고 thinkingConfig를 빼면 모델이 예산을 알아서 쓰다가 출력이
    #   잘린다(40토큰 중 35를 사고가 소모 → MAX_TOKENS).
    #   → 역할 예산이 0이면 **이 최소값**을 보낸다. "사고를 최소로"의 실제 구현이다.
    gemini_min_thinking: int = 128
    # Gemini 무료 티어는 **분당** 제한이다(실측: 몇 분 뒤 풀렸다 — 소진 아님).
    # Perplexity와 같은 방식으로 호출 간격을 둔다.
    gemini_min_interval: float = 4.0
    # Groq 무료 티어도 분당 제한이 있다. 2단은 경기당 2콜이라 연속으로 나간다.
    openai_compat_min_interval: float = 1.0
    # 429를 만나면 이만큼 재시도한다(Retry-After가 오면 그것을 우선).
    llm_rate_retries: int = 2
    gemini_base_url: str | None = None
    groq_base_url: str | None = None
    deepseek_base_url: str | None = None
    ollama_base_url: str | None = None
    xai_base_url: str | None = None

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
    # [§8-18] **돈·시장을 분석에서 완전히 뺐다** (2026-08-26 사용자 지시).
    #   제거: bankroll_krw · kelly_fraction · kelly_cap · weekly_stop_loss_pct
    #         min_odds · max_edge_vs_market
    #   이유: 이 값들이 "우리 판단을 시장 기준으로 재단"했다. 실사고 — 판정이
    #   구체적 근거로 지바 롯데 70%를 냈는데 시장 환산 37%와 33%p 어긋난다는
    #   이유로 **데이터 오류 취급해 삭제**했다. 우리 기준을 넘어설 방법이 사라진다.
    #   ⚠️ 라인(핸디 ±1.5·토탈 8.5)은 남긴다 — 그건 가격이 아니라 **질문**이다.
    #   봇은 얼마를 걸라고 말하지 않는다. 수집·분석까지가 전부다.
    min_win_prob: float = 0.58
    # ── §0 시스템 상수 — 물리적 한계 (임의 완화 금지, docs/MODEL.md 참조) ──
    # 근거: 운의 비중 연구 MLB 27.8% / EPL 31.4%. 완벽한 정보를 가져도 MLB 단일 경기
    # 예측 상한은 약 72%이며, 학계 최고 모델 정확도는 61.77%(Wharton)다.
    # 우리 상한은 그보다 보수적으로 잡는다. 이를 넘는 값은 '강한 픽'이 아니라 계산 오류다.
    max_win_prob_mlb: float = 0.68
    min_win_prob_mlb: float = 0.32
    # ── [v1.4 2026-09-07] 자료12 실력 레이팅 · 시장 동의 게이트 ──────────
    #: 🔴 ELO 최근 가중 감쇠. 하루 지날 때마다 그 경기의 K 에 이 값을 곱한다.
    #   0.9 → 열흘 전 경기는 K 의 35%, 한 달 전은 4%. "시즌 누적"이 아니라
    #   **오늘 시점 실력값**을 만드는 것이 목적이다.
    #   ⚠️ 사용자 지정 초기값이다. 바꾸려면 실측 근거를 남겨라.
    elo_decay: float = 0.9
    #: 🔴 [임시 방어] 추천은 시장과 같은 방향일 때만 낸다.
    #   근거: 2026-09-06 620행 분석 — 추천 게이트 통과분이 30.8%(n=13),
    #   보드만이 59.7%(n=77). 우세팀이 갈린 경기는 시장 7승 우리 3승(n=8).
    #   시장을 거스르는 확신이 데이터상 **안티 신호**였다.
    #   🔴 [MKT-3 2026-09-09] **한시가 아니라 상시다. 끄지 마라.**
    #      종전 주석은 "재캘리브레이션이 끝나면 꺼라"였다. 재캘리브레이션은
    #      끝났고 **답은 반대**였다 — 끄면 적중 28.6% 짜리 추천이 되살아난다.
    #      실측 2026-09-09 (운영 원장 `is_final`·채점 완료):
    #      게이트 통과분(추천+가치주의)  6/21 = **28.6%**  P(동전 이하)=0.039
    #      보드만 74/133 = 55.6% · 거부권탈락 14/22 = 63.6%(거부한 쪽이 더 맞다)
    #      판정 확률 AUC 0.5122 [0.426,0.601] · 적중 상관 r = **-0.079**
    #      시장 확률 AUC 0.6421 [0.545,0.734] ← 유일하게 유의
    #      괴리 상위 20경기 — 판정 7/20(35%) vs 시장 17/20(85%)
    #      혼합하면 판정 비중이 늘수록 단조 악화 (0.642 → 0.494)
    #      ⚠️ "구조적으로 시장을 이길 수 없다"는 지적은 맞다. 그러나 우리가
    #         시장을 이긴다는 증거가 없다 — 갈릴수록 우리가 틀렸다.
    #   ⚠️ 임계값은 `market_divergence_pp`(4.0)를 그대로 쓴다. 카드의
    #      "시장 이견" 판정과 **같은 값**이어야 한다(사본 금지).
    #: 🔒 [BAT-6 2026-09-08] 자료3 타자 숫자 주입 스위치. **기본 꺼짐.**
    #   자료 1~11 의 구성과 판정 프롬프트 문구는 v1.4 동결 대상이고, 해제
    #   조건(리그별 graded 50건)이 아직 아니다 — 운영 실측 2026-09-08:
    #   mlb 10/50 · kbo 0/50 · npb 0/50 (표본 재시작 2026-09-07).
    #   ⚠️ **수집·적재는 이 스위치와 무관하게 돈다** — 켜는 날 표본이 0이면
    #      켜는 의미가 없다. 켜는 것은 사람의 결정이다.
    batter_material_enabled: bool = False

    market_agree_required: bool = True
    #: 🔴 [2026-09-06 사용자 지시] 축구 시범 운영 스위치 — **기본 꺼짐**.
    #   `soccer_trial` 은 `judge_route.chain` 을 타지 않고 Anthropic 을
    #   직접 부른다(무료 우회 없음). 그 호출이 400(credit) 을 받으면
    #   `trip_credit` 이 **전역** 가드를 걸어 야구 판정까지 멈춘다 —
    #   실측 2026-09-06 아침 MLB 0/85 가 이 경로였다.
    #   Anthropic 은 최종 판정에서만 쓴다. 되살리려면 이 값을 켜기 전에
    #   soccer_trial 을 무료 사슬로 옮겨야 한다.
    soccer_trial_enabled: bool = False
    #: 🔴 [2026-09-06 사용자 지시] 구 Judge(축구 판정) 스위치 — **기본 꺼짐**.
    #   "2차만 안트로픽 사용하고 관련없는 거는 빼라."
    #   `app/engine/judge.py` 는 `judge_model`(claude-opus-4-6)을 직접 부르는
    #   마지막 Anthropic 경로였다. 야구 2차 최종 판정과 잔액을 나눠 쓰므로,
    #   축구가 많이 쓰면 야구의 그 한 번이 캡에 막힌다.
    #   ⚠️ 끄면 **축구는 판정도 카드도 없다.** 무료 사슬은 이 경로의 tool-use
    #      규약을 타지 않아 그냥 옮길 수 없다 — 옮기려면 별도 작업이다.
    #   되살리려면 `SOCCER_JUDGE_ENABLED=true` 한 줄.
    soccer_judge_enabled: bool = False
    max_win_prob_soccer: float = 0.72
    min_win_prob_soccer: float = 0.10   # 3-way라 원정 승 확률은 낮게 나올 수 있다
    # 세계 최고 조직(Starlizard, 분석가 200명)의 시장 대비 엣지가 1~2%다.
    # 5% 초과는 우리가 더 똑똑한 게 아니라 데이터가 틀린 것이다.
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
    # NPB 최근 3경기. 2026-08-29 라이브 Yahoo 36/36 부착·타격표 대조 후 True.
    # False면 추천 자동 탈락(보드는 발송). DISCIPLINE 1-A-2.
    npb_last3_verified: bool = True

    # 승패 λ 변별 하한. |p_λ − 0.5| 미만이면 승패 결합에서 λ를 뺀다 (Claude 단독).
    # 실측 2026-08-28 NPB: λ 47~50%가 Claude 65%를 56%로 깎아 승패 추천 0건.
    # 언더오버·런라인은 건드리지 않는다. min_win_prob 0.58은 유지.
    lambda_h2h_min_edge: float = 0.05

    # ── 기대득점(λ) 모델 계수 ([2][3]) ──────────────────────────────────
    league_runs_per_game: float = 4.40    # MLB 팀당 평균 득점
    # [§8-14] KBO는 득점 환경이 다르다 — MLB 값을 그대로 쓰면 λ가 통째로 낮게 나온다.
    #   실측(2026-08-26, KBO 공식 기록실 10팀): 팀당 평균 득점 5.094 · 리그 ERA 4.658
    #   (MLB 4.40 대비 +0.694). 시즌 누적값이며 매 시즌 재측정이 필요하다.
    kbo_runs_per_game: float = 5.09
    kbo_league_era: float = 4.66
    # [§8-20] NPB는 **완전히 다른 득점 환경**이다 — 야구라고 KBO 값을 빌려오면
    #   λ가 통째로 1.5점 높게 나온다.
    #   실측(2026-08-26, npb.jp 공식 12팀): 팀당 평균 득점 3.610 · 리그 ERA 3.339
    #   대조: KBO 5.094/4.658 · MLB 4.40/4.30 — NPB가 가장 투수 친화적이다.
    npb_runs_per_game: float = 3.61
    npb_league_era: float = 3.34
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
    # [§8-8] 5이닝까지의 득점 비중. 5/9=0.556 근사였으나 **실측은 0.561**이다
    #   (2026-08-26, 5회말 완료 6807경기 · F5 득점 4.974 / 전체 8.867).
    #   0.55는 F5 λ를 약 2% 낮게 만들었다.
    f5_share: float = 0.561

    # [§8-5] 팀 타선 지표를 **양 팀 평균으로 둘 다에 적용**한다.
    # 실측(2026-08-26, 1324경기): 타선 지표는 두 팀의 '차이'를 틀리게 잡고
    # '합계'는 맞게 잡는다 — 그래서 승패엔 해롭고 토탈엔 유익했다.
    #   현행(비대칭) 승패 0.5257 / 토탈 0.5675
    #   타선 제거    승패 0.5340 / 토탈 0.5645
    #   대칭 적용    승패 0.5355 / 토탈 0.5670  ◀ 양쪽 모두 우위
    # 끄면 종전 동작으로 즉시 복귀한다(재측정 가능성 보존).
    offense_symmetric: bool = True

    # [§8-6] 관측 창 — **일수가 아니라 경기 수**로 자른다.
    # 실측(2026-08-26, 1496경기 · 창 길이 스윕):
    #    창        승패      토탈8.5
    #    3경기   +0.67%p   +1.87%p (p=0.074)
    #    7경기   +1.47%p   +2.67%p (p=0.019)
    #   15경기   +1.61%p   +2.80%p (p=0.015)  ◀ 최적
    #   30경기   +0.27%p   +2.33%p
    #   30일(종전) +0.27%p +2.07%p
    # 너무 짧아도(3) 너무 길어도(30) 나빠지고 가운데가 최고다.
    # 0이면 창을 자르지 않는다(종전 30일 전량 동작).
    recent_window_games: int = 15      # 숫자 지표(xwOBA 등)를 몇 경기로 볼 것인가
    recent_window_starts: int = 8      # 선발 지표를 몇 등판으로 볼 것인가
    # 사실·상태(라인업·불펜 소모·결장·피로)는 별개다 — "지금 어떤 상태인가"는
    # 최근 몇 경기만 보면 된다. 숫자 창과 섞지 않는다.
    recent_facts_games: int = 3
    league_goals_per_team: float = 1.40   # 축구 팀당 평균 득점
    home_goal_edge: float = 0.10          # 홈 득점 이점 (축구)
    # [§8-8] 득점 분포 형태. 포아송은 분산=평균을 가정하는데 **야구는 그렇지 않다.**
    #   실측(2026-08-26, 1496경기): 실제 총득점 분산 20.52 / 평균 8.92 → 비율 2.302.
    #   적률법 역산 r = 3.32 → 3.3 채택 (Brier 최소값을 채굴하지 않았다).
    #   포아송 → 음이항 r=3.3 전환 효과:
    #     토탈 Brier 0.7536 → 0.7338 · 승패 Brier 0.2523 → 0.2489
    #     승패 정확도 0.5301 → 0.5314 · 토탈 8.5 정확도 0.5508 → 0.5548
    #     라인 7.5 오버확률 0.6179(실제 0.5575) → 0.5416  ◀ 과신이 크게 줄었다
    #   전 지표에서 포아송보다 낫다.
    # ⚠️ **축구는 None으로 둔다** — 축구 득점의 과분산을 측정한 적이 없다.
    #    측정 없이 같은 값을 쓰면 지시받지 않은 튜닝이다(DISCIPLINE 5-1).
    score_dispersion_mlb: float | None = 3.3
    score_dispersion_soccer: float | None = None
    score_dispersion: float | None = None # 전역 강제값 (설정 시 종목별 값을 덮어쓴다)
    signal_green_prob: float = 0.62      # 🟢 승률 하한

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
    report_banner: str = ""         # 비상 배너 (예: EV 점검 중) — 비면 미표시

    ev_threshold: float = 0.05      # 이 이상 EV일 때만 추천 픽 (기준 EV +5%↑)
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
    def mock_freesource(self) -> bool:
        """무인증 수집기(Statcast·네이버·Yahoo재팬·KBO 기록실·open-meteo 등)를
        목으로 돌릴 것인가.

        🔴 다른 `mock_*` 은 전부 `force_mock or not <API키>` 형태다. 무인증
           소스는 걸 고리가 될 키가 없어서 **목 판정 자체가 없었고, 테스트에서
           실트래픽이 나갔다.** 그래서 이 속성은 `force_mock` 하나만 본다.

        ⚠️ 프로덕션에서 켜지지 않는다: `force_mock` 기본값은 False이고,
           켜지는 경로는 `FORCE_MOCK=true` 뿐이다. 그 값을 세우는 곳은
           `tests/conftest.py`(pytest 수집 시)와 개발자가 직접 지정하는
           `.env` 뿐이며, `.env.example` 에도 운영값 False로 적혀 있다.
        """
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

    def deepsearch_enabled(self, sport: str) -> bool:
        """그 종목에서 딥서치(Perplexity)를 쓰는가."""
        allow = {x.strip().lower() for x in (self.deepsearch_sports or "").split(",")}
        return bool(sport) and sport.lower() in allow

    def disabled_set(self) -> set[str]:
        return {x.strip().lower()
                for x in (self.disabled_providers or "").split(",") if x.strip()}

    def is_disabled(self, name: str) -> bool:
        """의도적 미사용인가. mock·키오류와 섞지 않는다."""
        return bool(name) and name.lower() in self.disabled_set()

    @property
    def mock_grok(self) -> bool:
        return self.force_mock or not self.xai_api_key

    @property
    def mock_judge(self) -> bool:
        return self.force_mock or not self.anthropic_api_key

    @property
    def mock_gemini(self) -> bool:
        """🔴 [BUD-1 2026-09-11] **판정 사슬의 주전이 여기 없었다.**

        실측(키 전부 제거, 2026-09-11): `mock_judge` 는 `anthropic_api_key` 만
        보고 `mock_grok` 은 `xai_api_key` 만 본다. 2026-09-11 전환으로 판정
        주전은 **gemini** 인데, 그 키가 없어도 기동 로그·상태 표시에는 아무
        것도 안 떴다 — 표시가 실제 경로와 어긋나 있었다.

        ⚠️ 이 속성은 **표시용이다.** 판정 사슬은 목으로 폴백하지 않는다 —
           키가 없으면 빈 응답을 돌려주고 그 경기는 "재료 없이" 간다
           (절대규칙 6: 재료 없으면 분석 생성 금지). 목 판정을 카드로 내보내는
           것이 더 나쁘기 때문이다. 실측에서 크래시는 없었다(절대규칙 3 후단).
        """
        return self.force_mock or not self.gemini_api_key

    def log_mock_status(self) -> None:
        for name in ("mlb", "odds", "football", "perplexity", "gemini",
                     "grok", "judge"):
            if self.is_disabled(name):
                mode = "DISABLED"
            else:
                mode = "MOCK" if getattr(self, f"mock_{name}") else "LIVE"
            logger.info("module %-10s -> %s", name, mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()
