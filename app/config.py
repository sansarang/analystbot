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

    # API 키 — 없으면 해당 모듈은 mock_data/ 목 모드로 동작한다.
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None  # 쿼터 소진 등 운영 알림 수신 채팅
    anthropic_api_key: str | None = None
    pplx_api_key: str | None = None
    xai_api_key: str | None = None
    odds_api_key: str | None = None
    # [B-2] 추가 LLM provider — 없으면 그 provider는 쓰지 않는다(크래시 금지).
    gemini_api_key: str | None = None
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
    gemini_model: str = Field(default="gemini-2.5-flash",
                              validation_alias=AliasChoices("GEMINI_MODEL",
                                                            "gemini_model"))
    #: 무료 티어 분당 10요청 — 호출 간 최소 간격(초).
    gemini_min_interval_sec: float = 7.0
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

    matchup_model: str = Field(
        default="claude-sonnet-5",
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
    matchup_max_tokens: int = 6000

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
    deepsearch_max_tokens: int = 8000
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

    # ── 프로바이더 의도적 미사용 ────────────────────────────────────────
    # mock(키 없음)도 오류도 아니다. 여기 있는 이름은 HTTP를 나가지 않고
    # 알림도 내지 않는다. 콤마 구분.
    # 2026-08-28 사용자 지시: AI API는 Anthropic만 충전. Grok·Perplexity 충전 안 함.
    # 2026-08-28 저녁: Groq·Gemini 키 불량 → 오늘 건너뛰고 Claude만.
    disabled_providers: str = "grok,perplexity,groq,gemini"

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
    # 🔴 기본값이 서로 모순이었다: interpreter_provider="groq" 인데 groq 은
    #    disabled_providers 기본값에 들어 있다. 그래서 라인업 의도 해석이
    #    **한 번도 돌지 않았다** — 변경점(사실)만 카드에 실리고 "감독이 왜
    #    그렇게 짰나"(해석)는 통째로 비어 있었다 (실측 2026-09-01).
    interpreter_provider: str = "anthropic"  # 2단 해석봇 — 칸 단위 판정 (호출량 최다)
    # ⚠️ **비워두지 마라.** 비면 역할 폴백이 judge_model(=Opus)을 넣는다.
    #    해석봇은 경기×양팀으로 호출량이 가장 많은 역할이라 Opus 로 돌면
    #    슬레이트당 20콜이 Opus 가 된다. 분류·요약 작업이므로 팀 폼과 같은
    #    등급(Haiku)이 맞다.
    interpreter_model: str = "claude-haiku-4-5-20251001"
    interpreter_fallback: str = "gemini,anthropic"
    judge_a_provider: str = "anthropic"     # 3단 대조봇 A — 품질 우선
    judge_a_model: str = ""                 # 비우면 judge_model을 쓴다
    judge_a_fallback: str = "gemini,groq"
    judge_b_provider: str = ""              # 3단 대조봇 B (병렬 비교군) — 기본 꺼짐
    judge_b_model: str = ""
    judge_b_fallback: str = ""
    narrator_provider: str = "gemini"       # 서술
    narrator_model: str = ""
    narrator_fallback: str = "groq,anthropic"   # 서술은 슬레이트당 1~3콜이라 Gemini로 충분
    intent_provider: str = "groq"           # 의도 파싱 — 질문마다 1콜이라 빠른 쪽
    intent_model: str = ""
    intent_fallback: str = "gemini,anthropic"  # groq·gemini 미사용 시 Claude
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

    def log_mock_status(self) -> None:
        for name in ("mlb", "odds", "football", "perplexity", "grok", "judge"):
            if self.is_disabled(name):
                mode = "DISABLED"
            else:
                mode = "MOCK" if getattr(self, f"mock_{name}") else "LIVE"
            logger.info("module %-10s -> %s", name, mode)


@lru_cache
def get_settings() -> Settings:
    return Settings()
