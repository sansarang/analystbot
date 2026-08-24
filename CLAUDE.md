# AnalystBot — 스포츠 분석 텔레그램 챗봇

## 프로젝트 한 줄 정의

**숫자는 API로**(statsapi.mlb.com, The Odds API, API-Football), **의견은 딥서치로**(Perplexity sonar-pro, Grok Live Search), **판정은 Claude로**(JUDGE_MODEL, extended thinking) 하는 분석 챗봇.

## MCP 사용 규약

- **코드 탐색·수정은 Serena 우선**: `find_symbol` → `replace_symbol_body` 순으로 심볼 단위 정밀 편집. 파일 전체 재작성 금지. collectors/research/engine 간 의존이 많으므로 참조 확인은 `find_referencing_symbols` 사용.
- **DB 상태 확인은 postgres MCP로 직접 쿼리**: 스키마 검증, 적재 데이터 확인(예: `odds_snapshots` 스냅샷이 실제로 쌓이는지)은 코드 추측이 아니라 SELECT로 확인.
- **캐시 상태는 redis MCP**: 프리페치 캐시 TTL·히트 여부 확인.
- **라이브러리 사용법이 불확실하면 context7로 문서 확인 후 작성**: aiogram 3.x, FastAPI, Anthropic SDK는 버전 간 API 변경이 잦다. 학습 데이터 기억으로 코딩하지 말 것.

## 절대 규칙

1. **자동 베팅 집행 기능 금지.** 분석·추천까지만. 베팅 실행 코드는 어떤 형태로도 작성하지 않는다.
2. **LLM 출력의 수치는 API 숫자와 교차검증. 충돌 시 API가 이긴다.** 딥서치·Claude가 말한 배당/스탯이 API 값과 다르면 API 값을 사용한다.
3. **API 키가 없으면 `mock_data/` 기반 목 모드로 동작.** 키 부재로 크래시하지 않는다.
4. **DB는 UTC 저장, 표시만 KST.** timestamptz 사용, 변환은 표시 계층에서만.
5. **날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 리포트의 경기 시각 표기는 항상 KST**이며, 이미 시작/종료된 경기는 "진행 중"/"종료" 라벨을 붙이고 분석(픽·파레이·판정) 대상에서 제외한다.

## 실시간 리서치 체제 (app/research/deep.py)

- 새벽 프리페치(04:00 KST)가 전 경기 심층 리서치(경기당 Perplexity 1콜, **리그·경기 단위 순차**) + 2단 판정(잠정 결론 → 반박 검증, `reversal_factor`)을 캐시. 실패 경기는 '리서치 미완' 마킹 후 첫 요청 시 온디맨드 보완.
- 신선도 게이트: 리서치 캐시 6시간 이내 & 킥오프 3시간 이상 → 캐시 즉답. 킥오프 3시간 이내 or 캐시 6시간 초과 → 재리서치+재판정. 실패 시 캐시 폴백("새벽 데이터 기준" 표기).
- 반박 검증으로 결론이 바뀌면 신호등 한 단계 보수화 (🟢→🟡→🔴).
- 비용 가드: Perplexity 일 상한 60콜(`research_calls:{date}`), 초과 시 재리서치 억제 + 카드 경고. 주간 예상 비용은 프리페치 로그.
- 전문가 전적은 마켓별 분리(`load_expert_market_ledger`): 해당 마켓 ROI 마이너스(표본 5+)면 불채택, 전적 미상은 0.5표.

## 리서치 응답 검증 (app/research/validate.py)

딥서치가 데이터를 못 찾으면 **우리가 보낸 요청 문구를 되풀이하는 산문**을 돌려준다
("최근 5~7경기별 일자·상대·이닝·실점·피OPS 등을 확인할 수 있는 로그에 접근할 수 없어…").
이 값이 `recent_form`/`last5` 자리에 담겨 데이터인 척 출력된 사고가 있었다. 규칙:

- **무효 판정 3종**: ①미확보 산문("확인 불가", "접근할 수 없", "미확인" 등) ②프롬프트/스키마
  반향(지시 문구 포함 또는 프롬프트 토큰과 자카드 0.72↑) ③수치 요구 필드에 숫자 0개.
- 무효 값은 필드에서 제거하고, **재료(recent_form·전문가 픽·결장 정보)가 하나도 없으면
  리서치 실패**로 처리한다 (`ResearchUnusableError` → 1회 재요청 → status `invalid`).
- 출처 URL도 전문가 이름도 없는 전문가 픽은 인용 불가 — 2-소스 룰의 '전문가 축'이 못 된다.
- **캐시 구데이터도 렌더 직전에 재검증**한다 (이전 버전이 저장한 오염 데이터 차단).
- **재료 0이면 심층 분석을 만들지 않는다.** "최신 데이터 수집에 실패해 분석할 수 없습니다"만 출력.

## 출력 문구 규칙

- **경기 고유성**: "조심할 점"·"걸 만한가" 각 줄은 그 경기 고유의 숫자나 선수 이름을 최소 1개
  포함해야 한다(`line_is_game_specific`). 만들 수 없으면 그 줄을 **생략**한다 — 빈말 금지.
  여러 경기를 함께 낼 때는 `render_games_easy`가 공유 집합으로 중복 문장을 재생성한다.
- **종목별 용어 분리**: 야구는 "경기 시작 전 라인업 발표"·"런라인", 축구는 "킥오프 직전"·
  "핸디"·"더블찬스". 분기 기준은 `_sport_of(jg)` (jg["sport"] → 리그 → 선발 투수 유무 순).

## 외부 API 에러 분류 (app/collectors/base.py)

`classify_api_error(status, body)` → `credit` | `auth` | `rate_limit` | `server` | `other`.

| 상황 | 분류 | 예외 | 사용자 알림 |
|---|---|---|---|
| 402 / 잔액·사용량 상한 문구 | credit | `ApiQuotaError` | 충전 안내 |
| 401·403 (인증 실패) | auth | `ApiAuthError` | 키 교체 안내 |
| **429 (레이트리밋)** | rate_limit | `ApiRateLimitError` | **없음** — 내부 재시도·큐 재처리 |
| 5xx | server | 원 예외 | 없음 (지수 백오프) |

429를 "크레딧 소진 — 충전 필요"로 안내하던 오분류가 실사고였다(잔액 $6.90 잔존).
알림은 반드시 `notify_api_error(exc)`로 라우팅한다 — `notify_quota` 직접 호출 금지.

## Perplexity 레이트리밋·마이그레이션

- **레이트리밋 방어**: 동시 실행 `PPLX_MAX_CONCURRENCY`(기본 2), 요청 간 최소 간격
  `PPLX_MIN_INTERVAL`(기본 1.5s), 429는 Retry-After 우선 + 2s→6s→15s 3회 재시도,
  최종 실패는 `research_retry_queue`에 적재해 다음 사이클(45분 간격 잡)에 순차 재시도.
- **프리페치는 순차**: 종목(리그) 단위 순차 + 경기 단위 순차(`sequential_research=True`).
  전 경기 동시 리서치(MLB 10 + 축구 17)가 429를 유발한 실사고 반영.
- **실패 계측**: `research_fail:{date}:{reason}` — reason은 rate_limit/timeout/parse/credit/auth/other.
  `research_failure_report(redis, date)`로 원인별 집계.
- **⚠️ 마이그레이션 필수 (기한 2026-09-27)**: Perplexity가 Sonar Chat Completions를 종료하고
  Agent API로 이전한다. 엔드포인트·모델은 config로 분리돼 있어 **코드 수정 없이 .env로 전환**한다:

  ```
  PPLX_API_MODE=agent          # chat → agent
  PPLX_AGENT_PATH=/v1/agent
  PPLX_AGENT_PRESET=medium     # fast|low|medium|high|xhigh
  ```

  요청은 `{"model", "messages"}` → `{"preset", "input"}`, 응답은 `choices[]` → typed `output[]`
  (`{"type":"message","content":[{"text":…}]}` / `{"type":"search_results","results":[…]}`)로 바뀌며,
  `perplexity.normalize_response()`가 두 형태를 Sonar 형태로 흡수한다.
  전환 시 확인할 것: ①Agent 프리셋별 단가·품질 ②`citations` 대체(search_results) ③일 상한 재산정.

## 기술 스택

Python 3.12 · FastAPI · aiogram 3.x · httpx(비동기) · PostgreSQL · Redis · APScheduler · pytest

## 디렉토리 규약

```
app/
  collectors/     # 숫자 수집 (statsapi.mlb.com, The Odds API, API-Football)
  research/       # 딥서치 (Perplexity sonar-pro, Grok Live Search)
  engine/         # value · consensus · parlay · judge
  pipeline.py     # 수집→리서치→판정 파이프라인 오케스트레이션
  bot/            # aiogram 텔레그램 봇
  scheduler.py    # APScheduler 잡 (배당 스냅샷, 프리페치 등)
  grader.py       # 경기 결과 채점
db/schema.sql     # DB 스키마 (마이그레이션 원본)
mock_data/        # API 키 없을 때 쓰는 목 데이터
tests/            # pytest 테스트
```

## 핵심 수식

- Expected value: `ev = p * odds - 1`
- 스테이킹: **하프 켈리, 뱅크롤 5% 상한**
- 앙상블 확률: `p_ensemble = 0.45 * p_model + 0.30 * p_market + 0.25 * p_claude`
- 시장 수축: `p_final = λ * p_market + (1-λ) * p_ensemble` — λ는 리그 데이터 성숙도 연동
  (MLB·EPL·라리가·세리에A·분데스리가 0.3, 그 외 0.6; 채점 300픽부터 리그별 실측 재추정)

## 추천 자격 규칙 (app/engine/markets.py)

- **2-소스 룰**: 독립 근거 축(①시즌 실데이터 ②전문가 픽 ③모델 ④시장 방향) 2개 이상 지지 필수. 모델 단독 픽은 EV 무관 추천 금지.
- **괴리 검증**: 모델-시장 괴리 ≥10%p + 전문가 미지지 승패 픽 → "시장이 아는 정보" 라벨 제외.
- **축구 저분산 기본**: 추천 기본 마켓은 더블찬스(3-way 합성)·+1.5 핸디캡. 승패 단식은 판정 신뢰도 high에서만.
- **데이터 제로 강등**: 시즌 실데이터 0건 경기는 신뢰도 자동 '낮음' + 추천 박탈.
- **멀티마켓**: 경기당 승패·더블찬스·핸디캡·토탈 전 마켓을 평가해 마켓 보드(⑧)로 표기, 추천·조합은 전 마켓 승인 풀에서 구성. 같은 경기 상관 레그 2개는 한 조합 금지.

## 명령어

```bash
docker compose up -d                 # PostgreSQL 16 + Redis 7 기동
uvicorn app.main:app --reload        # FastAPI 개발 서버
python -m app.bot                    # 텔레그램 봇 실행 (polling)
pytest                               # 전체 테스트
pytest tests/test_engine.py -x -q    # 단일 파일 빠른 실행
```

## 코드 규칙

- 모든 외부 HTTP 호출은 **지수 백오프 3회 재시도 + 타임아웃** 필수 (httpx 기준).
- **새 기능은 테스트와 함께 커밋.** 테스트 없는 기능 코드 커밋 금지.

## .env 변수

| 변수 | 용도 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `ANTHROPIC_API_KEY` | Claude 판정(judge) 호출 |
| `PPLX_API_KEY` | Perplexity sonar-pro 딥서치 |
| `XAI_API_KEY` | Grok Live Search |
| `ODDS_API_KEY` | The Odds API (배당) |
| `APIFOOTBALL_KEY` | API-Football (축구 스탯) |
| `JUDGE_MODEL` | 판정에 쓸 Claude 모델 ID |
| `PPLX_API_MODE` | `chat`(현행 Sonar) \| `agent`(2026-09-27 이후 필수) |
| `PPLX_BASE_URL` / `PPLX_CHAT_PATH` / `PPLX_AGENT_PATH` | 엔드포인트 (마이그레이션용) |
| `PPLX_MODEL` / `PPLX_AGENT_PRESET` | 모델명 / Agent 프리셋 |
| `PPLX_MAX_CONCURRENCY` / `PPLX_MIN_INTERVAL` | 레이트리밋 방어 (기본 2 / 1.5초) |
| `TELEGRAM_ADMIN_CHAT_ID` | 크레딧·키 오류 알림 수신 채팅 |

키가 하나라도 없으면 해당 모듈은 `mock_data/` 목 모드로 폴백한다.
