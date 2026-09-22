# LE-1a — 결정 원장과 지표 계산기 (영향 지도 5문)

지시문 `learning_engine_0922` LE-1. **봇의 "기억"이다** — 이게 없으면 학습이
없다. LE-1 을 둘로 쪼갠다:

| 단위 | 무엇 | 왜 쪼개나 |
|---|---|---|
| **LE-1a (지금)** | 원장 구조 · 지표 모듈 · 리포트 도구 · **우리 실시간 원장의 첫 표** | LE-2 를 푸는 데 필요한 전부 |
| LE-1b (다음) | 역사 적재기(`tools/backfill_history.py`) | LE-0 5번(소스 형식·기간)이 선행. LE-2 완료 조건이 이걸 요구한다 |

## ① 파일

| 파일 | 무엇 | 신규? |
|---|---|---|
| `db/schema.sql` | `decision_ledger` 테이블 + `market_prices` 뷰 | 추가(멱등) |
| `config/learning.yaml` | 문턱·창 크기 — **전부 미검증 사전값** 주석 | 신규 |
| `app/learning/__init__.py` | 빈 패키지 | 신규 |
| `app/learning/metrics.py` | **순수 함수** — Brier · 로그손실 · 보정 10분위 · CLV · ROI · 집계 | 신규 |
| `app/learning/prices.py` | 가격 조회 — `close_price` 등. **종가 규칙의 단일 원본** | 신규 |
| `app/learning/decisions.py` | `decision_ledger` 읽기/쓰기 + `pick_ledger` 로부터 소급 적재 | 신규 |
| `tools/ledger_report.py` | 표 출력. 30건 미만 셀은 "표본 부족"만 | 신규 |
| `tests/learning/test_le1_ledger.py` | T-LE1 계약 4건 + 추가 | 신규 |

🔴 **`market_ledger` 를 새로 만들지 않는다.** `odds_snapshots`(180,152행)이 이미
그 모양이다 — `(game_id, captured_at, book, market, side, line, odds, provider,
snap_tag)`. 지시문도 "뷰로 감싸도 되나"를 허용한다. 빠진 것은 `implied_p` 하나이고
그건 **계산값**이라 저장하지 않는다(devig 구현이 두 벌이 되면 어긋난다).

🔴 **`decision_ledger` 는 새로 만드는 것이 정당하다.** `pick_ledger` 는
"한 행 = 한 경기 한 판정"이고 지시문은 "한 행 = 한 후보(엔진·마켓·라인·방향)"다.
한 경기에 총점·핸디 후보가 같이 나오면 `pick_ledger` 로는 담을 자리가 없다.

## ② 테이블 / 잡

**추가**: `decision_ledger` · 뷰 `market_prices`. 새 잡 **없음**(리포트는 수동 도구).
**읽기만**: `odds_snapshots` · `games` · `pick_ledger`.
⚠️ `pick_ledger`·`odds_snapshots` 에 **컬럼을 추가하지 않는다.**

### 🔴 `side` 가 팀명이다 — 이게 뷰의 핵심 일이다

실측: `odds_snapshots.side` 는 `'Minnesota Twins'`·`'NC Dinos'`·`'Draw'` 처럼
**팀명**이다(`'home'`/`'away'` 가 아니다). 뷰가 `games.home`/`games.away` 와
맞춰 `side_norm ∈ {home, draw, away}` 를 만든다.
⚠️ 이름 대조는 D15 가 세 번 오탐을 낸 자리다. **정확 일치만** 쓰고 못 맞추면
   `side_norm = NULL` 로 둔다 — 추측해서 채우지 않는다. 계약이 NULL 비율을 본다.

### 🔴 종가 규칙을 두 벌로 만들지 않는다

원본은 `pick_ledger._CLV_SNAP` 이다:
```sql
captured_at <= LEAST($2::timestamptz, g.starts_at)  ORDER BY captured_at DESC LIMIT 1
```
`app/learning/prices.close_price` 가 **같은 규칙**을 쓰고, 계약
`test_close_rule_matches_clv_snap` 이 두 곳의 문구 일치를 잠근다. 어느 한쪽이
바뀌면 계약이 깨진다.

### devig 는 기존 것을 쓴다

`app/flow/odds_math.devig_2way` · `devig_3way`. **새로 짜지 않는다.**
(저장소에 devig 구현이 이미 넷 있다 — `market_baseline.devig_two_way`,
`value.devig`, `market_edge.devig_ok`, `odds_math.devig_*`. 다섯째를 만들지 않는다.)

## ③ 깨질 테스트

- 예상 **없음** — 기존 코드를 수정하지 않는다(추가만).
- `db/schema.sql` 을 읽는 계약이 있으면 표 개수 단정에 걸릴 수 있다. 전체
  스위트로 확인한다(현재 5,552 passed).
- ⚠️ 새 패키지 `app/learning/` 이 생기므로 "모듈 목록"을 단정하는 계약이
  있으면 깨진다. 돌려서 확인한다.

## ④ 롤백

- 코드: 파일 7개 삭제.
- DB: `DROP TABLE decision_ledger; DROP VIEW market_prices;` — **기존 표를
  건드리지 않으므로 되돌림이 완전하다.**
- ⚠️ `decision_ledger` 소급 적재는 **멱등**으로 만든다(같은 키 재실행 시 중복
  없음). 아니면 되돌리기가 "행 삭제"가 되어 위험해진다.

## ⑤ 완료 조건 (지시문 원문)

> "역사 적재 행 수(리그·시즌·북별) · 우리 실시간 원장의 Brier·CLV 첫 표
> (봇 판정 79% 복사 상태의 기준선으로 남긴다)."

LE-1a 가 내는 것:
1. `pick_ledger` → `decision_ledger` 소급 적재 행 수(엔진·종목별)
2. **우리 실시간 원장의 첫 표** — 엔진·종목·마켓별 Brier · 로그손실 ·
   보정 10분위 · CLV · ROI. 30건 미만 셀은 "표본 부족".
3. 계약 T-LE1 4건 + 추가 통과 · 전체 스위트 통과 · 발송 0건
4. 🔴 **이 표가 기준선이다** — 나중에 "나아졌다"를 말할 근거.

역사 적재 행 수는 **LE-1b** 가 낸다. LE-1 은 둘이 끝나야 닫힌다.

## ⚠️ 미리 적어 두는 한계

- 우리 DB 배당은 **한 달치**(MLB 8/22~ · KBO·NPB 9/2~ · 축구 8/23~).
  open+close 둘 다 있는 종료 경기: MLB 96 · 축구 39 · NPB 31 · KBO 23.
  → **CLV 표의 대부분 셀이 "표본 부족"으로 나올 것이다.** 그게 정직한 첫 표다.
- `p_home`(=옛 Judge) 은 지표에 **쓰지 않는다.** `p_code` 를 쓴다(D55).
  `calibration.py` 는 이 단위에서 건드리지 않는다 — 그쪽은 별도 결정이다.
