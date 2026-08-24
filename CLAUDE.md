# AnalystBot — 스포츠 분석 텔레그램 챗봇

## ⚠️ 작업 시작 전 필수 확인

**작업 시작 전 [docs/DISCIPLINE.md](docs/DISCIPLINE.md)(운용 규율)와
[docs/RESEARCH_VALIDATION.md](docs/RESEARCH_VALIDATION.md)(데이터 신뢰 규칙)를 반드시 확인하라.
두 문서의 규율을 위반하는 변경은 하지 마라. 규율과 충돌하는 요청을 받으면 실행하기 전에
그 사실을 먼저 보고하라.**

**지시받지 않은 파라미터·설정 변경 금지.** `max_tokens`·배치 크기·타임아웃·모델명·임계값·
프롬프트 등은 **사용자가 요청했거나 버그 수정에 필수인 경우에만** 바꾼다. 바꿨다면 보고에
**(a) 변경 전후 값 (b) 변경 이유 (c) 영향 범위**를 반드시 명시하라.
"성능이 나아질 것 같아서" 같은 자발적 튜닝은 금지다. → [DISCIPLINE.md 5-1](docs/DISCIPLINE.md)

## 프로젝트 정의

**숫자는 API로**(statsapi.mlb.com, The Odds API, football-data.org),
**의견은 딥서치로**(Perplexity sonar, Grok Live Search),
**판정은 Claude로**(JUDGE_MODEL + extended thinking) 하는 스포츠 분석 텔레그램 봇.

**자동 발송 없음 — 사용자가 요청할 때만 응답한다.** 스케줄러는 데이터를 미리 조사해
캐시할 뿐 리포트를 보내지 않는다. (예외: 크레딧 소진·키 오류 시 관리자 채팅으로 운영 알림)

## 문서 목록

| 문서 | 내용 |
|---|---|
| **[docs/DISCIPLINE.md](docs/DISCIPLINE.md)** | 픽 선정·데이터 신뢰·자금·평가·개발 규율 **(최우선)** |
| [docs/RESEARCH_VALIDATION.md](docs/RESEARCH_VALIDATION.md) | 리서치 응답 검증 체계와 튜닝 기준 |
| CLAUDE.md | 이 문서 — 구조·명령어·규약 |

---

## 절대 규칙

1. **자동 베팅 집행 기능 금지.** 분석·추천까지만. 베팅 실행 코드는 어떤 형태로도 작성하지 않는다.
2. **LLM 출력의 수치는 API 숫자와 교차검증. 충돌 시 API가 이긴다.**
3. **API 키가 없으면 `mock_data/` 기반 목 모드로 동작.** 키 부재로 크래시하지 않는다.
4. **DB는 UTC 저장, 표시만 KST.** timestamptz 사용, 변환은 표시 계층에서만.
5. **날짜 기준: MLB=미국 동부 오늘(슬레이트 날짜), 축구=KST 오늘. 표기는 항상 KST.**
   이미 시작/종료된 경기는 "진행 중"/"종료" 라벨을 붙이고 분석 대상에서 제외한다.
   ⚠️ 현재 KST 날짜 경계는 **자정**이다(`today_kst`). "KST 06:00~익일 06:00" 경계는 미구현.

---

## 아키텍처 요약

```
app/
  collectors/     # 숫자 수집 — statsapi.mlb.com, The Odds API, football-data.org, API-Football
    base.py       #   공통 HTTP: 재시도·백오프·스로틀·에러 분류(credit/auth/rate_limit)
  research/       # 딥서치 — Perplexity sonar(deep.py), Grok Live Search(grok.py)
    validate.py   #   응답 검증 (프롬프트 반향·미확보 산문 차단) ★
    crosscheck.py #   리서치 수치 ↔ statsapi 교차검증 샘플링 (지어내기 감시)
  engine/         # value · consensus · parlay · markets · judge
    markets.py    #   추천 자격 판정 (2-소스 룰·괴리 검증·마켓 보드)
  pipeline.py     # 수집 → 리서치 → 판정 오케스트레이션 + 렌더
  bot/            # aiogram 텔레그램 봇
  scheduler.py    # APScheduler 잡
  grader.py       # 경기 결과 채점
db/schema.sql     # DB 스키마 (마이그레이션 원본)
mock_data/        # API 키 없을 때 쓰는 목 데이터
docs/             # DISCIPLINE.md · RESEARCH_VALIDATION.md
tests/            # pytest
```

**스케줄러 잡**: 프리페치 04:00 KST(종목·경기 단위 **순차**) · 배당 스냅샷 30분 ·
리서치 재시도 큐 45분 · 채점 13:00 KST · Elo 갱신 주 1회(월 05:00).

**리서치 신선도 게이트**: 캐시 6시간 이내 & 킥오프 3시간 이상 → 캐시 즉답.
캐시 6시간 초과 또는 킥오프 3시간 이내 → 재리서치 + 재판정. 실패 시 캐시 폴백.

---

## 핵심 규칙 (요약 — 상세는 [DISCIPLINE.md](docs/DISCIPLINE.md))

- **추천 자격**: 2-소스 룰(독립 근거 축 2개 이상) + 괴리 검증(모델-시장 10%p 이상인데
  전문가 미지지면 제외) + 신뢰도 연동(판정 '낮음'은 전 마켓 박탈, 축구 승패 단식은 '높음'만)
- **재료 없으면 분석 생성 금지.** LLM 수치는 API와 교차검증, 충돌 시 API 우선
- **EV +20% 초과 · 확률-배당암시 괴리 25%p 초과는 데이터 오류 플래그** (가치가 아니다)
- **자동 베팅 집행 기능 구현 금지**
- **멀티마켓**: 경기당 승패·더블찬스·핸디캡(런라인)·언더오버 전 마켓을 평가해 마켓 보드(⑧)로
  표기. 추천·조합은 전 마켓 승인 풀에서 구성하고, 같은 경기 상관 레그 2개는 한 조합 금지

### 핵심 수식

- Expected value: `ev = p * odds - 1`
- 스테이킹: **하프 켈리, 뱅크롤 5% 상한** (모드에 따라 플랫 스테이크)
- 앙상블: `p_ensemble = 0.45*p_model + 0.30*p_market + 0.25*p_claude`
- 시장 수축: `p_final = λ*p_market + (1-λ)*p_ensemble` — λ는 리그 데이터 성숙도 연동
  (MLB·EPL·라리가·세리에A·분데스리가 0.3, 그 외 0.6; 채점 300픽부터 리그별 실측 재추정)

### 출력 문구 규칙

- **경기 고유성**: "조심할 점"·"걸 만한가" 각 줄은 그 경기 고유의 숫자나 선수 이름을 최소
  1개 포함해야 한다(`line_is_game_specific`). 만들 수 없으면 그 줄을 **생략**한다 — 빈말 금지.
  여러 경기를 함께 낼 때는 `render_games_easy`가 공유 집합으로 중복 문장을 재생성한다.
- **종목별 용어 분리**: 야구는 "경기 시작 전 라인업 발표"·"런라인", 축구는 "킥오프 직전"·
  "핸디"·"더블찬스". 분기 기준은 `_sport_of(jg)`.

---

## 리서치 데이터 신뢰 규칙

> 상세·사고 기록: [docs/RESEARCH_VALIDATION.md](docs/RESEARCH_VALIDATION.md)

- **LLM 응답은 200 OK여도 데이터가 아닐 수 있다 — `validate.py` 통과 전 사용 금지.**
  Perplexity는 데이터를 못 찾으면 200 OK로 "왜 못 찾았는지" 산문을 JSON 필드에 담아 보낸다.
- **재료(recent_form·전문가 픽·결장 정보)가 없으면 분석을 만들지 말고 "수집 실패"로
  정직하게 표시한다.**
- **새 리서치 필드를 추가할 때는 `validate.py`의 정책을 함께 정의한다** —
  **문장 필터 대상**(자유서술 필드: 미확보 문장만 제거)인지 **전량 폐기 대상**(구간을
  단언하는 필드: `last5`처럼 조건 불충족 시 통째 폐기)인지. 라벨이 무엇을 단언하는가로 나눈다.
- **튜닝 기준**: 무효율 **30% 초과 = 키워드 과잉** / 채움률 **급락 = 프롬프트 금지문 과잉** /
  교차검증 **불일치 반복 = 지어내기 의심(금지문 롤백)**.
  지표는 `research_fill:{date}`·`research_crosscheck:{date}`에 쌓이고 프리페치 로그에 출력된다.
- **⚠️ Perplexity Agent API 마이그레이션 기한: 2026-09-27.** Sonar Chat Completions가
  종료된다. 엔드포인트·모델이 config로 분리돼 있어 **코드 수정 없이 `.env`로 전환**한다:
  `PPLX_API_MODE=agent` (요청 `{"model","messages"}` → `{"preset","input"}`, 응답
  `choices[]` → typed `output[]`; `perplexity.normalize_response()`가 두 형태를 흡수).

### 외부 API 에러 분류 (`app/collectors/base.py`)

`classify_api_error(status, body)` → `credit` | `auth` | `rate_limit` | `server` | `other`

| 상황 | 분류 | 예외 | 사용자 알림 |
|---|---|---|---|
| 402 / 잔액·사용량 상한 문구 | credit | `ApiQuotaError` | 충전 안내 |
| 401·403 (인증 실패) | auth | `ApiAuthError` | 키 교체 안내 |
| **429 (레이트리밋)** | rate_limit | `ApiRateLimitError` | **없음** — 내부 재시도·큐 재처리 |
| 5xx | server | 원 예외 | 없음 (지수 백오프) |

알림은 반드시 `notify_api_error(exc)`로 라우팅한다 — `notify_quota` 직접 호출 금지.
Perplexity는 동시 실행 2 · 요청 간 1.5초 · 429는 Retry-After 우선 후 2s→6s→15s 재시도 ·
최종 실패는 `research_retry_queue`에 적재해 45분 잡이 순차 재시도한다.

---

## 기술 스택

Python 3.12 · FastAPI · aiogram 3.x · httpx(비동기) · PostgreSQL · Redis · APScheduler · pytest

## 명령어

```bash
docker compose up -d                  # PostgreSQL 16 + Redis 7 기동 (colima 환경이면 colima start 먼저)
uvicorn app.main:app --reload         # FastAPI 개발 서버
python -m app.bot                     # 텔레그램 봇 실행 (polling)
python -m app.scheduler               # 스케줄러 실행
python -m app.pipeline --sport mlb    # 봇 없이 파이프라인 직접 호출
pytest                                # 전체 테스트
pytest tests/test_engine.py -x -q     # 단일 파일 빠른 실행

# 프리페치 1회 수동 실행 (라이브 API 호출 — 비용 발생)
python -c "import asyncio; from app.scheduler import prefetch_job; asyncio.run(prefetch_job())"
```

## MCP 사용 규약

- **코드 탐색·수정은 Serena 우선**: `find_symbol` → `replace_symbol_body`로 심볼 단위 정밀
  편집. **파일 전체 재작성 금지.** collectors/research/engine 간 의존이 많으므로 참조 확인은
  `find_referencing_symbols`를 쓴다.
- **DB 상태 확인은 postgres MCP로 직접 쿼리**: 스키마 검증, 적재 확인(예: `odds_snapshots`가
  실제로 쌓이는지)은 코드 추측이 아니라 SELECT로 확인한다.
- **캐시 상태는 redis MCP**: 리서치 캐시 TTL·히트 여부 확인.
- **라이브러리 사용법이 불확실하면 context7로 문서 확인 후 작성.** aiogram 3.x, FastAPI,
  Anthropic SDK는 버전 간 API 변경이 잦다. 학습 데이터 기억으로 코딩하지 말 것.

## 코드 규칙

- 모든 외부 HTTP 호출은 **지수 백오프 3회 재시도 + 타임아웃** 필수 (httpx 기준).
- **새 기능은 테스트와 함께 커밋.** 테스트 없는 기능 코드 커밋 금지.
- 새 필터·가드를 추가할 때는 **반대 위험(정상 데이터 폐기)을 함께 측정**한다.
- **파라미터·설정은 임의로 바꾸지 않는다** (위 최상단 규칙). 변경 이력은
  [DISCIPLINE.md 부록: 파라미터 변경 이력](docs/DISCIPLINE.md)에 한 줄씩 남긴다.
  실사고: `max_tokens` 16000→32000 임의 상향이 SDK 비스트리밍 거부를 유발해
  judge 전 배치가 실패했고 전 슬레이트가 "판정 실패"로 나갔다.

---

## .env 변수

| 변수 | 용도 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_ADMIN_CHAT_ID` | 크레딧·키 오류 등 운영 알림 수신 채팅 |
| `ANTHROPIC_API_KEY` | Claude 판정(judge) 호출 |
| `JUDGE_MODEL` | 판정에 쓸 Claude 모델 ID |
| `PPLX_API_KEY` | Perplexity 딥서치 |
| `PPLX_API_MODE` | `chat`(현행 Sonar) \| `agent`(2026-09-27 이후 필수) |
| `PPLX_BASE_URL` / `PPLX_CHAT_PATH` / `PPLX_AGENT_PATH` | 엔드포인트 (마이그레이션용) |
| `PPLX_MODEL` / `PPLX_AGENT_PRESET` | 모델명 / Agent 프리셋 |
| `PPLX_MAX_CONCURRENCY` / `PPLX_MIN_INTERVAL` | 레이트리밋 방어 (기본 2 / 1.5초) |
| `XAI_API_KEY` | Grok Live Search |
| `ODDS_API_KEY` | The Odds API (배당) |
| `FOOTBALL_DATA_KEY` | football-data.org (메이저 12개 대회 무료) |
| `APIFOOTBALL_KEY` | API-Football (축구 스탯, 보조) |
| `BANKROLL_KRW` | 스테이크 환산 기준 자금 |
| `REPORT_MODE` | `live_conservative`(운영 보수) \| `research`(전량 표시) |

키가 하나라도 없으면 해당 모듈은 `mock_data/` 목 모드로 폴백한다.

---

## 실패에서 배운 것

- **모델 단독 밸류 픽은 실패했다** (8/22 빌라 3.30, 8/23 AGF 1.79). **실데이터 기반 픽은
  적중했다** (마치다). → 2-소스 룰.
- **"200 OK 산문 응답"이 재료 0인 분석을 만들었다.** JSON이 파싱된다고 데이터인 것은 아니다.
  → 검증 없는 신뢰 금지.
- **429를 크레딧 소진으로 오분류**해, 잔액이 남아 있는데 충전 알림을 보냈다.
  → 에러는 코드별로 정확히 분류하라.
- **원인을 추정으로 덮을 뻔했다.** 산문 응답 사고를 "429 탓"으로 추정했으나 실제로는
  모든 응답이 200 OK였다. → 실캐시·실로그를 열어 원인을 특정할 때까지 결론짓지 않는다.
- **한 방향만 고치면 반대편에서 새 오류가 난다.** 미확보 산문 차단 키워드를 넓혔더니
  실수치가 섞인 문장이 통째로 버려졌다. → 새 가드는 양방향으로 측정한다.
- **8/23 AGF 승은 실패했지만 더블찬스는 적중이었다.** → 승패 단식 편중 금지, 전 마켓 평가.
- **지시받지 않은 튜닝이 사고를 만들었다.** judge 안정화를 명분으로 `max_tokens`를 임의로
  두 배 올렸다가 SDK 제한에 걸려 전 슬레이트 판정이 0건이 됐다. 진짜 해법은 배치 축소였다.
  → 파라미터는 요청받았거나 필수일 때만, 전후값·이유·영향을 밝히고 바꾼다.
