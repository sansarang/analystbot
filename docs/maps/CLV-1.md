# CLV-1 — 판정 시각 배당과 마감 배당을 남긴다 (저장만)

사용자 지시 2026-09-13 (4단계, **코드 추가가 허가된 유일한 단계**):
"판정의 값어치를 측정할 유일한 지표를 남긴다. §4-1 '배당은 판정 입력 금지'는
그대로 — 여기서는 **저장만** 한다."

## 왜

실측 재측정(운영 원장 `is_final`·채점 완료 178경기):
```
실제 적중   54.8%
판정 확률   AUC 0.5122 [0.426, 0.601] · 브라이어 0.2537 (50%로 찍는 것보다 나쁘다)
시장 확률   AUC 0.6421 [0.545, 0.734] · 브라이어 0.2394   ← 유일하게 유의
```
적중률만으로는 판정이 **시장보다 나은지** 알 수 없다. CLV(판정 시각 배당 대비
마감 배당)는 그것을 재는 표준 지표이고, **지금 우리에겐 그 칸이 없다.**

기존 원장에 `odds`·`market_prob` 가 있지만 그것은 **한 시점의 값**이다
(`_fill_market` 이 나중에 채운다). 판정 시각과 마감 시각을 **구분해 두 번**
남기지 않으면 차이를 계산할 수 없다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
$ grep -rn "pick_ledger" app/
app/engine/pick_ledger.py   record_analysis(281 INSERT) · _fill_market(105) · grade_pending(312)
app/pipeline.py             record_analysis 호출
db/schema.sql:453           테이블 정의 · 499~506 인덱스 3개
clv_ledger (0행)            집계 뷰 — method·picks_with_close·beat_close·clv_avg…
```
배당 원본: `odds_snapshots` (42,675행 · game_id·captured_at·book·market·side·odds·provider)

빌려 쓰는 원본 — 새로 만들지 않는다:
| 무엇 | 원본 |
|---|---|
| 배당 값 | `odds_snapshots` (기존 크롤). **새 소스 금지** |
| 확률 변환 | `pick_ledger._market_cols` 가 쓰는 기존 변환 |
| 스키마 적용 | `app/db.py:apply_schema` — 기동 시 `db/schema.sql` 실행 |
| 컬럼 추가 관례 | `ALTER TABLE … ADD COLUMN IF NOT EXISTS` (schema.sql:26 등) |

## ② 만드는/바꾸는 상태

| 상태 | 성격 |
|---|---|
| `pick_ledger.odds_at_verdict` | 판정 시각 배당 (DOUBLE PRECISION) |
| `pick_ledger.odds_closing` | 마감(킥오프 직후) 배당 |
| `pick_ledger.clv` | 확률 기준 %p 차이 |
| `pick_ledger.record_clv()` | 두 시점을 기록하는 함수 |

🔴 **판정·서술·확신 어디에도 이 값을 넣지 않는다.** 저장 전용이다.
   `record_analysis` 의 판정 컬럼과 `_same_judgement` 비교에 넣지 않는다 —
   넣으면 배당이 바뀔 때마다 재판정 행이 생긴다.
🔴 **새 소스를 부르지 않는다.** `odds_snapshots` 에 이미 있는 값만 읽는다.
   없으면 NULL 이다 — 없는 것을 지어내지 않는다.

## ③ 리그·종목·경로 분기

분기 없음. 종목과 무관하게 `game_id` 로 `odds_snapshots` 를 읽는다.
배당이 없는 종목·경기는 NULL 로 남는다(축구 J1·K리그1 은 Odds 크레딧 소진이라 NULL).

## ④ 조용히 실패하는가

| 위험 | 대응 |
|---|---|
| 🔴 **배당이 판정에 새어 든다** ← 가장 큰 반대 위험 | 판정 경로가 이 컬럼을 읽지 않는지 계약(소스 grep) |
| 🔴 배당 변동이 재판정 행을 만든다 | `_same_judgement` 에 넣지 않는다. 계약 |
| 값이 없는데 0 으로 채운다 | 없으면 **NULL**. 계약 |
| 확률 변환을 두 곳에 적는다 | 기존 변환 재사용. 계약이 중복 정의 부재를 단언 |
| 마감 배당이 킥오프 **후** 값이라 오염 | 킥오프 시각 **이전** 마지막 스냅샷만 쓴다. 계약 |
| 기존 1,072행이 깨진다 | `ADD COLUMN IF NOT EXISTS` — 기존 행은 NULL |

⚠️ **아직 못 잰 것**: 오늘 MLB 슬레이트에서 실제로 몇 건이 채워지는가.
   `odds_snapshots` 가 경기별로 판정 시각 전후를 모두 담고 있는지는 미확인이다.

## ⑤ 이미 있는 사실을 다시 적는가

- 배당 소스를 새로 만들지 않는다 — `odds_snapshots` 그대로.
- 확률 변환식을 새로 쓰지 않는다 — 기존 `_market_cols` 경로.
- 스키마 적용 방식을 바꾸지 않는다 — `schema.sql` 에 `ADD COLUMN IF NOT EXISTS`.
