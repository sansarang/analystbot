# AnalystBot — 스포츠 분석 텔레그램 챗봇

**숫자는 API로**(statsapi.mlb.com, The Odds API, API-Football), **의견은 딥서치로**(Perplexity sonar-pro, Grok Live Search), **판정은 Claude로**(JUDGE_MODEL) 하는 분석 챗봇.

> ⚠️ **이 도구는 분석 정보 제공용입니다. 자동 베팅 집행 기능은 없으며, 베팅에 따른 손실 책임은 전적으로 사용자 본인에게 있습니다.**

## 설치

요구사항: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (PostgreSQL 16 + Redis 7)

```bash
git clone <repo> && cd analystbot
docker compose up -d          # PostgreSQL 16 + Redis 7 기동 (analyst/analyst/analystbot)
uv sync                       # 의존성 설치 (.venv)
uv run python -m app.db init  # 스키마 적용
uv run pytest                 # 전체 테스트 (외부 API 호출 없음 — 강제 목 모드)
```

## .env 설정

`.env.example`을 `.env`로 복사한 뒤 키를 채운다. **키가 하나라도 없으면 해당 모듈은 `mock_data/` 목 모드로 자동 전환**되며(로그에 MOCK/LIVE 표기), 크래시하지 않는다.

| 변수 | 용도 | 없을 때 |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 | CLI 시뮬레이터로 검증 |
| `ANTHROPIC_API_KEY` | Claude 판정·리포트·의도 파싱 | 결정적 목 판정 + 템플릿 리포트 |
| `PPLX_API_KEY` | Perplexity sonar-pro 전문가 픽 | 목 픽 |
| `XAI_API_KEY` | Grok Live Search 속보 | 목 속보 |
| `ODDS_API_KEY` | The Odds API 배당 | 목 배당 |
| `APIFOOTBALL_KEY` | API-Football 축구 | 목 일정 |
| `JUDGE_MODEL` | 판정 모델 ID (기본 `claude-opus-4-6`) | 404 시 사용 가능한 최상위 모델로 폴백 |

MLB(statsapi.mlb.com)는 무키 API라 기본 LIVE로 동작한다. 전 모듈 강제 목 모드는 `FORCE_MOCK=true`.

## 실키 전환 방법

1. `.env`에 해당 키 추가 (예: `ODDS_API_KEY=...`)
2. 프로세스 재시작 — 시작 로그에서 `module odds -> LIVE` 확인
3. 첫 실행 후 확인 사항: **"실키 전환 시 확인 항목"** 아래 체크리스트 참고

## 실행

```bash
docker compose up -d                                  # 인프라
uvicorn app.main:app --reload                         # FastAPI (GET /health, /report/mlb)
uv run python -m app.bot                              # 텔레그램 봇 (polling)
uv run python -m app.bot --simulate "/mlb"            # 토큰 없이 CLI 시뮬레이터
uv run python -m app.scheduler                        # 스케줄러 (프리페치·스냅샷·채점)
uv run python -m app.collectors.mlb --date 2026-08-22 # 일정 수동 적재
```

## 명령어 (텔레그램)

| 명령 | 동작 |
|---|---|
| `/start` | 안내 |
| `/mlb` | 오늘 MLB 슬레이트 분석 리포트 |
| `/soccer` | 오늘 EPL 분석 리포트 |
| `/today` | 오늘(KST) 리포트 |
| 자유 질문 | Haiku 의도 파싱(`{sport, date, teams, depth}`) 후 분석 |

리포트는 Redis에 30분 캐시된다(프리페치 후 즉시 응답). 04:00 KST 프리페치, 30분마다 배당 스냅샷, 13:00 KST 전날 채점(`expert_ledger` 자동 갱신).

## 실키 전환 시 확인 항목

- [ ] The Odds API 잔여 쿼터(응답 헤더 `x-requests-remaining`) — 30분 스냅샷 주기와 요금제 확인
- [ ] 팀명 매칭: The Odds API 팀명이 statsapi 팀명과 일치하는지 (`odds_snapshots` 미적재 경고 로그 확인)
- [ ] Perplexity 응답이 JSON 파싱되는지 (실패 시 1회 재요청 로그) 및 픽 정규화 성공률
- [ ] `JUDGE_MODEL` 유효성 — 404면 최상위 모델 폴백 로그 확인
- [ ] Anthropic 토큰 비용: 판정은 슬레이트당 1회 호출(캐시 활용), 프리페치 주기 점검
- [ ] API-Football 요금제의 리그 커버리지(league=39 EPL, season 파라미터)
- [ ] DB `odds_snapshots`가 실제로 쌓이는지: `SELECT count(*), max(captured_at) FROM odds_snapshots;`

## 아키텍처

```
collectors/  숫자 수집 (MLB statsapi · The Odds API · API-Football)
research/    딥서치 의견 (Perplexity sonar-pro · Grok Live Search)
engine/      value(EV·하프켈리) · consensus(ROI 가중) · parlay · judge(Claude)
pipeline.py  (일정+스탯 ∥ 배당 ∥ 딥서치) → 앙상블 p_final = 0.45·p_model + 0.30·p_market + 0.25·p_claude
bot/         aiogram 3.x (+ CLI 시뮬레이터)
scheduler.py APScheduler (KST 크론)
```

원칙: LLM 출력의 수치는 API 숫자와 교차검증하며 충돌 시 API가 이긴다. DB는 UTC 저장, 표시만 KST.
