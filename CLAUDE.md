# AnalystBot — 스포츠 분석 텔레그램 챗봇

**숫자는 API로**(statsapi.mlb.com, The Odds API, football-data.org),
**의견은 딥서치로**(Perplexity, Grok), **판정은 LLM으로** 하는 스포츠 분석 봇.
KBO·NPB·MLB 자동 발송. 축구는 요청 시에만.

## 이 문서의 규칙

**여기 남은 것은 "실제로 위반이 발생했던 규칙"뿐이다.** 기계가 강제할 수
있는 것은 `.claude/hooks/` 로 옮겼고 여기서 지웠다 — 두 곳에 적으면 사본이
되고, 사본은 원본이 바뀔 때 따라가지 않는다.

| 어디 | 무엇 |
|---|---|
| `.claude/hooks/` | 커밋·배포·위험 명령·**수정 단계** 게이트 (**기계가 강제**) |
| `app/engine/CLAUDE.md` | 판정 도메인 세칙 — 자료 구성·프롬프트 (조건부 로드) |
| [docs/DISCIPLINE.md](docs/DISCIPLINE.md) | 픽 선정·자금·적중 목표 |
| [docs/MODEL.md](docs/MODEL.md) | 확률 모델 · λ 아카이브 |
| [docs/ENGINEERING.md](docs/ENGINEERING.md) | 변경 절차 — 영향 지도 5문 |
| [docs/DATAFLOW.md](docs/DATAFLOW.md) | 수집→판정→발송 흐름 |
| [docs/RESEARCH_VALIDATION.md](docs/RESEARCH_VALIDATION.md) | 리서치 검증 |
| [docs/JUDGE_STABILITY_2026-09-05.md](docs/JUDGE_STABILITY_2026-09-05.md) | 판정 안정성 실측 |

---

## 🔒 동결과 한계값 — 여기서 지운 적 없다

⚠️ 아래 넷은 **모든 세션이 읽어야 하므로 루트에 둔다.** 하위 디렉토리
   CLAUDE.md 는 그 디렉토리를 만질 때만 로드된다 — 동결을 거기 두면
   다음 세션이 모르고 만진다. (계약 테스트가 이 위치를 강제한다)

**v1.3 동결(2026-09-03) → v1.4 동결(2026-09-05).
해제 조건은 리그별 `graded` 50건. 예외는 발송 중단급 P0 뿐이다** —
카드가 안 나가거나 틀린 값이 나가는 결함. "더 좋아질 것 같다"는 예외가 아니다.
동결 대상과 자료 구성은 → [app/engine/CLAUDE.md](app/engine/CLAUDE.md)

### 절대 완화하면 안 되는 한계값 ([MODEL.md](docs/MODEL.md) §1)

| 상수 | 값 |
|---|---|
| 승률 상한 (야구 / 축구) | **0.68 / 0.72** (야구는 0.32–0.68 절사) |
| 추천 하한 | **0.58** (원정 **0.63**) |
| 신호등 🟢 | **0.62** — **표시 전용**, 추천 게이트 아님 |
| 정확도 목표 | **58~60%** |

이 값을 넘는 산출은 "강한 픽"이 아니라 **모델이 틀렸다는 신호**다.
**배당은 판정·폼·서술의 입력에 절대 넣지 않는다** (판정 확정 후 후처리만).

### 코드 변경 절차

**모든 코드 변경은 [docs/ENGINEERING.md](docs/ENGINEERING.md) 를 따른다** —
착수 전 영향 지도 5문 → 5대 반복 결함 체크 → 계약 테스트 → 1변경 1배포 →
첫 사이클 실측. **절차를 생략한 커밋은 반려 대상이다.**
배포 전 **자기검증 3문**: (a) 손으로 적은 사실이 있는가 (b) 틀렸을 때
알려줄 테스트가 있는가 (c) 기존 경로를 건드리는가.

## ⚠️ 추측 금지 — 조사하고 측정한 뒤에 말한다

**원인을 말하기 전에 이 순서를 지켜라. 건너뛴 결론은 보고하지 마라.**

1. **해당 코드 본문을 연다.** 함수 시그니처·반환 키·컬럼명·상수는 추측하지 않는다.
2. **데이터·로그로 재현하거나 측정한다.**
3. 외부 지표·라이브러리 정의가 걸리면 **웹 검색으로 확인**한다.
4. 그 다음에 결론을 말한다. **측정하지 않았으면 "아직 모른다"고 쓴다.**

**"~때문일 것이다"·"아마"·"~로 보인다"를 원인 보고에 쓰지 마라.**
상태값(SUCCESS·200 OK·테스트 통과)은 **의도한 것이 동작한다는 증거가 아니다.**

**절제 실험(하나씩 빼보기) 한 번이 추론 세 번보다 정확하다.**

> 실사고 2026-08-26 하루: 추측으로 낸 결론이 **연속 8건** 틀렸다.
> 실사고 2026-09-05: `railway variable set` 이 조용히 실패했는데 출력을
> 버리고 "설정 완료"라고 보고했다. **명령을 보냈다 ≠ 반영됐다.**
> 같은 날: 감시 오탐을 고친다며 측정 없이 규칙을 넓혀 검증 184→137건으로
> 악화시켰다. 실데이터로 전후를 재고서야 알았다.

## ⚠️ 완료 보고는 증거 3요소

**① 테스트 수치(실제 출력의 숫자) ② 실행 시각 ③ 커밋 해시.**
셋이 없으면 "완료"라고 쓰지 마라. Stop 훅이 검사한다.

## ⚠️ 3파일 이상이면 계획서를 먼저 낸다

3개 이상의 파일을 건드리는 작업은 **Plan Mode 로 계획 → 승인 → 구현**이다.
큰 변경을 즉흥으로 시작하면 중간에 방향이 바뀌고, 그때 이미 되돌리기 어렵다.

---

## 서버 접근 — `railway run` 은 운영에 닿지 않는다

🔴 **`railway run` 은 "서버에서 돌린다"가 아니다.** 운영 **환경변수만** 주입해
**로컬에서** 실행한다. 그래서 `REDIS_URL` 이 `.railway.internal` 을 가리켜도
로컬에서는 닿지 않는다. `tools/resend`·`tools/unblock` 이 이것 때문에
운영 상태를 바꾸지 못했다 (실측 2026-09-05).

컨테이너 안에서 도는 것은 **`railway ssh`** 뿐이다. 키는 컨테이너의
`authorized_keys` 가 아니라 **Railway 계정**에 등록한다.

```bash
railway ssh keys list
railway ssh -i ~/.ssh/id_ed25519_new --project d29edc63-4309-4656-a8af-543b8b773437 \
  --environment production --service analystbot-scheduler "python /tmp/probe.py"
# 긴 스크립트는 base64 로: B=$(base64 < p.py | tr -d '\n'); ... "echo $B | base64 -d > /tmp/p.py && python /tmp/p.py"
```

## 배포 — 커밋은 배포가 아니다

이 저장소에는 git remote 가 없다. `tools/deploy.sh` **수동 배포**다.
게이트(미커밋 차단·빌드 검증·안정성 스모크·SUCCESS 확인)는 스크립트와 훅이
자동으로 건다 — 사람이 기억할 것은 **스케줄러를 먼저 배포한다**는 것뿐이다
(기동 시 DB 스키마를 적용하므로).

```bash
tools/deploy.sh all          # 스케줄러 → 봇 → 크롤러
```

| 서비스 | 실행 | 역할 |
|---|---|---|
| `analystbot-scheduler` | `python -m app.scheduler` | 프리페치·점수 적재·스키마 적용 |
| `analystbot-bot` | `python -m app.bot` | 텔레그램 응답 |
| `analystbot-crawler` | `crawler -interval 10m` | Go 크롤러 |

> 실사고 2026-08-27: 로컬에 **14커밋**을 쌓는 동안 서버는 하루 전 코드로 돌았다.
> 실사고 2026-08-25: 봇이 **26커밋 뒤처진 코드**로 하루 넘게 돌았다.
> → `/health` 로 커밋 해시를 대조하라.

---

## 절대 규칙

1. **자동 베팅 집행 기능 금지.** 분석·추천까지만.
2. **LLM 출력의 수치는 API 숫자와 교차검증. 충돌 시 API가 이긴다.**
3. **API 키가 없으면 목 모드로 동작.** 키 부재로 크래시하지 않는다.
4. **DB는 UTC 저장, 표시만 KST.**
5. **날짜 기준: MLB=미국 동부 오늘, 축구=KST 오늘. 표기는 항상 KST.**
6. **재료 없으면 분석 생성 금지.** "수집 실패"로 정직하게 표시한다.

## 지시받지 않은 파라미터 변경 금지

`max_tokens`·배치 크기·타임아웃·모델명·임계값·프롬프트는 **요청받았거나 버그
수정에 필수인 경우에만** 바꾼다. 바꿨다면 **(a) 전후값 (b) 이유 (c) 영향 범위**를
보고에 명시하라.

> 실사고: judge 안정화를 명분으로 `max_tokens` 를 임의로 두 배 올렸다가
> SDK 제한에 걸려 **전 슬레이트 판정이 0건**이 됐다. 진짜 해법은 배치 축소였다.

## 사본 금지

**시스템에 이미 존재하는 사실은 다시 적지 말고 원본을 읽어라.**
주기·담당 리그·활성 소스·임계값을 손으로 옮겨 적는 순간 그것은 미래의 오탐이다.

> 실사고 2026-09-02: 워치독 오탐 4건이 전부 같은 실수였다 — 코드에 있는
> 값을 문서·상수로 베껴 적었고, 원본이 바뀔 때 사본은 따라가지 않았다.

## 신규 모듈은 태어나는 날 계약 테스트와 함께 태어난다

"나중에 테스트를 붙이겠다"는 배포는 그 모듈이 틀렸을 때 **알려줄 사람이 없다**는 뜻이다.
새 필터·가드를 추가할 때는 **반대 위험(정상 데이터 폐기)을 함께 측정**한다.

---

## 발송 규율

- **1차 카드는 발송 창이 열리면 타순 전이라도 보낸다.** 판정이 있으면
  `🕐 잠정 · 보드만`으로 먼저 내고, 타순이 뜨면 재판정해 수정 카드를 보낸다.
- **첫 카드 보장선 T-30 · 수정 카드는 시작 15분 전에 손에 있어야 한다.**
  KBO 재판정 마감 T-20, NPB 풀 T-15 · 경량 T-10.
- **목표는 발송률 100%이고, 미발송은 전건에 사유가 붙어야 한다 —
  "조용한 0"은 결함이다.** 결과는 `dispatch:{sport}:{date}` 에 쌓인다.

> 실측 2026-09-01: KBO 5경기 판정이 14:00 에 끝나 캐시에 있는데도 카드가
> 한 장도 안 나갔다. 사용자는 "봇이 죽었나"와 "라인업이 안 떴다"를
> 구분할 수 없었다.

## 워치독 (5분) — 읽기만 한다

**경보 코드 목록은 여기 적지 않는다** — 원본은 `app/alerts.py` 의
`WATCHDOG_CODES` 다. 손으로 적은 사본 넷이 전부 달랐고, 라벨이 빠진 코드 둘이
`점검 필요` 로 나가고 있었다(실측 2026-09-08 WD-1). 지금 목록을 보려면:

```bash
python -c "from app.alerts import WATCHDOG_CODES as W; [print(k,'·',v) for k,v in W.items()]"
```

**차단을 자동으로 풀지 않는다** — 잔액 없는 키로 계속 호출하면 요금만 태운다.
해제는 사람이 `tools/unblock` 으로 한다 (`railway ssh` 로 실행).

## 외부 API 에러 분류 (`app/collectors/base.py`)

| 상황 | 분류 | 사용자 알림 |
|---|---|---|
| 402 / 잔액 문구 | credit | 충전 안내 |
| 401·403 | auth | 키 교체 안내 |
| **429** | rate_limit | **없음** — 내부 재시도·큐 재처리 |
| 5xx | server | 없음 (지수 백오프) |

알림은 반드시 `notify_api_error(exc)` 로 라우팅한다 — `notify_quota` 직접 호출 금지.

> 실사고: **429를 크레딧 소진으로 오분류**해, 잔액이 남아 있는데 충전 알림을 보냈다.

## 리서치 신뢰 규칙

- **LLM 응답은 200 OK 여도 데이터가 아닐 수 있다 — `validate.py` 통과 전 사용 금지.**
- **새 리서치 필드를 추가할 때 `validate.py` 정책을 함께 정의한다** —
  문장 필터 대상인지 전량 폐기 대상인지.
- ⚠️ **Perplexity Agent API 마이그레이션 기한: 2026-09-27.**
  `PPLX_API_MODE=agent` 로 코드 수정 없이 전환한다.

> 실사고: **"200 OK 산문 응답"이 재료 0인 분석을 만들었다.** JSON 이 파싱된다고
> 데이터인 것은 아니다.

---

## 명령어

```bash
docker compose up -d                  # PostgreSQL + Redis (colima 환경이면 colima start 먼저)
PYTHONPATH=. uv run pytest tests -q   # 전체 스위트 (커밋·배포 게이트가 이걸 본다)
python -m app.pipeline --sport mlb    # 파이프라인 직접 호출
.claude/hooks/selftest.sh             # 훅 자기검증
```

## MCP 규약

- **코드 탐색·수정은 Serena 우선** — `find_symbol` → `replace_symbol_body`.
  **파일 전체 재작성 금지.** 참조 확인은 `find_referencing_symbols`.
  ⚠️ `go` 는 일부러 뺐다 (모듈이 `crawler/go.mod` 에 있어 gopls 가 실패한다).
- **DB 상태는 postgres MCP 로 SELECT** — 코드 추측이 아니라 쿼리로 확인한다.
  ⚠️ 로컬 DB 다. 운영은 `railway ssh`.
- **라이브러리 사용법이 불확실하면 context7** — aiogram 3.x·FastAPI·Anthropic SDK 는
  버전 간 API 변경이 잦다. 학습 기억으로 코딩하지 말 것.

## .env 주요 변수

| 변수 | 용도 |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ADMIN_CHAT_ID` | 봇 토큰 / 운영 알림 채팅 |
| `JUDGE_PROVIDER` / `FREE_JUDGE_MODEL` / `FREE_FORM_MODEL` | 판정 사슬 (앞이 주전) |
| `LLM_SEED` | 판정 호출 고정 seed (0 이면 미전송) |
| `GEMINI_API_KEY` / `NVIDIA_API_KEY` / `GROQ_API_KEY` / `OPENROUTER_API_KEY` | 무료 사슬 |
| `ANTHROPIC_API_KEY` / `JUDGE_MODEL` | 구 Judge (축구·`--old`) |
| `PPLX_API_KEY` / `PPLX_API_MODE` | Perplexity |
| `XAI_API_KEY` / `ODDS_API_KEY` / `FOOTBALL_DATA_KEY` | Grok / 배당 / 축구 |
| `BANKROLL_KRW` / `REPORT_MODE` | 자금 / 표시 모드 |

키가 없으면 해당 모듈은 `mock_data/` 목 모드로 폴백한다.
