# ODN-1-a — 경기 매칭 SQL 이 **타입 추론에 터진다**

## 왜

배포 뒤 ⑨ 첫 사이클 실측 2026-09-17:
```
asyncpg.exceptions.UndefinedFunctionError:
  operator does not exist: timestamp with time zone >= interval
```
`$2` 가 `BETWEEN $2 - interval … AND $2 + interval …` 처럼 **산술에만** 쓰여
asyncpg 가 타입을 정하지 못한다. `$2::timestamptz` 로 명시해야 한다.

🔴 **스위트도 계약도 통과했다** — SQL 을 실제로 돌리지 않기 때문이다.
   **⑨ 가 아니었으면 못 봤다.** ENGINEERING §4("등록 확인은 실행 확인이
   아니다")가 정확히 이 자리를 위해 있다.

## ① 이 함수/상태를 읽는 곳 **전부**

```
scheduler._match_oddsapinet   ← 고치는 곳(SQL 한 줄)
scheduler.oddsapinet_job      ← 유일한 호출자
```

## ② 깨뜨릴 수 있는 기존 동작

- 🔴 **결과가 같아야 한다.** 캐스트는 타입을 밝힐 뿐 범위를 안 바꾼다.
- 🔴 **다른 SQL 을 안 건드린다.** 같은 병이 있는지는 별개 문제다.
- ⚠️ 이 결함은 **키가 있어야만** 드러난다(없으면 조기 반환). 그래서 키를
  넣은 첫 실행에서 나왔다.

## ③ 되돌리기

커밋 1개 revert (한 줄).

## ④ 측정

①과 **같은 명령**이 통과하고, 운영에서 실제로 돌려 적재를 확인한다(⑨).

## ⑤ 계약

3건 — 캐스트가 있다 · BETWEEN 범위가 그대로다 · 다른 파라미터를 안 건드렸다.
