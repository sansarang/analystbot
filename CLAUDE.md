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
- 앙상블 확률: `p_final = 0.45 * p_model + 0.30 * p_market + 0.25 * p_claude`

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

키가 하나라도 없으면 해당 모듈은 `mock_data/` 목 모드로 폴백한다.
