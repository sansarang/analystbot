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

    # ── [A-5단계] 리그별 딥서치 스위치 ─────────────────────────────────────
    # 콤마 구분 종목 목록. 여기 없는 종목은 **딥서치를 부르지 않는다.**
    #   KBO·NPB는 크롤링으로 완전 대체됐다(2026-08-27): 공식 기록실·네이버·
    #   Yahoo·1군 공시·경기 전 기사. 딥서치 콜이 5 → 0이 됐다.
    #   MLB도 같다(2026-08-28): statsapi·Statcast. 전문가 픽·Odds 없음.
    #   유럽축구는 전문가 픽이 웹에 흩어져 있어 검색이 필요하다.
    # ⚠️ 이 값을 비우면 전 종목에서 딥서치가 꺼진다 — 의도한 경우에만 그렇게 하라.
    deepsearch_sports: str = "soccer"

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
    interpreter_provider: str = "groq"      # 2단 해석봇 — 칸 단위 판정 (호출량 최다)
    interpreter_model: str = ""
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
