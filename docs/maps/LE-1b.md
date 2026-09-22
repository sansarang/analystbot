# LE-1b — 역사 배당 적재기 (영향 지도 5문)

지시문 LE-1-4: "`tools/backfill_history.py`: LE-0 5번의 소스에서 (결과, 여러 북
open/close 배당)을 market_ledger 형식으로 적재. 소스·기간·행 수 보고."

## ⓪ LE-0 5번의 답 — 소스 실측 (이미 우리가 쓰고 있다)

`football-data.co.uk` 는 **이미 이 저장소가 받아 캐시한다**
(`app/models/soccer_elo.py` · `BASE`·`download_csvs()` · `CSV_DIR`).
robots 는 `[3] 감사 2026-09-21` 에서 **허용**으로 확인됐다(`Disallow:` 빈 값).

```
로컬 캐시: 34파일 · 19,289줄
  주요 8리그 × 4시즌   E0 E1 D1 SP1 I1 F1 N1 P1 × 2223 2324 2425 2526
  Extra 2리그 단일파일 DNK(덴마크) · JPN(J리그)
```

🔴 **개별 북 8개 × 개장/마감이 한 줄에 다 있다** — 실측 헤더:
```
개장  B365H/D/A · BWH/D/A · IWH/D/A · PSH/D/A · WHH/D/A · VCH/D/A · MaxH/D/A · AvgH/D/A
마감  B365CH/CD/CA · BWCH · IWCH · PSCH · WHCH · VCCH · MaxCH · AvgCH
총점  B365>2.5 · P>2.5 · Max>2.5 · Avg>2.5  (마감은 B365C>2.5 …)
핸디  AHh + B365AHH/AHA · PAHH/PAHA · MaxAH · AvgAH  (마감은 AHCh + …C…)
결과  FTHG · FTAG · FTR
```
LE-3(느린 북)·LE-4(개장→마감 이동)가 필요한 것이 **전부 여기 있다.**

⚠️ **야구 역사 배당 무료 소스는 이 단계에서 찾지 않았다.** 지시문이 든 후보
   (Retrosheet=결과만 · SportsBookReviewsOnline)는 배당 형식·최신성·이용조건을
   재야 하고, 그것은 **네트워크 조사**다. 야구는 실시간 축적분(한 달)으로 두고
   LE-4 를 축구로 먼저 돈다 — 그 사실을 여기 적는다.

## ① 파일

| 파일 | 무엇 | 신규 |
|---|---|---|
| `db/schema.sql` | `history_matches` · `history_prices` | 추가(멱등) |
| `tools/backfill_history.py` | CSV → 두 표. 소스·기간·행 수 보고 | 신규 |
| `tests/learning/test_le1b_history.py` | 계약 | 신규 |

🔴 **`soccer_elo` 의 다운로드를 재사용한다**(`download_csvs`·`CSV_DIR`·
   `_parse_date`·리그/시즌 목록). 같은 파일을 두 번 받지 않는다.
⚠️ 파싱은 **다시 쓴다** — `_parse_csv` 는 Elo 용이라 북별 배당을 버리고
   `_market_probs_from_row` 로 **하나의 확률**만 남긴다. 우리는 북별 원가가
   필요하다. 같은 함수를 고치면 Elo 가 깨진다.

## ② 테이블 / 잡

**새 표 둘.** 잡 없음(수동 도구).

🔴 **`odds_snapshots` 에 넣지 않는다.** 그 표는 `game_id REFERENCES games(id)`
   다 — 역사 경기를 넣으려면 `games` 에 19,289행을 만들어야 하고, 그것이
   **D32 가 겪은 사고**다(소급이 타국 동명 리그를 끌어와 `games` 오염 750행,
   백업 뜨고 삭제). 역사는 **격리된 표**에 둔다.

```
history_matches  (source, div, season, match_date, home, away, fthg, ftag, ftr)
                 UNIQUE(source, div, season, match_date, home, away)
history_prices   (match_id, book, phase[open|close], market, line, side, odds)
                 UNIQUE(match_id, book, phase, market, line, side)
```
⚠️ 정규화하는 이유: 한 표에 다 넣으면 홈·원정·결과가 ~100만 행에 반복된다.

## ③ 깨질 테스트

- 예상 없음(추가만). `db/schema.sql` 표 개수를 단정하는 계약이 있으면 걸린다 —
  전체 스위트로 확인한다(현재 5,572).

## ④ 롤백

`DROP TABLE history_prices, history_matches;` + 파일 삭제.
🔴 **기존 표를 한 줄도 건드리지 않으므로 되돌림이 완전하다.**
⚠️ 적재는 **멱등**이다(`ON CONFLICT DO NOTHING`). 두 번 돌려도 중복이 없다.

## ⑤ 완료 조건

지시문: "소스·기간·행 수 보고. 원본 파일은 캐시."
1. 리그·시즌·북별 적재 행 수 표
2. 개장/마감이 **둘 다** 있는 경기 수(= LE-4 가 쓸 표본)
3. 계약 통과 · 전체 스위트 통과 · 발송 0건
4. 🔴 **야구는 "없음"으로 적는다** — 찾지 못했다는 것을 결론으로 남긴다

## ⚠️ 누설에 대해 미리 (LE-2 가 잠글 것)

이 표에는 **마감 배당과 결과가 들어 있다.** 그건 정답지다.
🔴 `phase='close'` 와 `ftr`·`fthg`·`ftag` 는 **학습 입력이 될 수 없다.**
   LE-2 의 `test_no_future_feature` 가 그것을 잠근다. 여기서는 적재만 하고
   피처를 만들지 않는다 — 이 단계에 모델이 없는 이유다.
