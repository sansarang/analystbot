# ADJ-1 — 조정 변수를 DB 원자료에서 계산한다 (결정 A·B)

사용자 결정 2026-09-13(2차): **(C) 새 부착 단계**. `prob.py` 는 순수 함수로
유지하고 `adjust.attach(jg, pool)` 가 `_attach_market_spine` **직전**에
`jg` 에 키만 세팅한다. 수집기는 건드리지 않는다.

## 왜

실측 2026-09-13(결정 1 배포 직후, MLB 8경기): `adj_pp` 가 **전부 `{}`**.
`p_code == p_market` 이었다 — **코드가 시장을 그대로 베꼈다.** 이 상태로
CLV 를 쌓으면 평균 0 이 나오는 것이 당연하다(이기려는 시도가 없다).
원인은 `prob.adjustments` 가 읽는 키(`out_starters`·`bullpen_b2b` …)를
아무도 채우지 않는 것이었다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
prob.adjustments(jg)      jg 의 키만 읽는다 — pool 을 모른다(순수 유지)
_attach_market_spine      pipeline. 여기 **직전**에 attach 를 넣는다
원자료:
  lineups              status='confirmed'(=official) · batting_order · scratches
  pitcher_appearances  is_starter=false · game_id → games.starts_at 로 날짜
  games                starts_at · home/away · home_pitcher/away_pitcher
```
빌려 쓰는 원본:
| 무엇 | 원본 |
|---|---|
| official 상태값 | `collectors.lineups.STATUS_CONFIRMED` — **손으로 적지 않는다** |
| 조정 크기표 | `prob.ADJ_RULES` (결정 1-2) |
| 축소 계수 | `prob.ADJ_SHRINK` (결정 B) |

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `app/engine/adjust.py` | 새 모듈 — `ADJ_DEFS`(임계값 한 곳) · `attach` |
| `jg["out_starters"]` 등 | 조정 입력 키 |
| `jg["adj_inputs"]` | 원자료 요약(명단·일수) — 서술의 `reason_vars` 근거 |
| `jg["adj_missing"]` | **미계산 목록.** 0 과 구분한다 |
| `jg["adj_pending"]` | 타순이 official 이 아님 |
| `prob.ADJ_SHRINK` · `ADJ_SUM_CAP` | 결정 B — 표 × 0.5, 합계 ≤ 6%p |

🔴 **0 과 미계산을 구분한다.** 0 은 "조사했는데 없었다", 미계산은 "원자료가
   없어 못 쟀다"다. 섞으면 조정이 왜 안 붙었는지 영영 모른다.
🔴 **잠정 타순으로 조정하지 않는다** — 확정 뒤 뒤집힌다(`adj_pending`).

## ③ 리그·종목 분기

임계값 표(`ADJ_DEFS`) 하나에 야구·축구 값을 함께 두고 종목으로 조회한다.
분기문을 늘리지 않는다.

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **잠정 타순으로 조정** | `gate()` 가 `STATUS_CONFIRMED` 만 통과. 계약 |
| 🔴 미계산이 0 으로 섞인다 | `adj_missing` 분리. 계약 |
| 임계값이 함수 안에 흩어진다 | `ADJ_DEFS` 한 곳. 계약이 키 존재를 단언 |
| 상태 문자열을 베껴 적는다 | `STATUS_CONFIRMED` 임포트 계약 |
| 수집기가 함께 바뀐다 | 소스에 `gather.collect`·`bullpen_recent` 부재 계약 |
| 조정이 폭주한다 | `ADJ_SHRINK=0.5` + 합계 ≤ 6%p 계약 |

⚠️ **아직 못 하는 것 — `starter_changed`**
   T-24h 선발 스냅샷을 저장하는 테이블·트리거가 **없다**(`%snapshot%` 검색
   결과 `odds_snapshots` 뿐). 그래서 이 변수는 **미계산**으로 둔다.
   트리거 추가는 통합 지시문 Part A 의 몫이고 여기서 만들지 않는다.
⚠️ `midweek_away`(축구)도 대항전 일정 소스가 없어 **미계산**이다.

## ⑤ 사본

- 임계값·상태값·크기표를 두 곳에 적지 않는다.
- 날짜 변환을 새로 만들지 않는다 — `games.starts_at` 를 그대로 쓴다.
